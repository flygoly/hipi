"""Async-capable RPC client with event subscription for Qt UI."""

from __future__ import annotations

import json
import socket
import threading
import uuid
from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, Signal

from hipi.config import DEFAULT_RPC_TIMEOUT, SOCKET_PATH
from hipi.daemon.rpc_client import RpcError


class RpcEventClient(QObject):
    event_received = Signal(str, dict)
    connection_lost = Signal()

    def __init__(self, socket_path: str | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.socket_path = socket_path or str(SOCKET_PATH)
        self.timeout = DEFAULT_RPC_TIMEOUT
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        request = {
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params or {},
        }
        payload = (json.dumps(request) + "\n").encode("utf-8")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout)
                sock.connect(self.socket_path)
                sock.sendall(payload)
                data = b""
                while b"\n" not in data:
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    data += chunk
        except (FileNotFoundError, ConnectionRefusedError, TimeoutError) as exc:
            raise RpcError("HiPi daemon is not running") from exc

        line = data.decode("utf-8").split("\n", 1)[0]
        response = json.loads(line)
        if not response.get("ok"):
            raise RpcError(response.get("error", "Unknown error"))
        return response.get("result")

    def _listen_loop(self) -> None:
        while not self._stop.is_set():
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                    sock.settimeout(1.0)
                    sock.connect(self.socket_path)
                    sock.sendall(
                        (json.dumps({"id": "sub", "method": "ping", "params": {}}) + "\n").encode()
                    )
                    buffer = ""
                    while not self._stop.is_set():
                        try:
                            chunk = sock.recv(4096)
                        except TimeoutError:
                            continue
                        if not chunk:
                            break
                        buffer += chunk.decode("utf-8", errors="replace")
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            self._handle_line(line.strip())
            except (ConnectionError, OSError):
                if not self._stop.is_set():
                    self.connection_lost.emit()
                self._stop.wait(2.0)

    def _handle_line(self, line: str) -> None:
        if not line:
            return
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            return
        if msg.get("type") == "event":
            self.event_received.emit(msg.get("event", ""), msg.get("payload", {}))


class DaemonStarter(QThread):
    started_ok = Signal()
    failed = Signal(str)

    def run(self) -> None:
        import subprocess
        import sys

        try:
            subprocess.Popen(
                [sys.executable, "-m", "hipi.daemon.server"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            import time

            client = RpcEventClient()
            for _ in range(20):
                time.sleep(0.25)
                try:
                    client.call("ping")
                    self.started_ok.emit()
                    return
                except RpcError:
                    continue
            self.failed.emit("Daemon did not start in time")
        except Exception as exc:
            self.failed.emit(str(exc))
