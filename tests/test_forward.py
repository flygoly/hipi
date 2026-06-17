"""Tests for SMS forwarding rules."""

from hipi.daemon.forward import is_forwardable_sms


def test_forwardable_text_sms():
    assert is_forwardable_sms({"PduType": 1, "Encoding": 3}, "你好")


def test_skip_empty_body():
    assert not is_forwardable_sms({"PduType": 1}, "")


def test_skip_forward_loop():
    assert not is_forwardable_sms({"PduType": 1}, "[HiPi转发] 来自 +86111: hi")


def test_skip_status_report():
    assert not is_forwardable_sms({"PduType": 3}, "delivery report")
