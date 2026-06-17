"""SMS PDU and encoding helpers for ModemManager properties."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ModemManager MM_SMS_ENCODING_*
ENCODING_7BIT = 1
ENCODING_8BIT = 2
ENCODING_UCS2 = 3


def decode_sms_body(props: dict[str, Any]) -> str:
    """Extract human-readable SMS body from ModemManager SMS properties."""
    text = props.get("Text")
    if text:
        return str(text)

    data = props.get("Data")
    if not data:
        return ""

    raw = bytes(int(b) for b in data)
    encoding = int(props.get("Encoding", 0))

    if encoding == ENCODING_UCS2:
        decoded = _decode_ucs2(raw)
        if decoded:
            return decoded

    if encoding == ENCODING_7BIT:
        decoded = _decode_gsm7(raw)
        if decoded:
            return decoded

    pdu_text = _decode_full_pdu(raw)
    if pdu_text:
        return pdu_text

    if encoding == ENCODING_8BIT:
        try:
            return raw.decode("utf-8", errors="replace")
        except Exception:
            pass

    return raw.decode("utf-8", errors="replace")


def _decode_ucs2(raw: bytes) -> str:
    try:
        return raw.decode("utf-16-be", errors="strict")
    except UnicodeDecodeError:
        try:
            return raw.decode("utf-16-le", errors="replace")
        except UnicodeDecodeError:
            return ""


def _decode_gsm7(raw: bytes) -> str:
    try:
        from smspdu import gsm0338

        codec = gsm0338.Codec()
        text, _length = codec.decode(raw)
        return str(text)
    except Exception as exc:
        logger.debug("GSM-7 decode failed: %s", exc)
        return ""


def _decode_full_pdu(raw: bytes) -> str:
    pdu_hex = raw.hex().upper()
    if len(pdu_hex) < 4:
        return ""

    try:
        from smspdu import SMS_DELIVER, SMS_SUBMIT

        for cls in (SMS_DELIVER, SMS_SUBMIT):
            try:
                pdu = cls.fromPDU(pdu_hex)
                user_data = getattr(pdu, "user_data", None)
                if user_data:
                    return str(user_data)
            except Exception:
                continue
    except ImportError:
        logger.debug("smspdu not installed")

    try:
        from io import BytesIO

        from smspdudecoder.easy import read_incoming_sms

        return str(read_incoming_sms(pdu_hex).get("text", "") or "")
    except Exception:
        pass

    return ""
