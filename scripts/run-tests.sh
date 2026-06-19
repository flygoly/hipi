#!/usr/bin/env bash
# Run HiPi unit tests locally (works without pytest installed).
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=.

if command -v pytest >/dev/null 2>&1; then
  exec pytest -q -m "not hardware" "$@"
fi

python3 <<'PY'
import importlib
import pkgutil
import sys

SKIP_WITHOUT_PYTEST = {"test_hardware", "test_rpc"}

failed: list[str] = []
skipped = 0
count = 0
for modinfo in pkgutil.iter_modules(["tests"]):
    if not modinfo.name.startswith("test_"):
        continue
    if modinfo.name in SKIP_WITHOUT_PYTEST:
        try:
            import pytest  # noqa: F401
        except ImportError:
            skipped += 1
            continue
    try:
        mod = importlib.import_module(f"tests.{modinfo.name}")
    except ModuleNotFoundError as exc:
        failed.append(f"tests.{modinfo.name}: import failed: {exc}")
        continue
    for name in sorted(dir(mod)):
        if not name.startswith("test_"):
            continue
        count += 1
        try:
            getattr(mod, name)()
        except Exception as exc:
            failed.append(f"tests.{modinfo.name}.{name}: {exc}")

if failed:
    print("FAILED:", file=sys.stderr)
    for line in failed:
        print(line, file=sys.stderr)
    sys.exit(1)
print(f"OK ({count} tests, skipped {skipped} pytest-only modules)")
PY
