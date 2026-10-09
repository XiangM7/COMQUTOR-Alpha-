#!/usr/bin/env bash
# T4 round 32 test runner, on the FROZEN final code. Every pytest group runs under net_trap_plugin (any non-loopback connection
# raises and is counted). The code identity is recorded immediately before and after each group (it must not change while a
# group runs). Logs, junit XML (every nodeid), the exact command, times, exit code -> 04_tests/<group>.*
#
#   bash run_r32_tests.sh new        # this round's tests + Round 28/27 environment, metering and stop tests + the two fixed tests
#   bash run_r32_tests.sh affected   # Round 28's 53-file affected group + the files touching this round's changed surfaces
#   bash run_r32_tests.sh pg         # all PostgreSQL integration files against comqutor_alpha_t4_r32_pytest_test; a skip FAILS it
#   bash run_r32_tests.sh replay     # test_replay_conflict_does_not_get_run_id_mismatch alone, verbose
#   bash run_r32_tests.sh frontend   # ESLint (src e2e), typecheck, vitest of the touched components/pages
set -uo pipefail
GROUP="${1:-}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
R="$(cd "$HERE/.." && pwd)"
REPO_ROOT="$(cd "$HERE/../../../../.." && pwd)"
EVIDENCE="$R/04_tests"
TRAP="$REPO_ROOT/docs/audit_artifacts/round_source_linking_t0_t2/round28_t4_launch_protection_20261008/tools"
mkdir -p "$EVIDENCE"
cd "$REPO_ROOT"
PY="$REPO_ROOT/.venv/bin/python"
export PYTHONPATH="$TRAP${PYTHONPATH:+:$PYTHONPATH}"
export NET_TRAP_REPORT="$EVIDENCE/${GROUP}_net_trap.json"
unset COMQUTOR_DATABASE_URL COMQUTOR_ENV COMQUTOR_DATA_SANITY_ENABLED COMQUTOR_REQUIRE_DATABASE_NAME COMQUTOR_REQUIRE_DATABASE_DIALECT COMQUTOR_TEST_DATABASE_URL

identity() {
  "$PY" -c 'import json,sys; sys.path.insert(0,"."); from comqutor_alpha.run_environment import process_code_identity as p; d=p(); print(d["tracked_diff_sha256"], d["untracked_runtime_source_sha256"])'
}

NEW_FILES=(
  tests/test_t4_round32_not_sent_and_stage_disclosure.py
  tests/test_t4_round28_provider_stop.py
  tests/test_t4_phase_a_environment_and_metering.py
  "tests/test_structured_adapter_concurrency.py::test_structured_adapter_concurrency_touches_no_alpha_mapping_code"
  "tests/structured_output_shadow/test_shadow_semantic_runtime.py::test_structured_claim_shadow_is_additive_to_semantic_tasks"
)
AFFECTED_FILES=(
  # Round 28's affected group (53 files), unchanged
  tests/test_request_budget.py tests/test_tradingagents_progress_runner.py tests/test_tradingagents_usage_stats_callback.py
  tests/test_tradingagents_diagnostic_instrumentation.py tests/test_instrument_identity_timeout_hardening.py tests/test_live_research_final_closure.py
  tests/test_week2_llm.py tests/test_week2_execution_profile.py tests/test_week2_llm_true_concurrent_audit.py tests/test_week2_llm_markdown_fence_parsing.py
  tests/test_week2_llm_semantic_runtime_integration.py tests/test_alpha_classifier_audit_concurrency_fix.py tests/test_claim_identity_traceability.py
  tests/test_phase_c_script_transport_level_fixed_response.py tests/test_structured_adapter_concurrency.py tests/test_structured_output_adapter.py
  tests/test_semantic_artifact_live_pipeline.py tests/test_llm_usage_stats.py tests/llm_runtime/test_evidence_stance_classifier_registration.py
  tests/structured_output_shadow/test_shadow_task_execution_policy.py tests/structured_output_shadow/test_shadow_provider_invoker.py
  tests/structured_output_shadow/test_shadow_provider_invoker_v2.py tests/structured_output_shadow/test_shadow_provider_invoker_v3.py
  tests/structured_output_shadow/test_shadow_provider_invoker_v4.py tests/structured_output_shadow/test_shadow_semantic_runtime.py
  tests/structured_output_shadow/test_live_shadow_integration.py
  tests/test_classification_recovery_derived_run.py tests/test_direction_evaluation.py tests/test_recovery_real_path_gating.py
  tests/test_recovery_staged_executor.py tests/test_recovery_mid_batch_crash.py
  tests/test_t3_closeout_content_support_citation_and_ledger.py tests/test_t3_diagnostic_evaluation_driver.py tests/test_t3_joint_verification_driver.py
  tests/test_alpha_mapper.py tests/test_alpha_mapper_llm_authority.py tests/test_alpha_classification_completion.py
  tests/test_content_support_llm.py tests/test_content_support_llm_multi_field_citation.py tests/test_content_support_llm_phase_c_batch_size_fix.py
  tests/test_content_support_llm_production_wiring.py tests/test_content_support_llm_v2_semantic_contract.py
  tests/test_evidence_stance_llm.py tests/test_evidence_stance_concurrency.py tests/test_evidence_stance_retry_fix.py
  tests/test_research_input_validation.py tests/test_research_progress.py tests/test_research_runs_api.py tests/test_research_runs_persistence.py
  tests/test_research_jobs.py tests/test_artifact_export_and_api.py tests/test_week3_security_hardening.py tests/test_week4_pipeline_api.py
  # Round 32 additions: tests touching the research response, artifact allowlist/manifest/finalization, stance/content-support
  # fallback vocabularies, evidence trace, replay, and the new tests
  tests/replay/test_capture_artifacts_replay_compat.py tests/replay/test_evidence_stance_binding.py tests/test_a3_unclassified_findings_control.py
  tests/test_alpha_memory_api_exposure.py tests/test_alpha_memory_history_reader.py tests/test_canonical_relation_prompt_injection.py
  tests/test_content_support_reevaluation_export_roundtrip.py tests/test_data_sanity_api.py tests/test_evidence_stance_integration.py
  tests/test_persisted_run_serveability.py tests/test_recovery_downstream_zero_model_calls.py tests/test_regression_report_v3.py
  tests/test_replay_identity_correction.py tests/test_run_audit_v2.py tests/test_t1_closeout_capture_artifacts.py
  tests/test_t1_closure_grounding_dependency_trace.py tests/test_t4_phase_a_environment_and_metering.py tests/test_t4_round28_provider_stop.py
  tests/test_week1a_gate.py tests/test_t4_round32_not_sent_and_stage_disclosure.py
)
PG_FILES=(
  tests/test_agent_outputs_postgres_integration.py tests/test_agent_outputs_source_linking_db_migration.py
  tests/test_content_support_reevaluation_postgres_integration.py tests/test_content_support_reevaluation_export_roundtrip.py
  tests/test_graph_persistence_postgres_integration.py tests/test_research_progress_postgres_integration.py
  tests/test_research_runs_postgres_integration.py tests/test_t1_market_source_fields_postgres_integration.py
  tests/test_w5_1b_postgres_integration.py tests/test_week4_postgres_persistence.py tests/test_t4_required_postgres_integration.py
)
REPLAY_NODE="tests/test_artifact_export_and_api.py::test_replay_conflict_does_not_get_run_id_mismatch"

