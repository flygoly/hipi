#!/usr/bin/env bash
# Optional Quectel EC801E voice/IMS tuning for China carriers
set -euo pipefail

if ! command -v mmcli >/dev/null; then
  echo "mmcli not found. Install modemmanager." >&2
  exit 1
fi

MODEM="${1:-0}"
AT_PORT=$(mmcli -m "$MODEM" 2>/dev/null | awk -F"'" '/primary port:/ {print $2}')
if [[ -z "$AT_PORT" ]]; then
  echo "Cannot find modem $MODEM" >&2
  exit 1
fi

run_at() {
  local cmd="$1"
  echo ">> AT$cmd"
  mmcli -m "$MODEM" --command="$cmd" || true
}

echo "=== Quectel EC801E voice setup (modem $MODEM, port $AT_PORT) ==="

# ECM data mode (recommended on Linux)
run_at 'AT+QCFG="usbnet",1'

# Check IMS state (VoLTE optional on EC801E)
run_at 'AT+QCFG="ims"'

# If SMS fails in LTE-only mode, try CS domain preference (carrier-specific)
# run_at 'AT+QNVWR="sms_domain_pref",00'

echo ""
echo "Restart ModemManager if settings changed:"
echo "  sudo systemctl restart ModemManager"
echo ""
echo "Verify audio: cat /proc/asound/cards | grep -i quectel"
