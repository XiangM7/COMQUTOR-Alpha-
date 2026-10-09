#!/usr/bin/env bash
# Round 8 (2026-10-06) -- ISOLATED-DATABASE-ONLY launcher for the AMD
# automated-eligibility re-evaluation script. Modeled directly on
# run_nvda_fresh_run_isolated_db.sh's own proven guard: forces
# COMQUTOR_DATABASE_URL to COMQUTOR_TEST_DATABASE_URL's value for THIS
# process only (.env on disk is never modified), refuses to proceed unless
# the resolved database name ends in "_test", and sets the independent
# COMQUTOR_REQUIRE_DATABASE_NAME guard the running process itself also
# checks at its actual DB-connection point
# (comqutor_alpha.storage.db.engine.enforce_required_database_name).
#
# Usage:
#   bash docs/audit_artifacts/round_source_linking_t0_t2/round8_automated_eligibility_20261006/00_run_isolated_db.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
cd "$REPO_ROOT"

fail() {
  echo "ROUND8_ISOLATED_DB_CHECK_FAILED: $1" >&2
  exit 1
}

[[ -f "$REPO_ROOT/.env" ]] || fail "Missing .env -- cannot read COMQUTOR_TEST_DATABASE_URL."
set -a
# shellcheck disable=SC1091
source "$REPO_ROOT/.env"
set +a

[[ -n "${COMQUTOR_TEST_DATABASE_URL:-}" ]] || fail "COMQUTOR_TEST_DATABASE_URL is not set in .env."

export COMQUTOR_DATABASE_URL="$COMQUTOR_TEST_DATABASE_URL"

db_name="${COMQUTOR_DATABASE_URL##*/}"
db_name="${db_name%%\?*}"
[[ -n "$db_name" ]] || fail "Could not parse a database name out of COMQUTOR_DATABASE_URL."
case "$db_name" in
  *_test) ;;
  *) fail "COMQUTOR_DATABASE_URL resolves to database '$db_name', which does not end in _test -- refusing." ;;
esac

export COMQUTOR_REQUIRE_DATABASE_NAME="$db_name"

echo "Round 8 isolated-DB check passed: COMQUTOR_DATABASE_URL -> database '$db_name'."
exec .venv/bin/python3 "$SCRIPT_DIR/01_amd_automated_eligibility_reevaluation.py"
