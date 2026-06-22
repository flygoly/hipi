"""Tests for notification icon helper."""

from hipi.icon_paths import find_icon_path, notification_icon


def test_notification_icon_uses_svg_path():
    path = find_icon_path()
    assert path is not None
    icon = notification_icon()
    assert icon.endswith("hipi.svg")
    assert path.as_posix() in icon.replace("\\", "/")
