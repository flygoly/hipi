"""Tests for shared status file I/O."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from hipi.status_file import read_status_file, write_status_file


def test_write_and_read_status_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "hipi-status.json"
        with patch("hipi.status_file.STATUS_FILE", path):
            payload = {"modem_present": True, "unread_sms": 2}
            write_status_file(payload)
            assert read_status_file() == payload


def test_read_missing_file_returns_none():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "missing.json"
        with patch("hipi.status_file.STATUS_FILE", path):
            assert read_status_file() is None


def test_read_invalid_json_returns_none():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "bad.json"
        path.write_text("not json", encoding="utf-8")
        with patch("hipi.status_file.STATUS_FILE", path):
            assert read_status_file() is None
