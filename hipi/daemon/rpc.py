"""Unix socket JSON-RPC for UI ↔ daemon communication."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

Handler = Callable[[dict[str, Any]], Awaitable[Any] | Any]


class RpcError(Exception):
    pass


class RpcServer:
    def __init__(self, socket_path: str) -> None:
        self.socket_path = socket_path
        self._handlers: dict[str, Handler] = {}
        self._clients: set[asyncio.StreamWriter] = set()
        self._server: asyncio.Server | None = None
        self._client_added: asyncio.Event | None = None

    def register(self, method: str, handler: Handler) -> None:
        self._handlers[method] = handler

    async def broadcast_event(self, event: str, payload: dict[str, Any]) -> None:
        message = json.dumps({"type": "event", "event": event, "payload": payload}) + "\n"
        if not self._clients and self._client_added:
            # wait briefly for a client to connect (tests only)
            try:
                await asyncio.wait_for(self._client_added.wait(), timeout=0.5)
            except asyncio.TimeoutError:
                pass
        dead: list[asyncio.StreamWriter] = []
        for writer in self._clients:
            try:
                writer.write(message.encode("utf-8"))
                await writer.drain()
            except (ConnectionError, OSError):
                dead.append(writer)
        for writer in dead:
            self._clients.discard(writer)

    async def start(self) -> None:
        from pathlib import Path

        path = Path(self.socket_path)
        if path.exists():
            path.unlink()
        self._server = await asyncio.start_unix_server(self._handle_client, path=self.socket_path)
        path.chmod(0o600)
        logger.info("RPC server listening on %s", self.socket_path)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        for writer in list(self._clients):
            writer.close()
            await writer.wait_closed()
        self._clients.clear()

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        self._clients.add(writer)
        if self._client_added:
            self._client_added.set()
            self._client_added.clear()
        buffer = ""
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                buffer += data.decode("utf-8", errors="replace")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    response = await self._dispatch(line)
                    writer.write((json.dumps(response) + "\n").encode("utf-8"))
                    await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            self._clients.discard(writer)
            writer.close()
            await writer.wait_closed()

    async def _dispatch(self, line: str) -> dict[str, Any]:
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            return {"ok": False, "error": "Invalid JSON"}

        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}

        if not method or method not in self._handlers:
            return {"id": req_id, "ok": False, "error": f"Unknown method: {method}"}

        try:
            handler = self._handlers[method]
            result = handler(params)
            if asyncio.iscoroutine(result):
                result = await result
            return {"id": req_id, "ok": True, "result": result}
        except Exception as exc:
            logger.exception("RPC handler error for %s", method)
            return {"id": req_id, "ok": False, "error": str(exc)}
