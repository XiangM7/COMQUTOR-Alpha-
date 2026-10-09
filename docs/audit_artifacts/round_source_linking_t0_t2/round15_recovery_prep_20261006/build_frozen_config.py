#!/usr/bin/env python3
"""Writes frozen_recovery_config.json: everything the real AMD classification recovery is frozen to, in one
machine-readable file, computed from the current tree with ZERO network and ZERO Provider calls.

Also re-proves, against TODAY's code and taxonomy, that the request a recovery would send for the two reused
claims is byte-identical to what the original run really sent (so "model / prompt / taxonomy / original
classification input frozen" is checked now, not inherited from an earlier round).
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))
SCRIPT = REPO / "docs/audit_artifacts/round_source_linking_t0_t2/round12_alpha_classifier_audit_fix_20261006/recover_alpha_classification.py"

spec = importlib.util.spec_from_file_location("recover_alpha_classification_cfg", SCRIPT)
recover = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recover)

from comqutor_alpha.alpha_library.alpha_loader import TAXONOMY_PATH
from comqutor_alpha.llm_runtime.canonical_json import sha256_canonical_json
from comqutor_alpha.structure_engine import alpha_mapper
from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway
import hashlib

scope = recover.compute_recovery_scope()
plan = recover.build_recovery_plan(scope)
binding = recover.verify_valid_results_binding(scope)

original_dir = recover.ORIGINAL_DIR
structured = {r["claim_id"]: r for r in json.loads((original_dir / "structured_agent_outputs.json").read_text())["records"]}
calls = [json.loads(line) for line in (original_dir / "llm_semantic_calls.jsonl").read_text().splitlines() if line.strip()]
alpha_calls = [c for c in calls if c["task"] == "alpha_classifier"]
taxonomy_block = alpha_mapper._alpha_taxonomy_request_block(alpha_mapper.load_alpha_taxonomy())


def rebuilt_input_sha(record):
    return sha256_canonical_json({
        "claim": str(record.get("claim") or ""),
        "evidence": str(record.get("evidence") or ""),
        "ticker": str(record.get("ticker") or ""),
        "factors": alpha_mapper._record_factors(record),
        "direction": alpha_mapper.normalize_direction(record.get("direction")),
        "alpha_taxonomy": taxonomy_block,
    })


identity_checks = []
for call in alpha_calls:
    twins = [r for r in structured.values() if str(r.get("claim") or "") == call["input_payload"]["claim"]]
    identity_checks.append({
        "original_call_id": call["call_id"],
        "original_input_sha256": call["input_sha256"],
        "rebuilt_input_sha256_by_current_code": sorted({rebuilt_input_sha(r) for r in twins}),
        "matches_original": all(rebuilt_input_sha(r) == call["input_sha256"] for r in twins) and bool(twins),
    })
prompt_now = Week2LLMGateway.prompt_identity_sha256("alpha_classifier")
prompt_then = sorted({c["prompt_sha256"] for c in alpha_calls})

config = {
    "schema_version": "comqutor.frozen_recovery_config.v1",
    "purpose": "real Alpha-classification recovery of the c904d4cc claims whose alpha_classifier call was lost to the audit-concurrency defect",
    "zero_provider_calls_made_producing_this_file": True,
    "original_run_id": recover.ORIGINAL_RUN_ID,
    "original_run_access": "read-only; file hashes recorded before derivation and compared after",
    "scope": {
        "total_claims": scope["total_claims"],
        "reused_valid_none_claim_ids": scope["valid_llm_results_claim_ids"],
        "to_recover_count": scope["needs_recovery_count"],
        "unexpected_buckets": scope["other_buckets"],
        "reused_results_bound_to_a_successful_matching_call": all(row["result_consistent_with_call"] for row in binding),
    },
    "request_budget": {
        "hard_cap_provider_requests": recover.HARD_REQUEST_CAP,
        "counting_rule": "every request that reaches the audited transport counts, whether it later succeeds or fails; a resume counts requests already audited in the execution directory",
        "independent_of_original_run_budget": True,
        "expected_real_sends": "955 to 973 (identical-input claims may be served by the semantic cache; a cache hit never reserves budget)",
        "research_agent_calls": 0,
        "data_fetch_or_search_calls": 0,
        "content_verification_calls": 0,
        "direction_task_calls": 0,
    },
    "request_config": {
        "model": recover.EXPECTED_MODEL,
        "provider": "deepseek",
        "client_level_retries": 0,
        "client_level_retries_source": "hardcoded 0 by build_server_week2_llm_gateway; also verified on the wire per batch (x-stainless-retry-count)",
        "application_level_retries": 0,
        "application_level_retries_source": "COMQUTOR_WEEK2_LLM_MAX_RETRIES=0 exported by the launcher; preflight refuses anything else",
        "timeout_seconds": recover.EXPECTED_TIMEOUT_SECONDS,
        "timeout_source": "COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS=45 exported by the launcher (NOT the .env value); preflight checks the gateway, and every batch's audited request is checked for x-stainless-read-timeout=45.0",
        "concurrency": recover.FROZEN_CONCURRENCY,
        "request_response_audit": "on (mounted by the executor)",
        "per_task_model_override": "none",
        "request_shape": {
            "url": recover.EXPECTED_REQUEST_URL,
            "body_keys": sorted(recover.EXPECTED_REQUEST_BODY_KEYS),
            "stream": False,
            "note": "the original run's shape (no max_tokens, no thinking/reasoning field); verified on the wire for every audited request, and these env vars must be absent from the launch shell: " + ", ".join(recover.FORBIDDEN_REAL_ENV),
        },
    },
    "frozen_identities_rechecked_against_current_code": {
        "prompt_sha256_now": prompt_now,
        "prompt_sha256_in_original_real_calls": prompt_then,
        "prompt_unchanged": prompt_then == [prompt_now],
        "taxonomy_file_sha256_now": hashlib.sha256(Path(TAXONOMY_PATH).read_bytes()).hexdigest(),
        "request_input_identity_for_the_reused_claims": identity_checks,
        "all_request_inputs_unchanged": all(c["matches_original"] for c in identity_checks),
    },
    "order": [{"stage": s["name"], "claims": len(s["claim_ids"]), "batch_size": s["batch_size"], "gate": s["gate"]} for s in plan],
    "order_note": "the 19 analytical SUPPORTS claims go first purely as an ORDER; the scope stays all 973. The first 4 are the real parallel-configuration gate: all four must be protocol-complete (valid selection or valid NONE) with the right claim identity on the wire, else the run stops before anything else is scheduled.",
    "classification_outcome_rules": {
        "valid_none": "a COMPLETED classification; never retried to try to obtain a match",
        "failed_response": "saved as failed; never auto-resent",
        "unknown_inflight": "request audited but no response saved; never auto-resent; reported as unknown",
    },
    "task_isolation": {
        "allowed_tasks": ["alpha_classifier"],
        "mechanism": "TaskAllowlistGateway refuses any other task before it is forwarded; the executor also stops if a batch's audited requests contain another task",
        "direction_task": "evidence_stance_classifier is not sent; its needed requests, independent budget and reuse check are written to evidence_stance_followup_manifest.json and need their own authorization",
    },
    "stop_rules": {
        "local_audit_failure": "the request/response audit could not be persisted",
        "auth_failure": "a batch response was HTTP 401/403",
        "task_isolation_violation": "a second task was attempted or audited",
        "identity_failure": "an audited request carries no claim id",
        "config_failure": "an audited request's model, read-timeout or retry-count differs from the frozen values",
        "call_cap_would_be_exceeded": "audited-so-far + gateway count + next batch > 973",
        "stage_a_gate_failed": "any of the first 4 claims is not protocol-complete with correct identity (evaluated from the audit log, so it also holds on resume)",
        "semantics": "a stop prevents any NEW batch from being scheduled; the batch already in flight finishes and each of its calls is individually finalized -- in-flight calls are never claimed to be cancelled",
    },
    "checkpoints": {
        "per_batch": ["checkpoint_recovery.json", "recovery_match_records.jsonl (full per-claim match records)", "the request/response audit log"],
        "crash_recovery": "claim state is reconciled from the audit log, so a crash between a response and its batch checkpoint loses nothing; a claim audited but never saved is rebuilt offline from the audited decision",
        "resume": "launch_real_recovery.sh with EXECUTION_ID and RECOVERY_MAX_CALLS = 973 minus requests already audited",
    },
    "derived_run": {
        "execution_id_format": "recovery-<UTC stamp>-<8 hex>",
        "based_on_run_id": recover.ORIGINAL_RUN_ID,
        "finalized_only_when": "no stop rule fired",
        "mapping_artifact": "recovery_lineage.json",
    },
    "authorization": {
        "env_var": recover.REAL_EXECUTION_ACK_ENV,
        "required_value": recover.expected_real_execution_ack(plan),
        "frozen_plan_sha256": recover.frozen_plan_sha256(plan),
        "set_by_the_assistant": False,
        "note": "the value is derived from the frozen plan; changing the plan, cap, model, timeout, concurrency or task list changes it",
    },
    "required_environment": {**recover.REQUIRED_REAL_ENV,
                             "COMQUTOR_WEEK2_LLM_MAX_CALLS": "<= 973 minus requests already audited",
                             "COMQUTOR_DATABASE_URL": "exported; database name must end in _test",
                             "COMQUTOR_REQUIRE_DATABASE_NAME": "exported; equals the database name",
                             "DEEPSEEK_API_KEY": "exported (never printed)"},
    "launcher": "docs/audit_artifacts/round_source_linking_t0_t2/round15_recovery_prep_20261006/launch_real_recovery.sh",
}

out = HERE / "frozen_recovery_config.json"
out.write_text(json.dumps(config, indent=2) + "\n")
print(f"wrote {out}")
print("prompt unchanged:", config["frozen_identities_rechecked_against_current_code"]["prompt_unchanged"])
print("request inputs unchanged:", config["frozen_identities_rechecked_against_current_code"]["all_request_inputs_unchanged"])
print("reused results bound:", config["scope"]["reused_results_bound_to_a_successful_matching_call"])
