#!/usr/bin/env bash
# Round 32: reproduce the two Round 28 regression failures on reconstructed code snapshots and on the live working tree.
# Every run: exact command, full output, exit code -> 01_regressions/<label>.log (pytest node ids from Round 28's JUnit).
#   bash tools/reproduce_regressions.sh <label> <tree: head|fresh_code|worktree>
# head       = git HEAD 7a9aefa (committed code; neither the Round 9 comment nor the Round 26 registration exists there)
# fresh_code = HEAD + the Round 28 freeze tracked diff (sha256 1b53b921...) + untracked runtime sources (38ef636f...) =
#              the code both NVDA Fresh runs ran on, rebuilt from code_snapshot/ in a scratch directory
# worktree   = the repository working tree as it is now
set -uo pipefail
LABEL="$1"; TREE="$2"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
R="$(cd "$HERE/.." && pwd)"
REPO="$(cd "$HERE/../../../../.." && pwd)"
SNAP="$REPO/docs/audit_artifacts/round_source_linking_t0_t2/round28_t4_launch_protection_20261008/04_refreeze/code_snapshot"
TRAP="$REPO/docs/audit_artifacts/round_source_linking_t0_t2/round28_t4_launch_protection_20261008/tools"
OUT="$R/01_regressions"; mkdir -p "$OUT"
LOG="$OUT/$LABEL.log"
NODES=(
  "tests/test_structured_adapter_concurrency.py::test_structured_adapter_concurrency_touches_no_alpha_mapping_code"
  "tests/structured_output_shadow/test_shadow_semantic_runtime.py::test_structured_claim_shadow_is_additive_to_semantic_tasks"
)
SCRATCH="${TMPDIR:-/tmp}"
case "$TREE" in
  worktree) ROOT="$REPO" ;;
  head|fresh_code)
    ROOT="$(mktemp -d "$SCRATCH/r32_${TREE}.XXXXXX")"
    git -C "$REPO" archive HEAD comqutor_alpha tests tradingagents pyproject.toml | tar -x -C "$ROOT"
    if [ "$TREE" = fresh_code ]; then
      (cd "$ROOT" && git apply --include='comqutor_alpha/*' --include='tests/*' --include='tradingagents/*' --include='pyproject.toml' "$SNAP/tracked_diff_vs_HEAD.diff")
      tar -xzf "$SNAP/untracked_runtime_source.tar.gz" -C "$ROOT"
      # the code snapshot holds runtime sources only; the test tree (incl. untracked helpers such as tests/_network_guard.py)
      # is copied from the working tree, whose test files were last modified before the Round 28 test run (mtimes logged)
      rsync -a --delete --exclude '__pycache__' "$REPO/tests/" "$ROOT/tests/"
    fi ;;
  *) echo "tree must be head|fresh_code|worktree" >&2; exit 2 ;;
esac
{
  echo "label: $LABEL"
  echo "tree: $TREE  root: $ROOT"
  echo "started_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "tracked diff file sha256 (fresh_code input): $(shasum -a 256 "$SNAP/tracked_diff_vs_HEAD.diff" | cut -c1-64)"
  echo "sha256 structured_output_adapter.py: $(shasum -a 256 "$ROOT/comqutor_alpha/structure_engine/structured_output_adapter.py" | cut -c1-64)"
  echo "sha256 llm_runtime/contracts.py:      $(shasum -a 256 "$ROOT/comqutor_alpha/llm_runtime/contracts.py" | cut -c1-64)"
  echo "sha256 test_structured_adapter_concurrency.py: $(shasum -a 256 "$ROOT/tests/test_structured_adapter_concurrency.py" | cut -c1-64)"
  echo "sha256 test_shadow_semantic_runtime.py:        $(shasum -a 256 "$ROOT/tests/structured_output_shadow/test_shadow_semantic_runtime.py" | cut -c1-64)"
  echo "grep 'alpha_mapper' in structured_output_adapter.py:"; grep -n "alpha_mapper" "$ROOT/comqutor_alpha/structure_engine/structured_output_adapter.py" || echo "  (none)"
  echo "grep content_support_verification in SEMANTIC_TASKS block of contracts.py:"; grep -n '"content_support_verification",' "$ROOT/comqutor_alpha/llm_runtime/contracts.py" || echo "  (none)"
  echo "mtimes (UTC) of the two test files and conftests in this tree:"
  for f in tests/test_structured_adapter_concurrency.py tests/structured_output_shadow/test_shadow_semantic_runtime.py tests/conftest.py tests/structured_output_shadow/conftest.py tests/_network_guard.py; do
    [ -f "$ROOT/$f" ] && echo "  $f $(TZ=UTC stat -f '%Sm' -t '%Y-%m-%dT%H:%M:%SZ' "$ROOT/$f") sha256=$(shasum -a 256 "$ROOT/$f" | cut -c1-16)"
  done
  echo "python: $("$REPO/.venv/bin/python" --version 2>&1)  pytest: $("$REPO/.venv/bin/python" -m pytest --version 2>&1 | head -1)"
  echo "\$ cd $ROOT && PYTHONPATH=$ROOT:$TRAP NET_TRAP_REPORT=$OUT/$LABEL.net_trap.json $REPO/.venv/bin/python -m pytest -p net_trap_plugin -p no:cacheprovider -q -rfEs ${NODES[*]}"
} > "$LOG"
(cd "$ROOT" && env -u COMQUTOR_DATABASE_URL -u COMQUTOR_TEST_DATABASE_URL PYTHONPATH="$ROOT:$TRAP" NET_TRAP_REPORT="$OUT/$LABEL.net_trap.json" \
  "$REPO/.venv/bin/python" -m pytest -p net_trap_plugin -p no:cacheprovider -q -rfEs "${NODES[@]}") >> "$LOG" 2>&1
CODE=$?
{ echo "exit_code: $CODE"; echo "finished_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"; } >> "$LOG"
echo "$LABEL exit_code=$CODE"; grep -E "passed|failed" "$LOG" | tail -1
exit 0
