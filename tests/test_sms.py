"""Tests for SMS import state logic."""

from hipi.daemon.sms import INBOUND_IMPORT_STATES, OUTBOUND_IMPORT_STATES, SmsService


def test_import_state_sets():
    assert 3 in INBOUND_IMPORT_STATES  # RECEIVED
    assert 1 in INBOUND_IMPORT_STATES  # STORED
    assert 5 in OUTBOUND_IMPORT_STATES  # SENT
    assert 4 not in OUTBOUND_IMPORT_STATES  # SENDING


def test_status_for_state():
    assert SmsService._status_for_state(5, "outbound") == "sent"
    assert SmsService._status_for_state(4, "outbound") == "sending"
    assert SmsService._status_for_state(3, "inbound") == "received"
