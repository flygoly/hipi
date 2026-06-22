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
        from smspdudecoder.codecs import UCS2

        return UCS2.decode(raw.hex().upper())
    except Exception:
        try:
            return raw.decode("utf-16-be", errors="strict")
        except UnicodeDecodeError:
            try:
                return raw.decode("utf-16-le", errors="replace")
            except UnicodeDecodeError:
                return ""


def _decode_gsm7(raw: bytes) -> str:
    try:
        from smspdudecoder.codecs import GSM

        return GSM.decode(raw.hex().upper(), strip_padding=True)
    except Exception as exc:
        logger.debug("GSM-7 decode failed: %s", exc)
        return ""


def _decode_full_pdu(raw: bytes) -> str:
    pdu_hex = raw.hex().upper()
    if len(pdu_hex) < 4:
        return ""

    try:
        from smspdudecoder.easy import read_incoming_sms, read_outgoing_sms

        for reader in (read_incoming_sms, read_outgoing_sms):
            try:
                result = reader(pdu_hex)
                content = result.get("content", "")
                if content:
                    return str(content)
            except Exception:
                continue
    except ImportError:
        logger.debug("smspdudecoder not installed")
    except Exception as exc:
        logger.debug("PDU decode failed: %s", exc)

    return ""
