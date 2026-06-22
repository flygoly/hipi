"""Sanity checks for packaging scripts and metadata."""

from pathlib import Path


def test_build_deb_declares_audio_deps():
    text = Path("packaging/debian/build-deb.sh").read_text(encoding="utf-8")
    assert "pipewire-pulse" in text or "pulseaudio-utils" in text
    assert "enable --now hipi-daemon" in text


def test_build_deb_ships_icon_and_extension():
    text = Path("packaging/debian/build-deb.sh").read_text(encoding="utf-8")
    assert "hipi.svg" in text
    assert "gnome-shell-extension" in text


def test_desktop_entry_uses_hipi_icon():
    text = Path("packaging/desktop/hipi.desktop").read_text(encoding="utf-8")
    assert "Icon=hipi" in text
