"""Inbound SMS forwarding (text only, not MMS)."""

from __future__ import annotations

import logging
from typing import Any

from hipi.db.models import Database, Message
from hipi.daemon.sms import SmsService
from hipi.util import normalize_number

logger = logging.getLogger(__name__)

# ModemManager MM_SMS_PDU_TYPE — skip non-user-text types
_PDU_SKIP_TYPES = {3, 4}  # status report, command


def is_forwardable_sms(props: dict[str, Any], body: str) -> bool:
    """Return True for plain text SMS; exclude MMS/binary/status reports."""
    if not body or not body.strip():
        return False
    if body.startswith("[HiPi转发]"):
        return False

    pdu_type = int(props.get("PduType", 0))
    if pdu_type in _PDU_SKIP_TYPES:
        return False

    # MMS/WAP push often has 8-bit encoding with empty decoded text
    encoding = int(props.get("Encoding", 0))
    if encoding == 2 and not body.strip():  # 8-bit without text
        return False

    # Very large binary payloads are unlikely to be SMS text
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
        target = self._db.get_sms_forward_target()
        if not target:
            return
        target = normalize_number(target)
        if not target or target == msg.peer:
            return
        if not is_forwardable_sms(props, msg.body):
            logger.debug("Skip forward for non-text/MMS-like message from %s", msg.peer)
            return

        name = self._db.resolve_name(msg.peer)
        sender = f"{name} ({msg.peer})" if name else msg.peer
        text = f"[HiPi转发] 来自 {sender}: {msg.body}"
        result = sms.send_sms(modem_path, target, text)
        if result.get("ok"):
            logger.info("Forwarded SMS from %s to %s", msg.peer, target)
        else:
            logger.warning("SMS forward failed: %s", result.get("error"))
