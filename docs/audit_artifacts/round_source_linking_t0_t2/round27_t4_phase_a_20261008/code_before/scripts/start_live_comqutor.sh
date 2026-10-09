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
# 2026-10-02 incident fix: a caller (e.g. the isolated-database launcher,
# docs/audit_artifacts/round_source_linking_t0_t2/
# run_nvda_fresh_run_isolated_db.sh) may already have exported
# COMQUTOR_DATABASE_URL before invoking this script, specifically to
# override whatever .env's own value is. Sourcing .env below with `set -a`
# previously clobbered that override silently the moment .env defined its
# own COMQUTOR_DATABASE_URL -- this is exactly what caused a real NVDA
# research run to write 2111 rows into the production database instead of
# the isolated comqutor_alpha_test one (see docs/audit_artifacts/
# round_source_linking_t0_t2/incident_prod_db_writes_20261002/
# INCIDENT_REPORT_AND_CLEANUP_PLAN.md for the full incident, and
# comqutor_alpha.storage.db.engine.enforce_required_database_name for the
# independent second-layer guard added in the same fix). The caller's own
# explicit choice, captured here before .env is ever sourced, is restored
# immediately after -- it always wins over .env. When no caller override
# exists (the normal case: a developer running this script directly), the
# captured value is empty and .env's own value flows through exactly as
# before -- zero behavior change for that case.
#
# 2026-10-06 generalization (AMD Fresh Run preflight, round 7): the exact
# same clobber risk was reproduced for COMQUTOR_WEEK2_LLM_MAX_RETRIES --
# .env defines it as 1, so a caller exporting 0 (required for this run's
# "zero retries at both layers" budget constraint) was silently overwritten
# back to 1 by the unconditional `source .env` below, before this fix. Every
# var in this list gets the identical capture-before/restore-after
# treatment; .env is still the only source of truth for any var a caller
# does NOT already have exported.
# Plain indexed-array parallel lists, not an associative array -- this
# script's shebang resolves to the stock macOS /bin/bash (3.2.57), which has
# no `declare -A` support; a 3.2-incompatible construct here would crash the
# launcher before it ever reaches the real preflight checks below (caught
# and fixed during this same round's own zero-cost preflight, before any
# real Provider spend).
_CALLER_OVERRIDE_VARS=(COMQUTOR_DATABASE_URL COMQUTOR_WEEK2_LLM_MAX_RETRIES)
_CALLER_OVERRIDE_VALUES=()
for _var in "${_CALLER_OVERRIDE_VARS[@]}"; do
  _CALLER_OVERRIDE_VALUES+=("${!_var:-}")
done
if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.env"
  set +a
fi
for _i in "${!_CALLER_OVERRIDE_VARS[@]}"; do
  _var="${_CALLER_OVERRIDE_VARS[$_i]}"
  _val="${_CALLER_OVERRIDE_VALUES[$_i]}"
  if [[ -n "$_val" ]]; then
    export "$_var=$_val"
  fi
done

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
