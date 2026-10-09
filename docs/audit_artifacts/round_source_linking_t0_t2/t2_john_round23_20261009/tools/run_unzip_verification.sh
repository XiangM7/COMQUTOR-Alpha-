#!/usr/bin/env bash
# T2 John version (2026-10-09): unzip the delivered ZIP into a brand-new directory and check it there. Every command, its full
# output and its exit code go to unzip_verification/verification_log.txt. Read-only towards everything except that folder and
# the fresh extraction directory.
set -u
BASE="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$BASE/../../../.." && pwd)"
ZIP="$BASE/T2_John_round23_20261009.zip"
OUT="$BASE/unzip_verification"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
X="${X_ROOT:-/private/tmp/claude-501/-Users-xiangmao-COMQUTOR-Alpha-/8d38fcbd-98ee-4ff6-b804-8855e3f6b189/scratchpad}/t2john_unzip_$TS"
LOG="$OUT/verification_log.txt"
mkdir -p "$OUT"
: > "$LOG"
FAILS=0
run() {
  echo "\$ $*" >> "$LOG"
  "$@" >> "$LOG" 2>&1
  local rc=$?
  echo "[exit $rc]" >> "$LOG"
  echo >> "$LOG"
  [ $rc -eq 0 ] || FAILS=$((FAILS + 1))
  return $rc
}
cd "$BASE" || exit 2
echo "# unzip verification $TS; fresh directory: $X" >> "$LOG"
[ -e "$X" ] && { echo "extraction directory already exists" >> "$LOG"; exit 2; }
run ls -l "$ZIP"
run shasum -a 256 "$ZIP"
run unzip -tq "$ZIP"
run mkdir "$X"
run python3 -m zipfile -e "$ZIP" "$X"
run bash -c "find '$X' -type f | wc -l; find '$X' -maxdepth 2 | sort"
P="$X/T2_John_round23"
echo "## 1. in-package verifier (from the unzipped root), Python 3.12 and the system Python 3.9" >> "$LOG"
( cd "$P" && run python3 verify_t2_package.py )
( cd "$P" && run /usr/bin/python3 verify_t2_package.py )
( cd "$P" && python3 verify_t2_package.py --json > "$OUT/verify_t2_package_result.json"; echo "[--json exit $?] -> unzip_verification/verify_t2_package_result.json" >> "$LOG" )
echo "## 2. cross-check against sources outside the package (build dir, outputs/runs originals, T1 archive, Round 22 record, Round 23 dir)" >> "$LOG"
run python3 tools/crosscheck_extracted.py "$P" --build "$BASE/T2_John_round23"
echo "## 3. credential scan of the unzipped package (patterns + the .env secret values, names only)" >> "$LOG"
run python3 tools/scan_credentials.py --target "$P" --env "$REPO/.env" --out "$OUT/credential_scan_unzipped.json"
echo "## 4. originals after zipping vs before copying (six runs, Round 23 dir, uploaded t2.zip / t1.zip, T1 archive, reviewed ZIP, Round 22 records)" >> "$LOG"
run python3 tools/snapshot_originals.py --out "$BASE/hash_proof/state_after_zip.json" --compare "$BASE/hash_proof/state_before.json"
echo "# done; failed commands: $FAILS" >> "$LOG"
echo "failed commands: $FAILS (log: $LOG)"
[ $FAILS -eq 0 ]
