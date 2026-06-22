#!/usr/bin/env bash
# Build and install HiPi .deb on Orange Pi (ARM64 Ubuntu)
set -euo pipefail

VERSION="${1:-0.1.0}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Installing system dependencies"
sudo apt update
sudo apt install -y python3-pip python3-venv git \
  python3-gi python3-dbus modemmanager network-manager \
  pipewire pipewire-pulse libqmi-utils gir1.2-glib-2.0

echo "==> Building hipi_${VERSION}_arm64.deb"
cd "$ROOT"
chmod +x packaging/debian/build-deb.sh
./packaging/debian/build-deb.sh "$VERSION"

DEB="build/debian/hipi_${VERSION}_arm64.deb"
if [[ ! -f "$DEB" ]]; then
  echo "Build failed: $DEB not found" >&2
  exit 1
fi

echo "==> Installing package"
sudo dpkg -i "$DEB" || sudo apt install -f -y

echo "==> Installing ModemManager system policy (D-Bus / Polkit)"
sudo "$ROOT/scripts/install-system-policy.sh"

echo ""
echo "HiPi ${VERSION} installed."
echo "  1. Log out and log back in (dialout/plugdev group)"
echo "  2. Insert EC801E + SIM if not already"
echo "  3. Run: hipi ping && hipi status"
echo "  4. Run: hipi ui"
echo ""
echo "Full guide: docs/getting-started.md"
