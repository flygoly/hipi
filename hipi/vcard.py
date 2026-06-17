"""Minimal vCard 3.0 import/export for contacts."""

from __future__ import annotations

import re
from dataclasses import dataclass

from hipi.util import normalize_number

_VCARD_SPLIT = re.compile(r"BEGIN:VCARD", re.IGNORECASE)
_LINE = re.compile(r"^([^:;]+)(?:;([^:]*))?:(.*)$", re.MULTILINE)


@dataclass
class VCardContact:
    name: str
    number: str
    notes: str = ""


def parse_vcard(text: str) -> list[VCardContact]:
    """Parse one or more vCards from text."""
    chunks = _VCARD_SPLIT.split(text)
    results: list[VCardContact] = []

    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        if not chunk.upper().startswith("VERSION:"):
            chunk = "VERSION:3.0\n" + chunk

        name = ""
        number = ""
        notes = ""

        for match in _LINE.finditer(chunk):
            key = match.group(1).upper()
            params = (match.group(2) or "").upper()
            value = match.group(3).strip()

            if key == "END":
                break
            if key == "FN":
                name = _unescape(value)
            elif key == "N" and not name:
                parts = value.split(";")
                name = _unescape(" ".join(p for p in parts[:2] if p))
            elif key == "TEL" and not number:
                if "FAX" not in params:
                    number = _clean_tel(value)
            elif key == "NOTE":
                notes = _unescape(value)

        if name and number:
            results.append(VCardContact(name=name, number=number, notes=notes))

    return results


def export_vcards(contacts: list[dict]) -> str:
    """Export contacts as vCard 3.0 text."""
    lines: list[str] = []
    for c in contacts:
        name = c.get("name", "")
        number = c.get("number", "")
        notes = c.get("notes", "")
        lines.append("BEGIN:VCARD")
        lines.append("VERSION:3.0")
        lines.append(f"FN:{_escape(name)}")
        lines.append(f"TEL;TYPE=CELL:{number}")
        if notes:
            lines.append(f"NOTE:{_escape(notes)}")
        lines.append("END:VCARD")
    return "\n".join(lines) + ("\n" if lines else "")


def _clean_tel(value: str) -> str:
    return normalize_number(re.sub(r"[^\d+]", "", value.split(",")[0]))


def _unescape(value: str) -> str:
    return (
        value.replace("\\n", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")
