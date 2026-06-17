"""Tests for SMS PDU decoding."""

from hipi.daemon.pdu import ENCODING_UCS2, decode_sms_body


def test_decode_text_property():
    body = decode_sms_body({"Text": "你好", "Data": [], "Encoding": ENCODING_UCS2})
    assert body == "你好"


def test_decode_ucs2_data():
    raw = "你好".encode("utf-16-be")
    body = decode_sms_body(
        {
            "Text": "",
            "Data": list(raw),
            "Encoding": ENCODING_UCS2,
        }
    )
    assert body == "你好"


def test_decode_empty():
    assert decode_sms_body({}) == ""
