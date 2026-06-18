"""Inbound SMS forwarding (text only, not MMS)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

from hipi.db.models import Database, Message
from hipi.daemon.sms import SmsService
from hipi.util import normalize_number

logger = logging.getLogger(__name__)

_PDU_SKIP_TYPES = {3, 4}


def is_forwardable_sms(props: dict[str, Any], body: str) -> bool:
    """Return True for plain text SMS; exclude MMS/binary/status reports."""
    if not body or not body.strip():
        return False
    if body.startswith("[HiPi转发]"):
        return False

    pdu_type = int(props.get("PduType", 0))
    if pdu_type in _PDU_SKIP_TYPES:
        return False

    encoding = int(props.get("Encoding", 0))
    if encoding == 2 and not body.strip():
        return False

    data = props.get("Data") or []
    if len(data) > 512 and not props.get("Text"):
        return False

    return True


class SmsForwarder:
    def __init__(self, db: Database) -> None:
        self._db = db

    def maybe_forward(
        self,
        msg: Message,
        props: dict[str, Any],
        sms: SmsService,
        modem_path: str,
    ) -> None:
        if msg.direction != "inbound":
            return
        if not self._db.is_sms_forward_enabled():
            return
        if not is_forwardable_sms(props, msg.body):
            logger.debug("Skip forward for non-text/MMS-like message from %s", msg.peer)
            return

        name = self._db.resolve_name(msg.peer)
        sender = f"{name} ({msg.peer})" if name else msg.peer
        text = f"[HiPi转发] 来自 {sender}: {msg.body}"

        target = self._db.get_sms_forward_target()
        if target:
            target = normalize_number(target)
            if target and target != msg.peer:
                result = sms.send_sms(modem_path, target, text)
                if result.get("ok"):
                    logger.info("Forwarded SMS from %s to %s", msg.peer, target)
                else:
                    logger.warning("SMS forward failed: %s", result.get("error"))

        webhook = (self._db.get_sms_forward_webhook() or "").strip()
        if webhook:
            self._post_webhook(
                webhook,
                {
                    "event": "inbound_sms",
                    "from": msg.peer,
                    "from_name": name,
                    "body": msg.body,
                    "timestamp": msg.timestamp,
                    "message_id": msg.id,
                },
            )

    def _post_webhook(self, url: str, payload: dict[str, Any]) -> None:
        try:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers = {"Content-Type": "application/json; charset=utf-8"}
            secret = (self._db.get_sms_forward_webhook_secret() or "").strip()
            if secret:
                ts = str(int(time.time()))
                sig = hmac.new(
                    secret.encode("utf-8"),
                    f"{ts}.{body.decode('utf-8')}".encode("utf-8"),
                    hashlib.sha256,
                ).hexdigest()
                headers["X-HiPi-Timestamp"] = ts
                headers["X-HiPi-Signature"] = f"sha256={sig}"

            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                logger.info("Webhook %s responded %s", url, resp.status)
        except urllib.error.URLError as exc:
            logger.warning("Webhook POST failed: %s", exc)
