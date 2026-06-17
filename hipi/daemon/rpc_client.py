"""Synchronous RPC client for CLI and UI."""

from __future__ import annotations

import json
import socket
import uuid
from typing import Any

from hipi.config import DEFAULT_RPC_TIMEOUT, SOCKET_PATH


class RpcError(Exception):
    pass


class RpcClient:
    def __init__(self, socket_path: str | None = None, timeout: float = DEFAULT_RPC_TIMEOUT) -> None:
        self.socket_path = socket_path or str(SOCKET_PATH)
        self.timeout = timeout

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
            raise RpcError(
                "HiPi daemon is not running. Start it with: hipi-daemon"
            ) from exc

        line = data.decode("utf-8").split("\n", 1)[0]
        response = json.loads(line)
        if not response.get("ok"):
            raise RpcError(response.get("error", "Unknown RPC error"))
        return response.get("result")

    def ping(self) -> bool:
        try:
            self.call("ping")
            return True
        except RpcError:
            return False
