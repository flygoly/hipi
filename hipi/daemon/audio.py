"""PipeWire / ALSA audio routing helpers for modem voice."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

QUECTEL_ALSA_RE = re.compile(r"quectel|ec801|qcd", re.IGNORECASE)


class AudioRouter:
    """Route call audio to default sink/source when modem exposes ALSA devices."""

    def __init__(self) -> None:
        self._modem_card: str | None = None

    def detect_modem_alsa_card(self) -> str | None:
        cards_path = Path("/proc/asound/cards")
        if not cards_path.exists():
            return None
        text = cards_path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            match = re.match(r"\s*(\d+)\s+\[([^\]]+)\]", line)
            if match and QUECTEL_ALSA_RE.search(match.group(2)):
                self._modem_card = match.group(1)
                return self._modem_card
        return None

    def has_voice_audio(self) -> bool:
        return self.detect_modem_alsa_card() is not None

    def setup_call_audio(self) -> dict[str, str | bool]:
        card = self.detect_modem_alsa_card()
        if not card:
            return {
                "ok": False,
                "message": "No Quectel ALSA audio device found. Voice may use USB UAC or require EC801E audio variant.",
            }

        if shutil.which("pw-cli"):
            return self._setup_pipewire(card)
        if shutil.which("pactl"):
            return self._setup_pulse(card)
        return {"ok": False, "message": "Neither pw-cli nor pactl found"}

    def _setup_pipewire(self, card: str) -> dict[str, str | bool]:
        try:
            subprocess.run(
                ["pw-cli", "ls", "Node"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            logger.info("PipeWire available; modem ALSA card %s detected", card)
            return {
                "ok": True,
                "backend": "pipewire",
                "card": card,
                "message": f"Modem audio card {card} available. Set default I/O in system settings if needed.",
            }
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            logger.warning("PipeWire setup check failed: %s", exc)
            return {"ok": False, "message": str(exc)}

    def _setup_pulse(self, card: str) -> dict[str, str | bool]:
        try:
            result = subprocess.run(
                ["pactl", "list", "sources", "short"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.splitlines():
                if f"alsa_card.{card}" in line or "quectel" in line.lower():
                    source = line.split()[1]
                    subprocess.run(["pactl", "set-default-source", source], check=False)
                    break
            result = subprocess.run(
                ["pactl", "list", "sinks", "short"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.splitlines():
                if f"alsa_card.{card}" in line or "quectel" in line.lower():
                    sink = line.split()[1]
                    subprocess.run(["pactl", "set-default-sink", sink], check=False)
                    break
            return {"ok": True, "backend": "pulseaudio", "card": card, "message": "Default sink/source updated"}
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "message": str(exc)}

    def teardown_call_audio(self) -> None:
        logger.debug("Call audio teardown (no-op)")
