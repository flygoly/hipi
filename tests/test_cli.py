"""Tests for CLI argument routing."""

from unittest.mock import MagicMock, patch

from hipi.cli import main


def _mock_client(**returns):
    client = MagicMock()
    client.call.side_effect = lambda method, params=None: returns.get(
        method, {"ok": True} if method != "list_messages" else []
    )
    return client


def test_cli_dial():
    client = _mock_client(dial={"ok": True, "path": "/call/1"})
    with patch("hipi.cli.RpcClient", return_value=client):
        assert main(["dial", "13800138000"]) == 0
    client.call.assert_called_with("dial", {"number": "13800138000"})


def test_cli_hangup():
    client = _mock_client(hangup={"ok": True})
    with patch("hipi.cli.RpcClient", return_value=client):
        assert main(["hangup"]) == 0
    client.call.assert_called_with("hangup", {})


def test_cli_sync_modem():
    client = _mock_client(sync_modem={"ok": True})
    with patch("hipi.cli.RpcClient", return_value=client):
        assert main(["sync"]) == 0
    client.call.assert_called_with("sync_modem")


def test_cli_list_calls():
    client = _mock_client(list_calls=[{"peer": "+861111"}])
    with patch("hipi.cli.RpcClient", return_value=client):
        assert main(["list-calls", "--limit", "10"]) == 0
    client.call.assert_called_with("list_calls", {"limit": 10})
