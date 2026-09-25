#!/usr/bin/env bash
# Boots the API (which also serves the built frontend), drives the UI in a
# headless browser to capture screenshots, then shuts the server down.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
export API_PORT="${API_PORT:-8000}"
LOG=/tmp/tnea-capture.log

cd "$ROOT/backend"
"$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT" >"$LOG" 2>&1 &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null' EXIT

for _ in $(seq 1 40); do
  if curl -sf --max-time 3 "http://127.0.0.1:${API_PORT}/api/health" >/dev/null 2>&1; then break; fi
  sleep 0.5
done

if ! curl -sf --max-time 5 "http://127.0.0.1:${API_PORT}/api/health" >/dev/null 2>&1; then
  echo "API failed to start:"
  tail -25 "$LOG"
  exit 1
fi
echo "API up"

cd "$ROOT/frontend"
node "$ROOT/frontend/screenshot.mjs"
status=$?

echo
ls -la "$ROOT/screenshots" 2>/dev/null
exit $status
