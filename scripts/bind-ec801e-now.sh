#!/usr/bin/env bash
# Bind Quectel EC801E USB interfaces to option driver (RNDIS mode).
# Run once per USB connection.
set -euo pipefail

echo "==> Binding EC801E (2c7c:0903) to option driver"
echo "2c7c 0903" > /sys/bus/usb-serial/drivers/option1/new_id

sleep 0.5
echo "==> ttyUSB devices:"
ls -l /dev/ttyUSB* 2>/dev/null || echo "(none found yet — re-plug USB and re-run this script)"

echo "==> Restart ModemManager"
systemctl restart ModemManager
sleep 2

echo "==> ModemManager modems:"
mmcli -L 2>/dev/null || echo "(none)"

echo "==> Restart hipi-daemon"
systemctl --user restart hipi-daemon 2>/dev/null || true
sleep 2

echo "==> hipi status:"
hipi status 2>/dev/null || /home/flygoly/.local/bin/hipi status