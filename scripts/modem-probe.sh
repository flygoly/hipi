#!/usr/bin/env bash
# HiPi modem diagnostics for Quectel EC801E on Orange Pi
set -euo pipefail

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().strip()))'
}

echo "{"
echo '  "timestamp": "'"$(date -Iseconds)"'",'

echo -n '  "lsusb_quectel": '
if lsusb 2>/dev/null | grep -i '2c7c\|quectel' >/dev/null; then
  lsusb | grep -i '2c7c\|quectel' | json_escape
else
  echo 'null'
fi

echo -n '  "mmcli_version": '
if command -v mmcli >/dev/null; then
  mmcli --version 2>/dev/null | head -1 | json_escape
else
  echo 'null'
fi

echo -n '  "modemmanager_active": '
if systemctl is-active ModemManager >/dev/null 2>&1; then
  echo 'true'
else
  echo 'false'
fi

echo -n '  "modems": '
if command -v mmcli >/dev/null; then
  mmcli -L 2>/dev/null | json_escape || echo 'null'
else
  echo 'null'
fi

echo -n '  "primary_modem": '
if command -v mmcli >/dev/null && mmcli -m 0 >/dev/null 2>&1; then
  mmcli -m 0 2>/dev/null | json_escape
else
  echo 'null'
fi

echo -n '  "alsa_cards": '
if [[ -f /proc/asound/cards ]]; then
  cat /proc/asound/cards | json_escape
else
  echo 'null'
fi

echo -n '  "kernel_modules": '
lsmod 2>/dev/null | grep -E 'qmi_wwan|option|usbserial' | json_escape || echo '""'

echo "}"
