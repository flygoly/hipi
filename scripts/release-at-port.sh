#!/usr/bin/env bash
# Install udev rule to release ttyUSB1 (interface 03) from ModemManager.
# After running this, UNPLUG and REPLUG the EC801E USB for the rule to take effect.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/packaging/udev/99-hipi-quectel.rules"
DST="/etc/udev/rules.d/99-hipi-quectel.rules"

cp "$SRC" "$DST"
udevadm control --reload-rules

echo "✓ udev rule installed: $DST"
echo "  This tells ModemManager to ignore ttyUSB1 (interface 03)"
echo ""
echo "  === NOW UNPLUG and REPLUG the EC801E USB cable ==="
echo ""
echo "  Then run:"
echo "    systemctl --user restart hipi-daemon"
echo "    hipi status"
echo ""
echo "  Expected: sms_backend: \"at\"   at_port: \"/dev/ttyUSB1\""