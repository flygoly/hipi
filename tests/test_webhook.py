"""Tests for webhook HMAC signing."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from hipi.daemon.forward import SmsForwarder
from hipi.db.models import Database


def test_webhook_signature_headers():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        db.set_sms_forward_webhook_secret("test-secret")
        forwarder = SmsForwarder(db)

        captured: dict = {}

        def fake_urlopen(req, timeout=10):
            captured["req"] = req
            resp = MagicMock()
            resp.status = 200
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda *a: None
            return resp

        with patch("urllib.request.urlopen", fake_urlopen):
            forwarder._post_webhook("https://example.com/hook", {"event": "test"})

        req = captured["req"]
        assert req.has_header("X-HiPi-Signature")
        assert req.get_header("X-HiPi-Signature", "").startswith("sha256=")
        assert req.has_header("X-HiPi-Timestamp")
        db.close()
