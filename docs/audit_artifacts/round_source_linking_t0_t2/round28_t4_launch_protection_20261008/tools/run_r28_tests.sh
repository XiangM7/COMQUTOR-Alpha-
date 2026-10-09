#!/usr/bin/env bash
# T4 round 28 test runner (net_trap_plugin: every non-loopback connection raises and is counted). Logs, junit XML (every nodeid),
# the exact command and the exit code land in test_evidence/<group>.*
#   bash run_r28_tests.sh new        # this round's tests + round 27's environment/metering tests (same response/status code)
#   bash run_r28_tests.sh affected   # tests of the modules this round changed (guard/runner, gateway/builder, fallback mapping,
#                                    # research status / error mapping / export) -- NOT the whole 1067-test round-27 group
set -uo pipefail
GROUP="${1:-}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
R="$(cd "$HERE/.." && pwd)"
REPO_ROOT="$(cd "$HERE/../../../../.." && pwd)"
EVIDENCE="$R/test_evidence"
mkdir -p "$EVIDENCE"
cd "$REPO_ROOT"
PY="$REPO_ROOT/.venv/bin/python"
export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"
export NET_TRAP_REPORT="$EVIDENCE/${GROUP}_net_trap.json"
unset COMQUTOR_DATABASE_URL COMQUTOR_ENV COMQUTOR_DATA_SANITY_ENABLED COMQUTOR_REQUIRE_DATABASE_NAME COMQUTOR_REQUIRE_DATABASE_DIALECT COMQUTOR_TEST_DATABASE_URL
NEW_FILES=(
  tests/test_t4_round28_provider_stop.py
  tests/test_t4_phase_a_environment_and_metering.py
)
AFFECTED_FILES=(
  # research-agent guard and streaming runner
  tests/test_request_budget.py tests/test_tradingagents_progress_runner.py tests/test_tradingagents_usage_stats_callback.py
  tests/test_tradingagents_diagnostic_instrumentation.py tests/test_instrument_identity_timeout_hardening.py tests/test_live_research_final_closure.py
  # Week 2 gateway / builder (all three attempt loops, audit transport, profile)
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
  # fallback vocabularies (alpha / content support / stance)
  tests/test_alpha_mapper.py tests/test_alpha_mapper_llm_authority.py tests/test_alpha_classification_completion.py
  tests/test_content_support_llm.py tests/test_content_support_llm_multi_field_citation.py tests/test_content_support_llm_phase_c_batch_size_fix.py
  tests/test_content_support_llm_production_wiring.py tests/test_content_support_llm_v2_semantic_contract.py
  tests/test_evidence_stance_llm.py tests/test_evidence_stance_concurrency.py tests/test_evidence_stance_retry_fix.py
  # research status / error mapping / export / jobs
  tests/test_research_input_validation.py tests/test_research_progress.py tests/test_research_runs_api.py tests/test_research_runs_persistence.py
  tests/test_research_jobs.py tests/test_artifact_export_and_api.py tests/test_week3_security_hardening.py tests/test_week4_pipeline_api.py
)
case "$GROUP" in
  new) FILES=("${NEW_FILES[@]}") ;;
  affected) FILES=("${AFFECTED_FILES[@]}") ;;
  *) echo "usage: run_r28_tests.sh new|affected" >&2; exit 2 ;;
esac
CMD=("$PY" -m pytest -p net_trap_plugin -p no:cacheprovider -q -rfEs --junitxml="$EVIDENCE/${GROUP}_junit.xml" "${FILES[@]}")
{ echo "started_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"; echo "command: ${CMD[*]}"; } > "$EVIDENCE/${GROUP}_command.txt"
"${CMD[@]}" > "$EVIDENCE/${GROUP}.log" 2>&1
CODE=$?
{ echo "finished_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"; echo "pytest_exit_code: $CODE"; } >> "$EVIDENCE/${GROUP}_command.txt"
tail -3 "$EVIDENCE/${GROUP}.log"
echo "pytest_exit_code=$CODE net_trap=$(tr -d '\n ' < "$NET_TRAP_REPORT" 2>/dev/null | head -c 200)"
exit $CODE
