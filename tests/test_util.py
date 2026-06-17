"""Tests for phone number normalization."""

from hipi.util import normalize_number


def test_normalize_china_mobile():
    assert normalize_number("13800138000") == "+8613800138000"


def test_normalize_with_plus():
    assert normalize_number("+8613800138000") == "+8613800138000"


def test_normalize_strips_formatting():
    assert normalize_number("138 0013 8000") == "+8613800138000"
