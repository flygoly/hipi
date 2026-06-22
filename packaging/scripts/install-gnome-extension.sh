#!/usr/bin/env bash
# Install HiPi GNOME Shell extension for one user (from deb or git tree)
set -euo pipefail

if [[ -n "${HIPI_EXT_SRC:-}" ]]; then
  EXT_SRC="$HIPI_EXT_SRC"
elif [[ -d /usr/share/hipi/gnome-shell-extension/hipi@hipi ]]; then
  EXT_SRC="/usr/share/hipi/gnome-shell-extension/hipi@hipi"
else
  ROOT="$(cd "$(dirname "$0")/.." && pwd)"
  EXT_SRC="$ROOT/gnome-shell-extension/hipi@hipi"
fi

EXT_DST="${HOME}/.local/share/gnome-shell/extensions/hipi@hipi"

if [[ ! -d "$EXT_SRC" ]]; then
  echo "Extension source not found: $EXT_SRC" >&2
  exit 1
fi

mkdir -p "$(dirname "$EXT_DST")"
rm -rf "$EXT_DST"
cp -a "$EXT_SRC" "$EXT_DST"

if command -v gnome-extensions >/dev/null; then
  gnome-extensions enable hipi@hipi 2>/dev/null || true
fi
