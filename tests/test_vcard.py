"""Tests for vCard import/export."""

from hipi.vcard import export_vcards, parse_vcard


SAMPLE = """BEGIN:VCARD
VERSION:3.0
FN:张三
TEL;TYPE=CELL:13800138000
NOTE:同事
END:VCARD
BEGIN:VCARD
VERSION:3.0
FN:Bob Lee
TEL:+8613912345678
END:VCARD
"""


def test_parse_vcard():
    contacts = parse_vcard(SAMPLE)
    assert len(contacts) == 2
    assert contacts[0].name == "张三"
    assert contacts[0].number == "+8613800138000"
    assert contacts[0].notes == "同事"


def test_export_vcard_roundtrip():
    data = [{"name": "Alice", "number": "+8611111111111", "notes": "test"}]
    exported = export_vcards(data)
    parsed = parse_vcard(exported)
    assert len(parsed) == 1
    assert parsed[0].name == "Alice"
    assert parsed[0].number == "+8611111111111"
