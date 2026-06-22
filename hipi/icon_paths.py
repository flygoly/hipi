"""Application icon path resolution (no Qt dependency)."""

from __future__ import annotations

from pathlib import Path

_ICON_NAME = "hipi.svg"


def icon_paths() -> list[Path]:
    root = Path(__file__).resolve().parents[1]
    return [
        Path("/usr/share/icons/hicolor/scalable/apps") / _ICON_NAME,
        root / "packaging" / "icons" / _ICON_NAME,
    ]


def find_icon_path() -> Path | None:
    for path in icon_paths():
        if path.is_file():
            return path
    return None
