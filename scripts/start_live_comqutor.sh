#!/usr/bin/env bash
# The ONE permanent launcher for live COMQUTOR research (operational safety
# fix). Two fresh live runs (NVDA 40bd7e3d-2759-45bc-97ec-8f1cf96c2266, SNDK
# 52c23371-c374-4064-a91c-20c599ffa79c) were allowed to execute real,
# expensive TradingAgents research while COMQUTOR_WEEK2_LLM_ENABLED was
# false, producing zero committed Alpha matches and zero Activation. This
# script exists so live research is never started again without first
# proving, in this exact process's own environment, that the whole
# semantic pipeline (not just TradingAgents) is actually ready.
#
# Usage:
#   bash scripts/start_live_comqutor.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

fail() {
  echo "COMQUTOR_LIVE_START_FAILED: $1" >&2
  exit 1
}

# --- 1. cd to repository root -----------------------------------------------
cd "$REPO_ROOT"

# --- 2. activate .venv -------------------------------------------------------
[[ -f "$REPO_ROOT/.venv/bin/activate" ]] || fail "Missing .venv. Create the project virtual environment first."
# shellcheck disable=SC1091
source "$REPO_ROOT/.venv/bin/activate"

# --- 3. load .env safely (never let it define the safety-critical vars --
#        those are always forced explicitly in step 4, below, regardless of
#        whatever .env contains) ---------------------------------------------
if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.env"
  set +a
fi

# --- 4. explicitly export the required live-research environment -----------
export COMQUTOR_REAL_TRADINGAGENTS_ENABLED=true
export COMQUTOR_WEEK2_LLM_ENABLED=true
export COMQUTOR_CORS_ORIGINS="http://127.0.0.1:5175"
export COMQUTOR_API_HOST="127.0.0.1"
export COMQUTOR_API_PORT="8000"

# --- 5. default force_refresh to false unless the operator's own shell/.env
#        already set it -- never silently enabled by this launcher ---------
export COMQUTOR_REAL_FORCE_REFRESH_ENABLED="${COMQUTOR_REAL_FORCE_REFRESH_ENABLED:-false}"

# --- 6. refuse to start if the port is already occupied ---------------------
port_in_use() {
  "$REPO_ROOT/.venv/bin/python" -c \
    'import socket, sys
s = socket.socket()
s.settimeout(0.2)
result = s.connect_ex(("127.0.0.1", int(sys.argv[1])))
s.close()
raise SystemExit(0 if result == 0 else 1)' "$1"
}

if port_in_use "$COMQUTOR_API_PORT"; then
  fail "Port $COMQUTOR_API_PORT is already occupied. Stop the existing process first (this launcher never reuses or kills another server)."
fi

# --- 7/8. same-process Python preflight: verify Real TradingAgents, Week2
#          LLM, and the Week2 semantic Provider are all actually ready --
#          reuses comqutor_alpha.server_execution's own readiness functions
#          (the exact same ones the API's /ready and POST /api/research
#          guards use), never a second, independently re-implemented check.
PREFLIGHT_STATUS=0
PREFLIGHT_OUTPUT="$(
  "$REPO_ROOT/.venv/bin/python" -c '
import sys

from comqutor_alpha import server_execution

real_on = server_execution.is_real_tradingagents_enabled()
week2_on = server_execution.is_week2_llm_enabled()
readiness = server_execution.build_live_semantic_readiness()
provider_ready = readiness["ready"] and week2_on

print("REAL=%s" % ("1" if real_on else "0"))
print("WEEK2=%s" % ("1" if week2_on else "0"))
print("PROVIDER=%s" % ("1" if provider_ready else "0"))
print("ERROR=%s" % (readiness["error"] or ""))

sys.exit(0 if (real_on and week2_on and provider_ready) else 1)
'
)" || PREFLIGHT_STATUS=$?

REAL_STATE="$(echo "$PREFLIGHT_OUTPUT" | sed -n 's/^REAL=//p')"
WEEK2_STATE="$(echo "$PREFLIGHT_OUTPUT" | sed -n 's/^WEEK2=//p')"
PROVIDER_STATE="$(echo "$PREFLIGHT_OUTPUT" | sed -n 's/^PROVIDER=//p')"
ERROR_CODE="$(echo "$PREFLIGHT_OUTPUT" | sed -n 's/^ERROR=//p')"

state_label() {
  [[ "$1" == "1" ]] && echo "✅ ON" || echo "❌ OFF"
}
state_label_ready() {
  [[ "$1" == "1" ]] && echo "✅ READY" || echo "❌ NOT READY"
}

echo "========================================"
echo "COMQUTOR LIVE PREFLIGHT"
echo "Real TradingAgents : $(state_label "$REAL_STATE")"
echo "Week2 Semantic LLM : $(state_label "$WEEK2_STATE")"
echo "Semantic Provider  : $(state_label_ready "$PROVIDER_STATE")"
echo "API                : ${COMQUTOR_API_HOST}:${COMQUTOR_API_PORT}"
echo "Frontend CORS      : 127.0.0.1:5175"
echo "========================================"

# --- 10. if ANY required condition fails: exit non-zero, do not start ------
if [[ "$PREFLIGHT_STATUS" -ne 0 ]]; then
  fail "Live semantic pipeline preflight failed${ERROR_CODE:+ ($ERROR_CODE)}. The API was NOT started."
fi

# --- 11. exec comqutor-api so the server process inherits the exact
#         verified environment -- never a detached/sub-shell process that
#         could silently lose an env var before the API actually starts. --
exec comqutor-api
