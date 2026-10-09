#!/usr/bin/env bash
# T4 round 32: an isolated, READ-ONLY API instance on the FINAL code (real execution OFF, Week 2 LLM OFF, outbound HTTP(S)
# proxied to a dead loopback port -- it can serve saved runs but cannot reach a provider or a data source).
#
#   bash start_r32_instance.sh verify   # comqutor_alpha_t4_r32_verify_test + outputs/t4_r32_verify_runs, port 8004, web origin 5178
#   bash start_r32_instance.sh demo     # comqutor_alpha_t4_r32_demo_test (restored copy of comqutor_alpha_t4_test)
#                                       # + outputs/t4_r32_demo_runs (copy of outputs/t4_runs), port 8005, web origin 5179
#
# Refuses to start unless the URL is PostgreSQL and names that database (checked again inside the server process by
# COMQUTOR_REQUIRE_DATABASE_DIALECT / COMQUTOR_REQUIRE_DATABASE_NAME). Never the 8000/8002 services or their databases.
set -euo pipefail
MODE="${1:-}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../../../.." && pwd)"
cd "$REPO_ROOT"
fail() { echo "R32_INSTANCE_REFUSED: $1" >&2; exit 1; }
case "$MODE" in
  verify) DB=comqutor_alpha_t4_r32_verify_test; OUT="$REPO_ROOT/outputs/t4_r32_verify_runs"; PORT=8004; WEB=5178 ;;
  demo) DB=comqutor_alpha_t4_r32_demo_test; OUT="$REPO_ROOT/outputs/t4_r32_demo_runs"; PORT=8005; WEB=5179 ;;
  *) fail "usage: start_r32_instance.sh verify|demo" ;;
esac
source "$REPO_ROOT/.venv/bin/activate"
URL="$(python "$HERE/create_r32_databases.py" --print-url-for "$DB")" || fail "could not derive the database URL"
[[ "$URL" == postgresql* ]] || fail "not a PostgreSQL URL"
set -a; source "$REPO_ROOT/.env"; set +a   # credentials only; every safety-relevant value is forced below
export COMQUTOR_DATABASE_URL="$URL"
export COMQUTOR_REQUIRE_DATABASE_NAME="$DB"
export COMQUTOR_REQUIRE_DATABASE_DIALECT="postgresql"
export COMQUTOR_OUTPUT_DIR="$OUT"
[[ -d "$OUT" ]] || fail "output directory $OUT does not exist"
export COMQUTOR_REAL_TRADINGAGENTS_ENABLED=false
export COMQUTOR_WEEK2_LLM_ENABLED=false
export COMQUTOR_DATA_SANITY_ENABLED=false
unset COMQUTOR_WEEK2_LLM_PROFILE
export HTTP_PROXY="http://127.0.0.1:9" HTTPS_PROXY="http://127.0.0.1:9" ALL_PROXY="http://127.0.0.1:9"
export http_proxy="$HTTP_PROXY" https_proxy="$HTTPS_PROXY" all_proxy="$ALL_PROXY" NO_PROXY="127.0.0.1,localhost" no_proxy="127.0.0.1,localhost"
export COMQUTOR_API_HOST=127.0.0.1 COMQUTOR_API_PORT=$PORT COMQUTOR_CORS_ORIGINS="http://127.0.0.1:$WEB"
echo "R32 instance ($MODE): db=$DB port=$PORT output=$OUT real_execution=off week2_llm=off outbound=dead-proxy started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
exec "$REPO_ROOT/.venv/bin/comqutor-api"
