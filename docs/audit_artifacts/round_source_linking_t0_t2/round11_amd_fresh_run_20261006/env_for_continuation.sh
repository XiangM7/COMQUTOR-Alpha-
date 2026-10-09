#!/usr/bin/env bash
# Environment setup for the AMD post-processing continuation script
# (run_postprocessing_continuation.py). Source this, then run the Python
# script in the SAME shell. Mirrors run_amd_fresh_run_isolated_db.sh's own
# isolated-DB + budget config, minus the TradingAgents-specific vars (this
# continuation never invokes TradingAgents).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
cd "$REPO_ROOT"

fail() {
  echo "AMD_CONTINUATION_ENV_CHECK_FAILED: $1" >&2
  return 1
}

[[ -f "$REPO_ROOT/.env" ]] || { fail "Missing .env"; return 1 2>/dev/null || exit 1; }
set -a
source "$REPO_ROOT/.env"
set +a

[[ -n "${COMQUTOR_TEST_DATABASE_URL:-}" ]] || { fail "COMQUTOR_TEST_DATABASE_URL not set"; return 1 2>/dev/null || exit 1; }
export COMQUTOR_DATABASE_URL="$COMQUTOR_TEST_DATABASE_URL"
db_name="${COMQUTOR_DATABASE_URL##*/}"
db_name="${db_name%%\?*}"
case "$db_name" in
  *_test) ;;
  *) fail "resolved database '$db_name' does not end in _test"; return 1 2>/dev/null || exit 1 ;;
esac
export COMQUTOR_REQUIRE_DATABASE_NAME="$db_name"

export COMQUTOR_REAL_TRADINGAGENTS_ENABLED=true
export COMQUTOR_WEEK2_LLM_ENABLED=true
export COMQUTOR_WEEK2_LLM_MAX_RETRIES=0
export COMQUTOR_WEEK2_CONTENT_SUPPORT_BATCH_SIZE=1
export COMQUTOR_WEEK2_CONTENT_SUPPORT_MAX_TOKENS=16384
export COMQUTOR_WEEK2_LLM_ENABLE_REQUEST_AUDIT=1
# COMQUTOR_WEEK2_LLM_MAX_CALLS is set by the Python script itself (remaining
# budget, not the full 1500) -- never set here, to avoid a stale value.

echo "Continuation environment ready: database -> $db_name"
