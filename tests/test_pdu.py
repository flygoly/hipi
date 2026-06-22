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


def test_decode_gsm7_data():
    from smspdudecoder.codecs import GSM

    text = "HiPi"
    raw = bytes.fromhex(GSM.encode(text))
    body = decode_sms_body({"Text": "", "Data": list(raw), "Encoding": 1})
    assert body == text


def test_decode_full_incoming_pdu():
    pdu_hex = "07916407058099F9040B916407950303F100008921222140140004D4E2940A"
    raw = bytes.fromhex(pdu_hex)
    body = decode_sms_body({"Text": "", "Data": list(raw), "Encoding": 0})
    assert body == "TEST"


def test_decode_gsm7_packed_hex():
    raw = bytes.fromhex("C8F71D14969741F977FD07")
    body = decode_sms_body({"Text": "", "Data": list(raw), "Encoding": 1})
    assert body == "How are you?"
