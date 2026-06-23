#!/usr/bin/env bash
# Restrict MM to one AT port, freeing the other for hipi's direct serial client.
# Run: sudo ~/Documents/workspace/hipi/scripts/filter-mm-ports.sh
set -euo pipefail

PRIMARY=$(mmcli -m 0 2>/dev/null | grep 'primary port' | awk '{print $NF}' | sed 's/ttyUSB//')

if [[ -z "$PRIMARY" ]]; then
  echo "No modem found. Ensure EC801E is connected." >&2
  exit 1
fi

echo "==> ModemManager currently uses ALL AT ports — restricting to ttyUSB$PRIMARY only"
mkdir -p /etc/ModemManager/conf.d
cat > /etc/ModemManager/conf.d/99-hipi-port-filter.conf <<EOF
[filter]
policy=strict
default=allow

[device id=2c7c:0903]
preferred_port=ttyUSB$PRIMARY
EOF

systemctl restart ModemManager
sleep 4

echo "==> MM ports after filter:"
mmcli -m 0 2>/dev/null | grep -E 'port|Port' || echo "(no modem)"
ls -l /dev/ttyUSB*

echo "==> Port availability:"
for p in /dev/ttyUSB{1,2,3,4}; do
  if [[ -e "$p" ]]; then
    if timeout 1 python3 -c "import os; os.open('$p', os.O_RDWR|os.O_NOCTTY)" 2>/dev/null; then
      echo "  $p: FREE"
    else
      echo "  $p: BUSY"
    fi
  fi
done

echo "==> Restarting hipi-daemon"
rm -f "$HOME/.config/hipi/at_port"
systemctl --user restart hipi-daemon 2>/dev/null || true
sleep 2
/home/flygoly/.local/bin/hipi status 2>/dev/null