"""Contact name resolution helpers."""

from __future__ import annotations

from hipi.util import normalize_number


def contact_display_name(number: str, name: str | None) -> str:
    if name:
        return f"{name} ({number})"
    return number


def match_contact_number(stored: str, query: str) -> bool:
    return normalize_number(stored) == normalize_number(query)
