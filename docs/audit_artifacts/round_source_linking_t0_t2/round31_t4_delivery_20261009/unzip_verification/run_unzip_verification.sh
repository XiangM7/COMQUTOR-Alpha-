#!/usr/bin/env bash
# Round 31: unzip the final T4 ZIP into a NEW temporary directory and run every check there; every command, its full output
# and its exit code go to unzip_verification/verification_log.txt. Run from the repository root:
#   bash docs/audit_artifacts/round_source_linking_t0_t2/round31_t4_delivery_20261009/unzip_verification/run_unzip_verification.sh
set -u
REPO="$(pwd)"
R31="docs/audit_artifacts/round_source_linking_t0_t2/round31_t4_delivery_20261009"
ZIP="$REPO/$R31/T4_delivery_round31_20261009.zip"
OUT="$REPO/$R31/unzip_verification"
LOG="$OUT/verification_log.txt"
SCRATCH="${TMPDIR:-/tmp}"
DEST="$(mktemp -d "$SCRATCH/t4_unzip_verify.XXXXXX")"
: > "$LOG"

run() {  # run <label> <command...>: log the command, its full output and exit code
  local label="$1"; shift
  {
    echo "=================================================================="
    echo "[$label] $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "cwd: $(pwd)"
    echo "\$ $*"
  } >> "$LOG"
  "$@" >> "$LOG" 2>&1
  local code=$?
  echo "exit_code: $code" >> "$LOG"
  echo "[$label] exit_code=$code"
  return 0
}

run "0a zip sha256" shasum -a 256 "$ZIP"
run "0b zip size and entry count" bash -c "ls -l '$ZIP'; unzip -Z1 '$ZIP' | grep -v '/\$' | wc -l"
run "0c unzip into a new empty directory" unzip -q "$ZIP" -d "$DEST"
cd "$DEST/T4_delivery" || exit 2
run "1-6 verify_package (sha256 per file, references + README commands, statistics, export, secrets incl. .env values, identity)" \
    python3 tools/verify_package.py --env "$REPO/.env" --out "$DEST/verify_package_result.json"
cp "$DEST/verify_package_result.json" "$OUT/verify_package_result.json"
run "README command 1 (as written)" python3 tools/verify_package.py
run "README command 2 (as written): offline statistics rebuild vs report" python3 tools/rebuild_stats.py
run "README command 3 (as written): credential pattern scan" python3 tools/scan_credentials.py
run "optional: regenerate the claim ledgers with the production code (repository at the run's code identity)" \
    python3 tools/verify_package.py --regenerate-ledgers --repo "$REPO" --out "$DEST/verify_regenerate_result.json"
cp "$DEST/verify_regenerate_result.json" "$OUT/verify_regenerate_result.json"
run "no __pycache__ or stray files were created by the checks" bash -c "find . -name __pycache__ -o -name '.DS_Store' | wc -l"
cd "$REPO" || exit 2
run "6b original runs and protected directories: before/after hashes" \
    python3 "$R31/T4_delivery/tools/snapshot_state.py" --out "$R31/hash_proof/state_after.json" --compare "$R31/hash_proof/state_before.json"
run "6c the original run directories equal the package copies byte for byte" bash -c "diff -r outputs/t4_runs/12591384-0b26-470d-a99d-a49c00be440b '$DEST/T4_delivery/runs/12591384-0b26-470d-a99d-a49c00be440b' && diff -r outputs/t4_runs/fa642639-8d93-4f9a-9de1-2c4d789eade8 '$DEST/T4_delivery/runs/fa642639-8d93-4f9a-9de1-2c4d789eade8' && echo identical"
echo "unzipped at: $DEST" >> "$LOG"
echo "log: $LOG"
