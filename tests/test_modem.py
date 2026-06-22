"""Tests for ModemManager D-Bus client."""

from unittest.mock import MagicMock, patch

import dbus

from hipi.daemon.modem import MODEM_IFACE, ModemManagerClient


def test_list_modem_paths_uses_object_manager():
    mock_om = MagicMock()
    mock_om.GetManagedObjects.return_value = {
        "/org/freedesktop/ModemManager1/Modem/0": {
            MODEM_IFACE: {"State": dbus.Int32(8)},
        },
        "/org/freedesktop/ModemManager1/SMS/0": {
            "org.freedesktop.ModemManager1.Sms": {},
        },
    }

    with patch("hipi.daemon.modem.dbus.SystemBus") as mock_bus_cls:
        mock_bus = MagicMock()
        mock_bus_cls.return_value = mock_bus
        mock_bus.get_object.return_value = MagicMock()

        with patch("hipi.daemon.modem.dbus.Interface") as mock_iface_cls:
            def iface_factory(obj, name):
                if name == "org.freedesktop.DBus.ObjectManager":
                    return mock_om
                return MagicMock()

            mock_iface_cls.side_effect = iface_factory
            client = ModemManagerClient()

    paths = client.list_modem_paths()
    assert paths == ["/org/freedesktop/ModemManager1/Modem/0"]
    mock_om.GetManagedObjects.assert_called_once()
