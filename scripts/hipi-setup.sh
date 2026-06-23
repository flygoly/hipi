#!/usr/bin/env bash
# HiPi EC801E one-shot setup: install udev rule → bind driver → restart services.
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

# ── 1. Udev rule ──────────────────────────────────────────────────
SECTION "Installing udev rule (MM ignores ttyUSB1/interface 03)"
D=/etc/udev/rules.d/99-hipi-quectel.rules
cat > "$D" <<'RULE'
# Quectel USB modems (EC801E etc.)
SUBSYSTEM=="tty", ATTRS{idVendor}=="2c7c", GROUP="dialout", MODE="0660"
SUBSYSTEM=="usb", ATTRS{idVendor}=="2c7c", GROUP="plugdev", MODE="0660"
KERNEL=="cdc-wdm*", ATTRS{idVendor}=="2c7c", GROUP="dialout", MODE="0660"
KERNEL=="wwan*", ATTRS{idVendor}=="2c7c", GROUP="dialout", MODE="0660"
SUBSYSTEM=="tty", ATTRS{idVendor}=="2c7c", ATTRS{idProduct}=="0903", \
  ATTRS{bInterfaceNumber}=="03", ENV{ID_MM_PORT_IGNORE}="1"
RULE
udevadm control --reload-rules
echo "  Installed"

# ── 2. USB re-plug ────────────────────────────────────────────────
SECTION "Waiting for EC801E USB re-plug (you have 20 seconds)..."
echo "  NOW unplug EC801E from VMware, wait 3s, replug, then WAIT."
echo "  (VMware -> Removable Devices -> Disconnect -> Connect)"
echo "  Polling for 2c7c:0903 ..."

for i in $(seq 20 -1 1); do
  if lsusb -d 2c7c:0903 >/dev/null 2>&1; then
    echo "  Detected"
    break
  fi
  if [[ $i -eq 1 ]]; then
    echo "  Timeout - no EC801E found on USB bus"
    exit 1
  fi
  sleep 1
done

sleep 2

# ── 3. Bind option driver ─────────────────────────────────────────
SECTION "Binding option driver"
modprobe option 2>/dev/null || true
sleep 0.5
echo "2c7c 0903" > /sys/bus/usb-serial/drivers/option1/new_id 2>/dev/null || true
sleep 0.5

TTYS=$(ls /dev/ttyUSB* 2>/dev/null || true)
if [[ -z "$TTYS" ]]; then
  echo "  No /dev/ttyUSB* - binding failed. Re-plug and re-run."
  exit 1
fi
echo "  ttyUSB devices:"
ls -l /dev/ttyUSB*

# ── 4. Restart ModemManager ───────────────────────────────────────
SECTION "Restarting ModemManager"
systemctl daemon-reload
systemctl restart ModemManager
sleep 3

echo "  ModemManager ports:"
mmcli -m 0 2>/dev/null | grep -E 'port|Port' || echo "(no modem yet - OK, MM may take a moment)"

# ── 5. Check port availability ────────────────────────────────────
SECTION "Checking port availability"
for p in /dev/ttyUSB{0,1,2}; do
  if [[ -e "$p" ]]; then
    if timeout 1 python3 -c "
import os
os.open('$p', os.O_RDWR | os.O_NOCTTY)
" 2>/dev/null; then
      echo "  $p : FREE (available for hipi)"
    else
      echo "  $p : BUSY (locked by ModemManager)"
    fi
  fi
done

# ── 6. Ensure dialout group ───────────────────────────────────────
SECTION "Checking dialout group"
if groups "$USERNAME" | grep -qw dialout; then
  echo "  $USERNAME is in dialout group"
else
  usermod -aG dialout "$USERNAME" 2>/dev/null || true
  echo "  Added $USERNAME to dialout (re-login required for effect)"
fi

# ── 7. Install hipi (user pip) ────────────────────────────────────
SECTION "Installing hipi"
cd "$WS"
git pull --ff-only 2>/dev/null || true
sudo -u "$USERNAME" pip3 install --user --break-system-packages -q . 2>/dev/null || true
echo "  Done"

# ── 8. Restart hipi-daemon ────────────────────────────────────────
SECTION "Restarting hipi-daemon"
pkill -f 'python3.*hipi-daemon' 2>/dev/null || true
sleep 1
rm -f /run/user/1000/hipi.sock
rm -f "$HOME_DIR/.config/hipi/at_port"

HIPI_DAEMON="/home/$USERNAME/.local/bin/hipi-daemon"
sudo -u "$USERNAME" nohup "$HIPI_DAEMON" > /dev/null 2>&1 &
sleep 3

# ── 9. Show result ────────────────────────────────────────────────
SECTION "hipi status"
sudo -u "$USERNAME" /home/"$USERNAME"/.local/bin/hipi status 2>/dev/null || echo "(daemon not ready yet)"

echo
echo "== Done. Run 'hipi status' to see sms_backend and at_port. =="
echo "   If sms_backend is still 'none', re-login (for dialout group)"
echo "   and run: systemctl --user restart hipi-daemon"