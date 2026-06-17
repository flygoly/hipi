"""Tests for Unix socket RPC server."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from hipi.daemon.rpc import RpcServer


@pytest.mark.asyncio
async def test_rpc_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        sock = str(Path(tmp) / "test.sock")
        server = RpcServer(sock)
        server.register("echo", lambda p: {"value": p.get("x")})
        await server.start()

        reader, writer = await asyncio.open_unix_connection(sock)
        req = json.dumps({"id": "1", "method": "echo", "params": {"x": 42}}) + "\n"
        writer.write(req.encode())
        await writer.drain()
        line = await reader.readline()
        writer.close()
        await writer.wait_closed()
        await server.stop()

        resp = json.loads(line.decode())
        assert resp["ok"] is True
        assert resp["result"]["value"] == 42


@pytest.mark.asyncio
async def test_rpc_broadcast_event():
    with tempfile.TemporaryDirectory() as tmp:
        sock = str(Path(tmp) / "test.sock")
        server = RpcServer(sock)
        server.register("ping", lambda _p: True)
        await server.start()

        reader, writer = await asyncio.open_unix_connection(sock)
        await server.broadcast_event("new_message", {"body": "hi"})

        line = await asyncio.wait_for(reader.readline(), timeout=2.0)
        writer.close()
        await writer.wait_closed()
        await server.stop()

        msg = json.loads(line.decode())
        assert msg["type"] == "event"
        assert msg["event"] == "new_message"
        assert msg["payload"]["body"] == "hi"
