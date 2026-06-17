"""Application paths and defaults."""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "hipi"
XDG_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
XDG_DATA = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
XDG_RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))

CONFIG_DIR = XDG_CONFIG / APP_NAME
DATA_DIR = XDG_DATA / APP_NAME
DB_PATH = DATA_DIR / "hipi.db"
SOCKET_PATH = XDG_RUNTIME / f"{APP_NAME}.sock"

DEFAULT_RPC_TIMEOUT = 30.0


def ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    XDG_RUNTIME.mkdir(parents=True, exist_ok=True)
