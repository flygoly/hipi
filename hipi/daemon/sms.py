"""SMS send/receive via ModemManager."""

from __future__ import annotations

import logging
from typing import Any, Callable

import dbus

from hipi.daemon.modem import ModemManagerClient, ModemManagerError, SMS_IFACE
from hipi.db.models import Database, Message
from hipi.util import normalize_number

logger = logging.getLogger(__name__)

SMS_STATE_RECEIVED = 3
SMS_STATE_SENT = 4


class SmsService:
    def __init__(
        self,
        mm: ModemManagerClient,
        db: Database,
        on_message: Callable[[Message], None] | None = None,
    ) -> None:
        self._mm = mm
        self._db = db
        self._on_message = on_message

    def sync_from_modem(self, modem_path: str) -> list[Message]:
        imported: list[Message] = []
        for sms_path in self._mm.list_modem_sms_paths(modem_path):
            msg = self._import_sms(sms_path)
            if msg:
                imported.append(msg)
        return imported

    def _import_sms(self, sms_path: str) -> Message | None:
        if self._db.has_modem_sms(sms_path):
            return None
        props = self._mm.get_sms_properties(sms_path)
        state = int(props.get("State", 0))
        if state not in (SMS_STATE_RECEIVED, SMS_STATE_SENT):
            return None

        body = str(props.get("Text", "") or "")
        number = str(props.get("Number", "") or "")
        direction = "inbound" if state == SMS_STATE_RECEIVED else "outbound"
        peer = normalize_number(number)
        status = "received" if direction == "inbound" else "sent"

        msg = self._db.add_message(
            peer=peer,
            body=body,
            direction=direction,
            status=status,
            modem_path=sms_path,
            modem_sms_id=sms_path,
        )
        if self._on_message:
            self._on_message(msg)
        return msg

    def handle_sms_added(self, sms_path: str) -> Message | None:
        return self._import_sms(sms_path)

    def send_sms(self, modem_path: str, number: str, text: str) -> dict[str, Any]:
        peer = normalize_number(number)
        if not peer:
            return {"ok": False, "error": "Invalid phone number"}

        messaging = self._mm.get_messaging_interface(modem_path)
        try:
            sms_path = messaging.Create(
                {
                    "number": peer,
                    "text": text,
                }
            )
            sms_path = str(sms_path)
            sms_obj = dbus.Interface(
                dbus.SystemBus().get_object("org.freedesktop.ModemManager1", sms_path),
                SMS_IFACE,
            )
            sms_obj.Send()

            msg = self._db.add_message(
                peer=peer,
                body=text,
                direction="outbound",
                status="sending",
                modem_path=sms_path,
                modem_sms_id=sms_path,
            )
            return {"ok": True, "message": msg.to_dict()}
        except dbus.DBusException as exc:
            logger.exception("Failed to send SMS")
            return {"ok": False, "error": str(exc)}
        except ModemManagerError as exc:
            return {"ok": False, "error": str(exc)}
