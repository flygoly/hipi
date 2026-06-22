"""Tests for SMS import and status updates with mocked ModemManager."""

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from hipi.daemon.pdu import ENCODING_UCS2
from hipi.daemon.sms import SMS_STATE_RECEIVED, SMS_STATE_SENT, SMS_STATE_SENDING, SmsService
from hipi.db.models import Database


class FakeSmsModem:
    def __init__(self) -> None:
        self._props: dict[str, dict[str, Any]] = {}

    def set_sms(self, path: str, **props: Any) -> None:
        self._props[path] = props

    def get_sms_properties(self, path: str) -> dict[str, Any]:
        return self._props[path]

    def list_modem_sms_paths(self, modem_path: str) -> list[str]:
        return list(self._props.keys())

    def has_messaging(self, modem_path: str) -> bool:
        return True

    def watch_properties(self, path: str, iface: str, callback: Any) -> None:
        pass

    def get_primary_modem_path(self) -> str:
        return "/modem/0"


def test_import_inbound_ucs2_dedupes_modem_sms_id():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        mm = FakeSmsModem()
        path = "/org/freedesktop/ModemManager1/SMS/1"
        raw = "你好".encode("utf-16-be")
        mm.set_sms(
            path,
            State=SMS_STATE_RECEIVED,
            Number="+8613800138000",
            Text="",
            Data=list(raw),
            Encoding=ENCODING_UCS2,
        )

        sms = SmsService(mm, db)
        first = sms._import_sms(path, emit_event=False, modem_path="/modem/0")
        second = sms._import_sms(path, emit_event=False, modem_path="/modem/0")

        assert first is not None
        assert first.body == "你好"
        assert second is None
        assert len(db.list_messages()) == 1
        db.close()


def test_update_existing_outbound_to_sent():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        mm = FakeSmsModem()
        path = "/org/freedesktop/ModemManager1/SMS/2"
        db.add_message(
            "+861111",
            "hello",
            "outbound",
            status="sending",
            modem_sms_id=path,
        )
        mm.set_sms(path, State=SMS_STATE_SENT, Number="+861111", Text="hello", Encoding=1)

        updates: list = []
        sms = SmsService(mm, db, on_message_updated=updates.append)
        sms._maybe_update_existing(path, mm.get_sms_properties(path), SMS_STATE_SENT, emit_event=True)

        msg = db.get_message_by_modem_sms_id(path)
        assert msg and msg.status == "sent"
        assert len(updates) == 1
        db.close()


def test_sending_state_watches_without_import():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        mm = FakeSmsModem()
        path = "/org/freedesktop/ModemManager1/SMS/3"
        mm.set_sms(path, State=SMS_STATE_SENDING, Number="+861111", Text="wait", Encoding=1)

        sms = SmsService(mm, db)
        result = sms._import_sms(path, emit_event=False)
        assert result is None
        assert path in sms._watched_sms
        db.close()
