"""Tests for voice call service and call DB deduplication."""

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from hipi.daemon.voice import CALL_STATE_RINGING_IN, CALL_STATE_TERMINATED, VoiceService
from hipi.db.models import Database


class FakeModemManager:
    def __init__(self) -> None:
        self._props: dict[str, dict[str, Any]] = {}
        self._watchers: dict[str, list] = {}

    def set_call(self, path: str, **props: Any) -> None:
        self._props[path] = props

    def get_call_properties(self, path: str) -> dict[str, Any]:
        return self._props.get(path, {})

    def list_modem_call_paths(self, modem_path: str) -> list[str]:
        return list(self._props.keys())

    def watch_properties(self, path: str, iface: str, callback: Any) -> None:
        self._watchers.setdefault(path, []).append(callback)

    def emit_state(self, path: str, state: int) -> None:
        if path in self._props:
            self._props[path]["State"] = state
        for cb in self._watchers.get(path, []):
            cb({"State": state})


def test_get_call_by_modem_path():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        path = "/org/freedesktop/ModemManager1/Call/1"
        record = db.add_call("+861111", "inbound", "ringing-in", modem_call_path=path)
        found = db.get_call_by_modem_path(path)
        assert found and found.id == record.id
        assert not db.get_call_by_modem_path("/missing")
        db.close()


def test_handle_call_added_dedupes_by_modem_path():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        mm = FakeModemManager()
        path = "/org/freedesktop/ModemManager1/Call/1"
        db.add_call("+861111", "inbound", "ringing-in", modem_call_path=path)
        mm.set_call(path, State=CALL_STATE_RINGING_IN, Number="+861111", Direction=1)

        events: list[dict] = []
        voice = VoiceService(mm, db, on_call_event=events.append)
        result = voice.handle_call_added(path)

        assert result is not None
        assert len(db.list_calls()) == 1
        assert not events  # existing record: no duplicate incoming event
        db.close()


def test_call_terminated_emits_event():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        mm = FakeModemManager()
        path = "/org/freedesktop/ModemManager1/Call/2"
        record = db.add_call("+862222", "outbound", "active", modem_call_path=path)
        mm.set_call(path, State=4, Number="+862222", Direction=0)

        events: list[dict] = []
        voice = VoiceService(mm, db, on_call_event=events.append)
        voice._track_call(path, record.id)
        voice._active_since[path] = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        )
        voice._update_call_state(path, "terminated")

        updated = db.list_calls(limit=1)[0]
        assert updated.state == "terminated"
        assert updated.ended_at
        assert events and events[-1]["state"] == "terminated"
        db.close()


def test_incoming_call_includes_contact_name():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        db.add_contact("Bob", "+861111")
        mm = FakeModemManager()
        path = "/org/freedesktop/ModemManager1/Call/3"
        mm.set_call(path, State=CALL_STATE_RINGING_IN, Number="+861111", Direction=1)

        events: list[dict] = []
        voice = VoiceService(mm, db, on_call_event=events.append)
        voice.handle_call_added(path)

        assert events[0]["type"] == "incoming_call"
        assert events[0]["call"]["name"] == "Bob"
        db.close()
