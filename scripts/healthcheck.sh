#!/usr/bin/env bash
# Machine-runnable smoke check (MVP Audit, Evaluation, Golden Fixtures, and
# Delivery Readiness Sprint, Track D, section 28).
#
# Checks an ALREADY-RUNNING COMQUTOR instance (start one first with
# scripts/demo_offline.sh, or point this at any other API_URL). Exits
# non-zero on the first failed check; prints PASS/FAIL for every check it
# ran so a failure is never silent.
#
# Usage:
#   scripts/healthcheck.sh
#   API_URL=http://127.0.0.1:8001 FRONTEND_URL=http://127.0.0.1:5175 scripts/healthcheck.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
API_URL="${API_URL:-http://127.0.0.1:8001}"
FRONTEND_URL="${FRONTEND_URL:-http://127.0.0.1:5175}"

FAILURES=0

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILURES=$((FAILURES + 1)); }

http_status() {
  local code
  code="$(curl --silent --max-time 5 --output /dev/null --write-out '%{http_code}' "$1" 2>/dev/null)"
  if [[ -z "$code" || "$code" == "000" ]]; then
    echo "000"
  else
    echo "$code"
  fi
}

echo "COMQUTOR healthcheck -- API_URL=$API_URL FRONTEND_URL=$FRONTEND_URL"
echo "---"

# 1. Backend health
status="$(http_status "$API_URL/health")"
if [[ "$status" == "200" ]]; then
  pass "backend health ($API_URL/health -> 200)"
else
  fail "backend health ($API_URL/health -> $status, expected 200)"
fi

# 2. Database connectivity (the /ready route only returns 200 once the DB
# migration/connection has actually succeeded -- see
# comqutor_alpha/api/routes_system.py).
status="$(http_status "$API_URL/ready")"
if [[ "$status" == "200" ]]; then
  pass "database connectivity (/ready -> 200)"
else
  fail "database connectivity (/ready -> $status, expected 200)"
fi

# 3 & 4. Fixture presence + run API readable
run_list_json="$(curl --silent --max-time 5 "$API_URL/api/research" 2>/dev/null || echo "")"
first_run_id="$(printf '%s' "$run_list_json" | "$REPO_ROOT/.venv/bin/python" -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    print("")
    raise SystemExit(0)
items = data.get("items") if isinstance(data, dict) else None
if isinstance(items, list) and items and isinstance(items[0], dict):
    print(items[0].get("run_id") or "")
else:
    print("")
' 2>/dev/null)"

if [[ -n "$first_run_id" ]]; then
  pass "fixture presence (/api/research lists at least one run: $first_run_id)"
else
  fail "fixture presence (/api/research returned no runs -- seed a demo fixture first, e.g. scripts/seed_w5_demo.py)"
fi

if [[ -n "$first_run_id" ]]; then
  status="$(http_status "$API_URL/api/research/$first_run_id")"
  if [[ "$status" == "200" ]]; then
    pass "run API readable (/api/research/$first_run_id -> 200)"
  else
    fail "run API readable (/api/research/$first_run_id -> $status, expected 200)"
  fi

  # 5. Graph API readable
  status="$(http_status "$API_URL/api/research/$first_run_id/graph")"
  if [[ "$status" == "200" ]]; then
    pass "graph API readable (/api/research/$first_run_id/graph -> 200)"
  else
    fail "graph API readable (/api/research/$first_run_id/graph -> $status, expected 200)"
  fi

  # 6. Conflict API readable
  status="$(http_status "$API_URL/api/research/$first_run_id/conflicts")"
  if [[ "$status" == "200" ]]; then
    pass "conflict API readable (/api/research/$first_run_id/conflicts -> 200)"
  else
    fail "conflict API readable (/api/research/$first_run_id/conflicts -> $status, expected 200)"
  fi
else
  fail "run/graph/conflict API readable (skipped -- no run_id available)"
fi

# 7. Frontend build exists
if [[ -f "$REPO_ROOT/frontend/dist/index.html" ]]; then
  pass "frontend build exists (frontend/dist/index.html present)"
else
  fail "frontend build exists (frontend/dist/index.html missing -- run: cd frontend && npm run build)"
fi

# 7b. Frontend dev/preview server reachable (best-effort, not required if
# only the built artifact is being checked -- e.g. in CI with no server
# running).
status="$(http_status "$FRONTEND_URL/research")"
if [[ "$status" == "200" ]]; then
  pass "frontend server reachable ($FRONTEND_URL/research -> 200)"
else
  echo "INFO: frontend server not reachable at $FRONTEND_URL/research (status=$status) -- not counted as a failure unless you expected a server to be running"
fi

# 8. No Provider call in offline demo -- structurally guaranteed by
# demo_offline.sh's own environment (COMQUTOR_REAL_TRADINGAGENTS_ENABLED=
# false, COMQUTOR_WEEK2_LLM_ENABLED=false), not independently re-verifiable
# over HTTP from here. Reported explicitly rather than faked as a check.
echo "INFO: Provider-call-free execution is enforced by scripts/demo_offline.sh's environment variables (COMQUTOR_REAL_TRADINGAGENTS_ENABLED=false, COMQUTOR_WEEK2_LLM_ENABLED=false), not re-verified by this script."

echo "---"
if [[ "$FAILURES" -eq 0 ]]; then
  echo "HEALTHCHECK_OK"
  exit 0
else
  echo "HEALTHCHECK_FAILED: $FAILURES check(s) failed"
  exit 1
fi
