#!/usr/bin/env bash
# Ensure Quectel EC801E serial ports are available (ECM usbnet 1/3)
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

modprobe option 2>/dev/null || true

for vidpid in "2c7c:0903" "2c7c:0801"; do
  vid="${vidpid%%:*}"
  pid="${vidpid##*:}"
  if lsusb -d "${vid}:${pid}" >/dev/null 2>&1; then
    echo "==> Binding option driver for ${vidpid}"
    echo "${vid} ${pid}" > /sys/bus/usb-serial/drivers/option1/new_id 2>/dev/null || true
  fi
done

echo "option" > /etc/modules-load.d/hipi-option.conf 2>/dev/null || true

# Install udev rule to release one AT port from ModemManager
RULES_DST="/etc/udev/rules.d/99-hipi-quectel.rules"
if [ -f "$(dirname "$0")/packaging/udev/99-hipi-quectel.rules" ]; then
  cp "$(dirname "$0")/packaging/udev/99-hipi-quectel.rules" "$RULES_DST"
elif [ -f "/usr/lib/udev/rules.d/99-hipi-quectel.rules" ]; then
  cp "/usr/lib/udev/rules.d/99-hipi-quectel.rules" "$RULES_DST"
fi
udevadm control --reload-rules 2>/dev/null || true

echo "Done. Replug EC801E if /dev/ttyUSB* is missing."
