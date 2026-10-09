#!/usr/bin/env bash
# T4 round 33 (2026-10-09): unzip the delivered ZIP into a brand-new directory and check it there; every command, its full
# output and its exit code go to unzip_verification/verification_log.txt. Writes only into unzip_verification/, the fresh
# extraction directory and a scratch directory for the README re-runs.
set -u
BASE="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$BASE/../../../.." && pwd)"
ZIP="$BASE/T4_final_round33_20261009.zip"
OUT="$BASE/unzip_verification"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
SCRATCH="${SCRATCH:-/private/tmp/claude-501/-Users-xiangmao-COMQUTOR-Alpha-/8d38fcbd-98ee-4ff6-b804-8855e3f6b189/scratchpad}"
X="$SCRATCH/t4r33_unzip_$TS"
RERUN="$SCRATCH/t4r33_readme_rerun_$TS"
LOG="$OUT/verification_log.txt"
mkdir -p "$OUT"; : > "$LOG"
FAILS=0
run() { echo "\$ $*" >> "$LOG"; "$@" >> "$LOG" 2>&1; local rc=$?; echo "[exit $rc]" >> "$LOG"; echo >> "$LOG"; [ $rc -eq 0 ] || FAILS=$((FAILS + 1)); return $rc; }
cd "$BASE" || exit 2
echo "# unzip verification $TS; fresh directory: $X" >> "$LOG"
[ -e "$X" ] && { echo "extraction directory exists" >> "$LOG"; exit 2; }
run ls -l "$ZIP"
run shasum -a 256 "$ZIP"
run unzip -tq "$ZIP"
run mkdir "$X" "$RERUN"
run python3 -m zipfile -e "$ZIP" "$X"
run bash -c "find '$X' -type f | wc -l; find '$X' -name __pycache__ | wc -l; find '$X' -maxdepth 2 | sort"
P="$X/T4_final_r33"
echo "## 1. in-package check from the unzipped root (the command in README section 1)" >> "$LOG"
( cd "$P" && run python3 verify_package33.py )
( cd "$P" && python3 verify_package33.py --json > "$OUT/verify_package33_result.json"; echo "[--json exit $?] -> unzip_verification/verify_package33_result.json" >> "$LOG" )
run bash -c "find '$P' -name __pycache__ | wc -l"
echo "## 2. the unzipped package equals the build directory; round32/ equals the Round 32 ZIP except the logged edits / superseded files" >> "$LOG"
run python3 - "$P" "$BASE/T4_final_r33" "$BASE/../round32_t4_closure_20261009/T4_final_round32_20261009.zip" <<'EOF'
import hashlib, json, sys, zipfile
from pathlib import Path
x, b, z32 = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
def tree(r): return {p.relative_to(r).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(r.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}
tx, tb = tree(x), tree(b)
print("unzipped == build dir:", tx == tb, len(tx), len(tb))
log = json.loads((x / "round33/records/文档修改记录.json").read_text(encoding="utf-8"))
edited = {e["round32_path"] for e in log["edited_documents"]}; superseded = {s["round32_path"] for s in log["superseded_not_copied"]}
with zipfile.ZipFile(z32) as z:
    name = lambda i: i.filename if i.flag_bits & 0x800 else i.filename.encode("cp437").decode("utf-8")  # some names lack the UTF-8 flag
    members = {name(i)[len("T4_final/"):]: hashlib.sha256(z.read(i)).hexdigest() for i in z.infolist() if not i.filename.endswith("/")}
same = sum(1 for k, v in members.items() if k not in edited | superseded and tx.get("round32/" + k) == v)
print("Round 32 ZIP files:", len(members), "| byte-identical in round32/:", same, "| edited:", sorted(edited), "| superseded (not copied):", sorted(superseded))
ok = tx == tb and same == len(members) - len(edited) - len(superseded) and all(("round32/" + k) not in tx for k in superseded)
print("ok:", ok); sys.exit(0 if ok else 1)
EOF
echo "## 3. README section 2 commands re-run from the repository root (outputs to a scratch directory instead of /tmp), compared with the package" >> "$LOG"
R33=docs/audit_artifacts/round_source_linking_t0_t2/round33_t4_closeout_20261009
( cd "$REPO" && source .venv/bin/activate && run python "$R33/tools/run_with_network_trap.py" "$R33/tools/d1_offline_reproduction.py" --run 12591384-0b26-470d-a99d-a49c00be440b --out "$RERUN/d1_recheck.json" )
( cd "$REPO" && run python3 "$R33/tools/run_with_network_trap.py" "$R33/tools/reconcile_not_sent.py" --out-json "$RERUN/reconcile.json" --out-md "$RERUN/reconcile.md" )
( cd "$REPO" && run node "$R33/tools/viewer_check.mjs" --base http://127.0.0.1:5179 --api http://127.0.0.1:8005 --out "$RERUN/viewer_check" )
run python3 - "$P" "$RERUN" <<'EOF'
import json, sys
from pathlib import Path
p, r = Path(sys.argv[1]) / "round33", Path(sys.argv[2])
load = lambda f: json.loads(f.read_text(encoding="utf-8"))
d1 = load(r / "d1_recheck.json") == load(p / "01_d1/d1_fresh2.json")
rc = {k: v for k, v in load(r / "reconcile.json").items()} == load(p / "03_not_sent_reconcile/reconcile.json")
v_new, v_old = load(r / "viewer_check/viewer_check_result.json"), load(p / "02_viewer/check/viewer_check_result.json")
view = (v_new["export_sha256"] == v_old["export_sha256"] and v_new["ready"]["code_identity"]["tracked_diff_sha256"] == v_old["ready"]["code_identity"]["tracked_diff_sha256"]
        and [s["value"] for s in v_new["steps"][:3]] == [s["value"] for s in v_old["steps"][:3]] and not v_new["safety"]["blocked_requests"]
        and load(r / "viewer_check/api_stage_disclosure.json") == load(p / "02_viewer/check/api_stage_disclosure.json"))
print("README re-run equals the package -- D1:", d1, "| reconcile:", rc, "| viewer (export sha, code, panel text, disclosure, 0 blocked):", view)
sys.exit(0 if d1 and rc and view else 1)
EOF
echo "## 4. credential scan of the unzipped package (patterns + the .env secret values, names only)" >> "$LOG"
run python3 tools/scan_credentials.py --target "$P" --env "$REPO/.env" --out "$OUT/credential_scan_unzipped.json"
echo "## 5. originals after zipping vs the start of this round" >> "$LOG"
rm -f "$BASE/hash_proof/state_after_zip.json"
run python3 tools/snapshot_state.py --out "$BASE/hash_proof/state_after_zip.json" --compare "$BASE/hash_proof/state_before.json"
run python3 -c "import json; d=json.load(open('$BASE/hash_proof/state_after_zip.json')); print(json.dumps(d['read_only_comparison'], ensure_ascii=False)); print(json.dumps(d['code_identity_changes']))"
echo "# done; failed commands: $FAILS" >> "$LOG"
echo "failed commands: $FAILS (log: $LOG)"
[ $FAILS -eq 0 ]
