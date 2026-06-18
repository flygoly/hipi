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
        db.set_sms_forward_webhook("https://example.com/hook")
        cfg = db.get_sms_forward_config()
        assert cfg["enabled"] is True
        assert cfg["target"] == "+8613999999999"
        assert cfg["webhook"] == "https://example.com/hook"
        db.close()


def test_import_contacts_batch():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        stats = db.import_contacts_batch([("A", "13800138001", ""), ("B", "13800138001", "")])
        assert stats["imported"] == 1
        assert stats["updated"] == 0
        assert stats["skipped"] == 1
        db.close()


def test_import_contacts_merge():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        db.add_contact("旧名", "13800138001", "旧备注")
        stats = db.import_contacts_batch([("新名", "13800138001", "新备注")], merge=True)
        assert stats["imported"] == 0
        assert stats["updated"] == 1
        assert stats["skipped"] == 0
        contact = db.get_contact_by_number("13800138001")
        assert contact and contact.name == "新名"
        assert contact.notes == "新备注"
        db.close()


def test_count_unread():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        db.add_message("+86111", "hi", "inbound", status="received")
        db.add_message("+86222", "hi", "inbound", status="read")
        assert db.count_unread_messages() == 1
        db.close()
