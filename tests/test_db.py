"""Tests for SQLite database layer."""

import tempfile
from pathlib import Path

from hipi.db.models import Database


def test_add_and_list_messages():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        msg = db.add_message(peer="+8613800138000", body="hello", direction="inbound")
        assert msg.id > 0
        listed = db.list_messages(peer="+8613800138000")
        assert len(listed) == 1
        assert listed[0].body == "hello"
        db.close()


def test_conversations_and_unread():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        db.add_message(peer="+861111", body="a", direction="inbound", status="received")
        db.add_message(peer="+862222", body="b", direction="outbound", status="sent")
        convs = db.list_conversations()
        assert len(convs) == 2
        unread_peer = next(c for c in convs if c["peer"] == "+861111")
        assert unread_peer["unread"] == 1
        db.close()


def test_onboarding_flag():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        assert not db.is_onboarding_complete()
        db.mark_onboarding_complete()
        assert db.is_onboarding_complete()
        db.close()


def test_modem_sms_dedup():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        db.add_message(
            peer="+861111",
            body="x",
            direction="inbound",
            modem_sms_id="/org/freedesktop/ModemManager1/SMS/0",
        )
        assert db.has_modem_sms("/org/freedesktop/ModemManager1/SMS/0")
        db.close()
