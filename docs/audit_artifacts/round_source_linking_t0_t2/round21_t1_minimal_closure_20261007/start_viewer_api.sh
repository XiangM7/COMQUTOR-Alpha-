#!/usr/bin/env bash
# Round 21: a READ-ONLY viewer instance of the COMQUTOR API for UI verification.
#   * the isolated *_test database only (refuses anything else), port 8001, CORS for the viewer's own Vite port only;
#   * NO real-execution flag and NO Week2 LLM flag: this process cannot start a paid run even if asked to;
#   * the always-on service on port 8000 and the user's dev server on 5175 are never touched or reused.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "$REPO_ROOT"
set -a
# shellcheck disable=SC1091
source "$REPO_ROOT/.env"
set +a
[[ -n "${COMQUTOR_TEST_DATABASE_URL:-}" ]] || { echo "VIEWER_REFUSED: COMQUTOR_TEST_DATABASE_URL missing" >&2; exit 1; }
export COMQUTOR_DATABASE_URL="$COMQUTOR_TEST_DATABASE_URL"
db_name="${COMQUTOR_DATABASE_URL##*/}"; db_name="${db_name%%\?*}"
case "$db_name" in *_test) ;; *) echo "VIEWER_REFUSED: database '$db_name' does not end in _test" >&2; exit 1 ;; esac
export COMQUTOR_REQUIRE_DATABASE_NAME="$db_name"
unset COMQUTOR_REAL_TRADINGAGENTS_ENABLED COMQUTOR_WEEK2_LLM_ENABLED COMQUTOR_REAL_FORCE_REFRESH_ENABLED
export COMQUTOR_API_HOST=127.0.0.1 COMQUTOR_API_PORT="${VIEWER_API_PORT:-8001}" COMQUTOR_CORS_ORIGINS="http://127.0.0.1:${VIEWER_WEB_PORT:-5176}"
echo "viewer API: db=$db_name port=$COMQUTOR_API_PORT real_execution=off week2_llm=off"
exec "$REPO_ROOT/.venv/bin/comqutor-api"
