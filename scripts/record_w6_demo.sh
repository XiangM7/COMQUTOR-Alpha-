#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON="$REPO_ROOT/.venv/bin/python"
VIDEO_PATH=".demo/w6/recordings/comqutor_alpha_w6_demo.webm"
DEMO_PID=""

cleanup() {
  trap - EXIT INT TERM
  if [[ -n "$DEMO_PID" ]] && kill -0 "$DEMO_PID" 2>/dev/null; then
    kill -TERM "$DEMO_PID" 2>/dev/null || true
    wait "$DEMO_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

fail() {
  echo "W6_DEMO_RECORDING_FAILED: $1" >&2
  exit 1
}

free_port() {
  "$PYTHON" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()'
}

wait_for_url() {
  local url="$1"
  for _ in $(seq 1 80); do
    if curl --fail --silent --output /dev/null "$url"; then
      return 0
    fi
    if ! kill -0 "$DEMO_PID" 2>/dev/null; then
      return 1
    fi
    sleep 0.5
  done
  return 1
}

[[ -x "$PYTHON" ]] || fail "project .venv is missing"
[[ -x "$REPO_ROOT/frontend/node_modules/.bin/playwright" ]] || \
  fail "frontend dependencies are missing; run npm ci in frontend"
command -v node >/dev/null 2>&1 || fail "node is required"
command -v curl >/dev/null 2>&1 || fail "curl is required"
command -v shasum >/dev/null 2>&1 || fail "shasum is required"

API_PORT="${COMQUTOR_RECORD_API_PORT:-$(free_port)}"
FRONTEND_PORT="${COMQUTOR_RECORD_FRONTEND_PORT:-$(free_port)}"
while [[ "$FRONTEND_PORT" == "$API_PORT" ]]; do
  FRONTEND_PORT="$(free_port)"
done

(
  cd "$REPO_ROOT"
  exec env COMQUTOR_API_PORT="$API_PORT" COMQUTOR_FRONTEND_PORT="$FRONTEND_PORT" \
    ./scripts/run_w5_demo.sh
) >"$REPO_ROOT/.demo/w6-recording-demo.log" 2>&1 &
DEMO_PID=$!

API_URL="http://127.0.0.1:$API_PORT"
FRONTEND_URL="http://127.0.0.1:$FRONTEND_PORT"
wait_for_url "$API_URL/ready" || fail "Demo API did not become ready"
wait_for_url "$FRONTEND_URL/research" || fail "Demo frontend did not become ready"

cd "$REPO_ROOT"
node scripts/w6_demo_recorder.mjs "$FRONTEND_URL" "$VIDEO_PATH"
test -s "$VIDEO_PATH" || fail "recorded video is empty"
shasum -a 256 "$VIDEO_PATH"
echo "W6_DEMO_RECORDING_PASS"
