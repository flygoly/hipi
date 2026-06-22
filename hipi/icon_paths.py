"""Application icon path resolution (no Qt dependency)."""

from __future__ import annotations

from pathlib import Path

_ICON_NAME = "hipi.svg"
_PKG_ROOT = Path(__file__).resolve().parent


def icon_paths() -> list[Path]:
    repo_root = _PKG_ROOT.parent
    return [
        Path("/usr/share/icons/hicolor/scalable/apps") / _ICON_NAME,
        _PKG_ROOT / "data" / _ICON_NAME,
        repo_root / "packaging" / "icons" / _ICON_NAME,
    ]


def find_icon_path() -> Path | None:
    for path in icon_paths():
        if path.is_file():
            return path
    return None


def notification_icon() -> str:
    path = find_icon_path()
    return str(path) if path else "phone"
