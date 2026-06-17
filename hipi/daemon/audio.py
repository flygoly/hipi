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
        self._saved_sink: str | None = None
        self._saved_source: str | None = None
        self._active_sink: str | None = None
        self._active_source: str | None = None

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
                "message": (
                    "No Quectel ALSA audio device found. "
                    "Voice may use USB UAC or require EC801E audio variant."
                ),
            }

        if not shutil.which("pactl"):
            return {"ok": False, "message": "pactl not found (install pipewire-pulse or pulseaudio)"}

        return self._setup_pactl(card)

    def _setup_pactl(self, card: str) -> dict[str, str | bool]:
        try:
            if self._saved_sink is None:
                self._saved_sink = self._pactl_default("sink")
            if self._saved_source is None:
                self._saved_source = self._pactl_default("source")

            source = self._find_device("sources", card)
            sink = self._find_device("sinks", card)

            if source:
                subprocess.run(["pactl", "set-default-source", source], check=False, timeout=5)
                self._active_source = source
            if sink:
                subprocess.run(["pactl", "set-default-sink", sink], check=False, timeout=5)
                self._active_sink = sink

            if not source and not sink:
                return {
                    "ok": False,
                    "card": card,
                    "message": f"Quectel card {card} found in ALSA but not in PulseAudio/PipeWire.",
                }

            backend = "pipewire" if shutil.which("pw-cli") else "pulseaudio"
            return {
                "ok": True,
                "backend": backend,
                "card": card,
                "sink": sink or "",
                "source": source or "",
                "message": "Default audio I/O switched to modem",
            }
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "message": str(exc)}

    def _find_device(self, kind: str, card: str) -> str | None:
        result = subprocess.run(
            ["pactl", "list", kind, "short"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        card_patterns = (f"alsa_card.{card}", f"card_{card}", "quectel", "ec801")
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            name = parts[1]
            lower = line.lower()
            if any(p in lower or p in name for p in card_patterns):
                return name
        return None

    @staticmethod
    def _pactl_default(kind: str) -> str | None:
        result = subprocess.run(
            ["pactl", "get-default-" + kind],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None

    def teardown_call_audio(self) -> None:
        if not shutil.which("pactl"):
            return
        try:
            if self._saved_source:
                subprocess.run(
                    ["pactl", "set-default-source", self._saved_source],
                    check=False,
                    timeout=5,
                )
            if self._saved_sink:
                subprocess.run(
                    ["pactl", "set-default-sink", self._saved_sink],
                    check=False,
                    timeout=5,
                )
        except subprocess.TimeoutExpired:
            logger.warning("Audio teardown timed out")
        finally:
            self._saved_sink = None
            self._saved_source = None
            self._active_sink = None
            self._active_source = None
            logger.debug("Call audio restored to previous defaults")
