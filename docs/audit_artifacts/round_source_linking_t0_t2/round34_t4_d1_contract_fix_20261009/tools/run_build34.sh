#!/usr/bin/env bash
# T4 round 34 (D1 fix): build the supplement package and ZIP; commands, full output and exit codes go to build_log.txt.
# Removes only its own previous package directory; refuses to overwrite an existing ZIP. Expects hash_proof/state_after.json.
set -u
BASE="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$BASE/../../../.." && pwd)"
PKG=T4_D1_fix_r34
ZIP=T4_D1_fix_round34_20261009.zip
LOG="$BASE/build_log.txt"
cd "$BASE" || exit 2
: > "$LOG"
run() { echo "\$ $*" | tee -a "$LOG"; "$@" >> "$LOG" 2>&1; local rc=$?; echo "[exit $rc]" | tee -a "$LOG"; echo >> "$LOG"; return $rc; }
echo "# build started $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
[ -e "$ZIP" ] && { echo "$ZIP exists; not rebuilding" | tee -a "$LOG"; exit 2; }
[ -f hash_proof/state_after.json ] || { echo "missing hash_proof/state_after.json" | tee -a "$LOG"; exit 2; }
run rm -rf "$PKG" || exit 1
run python3 tools/build_d1_package34.py --pkg "$PKG" || exit 1
run python3 tools/scan_credentials.py --target "$PKG" --env "$REPO/.env" --out "$PKG/credential_scan_result.json" || exit 1
run python3 tools/finalize_manifest33.py --pkg "$PKG" || exit 1
( cd "$PKG" && run python3 verify_d1_fix.py ) || exit 1
run python3 tools/make_zip.py --pkg "$PKG" --out "$ZIP" || exit 1
echo "# build finished $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
