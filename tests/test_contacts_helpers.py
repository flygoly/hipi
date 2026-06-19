"""Tests for contact display helpers."""

from hipi.contacts import contact_display_name, match_contact_number


def test_contact_display_name_with_name():
    assert contact_display_name("+8613800138000", "张三") == "张三 (+8613800138000)"


def test_contact_display_name_without_name():
    assert contact_display_name("+8613800138000", None) == "+8613800138000"


def test_match_contact_number():
    assert match_contact_number("+8613800138000", "13800138000")
    assert not match_contact_number("+861111", "+862222")
