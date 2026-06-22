"""Direct AT commands over Quectel serial port (ECM / EC801E)."""

from __future__ import annotations

import glob
import logging
import os
import re
import select
import termios
import threading
import time
from collections.abc import Callable
from typing import Any

from hipi.config import CONFIG_DIR
from hipi.util import normalize_number

logger = logging.getLogger(__name__)

_BAUD = termios.B115200
_CMGL_RE = re.compile(
    r'\+CMGL:\s*(\d+),"([^"]*)","([^"]*)"(?:,[^\r\n]*)?\r?\n(.*?)(?=\r\n\+CMGL:|\r\nOK|\Z)',
    re.DOTALL,
)


class AtSerialError(Exception):
    pass


AT_MODEM_PREFIX = "at:"


def at_modem_path(port: str) -> str:
    return f"{AT_MODEM_PREFIX}{port}"


def parse_at_modem_path(path: str) -> str | None:
    if path.startswith(AT_MODEM_PREFIX):
        return path[len(AT_MODEM_PREFIX) :]
    return None


class AtSerialClient:
    """Thread-safe AT client for SMS on modems without MM Messaging (e.g. EC801E ECM)."""

    def __init__(self, port: str | None = None, baud: int = 115200) -> None:
        self._configured_port = port or self._read_config_port()
        self._port: str | None = None
        self._baud = baud
        self._lock = threading.Lock()

    @staticmethod
    def _read_config_port() -> str | None:
        path = CONFIG_DIR / "at_port"
        try:
            value = path.read_text(encoding="utf-8").strip()
            return value if value.startswith("/dev/") else None
        except OSError:
            return None

    def configured_port(self) -> str | None:
        return self._configured_port

    def active_port(self) -> str | None:
        return self._port or self._configured_port

    def find_port(self, *, force_rescan: bool = False) -> str | None:
        if self._configured_port and not force_rescan:
            if self._probe(self._configured_port):
                self._port = self._configured_port
                return self._port
        if self._port and not force_rescan and self._probe(self._port):
            return self._port
        for pattern in ("/dev/ttyUSB*", "/dev/ttyACM*"):
            for candidate in sorted(glob.glob(pattern)):
                if self._probe(candidate):
                    self._port = candidate
                    logger.info("AT port: %s", candidate)
                    return candidate
        self._port = None
        return None

    def _probe(self, path: str) -> bool:
        try:
            response = _exchange(path, "AT", baud=self._baud, timeout=1.5)
            return "OK" in response
        except OSError:
            return False

    def command(self, cmd: str, *, timeout: float = 5.0, wait_prompt: str | None = None) -> str:
        return self._run_locked(
            lambda port: _exchange(
                port, cmd, baud=self._baud, timeout=timeout, wait_prompt=wait_prompt
            )
        )

    def unlock_sim(self, pin: str) -> None:
        pin = pin.strip()
        if not pin:
            raise AtSerialError("PIN required")
        resp = self.command(f'AT+CPIN="{pin}"', timeout=10)
        if "OK" not in resp:
            raise AtSerialError(resp.strip() or "SIM unlock failed")

    def send_sms(self, number: str, text: str) -> None:
        peer = normalize_number(number)
        if not peer:
            raise AtSerialError("Invalid phone number")
        if not text.strip():
            raise AtSerialError("Empty message")

        def _send(port: str) -> str:
            _exchange(port, "AT+CMGF=1", baud=self._baud, timeout=3)
            if _is_ascii(text):
                _exchange(port, 'AT+CSCS="GSM"', baud=self._baud, timeout=3)
                return _exchange(
                    port,
                    f'AT+CMGS="{peer}"',
                    baud=self._baud,
                    timeout=30,
                    wait_prompt=">",
                    suffix=b"\x1a",
                    payload_after_prompt=text,
                )
            _exchange(port, 'AT+CSCS="UCS2"', baud=self._baud, timeout=3)
            num_hex = peer.encode("utf-16-be").hex().upper()
            body_hex = text.encode("utf-16-be").hex().upper()
            return _exchange(
                port,
                f'AT+CMGS="{num_hex}"',
                baud=self._baud,
                timeout=30,
                wait_prompt=">",
                suffix=b"\x1a",
                payload_after_prompt=body_hex,
            )

        resp = self._run_locked(_send)
        if "+CMS ERROR" in resp or "+CME ERROR" in resp:
            raise AtSerialError(resp.strip())
        if "OK" not in resp and "+CMGS:" not in resp:
            raise AtSerialError(resp.strip() or "SMS send failed")

    def list_messages(self) -> list[dict[str, Any]]:
        def _list(port: str) -> str:
            _exchange(port, "AT+CMGF=1", baud=self._baud, timeout=3)
            _exchange(port, 'AT+CSCS="GSM"', baud=self._baud, timeout=3)
            return _exchange(port, 'AT+CMGL="ALL"', baud=self._baud, timeout=15)

        resp = self._run_locked(_list)
        return _parse_cmgl(resp)

    def dial(self, number: str) -> None:
        peer = normalize_number(number)
        if not peer:
            raise AtSerialError("Invalid phone number")
        resp = self.command(f"ATD{peer};", timeout=15)
        if "OK" not in resp and "CONNECT" not in resp and "ERROR" in resp:
            raise AtSerialError(resp.strip())

    def hangup(self) -> None:
        resp = self.command("ATH", timeout=10)
        if "OK" not in resp and "ERROR" in resp:
            raise AtSerialError(resp.strip())

    def probe_modem_info(self) -> dict[str, Any]:
        """Best-effort modem identity via AT (when ModemManager has no modem object)."""
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
            ati = self.command("ATI", timeout=3)
            for line in ati.splitlines():
                line = line.strip()
                if not line or line in ("OK", "ERROR"):
                    continue
                if "EC801" in line.upper():
                    info["model"] = line.split()[-1] if line else "EC801E"
                elif "QUECTEL" in line.upper():
                    info["manufacturer"] = "Quectel"
            imei = self.command("AT+CGSN", timeout=3)
            for line in imei.splitlines():
                digits = "".join(c for c in line if c.isdigit())
                if len(digits) >= 14:
                    info["imei"] = digits
                    break
            csq = self.command("AT+CSQ", timeout=3)
            m = re.search(r"\+CSQ:\s*(\d+)", csq)
            if m:
                rssi = int(m.group(1))
                if rssi != 99:
                    info["signal_quality"] = min(100, max(0, int((rssi / 31) * 100)))
            cpin = self.command("AT+CPIN?", timeout=3)
            if "READY" in cpin:
                info["sim_locked"] = False
                info["state"] = "registered"
            elif "SIM PIN" in cpin:
                info["sim_locked"] = True
                info["state"] = "locked"
            cnum = self.command("AT+CNUM", timeout=3)
            numbers = re.findall(r'"([^"]+)"', cnum)
            info["own_numbers"] = [n for n in numbers if any(c.isdigit() for c in n)]
        except AtSerialError as exc:
            logger.debug("AT probe partial: %s", exc)
        port = self.active_port() or self.find_port()
        if port:
            info["at_port"] = port
        return info

    def _run_locked(self, fn: Callable[[str], Any]) -> Any:
        with self._lock:
            port = self.find_port()
            if not port:
                raise AtSerialError("No AT serial port found (check dialout group and USB)")
            return fn(port)


