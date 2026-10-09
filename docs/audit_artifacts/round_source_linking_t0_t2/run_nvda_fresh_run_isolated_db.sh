#!/usr/bin/env bash
# T4 single NVDA Fresh Run -- ISOLATED-DATABASE-ONLY launcher (2026-09-30).
#
# scripts/start_live_comqutor.sh (the one permanent live-research launcher)
# uses whatever COMQUTOR_DATABASE_URL the sourced .env already defines --
# which, in THIS repository's own .env, points at db name "comqutor_alpha"
# (the main/default database), not "comqutor_alpha_test" (the confirmed
# isolated instance every other real-PostgreSQL verification in this round
# uses). Starting a Fresh Run through start_live_comqutor.sh directly would
# therefore silently write to the main database by default.
#
# This wrapper exists so that never happens by accident: it explicitly
# overrides COMQUTOR_DATABASE_URL to COMQUTOR_TEST_DATABASE_URL's own value
# for this process only (the same "force the safety-critical var explicitly
# in this exact process's environment" pattern start_live_comqutor.sh
# already uses for COMQUTOR_REAL_TRADINGAGENTS_ENABLED/COMQUTOR_WEEK2_LLM_ENABLED),
# checks the result, and REFUSES TO START if the target still isn't the
# isolated instance -- never asks whether to proceed against the main
# database instead; it just stops.
#
# Usage:
#   bash docs/audit_artifacts/round_source_linking_t0_t2/run_nvda_fresh_run_isolated_db.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$REPO_ROOT"

fail() {
  echo "T4_ISOLATED_DB_CHECK_FAILED: $1" >&2
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

# Extract the database name (the path component after the last '/') and
# require it to literally end in "_test" -- the one, simple, checkable fact
# that actually distinguishes this repository's isolated instance from its
# main one. Refuses rather than guesses if the URL doesn't parse as expected.
db_name="${COMQUTOR_DATABASE_URL##*/}"
db_name="${db_name%%\?*}"
[[ -n "$db_name" ]] || fail "Could not parse a database name out of COMQUTOR_DATABASE_URL."
case "$db_name" in
  *_test) ;;
  *) fail "COMQUTOR_DATABASE_URL resolves to database '$db_name', which does not end in _test -- refusing to start against what looks like the main database. This script never proceeds against a non-isolated target and never asks whether to override this check." ;;
esac

# 2026-10-02 incident fix: COMQUTOR_DATABASE_URL alone is not enough -- it
# was silently clobbered back to .env's own production value by
# start_live_comqutor.sh's own ".env" re-source one handoff later (see that
# script's step 3, and comqutor_alpha.storage.db.engine.
# enforce_required_database_name's docstring for the full incident writeup).
# COMQUTOR_REQUIRE_DATABASE_NAME is a second, independent variable -- .env
# never defines it, so re-sourcing .env cannot clobber it -- checked again at
# the actual write-connection construction point inside the running process,
# regardless of what COMQUTOR_DATABASE_URL ends up as by then.
export COMQUTOR_REQUIRE_DATABASE_NAME="$db_name"

echo "T4 isolated-DB check passed: COMQUTOR_DATABASE_URL -> database '$db_name'."
echo "Handing off to scripts/start_live_comqutor.sh with this database forced..."
exec bash "$REPO_ROOT/scripts/start_live_comqutor.sh"
