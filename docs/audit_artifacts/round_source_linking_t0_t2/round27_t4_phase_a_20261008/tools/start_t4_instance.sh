#!/usr/bin/env bash
# T4 Phase A: the isolated T4 API instance -- its own PostgreSQL database (comqutor_alpha_t4_test), its own output directory
# (outputs/t4_runs), port 8002, frontend origin http://127.0.0.1:5177. Never the 8000 service, its database or outputs/runs' runs.
#
#   bash start_t4_instance.sh verify   # real execution OFF, Week 2 LLM OFF, outbound HTTP(S) proxied to a dead loopback port:
#                                      # can only run frozen/offline inputs, cannot reach a provider or a data source
#   bash start_t4_instance.sh fresh    # the NVDA Fresh Run instance: through scripts/start_live_comqutor.sh (its live preflight),
#                                      # Week 2 profile t3_verified_20261008, request budgets and stop rules of 04_fresh_prep/
#
# Either mode refuses to start unless the database URL is PostgreSQL and names comqutor_alpha_t4_test (checked again inside the
# server process by COMQUTOR_REQUIRE_DATABASE_DIALECT / COMQUTOR_REQUIRE_DATABASE_NAME).
set -euo pipefail
MODE="${1:-}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../../../.." && pwd)"
cd "$REPO_ROOT"
fail() { echo "T4_INSTANCE_REFUSED: $1" >&2; exit 1; }
[[ "$MODE" == "verify" || "$MODE" == "fresh" ]] || fail "usage: start_t4_instance.sh verify|fresh"
source "$REPO_ROOT/.venv/bin/activate"
T4_DB="comqutor_alpha_t4_test"
T4_URL="$(python "$HERE/create_t4_databases.py" --print-url-for "$T4_DB")" || fail "could not derive the T4 database URL"
export COMQUTOR_DATABASE_URL="$T4_URL"
export COMQUTOR_REQUIRE_DATABASE_NAME="$T4_DB"
export COMQUTOR_REQUIRE_DATABASE_DIALECT="postgresql"
export COMQUTOR_OUTPUT_DIR="$REPO_ROOT/outputs/t4_runs"
mkdir -p "$COMQUTOR_OUTPUT_DIR"
unset COMQUTOR_WEEK2_CONTENT_SUPPORT_MAX_TOKENS COMQUTOR_WEEK2_ALPHA_CLASSIFIER_MAX_TOKENS COMQUTOR_WEEK2_CONTENT_SUPPORT_BATCH_SIZE

if [[ "$MODE" == "verify" ]]; then
  set -a; source "$REPO_ROOT/.env"; set +a   # credentials only; every safety-relevant value is forced below
  export COMQUTOR_DATABASE_URL="$T4_URL"
  export COMQUTOR_REAL_TRADINGAGENTS_ENABLED=false
  export COMQUTOR_WEEK2_LLM_ENABLED=false
  export COMQUTOR_DATA_SANITY_ENABLED=false
  unset COMQUTOR_WEEK2_LLM_PROFILE
  export HTTP_PROXY="http://127.0.0.1:9" HTTPS_PROXY="http://127.0.0.1:9" ALL_PROXY="http://127.0.0.1:9"
  export http_proxy="$HTTP_PROXY" https_proxy="$HTTPS_PROXY" all_proxy="$ALL_PROXY" NO_PROXY="127.0.0.1,localhost" no_proxy="127.0.0.1,localhost"
  export COMQUTOR_API_HOST=127.0.0.1 COMQUTOR_API_PORT=8002 COMQUTOR_CORS_ORIGINS="http://127.0.0.1:5177"
  echo "T4 instance (verify): db=$T4_DB port=8002 output=$COMQUTOR_OUTPUT_DIR real_execution=off week2_llm=off outbound=dead-proxy"
  exec "$REPO_ROOT/.venv/bin/comqutor-api"
fi

# fresh: hand off to the one permanent live launcher (its own .env handling keeps COMQUTOR_DATABASE_URL, and it runs the live
# semantic preflight before exec'ing comqutor-api); the values below are the frozen configuration of 04_fresh_prep/frozen_config.json
export COMQUTOR_LIVE_API_PORT=8002
export COMQUTOR_LIVE_FRONTEND_ORIGIN="http://127.0.0.1:5177"
export COMQUTOR_WEEK2_LLM_PROFILE="t3_verified_20261008"
export COMQUTOR_WEEK2_LLM_MAX_RETRIES=0
export COMQUTOR_WEEK2_LLM_MAX_CALLS="${T4_WEEK2_MAX_CALLS:?set T4_WEEK2_MAX_CALLS from 04_fresh_prep/budget.json}"
export COMQUTOR_RESEARCH_AGENT_MAX_ACTUAL_REQUESTS="${T4_AGENT_MAX_REQUESTS:?set T4_AGENT_MAX_REQUESTS from 04_fresh_prep/budget.json}"
export COMQUTOR_RESEARCH_AGENT_MAX_RETRIES=0
export COMQUTOR_JOB_TIMEOUT_SECONDS="${T4_JOB_TIMEOUT_SECONDS:?set T4_JOB_TIMEOUT_SECONDS from 04_fresh_prep/budget.json}"
export COMQUTOR_JOB_MAX_WORKERS=1
export COMQUTOR_REAL_FORCE_REFRESH_ENABLED=false
echo "T4 instance (fresh): db=$T4_DB port=8002 output=$COMQUTOR_OUTPUT_DIR week2_profile=$COMQUTOR_WEEK2_LLM_PROFILE week2_max_calls=$COMQUTOR_WEEK2_LLM_MAX_CALLS agent_max_requests=$COMQUTOR_RESEARCH_AGENT_MAX_ACTUAL_REQUESTS job_timeout_s=$COMQUTOR_JOB_TIMEOUT_SECONDS"
exec bash "$REPO_ROOT/scripts/start_live_comqutor.sh"
