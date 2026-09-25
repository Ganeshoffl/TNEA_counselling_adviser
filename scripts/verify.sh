#!/usr/bin/env bash
# End-to-end verification: boots the API, exercises every endpoint, checks the
# engine against the raw official figures, then shuts the server down.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
PORT="${API_PORT:-8000}"
BASE="http://127.0.0.1:${PORT}"
LOG=/tmp/tnea-verify.log

pass=0
fail=0

check() {
  local label="$1" condition="$2"
  if [[ "$condition" == "1" ]]; then
    echo "  PASS  $label"
    pass=$((pass + 1))
  else
    echo "  FAIL  $label"
    fail=$((fail + 1))
  fi
}

cd "$ROOT/backend"
"$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" >"$LOG" 2>&1 &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null' EXIT

for _ in $(seq 1 40); do
  if curl -sf --max-time 3 "$BASE/api/health" >/dev/null 2>&1; then break; fi
  sleep 0.5
done

if ! curl -sf --max-time 5 "$BASE/api/health" >/dev/null 2>&1; then
  echo "Server failed to start. Log:"
  tail -30 "$LOG"
  exit 1
fi

echo "== endpoints =="

HEALTH=$(curl -s --max-time 10 "$BASE/api/health")
check "/api/health reports 422 colleges" \
  "$(echo "$HEALTH" | grep -c '"colleges_loaded":422')"

META=$(curl -s --max-time 10 "$BASE/api/meta")
check "/api/meta admission year is 2026" "$(echo "$META" | grep -c '"admission_year":2026')"
check "/api/meta publishes scoring weights" "$(echo "$META" | grep -c 'placement_median_salary')"
check "/api/meta lists official rounds" "$(echo "$META" | grep -c 'rounds_with_official_data')"

BRANCHES=$(curl -s --max-time 10 "$BASE/api/branches")
check "/api/branches returns branch names" "$(echo "$BRANCHES" | grep -c 'COMPUTER SCIENCE AND ENGINEERING')"

MODES=$(curl -s --max-time 10 "$BASE/api/modes")
check "/api/modes cites Accept and Upward" "$(echo "$MODES" | grep -c 'Accept and Upward')"

COLLEGES=$(curl -s --max-time 20 "$BASE/api/colleges?limit=5")
check "/api/colleges returns ranked colleges" "$(echo "$COLLEGES" | grep -c 'quality_score')"

DETAIL=$(curl -s --max-time 10 "$BASE/api/colleges/2006")
check "/api/colleges/2006 is PSG College of Technology" "$(echo "$DETAIL" | grep -c 'PSG College of Technology')"

MISSING=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/colleges/999999")
check "unknown college code returns 404" "$([[ "$MISSING" == "404" ]] && echo 1 || echo 0)"

echo "== validation =="

BAD_COMMUNITY=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 -X POST "$BASE/api/recommend" \
  -H 'Content-Type: application/json' \
  -d '{"cutoff_mark":190,"rank":100,"community":"XYZ","current_round":2}')
check "invalid community rejected (422)" "$([[ "$BAD_COMMUNITY" == "422" ]] && echo 1 || echo 0)"

BAD_ROUND=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 -X POST "$BASE/api/recommend" \
  -H 'Content-Type: application/json' \
  -d '{"cutoff_mark":190,"rank":100,"community":"OC","current_round":9}')
check "invalid round rejected (422)" "$([[ "$BAD_ROUND" == "422" ]] && echo 1 || echo 0)"

BAD_MARK=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 -X POST "$BASE/api/recommend" \
  -H 'Content-Type: application/json' \
  -d '{"cutoff_mark":250,"rank":100,"community":"OC","current_round":2}')
check "cutoff mark above 200 rejected (422)" "$([[ "$BAD_MARK" == "422" ]] && echo 1 || echo 0)"

echo "== recommendation =="

curl -s --max-time 90 -X POST "$BASE/api/recommend" \
  -H 'Content-Type: application/json' \
  -d '{"cutoff_mark":190.0,"rank":12000,"community":"MBC","current_round":2,"current_college_code":1419,"current_branch_code":"EC","limit":3}' \
  -o /tmp/tnea-rec.json

