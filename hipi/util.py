"""Phone number normalization."""

from __future__ import annotations

import re

_NON_DIGIT = re.compile(r"[^\d+]")


def normalize_number(number: str) -> str:
    cleaned = _NON_DIGIT.sub("", number.strip())
    if cleaned.startswith("+"):
        return cleaned
    if cleaned.startswith("86") and len(cleaned) > 11:
        return f"+{cleaned}"
    if len(cleaned) == 11 and cleaned.startswith("1"):
        return f"+86{cleaned}"
    return cleaned
