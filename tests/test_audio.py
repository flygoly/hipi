"""Tests for audio router ALSA card detection."""

from pathlib import Path
from unittest.mock import patch

from hipi.daemon.audio import AudioRouter


def test_detect_quectel_card():
    cards = """
  0 [PCH            ]: HDA-Intel - HDA Intel PCH
  1 [EC801E         ]: USB-Audio - Quectel EC801E
"""
    router = AudioRouter()
    with patch.object(Path, "exists", return_value=True), patch.object(
        Path, "read_text", return_value=cards
    ):
        assert router.detect_modem_alsa_card() == "1"


def test_detect_no_quectel_card():
    cards = """
  0 [PCH            ]: HDA-Intel - HDA Intel PCH
"""
    router = AudioRouter()
    with patch.object(Path, "exists", return_value=True), patch.object(
        Path, "read_text", return_value=cards
    ):
        assert router.detect_modem_alsa_card() is None
