#!/usr/bin/env bash
# T4 round 34 (D1 fix) test runner, on the frozen final code. Each group runs under the Round 28 net_trap_plugin (any
# non-loopback connection raises and is counted). The code identity is recorded right before and after each group.
# Logs, junit XML, the exact command, times and exit code -> 03_tests/<group>.*
#
#   bash run_r34_tests.sh d1    # the new D1 contract tests + the adapter, source-linking, Gateway / version-identity, replay
#                               # registry and consumption-path tests that touch the changed surfaces
#   bash run_r34_tests.sh pin   # tests/structured_output_shadow/test_source_integrity.py -- recorded only: it already failed
#                               # before this round (pre-existing hash drift of three files), see 03_tests/source_integrity_pin_BEFORE.log
set -uo pipefail
GROUP="${1:-}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
R="$(cd "$HERE/.." && pwd)"
REPO_ROOT="$(cd "$HERE/../../../../.." && pwd)"
EVIDENCE="$R/03_tests"
TRAP="$REPO_ROOT/docs/audit_artifacts/round_source_linking_t0_t2/round28_t4_launch_protection_20261008/tools"
mkdir -p "$EVIDENCE"
cd "$REPO_ROOT"
PY="$REPO_ROOT/.venv/bin/python"
export PYTHONPATH="$TRAP${PYTHONPATH:+:$PYTHONPATH}"
export NET_TRAP_REPORT="$EVIDENCE/${GROUP}_net_trap.json"
unset COMQUTOR_DATABASE_URL COMQUTOR_ENV COMQUTOR_DATA_SANITY_ENABLED COMQUTOR_REQUIRE_DATABASE_NAME COMQUTOR_REQUIRE_DATABASE_DIALECT COMQUTOR_TEST_DATABASE_URL

identity() {
  "$PY" -c 'import sys; sys.path.insert(0,"."); from comqutor_alpha.run_environment import process_code_identity as p; d=p(); print(d["tracked_diff_sha256"], d["untracked_runtime_source_sha256"])'
}

D1_FILES=(
  tests/test_t4_round34_d1_adapter_citation_contract.py
  tests/test_t1_source_linking_pipeline.py tests/test_structured_output_adapter.py
  tests/test_structured_adapter_concurrency.py tests/test_week2_llm.py tests/test_week2_llm_semantic_runtime_integration.py
  tests/test_semantic_artifact_live_pipeline.py tests/test_t4_round32_not_sent_and_stage_disclosure.py tests/test_t3_joint_verification_driver.py
  tests/test_t4_round28_provider_stop.py tests/test_t4_phase_a_environment_and_metering.py tests/test_provider_health_diagnostics.py
  tests/test_evidence_stance_retry_fix.py
  tests/replay tests/llm_runtime
  tests/structured_output_shadow/test_shadow_exact_replay.py tests/structured_output_shadow/test_shadow_semantic_runtime.py
  tests/structured_output_shadow/test_phase1_master_global_ledger_prompt_version_collision.py tests/structured_output_shadow/test_live_shadow_integration.py
  tests/structured_output_shadow/test_stage_g_primary_authority_routing.py tests/structured_output_shadow/test_shadow_prompt.py
)
PIN_FILES=(tests/structured_output_shadow/test_source_integrity.py)

ID_BEFORE="$(identity)"
{ echo "group: $GROUP"; echo "started_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"; echo "code_identity_before (tracked untracked): $ID_BEFORE"; } > "$EVIDENCE/${GROUP}_command.txt"
case "$GROUP" in
  d1) FILES=("${D1_FILES[@]}") ;;
  pin) FILES=("${PIN_FILES[@]}") ;;
  *) echo "usage: run_r34_tests.sh d1|pin" >&2; exit 2 ;;
esac
CMD=("$PY" -m pytest -p net_trap_plugin -p no:cacheprovider -q -rfEs --junitxml="$EVIDENCE/${GROUP}_junit.xml" "${FILES[@]}")
echo "command: ${CMD[*]}" >> "$EVIDENCE/${GROUP}_command.txt"
"${CMD[@]}" > "$EVIDENCE/${GROUP}.log" 2>&1
CODE=$?
ID_AFTER="$(identity)"
{
  echo "finished_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "code_identity_after (tracked untracked): $ID_AFTER"
  echo "code_unchanged_during_group: $([[ "$ID_BEFORE" == "$ID_AFTER" ]] && echo yes || echo NO)"
  echo "exit_code: $CODE"
} >> "$EVIDENCE/${GROUP}_command.txt"
tail -3 "$EVIDENCE/${GROUP}.log"
echo "group=$GROUP exit=$CODE code_unchanged=$([[ "$ID_BEFORE" == "$ID_AFTER" ]] && echo yes || echo NO) net_trap=$(tr -d '\n ' < "$EVIDENCE/${GROUP}_net_trap.json" 2>/dev/null | head -c 160)"
exit $CODE
