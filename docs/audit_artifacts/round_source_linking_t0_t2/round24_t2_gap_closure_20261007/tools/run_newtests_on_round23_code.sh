#!/bin/bash
# Round 24: do the FINAL tests catch the defects the round fixed? Runs them against the Round 23 code.
#
# Builds a temporary tree outside the repository:
#   comqutor_alpha/ tradingagents/ scripts/ tests/   copied from the working tree (the FINAL tests),
#   then comqutor_alpha/ and scripts/ overlaid with the Round 23 versions of every file this round modified
#   (round23_state_of_changed_files/), and comqutor_alpha/regression/gold_contract_rules.py removed (it did not exist in Round 23);
#   outputs/ and docs/ are symlinks to the repository's (read only by the tests).
# Then runs the test files below with the network trap and writes command / log / exit code / JUnit / trap report into <out-dir>.
# Nothing in the repository is written.
#
# usage: bash tools/run_newtests_on_round23_code.sh <out-dir>   (run from anywhere; <out-dir> must not exist)
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"      # the Round 24 directory
REPO="$HERE"
while [ ! -d "$REPO/comqutor_alpha" ]; do REPO="$(dirname "$REPO")"; done
OUT="$1"
if [ -e "$OUT" ]; then echo "refusing: $OUT exists" >&2; exit 2; fi
mkdir -p "$OUT"
TREE="$(mktemp -d)"
cp -R "$REPO/comqutor_alpha" "$REPO/tradingagents" "$REPO/scripts" "$REPO/tests" "$TREE/"
find "$TREE" -name __pycache__ -type d -prune -exec rm -rf {} +
ln -s "$REPO/outputs" "$TREE/outputs"
ln -s "$REPO/docs" "$TREE/docs"
cp "$REPO/pyproject.toml" "$TREE/"
cp -R "$HERE/round23_state_of_changed_files/comqutor_alpha/." "$TREE/comqutor_alpha/"
cp -R "$HERE/round23_state_of_changed_files/scripts/." "$TREE/scripts/"
rm -f "$TREE/comqutor_alpha/regression/gold_contract_rules.py"

TESTS="tests/test_t2_conflict_semantics_real_b2.py tests/test_t2_gold_contract_alpha_rules.py tests/test_t2_rule_config_errors.py tests/test_acceptance_engine.py tests/test_formal_acceptance_report.py tests/test_open_review_ledger.py tests/test_formal_acceptance_artifact_production_wiring.py tests/test_no_gold_label_import_in_research_path.py tests/test_t2_acceptance_engine_qualified_evidence_scenarios.py"
echo "cd <temporary tree: Round 23 comqutor_alpha/ and scripts/ + the FINAL tests/> && PYTHONPATH=<tree>:<tools dir> NET_TRAP_REPORT=net_trap.json PYTHONDONTWRITEBYTECODE=1 python -m pytest -p net_trap_plugin $TESTS -q -p no:cacheprovider --continue-on-collection-errors --junitxml=newtests_on_round23_code.junit.xml" > "$OUT/newtests_on_round23_code.command.txt"
cd "$TREE" || exit 1
PYTHONPATH="$TREE:$HERE/tools" NET_TRAP_REPORT="$OUT/net_trap.json" PYTHONDONTWRITEBYTECODE=1 "$REPO/.venv/bin/python" -m pytest -p net_trap_plugin $TESTS -q -p no:cacheprovider --continue-on-collection-errors --junitxml="$OUT/newtests_on_round23_code.junit.xml" > "$OUT/newtests_on_round23_code.log" 2>&1
echo "exit=$?" > "$OUT/newtests_on_round23_code.exitcode"
rm -rf "$TREE"
cat "$OUT/newtests_on_round23_code.exitcode"
