#!/usr/bin/env bash
# T4 round 33 (2026-10-09): build the John-version package and ZIP; every command, its full output and its exit code go to
# build_log.txt. Removes only its own previous outputs (the package directory and hash_proof/state_after_build.json);
# refuses to overwrite an existing ZIP.
set -u
BASE="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$BASE/../../../.." && pwd)"
PKG=T4_final_r33
ZIP=T4_final_round33_20261009.zip
LOG="$BASE/build_log.txt"
cd "$BASE" || exit 2
: > "$LOG"
run() { echo "\$ $*" | tee -a "$LOG"; "$@" >> "$LOG" 2>&1; local rc=$?; echo "[exit $rc]" | tee -a "$LOG"; echo >> "$LOG"; return $rc; }
echo "# build started $(date -u +%Y-%m-%dT%H:%M:%SZ); python3 $(python3 -c 'import sys; print(sys.version.split()[0])')" >> "$LOG"
[ -e "$ZIP" ] && { echo "$ZIP already exists; not rebuilding" | tee -a "$LOG"; exit 2; }
run rm -rf "$PKG" hash_proof/state_after_build.json || exit 1
run python3 tools/snapshot_state.py --out hash_proof/state_after_build.json --compare hash_proof/state_before.json || exit 1
run python3 tools/build_package33.py --pkg "$PKG" --state-before hash_proof/state_before.json --state-after hash_proof/state_after_build.json || exit 1
run python3 tools/scan_credentials.py --target "$PKG" --env "$REPO/.env" --out "$PKG/round33/records/credential_scan_result.json" || exit 1
run python3 tools/finalize_manifest33.py --pkg "$PKG" || exit 1
( cd "$PKG" && run python3 verify_package33.py ) || exit 1
run python3 tools/make_zip.py --pkg "$PKG" --out "$ZIP" || exit 1
echo "# build finished $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
