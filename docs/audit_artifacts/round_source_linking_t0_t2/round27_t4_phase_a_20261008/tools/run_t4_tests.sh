#!/usr/bin/env bash
# T4 Phase A test runner. Every group runs under net_trap_plugin (any non-loopback connection raises and is counted);
# logs, junit XML, the exact command and the exit code land in test_evidence/<group>.*
#
#   bash run_t4_tests.sh pg     # PostgreSQL integration group against comqutor_alpha_t4_pytest_test (never the 8000 database);
#                               # a skipped test FAILS the group (exit 3): PostgreSQL items are not closed by a skip
#   bash run_t4_tests.sh unit   # unit tests of the modules this phase changed + every test driving the research pipeline
set -uo pipefail
GROUP="${1:-}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
T4="$(cd "$HERE/.." && pwd)"
REPO_ROOT="$(cd "$HERE/../../../../.." && pwd)"
EVIDENCE="$T4/test_evidence"
mkdir -p "$EVIDENCE"
cd "$REPO_ROOT"
PY="$REPO_ROOT/.venv/bin/python"
export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"
export NET_TRAP_REPORT="$EVIDENCE/${GROUP}_net_trap.json"
unset COMQUTOR_DATABASE_URL COMQUTOR_ENV COMQUTOR_DATA_SANITY_ENABLED COMQUTOR_REQUIRE_DATABASE_NAME COMQUTOR_REQUIRE_DATABASE_DIALECT

PG_FILES=(
  tests/test_agent_outputs_postgres_integration.py
  tests/test_agent_outputs_source_linking_db_migration.py
  tests/test_content_support_reevaluation_postgres_integration.py
  tests/test_graph_persistence_postgres_integration.py
  tests/test_research_progress_postgres_integration.py
  tests/test_research_runs_postgres_integration.py
  tests/test_t1_market_source_fields_postgres_integration.py
  tests/test_w5_1b_postgres_integration.py
  tests/test_week4_postgres_persistence.py
  tests/test_t4_required_postgres_integration.py
)
UNIT_FILES=(
  # changed modules, directly
  tests/test_t4_phase_a_environment_and_metering.py
  tests/test_live_launcher_database_isolation.py
  tests/test_graph_persistence.py
  tests/test_api_system_routes.py tests/test_w5_1b_api.py tests/test_w5_1b_final_patch.py tests/test_deepseek_default_profile.py
  tests/test_week2_llm.py tests/test_week2_execution_profile.py tests/test_week2_llm_true_concurrent_audit.py
  tests/test_alpha_classifier_audit_concurrency_fix.py
  tests/test_llm_usage_stats.py tests/test_tradingagents_usage_stats_callback.py
  tests/test_tradingagents_output_writer.py tests/test_structured_output_adapter.py
  tests/test_artifact_export_and_api.py tests/test_artifact_bundle_audit.py tests/test_replay_identity_correction.py
  tests/test_alpha_classification_completion.py
  tests/test_classification_recovery_derived_run.py tests/test_direction_evaluation.py
  tests/test_recovery_real_path_gating.py tests/test_recovery_staged_executor.py tests/test_recovery_mid_batch_crash.py
  tests/test_recovery_downstream_zero_model_calls.py
  tests/test_t3_closeout_content_support_citation_and_ledger.py tests/test_t3_closeout_relation_and_opposition_consumption.py
  tests/test_t3_diagnostic_evaluation_driver.py tests/test_t3_joint_sample_driver.py tests/test_t3_joint_verification_driver.py
  tests/test_week3_security_hardening.py
  # research pipeline (routes_research: usage report written before the manifest; the fault-free "completed" rule)
  tests/test_content_support_llm_production_wiring.py tests/test_formal_acceptance_artifact_production_wiring.py
  tests/test_new_research_evidence_gate_production_wiring.py tests/test_evidence_gate_qualified_evidence_scenarios.py
  tests/test_t2_acceptance_engine_qualified_evidence_scenarios.py tests/test_evidence_stance_integration.py
  tests/test_a3_unclassified_findings_control.py tests/test_agent_outputs_persistence.py tests/test_alpha_memory_api_exposure.py
  tests/test_b3_entity_exposure_gated_states.py tests/test_data_sanity_api.py tests/test_graph_api.py
  tests/test_persisted_run_serveability.py tests/test_product_findings_end_to_end.py tests/test_research_input_validation.py
  tests/test_semantic_artifact_live_pipeline.py tests/test_week2_llm_semantic_runtime_integration.py
  tests/test_t1_cross_agent_reference_and_derived_calc.py tests/test_t1_financial_source_chain.py tests/test_t1_macro_source_chain.py
  tests/test_t1_market_data_source_linking.py tests/test_week1a_gate.py tests/test_week3_nvda_sanity.py tests/test_week3_qqq_sanity.py
  tests/test_week4_golden_closure.py tests/test_week4_nvda_conflict_sanity.py tests/test_week4_persistence.py tests/test_week4_pipeline_api.py
  tests/test_week4_qqq_conflict_sanity.py tests/test_evaluation_harness.py
)

case "$GROUP" in
  pg)
    export COMQUTOR_TEST_DATABASE_URL="$("$PY" "$HERE/create_t4_databases.py" --print-url-for comqutor_alpha_t4_pytest_test)"
    FILES=("${PG_FILES[@]}")
    ;;
  unit)
    unset COMQUTOR_TEST_DATABASE_URL
    FILES=("${UNIT_FILES[@]}")
    ;;
  *) echo "usage: run_t4_tests.sh pg|unit" >&2; exit 2 ;;
esac

CMD=("$PY" -m pytest -p net_trap_plugin -p no:cacheprovider -q -rs --junitxml="$EVIDENCE/${GROUP}_junit.xml" "${FILES[@]}")
{
  echo "started_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "database: $([[ "$GROUP" == pg ]] && echo "postgresql comqutor_alpha_t4_pytest_test (loopback 127.0.0.1:5433)" || echo "none (COMQUTOR_TEST_DATABASE_URL unset)")"
  echo "command: ${CMD[*]}"
} > "$EVIDENCE/${GROUP}_command.txt"
"${CMD[@]}" > "$EVIDENCE/${GROUP}.log" 2>&1
CODE=$?
SKIPPED="$("$PY" -c 'import sys, xml.etree.ElementTree as ET
root = ET.parse(sys.argv[1]).getroot()
suites = [root] if root.tag == "testsuite" else list(root)
print(sum(int(s.get("skipped", 0)) for s in suites))' "$EVIDENCE/${GROUP}_junit.xml" 2>/dev/null || echo "unknown")"
FINAL=$CODE
if [[ "$GROUP" == pg && "$SKIPPED" != "0" ]]; then
  FINAL=3
fi
{
  echo "finished_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "pytest_exit_code: $CODE"
  echo "skipped: $SKIPPED"
  echo "group_exit_code: $FINAL"
} >> "$EVIDENCE/${GROUP}_command.txt"
tail -3 "$EVIDENCE/${GROUP}.log"
echo "pytest_exit_code=$CODE skipped=$SKIPPED group_exit_code=$FINAL net_trap=$(cat "$NET_TRAP_REPORT" 2>/dev/null | head -c 300)"
exit $FINAL
