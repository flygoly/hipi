"""Desktop notifications via freedesktop D-Bus."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def notify(title: str, body: str, urgency: str = "normal") -> None:
    try:
        import dbus

        bus = dbus.SessionBus()
        iface = dbus.Interface(
            bus.get_object("org.freedesktop.Notifications", "/org/freedesktop/Notifications"),
            "org.freedesktop.Notifications",
        )
        urgency_map = {"low": 0, "normal": 1, "critical": 2}
        iface.Notify(
            "HiPi",
            0,
            "",
            title,
            body,
            [],
            {"urgency": dbus.Byte(urgency_map.get(urgency, 1))},
            -1,
        )
    except Exception as exc:
        logger.debug("Notification failed: %s", exc)
