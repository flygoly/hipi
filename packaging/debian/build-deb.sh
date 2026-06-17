#!/usr/bin/env bash
# Build HiPi .deb package (run on target ARM64 Ubuntu or with native Python)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="${1:-0.1.0}"
BUILD_DIR="$ROOT/build/debian"
PKG_DIR="$BUILD_DIR/hipi_${VERSION}_arm64"

rm -rf "$PKG_DIR"
mkdir -p "$PKG_DIR/DEBIAN" "$PKG_DIR/usr/lib/hipi" "$PKG_DIR/usr/bin"
mkdir -p "$PKG_DIR/usr/share/applications" "$PKG_DIR/usr/share/polkit-1/actions"
mkdir -p "$PKG_DIR/lib/udev/rules.d" "$PKG_DIR/usr/lib/systemd/user"

cd "$ROOT"
python3 -m pip install . --target "$PKG_DIR/usr/lib/hipi" --upgrade 2>/dev/null || \
  pip install . --target "$PKG_DIR/usr/lib/hipi" --upgrade

cat > "$PKG_DIR/usr/bin/hipi" <<'WRAP'
#!/bin/sh
export PYTHONPATH=/usr/lib/hipi${PYTHONPATH:+:$PYTHONPATH}
exec python3 -m hipi "$@"
WRAP
chmod 755 "$PKG_DIR/usr/bin/hipi"

cat > "$PKG_DIR/usr/bin/hipi-daemon" <<'WRAP'
#!/bin/sh
export PYTHONPATH=/usr/lib/hipi${PYTHONPATH:+:$PYTHONPATH}
exec python3 -m hipi.daemon.server "$@"
WRAP
chmod 755 "$PKG_DIR/usr/bin/hipi-daemon"

cp packaging/desktop/hipi.desktop "$PKG_DIR/usr/share/applications/"
cp packaging/polkit/com.hipi.ModemManager.policy "$PKG_DIR/usr/share/polkit-1/actions/"
cp packaging/udev/99-hipi-quectel.rules "$PKG_DIR/lib/udev/rules.d/"
cp packaging/systemd/hipi-daemon.service "$PKG_DIR/usr/lib/systemd/user/"

cat > "$PKG_DIR/DEBIAN/control" <<EOF
Package: hipi
Version: ${VERSION}
Section: net
Priority: optional
Architecture: arm64
Depends: python3 (>= 3.11), python3-gi, python3-dbus, modemmanager, network-manager, pipewire, libqmi-utils
Maintainer: HiPi Contributors <hipi@localhost>
Description: HiPi 4G SMS and voice desktop app
 Out-of-the-box SMS and voice for Quectel EC801E on Orange Pi Ubuntu Desktop.
EOF

cat > "$PKG_DIR/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
  udevadm control --reload-rules 2>/dev/null || true
  udevadm trigger 2>/dev/null || true
  for u in $(users); do
    usermod -aG dialout,plugdev "$u" 2>/dev/null || true
  done
fi
POSTINST
chmod 755 "$PKG_DIR/DEBIAN/postinst"

dpkg-deb --build "$PKG_DIR"
echo "Built: ${PKG_DIR}.deb"
