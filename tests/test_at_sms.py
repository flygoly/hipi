"""Tests for AT serial SMS parsing and backend selection."""

from unittest.mock import MagicMock, patch

from hipi.daemon.at_serial import AtSerialClient, _parse_cmgl
from hipi.daemon.sms import BACKEND_AT, BACKEND_MM, SmsService


def test_parse_cmgl_inbound():
    raw = (
        '+CMGL: 1,"REC UNREAD","18188621313",,"25/06/22,20:30:00+32"\r\n'
        "Hello world\r\n"
        "OK"
    )
    items = _parse_cmgl(raw)
    assert len(items) == 1
    assert items[0]["peer"] == "+8618188621313"
    assert items[0]["body"] == "Hello world"
    assert items[0]["direction"] == "inbound"
    assert items[0]["modem_sms_id"] == "at:1"


def test_sms_backend_prefers_mm_when_messaging_available():
    mm = MagicMock()
    mm.has_messaging.return_value = True
    db = MagicMock()
    sms = SmsService(mm, db, at=AtSerialClient(port="/dev/ttyUSB9"))
    assert sms.get_backend("/modem/0") == BACKEND_MM


def test_sms_backend_falls_back_to_at():
    mm = MagicMock()
    mm.has_messaging.return_value = False
    db = MagicMock()
    at = MagicMock()
    at.find_port.return_value = "/dev/ttyUSB2"
    sms = SmsService(mm, db, at=at)
    assert sms.get_backend("/modem/0") == BACKEND_AT


def test_send_sms_at_backend():
    mm = MagicMock()
    mm.has_messaging.return_value = False
    db = MagicMock()
    db.add_message.return_value = MagicMock(to_dict=lambda: {"id": 1, "body": "hi"})
    at = MagicMock()
    at.find_port.return_value = "/dev/ttyUSB2"
    sms = SmsService(mm, db, at=at)
    with patch.object(sms, "get_backend", return_value=BACKEND_AT):
        result = sms.send_sms("/modem/0", "18188621313", "测试")
    assert result["ok"] is True
    at.send_sms.assert_called_once()
