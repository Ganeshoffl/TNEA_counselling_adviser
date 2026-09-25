#!/usr/bin/env bash
# Asserts the Python and JavaScript engines produce identical recommendations.
#
# The engine exists twice: Python backs the documented API, JavaScript lets the app
# run with no server on static hosting. This check is what stops the two drifting.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
PROFILES="$ROOT/scripts/parity_profiles.json"

if [[ ! -f "$ROOT/frontend/public/data/colleges.json" ]]; then
  echo "  SKIP  static bundle missing (run: python scripts/build_static_bundle.py)"
  exit 0
fi

if ! command -v node >/dev/null 2>&1; then
  echo "  SKIP  node not available"
  exit 0
fi

"$PY" "$ROOT/scripts/parity_py.py" "$PROFILES" > /tmp/parity-py.json || {
  echo "  FAIL  python engine run failed"; exit 1; }

node "$ROOT/scripts/parity_js.mjs" "$PROFILES" > /tmp/parity-js.json || {
  echo "  FAIL  javascript engine run failed"; exit 1; }

"$PY" "$ROOT/scripts/parity_diff.py" /tmp/parity-py.json /tmp/parity-js.json
