#!/usr/bin/env bash
# Install D-Bus / Polkit / udev rules so hipi-daemon can use ModemManager as a normal user.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

echo "==> D-Bus policy (dialout/plugdev -> ModemManager)"
install -m 644 "$ROOT/packaging/dbus/hipi-modemmanager.conf" \
  /etc/dbus-1/system.d/hipi-modemmanager.conf

echo "==> Polkit action defaults"
install -m 644 "$ROOT/packaging/polkit/com.hipi.ModemManager.policy" \
  /usr/share/polkit-1/actions/com.hipi.ModemManager.policy

echo "==> Polkit rules (dialout/plugdev)"
install -m 644 "$ROOT/packaging/polkit/50-hipi-modemmanager.rules" \
  /etc/polkit-1/rules.d/50-hipi-modemmanager.rules

echo "==> udev rules (Quectel USB)"
install -m 644 "$ROOT/packaging/udev/99-hipi-quectel.rules" \
  /lib/udev/rules.d/99-hipi-quectel.rules
udevadm control --reload-rules 2>/dev/null || true
udevadm trigger 2>/dev/null || true

if [[ -n "${SUDO_USER:-}" ]]; then
  echo "==> Add $SUDO_USER to dialout, plugdev"
  usermod -aG dialout,plugdev "$SUDO_USER" 2>/dev/null || true
fi

echo "==> Reload D-Bus"
systemctl reload dbus 2>/dev/null || systemctl restart dbus

if [[ -x "$ROOT/scripts/setup-quectel-ec801e.sh" ]]; then
  echo "==> Quectel EC801E USB serial"
  bash "$ROOT/scripts/setup-quectel-ec801e.sh"
fi

echo ""
echo "System policy installed."
echo "  1. Log out and log back in (dialout/plugdev group)"
echo "  2. systemctl --user restart hipi-daemon"
echo "  3. hipi ping && hipi status"