"$PY" - <<'PYCHECK'
import json, sys

with open('/tmp/tnea-rec.json') as fh:
    r = json.load(fh)

problems = []

for mode in ('safe', 'optimal', 'risk'):
    block = r['modes'][mode]
    if 'verdict' not in block or 'options' not in block:
        problems.append(f'{mode} block malformed')
    for option in block['options']:
        adm = option['admission']
        if not 0.0 <= adm['probability'] <= 1.0:
            problems.append(f"{mode}: probability out of range {adm['probability']}")
        if adm.get('seats_vacant_entering_round') == 0 and adm['probability'] > 0:
            problems.append(f"{mode}: zero vacancy but non-zero probability")
        q = option['quality']
        if q['quality_score'] is None:
            problems.append(f"{mode}: unscorable college appeared in a ranked mode")
        for comp in q['components']:
            if comp['available'] and comp['component'] == 'placement_median_salary':
                if not comp.get('source_url'):
                    problems.append(f"{mode}: placement figure without a source link")

# Safe options must clear the safe threshold, risk options must stay below optimal.
for option in r['modes']['safe']['options']:
    if option['admission']['probability'] < 0.80:
        problems.append('safe option below 0.80')
for option in r['modes']['risk']['options']:
    if option['admission']['probability'] >= 0.45:
        problems.append('risk option at or above 0.45')

# Ordering: safe is ranked by quality descending.
safe_scores = [o['quality']['quality_score'] for o in r['modes']['safe']['options']]
if safe_scores != sorted(safe_scores, reverse=True):
    problems.append('safe options not ordered by quality')

if r['current_allotment']['college_code'] != 1419:
    problems.append('current allotment not echoed back')
if not r['disclaimer']:
    problems.append('missing disclaimer')

print('  PASS  recommendation payload is internally consistent' if not problems else '')
for p in problems:
    print(f'  FAIL  {p}')
sys.exit(1 if problems else 0)
PYCHECK
check "recommendation payload consistent" "$([[ $? == 0 ]] && echo 1 || echo 0)"

echo "== data confidence grades =="

"$PY" - <<'PYGRADE'
import json, sys

colleges = json.load(open('app/data/colleges.json'))
meta = colleges['meta']
problems = []

counts = meta['data_confidence_counts']
legend = meta['data_confidence_legend']

for grade in ('A', 'S', 'B', 'U'):
    if grade not in legend:
        problems.append(f'legend missing grade {grade}')

if counts.get('S', 0) == 0:
    problems.append('no grade S colleges were produced')

for college in colleges['colleges']:
    grade = college['data_confidence']
    placement = college.get('placement')
    infra = college.get('infrastructure')

    if grade == 'A':
        if not placement or placement.get('hosted_by') != 'ministry':
            problems.append(f"{college['college_code']}: grade A without Ministry-hosted placement")
    elif grade == 'S':
        if not placement:
            problems.append(f"{college['college_code']}: grade S without placement data")
        else:
            if placement.get('hosted_by') != 'institution':
                problems.append(f"{college['college_code']}: grade S not marked institution-hosted")
            if not placement.get('provenance_caveat'):
                problems.append(f"{college['college_code']}: grade S placement lacks a provenance caveat")
            if not placement.get('source_url'):
                problems.append(f"{college['college_code']}: grade S placement lacks a source link")
            if placement.get('disclosure_year') not in (2025, 2026):
                problems.append(f"{college['college_code']}: grade S disclosure year not 2025/2026")
        if infra and not infra.get('provenance_caveat'):
            problems.append(f"{college['college_code']}: grade S infrastructure lacks a provenance caveat")
    elif grade in ('B', 'U'):
        if placement:
            problems.append(f"{college['college_code']}: grade {grade} must not carry placement figures")

    if grade in ('A', 'S', 'B') and not college['recommendable']:
        problems.append(f"{college['college_code']}: grade {grade} should be recommendable")
    if grade == 'U' and college['recommendable']:
        problems.append(f"{college['college_code']}: grade U must not be recommendable")

for p in problems[:12]:
    print(f'  FAIL  {p}')
