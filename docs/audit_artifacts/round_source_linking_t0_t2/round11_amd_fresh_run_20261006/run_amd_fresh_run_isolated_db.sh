#!/usr/bin/env bash
# AMD Fresh Run (Round 11, 2026-10-06) -- ISOLATED-DATABASE-ONLY launcher.
#
# Same pattern as docs/audit_artifacts/round_source_linking_t0_t2/
# run_nvda_fresh_run_isolated_db.sh (force COMQUTOR_DATABASE_URL to the
# isolated _test database, refuse to start otherwise), plus this run's own
# explicit, bounded real-call budgets for both layers:
#   - Research Agent (TradingAgents) layer: <=150 real requests, 0 retries
#     at both the forced client level and this wrapper's own retry loop
#     (comqutor_alpha.runners.request_budget.RequestBudgetGuard, wired via
#     comqutor_alpha.research_lifecycle's real COMQUTOR_RESEARCH_AGENT_MAX_*
#     env var reads).
#   - Week2 semantic layer (all tasks, shared): <=1500 real requests, 0
#     retries, content-support verification specifically forced to
#     batch_size=1 / max_tokens=16384 (see comqutor_alpha/structure_engine/
#     week2_llm.py's COMQUTOR_WEEK2_CONTENT_SUPPORT_* overrides and
#     structured_output_adapter.py's COMQUTOR_WEEK2_CONTENT_SUPPORT_BATCH_SIZE
#     override, both added this round), with the real request/response audit
#     sink mounted (COMQUTOR_WEEK2_LLM_ENABLE_REQUEST_AUDIT).
#
# These budgets are hard stop conditions, not a dollar-cost guarantee, and
# are never auto-extended or auto-retried on exhaustion -- see this run's own
# 00_code_snapshot_identity.md for the full preflight evidence trail.
#
# Usage:
#   bash docs/audit_artifacts/round_source_linking_t0_t2/round11_amd_fresh_run_20261006/run_amd_fresh_run_isolated_db.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
cd "$REPO_ROOT"

fail() {
  echo "AMD_FRESH_RUN_ISOLATED_DB_CHECK_FAILED: $1" >&2
  exit 1
}

[[ -f "$REPO_ROOT/.env" ]] || fail "Missing .env -- cannot read COMQUTOR_TEST_DATABASE_URL."
set -a
# shellcheck disable=SC1091
source "$REPO_ROOT/.env"
set +a

[[ -n "${COMQUTOR_TEST_DATABASE_URL:-}" ]] || fail "COMQUTOR_TEST_DATABASE_URL is not set in .env."

# Force the target for THIS process only -- .env on disk is never modified.
export COMQUTOR_DATABASE_URL="$COMQUTOR_TEST_DATABASE_URL"

db_name="${COMQUTOR_DATABASE_URL##*/}"
db_name="${db_name%%\?*}"
[[ -n "$db_name" ]] || fail "Could not parse a database name out of COMQUTOR_DATABASE_URL."
case "$db_name" in
  *_test) ;;
  *) fail "COMQUTOR_DATABASE_URL resolves to database '$db_name', which does not end in _test -- refusing to start against what looks like the main database." ;;
esac
export COMQUTOR_REQUIRE_DATABASE_NAME="$db_name"

# --- This run's own explicit, bounded real-call budgets ---------------------
# Research Agent (TradingAgents) layer.
export COMQUTOR_RESEARCH_AGENT_MAX_ACTUAL_REQUESTS=150
export COMQUTOR_RESEARCH_AGENT_MAX_RETRIES=0

# Week2 semantic layer (shared across all Week2 tasks).
export COMQUTOR_WEEK2_LLM_MAX_CALLS=1500
export COMQUTOR_WEEK2_LLM_MAX_RETRIES=0
export COMQUTOR_WEEK2_CONTENT_SUPPORT_BATCH_SIZE=1
export COMQUTOR_WEEK2_CONTENT_SUPPORT_MAX_TOKENS=16384
export COMQUTOR_WEEK2_LLM_ENABLE_REQUEST_AUDIT=1

echo "AMD Fresh Run isolated-DB check passed: COMQUTOR_DATABASE_URL -> database '$db_name'."
echo "Research Agent budget: <=${COMQUTOR_RESEARCH_AGENT_MAX_ACTUAL_REQUESTS} requests, ${COMQUTOR_RESEARCH_AGENT_MAX_RETRIES} retries."
echo "Week2 budget: <=${COMQUTOR_WEEK2_LLM_MAX_CALLS} requests, ${COMQUTOR_WEEK2_LLM_MAX_RETRIES} retries; content-support batch_size=${COMQUTOR_WEEK2_CONTENT_SUPPORT_BATCH_SIZE}, max_tokens=${COMQUTOR_WEEK2_CONTENT_SUPPORT_MAX_TOKENS}."
echo "Handing off to scripts/start_live_comqutor.sh with this environment forced..."
exec bash "$REPO_ROOT/scripts/start_live_comqutor.sh"
