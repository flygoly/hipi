"""Tests for CSV export."""

import tempfile
from pathlib import Path

from hipi.db.models import Database
from hipi.export import export_calls_csv, export_messages_csv


def test_export_messages_csv():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        db.add_contact("Bob", "13800138000")
        db.add_message("+8613800138000", "hello", "inbound")
        csv_text = export_messages_csv(db)
        assert "contact_name" in csv_text
        assert "Bob" in csv_text
        assert "hello" in csv_text
        db.close()


def test_export_calls_csv():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        db.add_call("+861111", "outbound", "terminated")
        csv_text = export_calls_csv(db)
        assert "duration_sec" in csv_text
        assert "+861111" in csv_text
        db.close()