if not problems:
    print(f"  PASS  grades consistent (A={counts.get('A')} S={counts.get('S')} "
          f"B={counts.get('B')} U={counts.get('U')})")
sys.exit(1 if problems else 0)
PYGRADE
check "confidence grades consistent" "$([[ $? == 0 ]] && echo 1 || echo 0)"

"$PY" - <<'PYSELF'
import json, sys, urllib.parse

doc = json.load(open('../data-sources/parsed/self_hosted_sources.json'))
problems = []

for college, meta in doc['sources'].items():
    host = (urllib.parse.urlparse(meta['source_url']).hostname or '').lower()
    if host != meta['source_host']:
        problems.append(f'{college}: recorded host does not match the URL')
    if meta['rankings_year'] not in (2025, 2026):
        problems.append(f"{college}: year {meta['rankings_year']} not accepted")
    if not meta['institute_id'].startswith('IR-E-'):
        problems.append(f"{college}: id {meta['institute_id']} is not an Engineering submission")
    if meta['provenance'] != 'self_hosted_by_institution':
        problems.append(f'{college}: provenance not recorded as self-hosted')
    # No third-party aggregators may have slipped through.
    for banned in ('scribd', 'notopedia', 'amazonaws', 'cloudfront', 'filesusr', 'storyblok', 'ctfassets'):
        if banned in host:
            problems.append(f'{college}: host {host} is a third-party aggregator')

for p in problems[:12]:
    print(f'  FAIL  {p}')
if not problems:
    print(f"  PASS  {len(doc['sources'])} self-hosted sources are institution-owned and correctly typed")
sys.exit(1 if problems else 0)
PYSELF
check "self-hosted sources are institution-owned" "$([[ $? == 0 ]] && echo 1 || echo 0)"

echo "== engine vs raw official data =="

"$PY" - <<'PYRAW'
import json, sys
sys.path.insert(0, '.')
from app.data_store import get_store
from app import probability as prob

store = get_store()
raw = json.load(open('app/data/cutoffs.json'))
target = next(
    rec for rec in raw['records']
    if rec['college_code'] == 2 and rec['branch_code'] == 'AP'
    and rec['community'] == 'MBC' and rec['round'] == 2
)
est = prob.estimate(store, 2, 'AP', 'MBC', 12000, 2)

problems = []
if est['closing_rank'] != target['closing_rank']:
    problems.append('closing rank does not match the official file')
if est['opening_rank'] != target['opening_rank']:
    problems.append('opening rank does not match the official file')
if est['seats_allotted_in_evidence_round'] != target['seats_allotted']:
    problems.append('allotted seat count does not match the official file')

# A candidate far ahead of the closing rank, with seats free, must be near certain.
if est['probability'] < 0.9:
    problems.append('rank far ahead of closing rank did not yield a high probability')

# A candidate far behind must be near zero.
low = prob.estimate(store, 2, 'AP', 'MBC', 400000, 2)
if low['probability'] > 0.05:
    problems.append('rank far behind closing rank did not yield a low probability')

# Zero vacancy must be an absolute stop.
zero = prob.estimate(store, 2, 'AP', 'MBC', 1, 3)
if zero and zero['seats_vacant_entering_round'] == 0 and zero['probability'] != 0.0:
    problems.append('zero vacancy did not force probability to zero')

for p in problems:
    print(f'  FAIL  {p}')
if not problems:
    print('  PASS  engine figures match the official allotment file exactly')
sys.exit(1 if problems else 0)
PYRAW
check "engine matches raw official data" "$([[ $? == 0 ]] && echo 1 || echo 0)"

echo "== frontend =="
if [[ -f "$ROOT/frontend/dist/index.html" ]]; then
  ROOTPAGE=$(curl -s --max-time 10 "$BASE/")
  check "built frontend served from the API origin" \
    "$(echo "$ROOTPAGE" | grep -c 'TNEA Counselling Advisor')"
else
  echo "  SKIP  frontend not built (run: cd frontend && npm run build)"
fi

echo
echo "passed=$pass failed=$fail"
[[ $fail -eq 0 ]] || exit 1
