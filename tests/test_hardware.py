"""Optional hardware smoke tests (require modem)."""

import pytest

from hipi.daemon.rpc_client import RpcClient, RpcError


def _client_or_skip() -> RpcClient:
    client = RpcClient()
    try:
        client.call("ping")
    except RpcError:
        pytest.skip("hipi-daemon not running")
    return client


@pytest.mark.hardware
def test_daemon_ping():
    client = _client_or_skip()
    assert client.call("ping") == {"pong": True}


@pytest.mark.hardware
def test_daemon_status():
    client = _client_or_skip()
    status = client.call("get_status")
    assert "modem_present" in status
    assert "unread_sms" in status
    if status.get("modem_present"):
        modem = status["modem"]
        assert "signal_quality" in modem
        assert "state" in modem


@pytest.mark.hardware
def test_list_conversations_shape():
    client = _client_or_skip()
    convs = client.call("list_conversations")
    assert isinstance(convs, list)


@pytest.mark.hardware
def test_setup_call_audio():
    client = _client_or_skip()
    status = client.call("get_status")
    if not status.get("modem_present"):
        pytest.skip("no modem")
    result = client.call("setup_call_audio")
    assert "ok" in result
