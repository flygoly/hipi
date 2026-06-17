"""Optional hardware smoke tests (require modem)."""

import pytest

from hipi.daemon.rpc_client import RpcClient, RpcError


@pytest.mark.hardware
def test_daemon_status():
    client = RpcClient()
    try:
        status = client.call("get_status")
    except RpcError:
        pytest.skip("hipi-daemon not running")
    assert "modem_present" in status
