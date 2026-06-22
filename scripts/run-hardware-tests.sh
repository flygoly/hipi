#!/usr/bin/env bash
# Run hardware-marked pytest on device (requires hipi-daemon + modem)
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=.

if ! command -v pytest >/dev/null; then
  echo "pytest not installed; try: pip install -e '.[dev]'" >&2
  exit 1
fi

exec pytest -q -m hardware tests/test_hardware.py "$@"
