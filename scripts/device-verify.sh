#!/usr/bin/env bash
# HiPi EC801E on-device verification preflight checks
set -euo pipefail

SMOKE=false
HARDWARE_TESTS=false
for arg in "$@"; do
  case "$arg" in
    --smoke) SMOKE=true ;;
    --hardware-tests) HARDWARE_TESTS=true ;;
  esac
done

PASS=0
WARN=0
FAIL=0

ok() { echo "  [OK]   $*"; PASS=$((PASS + 1)); }
warn() { echo "  [WARN] $*"; WARN=$((WARN + 1)); }
fail() { echo "  [FAIL] $*"; FAIL=$((FAIL + 1)); }

section() {
  echo
  echo "== $* =="
}

section "USB / Quectel"
if lsusb 2>/dev/null | grep -qiE '2c7c|quectel'; then
  ok "Quectel USB device present"
  lsusb | grep -iE '2c7c|quectel' | sed 's/^/         /'
else
  fail "No Quectel device on USB (expected VID 2c7c)"
fi

section "ModemManager"
if systemctl is-active ModemManager >/dev/null 2>&1; then
  ok "ModemManager is active"
else
  fail "ModemManager is not running"
fi

if command -v mmcli >/dev/null; then
  if mmcli -L 2>/dev/null | grep -qi modem; then
    ok "mmcli lists at least one modem"
    mmcli -L 2>/dev/null | sed 's/^/         /'
  else
    fail "mmcli found no modems"
  fi
else
  warn "mmcli not installed"
fi

section "HiPi daemon"
if systemctl --user is-active hipi-daemon >/dev/null 2>&1; then
  ok "hipi-daemon user service is active"
elif pgrep -f 'hipi-daemon' >/dev/null 2>&1; then
  warn "hipi-daemon process running but user service not active"
else
  fail "hipi-daemon not running (try: systemctl --user enable --now hipi-daemon)"
fi

section "HiPi status"
STATUS_FILE="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/hipi-status.json"
if [[ -f "$STATUS_FILE" ]]; then
  ok "Status file exists: $STATUS_FILE"
  if python3 -c "
import json, sys
d=json.load(open('$STATUS_FILE'))
sys.exit(0 if d.get('modem_present') else 1)
" 2>/dev/null; then
    ok "modem_present=true in status file"
    python3 -c "
import json
d=json.load(open('$STATUS_FILE'))
m=d.get('modem',{})
print('         operator:', m.get('operator_name') or m.get('operator_code') or '?')
print('         signal:', m.get('signal_quality', '?'), '%')
print('         unread:', d.get('unread_sms', 0))
"
  else
    fail "modem_present=false — check SIM, USB, ModemManager"
    python3 -c "
import json
d=json.load(open('$STATUS_FILE'))
print('         hint:', d.get('modem_hint', 'n/a'))
" 2>/dev/null || true
  fi
elif command -v hipi >/dev/null; then
  warn "Status file missing; trying hipi status"
  hipi status 2>/dev/null | head -20 | sed 's/^/         /' || fail "hipi status failed"
else
  warn "hipi CLI not in PATH and no status file"
fi

section "Audio (voice)"
if [[ -f /proc/asound/cards ]] && grep -qi quectel /proc/asound/cards; then
  ok "ALSA card mentions Quectel"
  grep -i quectel /proc/asound/cards | sed 's/^/         /'
else
  warn "No Quectel ALSA card — voice may need quectel-voice-setup.sh"
fi

section "System policy (D-Bus / Polkit)"
if [[ -f /etc/dbus-1/system.d/hipi-modemmanager.conf ]]; then
  ok "D-Bus policy installed"
else
  warn "Missing /etc/dbus-1/system.d/hipi-modemmanager.conf — run: sudo ./scripts/install-system-policy.sh"
fi
if [[ -f /etc/polkit-1/rules.d/50-hipi-modemmanager.rules ]]; then
  ok "Polkit rules installed"
else
  warn "Missing Polkit rules — run: sudo ./scripts/install-system-policy.sh"
fi

section "User groups"
if groups | grep -qw dialout && groups | grep -qw plugdev; then
  ok "User in dialout and plugdev"
else
  warn "User missing dialout/plugdev — re-login after: sudo usermod -aG dialout,plugdev \$USER"
fi

section "Manual checklist"
cat <<'EOF'
  Complete these in HiPi UI (see docs/device-checklist.md):
  - Send/receive Chinese SMS
  - Outbound and inbound voice call with audio
  - Contact name display and optional webhook forward
EOF

if $SMOKE; then
  section "Smoke tests (optional)"
  if ! command -v hipi >/dev/null; then
    fail "hipi CLI not found for smoke tests"
  elif [[ -z "${HIPI_SMOKE_NUMBER:-}" ]]; then
    warn "Set HIPI_SMOKE_NUMBER to run SMS smoke test"
  else
    if hipi send-sms "$HIPI_SMOKE_NUMBER" "HiPi smoke $(date +%H:%M:%S)" 2>/dev/null | grep -q '"ok": true'; then
      ok "hipi send-sms succeeded"
    else
      fail "hipi send-sms failed (see journalctl --user -u hipi-daemon)"
    fi
    if hipi status 2>/dev/null | grep -q '"modem_present": true'; then
      ok "hipi status reports modem_present"
    else
      fail "hipi status missing modem"
    fi
  fi
fi

if $HARDWARE_TESTS; then
  section "Pytest hardware markers"
  if command -v pytest >/dev/null; then
    if pytest -q -m hardware tests/test_hardware.py; then
      ok "hardware pytest passed"
    else
      fail "hardware pytest failed (daemon/modem required)"
    fi
  else
    warn "pytest not installed; skip hardware tests"
  fi
fi

section "Summary"
echo "  Passed: $PASS  Warnings: $WARN  Failed: $FAIL"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
