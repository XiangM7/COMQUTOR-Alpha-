#!/usr/bin/env bash
# Round 32: unzip the final T4 ZIP into a NEW temporary directory and run every check there; each command, its full output and
# its exit code go to unzip_verification/verification_log.txt. Run from the repository root:
#   bash docs/audit_artifacts/round_source_linking_t0_t2/round32_t4_closure_20261009/unzip_verification/run_unzip_verification.sh
set -u
REPO="$(pwd)"
R32="docs/audit_artifacts/round_source_linking_t0_t2/round32_t4_closure_20261009"
ZIP="$REPO/$R32/T4_final_round32_20261009.zip"
OUT="$REPO/$R32/unzip_verification"
LOG="$OUT/verification_log.txt"
DEST="$(mktemp -d "${TMPDIR:-/tmp}/t4_r32_unzip_verify.XXXXXX")"
: > "$LOG"
run() {
  local label="$1"; shift
  { echo "=================================================================="; echo "[$label] $(date -u +%Y-%m-%dT%H:%M:%SZ)"; echo "cwd: $(pwd)"; echo "\$ $*"; } >> "$LOG"
  "$@" >> "$LOG" 2>&1
  local code=$?
  echo "exit_code: $code" >> "$LOG"; echo "[$label] exit_code=$code"
}
run "0a zip sha256" shasum -a 256 "$ZIP"
run "0b zip size and file count" bash -c "ls -l '$ZIP'; unzip -Z1 '$ZIP' | grep -v '/\$' | wc -l"
run "0c unzip into a new empty directory" unzip -q "$ZIP" -d "$DEST"
cd "$DEST/T4_final" || exit 2
run "1-6 verify_package32 (hashes, references + README commands, offline statistics, artifacts, secrets incl. .env values, identity)" \
    python3 tools/verify_package32.py --env "$REPO/.env" --out "$DEST/verify_package32_result.json"
cp "$DEST/verify_package32_result.json" "$OUT/verify_package32_result.json"
run "README command 1 (as written)" python3 tools/verify_package32.py
run "README command 2 (as written): offline statistics vs report" python3 tools/rebuild_stats32.py
run "README command 3 (as written): credential pattern scan" python3 tools/scan_credentials.py
run "no __pycache__ or stray files created by the checks" bash -c "find . -name __pycache__ -o -name '.DS_Store' | wc -l"
cd "$REPO" || exit 2
run "7 original runs, round 31 package / old ZIPs and protected directories: before/after hashes" \
    python3 "$R32/tools/snapshot_state.py" --out "$R32/hash_proof/state_after.json" --compare "$R32/hash_proof/state_before.json"
run "7b original Fresh run directories equal the copies inside the nested Round 31 ZIP" bash -c "mkdir -p '$DEST/r31' && unzip -q '$DEST/T4_final/references/T4_delivery_round31_20261009.zip' -d '$DEST/r31' && diff -r outputs/t4_runs/12591384-0b26-470d-a99d-a49c00be440b '$DEST/r31/T4_delivery/runs/12591384-0b26-470d-a99d-a49c00be440b' && diff -r outputs/t4_runs/fa642639-8d93-4f9a-9de1-2c4d789eade8 '$DEST/r31/T4_delivery/runs/fa642639-8d93-4f9a-9de1-2c4d789eade8' && echo identical"
run "7c the original Round 31 ZIP is unchanged" bash -c "shasum -a 256 docs/audit_artifacts/round_source_linking_t0_t2/round31_t4_delivery_20261009/T4_delivery_round31_20261009.zip"
echo "unzipped at: $DEST" >> "$LOG"
echo "log: $LOG"
