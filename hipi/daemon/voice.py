"""Voice call handling via ModemManager."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

import dbus

from hipi.daemon.modem import CALL_IFACE, ModemManagerClient
from hipi.db.models import CallRecord, Database
from hipi.util import normalize_number

logger = logging.getLogger(__name__)

CALL_STATE_UNKNOWN = 0
CALL_STATE_DIALING = 1
CALL_STATE_RINGING_OUT = 2
CALL_STATE_RINGING_IN = 3
CALL_STATE_ACTIVE = 4
CALL_STATE_HELD = 5
CALL_STATE_WAITING = 6
CALL_STATE_TERMINATED = 7

STATE_NAMES = {
    CALL_STATE_UNKNOWN: "unknown",
    CALL_STATE_DIALING: "dialing",
    CALL_STATE_RINGING_OUT: "ringing-out",
    CALL_STATE_RINGING_IN: "ringing-in",
    CALL_STATE_ACTIVE: "active",
    CALL_STATE_HELD: "held",
    CALL_STATE_WAITING: "waiting",
    CALL_STATE_TERMINATED: "terminated",
}


class VoiceService:
    def __init__(
        self,
        mm: ModemManagerClient,
        db: Database,
        on_call_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._mm = mm
        self._db = db
        self._on_call_event = on_call_event
        self._active_calls: dict[str, int] = {}
        self._active_since: dict[str, datetime] = {}
        self._watched_calls: set[str] = set()

    def dial(self, modem_path: str, number: str) -> dict[str, Any]:
        peer = normalize_number(number)
        if not peer:
            return {"ok": False, "error": "Invalid phone number"}
        voice = self._mm.get_voice_interface(modem_path)
        try:
            call_path = str(voice.CreateCall({"number": peer}))
            record = self._db.add_call(
                peer=peer, direction="outbound", state="dialing", modem_call_path=call_path
            )
            self._track_call(call_path, record.id)
            self._watch_call(call_path)
            self._emit({"type": "call_started", "call": record.to_dict(), "path": call_path})
            return {"ok": True, "call": record.to_dict(), "path": call_path}
        except dbus.DBusException as exc:
            logger.exception("Dial failed")
            return {"ok": False, "error": str(exc)}

    def answer(self, call_path: str) -> dict[str, Any]:
        try:
            call = dbus.Interface(
                dbus.SystemBus().get_object("org.freedesktop.ModemManager1", call_path),
                CALL_IFACE,
            )
            call.Accept()
            self._update_call_state(call_path, "active")
            return {"ok": True}
        except dbus.DBusException as exc:
            return {"ok": False, "error": str(exc)}

    def hangup(self, call_path: str | None = None) -> dict[str, Any]:
        try:
            if call_path:
                paths = [call_path]
            else:
                modem = self._mm.get_primary_modem_path()
                if not modem:
                    return {"ok": False, "error": "No modem"}
                paths = self._mm.list_modem_call_paths(modem)

            for path in paths:
                props = self._mm.get_call_properties(path)
                state = int(props.get("State", CALL_STATE_TERMINATED))
                if state != CALL_STATE_TERMINATED:
                    call = dbus.Interface(
                        dbus.SystemBus().get_object("org.freedesktop.ModemManager1", path),
                        CALL_IFACE,
                    )
                    call.Hangup()
                    self._update_call_state(path, "terminated")
            return {"ok": True}
        except dbus.DBusException as exc:
            return {"ok": False, "error": str(exc)}

    def handle_call_added(self, call_path: str) -> CallRecord | None:
        props = self._mm.get_call_properties(call_path)
        state_val = int(props.get("State", 0))
        state = STATE_NAMES.get(state_val, "unknown")
        number = str(props.get("Number", "") or "")
        direction_val = int(props.get("Direction", 0))
        direction = "inbound" if direction_val == 1 else "outbound"

        self._watch_call(call_path)

        if call_path in self._active_calls:
            self._update_call_state(call_path, state)
            return None

        record = self._db.add_call(
            peer=normalize_number(number),
            direction=direction,
            state=state,
            modem_call_path=call_path,
        )
        self._track_call(call_path, record.id)
        event_type = "incoming_call" if state == "ringing-in" else "call_started"
        self._emit({"type": event_type, "call": record.to_dict(), "path": call_path})
        return record

    def poll_calls(self, modem_path: str) -> None:
        for call_path in self._mm.list_modem_call_paths(modem_path):
            props = self._mm.get_call_properties(call_path)
            state_val = int(props.get("State", 0))
            state = STATE_NAMES.get(state_val, "unknown")
            if call_path in self._active_calls:
                self._update_call_state(call_path, state)
            elif state == CALL_STATE_RINGING_IN:
                self.handle_call_added(call_path)

    def list_active_calls(self, modem_path: str) -> list[dict[str, Any]]:
        result = []
        for call_path in self._mm.list_modem_call_paths(modem_path):
            props = self._mm.get_call_properties(call_path)
            state_val = int(props.get("State", 0))
            if state_val == CALL_STATE_TERMINATED:
                continue
            result.append(
                {
                    "path": call_path,
                    "number": str(props.get("Number", "")),
                    "state": STATE_NAMES.get(state_val, "unknown"),
                    "direction": "inbound" if int(props.get("Direction", 0)) == 1 else "outbound",
                }
            )
        return result

    def _track_call(self, call_path: str, call_id: int) -> None:
        self._active_calls[call_path] = call_id

    def _watch_call(self, call_path: str) -> None:
        if call_path in self._watched_calls:
            return
        self._watched_calls.add(call_path)

        def on_change(changed: dict[str, Any]) -> None:
            if "State" not in changed:
                return
            state_val = int(changed["State"])
            state = STATE_NAMES.get(state_val, "unknown")
            if call_path in self._active_calls:
                self._update_call_state(call_path, state)
            elif state == "ringing-in":
                self.handle_call_added(call_path)

        self._mm.watch_properties(call_path, CALL_IFACE, on_change)

    def _update_call_state(self, call_path: str, state: str) -> None:
        call_id = self._active_calls.get(call_path)
        if not call_id:
            return

        if state == "active" and call_path not in self._active_since:
            self._active_since[call_path] = datetime.now(timezone.utc)

        ended = None
        duration = None
        if state == "terminated":
            ended = datetime.now(timezone.utc).isoformat()
            started = self._active_since.pop(call_path, None)
            if started:
                duration = int((datetime.now(timezone.utc) - started).total_seconds())
            self._active_calls.pop(call_path, None)

        self._db.update_call(call_id, state=state, ended_at=ended, duration_sec=duration)
        self._emit({"type": "call_state", "path": call_path, "state": state})

    def _emit(self, event: dict[str, Any]) -> None:
        if self._on_call_event:
            self._on_call_event(event)
