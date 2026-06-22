"""SMS send/receive via ModemManager or direct AT (EC801E ECM)."""

from __future__ import annotations

import logging
from typing import Any, Callable

import dbus

from hipi.daemon.at_serial import AT_MODEM_PREFIX, AtSerialClient, AtSerialError
from hipi.daemon.modem import ModemManagerClient, ModemManagerError, SMS_IFACE
from hipi.daemon.pdu import decode_sms_body
from hipi.db.models import Database, Message
from hipi.util import normalize_number

logger = logging.getLogger(__name__)

# ModemManager MM_SMS_STATE_*
SMS_STATE_UNKNOWN = 0
SMS_STATE_STORED = 1
SMS_STATE_RECEIVING = 2
SMS_STATE_RECEIVED = 3
SMS_STATE_SENDING = 4
SMS_STATE_SENT = 5

INBOUND_IMPORT_STATES = {SMS_STATE_STORED, SMS_STATE_RECEIVED}
OUTBOUND_IMPORT_STATES = {SMS_STATE_SENT}

BACKEND_MM = "mm"
BACKEND_AT = "at"
BACKEND_NONE = "none"


class SmsService:
    def __init__(
        self,
        mm: ModemManagerClient,
        db: Database,
        on_message: Callable[[Message], None] | None = None,
        on_message_updated: Callable[[Message], None] | None = None,
        on_inbound: Callable[[Message, dict[str, Any], str], None] | None = None,
        at: AtSerialClient | None = None,
    ) -> None:
        self._mm = mm
        self._db = db
        self._at = at or AtSerialClient()
        self._on_message = on_message
        self._on_message_updated = on_message_updated
        self._on_inbound = on_inbound
        self._watched_sms: set[str] = set()
        self._backend_cache: dict[str, str] = {}

    def get_backend(self, modem_path: str) -> str:
        if modem_path.startswith(AT_MODEM_PREFIX):
            return BACKEND_AT
        cached = self._backend_cache.get(modem_path)
        if cached:
            return cached
        if self._mm.has_messaging(modem_path):
            backend = BACKEND_MM
        elif self._at.find_port():
            backend = BACKEND_AT
        else:
            backend = BACKEND_NONE
        self._backend_cache[modem_path] = backend
        logger.info("SMS backend for %s: %s", modem_path, backend)
        return backend

    def sms_available(self, modem_path: str) -> bool:
        return self.get_backend(modem_path) != BACKEND_NONE

    def at_port(self) -> str | None:
        return self._at.active_port() or self._at.find_port()

    def unlock_sim_at(self, pin: str) -> None:
        self._at.unlock_sim(pin)

    def reset_backends(self) -> None:
        self._backend_cache.clear()

    def sync_from_modem(self, modem_path: str, *, emit_events: bool = False) -> list[Message]:
        backend = self.get_backend(modem_path)
        if backend == BACKEND_MM:
            return self._sync_from_mm(modem_path, emit_events=emit_events)
        if backend == BACKEND_AT:
            return self._sync_from_at(modem_path, emit_events=emit_events)
        return []

    def _sync_from_mm(self, modem_path: str, *, emit_events: bool) -> list[Message]:
        imported: list[Message] = []
        try:
            for sms_path in self._mm.list_modem_sms_paths(modem_path):
                msg = self._import_sms(sms_path, emit_event=emit_events, modem_path=modem_path)
                if msg:
                    imported.append(msg)
        except dbus.DBusException as exc:
            logger.warning("MM SMS sync failed: %s", exc)
        return imported

    def _sync_from_at(self, modem_path: str, *, emit_events: bool) -> list[Message]:
        imported: list[Message] = []
        try:
            for item in self._at.list_messages():
                msg = self._import_at_message(item, emit_event=emit_events, modem_path=modem_path)
                if msg:
                    imported.append(msg)
        except AtSerialError as exc:
            logger.warning("AT SMS sync failed: %s", exc)
        return imported

    def _import_at_message(
        self,
        item: dict[str, Any],
        *,
        emit_event: bool,
        modem_path: str,
    ) -> Message | None:
        sms_id = str(item.get("modem_sms_id", ""))
        if not sms_id:
            return None
        if self._db.has_modem_sms(sms_id):
            return None

        peer = normalize_number(str(item.get("peer", "")))
        body = str(item.get("body", "") or "")
        direction = str(item.get("direction", "inbound"))
        status = str(item.get("status", "received"))

        msg = self._db.add_message(
            peer=peer,
            body=body,
            direction=direction,
            status=status,
            modem_path=modem_path,
            modem_sms_id=sms_id,
        )
        if emit_event and self._on_message:
            self._on_message(msg)
        if emit_event and direction == "inbound" and self._on_inbound:
            props = {"Text": body, "Number": peer, "PduType": 0}
            self._on_inbound(msg, props, modem_path)
        return msg

    def _import_sms(
        self,
        sms_path: str,
        *,
        emit_event: bool = True,
        modem_path: str | None = None,
    ) -> Message | None:
        props = self._mm.get_sms_properties(sms_path)
        state = int(props.get("State", 0))

        if self._db.has_modem_sms(sms_path):
            self._maybe_update_existing(sms_path, props, state, emit_event=emit_event)
            return None

        if not self._should_import(state):
            if state in (SMS_STATE_SENDING, SMS_STATE_RECEIVING):
                self._watch_sms(sms_path)
            return None

        body = decode_sms_body(props)
        number = str(props.get("Number", "") or "")
        direction = "inbound" if state in INBOUND_IMPORT_STATES else "outbound"
        peer = normalize_number(number)
        status = self._status_for_state(state, direction)

        msg = self._db.add_message(
            peer=peer,
            body=body,
            direction=direction,
            status=status,
            modem_path=sms_path,
            modem_sms_id=sms_path,
        )
        self._watch_sms(sms_path)
        if emit_event and self._on_message:
            self._on_message(msg)
        if (
            emit_event
            and direction == "inbound"
            and self._on_inbound
            and modem_path
        ):
            self._on_inbound(msg, props, modem_path)
        return msg

    def _maybe_update_existing(
        self,
        sms_path: str,
        props: dict[str, Any],
        state: int,
        *,
        emit_event: bool,
    ) -> None:
        existing = self._db.get_message_by_modem_sms_id(sms_path)
        if not existing:
            return

        new_status = self._status_for_state(state, existing.direction)
        body = decode_sms_body(props) or existing.body
        changed = existing.status != new_status or (body and body != existing.body)
        if not changed:
            return

        self._db.update_message(
            existing.id,
            status=new_status,
            body=body if body else None,
        )
        if emit_event and self._on_message_updated:
            updated = self._db.get_message_by_id(existing.id)
            if updated:
                self._on_message_updated(updated)

    def _watch_sms(self, sms_path: str) -> None:
        if sms_path in self._watched_sms:
            return
        self._watched_sms.add(sms_path)

        def on_change(changed: dict[str, Any]) -> None:
            if "State" not in changed and "Text" not in changed and "Data" not in changed:
                return
            props = self._mm.get_sms_properties(sms_path)
            state = int(props.get("State", 0))
            if self._db.has_modem_sms(sms_path):
                self._maybe_update_existing(sms_path, props, state, emit_event=True)
            else:
                self._import_sms(sms_path, emit_event=True)

        self._mm.watch_properties(sms_path, SMS_IFACE, on_change)

    @staticmethod
    def _should_import(state: int) -> bool:
        return state in INBOUND_IMPORT_STATES or state in OUTBOUND_IMPORT_STATES

    @staticmethod
    def _status_for_state(state: int, direction: str) -> str:
        if state == SMS_STATE_SENT:
            return "sent"
        if state == SMS_STATE_SENDING:
            return "sending"
        if state in INBOUND_IMPORT_STATES:
            return "received"
        return "failed" if state == SMS_STATE_UNKNOWN else "received"

    def handle_sms_added(self, sms_path: str, modem_path: str | None = None) -> Message | None:
        if not modem_path:
            modem_path = self._mm.get_primary_modem_path() or ""
        if self.get_backend(modem_path or "") != BACKEND_MM:
            return None
        return self._import_sms(
            sms_path,
            emit_event=True,
            modem_path=modem_path or None,
        )

    def send_sms(self, modem_path: str, number: str, text: str) -> dict[str, Any]:
        backend = self.get_backend(modem_path)
        if backend == BACKEND_AT:
            return self._send_sms_at(modem_path, number, text)
        if backend == BACKEND_MM:
            return self._send_sms_mm(modem_path, number, text)
        return {"ok": False, "error": "SMS not available (no MM Messaging or AT port)"}

    def _send_sms_at(self, modem_path: str, number: str, text: str) -> dict[str, Any]:
        peer = normalize_number(number)
        if not peer:
            return {"ok": False, "error": "Invalid phone number"}
        try:
            self._at.send_sms(peer, text)
            msg = self._db.add_message(
                peer=peer,
                body=text,
                direction="outbound",
                status="sent",
                modem_path=modem_path,
            )
            return {"ok": True, "message": msg.to_dict(), "backend": BACKEND_AT}
        except AtSerialError as exc:
            logger.warning("AT SMS send failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    def _send_sms_mm(self, modem_path: str, number: str, text: str) -> dict[str, Any]:
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
            self._watch_sms(sms_path)
            return {"ok": True, "message": msg.to_dict(), "backend": BACKEND_MM}
        except dbus.DBusException as exc:
            logger.exception("Failed to send SMS")
            return {"ok": False, "error": str(exc)}
        except ModemManagerError as exc:
            return {"ok": False, "error": str(exc)}
