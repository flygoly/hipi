"""ModemManager D-Bus client."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import dbus
from dbus.mainloop.glib import DBusGMainLoop

DBusGMainLoop(set_as_default=True)

logger = logging.getLogger(__name__)

MM_SERVICE = "org.freedesktop.ModemManager1"
MM_PATH = "/org/freedesktop/ModemManager1"
MM_IFACE = "org.freedesktop.ModemManager1"
OM_IFACE = "org.freedesktop.DBus.ObjectManager"
MODEM_IFACE = "org.freedesktop.ModemManager1.Modem"
MODEM_SIMPLE_IFACE = "org.freedesktop.ModemManager1.Modem.Simple"
MODEM_MESSAGING_IFACE = "org.freedesktop.ModemManager1.Modem.Messaging"
MODEM_VOICE_IFACE = "org.freedesktop.ModemManager1.Modem.Voice"
SMS_IFACE = "org.freedesktop.ModemManager1.Sms"
CALL_IFACE = "org.freedesktop.ModemManager1.Call"

MM_MODEM_STATE_FAILED = -1
MM_MODEM_STATE_UNKNOWN = 0
MM_MODEM_STATE_INITIALIZING = 1
MM_MODEM_STATE_LOCKED = 2
MM_MODEM_STATE_DISABLED = 3
MM_MODEM_STATE_DISABLING = 4
MM_MODEM_STATE_ENABLING = 5
MM_MODEM_STATE_ENABLED = 6
MM_MODEM_STATE_SEARCHING = 7
MM_MODEM_STATE_REGISTERED = 8
MM_MODEM_STATE_CONNECTING = 9
MM_MODEM_STATE_CONNECTED = 10
MM_MODEM_STATE_DISCONNECTING = 11

STATE_NAMES = {
    MM_MODEM_STATE_FAILED: "failed",
    MM_MODEM_STATE_UNKNOWN: "unknown",
    MM_MODEM_STATE_INITIALIZING: "initializing",
    MM_MODEM_STATE_LOCKED: "locked",
    MM_MODEM_STATE_DISABLED: "disabled",
    MM_MODEM_STATE_DISABLING: "disabling",
    MM_MODEM_STATE_ENABLING: "enabling",
    MM_MODEM_STATE_ENABLED: "enabled",
    MM_MODEM_STATE_SEARCHING: "searching",
    MM_MODEM_STATE_REGISTERED: "registered",
    MM_MODEM_STATE_CONNECTING: "connecting",
    MM_MODEM_STATE_CONNECTED: "connected",
    MM_MODEM_STATE_DISCONNECTING: "disconnecting",
}


@dataclass
class ModemStatus:
    path: str
    manufacturer: str
    model: str
    state: str
    state_failed_reason: str
    signal_quality: int
    access_technologies: list[str]
    operator_name: str
    operator_code: str
    imei: str
    own_numbers: list[str]
    sim_path: str | None
    sim_locked: bool
    messaging: bool
    voice: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "state": self.state,
            "state_failed_reason": self.state_failed_reason,
            "signal_quality": self.signal_quality,
            "access_technologies": self.access_technologies,
            "operator_name": self.operator_name,
            "operator_code": self.operator_code,
            "imei": self.imei,
            "own_numbers": self.own_numbers,
            "sim_path": self.sim_path,
            "sim_locked": self.sim_locked,
            "messaging": self.messaging,
            "voice": self.voice,
        }


class ModemManagerError(Exception):
    pass


class ModemManagerClient:
    def __init__(self) -> None:
        self._bus = dbus.SystemBus()
        try:
            self._mm = self._bus.get_object(MM_SERVICE, MM_PATH)
            self._mm_iface = dbus.Interface(self._mm, MM_IFACE)
            self._om_iface = dbus.Interface(self._mm, OM_IFACE)
        except dbus.DBusException as exc:
            raise ModemManagerError(
                "ModemManager not available. Install and start modemmanager."
            ) from exc
        self._modem_added_handlers: list[Any] = []
        self._modem_removed_handlers: list[Any] = []
        self._sms_added_handlers: list[Any] = []
        self._call_added_handlers: list[Any] = []

    def list_modem_paths(self) -> list[str]:
        try:
            modems = self._om_iface.GetManagedObjects()
        except dbus.DBusException as exc:
            if "AccessDenied" in str(exc) or "Unauthorized" in str(exc):
                raise ModemManagerError(
                    "ModemManager D-Bus access denied. Run: "
                    "sudo ./scripts/install-system-policy.sh "
                    "then log out and back in."
                ) from exc
            raise ModemManagerError(f"ModemManager error: {exc}") from exc
        return [
            path
            for path, ifaces in modems.items()
            if MODEM_IFACE in ifaces and not path.endswith("/SMS/") and "/Call/" not in path
        ]

    def get_primary_modem_path(self) -> str | None:
        paths = self.list_modem_paths()
        if not paths:
            return None
        preferred: str | None = None
        for path in paths:
            try:
                status = self.get_modem_status(path)
            except dbus.DBusException as exc:
                logger.warning("Modem status %s: %s", path, exc)
                if preferred is None:
                    preferred = path
                continue
            if "quectel" in status.manufacturer.lower() or "ec801" in status.model.lower():
                return path
            if preferred is None:
                preferred = path
        return preferred

    def get_primary_at_port(self, modem_path: str) -> str | None:
        try:
            modem = self._bus.get_object(MM_SERVICE, modem_path)
            props = dbus.Interface(modem, "org.freedesktop.DBus.Properties")
            port = str(props.Get(MODEM_IFACE, "PrimaryPort") or "").strip()
            if not port:
                return None
            return port if port.startswith("/dev/") else f"/dev/{port}"
        except dbus.DBusException:
            return None

    def get_modem_status(self, modem_path: str) -> ModemStatus:
        modem = self._bus.get_object(MM_SERVICE, modem_path)
        props = dbus.Interface(modem, "org.freedesktop.DBus.Properties")
        values = props.GetAll(MODEM_IFACE)

        state_val = int(values.get("State", 0))
        signal = values.get("SignalQuality", (0, False))
        quality = int(signal[0]) if signal else 0

        access = values.get("AccessTechnologies", 0)
        techs = _decode_access_technologies(int(access))

        manufacturer = str(values.get("Manufacturer", ""))
        model = str(values.get("Model", ""))
        operator_name = ""
        operator_code = ""
        try:
            operator = values.get("Operator", ("", "", ""))
            if operator:
                operator_code = str(operator[0] or "")
                operator_name = str(operator[1] or operator[2] or "")
        except (TypeError, IndexError):
            pass

        own_numbers = [str(n) for n in values.get("OwnNumbers", [])]
        sim_path = str(values["Sim"]) if values.get("Sim") else None
        locked = state_val == MM_MODEM_STATE_LOCKED

        caps = values.get("CurrentCapabilities", 0)
        messaging = bool(int(caps) & 0x4)  # MM_MODEM_CAPABILITY_SMS
        voice = bool(int(caps) & 0x8)  # MM_MODEM_CAPABILITY_VOICE

        failed_reason = ""
        if state_val == MM_MODEM_STATE_FAILED:
            try:
                failed_reason = str(values.get("StateFailedReason", ""))
            except dbus.DBusException:
                failed_reason = "unknown"

        return ModemStatus(
            path=modem_path,
            manufacturer=manufacturer,
            model=model,
            state=STATE_NAMES.get(state_val, "unknown"),
            state_failed_reason=failed_reason,
            signal_quality=quality,
            access_technologies=techs,
            operator_name=operator_name,
            operator_code=operator_code,
            imei=str(values.get("EquipmentIdentifier", "")),
            own_numbers=own_numbers,
            sim_path=sim_path,
            sim_locked=locked,
            messaging=messaging,
            voice=voice,
        )

    def enable_modem(self, modem_path: str) -> None:
        simple = dbus.Interface(
            self._bus.get_object(MM_SERVICE, modem_path),
            MODEM_SIMPLE_IFACE,
        )
        simple.Enable()

    def unlock_sim(self, modem_path: str, pin: str) -> None:
        sim_path = self.get_modem_status(modem_path).sim_path
        if not sim_path:
            raise ModemManagerError("No SIM detected")
        sim = self._bus.get_object(MM_SERVICE, sim_path)
        sim_iface = dbus.Interface(sim, "org.freedesktop.ModemManager1.Sim")
        sim_iface.SendPin(pin)

    def send_at_command(self, modem_path: str, command: str) -> str:
        modem = self._bus.get_object(MM_SERVICE, modem_path)
        modem_iface = dbus.Interface(modem, MODEM_IFACE)
        return str(modem_iface.Command(command, timeout=10))

    def on_modem_added(self, callback) -> None:
        def _handler(path, interfaces):
            if MODEM_IFACE in interfaces:
                callback(str(path))

        self._bus.add_signal_receiver(
            _handler,
            dbus_interface=OM_IFACE,
            signal_name="InterfacesAdded",
            path=MM_PATH,
        )
        self._modem_added_handlers.append(_handler)

    def on_sms_added(self, callback) -> None:
        def _handler(path, interfaces):
            if SMS_IFACE in interfaces:
                callback(str(path))

        self._bus.add_signal_receiver(
            _handler,
            dbus_interface=OM_IFACE,
            signal_name="InterfacesAdded",
            path=MM_PATH,
        )
        self._sms_added_handlers.append(_handler)

    def on_call_added(self, callback) -> None:
        def _handler(path, interfaces):
            if CALL_IFACE in interfaces:
                callback(str(path))

        self._bus.add_signal_receiver(
            _handler,
            dbus_interface=OM_IFACE,
            signal_name="InterfacesAdded",
            path=MM_PATH,
        )
        self._call_added_handlers.append(_handler)

    def on_modem_removed(self, callback) -> None:
        def _handler(path, interfaces):
            if MODEM_IFACE in interfaces:
                callback(str(path))

        self._bus.add_signal_receiver(
            _handler,
            dbus_interface=OM_IFACE,
            signal_name="InterfacesRemoved",
            path=MM_PATH,
        )
        self._modem_removed_handlers.append(_handler)

    def get_messaging_interface(self, modem_path: str):
        return dbus.Interface(
            self._bus.get_object(MM_SERVICE, modem_path),
            MODEM_MESSAGING_IFACE,
        )

    def get_voice_interface(self, modem_path: str):
        return dbus.Interface(
            self._bus.get_object(MM_SERVICE, modem_path),
            MODEM_VOICE_IFACE,
        )

    def get_sms_properties(self, sms_path: str) -> dict[str, Any]:
        sms = self._bus.get_object(MM_SERVICE, sms_path)
        props = dbus.Interface(sms, "org.freedesktop.DBus.Properties")
        values = props.GetAll(SMS_IFACE)
        return {k: _dbus_to_python(v) for k, v in values.items()}

    def get_call_properties(self, call_path: str) -> dict[str, Any]:
        call = self._bus.get_object(MM_SERVICE, call_path)
        props = dbus.Interface(call, "org.freedesktop.DBus.Properties")
        values = props.GetAll(CALL_IFACE)
        return {k: _dbus_to_python(v) for k, v in values.items()}

    def list_modem_sms_paths(self, modem_path: str) -> list[str]:
        if not self.has_messaging(modem_path):
            return []
        messaging = self.get_messaging_interface(modem_path)
        return [str(p) for p in messaging.List()]

    def list_modem_call_paths(self, modem_path: str) -> list[str]:
        if not self.has_voice(modem_path):
            return []
        voice = self.get_voice_interface(modem_path)
        return [str(p) for p in voice.ListCalls()]

    def has_messaging(self, modem_path: str) -> bool:
        try:
            modem = self._bus.get_object(MM_SERVICE, modem_path)
            introspect = dbus.Interface(modem, "org.freedesktop.DBus.Introspectable")
            xml = str(introspect.Introspect())
            if MODEM_MESSAGING_IFACE not in xml:
                return False
            messaging = dbus.Interface(modem, MODEM_MESSAGING_IFACE)
            messaging.List()
            return True
        except dbus.DBusException:
            return False

    def has_voice(self, modem_path: str) -> bool:
        try:
            modem = self._bus.get_object(MM_SERVICE, modem_path)
            introspect = dbus.Interface(modem, "org.freedesktop.DBus.Introspectable")
            xml = str(introspect.Introspect())
            if MODEM_VOICE_IFACE not in xml:
                return False
            voice = dbus.Interface(modem, MODEM_VOICE_IFACE)
            voice.ListCalls()
            return True
        except dbus.DBusException:
            return False

    def watch_properties(self, object_path: str, iface: str, callback) -> None:
        """Subscribe to PropertiesChanged on a D-Bus object."""

        def handler(interface: str, changed: dict, _invalidated: list) -> None:
            if interface != iface:
                return
            callback({k: _dbus_to_python(v) for k, v in changed.items()})

        self._bus.add_signal_receiver(
            handler,
            dbus_interface="org.freedesktop.DBus.Properties",
            signal_name="PropertiesChanged",
            path=object_path,
        )


def _dbus_to_python(value: Any) -> Any:
    if isinstance(value, dbus.Byte):
        return int(value)
    if isinstance(value, (dbus.String,)):
        return str(value)
    if isinstance(value, dbus.Boolean):
        return bool(value)
    if isinstance(value, (dbus.Int16, dbus.Int32, dbus.Int64, dbus.UInt16, dbus.UInt32, dbus.UInt64)):
        return int(value)
    if isinstance(value, dbus.Double):
        return float(value)
    if isinstance(value, dbus.Array):
        return [_dbus_to_python(v) for v in value]
    if isinstance(value, dbus.Dictionary):
        return {str(k): _dbus_to_python(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return tuple(_dbus_to_python(v) for v in value)
    return value


def _decode_access_technologies(value: int) -> list[str]:
    mapping = {
        0x1: "POTS",
        0x2: "GSM",
        0x4: "GPRS",
        0x8: "EDGE",
        0x10: "UMTS",
        0x20: "HSDPA",
        0x40: "HSUPA",
        0x80: "HSPA",
        0x100: "HSPA+",
        0x200: "1xRTT",
        0x400: "EVDO0",
        0x800: "EVDOA",
        0x1000: "EVDOB",
        0x2000: "LTE",
        0x4000: "5GNR",
    }
    return [name for bit, name in mapping.items() if value & bit]
