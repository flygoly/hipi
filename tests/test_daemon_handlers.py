"""Smoke tests for HiPiDaemon RPC handlers (mocked modem)."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from hipi.daemon.server import HiPiDaemon
from hipi.status_file import read_status_file


def _daemon_with_db(tmp: str) -> HiPiDaemon:
    daemon = HiPiDaemon()
    daemon.db.close()
    daemon.db = __import__("hipi.db.models", fromlist=["Database"]).Database(Path(tmp) / "test.db")
    daemon.mm = MagicMock()
    daemon.mm.get_primary_modem_path.return_value = "/modem/0"
    status = MagicMock()
    status.to_dict.return_value = {"state": "registered", "signal_quality": 80}
    daemon.mm.get_modem_status.return_value = status
    daemon._init_services()
    return daemon


def test_new_message_event_includes_contact_name():
    with tempfile.TemporaryDirectory() as tmp:
        daemon = _daemon_with_db(tmp)
        daemon.db.add_contact("Alice", "+861111")
        msg = daemon.db.add_message("+861111", "hi", "inbound")
        captured: list = []

        async def _capture(event, payload):
            captured.append((event, payload))

        def _run_coro(coro, _loop):
            asyncio.run(coro)
            return MagicMock()

        with patch("asyncio.run_coroutine_threadsafe", side_effect=_run_coro):
            with patch.object(daemon.rpc, "broadcast_event", side_effect=_capture):
                daemon._on_message(msg)

        assert captured[0][0] == "new_message"
        assert captured[0][1]["name"] == "Alice"
        daemon.db.close()


def test_mark_read_updates_unread_in_status_file():
    with tempfile.TemporaryDirectory() as tmp:
        status_path = Path(tmp) / "hipi-status.json"
        with patch("hipi.status_file.STATUS_FILE", status_path):
            daemon = _daemon_with_db(tmp)
            daemon.db.add_message("+861111", "hi", "inbound", status="received")
            daemon._handle_mark_read({"peer": "+861111"})
            status = read_status_file()
            assert status is not None
            assert status["unread_sms"] == 0
            daemon.db.close()


def test_call_terminated_triggers_audio_teardown():
    with tempfile.TemporaryDirectory() as tmp:
        daemon = _daemon_with_db(tmp)
        daemon.audio.teardown_call_audio = MagicMock()
        daemon._on_call_event({"type": "call_state", "path": "/call/1", "state": "terminated"})
        daemon.audio.teardown_call_audio.assert_called_once()
        daemon.db.close()


def test_call_active_does_not_teardown_audio():
    with tempfile.TemporaryDirectory() as tmp:
        daemon = _daemon_with_db(tmp)
        daemon.audio.teardown_call_audio = MagicMock()
        daemon._on_call_event({"type": "call_state", "path": "/call/1", "state": "active"})
        daemon.audio.teardown_call_audio.assert_not_called()
        daemon.db.close()


def test_set_sms_forward_requires_target_or_webhook():
    with tempfile.TemporaryDirectory() as tmp:
        daemon = _daemon_with_db(tmp)
        result = daemon._handle_set_sms_forward({"enabled": True, "target": "", "webhook": ""})
        assert not result.get("ok")
        daemon.db.close()