def _is_ascii(text: str) -> bool:
    try:
        text.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _exchange(
    port: str,
    payload: str,
    *,
    baud: int = _BAUD,
    timeout: float = 5.0,
    wait_prompt: str | None = None,
    suffix: bytes = b"",
    payload_after_prompt: str | None = None,
) -> str:
    raw_cmd = payload if payload.endswith("\r") else f"{payload}\r"
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        _configure_tty(fd, baud)
        termios.tcflush(fd, termios.TCIOFLUSH)
        os.write(fd, raw_cmd.encode("ascii", errors="ignore"))
        text = _read_until(fd, timeout=timeout, wait_prompt=wait_prompt)
        if wait_prompt and wait_prompt in text:
            if payload_after_prompt is not None:
                os.write(fd, payload_after_prompt.encode("utf-8", errors="replace") + suffix)
            elif suffix:
                os.write(fd, suffix)
            text += _read_until(fd, timeout=timeout)
        return text
    finally:
        os.close(fd)


def _configure_tty(fd: int, baud: int = _BAUD) -> None:
    attrs = termios.tcgetattr(fd)
    attrs[0] = attrs[0] & ~(termios.IGNBRK | termios.BRKINT | termios.PARMRK | termios.ISTRIP)
    attrs[1] = attrs[1] & ~termios.OPOST
    attrs[2] = attrs[2] | termios.CLOCAL | termios.CREAD
    attrs[2] = attrs[2] & ~(termios.PARENB | termios.CSTOPB | termios.CSIZE)
    attrs[2] = attrs[2] | termios.CS8
    attrs[3] = attrs[3] & ~(
        termios.ICANON | termios.ECHO | termios.ECHOE | termios.ISIG | termios.IEXTEN
    )
    attrs[3] = attrs[3] & ~(termios.IXON | termios.IXOFF | termios.IXANY)
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 0
    termios.cfsetispeed(attrs, baud)
    termios.cfsetospeed(attrs, baud)
    termios.tcsetattr(fd, termios.TCSANOW, attrs)


def _read_until(fd: int, *, timeout: float, wait_prompt: str | None = None) -> str:
    chunks: list[bytes] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], max(0.05, deadline - time.monotonic()))
        if not ready:
            if chunks:
                break
            continue
        data = os.read(fd, 4096)
        if not data:
            break
        chunks.append(data)
        text = b"".join(chunks).decode("utf-8", errors="replace")
        if wait_prompt and wait_prompt not in text:
            continue
        if "OK" in text or "ERROR" in text or "+CMS ERROR" in text or "+CME ERROR" in text:
            break
        if "+CMGS:" in text and "OK" in text:
            break
    return b"".join(chunks).decode("utf-8", errors="replace")


def _parse_cmgl(response: str) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for match in _CMGL_RE.finditer(response + "\nOK"):
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
                "modem_sms_id": f"at:{index}",
            }
        )
    return messages
