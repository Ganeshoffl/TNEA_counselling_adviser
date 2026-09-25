#!/usr/bin/env bash
# Start the TNEA advisor API for local development.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

PY="${PYTHON:-$ROOT/.venv/bin/python}"
LOG="${API_LOG:-/tmp/tnea-api.log}"

exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "${API_PORT:-8000}" >"$LOG" 2>&1
