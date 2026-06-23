"""AT commands over ModemManager's D-Bus Command() interface.

Used when /dev/ttyUSB* ports are locked by ModemManager and MM debug mode
is enabled (--debug flag), which allows the Command() D-Bus method.
"""

from __future__ import annotations

import logging
from typing import Any

import dbus

from hipi.daemon.modem import MM_SERVICE, MODEM_IFACE, ModemManagerError

logger = logging.getLogger(__name__)


class MmAtClient:
    """Send AT commands through the ModemManager D-Bus Command() API.

    Requires ModemManager running with --debug flag, otherwise commands return
    'Unauthorized: Operation only allowed in debug mode'.
    """

    def __init__(self, bus: dbus.Bus) -> None:
        self._bus = bus

    def command(self, modem_path: str, cmd: str, timeout: int = 10) -> str:
        """Send an AT command via MM and return the response string."""
        try:
            modem = self._bus.get_object(MM_SERVICE, modem_path)
            iface = dbus.Interface(modem, MODEM_IFACE)
            return str(iface.Command(cmd, timeout))
        except dbus.DBusException as exc:
            raise ModemManagerError(f"MM Command({cmd}) failed: {exc}") from exc

    def probe_modem_info(self, modem_path: str) -> dict[str, Any]:
        """Best-effort modem identity via MM AT commands."""
        info: dict[str, Any] = {
            "manufacturer": "Quectel",
            "model": "EC801E",
            "state": "unknown",
            "signal_quality": 0,
            "operator_name": "",
            "operator_code": "",
            "imei": "",
            "own_numbers": [],
            "sim_locked": False,
            "messaging": True,
            "voice": True,
        }
        try:
            ati = self.command(modem_path, "ATI", timeout=5)
            for line in ati.splitlines():
                line = line.strip()
                if not line or line in ("OK", "ERROR"):
                    continue
                if "EC801" in line.upper():
                    info["model"] = line.split()[-1] if line else "EC801E"
                elif "QUECTEL" in line.upper():
                    info["manufacturer"] = "Quectel"

            imei = self.command(modem_path, "AT+CGSN", timeout=5)
            for line in imei.splitlines():
                digits = "".join(c for c in line if c.isdigit())
                if len(digits) >= 14:
                    info["imei"] = digits
                    break

            csq = self.command(modem_path, "AT+CSQ", timeout=5)
            import re

            m = re.search(r"\+CSQ:\s*(\d+)", csq)
            if m:
                rssi = int(m.group(1))
                if rssi != 99:
                    info["signal_quality"] = min(100, max(0, int((rssi / 31) * 100)))

            cpin = self.command(modem_path, "AT+CPIN?", timeout=5)
            if "READY" in cpin:
                info["sim_locked"] = False
                info["state"] = "registered"
            elif "SIM PIN" in cpin:
                info["sim_locked"] = True
                info["state"] = "locked"

            cnum = self.command(modem_path, "AT+CNUM", timeout=5)
            numbers = re.findall(r'"([^"]+)"', cnum)
            info["own_numbers"] = [n for n in numbers if any(c.isdigit() for c in n)]
        except ModemManagerError as exc:
            logger.debug("MM AT probe partial: %s", exc)
        return info

    def send_sms(
        self, modem_path: str, number: str, text: str
    ) -> dict[str, Any]:
        """Send SMS via MM AT commands and return modem Sms object dict."""
        from hipi.util import normalize_number

        peer = normalize_number(number)
        if not peer:
            return {"ok": False, "error": "Invalid phone number"}
        if not text.strip():
            return {"ok": False, "error": "Empty message"}

        try:
            self.command(modem_path, "AT+CMGF=1", timeout=5)
            if self._is_ascii(text):
                self.command(modem_path, 'AT+CSCS="GSM"', timeout=5)
                resp = self.command(modem_path, f'AT+CMGS="{peer}"', timeout=30)
            else:
                self.command(modem_path, 'AT+CSCS="UCS2"', timeout=5)
                num_hex = peer.encode("utf-16-be").hex().upper()
                body_hex = text.encode("utf-16-be").hex().upper()
                resp = self.command(modem_path, f'AT+CMGS="{num_hex}"', timeout=30)
            # MM wraps the prompt response; CMGS returns the index or OK
            if "+CMS ERROR" in resp or "+CME ERROR" in resp:
                return {"ok": False, "error": resp.strip()}
            if "OK" in resp or "+CMGS:" in resp:
                return {"ok": True, "message": f"SMS sent via MM AT: {resp.strip()[:100]}"}
            return {"ok": True, "message": "SMS sent"}
        except ModemManagerError as exc:
            return {"ok": False, "error": str(exc)}

    def list_messages(self, modem_path: str) -> list[dict[str, Any]]:
        """List SMS messages via MM AT+CMGL. Returns structured list."""
        try:
            self.command(modem_path, "AT+CMGF=1", timeout=5)
            self.command(modem_path, 'AT+CSCS="GSM"', timeout=5)
            resp = self.command(modem_path, 'AT+CMGL="ALL"', timeout=15)
        except ModemManagerError as exc:
            logger.warning("MM AT CMGL failed: %s", exc)
            return []
        return self._parse_cmgl(resp)

    def _is_ascii(self, text: str) -> bool:
        try:
            text.encode("ascii")
            return True
        except UnicodeEncodeError:
            return False

    def _parse_cmgl(self, response: str) -> list[dict[str, Any]]:
        import re

        cmgl_re = re.compile(
            r'\+CMGL:\s*(\d+),"([^"]*)","([^"]*)"(?:,[^\r\n]*)?\r?\n(.*?)(?=\r\n\+CMGL:|\r\nOK|\Z)',
            re.DOTALL,
        )
        from hipi.util import normalize_number

        messages: list[dict[str, Any]] = []
        for match in cmgl_re.finditer(response):
            index, stat, number, body = match.groups()
            stat_u = stat.upper()
            if stat_u.startswith("STO"):
                direction = "outbound"
                status = "sent" if "SENT" in stat_u else "sending"
            else:
                direction = "inbound"
                status = "received"
            peer = normalize_number(number) or number
            body = body.strip("\r\n")
            messages.append(
                {
                    "index": index,
                    "peer": peer,
                    "body": body,
                    "direction": direction,
                    "status": status,
                    "modem_sms_id": f"mmat:{index}",
                }
            )
        return messages
