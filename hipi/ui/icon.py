"""Qt application icon helper."""

from __future__ import annotations

from PySide6.QtGui import QIcon

from hipi.icon_paths import find_icon_path


def app_icon() -> QIcon:
    path = find_icon_path()
    if path:
        return QIcon(str(path))
    themed = QIcon.fromTheme("phone")
    return themed if not themed.isNull() else QIcon()
