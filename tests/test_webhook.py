"""Tests for webhook HMAC signing and verification."""

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from hipi.daemon.forward import SmsForwarder
from hipi.db.models import Database
from hipi.webhook import sign_webhook_payload, verify_webhook_request, verify_webhook_signature


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

        with patch("hipi.daemon.forward.urllib.request.urlopen", fake_urlopen):
            forwarder._post_webhook("https://example.com/hook", {"event": "test"})

        req = captured["req"]
        assert req.has_header("X-hipi-signature")
        assert req.get_header("X-hipi-signature", "").startswith("sha256=")
        assert req.has_header("X-hipi-timestamp")
        db.close()


def test_sign_and_verify_roundtrip():
    body = json.dumps({"event": "inbound_sms", "body": "你好"}, ensure_ascii=False).encode()
    ts, sig = sign_webhook_payload("secret-key", body, timestamp=1_700_000_000)
    assert verify_webhook_signature(
        "secret-key", body, ts, sig, max_age_sec=999_999, now=1_700_000_000
    )


def test_verify_rejects_wrong_secret():
    body = b'{"event":"test"}'
    ts, sig = sign_webhook_payload("right", body, timestamp=1_700_000_000)
    assert not verify_webhook_signature(
        "wrong", body, ts, sig, max_age_sec=999_999, now=1_700_000_000
    )


def test_verify_rejects_stale_timestamp():
    body = b'{"event":"test"}'
    now = int(time.time())
    ts, sig = sign_webhook_payload("secret", body, timestamp=now - 600)
    assert not verify_webhook_signature("secret", body, ts, sig, max_age_sec=300, now=now)


def test_verify_webhook_request_headers_case_insensitive():
    body = b'{"event":"test"}'
    ts, sig = sign_webhook_payload("secret", body, timestamp=1_700_000_000)
    headers = {"X-HiPi-Timestamp": ts, "X-HiPi-Signature": sig}
    assert verify_webhook_request(
        "secret", body, headers, max_age_sec=999_999, now=1_700_000_000
    )
    lower = {"x-hipi-timestamp": ts, "x-hipi-signature": sig}
    assert verify_webhook_request(
        "secret", body, lower, max_age_sec=999_999, now=1_700_000_000
    )
