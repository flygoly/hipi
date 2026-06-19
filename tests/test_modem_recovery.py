"""Tests for daemon ModemManager reconnect logic."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from hipi.daemon.modem import ModemManagerError
from hipi.daemon.server import HiPiDaemon


def _fresh_daemon(tmp: str) -> HiPiDaemon:
    daemon = HiPiDaemon()
    daemon.db.close()
    daemon.db = __import__("hipi.db.models", fromlist=["Database"]).Database(Path(tmp) / "test.db")
    daemon.mm = None
    daemon._sms = None
    daemon._voice = None
    daemon._mm_signals_connected = False
    return daemon


def test_ensure_mm_initializes_services():
    with tempfile.TemporaryDirectory() as tmp:
        daemon = _fresh_daemon(tmp)
        mock_mm = MagicMock()
        mock_mm.get_primary_modem_path.return_value = "/modem/0"
        with patch("hipi.daemon.server.ModemManagerClient", return_value=mock_mm):
            assert daemon._ensure_mm() is True
        assert daemon.mm is mock_mm
        assert daemon._sms is not None
        assert daemon._voice is not None
        daemon.db.close()


def test_ensure_mm_returns_false_when_mm_unavailable():
    with tempfile.TemporaryDirectory() as tmp:
        daemon = _fresh_daemon(tmp)
        with patch("hipi.daemon.server.ModemManagerClient", side_effect=ModemManagerError("down")):
            assert daemon._ensure_mm() is False
        assert daemon.mm is None
        daemon.db.close()


def test_on_modem_added_reconnects_after_late_plug():
    with tempfile.TemporaryDirectory() as tmp:
        daemon = _fresh_daemon(tmp)
        mock_mm = MagicMock()
        mock_mm.get_primary_modem_path.return_value = "/modem/0"
        with patch("hipi.daemon.server.ModemManagerClient", return_value=mock_mm):
            daemon._on_modem_added("/modem/0")
        assert daemon.mm is mock_mm
        mock_mm.enable_modem.assert_called_once_with("/modem/0")
        daemon.db.close()
