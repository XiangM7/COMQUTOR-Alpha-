#!/usr/bin/env bash
# Round 25: the affected tests, under the outbound-network trap; writes log, exit code, JUnit and trap report into 05_driver/test_evidence/.
# usage (from the repository root): bash docs/audit_artifacts/round_source_linking_t0_t2/round25_t3_minimal_prep_20261008/tools/run_affected_tests.sh <label> [output dir]
set -u
LABEL="${1:-affected}"
PKG="docs/audit_artifacts/round_source_linking_t0_t2/round25_t3_minimal_prep_20261008"
OUT="${2:-$PKG/05_driver/test_evidence}"
mkdir -p "$OUT"
TESTS=(tests/test_t3_joint_sample_driver.py tests/test_t3_joint_verification_driver.py tests/test_t3_diagnostic_evaluation_driver.py)
echo "PYTHONPATH=$PKG/tools NET_TRAP_REPORT=$OUT/net_trap_$LABEL.json .venv/bin/python -m pytest -p net_trap_plugin -p no:cacheprovider ${TESTS[*]} -q --junitxml=$OUT/junit_$LABEL.xml" > "$OUT/command_$LABEL.txt"
PYTHONPATH="$PKG/tools" NET_TRAP_REPORT="$OUT/net_trap_$LABEL.json" .venv/bin/python -m pytest -p net_trap_plugin -p no:cacheprovider "${TESTS[@]}" -q --junitxml="$OUT/junit_$LABEL.xml" > "$OUT/pytest_$LABEL.log" 2>&1
CODE=$?
echo "$CODE" > "$OUT/exitcode_$LABEL.txt"
tail -3 "$OUT/pytest_$LABEL.log"
echo "exit code: $CODE"
cat "$OUT/net_trap_$LABEL.json"
exit "$CODE"
