#!/usr/bin/env bash
# T4 round 34 (D1 fix): unzip the supplement into a brand-new directory and check it there (Python 3.12 and the system 3.9);
# commands, full output and exit codes go to unzip_verification/verification_log.txt.
set -u
BASE="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$BASE/../../../.." && pwd)"
ZIP="$BASE/T4_D1_fix_round34_20261009.zip"
OUT="$BASE/unzip_verification"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
X="${SCRATCH:-/private/tmp/claude-501/-Users-xiangmao-COMQUTOR-Alpha-/8d38fcbd-98ee-4ff6-b804-8855e3f6b189/scratchpad}/t4r34_unzip_$TS"
LOG="$OUT/verification_log.txt"
mkdir -p "$OUT"; : > "$LOG"; FAILS=0
run() { echo "\$ $*" >> "$LOG"; "$@" >> "$LOG" 2>&1; local rc=$?; echo "[exit $rc]" >> "$LOG"; echo >> "$LOG"; [ $rc -eq 0 ] || FAILS=$((FAILS + 1)); return $rc; }
cd "$BASE" || exit 2
echo "# unzip verification $TS; fresh directory: $X" >> "$LOG"
run ls -l "$ZIP"; run shasum -a 256 "$ZIP"; run unzip -tq "$ZIP"
run mkdir "$X"; run python3 -m zipfile -e "$ZIP" "$X"
run bash -c "find '$X' -type f | wc -l; find '$X' -name __pycache__ | wc -l"
P="$X/T4_D1_fix_r34"
( cd "$P" && run python3 verify_d1_fix.py )
( cd "$P" && run /usr/bin/python3 verify_d1_fix.py )
( cd "$P" && python3 verify_d1_fix.py --json > "$OUT/verify_d1_fix_result.json"; echo "[--json exit $?]" >> "$LOG" )
run python3 - "$P" "$BASE/T4_D1_fix_r34" <<'PY'
import hashlib, sys
from pathlib import Path
t = lambda r: {p.relative_to(r).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(r.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}
a, b = t(Path(sys.argv[1])), t(Path(sys.argv[2]))
print("unzipped == build dir:", a == b, len(a), len(b)); sys.exit(0 if a == b else 1)
PY
run python3 tools/scan_credentials.py --target "$P" --env "$REPO/.env" --out "$OUT/credential_scan_unzipped.json"
rm -f "$BASE/hash_proof/state_after_zip.json"
run python3 tools/snapshot_state.py --out "$BASE/hash_proof/state_after_zip.json" --compare "$BASE/hash_proof/state_before.json"
run python3 -c "import json; d=json.load(open('$BASE/hash_proof/state_after_zip.json')); print(json.dumps(d['read_only_comparison'])); print(json.dumps(d['code_identity_changes']))"
echo "# done; failed commands: $FAILS" >> "$LOG"; echo "failed commands: $FAILS (log: $LOG)"
[ $FAILS -eq 0 ]
