"""Shared modem status snapshot for UI and GNOME extension."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from hipi.config import STATUS_FILE

logger = logging.getLogger(__name__)


def write_status_file(status: dict[str, Any]) -> None:
    try:
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATUS_FILE.write_text(
            json.dumps(status, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.debug("Could not write status file: %s", exc)


def read_status_file() -> dict[str, Any] | None:
    try:
        if not STATUS_FILE.exists():
            return None
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
