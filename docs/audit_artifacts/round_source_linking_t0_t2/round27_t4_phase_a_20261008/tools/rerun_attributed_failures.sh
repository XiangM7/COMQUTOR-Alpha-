#!/usr/bin/env bash
# T4 Phase A: reruns of the unit-group failures attributed to the environment, each with its exact command and exit code.
#   launcher tests: the same tests with the launcher's live port moved off the occupied 8000 (the live service must not be stopped)
#   job-timing tests: the three tests alone, outside the 22-minute group run
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
E="$HERE/../test_evidence"
cd "$HERE/../../../../.."
unset COMQUTOR_DATABASE_URL COMQUTOR_TEST_DATABASE_URL COMQUTOR_ENV COMQUTOR_DATA_SANITY_ENABLED
run() {
  local log="$1"; shift
  { echo "started_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"; echo "command: $*"; } > "$E/$log"
  env "$@" >> "$E/$log" 2>&1
  local code=$?
  echo "exit_code: $code" >> "$E/$log"
  echo "$log exit=$code :: $(grep -E 'passed|failed' "$E/$log" | tail -1)"
}
run rerun_launcher_free_port.log COMQUTOR_LIVE_API_PORT=8099 .venv/bin/python -m pytest -p no:cacheprovider -q tests/test_live_launcher_database_isolation.py
run rerun_job_timing_isolated.log .venv/bin/python -m pytest -p no:cacheprovider -q \
  tests/test_w5_1b_api.py::test_scenario_e_read_only_status_unaffected_by_live_semantic_readiness \
  tests/test_w5_1b_api.py::test_status_and_history_never_expose_fingerprint_or_config \
  tests/test_w5_1b_final_patch.py::test_status_and_history_and_graph_and_conflicts_all_use_same_output_root
