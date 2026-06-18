"""Webhook HMAC signing and verification for SMS forward events."""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Mapping

SIGNATURE_PREFIX = "sha256="
TIMESTAMP_HEADER = "X-HiPi-Timestamp"
SIGNATURE_HEADER = "X-HiPi-Signature"


def sign_webhook_payload(
    secret: str,
    body: bytes,
    timestamp: int | None = None,
) -> tuple[str, str]:
    """Return (timestamp, signature_header_value) for a JSON webhook body."""
    ts = str(timestamp if timestamp is not None else int(time.time()))
    message = f"{ts}.{body.decode('utf-8')}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return ts, f"{SIGNATURE_PREFIX}{digest}"


def verify_webhook_signature(
    secret: str,
    body: bytes,
    timestamp: str,
    signature: str,
    *,
    max_age_sec: int = 300,
    now: int | None = None,
) -> bool:
    """Verify HiPi webhook HMAC signature and reject stale timestamps."""
    if not secret or not timestamp or not signature:
        return False
    if not signature.startswith(SIGNATURE_PREFIX):
        return False

    try:
        ts = int(timestamp)
    except ValueError:
        return False

    current = now if now is not None else int(time.time())
    if abs(current - ts) > max_age_sec:
        return False

    expected_ts, expected_sig = sign_webhook_payload(secret, body, timestamp=ts)
    if expected_ts != timestamp:
        return False
    return hmac.compare_digest(expected_sig, signature)


def verify_webhook_request(
    secret: str,
    body: bytes,
    headers: Mapping[str, str],
    *,
    max_age_sec: int = 300,
    now: int | None = None,
) -> bool:
    """Verify using HTTP headers (case-insensitive keys)."""
    normalized = {k.lower(): v for k, v in headers.items()}
    return verify_webhook_signature(
        secret,
        body,
        normalized.get(TIMESTAMP_HEADER.lower(), ""),
        normalized.get(SIGNATURE_HEADER.lower(), ""),
        max_age_sec=max_age_sec,
        now=now,
    )
