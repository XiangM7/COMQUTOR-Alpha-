#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON="$REPO_ROOT/.venv/bin/python"
FRONTEND_DIR="$REPO_ROOT/frontend"
DEMO_ROOT="$REPO_ROOT/.demo/w5"
OUTPUT_ROOT="$DEMO_ROOT/outputs/runs"
DATABASE_PATH="$DEMO_ROOT/comqutor_demo.db"
DATABASE_URL="sqlite:///$DATABASE_PATH"
API_PORT="${COMQUTOR_API_PORT:-8001}"
FRONTEND_PORT="${COMQUTOR_FRONTEND_PORT:-5175}"
API_URL="http://127.0.0.1:$API_PORT"
FRONTEND_URL="http://127.0.0.1:$FRONTEND_PORT"
API_PID=""
FRONTEND_PID=""

cleanup() {
  trap - EXIT INT TERM
  for pid in "$FRONTEND_PID" "$API_PID"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill -TERM "$pid" 2>/dev/null || true
    fi
  done
  for pid in "$FRONTEND_PID" "$API_PID"; do
    if [[ -n "$pid" ]]; then
      wait "$pid" 2>/dev/null || true
    fi
  done
  rm -f "$DEMO_ROOT/api.pid" "$DEMO_ROOT/frontend.pid"
}

trap cleanup EXIT INT TERM

fail() {
  echo "W5_DEMO_START_FAILED: $1" >&2
  exit 1
}

port_in_use() {
  "$PYTHON" -c 'import socket, sys; s=socket.socket(); s.settimeout(0.2); result=s.connect_ex(("127.0.0.1", int(sys.argv[1]))); s.close(); raise SystemExit(0 if result == 0 else 1)' "$1"
}

http_status() {
  curl --silent --output /dev/null --write-out '%{http_code}' "$1" || true
}

[[ -x "$PYTHON" ]] || fail "Missing .venv. Create the project virtual environment first."
"$PYTHON" -c 'import fastapi, uvicorn' >/dev/null 2>&1 || \
  fail 'API dependencies are missing. Run .venv/bin/python -m pip install -e ".[api,dev]".'
[[ -x "$FRONTEND_DIR/node_modules/.bin/vite" ]] || \
  fail "Frontend dependencies are missing. Run: cd frontend && npm install"
command -v curl >/dev/null 2>&1 || fail "curl is required for readiness checks."

if port_in_use "$API_PORT"; then
  health_status="$(http_status "$API_URL/health")"
  ready_status="$(http_status "$API_URL/ready")"
  history_status="$(http_status "$API_URL/api/research")"
  if [[ "$health_status" == "200" && "$ready_status" != "404" && "$history_status" != "404" ]]; then
    fail "Port $API_PORT already has a compatible COMQUTOR API. Stop it or choose another COMQUTOR_API_PORT."
  fi
  fail "INCOMPATIBLE_COMQUTOR_API on port $API_PORT. The existing process was not stopped."
fi

if port_in_use "$FRONTEND_PORT"; then
  fail "Port $FRONTEND_PORT is already occupied. The existing process was not stopped."
fi

mkdir -p "$DEMO_ROOT"
"$PYTHON" "$REPO_ROOT/scripts/seed_w5_demo.py" \
  --output-root "$OUTPUT_ROOT" \
  --database-url "$DATABASE_URL"
"$PYTHON" "$REPO_ROOT/scripts/verify_w5_demo.py" \
  --output-root "$OUTPUT_ROOT" \
  --database-url "$DATABASE_URL"

(
  export COMQUTOR_ENV="development"
  export COMQUTOR_DATABASE_URL="$DATABASE_URL"
  export COMQUTOR_OUTPUT_DIR="$OUTPUT_ROOT"
  export COMQUTOR_API_HOST="127.0.0.1"
  export COMQUTOR_API_PORT="$API_PORT"
  export COMQUTOR_CORS_ORIGINS="$FRONTEND_URL"
  export COMQUTOR_REAL_TRADINGAGENTS_ENABLED="false"
  export COMQUTOR_REAL_FORCE_REFRESH_ENABLED="false"
  export COMQUTOR_WEEK2_LLM_ENABLED="false"
  exec "$PYTHON" -m comqutor_alpha.api.server
) >"$DEMO_ROOT/api.log" 2>&1 &
API_PID=$!
printf '%s\n' "$API_PID" >"$DEMO_ROOT/api.pid"

api_ready="false"
for _ in $(seq 1 60); do
  if ! kill -0 "$API_PID" 2>/dev/null; then
    fail "COMQUTOR API exited during startup. See .demo/w5/api.log."
  fi
  health_status="$(http_status "$API_URL/health")"
  ready_status="$(http_status "$API_URL/ready")"
  history_status="$(http_status "$API_URL/api/research")"
  if [[ "$health_status" == "200" && ( "$ready_status" == "404" || "$history_status" == "404" ) ]]; then
    fail "INCOMPATIBLE_COMQUTOR_API"
  fi
  if [[ "$health_status" == "200" && "$ready_status" == "200" && "$history_status" == "200" ]]; then
    api_ready="true"
    break
  fi
  sleep 0.5
done
[[ "$api_ready" == "true" ]] || fail "API readiness checks did not pass."

(
  cd "$FRONTEND_DIR"
  export VITE_COMQUTOR_API_BASE_URL="$API_URL"
  exec ./node_modules/.bin/vite --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort
) >"$DEMO_ROOT/frontend.log" 2>&1 &
FRONTEND_PID=$!
printf '%s\n' "$FRONTEND_PID" >"$DEMO_ROOT/frontend.pid"

frontend_ready="false"
for _ in $(seq 1 60); do
  if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    fail "Vite frontend exited during startup. See .demo/w5/frontend.log."
  fi
  if [[ "$(http_status "$FRONTEND_URL/research")" == "200" ]]; then
    frontend_ready="true"
    break
  fi
  sleep 0.5
done
[[ "$frontend_ready" == "true" ]] || fail "Frontend readiness check did not pass."

echo "W5_DEMO_READY"
echo "Research page: $FRONTEND_URL/research"
echo "API: $API_URL"
echo "NVDA input: ticker=NVDA date=2026-06-30 analysts=market,news,fundamentals,sentiment"
echo "QQQ input: ticker=QQQ date=2026-06-30 analysts=market,news,fundamentals,sentiment"
echo "Real TradingAgents and Provider execution are disabled."
echo "Press Ctrl+C to stop this demo."

while kill -0 "$API_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 1
done

fail "A demo process exited unexpectedly."
