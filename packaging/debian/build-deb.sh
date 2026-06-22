#!/usr/bin/env bash
# Build HiPi .deb package (run on target ARM64 Ubuntu or with native Python)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VERSION="${1:-0.1.0}"
BUILD_DIR="$ROOT/build/debian"
PKG_DIR="$BUILD_DIR/hipi_${VERSION}_arm64"

if [[ ! -f "$ROOT/pyproject.toml" ]]; then
  echo "Error: pyproject.toml not found at $ROOT (wrong ROOT?)" >&2
  exit 1
fi

rm -rf "$PKG_DIR"
mkdir -p "$PKG_DIR/DEBIAN" "$PKG_DIR/usr/lib/hipi" "$PKG_DIR/usr/bin"
mkdir -p "$PKG_DIR/usr/share/applications" "$PKG_DIR/usr/share/polkit-1/actions"
mkdir -p "$PKG_DIR/usr/share/icons/hicolor/scalable/apps"
mkdir -p "$PKG_DIR/usr/share/hipi/gnome-shell-extension"
mkdir -p "$PKG_DIR/usr/share/hipi/scripts"
mkdir -p "$PKG_DIR/lib/udev/rules.d" "$PKG_DIR/usr/lib/systemd/user"
mkdir -p "$PKG_DIR/etc/dbus-1/system.d" "$PKG_DIR/etc/polkit-1/rules.d"

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
cp packaging/icons/hipi.svg "$PKG_DIR/usr/share/icons/hicolor/scalable/apps/" 2>/dev/null || \
  cp hipi/data/hipi.svg "$PKG_DIR/usr/share/icons/hicolor/scalable/apps/"
cp -a packaging/gnome-shell-extension/hipi@hipi "$PKG_DIR/usr/share/hipi/gnome-shell-extension/"
cp packaging/scripts/install-gnome-extension.sh "$PKG_DIR/usr/share/hipi/scripts/"
chmod 755 "$PKG_DIR/usr/share/hipi/scripts/install-gnome-extension.sh"
cp packaging/polkit/com.hipi.ModemManager.policy "$PKG_DIR/usr/share/polkit-1/actions/"
cp packaging/polkit/50-hipi-modemmanager.rules "$PKG_DIR/etc/polkit-1/rules.d/"
cp packaging/dbus/hipi-modemmanager.conf "$PKG_DIR/etc/dbus-1/system.d/"
cp packaging/udev/99-hipi-quectel.rules "$PKG_DIR/lib/udev/rules.d/"
cp packaging/systemd/hipi-daemon.service "$PKG_DIR/usr/lib/systemd/user/"

cat > "$PKG_DIR/DEBIAN/control" <<EOF
Package: hipi
Version: ${VERSION}
Section: net
Priority: optional
Architecture: arm64
Depends: python3 (>= 3.11), python3-gi, python3-dbus, modemmanager, network-manager, pipewire, pipewire-pulse | pulseaudio-utils, libqmi-utils
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
  systemctl reload dbus 2>/dev/null || systemctl restart dbus 2>/dev/null || true
  for u in $(users); do
    usermod -aG dialout,plugdev "$u" 2>/dev/null || true
  done
  for home in /home/*; do
    u=$(basename "$home")
    id "$u" >/dev/null 2>&1 || continue
    if [ -d "$home" ]; then
      su - "$u" -c "systemctl --user daemon-reload" 2>/dev/null || true
      su - "$u" -c "systemctl --user enable --now hipi-daemon.service" 2>/dev/null || true
      if command -v loginctl >/dev/null; then
        loginctl enable-linger "$u" 2>/dev/null || true
      fi
      if [ -x /usr/share/hipi/scripts/install-gnome-extension.sh ]; then
        su - "$u" -c "HIPI_EXT_SRC=/usr/share/hipi/gnome-shell-extension/hipi@hipi bash /usr/share/hipi/scripts/install-gnome-extension.sh" 2>/dev/null || true
      fi
    fi
  done
fi
POSTINST
chmod 755 "$PKG_DIR/DEBIAN/postinst"

dpkg-deb --build "$PKG_DIR"
echo "Built: ${PKG_DIR}.deb"
