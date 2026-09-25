#!/usr/bin/env bash
# Boots the app, proves the UI and API respond, prints a live recommendation,
# then shuts down. Useful as a smoke demo without leaving anything running.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
PORT="${API_PORT:-8000}"
BASE="http://127.0.0.1:${PORT}"

cd "$ROOT/backend"
"$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" >/tmp/tnea-demo.log 2>&1 &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null' EXIT

for _ in $(seq 1 40); do
  curl -sf --max-time 3 "$BASE/api/health" >/dev/null 2>&1 && break
  sleep 0.5
done
if ! curl -sf --max-time 5 "$BASE/api/health" >/dev/null 2>&1; then
  echo "server failed to start:"; tail -20 /tmp/tnea-demo.log; exit 1
fi

echo "=== HEALTH ==="
curl -s --max-time 10 "$BASE/api/health"; echo

echo "=== UI SERVED AT / ==="
curl -s --max-time 10 "$BASE/" | grep -o '<title>.*</title>'

echo "=== LIVE RECOMMENDATION (cutoff 175, rank 60000, SC, round 3) ==="
curl -s --max-time 90 -X POST "$BASE/api/recommend" \
  -H 'Content-Type: application/json' \
  -d '{"cutoff_mark":175,"rank":60000,"community":"SC","current_round":3,
       "current_college_code":1419,"current_branch_code":"EC","limit":2}' \
  -o /tmp/tnea-live.json -w "  http=%{http_code} bytes=%{size_download} time=%{time_total}s
"

"$PY" - <<'PY'
import json
r = json.load(open('/tmp/tnea-live.json'))
cur = r['current_allotment']
print(f"  current seat: {cur['college_name']}  quality={cur['quality']['quality_score']}")
for mode in ('safe', 'optimal', 'risk'):
    v = r['modes'][mode]['verdict']
    print(f"  {mode.upper():<8} {v['action']:<18} {v['headline']}")
    for o in r['modes'][mode]['options'][:1]:
        print(f"           -> {o['college_name'][:38]:<38} {o['branch_code']}  "
              f"q={o['quality']['quality_score']}  p={o['admission']['probability']:.0%}  "
              f"grade={o['data_confidence']}")
PY

echo "=== server stopped ==="
