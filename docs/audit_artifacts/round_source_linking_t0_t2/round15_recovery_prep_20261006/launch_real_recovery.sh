#!/usr/bin/env bash
# Real AMD Alpha-classification recovery launcher (round 15, 2026-10-06).
#
# NOT RUN by the round that wrote it. Starting it is the operator's explicit act:
#
#   export COMQUTOR_RECOVERY_REAL_EXECUTION_ACK=<the value printed by --dry-run for the current plan>
#   bash docs/audit_artifacts/round_source_linking_t0_t2/round15_recovery_prep_20261006/launch_real_recovery.sh
#
# Resume a stopped run (same execution id; failed / unknown claims are never re-sent, and requests already
# audited count against the same 973 cap):
#
#   EXECUTION_ID=recovery-... RECOVERY_MAX_CALLS=<973 minus requests already audited> bash .../launch_real_recovery.sh
#
# Same isolated-database pattern as the AMD Fresh Run launcher (round 11): the run rows go to the _test database
# the backend serves, never to what looks like the main database. Everything the plan freezes is exported
# EXPLICITLY here, because load_dotenv never overrides an exported value and the repo .env carries
# COMQUTOR_WEEK2_LLM_MAX_RETRIES=1 (which would silently give alpha_classifier a retry) and a 45 s timeout that
# is not a freeze. The Python entry point re-checks all of it against what this shell exported and refuses
# otherwise; it also refuses without the acknowledgement, which this script never sets.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
cd "$REPO_ROOT"

fail() {
  echo "REAL_RECOVERY_LAUNCH_CHECK_FAILED: $1" >&2
  exit 1
}

[[ -n "${COMQUTOR_RECOVERY_REAL_EXECUTION_ACK:-}" ]] || fail "COMQUTOR_RECOVERY_REAL_EXECUTION_ACK is not exported in this shell (operator authorization)."
[[ -f "$REPO_ROOT/.env" ]] || fail "Missing .env -- cannot read COMQUTOR_TEST_DATABASE_URL / DEEPSEEK_API_KEY."

set -a
# shellcheck disable=SC1091
source "$REPO_ROOT/.env"
set +a

[[ -n "${COMQUTOR_TEST_DATABASE_URL:-}" ]] || fail "COMQUTOR_TEST_DATABASE_URL is not set in .env."
[[ -n "${DEEPSEEK_API_KEY:-}" ]] || fail "DEEPSEEK_API_KEY is not set in .env."

export COMQUTOR_DATABASE_URL="$COMQUTOR_TEST_DATABASE_URL"
db_name="${COMQUTOR_DATABASE_URL##*/}"
db_name="${db_name%%\?*}"
[[ -n "$db_name" ]] || fail "Could not parse a database name out of COMQUTOR_DATABASE_URL."
case "$db_name" in
  *_test) ;;
  *) fail "COMQUTOR_DATABASE_URL resolves to database '$db_name', which does not end in _test -- refusing." ;;
esac
export COMQUTOR_REQUIRE_DATABASE_NAME="$db_name"

# --- The frozen recovery configuration (see the dry-run report) -------------
export COMQUTOR_WEEK2_LLM_ENABLED=1
export COMQUTOR_WEEK2_LLM_PROVIDER=deepseek
export COMQUTOR_WEEK2_LLM_MODEL=deepseek-v4-flash
export COMQUTOR_WEEK2_LLM_MAX_RETRIES=0          # application level; the client level is hardcoded 0 by the gateway builder
export COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS=45     # explicit, verified on the wire (x-stainless-read-timeout)
export COMQUTOR_WEEK2_LLM_CONCURRENCY=4
# These two change the request SHAPE / endpoint; the original run sent neither, so a stale value inherited from an
# earlier launch in this shell must not leak in. (The Python entry point refuses if either is present.)
unset COMQUTOR_WEEK2_ALPHA_CLASSIFIER_MAX_TOKENS COMQUTOR_WEEK2_LLM_BASE_URL
export COMQUTOR_WEEK2_LLM_MAX_CALLS="${RECOVERY_MAX_CALLS:-973}"   # independent of the original run's 1500; 973 = the recovery cap
# Request/response audit is mounted by the executor itself (enable_request_response_audit=True); not env-controlled.

echo "Recovery launch check passed: database '$db_name', model $COMQUTOR_WEEK2_LLM_MODEL, retries $COMQUTOR_WEEK2_LLM_MAX_RETRIES, timeout ${COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS}s, concurrency $COMQUTOR_WEEK2_LLM_CONCURRENCY, call cap $COMQUTOR_WEEK2_LLM_MAX_CALLS."

args=(--execute)
if [[ -n "${EXECUTION_ID:-}" ]]; then
  args+=(--execution-id "$EXECUTION_ID")
fi
exec "$REPO_ROOT/.venv/bin/python" \
  "$REPO_ROOT/docs/audit_artifacts/round_source_linking_t0_t2/round12_alpha_classifier_audit_fix_20261006/recover_alpha_classification.py" \
  "${args[@]}"
