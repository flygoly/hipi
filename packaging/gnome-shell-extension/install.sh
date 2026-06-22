#!/usr/bin/env bash
# Install HiPi GNOME Shell extension for the current user
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
export HIPI_EXT_SRC="$ROOT/hipi@hipi"
bash "$(cd "$ROOT/.." && pwd)/scripts/install-gnome-extension.sh"

if command -v gnome-extensions >/dev/null; then
  echo "Installed. Log out/in or restart GNOME Shell if the icon does not appear."
else
  echo "Installed extension. Install gnome-extensions and run: gnome-extensions enable hipi@hipi"
fi
