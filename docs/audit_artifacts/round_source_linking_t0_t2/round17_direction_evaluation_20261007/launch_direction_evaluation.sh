#!/usr/bin/env bash
# Real direction (evidence_stance_classifier) run for the recovered AMD classification (round 17, 2026-10-07).
#
#   export COMQUTOR_DIRECTION_REAL_EXECUTION_ACK=<the value printed by --dry-run for the current plan>
#   bash docs/audit_artifacts/round_source_linking_t0_t2/round17_direction_evaluation_20261007/launch_direction_evaluation.sh
#
# Resume (same execution id; requests already audited count against the same cap of 17; failed / unknown batches are
# never re-sent):
#   EXECUTION_ID=direction-... DIRECTION_MAX_CALLS=<17 minus requests already audited> bash .../launch_direction_evaluation.sh
#
# Same isolated-database pattern as the earlier launchers. Everything the plan freezes is exported EXPLICITLY (load_dotenv
# never overrides an exported value, and the repo .env carries MAX_RETRIES=1, which would give the stance task a retry).
# The Python entry point re-checks all of it against what THIS shell exported and refuses otherwise; it also refuses
# without the acknowledgement, which this script never sets.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
cd "$REPO_ROOT"
fail() { echo "DIRECTION_LAUNCH_CHECK_FAILED: $1" >&2; exit 1; }

[[ -n "${COMQUTOR_DIRECTION_REAL_EXECUTION_ACK:-}" ]] || fail "COMQUTOR_DIRECTION_REAL_EXECUTION_ACK is not exported in this shell (operator authorization)."
[[ -f "$REPO_ROOT/.env" ]] || fail "Missing .env -- cannot read COMQUTOR_TEST_DATABASE_URL / DEEPSEEK_API_KEY."
set -a
# shellcheck disable=SC1091
source "$REPO_ROOT/.env"
set +a
[[ -n "${COMQUTOR_TEST_DATABASE_URL:-}" ]] || fail "COMQUTOR_TEST_DATABASE_URL is not set in .env."
[[ -n "${DEEPSEEK_API_KEY:-}" ]] || fail "DEEPSEEK_API_KEY is not set in .env."

export COMQUTOR_DATABASE_URL="$COMQUTOR_TEST_DATABASE_URL"
db_name="${COMQUTOR_DATABASE_URL##*/}"; db_name="${db_name%%\?*}"
[[ -n "$db_name" ]] || fail "Could not parse a database name out of COMQUTOR_DATABASE_URL."
case "$db_name" in *_test) ;; *) fail "database '$db_name' does not end in _test -- refusing." ;; esac
export COMQUTOR_REQUIRE_DATABASE_NAME="$db_name"

# --- The frozen direction configuration (see the dry-run report) ------------------------------------------------------
export COMQUTOR_WEEK2_LLM_ENABLED=1
export COMQUTOR_WEEK2_LLM_PROVIDER=deepseek
export COMQUTOR_WEEK2_LLM_MODEL=deepseek-v4-flash
export COMQUTOR_WEEK2_LLM_MAX_RETRIES=0          # also gives evidence_stance_classifier 0 retries (an explicit 0 is respected)
export COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS=45     # the existing production timeout (shared by every Week2 task), explicit and verified on the wire
export COMQUTOR_WEEK2_STANCE_CONCURRENCY=4
# Request-shape / other-task variables that must not leak in from an earlier launch in this shell (the Python entry
# point refuses if any is present): no max-tokens override, no endpoint override, and not the content-verification
# experiment's token setting.
unset COMQUTOR_WEEK2_ALPHA_CLASSIFIER_MAX_TOKENS COMQUTOR_WEEK2_CONTENT_SUPPORT_MAX_TOKENS COMQUTOR_WEEK2_LLM_BASE_URL
export COMQUTOR_WEEK2_LLM_MAX_CALLS="${DIRECTION_MAX_CALLS:-17}"

echo "Direction launch check passed: database '$db_name', model $COMQUTOR_WEEK2_LLM_MODEL, retries $COMQUTOR_WEEK2_LLM_MAX_RETRIES, timeout ${COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS}s, stance concurrency $COMQUTOR_WEEK2_STANCE_CONCURRENCY, call cap $COMQUTOR_WEEK2_LLM_MAX_CALLS."
args=(--execute)
if [[ -n "${EXECUTION_ID:-}" ]]; then args+=(--execution-id "$EXECUTION_ID"); fi
exec "$REPO_ROOT/.venv/bin/python" "$SCRIPT_DIR/run_direction_evaluation.py" "${args[@]}"
