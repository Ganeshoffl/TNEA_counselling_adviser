#!/usr/bin/env bash
# Proves the app works with NO backend at all: builds the static site, serves the
# built files with a plain static file server, and drives it in a headless browser.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
PORT="${STATIC_PORT:-8099}"
export API_PORT="$PORT"   # screenshot.mjs reads this to build the base URL

cd "$ROOT/frontend"
npm run build >/tmp/tnea-static-build.log 2>&1 || { echo "build failed:"; tail -20 /tmp/tnea-static-build.log; exit 1; }
echo "built static site"

cd "$ROOT/frontend/dist"
"$PY" -m http.server "$PORT" --bind 127.0.0.1 >/tmp/tnea-static-serve.log 2>&1 &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null' EXIT

for _ in $(seq 1 40); do
  curl -sf --max-time 3 "http://127.0.0.1:${PORT}/" >/dev/null 2>&1 && break
  sleep 0.5
done
if ! curl -sf --max-time 5 "http://127.0.0.1:${PORT}/" >/dev/null 2>&1; then
  echo "static server failed to start"; tail -10 /tmp/tnea-static-serve.log; exit 1
fi
echo "serving static build on 127.0.0.1:${PORT} (no API process running)"

# Confirm no backend is listening, so this genuinely proves the static path works.
if curl -sf --max-time 2 "http://127.0.0.1:8000/api/health" >/dev/null 2>&1; then
  echo "WARNING: an API is running on 8000; the static proof is less meaningful"
fi

cd "$ROOT/frontend"
SHOT_DIR="${SHOT_DIR:-$ROOT/screenshots/static}" node "$ROOT/frontend/screenshot.mjs"
status=$?

echo
ls -la "${SHOT_DIR:-$ROOT/screenshots/static}" 2>/dev/null
exit $status
