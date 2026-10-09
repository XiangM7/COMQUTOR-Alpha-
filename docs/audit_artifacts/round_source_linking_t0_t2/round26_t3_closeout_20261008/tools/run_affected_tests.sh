#!/usr/bin/env bash
# T3 closeout: the affected tests under the outbound-network trap. Writes the command, full log, exit code, JUnit XML and the trap report.
# usage (repository root): bash docs/audit_artifacts/round_source_linking_t0_t2/round26_t3_closeout_20261008/tools/run_affected_tests.sh <label> [output dir]
set -u
LABEL="${1:-affected}"
PKG="docs/audit_artifacts/round_source_linking_t0_t2/round26_t3_closeout_20261008"
OUT="${2:-$PKG/test_evidence}"
mkdir -p "$OUT"
TESTS=(
  # new in this closeout
  tests/test_t3_closeout_content_support_citation_and_ledger.py
  tests/test_week2_execution_profile.py
  tests/test_t3_closeout_relation_and_opposition_consumption.py
  # content support (validator, batch processor, wiring)
  tests/test_content_support_llm.py
  tests/test_content_support_llm_multi_field_citation.py
  tests/test_content_support_llm_phase_c_batch_size_fix.py
  tests/test_content_support_llm_production_wiring.py
  tests/test_content_support_llm_v2_semantic_contract.py
  tests/test_content_support_never_inflates_scoring.py
  tests/test_automated_content_support_verification.py
  # gateway, profile wiring, audit, concurrency
  tests/test_week2_llm.py
  tests/test_week2_llm_semantic_runtime_integration.py
  tests/test_week2_llm_true_concurrent_audit.py
  tests/test_week2_llm_markdown_fence_parsing.py
  tests/test_alpha_classifier_audit_concurrency_fix.py
  tests/test_evidence_stance_concurrency.py
  tests/test_structured_adapter_concurrency.py
  tests/test_structured_output_adapter.py
  tests/test_phase_c_script_transport_level_fixed_response.py
  tests/test_claim_identity_traceability.py
  # semantic ledger task registry and exact replay mirrors
  tests/llm_runtime
  tests/replay
  tests/test_replay_identity_correction.py
  tests/test_replay_pipeline.py
  tests/test_semantic_artifact_live_pipeline.py
  # consumers read but not changed: stance, selector, verified gate, completion metric
  tests/test_evidence_stance_llm.py
  tests/test_structure_integrity_evidence_fact_index.py
  tests/test_verified_evidence_gate.py
  tests/test_verified_evidence_gate_production_wiring.py
  tests/test_alpha_classification_completion.py
  # the T3 drivers (frozen, unchanged) and the frozen-hash pins that name changed files
  tests/test_t3_joint_sample_driver.py
  tests/test_t3_joint_verification_driver.py
  tests/test_t3_diagnostic_evaluation_driver.py
  tests/structured_output_shadow/test_source_integrity.py
  tests/structured_output_shadow/test_phase1b1_boundaries.py
)
echo "PYTHONPATH=$PKG/tools NET_TRAP_REPORT=$OUT/net_trap_$LABEL.json .venv/bin/python -m pytest -p net_trap_plugin -p no:cacheprovider ${TESTS[*]} -q -rfE --junitxml=$OUT/junit_$LABEL.xml" > "$OUT/command_$LABEL.txt"
PYTHONPATH="$PKG/tools" NET_TRAP_REPORT="$OUT/net_trap_$LABEL.json" .venv/bin/python -m pytest -p net_trap_plugin -p no:cacheprovider "${TESTS[@]}" -q -rfE --junitxml="$OUT/junit_$LABEL.xml" > "$OUT/pytest_$LABEL.log" 2>&1
CODE=$?
echo "$CODE" > "$OUT/exitcode_$LABEL.txt"
tail -40 "$OUT/pytest_$LABEL.log"
echo "exit code: $CODE"
cat "$OUT/net_trap_$LABEL.json"
exit "$CODE"
