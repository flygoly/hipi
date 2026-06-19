"""Tests for SMS forwarder maybe_forward integration."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from hipi.daemon.forward import SmsForwarder
from hipi.db.models import Database, Message


def _inbound_msg(db: Database, peer: str = "+8613800138000", body: str = "你好") -> Message:
    return db.add_message(peer, body, "inbound", status="received")


def test_maybe_forward_sends_sms_to_target():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        db.set_sms_forward_enabled(True)
        db.set_sms_forward_target("13900139000")
        forwarder = SmsForwarder(db)
        sms = MagicMock()
        sms.send_sms.return_value = {"ok": True}
        msg = _inbound_msg(db)

        forwarder.maybe_forward(msg, {"PduType": 1, "Encoding": 3}, sms, "/modem/0")

        sms.send_sms.assert_called_once()
        args = sms.send_sms.call_args[0]
        assert args[0] == "/modem/0"
        assert args[1] == "+8613900139000"
        assert "[HiPi转发]" in args[2]
        assert "你好" in args[2]
        db.close()


def test_maybe_forward_skips_self_target():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        db.set_sms_forward_enabled(True)
        db.set_sms_forward_target("+8613800138000")
        forwarder = SmsForwarder(db)
        sms = MagicMock()
        msg = _inbound_msg(db)

        forwarder.maybe_forward(msg, {"PduType": 1}, sms, "/modem/0")

        sms.send_sms.assert_not_called()
        db.close()


def test_maybe_forward_includes_contact_name():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        db.add_contact("张三", "13800138000")
        db.set_sms_forward_enabled(True)
        db.set_sms_forward_target("13900139000")
        forwarder = SmsForwarder(db)
        sms = MagicMock()
        sms.send_sms.return_value = {"ok": True}
        msg = _inbound_msg(db)

        forwarder.maybe_forward(msg, {"PduType": 1}, sms, "/modem/0")

        text = sms.send_sms.call_args[0][2]
        assert "张三" in text
        db.close()


def test_maybe_forward_posts_webhook():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        db.set_sms_forward_enabled(True)
        db.set_sms_forward_webhook("https://example.com/hook")
        forwarder = SmsForwarder(db)
        sms = MagicMock()
        msg = _inbound_msg(db)
        captured: dict = {}

        def fake_urlopen(req, timeout=10):
            captured["body"] = req.data.decode("utf-8")
            resp = MagicMock()
            resp.status = 200
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda *a: None
            return resp

        with patch("hipi.daemon.forward.urllib.request.urlopen", fake_urlopen):
            forwarder.maybe_forward(msg, {"PduType": 1}, sms, "/modem/0")

        payload = json.loads(captured["body"])
        assert payload["event"] == "inbound_sms"
        assert payload["body"] == "你好"
        sms.send_sms.assert_not_called()
        db.close()
