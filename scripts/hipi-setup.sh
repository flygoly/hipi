#!/usr/bin/env bash
# HiPi EC801E full setup — single command.
# Run: sudo ~/Documents/workspace/hipi/scripts/hipi-setup.sh
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

USERNAME="${SUDO_USER:-$USER}"
HOME_DIR="$(getent passwd "$USERNAME" | cut -d: -f6)"
WS="$HOME_DIR/Documents/workspace/hipi"

SECTION() { echo; echo "==> $*"; }

# ── 1. Enable MM debug mode (allows AT Command() via D-Bus) ───────
SECTION "Enabling ModemManager debug mode"
mkdir -p /etc/systemd/system/ModemManager.service.d
cat > /etc/systemd/system/ModemManager.service.d/hipi-debug.conf <<'UNIT'
[Service]
Environment=MM_FILTER_RULE_EXPLICIT_BLACKLIST=1
Environment=MM_FILTER_RULE_TTY_BLACKLIST=
ExecStart=
ExecStart=/usr/sbin/ModemManager --debug
UNIT
systemctl daemon-reload

# ── 2. Udev rule ──────────────────────────────────────────────────
SECTION "Installing udev rule"
D=/etc/udev/rules.d/99-hipi-quectel.rules
cat > "$D" <<'RULE'
SUBSYSTEM=="tty", ATTRS{idVendor}=="2c7c", GROUP="dialout", MODE="0660"
SUBSYSTEM=="usb", ATTRS{idVendor}=="2c7c", GROUP="plugdev", MODE="0660"
RULE
udevadm control --reload-rules
echo "  Installed"

# ── 3. USB re-plug ────────────────────────────────────────────────
SECTION "Waiting for EC801E USB re-plug (20s)..."
echo "  NOW unplug EC801E, wait 3s, replug."
echo "  Polling for 2c7c:0903 ..."
for i in $(seq 20 -1 1); do
  if lsusb -d 2c7c:0903 >/dev/null 2>&1; then
    echo "  Detected"; break
  fi
  [[ $i -eq 1 ]] && { echo "  Timeout"; exit 1; }
  sleep 1
done
sleep 2

# ── 4. Bind option driver ─────────────────────────────────────────
SECTION "Binding option driver"
modprobe option 2>/dev/null || true
sleep 0.5
echo "2c7c 0903" > /sys/bus/usb-serial/drivers/option1/new_id 2>/dev/null || true
sleep 0.5
if ! ls /dev/ttyUSB* >/dev/null 2>&1; then
  echo "  No /dev/ttyUSB* — re-plug and re-run."
  exit 1
fi
ls -l /dev/ttyUSB*

# ── 5. Restart ModemManager ───────────────────────────────────────
SECTION "Restarting ModemManager (debug mode)"
systemctl restart ModemManager
sleep 4

echo "  ModemManager ports:"
mmcli -m 0 2>/dev/null | grep -E 'port|Port' || echo "(no modem yet)"

# ── 6. dialout group ──────────────────────────────────────────────
SECTION "Checking dialout group"
if groups "$USERNAME" | grep -qw dialout; then
  echo "  $USERNAME is in dialout"
else
  usermod -aG dialout "$USERNAME"
  echo "  Added $USERNAME to dialout (re-login needed)"
fi

# ── 7. Install hipi ───────────────────────────────────────────────
SECTION "Installing hipi"
cd "$WS"
git pull --ff-only 2>/dev/null || true
sudo -u "$USERNAME" pip3 install --user --break-system-packages -q .
echo "  Done"

# ── 8. Restart hipi-daemon ────────────────────────────────────────
SECTION "Restarting hipi-daemon"
pkill -f 'python3.*hipi-daemon' 2>/dev/null || true
sleep 1
rm -f /run/user/1000/hipi.sock
rm -f "$HOME_DIR/.config/hipi/at_port"

HIPI="/home/$USERNAME/.local/bin/hipi-daemon"
sudo -u "$USERNAME" nohup "$HIPI" > /dev/null 2>&1 &
sleep 3

# ── 9. Show result ────────────────────────────────────────────────
SECTION "hipi status"
sudo -u "$USERNAME" /home/"$USERNAME"/.local/bin/hipi status 2>/dev/null || echo "(daemon not ready yet)"

echo
echo "══ Done. Run 'hipi status' to verify. ══"