#!/usr/bin/env bash
# T2 John version (2026-10-09): build the package directory and the ZIP from read-only originals; every command, its full
# output and its exit code go to build_log.txt. Expects hash_proof/state_before.json to exist (taken before any copy).
# Removes only its own previous build output (T2_John_round23/); refuses to overwrite an existing ZIP.
set -u
BASE="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$BASE/../../../.." && pwd)"
STAGING="${STAGING:-/private/tmp/claude-501/-Users-xiangmao-COMQUTOR-Alpha-/8d38fcbd-98ee-4ff6-b804-8855e3f6b189/scratchpad/t2john_staging}"
PKG=T2_John_round23
ZIP=T2_John_round23_20261009.zip
LOG="$BASE/build_log.txt"
cd "$BASE" || exit 2
: > "$LOG"
run() {
  echo "\$ $*" | tee -a "$LOG"
  "$@" >> "$LOG" 2>&1
  local rc=$?
  echo "[exit $rc]" | tee -a "$LOG"
  echo >> "$LOG"
  return $rc
}
echo "# build started $(date -u +%Y-%m-%dT%H:%M:%SZ) in $(basename "$BASE"); python3 $(python3 -c 'import sys; print(sys.version.split()[0])')" >> "$LOG"
[ -f hash_proof/state_before.json ] || { echo "missing hash_proof/state_before.json" | tee -a "$LOG"; exit 2; }
[ -e "$ZIP" ] && { echo "$ZIP already exists; not rebuilding" | tee -a "$LOG"; exit 2; }
run rm -rf "$PKG" || exit 1
run python3 tools/build_package.py --pkg "$PKG" --staging "$STAGING" || exit 1
run python3 tools/snapshot_originals.py --out hash_proof/state_after_copy.json --compare hash_proof/state_before.json || exit 1
run python3 tools/build_inventory.py --pkg "$PKG" || exit 1
run python3 tools/scan_credentials.py --target "$PKG" --env "$REPO/.env" --out "$PKG/核查记录/credential_scan_result.json" || exit 1
run python3 tools/finalize_package.py --pkg "$PKG" || exit 1
( cd "$PKG" && run python3 verify_t2_package.py ) || exit 1
run python3 tools/make_zip.py --pkg "$PKG" --out "$ZIP" || exit 1
echo "# build finished $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
