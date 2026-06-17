"""Tests for contacts database."""

import tempfile
from pathlib import Path

from hipi.db.models import Database


def test_add_list_contacts():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        c = db.add_contact("张三", "13800138000", "朋友")
        assert c.name == "张三"
        assert c.number == "+8613800138000"
        listed = db.list_contacts()
        assert len(listed) == 1
        found = db.get_contact_by_number("13800138000")
        assert found and found.name == "张三"
        db.close()


def test_contact_map_and_search():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        db.add_contact("Bob", "+8611111111111")
        db.add_contact("Alice", "+8622222222222")
        assert db.get_contact_map()["+8611111111111"] == "Bob"
        results = db.list_contacts(query="Ali")
        assert len(results) == 1
        assert results[0].name == "Alice"
        db.close()


def test_sms_forward_settings():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        assert not db.is_sms_forward_enabled()
        db.set_sms_forward_enabled(True)
        db.set_sms_forward_target("+8613999999999")
        cfg = db.get_sms_forward_config()
        assert cfg["enabled"] is True
        assert cfg["target"] == "+8613999999999"
        db.close()
