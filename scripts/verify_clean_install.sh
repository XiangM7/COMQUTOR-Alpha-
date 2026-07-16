#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CLEAN_ROOT="$(mktemp -d /tmp/comqutor-w6-clean-XXXXXX)"
CLEAN_PYTHON="$CLEAN_ROOT/.venv/bin/python"
DEMO_PID=""
API_PORT=""
FRONTEND_PORT=""

cleanup() {
  trap - EXIT INT TERM
  if [[ -n "$DEMO_PID" ]] && kill -0 "$DEMO_PID" 2>/dev/null; then
    kill -TERM "$DEMO_PID" 2>/dev/null || true
    wait "$DEMO_PID" 2>/dev/null || true
  fi
  rm -f "$CLEAN_ROOT/.demo/w5/api.pid" "$CLEAN_ROOT/.demo/w5/frontend.pid"
  if [[ "${COMQUTOR_KEEP_CLEAN_ROOM:-0}" == "1" ]]; then
    echo "Clean room retained: $CLEAN_ROOT"
  else
    rm -rf "$CLEAN_ROOT"
  fi
}

trap cleanup EXIT INT TERM

fail() {
  echo "W6_CLEAN_INSTALL_FAILED: $1" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "$1 is required"
}

free_port() {
  "$CLEAN_PYTHON" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()'
}

wait_for_url() {
  local url="$1"
  for _ in $(seq 1 80); do
    if curl --fail --silent --output /dev/null "$url"; then
      return 0
    fi
    if [[ -n "$DEMO_PID" ]] && ! kill -0 "$DEMO_PID" 2>/dev/null; then
      return 1
    fi
    sleep 0.5
  done
  return 1
}

require_command python3
require_command rsync
require_command node
require_command npm
require_command curl

echo "Clean room: $CLEAN_ROOT"
rsync -a \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude '.env' \
  --exclude '.env.*' \
  --exclude '.demo/' \
  --exclude 'outputs/' \
  --exclude 'frontend/node_modules/' \
  --exclude 'frontend/dist/' \
  --exclude '.pytest_cache/' \
  --exclude '.ruff_cache/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  "$REPO_ROOT/" "$CLEAN_ROOT/"

python3 -m venv "$CLEAN_ROOT/.venv"
"$CLEAN_PYTHON" -m pip install -e "$CLEAN_ROOT[api,dev]"
"$CLEAN_PYTHON" -m pip check

(
  cd "$CLEAN_ROOT/frontend"
  npm ci
  npm run typecheck
  npm run lint
  npm run test -- --run
  npm run build
)

"$CLEAN_PYTHON" "$CLEAN_ROOT/scripts/seed_w5_demo.py"
"$CLEAN_PYTHON" "$CLEAN_ROOT/scripts/verify_w5_demo.py"

API_PORT="${COMQUTOR_CLEAN_API_PORT:-$(free_port)}"
FRONTEND_PORT="${COMQUTOR_CLEAN_FRONTEND_PORT:-$(free_port)}"
while [[ "$FRONTEND_PORT" == "$API_PORT" ]]; do
  FRONTEND_PORT="$(free_port)"
done

(
  cd "$CLEAN_ROOT"
  exec env COMQUTOR_API_PORT="$API_PORT" COMQUTOR_FRONTEND_PORT="$FRONTEND_PORT" \
    ./scripts/run_w5_demo.sh
) >"$CLEAN_ROOT/w6-clean-demo.log" 2>&1 &
DEMO_PID=$!

API_URL="http://127.0.0.1:$API_PORT"
FRONTEND_URL="http://127.0.0.1:$FRONTEND_PORT"
wait_for_url "$API_URL/health" || fail "health endpoint did not become ready"
wait_for_url "$API_URL/ready" || fail "readiness endpoint did not become ready"
wait_for_url "$API_URL/api/research" || fail "research history endpoint did not become ready"
wait_for_url "$FRONTEND_URL/research" || fail "frontend did not become ready"

curl --fail --silent "$API_URL/health" >"$CLEAN_ROOT/health.json"
curl --fail --silent "$API_URL/ready" >"$CLEAN_ROOT/ready.json"
curl --fail --silent "$API_URL/api/research" >"$CLEAN_ROOT/research.json"
curl --fail --silent "$API_URL/api/research/w5_demo_nvda_20260630" >"$CLEAN_ROOT/nvda.json"
curl --fail --silent "$API_URL/api/research/w5_demo_qqq_20260630" >"$CLEAN_ROOT/qqq.json"

"$CLEAN_PYTHON" -c 'import json,sys; p=json.load(open(sys.argv[1])); assert p["ticker"]=="NVDA" and p["status"]=="completed"' "$CLEAN_ROOT/nvda.json"
"$CLEAN_PYTHON" -c 'import json,sys; p=json.load(open(sys.argv[1])); assert p["ticker"]=="QQQ" and p["status"]=="completed"' "$CLEAN_ROOT/qqq.json"

kill -TERM "$DEMO_PID"
wait "$DEMO_PID" 2>/dev/null || true
DEMO_PID=""
for _ in $(seq 1 20); do
  if [[ ! -e "$CLEAN_ROOT/.demo/w5/api.pid" && ! -e "$CLEAN_ROOT/.demo/w5/frontend.pid" ]]; then
    break
  fi
  sleep 0.1
done
[[ ! -e "$CLEAN_ROOT/.demo/w5/api.pid" ]] || fail "API pid file was not cleaned"
[[ ! -e "$CLEAN_ROOT/.demo/w5/frontend.pid" ]] || fail "frontend pid file was not cleaned"

"$CLEAN_PYTHON" -c 'import socket,sys; ports=map(int,sys.argv[1:]); assert all(socket.socket().connect_ex(("127.0.0.1", p)) != 0 for p in ports)' "$API_PORT" "$FRONTEND_PORT"

echo "W6_CLEAN_INSTALL_PASS"
echo "health=PASS ready=PASS research_history=PASS NVDA=PASS QQQ=PASS cleanup=PASS"