ID_BEFORE="$(identity)"
{ echo "group: $GROUP"; echo "started_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"; echo "code_identity_before (tracked untracked): $ID_BEFORE"; } > "$EVIDENCE/${GROUP}_command.txt"

case "$GROUP" in
  new|affected|replay|pg)
    case "$GROUP" in
      new) FILES=("${NEW_FILES[@]}"); EXTRA=(-q) ;;
      affected) FILES=("${AFFECTED_FILES[@]}"); EXTRA=(-q) ;;
      replay) FILES=("$REPLAY_NODE"); EXTRA=(-vv) ;;
      pg)
        export COMQUTOR_TEST_DATABASE_URL="$("$PY" "$HERE/create_r32_databases.py" --print-url-for comqutor_alpha_t4_r32_pytest_test)"
        FILES=("${PG_FILES[@]}"); EXTRA=(-q)
        echo "database: postgresql comqutor_alpha_t4_r32_pytest_test (loopback 127.0.0.1:5433); required: a skipped test fails the group" >> "$EVIDENCE/${GROUP}_command.txt" ;;
    esac
    CMD=("$PY" -m pytest -p net_trap_plugin -p no:cacheprovider "${EXTRA[@]}" -rfEs --junitxml="$EVIDENCE/${GROUP}_junit.xml" "${FILES[@]}")
    echo "command: ${CMD[*]}" >> "$EVIDENCE/${GROUP}_command.txt"
    "${CMD[@]}" > "$EVIDENCE/${GROUP}.log" 2>&1
    CODE=$?
    SKIPPED="$("$PY" -c 'import sys, xml.etree.ElementTree as ET
root = ET.parse(sys.argv[1]).getroot()
suites = [root] if root.tag == "testsuite" else list(root)
print(sum(int(s.get("skipped", 0)) for s in suites))' "$EVIDENCE/${GROUP}_junit.xml" 2>/dev/null || echo unknown)"
    FINAL=$CODE
    [[ "$GROUP" == pg && "$SKIPPED" != "0" ]] && FINAL=3
    ;;
  frontend)
    unset NET_TRAP_REPORT
    : > "$EVIDENCE/frontend.log"
    FINAL=0
    for step in "npx eslint src e2e" "npm run typecheck" "npx vitest run src/components/StageDisclosurePanel.test.tsx src/pages/ResearchRunPage.test.tsx src/api/adapters.test.ts src/App.test.tsx"; do
      { echo "=== \$ cd frontend && $step"; echo "started_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"; } >> "$EVIDENCE/frontend.log"
      (cd frontend && bash -c "$step") >> "$EVIDENCE/frontend.log" 2>&1
      STEP_CODE=$?
      echo "exit_code: $STEP_CODE" >> "$EVIDENCE/frontend.log"
      echo "step: $step exit_code: $STEP_CODE" >> "$EVIDENCE/${GROUP}_command.txt"
      [[ $STEP_CODE -ne 0 ]] && FINAL=$STEP_CODE
    done
    CODE=$FINAL; SKIPPED=n/a
    ;;
  *) echo "usage: run_r32_tests.sh new|affected|pg|replay|frontend" >&2; exit 2 ;;
esac

ID_AFTER="$(identity)"
{
  echo "finished_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "code_identity_after (tracked untracked): $ID_AFTER"
  echo "code_unchanged_during_group: $([[ "$ID_BEFORE" == "$ID_AFTER" ]] && echo yes || echo NO)"
  echo "exit_code: $CODE"
  echo "skipped: $SKIPPED"
  echo "group_exit_code: $FINAL"
} >> "$EVIDENCE/${GROUP}_command.txt"
tail -3 "$EVIDENCE/${GROUP}.log" 2>/dev/null
echo "group=$GROUP exit=$CODE skipped=$SKIPPED group_exit=$FINAL code_unchanged=$([[ "$ID_BEFORE" == "$ID_AFTER" ]] && echo yes || echo NO) net_trap=$(tr -d '\n ' < "$EVIDENCE/${GROUP}_net_trap.json" 2>/dev/null | head -c 160)"
exit $FINAL
