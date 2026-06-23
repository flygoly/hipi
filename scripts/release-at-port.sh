#!/usr/bin/env bash
# One-shot: install udev rule, release AT port from MM, restart services.
set -euo pipefail

SRC="$(dirname "$0")/packaging/udev/99-hipi-quectel.rules"
DST="/etc/udev/rules.d/99-hipi-quectel.rules"

echo "==> Installing udev rule to free one AT port from ModemManager"
cp "$SRC" "$DST"
udevadm control --reload-rules
udevadm trigger --subsystem-match=tty --attr-match=idVendor=2c7c
sleep 1

echo "==> Restarting ModemManager (this releases the AT port)"
systemctl restart ModemManager
sleep 2

echo "==> ttyUSB devices:"
ls -l /dev/ttyUSB* 2>/dev/null || echo "(none)"

echo "==> ModemManager ports:"
mmcli -m 0 2>/dev/null | grep -E 'port|Port' || echo "(no modem found)"

echo "==> Confirm port is now free for hipi:"
for p in /dev/ttyUSB{0,1,2}; do
  if timeout 2 python3 -c "
import os
fd = os.open('$p', os.O_RDWR | os.O_NOCTTY)
os.close(fd)
print('$p: OPENABLE')" 2>/dev/null; then
    :  # printed by python
  else
    echo "$p: busy"
  fi
done

echo "==> Restarting hipi-daemon"
systemctl --user restart hipi-daemon 2>/dev/null || {
  pkill -f 'python3.*hipi-daemon' 2>/dev/null || true
  rm -f /run/user/1000/hipi.sock
  nohup /home/flygoly/.local/bin/hipi-daemon > /tmp/hipi-debug.log 2>&1 &
  sleep 3
}
sleep 2

echo "==> hipi status:"
hipi status 2>/dev/null || /home/flygoly/.local/bin/hipi status 2>/dev/null || echo "(hipi status failed)"