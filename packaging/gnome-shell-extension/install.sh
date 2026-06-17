#!/usr/bin/env bash
# Install HiPi GNOME Shell extension for the current user
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
EXT_SRC="$ROOT/hipi@hipi"
EXT_DST="${HOME}/.local/share/gnome-shell/extensions/hipi@hipi"

if [[ ! -d "$EXT_SRC" ]]; then
  echo "Extension source not found: $EXT_SRC" >&2
  exit 1
fi

mkdir -p "$(dirname "$EXT_DST")"
rm -rf "$EXT_DST"
cp -a "$EXT_SRC" "$EXT_DST"

if command -v gnome-extensions >/dev/null; then
  gnome-extensions enable hipi@hipi || true
  echo "Installed. Log out/in or restart GNOME Shell if the icon does not appear."
else
  echo "Installed to $EXT_DST"
  echo "Install gnome-extensions CLI and run: gnome-extensions enable hipi@hipi"
fi
