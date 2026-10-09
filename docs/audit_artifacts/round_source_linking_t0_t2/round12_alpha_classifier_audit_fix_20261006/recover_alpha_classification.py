#!/usr/bin/env python3
"""Recovery script for the c904d4cc Alpha-classification defect.

Default: DRY RUN. Prints the exact scope, config, and budget request; makes
ZERO Provider calls. Real execution requires --execute AND is out of this
round's own authorization (this round only runs --dry-run and
--fake-transport-test).

Calls ONLY real production functions (map_structured_records,
build_server_week2_llm_gateway) -- never reimplements classification,
scoring, or eligibility logic. Reuses the 973-of-975 defect this round's own
audit report (01_root_cause_fix_and_recovery_plan.md) already localized.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

# What the operator's SHELL exported, snapshotted before anything imports the repo (whose import runs
# load_dotenv and can add values from .env). The real run judges its authorization and its frozen
# configuration against this snapshot, so a value that merely came from .env can never satisfy either.
_LAUNCH_ENV = dict(os.environ)

ORIGINAL_RUN_ID = "c904d4cc-dc09-495c-aec5-b056979948e1"
OUTPUT_ROOT = (REPO_ROOT / "outputs" / "runs").resolve()
ORIGINAL_DIR = OUTPUT_ROOT / ORIGINAL_RUN_ID

# Hashes captured directly from the original run's own real files, confirmed
# unchanged as of this script's own writing (see this round's own report,
# section 八). Any drift means the frozen input changed since this script
# was authored -- refuse rather than silently proceed on a different input.
EXPECTED_HASHES = {
    "structured_agent_outputs.json": None,  # filled in by --seed-only on first real use
    "alpha_matches.json": None,
    "source_registry.json": None,
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute_recovery_scope() -> dict:
    """Zero-cost: reads the original run's own real, frozen alpha_matches.json
    and classifies every claim into exactly one bucket. Never calls any
    Provider. This is the authoritative scope computation both --dry-run and
    --execute must use identically."""
    alpha_matches = json.loads((ORIGINAL_DIR / "alpha_matches.json").read_text())
    matches = alpha_matches["matches"]

    valid_llm_results: list[str] = []
    needs_recovery: list[str] = []
    other: dict[str, list[str]] = {}

    for m in matches:
        claim_id = m["claim_id"]
        method = m.get("alpha_match_method")
        fallback = m.get("alpha_match_fallback_reason")
        if method == "llm" and fallback is None:
            valid_llm_results.append(claim_id)
        elif method == "llm_unavailable" and fallback == "provider_error":
            needs_recovery.append(claim_id)
        else:
            other.setdefault(f"{method}:{fallback}", []).append(claim_id)

    return {
        "total_claims": len(matches),
        "valid_llm_results_count": len(valid_llm_results),
        "valid_llm_results_claim_ids": valid_llm_results,
        "needs_recovery_count": len(needs_recovery),
        "needs_recovery_claim_ids": needs_recovery,
        "other_buckets": {k: len(v) for k, v in other.items()},
        "other_claim_ids": other,
    }


def load_checkpoint(checkpoint_path: Path) -> dict:
    if checkpoint_path.exists():
        return json.loads(checkpoint_path.read_text())
    return {"completed_claim_ids": {}, "created_at": datetime.now(timezone.utc).isoformat()}


def save_checkpoint(checkpoint_path: Path, checkpoint: dict) -> None:
    """Atomic-ish write (write to temp, then rename) so a crash mid-write
    never corrupts the last known-good checkpoint. Checkpoint save failure
    must stop scheduling new requests (per instruction) -- callers check
    this function's own success before proceeding to the next claim/batch."""
    tmp = checkpoint_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(checkpoint, indent=2))
    tmp.replace(checkpoint_path)


DRY_RUN_OUTPUT_DIR = REPO_ROOT / "docs" / "audit_artifacts" / "round_source_linking_t0_t2" / "round14_recovery_closure_20261006"


def run_dry_run(new_run_id: str) -> None:
    scope = compute_recovery_scope()
    print("=" * 70)
    print(f"RECOVERY DRY RUN for based_on_run_id={ORIGINAL_RUN_ID}")
    print(f"New execution id (proposed): {new_run_id}")
    print("=" * 70)
    print(f"Total claims in original run: {scope['total_claims']}")
    print(f"Already-valid LLM results (frozen, reused as-is): {scope['valid_llm_results_count']}")
    print(f"Claims needing real re-classification: {scope['needs_recovery_count']}")
    if scope["other_buckets"]:
        print(f"OTHER / UNEXPECTED buckets (not accounted for by the known defect, "
              f"review before proceeding): {scope['other_buckets']}")
    else:
        print("No unexpected buckets -- every claim is accounted for by exactly "
              "the known valid-result / needs-recovery split.")
    print()
    print("Proposed independent budget request for this recovery (NOT inherited "
          "from the original run's own 1500 cap, per instruction):")
    print(f"  alpha_classifier real requests needed: {scope['needs_recovery_count']}")
    print(f"  Research Agent layer: 0 (no TradingAgents re-run)")
    print(f"  Downstream (structure_graph/activation/exposure/conflict/formal_acceptance): "
          f"0 new Provider calls (deterministic, real production functions, reused as-is)")
    print()
    print("Client-side and application-level retries: 0 (both layers), matching the "
          "original run's own frozen config.")
    print()
    plan = build_recovery_plan(scope)
    dedup = request_input_dedup_report(scope)
    binding = verify_valid_results_binding(scope)
    print("Frozen send order (all inside the single 973 cap; no extra requests):")
    for stage in plan:
        print(f"  {stage['name']}: {len(stage['claim_ids'])} claims, batch_size={stage['batch_size']}, gate={stage['gate']}")
    print(f"Real sends: between {dedup['min_real_sends_if_cache_always_hits']} and {dedup['max_real_sends_if_cache_never_hits']} "
          f"({dedup['extra_claims_collapsible_by_cache']} extra identical-input claims may be served from cache; "
          f"cache hits never reserve call budget and are not new request allowance). Hard cap: {HARD_REQUEST_CAP}.")
    for row in binding:
        print(f"Reused valid result {row['claim_id'].split(':',1)[1]}: semantic call found={row['semantic_call_found']}, "
              f"consistent={row['result_consistent_with_call']}, exact-text twins to reclassify={len(row['exact_text_twins_inside_the_973_to_be_reclassified'])}")
    print("Evidence-stance task (a SECOND model task, applied only to claims that end up with a matched Alpha): "
          "NOT included in the 973 cap, NOT sent by this plan, and structurally unreachable from it: every call goes "
          "through a task allowlist ['alpha_classifier'] that refuses anything else before it is forwarded. After "
          "classification the run writes evidence_stance_followup_manifest.json (the needed requests, an independent "
          "budget, and a reuse check) and stops; sending them needs its own authorization.")
    print()
    from comqutor_alpha.classification_recovery import RECOVERY_EXECUTION_TYPE

    plan_sha = frozen_plan_sha256(plan)
    ack = expected_real_execution_ack(plan)
    derived_run = {
        "execution_id_format": "recovery-<UTC stamp>-<8 hex>",
        "based_on_run_id": ORIGINAL_RUN_ID,
        "execution_type": RECOVERY_EXECUTION_TYPE,
        "original_run_directory": "read-only (file hashes recorded before and compared after; nothing is appended into it)",
        "copied_with_run_id_rebased": ["raw_agent_outputs.json", "structured_agent_outputs.json", "extracted_structures.json",
                                       "source_registry.json", "market_data_snapshot.json", "data_sanity.json"],
        "assembled": ["alpha_matches.json (975 claims: 2 reused original results + recovered + any kept original failure)"],
        "identity_rule": "claim_id / agent_output_id / source_agent_output_id / text / evidence / source links / verification bindings preserved verbatim; only run_id fields are rebased",
        "mapping_artifact": "recovery_lineage.json (claim_identity_map: one entry per original claim)",
        "recomputed_by_production_pipeline_with_zero_model_calls": [
            "structure_graph", "alpha_activations", "entity_alpha_exposures", "conflicts", "evidence_facts", "summary",
            "run_audit", "artifact_manifest", "formal_acceptance"],
        "database": "research_runs row (execution_mode='recovery', unique fingerprint) + agent_outputs rows under the new id",
        "finalized_only_if": "no stop rule fired; a stopped run keeps its checkpoint/audit for --execution-id resume",
    }
    print("Derived run (never edits the original):")
    for key, value in derived_run.items():
        print(f"  {key}: {value}")
    print()
    print(f"Frozen plan sha256: {plan_sha}")
    print(f"Real execution is refused unless the operator's shell exports {REAL_EXECUTION_ACK_ENV}={ack}")
    print("and the environment matches: " + ", ".join(f"{k}={v}" for k, v in REQUIRED_REAL_ENV.items())
          + ", COMQUTOR_WEEK2_LLM_MAX_CALLS<=remaining cap, isolated *_test database + COMQUTOR_REQUIRE_DATABASE_NAME.")
    print()
    print("ZERO Provider calls made by this dry run.")
    print("=" * 70)

    ROUND15_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ROUND15_DIR / f"recovery_dry_run_report_{new_run_id}.json"
    out_path.write_text(json.dumps({
        "scope": scope,
        "plan": [{**stage, "claim_count": len(stage["claim_ids"])} for stage in plan],
        "request_input_dedup": dedup,
        "reused_valid_result_binding": binding,
        "hard_request_cap": HARD_REQUEST_CAP,
        "retries": {"client_level": 0, "application_level": 0},
        "frozen_plan_sha256": plan_sha,
        "real_execution_acknowledgement_required": {"env_var": REAL_EXECUTION_ACK_ENV, "value": ack},
        "required_environment": {**REQUIRED_REAL_ENV, "COMQUTOR_WEEK2_LLM_MAX_CALLS": f"<= {HARD_REQUEST_CAP} minus requests already audited"},
        "allowed_tasks": ["alpha_classifier"],
        "derived_run": derived_run,
    }, indent=2))
    print(f"Full dry-run report written to: {out_path}")


def run_fake_transport_test(new_run_id: str) -> None:
    """Exercises the REAL recovery call path (real gateway construction,
    real map_structured_records, real checkpoint read/write) with only the
    bottom-most httpx transport faked -- proves the recovery MECHANISM
    works, never a stand-in for real AMD classification quality."""
    import httpx

    from comqutor_alpha.structure_engine.alpha_mapper import map_structured_records
    from comqutor_alpha.structure_engine.week2_llm import build_server_week2_llm_gateway
    from comqutor_alpha.llm_runtime.cache import InMemoryLLMResponseCache
    from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession

    scope = compute_recovery_scope()
    needs_recovery_ids = set(scope["needs_recovery_claim_ids"])
    structured = json.loads((ORIGINAL_DIR / "structured_agent_outputs.json").read_text())
    records_to_recover = [r for r in structured["records"] if r["claim_id"] in needs_recovery_ids]
    print(f"[fake-transport-test] records scoped for recovery: {len(records_to_recover)}")

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "id": "chatcmpl-fake", "object": "chat.completion", "created": 0,
                    "model": "deepseek-v4-flash",
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": '{"decision": "none", "selected_alpha_id": null}'}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                },
            )

        os.environ["COMQUTOR_WEEK2_LLM_ENABLED"] = "1"
        os.environ["COMQUTOR_WEEK2_LLM_PROVIDER"] = "deepseek"
        os.environ["COMQUTOR_WEEK2_LLM_MODEL"] = "deepseek-v4-flash"
        os.environ["COMQUTOR_WEEK2_LLM_MAX_RETRIES"] = "0"
        os.environ["COMQUTOR_WEEK2_LLM_MAX_CALLS"] = str(len(records_to_recover) + 5)
        os.environ["DEEPSEEK_API_KEY"] = "fixed-test-key-not-real"

        gateway = build_server_week2_llm_gateway(
            new_run_id, tmp_path,
            enable_request_response_audit=True,
            _base_transport_for_testing=httpx.MockTransport(handler),
        )
        assert gateway is not None
        (tmp_path / new_run_id).mkdir(exist_ok=True)
        semantic_runtime = SemanticRuntimeSession(
            run_id=new_run_id, output_directory=str(tmp_path / new_run_id),
            execution_mode="live", provider=gateway.provider, model=gateway.model_name,
            cache=InMemoryLLMResponseCache(),
        )
        gateway.attach_semantic_runtime(semantic_runtime)

        checkpoint_path = tmp_path / "checkpoint.json"
        checkpoint = load_checkpoint(checkpoint_path)

        BATCH_SIZE = 10
        sample = records_to_recover[:30]  # a real but bounded sample for this fake-transport proof
        results_all = []
        for i in range(0, len(sample), BATCH_SIZE):
            batch = sample[i : i + BATCH_SIZE]
            batch = [r for r in batch if r["claim_id"] not in checkpoint["completed_claim_ids"]]
            if not batch:
                continue
            results = map_structured_records(
                batch, classifier_enabled=True, llm_gateway=gateway, concurrency=4,
            )
            for r in results:
                checkpoint["completed_claim_ids"][r["claim_id"]] = {
                    "alpha_match_method": r.get("alpha_match_method"),
                    "matched_alpha": r.get("matched_alpha"),
                    "fallback_reason": r.get("alpha_match_fallback_reason"),
                }
            try:
                save_checkpoint(checkpoint_path, checkpoint)
            except Exception as exc:
                print(f"CHECKPOINT SAVE FAILED: {exc} -- stopping, no further requests scheduled.")
                return
            results_all.extend(results)
            print(f"[fake-transport-test] batch {i // BATCH_SIZE + 1}: "
                  f"{len(results)} claims processed, checkpoint saved ({len(checkpoint['completed_claim_ids'])} total).")

        real_successes = sum(1 for r in results_all if r.get("alpha_match_method") == "llm")
        print(f"[fake-transport-test] {real_successes}/{len(results_all)} got a real, "
              f"audited classification via the fixed recovery path (fake transport, zero real cost).")

        req_audit = tmp_path / new_run_id / "error_logs" / "week2_llm_provider_request_audit.jsonl"
        if req_audit.exists():
            n = len(req_audit.read_text().splitlines())
            print(f"[fake-transport-test] real request-audit entries written: {n}")

        print("[fake-transport-test] re-running the script against the SAME checkpoint "
              "to confirm already-completed claims are skipped, not re-sent:")
        remaining_before = len(sample) - len(checkpoint["completed_claim_ids"])
        skip_count = sum(1 for r in sample if r["claim_id"] in checkpoint["completed_claim_ids"])
        print(f"  {skip_count} of {len(sample)} would be skipped on a restart; "
              f"{remaining_before} still outstanding.")


# ---------------------------------------------------------------------------
# 2026-10-06 (round 14, section 5): fake-HTTP artifacts must never become real
# results. Enforced, not merely conventional:
#   * a fake-HTTP runner refuses to write anywhere under outputs/runs/ and
#     drops a marker file into its directory;
#   * every checkpoint carries an "origin"; resuming with a different origin
#     than the one that created it is refused;
#   * a REAL-origin run refuses a directory that holds the fake marker or any
#     fake-origin checkpoint.
# ---------------------------------------------------------------------------

FAKE_HTTP_MARKER_FILENAME = "FAKE_HTTP_TEST_ARTIFACTS.marker"
CHECKPOINT_ORIGIN_FAKE = "fake_http_test"
CHECKPOINT_ORIGIN_REAL = "real"


def assert_not_inside_real_runs_dir(path: Path) -> None:
    resolved = Path(path).resolve()
    try:
        resolved.relative_to(OUTPUT_ROOT)
    except ValueError:
        return
    raise RuntimeError(
        f"refusing to use {resolved}: a fake-HTTP test run must never write under the real runs "
        f"directory {OUTPUT_ROOT}"
    )


def mark_fake_http_directory(path: Path) -> None:
    assert_not_inside_real_runs_dir(path)
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    (path / FAKE_HTTP_MARKER_FILENAME).write_text(
        "Everything in this directory was produced with a FAKE httpx transport (zero real Provider "
        "calls). Nothing here is a real classification result and none of it may be merged into, "
        "resumed from, or cited as a real recovery of any run.\n"
    )


def assert_directory_holds_no_fake_http_artifacts(path: Path) -> None:
    path = Path(path)
    if (path / FAKE_HTTP_MARKER_FILENAME).exists():
        raise RuntimeError(f"{path} is marked as a fake-HTTP test directory; refusing to use it for a real run")
    for checkpoint_file in path.glob("checkpoint*.json"):
        try:
            origin = json.loads(checkpoint_file.read_text()).get("origin")
        except (OSError, ValueError):
            continue
        if origin == CHECKPOINT_ORIGIN_FAKE:
            raise RuntimeError(f"{checkpoint_file} is a fake-HTTP checkpoint; refusing to resume it as a real run")


def _parse_alpha_classifier_decision(response_audit_record: dict) -> dict | None:
    """Returns the decoded {"decision", "selected_alpha_id"} object if, and
    only if, the real audited response is a genuine HTTP 200 carrying a
    valid alpha_classifier decision -- the SAME shape/rules alpha_mapper's
    own validate_response enforces. Returns None for anything else (non-200,
    malformed JSON, missing/extra fields, an unrecognized decision value) --
    the caller must treat None as "not a valid success", never guess."""
    if response_audit_record.get("status_code") != 200:
        return None
    try:
        body = json.loads(response_audit_record["body"])
        content = json.loads(body["choices"][0]["message"]["content"])
    except Exception:
        return None
    if not isinstance(content, dict) or set(content) != {"decision", "selected_alpha_id"}:
        return None
    decision = str(content.get("decision") or "").strip().lower()
    selected_alpha_id = content.get("selected_alpha_id")
    if decision == "none":
        return content if selected_alpha_id in (None, "") else None
    if decision == "select":
        return content if selected_alpha_id else None
    return None


def reconcile_claim_states_from_audit_log(run_output_root: Path, run_id: str) -> dict[str, dict]:
    """2026-10-06 (round 14, section 5): the authoritative, crash-safe
    source of "was this claim's real classification request actually sent,
    and did it actually get a real, valid response" -- read DIRECTLY from
    the real request/response audit JSONL (using the round-14 claim_ids
    field, now populated on both), independent of the coarser per-BATCH
    checkpoint, which only gets written after an entire batch's
    map_structured_records call returns. A process that stops mid-batch --
    after some of that batch's real HTTP round-trips already completed and
    were individually audited, but before the checkpoint for the whole
    batch was saved -- would otherwise have its already-completed claims
    incorrectly re-sent on resume, since the checkpoint alone has no record
    of them yet. Reconciling against the real audit log closes that gap.

    Returns, for every claim_id that appears in the request-audit log at
    least once, one of:
      {"state": "success", "attempt_id": ..., "decision": {...}} --
        a genuinely completed, reusable classification (including a valid
        NONE decision, which is complete, not pending).
      {"state": "failed", "attempt_id": ...} --
        a request+response pair exists, but the response was not a valid
        classification (non-200, malformed, or an invalid decision value).
        Terminal under the frozen 0-retry rule -- never auto-retried here,
        never silently treated as success.
      {"state": "unknown_inflight", "attempt_id": ...} --
        a request was audited (so it may genuinely have been sent to the
        real Provider) but NO matching response was ever saved -- the
        process stopped between send and response-save. The real Provider
        may or may not have processed and billed it; this script can never
        know which from local state alone. NEVER automatically retried.
    A claim_id with more than one request-audit record (should not happen
    under the frozen 0-retry, checkpoint-skip design, but never assumed) is
    resolved using its LATEST attempt_id, and the full list is attached
    under the returned dict's own "__multi_attempt_warnings__" key for the
    caller to surface rather than silently pick one and move on."""
    from comqutor_alpha.structure_engine.week2_llm import (
        PROVIDER_REQUEST_AUDIT_ARTIFACT_PATH,
        PROVIDER_RESPONSE_AUDIT_ARTIFACT_PATH,
    )

    req_path = run_output_root / run_id / PROVIDER_REQUEST_AUDIT_ARTIFACT_PATH
    resp_path = run_output_root / run_id / PROVIDER_RESPONSE_AUDIT_ARTIFACT_PATH

    def _read(path: Path) -> list[dict]:
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    claim_to_attempts: dict[str, list[str]] = {}
    for rec in _read(req_path):
        attempt_id = rec["attempt_id"]
        for claim_id in rec.get("claim_ids") or []:
            claim_to_attempts.setdefault(claim_id, []).append(attempt_id)

    responses_by_attempt = {rec["attempt_id"]: rec for rec in _read(resp_path)}

    def _attempt_ordinal(attempt_id: str) -> int:
        try:
            return int(attempt_id.rsplit(":", 1)[-1])
        except (ValueError, IndexError):
            return -1

    states: dict[str, dict] = {}
    multi_attempt_warnings: dict[str, list[str]] = {}
    for claim_id, attempt_ids in claim_to_attempts.items():
        if len(attempt_ids) > 1:
            multi_attempt_warnings[claim_id] = sorted(attempt_ids)
        latest_attempt = max(attempt_ids, key=_attempt_ordinal)
        response_record = responses_by_attempt.get(latest_attempt)
        if response_record is None:
            states[claim_id] = {"state": "unknown_inflight", "attempt_id": latest_attempt}
            continue
        decision = _parse_alpha_classifier_decision(response_record)
        if decision is not None:
            states[claim_id] = {"state": "success", "attempt_id": latest_attempt, "decision": decision}
        else:
            states[claim_id] = {"state": "failed", "attempt_id": latest_attempt}

    if multi_attempt_warnings:
        states["__multi_attempt_warnings__"] = multi_attempt_warnings
    return states


def run_full_fake_transport_recovery(new_run_id: str, *, simulate_crash_after_batches: int | None = None) -> dict:
    """2026-10-06 (round 13, scenario 8): scales the fake-transport proof
    from a 30-claim sample to the REAL, FULL 973-claim needs_recovery set,
    using genuine concurrency=4 (the real production default), and merges
    the result with the 2 already-valid claims into a complete 975-entry
    final structure -- proving the recovery mechanism (not just the audit
    identity fix in isolation) scales to the real frozen defect's full size.

    ``simulate_crash_after_batches``: when set, raises a RuntimeError right
    after that many batches have been processed and checkpointed, so a
    SECOND real call to this function (same checkpoint_path) can prove
    resume-from-checkpoint correctness under genuine concurrency: no claim
    already checkpointed is ever re-sent, and the run still reaches full
    completion. The checkpoint path is returned to the caller either way.
    """
    import httpx

    from comqutor_alpha.structure_engine.alpha_mapper import map_structured_records
    from comqutor_alpha.structure_engine.week2_llm import build_server_week2_llm_gateway
    from comqutor_alpha.llm_runtime.cache import InMemoryLLMResponseCache
    from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession

    scope = compute_recovery_scope()
    needs_recovery_ids = set(scope["needs_recovery_claim_ids"])
    structured = json.loads((ORIGINAL_DIR / "structured_agent_outputs.json").read_text())
    records_to_recover = [r for r in structured["records"] if r["claim_id"] in needs_recovery_ids]
    assert len(records_to_recover) == scope["needs_recovery_count"], (
        f"structured_agent_outputs.json is missing records for some needs_recovery claim_ids: "
        f"found {len(records_to_recover)}, expected {scope['needs_recovery_count']}"
    )

    tmp_path = Path(os.environ["COMQUTOR_RECOVERY_FULL_TEST_DIR"])
    mark_fake_http_directory(tmp_path)

    # 2026-10-06: the real send-identity record for "was this claim sent,
    # and how many times" is the REAL request-audit JSONL itself (its
    # claim_ids field comes straight from the payload dict _extract_
    # claim_ids reads -- the authoritative mechanism, already proven
    # correct by test_week2_llm_true_concurrent_audit.py). map_structured_
    # records' own alpha_classifier prompt embeds the claim's EVIDENCE TEXT,
    # not its claim_id string, so reconstructing claim_id from prompt text
    # in this handler would be a second, fragile, duplicate-text-prone
    # re-implementation of what the audit log already proves -- read the
    # real audit log in the driver script instead of guessing here.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-fake", "object": "chat.completion", "created": 0,
                "model": "deepseek-v4-flash",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": '{"decision": "none", "selected_alpha_id": null}'}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    os.environ["COMQUTOR_WEEK2_LLM_ENABLED"] = "1"
    os.environ["COMQUTOR_WEEK2_LLM_PROVIDER"] = "deepseek"
    os.environ["COMQUTOR_WEEK2_LLM_MODEL"] = "deepseek-v4-flash"
    os.environ["COMQUTOR_WEEK2_LLM_MAX_RETRIES"] = "0"
    os.environ["COMQUTOR_WEEK2_LLM_MAX_CALLS"] = str(len(records_to_recover) + 10)
    os.environ["DEEPSEEK_API_KEY"] = "fixed-test-key-not-real"

    gateway = build_server_week2_llm_gateway(
        new_run_id, tmp_path,
        enable_request_response_audit=True,
        _base_transport_for_testing=httpx.MockTransport(handler),
    )
    assert gateway is not None
    (tmp_path / new_run_id).mkdir(exist_ok=True)
    semantic_runtime = SemanticRuntimeSession(
        run_id=new_run_id, output_directory=str(tmp_path / new_run_id),
        execution_mode="live", provider=gateway.provider, model=gateway.model_name,
        cache=InMemoryLLMResponseCache(),
    )
    gateway.attach_semantic_runtime(semantic_runtime)

    checkpoint_path = tmp_path / "checkpoint_full.json"
    checkpoint = load_checkpoint(checkpoint_path)
    checkpoint["origin"] = CHECKPOINT_ORIGIN_FAKE

    # 2026-10-06 (round 14, section 5): reconcile against the REAL audit log
    # BEFORE trusting the (possibly stale, possibly mid-batch-crashed)
    # checkpoint alone. A "success" claim the checkpoint doesn't know about
    # yet is recovered into it here (never re-sent); "unknown_inflight" and
    # "failed" claims are excluded from this pass's sends entirely -- never
    # auto-resent, never silently upgraded.
    reconciled = reconcile_claim_states_from_audit_log(tmp_path, new_run_id)
    unknown_claim_ids: set[str] = set()
    failed_claim_ids: set[str] = set()
    recovered_from_audit_log = 0
    for claim_id, info in reconciled.items():
        if claim_id == "__multi_attempt_warnings__":
            print(f"[full-recovery] WARNING: multiple request-audit attempts found for "
                  f"{len(info)} claim_id(s) -- investigate before trusting reconciliation: {info}")
            continue
        if info["state"] == "success":
            if claim_id not in checkpoint["completed_claim_ids"]:
                checkpoint["completed_claim_ids"][claim_id] = {
                    "alpha_match_method": "llm",
                    "matched_alpha": info["decision"].get("selected_alpha_id"),
                    "fallback_reason": None,
                    "recovered_from_audit_log": True,
                }
                recovered_from_audit_log += 1
        elif info["state"] == "unknown_inflight":
            unknown_claim_ids.add(claim_id)
        elif info["state"] == "failed":
            failed_claim_ids.add(claim_id)
    if recovered_from_audit_log:
        save_checkpoint(checkpoint_path, checkpoint)
        print(f"[full-recovery] recovered {recovered_from_audit_log} claim(s) directly from the "
              "real audit log that the checkpoint alone did not yet reflect (mid-batch-crash recovery).")
    if unknown_claim_ids:
        print(f"[full-recovery] {len(unknown_claim_ids)} claim(s) are unknown_inflight "
              f"(request sent, no response ever saved) -- excluded from auto-resend: "
              f"{sorted(unknown_claim_ids)[:10]}")
    if failed_claim_ids:
        print(f"[full-recovery] {len(failed_claim_ids)} claim(s) failed in a prior attempt within "
              f"this recovery run -- excluded from auto-resend this pass: {sorted(failed_claim_ids)[:10]}")

    # 2026-10-06: an independent, cache-insensitive log of exactly which
    # claim_ids were ever SUBMITTED to map_structured_records (not how many
    # real transport sends resulted -- the Gateway's own semantic cache
    # legitimately collapses genuine duplicate-content claims to fewer real
    # sends, which is correct caching behavior, not a resume-correctness
    # signal). A real file, so it accumulates across the in-process
    # RuntimeError a simulated crash raises between phase 1 and phase 2.
    batches_submitted_path = tmp_path / "batches_submitted.jsonl"

    BATCH_SIZE = 25  # genuine concurrency=4 within each batch's own map_structured_records call
    batches_processed_this_call = 0
    for i in range(0, len(records_to_recover), BATCH_SIZE):
        batch = [
            r for r in records_to_recover[i : i + BATCH_SIZE]
            if r["claim_id"] not in checkpoint["completed_claim_ids"]
            and r["claim_id"] not in unknown_claim_ids
            and r["claim_id"] not in failed_claim_ids
        ]
        if not batch:
            continue
        with open(batches_submitted_path, "a") as f:
            f.write(json.dumps({"claim_ids": [r["claim_id"] for r in batch]}) + "\n")
        results = map_structured_records(
            batch, classifier_enabled=True, llm_gateway=gateway, concurrency=4,
        )
        for r in results:
            checkpoint["completed_claim_ids"][r["claim_id"]] = {
                "alpha_match_method": r.get("alpha_match_method"),
                "matched_alpha": r.get("matched_alpha"),
                "fallback_reason": r.get("alpha_match_fallback_reason"),
            }
        save_checkpoint(checkpoint_path, checkpoint)
        batches_processed_this_call += 1
        print(f"[full-recovery] batch {i // BATCH_SIZE + 1}: {len(results)} claims processed, "
              f"checkpoint now has {len(checkpoint['completed_claim_ids'])}/{len(records_to_recover)}.")
        if (
            simulate_crash_after_batches is not None
            and batches_processed_this_call >= simulate_crash_after_batches
        ):
            raise RuntimeError(
                f"SIMULATED CRASH after {batches_processed_this_call} batches "
                f"({len(checkpoint['completed_claim_ids'])}/{len(records_to_recover)} checkpointed) "
                "-- this is intentional, proving the checkpoint survives an abrupt stop."
            )

    return {
        "checkpoint_path": str(checkpoint_path),
        "tmp_path": str(tmp_path),
        "new_run_id": new_run_id,
        "request_audit_path": str(tmp_path / new_run_id / "error_logs" / "week2_llm_provider_request_audit.jsonl"),
        "needs_recovery_count": len(records_to_recover),
        "completed_count": len(checkpoint["completed_claim_ids"]),
        "recovered_from_audit_log_count": recovered_from_audit_log,
        "unknown_inflight_claim_ids": sorted(unknown_claim_ids),
        "failed_claim_ids": sorted(failed_claim_ids),
        "valid_llm_results_claim_ids": scope["valid_llm_results_claim_ids"],
    }


# ---------------------------------------------------------------------------
# 2026-10-06 (round 14, section 7): frozen recovery plan, input/identity
# verification, and the staged executor with hard stop rules.
#
# Nothing below sends anything by itself. run_staged_recovery() is the single
# executor both the fake-transport tests and a FUTURE, separately-authorized
# real run would use; the real entry point (--execute) stays hard-blocked in
# __main__ and is not unblocked by anything in this block.
# ---------------------------------------------------------------------------

NINETEEN_PATH = Path(__file__).resolve().parent / "19_analytical_supports_claim_list.json"
STAGE_A_SIZE = 4
STAGE_C_BATCH_SIZE = 25
HARD_REQUEST_CAP = 973
EXPECTED_MODEL = "deepseek-v4-flash"
EXPECTED_TIMEOUT_SECONDS = 45.0
AUTH_FAILURE_STATUS_CODES = frozenset({401, 403})


def load_nineteen_claim_ids() -> list[str]:
    payload = json.loads(NINETEEN_PATH.read_text())
    return [item["claim_id"] for item in payload["claims"]]


def build_recovery_plan(scope: dict | None = None) -> list[dict]:
    """The frozen send order: the fixed 19 analytical SUPPORTS claims first,
    in the existing list's own order; of those, the first 4 form the real
    parallel-configuration gate (counted inside the 973 cap, not extra);
    then the other 15; then the remaining 954 in frozen alpha_matches order.
    Pure function of the frozen inputs -- no I/O beyond reading them."""
    scope = scope or compute_recovery_scope()
    needs = list(scope["needs_recovery_claim_ids"])
    nineteen = load_nineteen_claim_ids()
    assert len(nineteen) == 19 and len(set(nineteen)) == 19, "the fixed analytical-SUPPORTS list must be exactly 19 distinct claims"
    missing = [cid for cid in nineteen if cid not in set(needs)]
    assert not missing, f"analytical-SUPPORTS claims not in the needs-recovery set: {missing}"
    nineteen_set = set(nineteen)
    rest = [cid for cid in needs if cid not in nineteen_set]
    stages = [
        {"name": "stage_a_parallel_config_check", "claim_ids": nineteen[:STAGE_A_SIZE],
         "batch_size": STAGE_A_SIZE, "gate": "all_must_be_protocol_complete_with_correct_identity_else_stop"},
        {"name": "stage_b_remaining_analytical_supports", "claim_ids": nineteen[STAGE_A_SIZE:],
         "batch_size": 19 - STAGE_A_SIZE, "gate": None},
        {"name": "stage_c_remaining_claims", "claim_ids": rest,
         "batch_size": STAGE_C_BATCH_SIZE, "gate": None},
    ]
    total = sum(len(stage["claim_ids"]) for stage in stages)
    assert total == scope["needs_recovery_count"] == HARD_REQUEST_CAP, (total, scope["needs_recovery_count"])
    all_ids = [cid for stage in stages for cid in stage["claim_ids"]]
    assert len(set(all_ids)) == total, "a claim appears in more than one stage"
    return stages


def request_input_dedup_report(scope: dict | None = None) -> dict:
    """Explains 973 claims vs the number of REAL sends a run can make. The
    Gateway's semantic cache is keyed on the exact request input, so claims
    with byte-identical request inputs collapse to one real send. Counted
    from the frozen records with today's own payload-building code (whose
    output was separately proven identical to the original run's recorded
    input hashes). A cache hit never reserves Gateway call budget; the
    973 cap stays the ceiling either way, because two identical-input claims
    dispatched concurrently can both miss the cache."""
    from collections import Counter

    from comqutor_alpha.llm_runtime.canonical_json import sha256_canonical_json
    from comqutor_alpha.structure_engine import alpha_mapper

    scope = scope or compute_recovery_scope()
    taxonomy_block = alpha_mapper._alpha_taxonomy_request_block(alpha_mapper.load_alpha_taxonomy())
    structured = json.loads((ORIGINAL_DIR / "structured_agent_outputs.json").read_text())
    records = {r["claim_id"]: r for r in structured["records"]}

    def request_hash(record: dict) -> str:
        return sha256_canonical_json({
            "claim": str(record.get("claim") or ""),
            "evidence": str(record.get("evidence") or ""),
            "ticker": str(record.get("ticker") or ""),
            "factors": alpha_mapper._record_factors(record),
            "direction": alpha_mapper.normalize_direction(record.get("direction")),
            "alpha_taxonomy": taxonomy_block,
        })

    counts = Counter(request_hash(records[cid]) for cid in scope["needs_recovery_claim_ids"])
    duplicate_groups = {h: n for h, n in counts.items() if n > 1}
    return {
        "claims_needing_recovery": scope["needs_recovery_count"],
        "unique_request_inputs": len(counts),
        "duplicate_groups": len(duplicate_groups),
        "duplicate_group_size_histogram": {str(size): cnt for size, cnt in sorted(Counter(duplicate_groups.values()).items())},
        "extra_claims_collapsible_by_cache": sum(n - 1 for n in duplicate_groups.values()),
        "min_real_sends_if_cache_always_hits": len(counts),
        "max_real_sends_if_cache_never_hits": scope["needs_recovery_count"],
        "hard_request_cap": HARD_REQUEST_CAP,
        "terminology_note": (
            "The earlier '16 duplicates' counted duplicate GROUPS (14 pairs + 2 triples = 16 groups), "
            "not claims; those groups contain 18 EXTRA claims (973 - 955 = 18)."
        ),
    }


def verify_valid_results_binding(scope: dict | None = None) -> list[dict]:
    """For each already-valid original result that recovery will REUSE
    (never re-send), prove it is bound to a real, successful, matching
    semantic call -- not merely labelled method='llm' in alpha_matches.json.
    Matching is by the frozen claim/evidence text the original call
    recorded; an original call whose text matches more than one frozen
    record is reported as such (it still binds, but ambiguously by text)."""
    scope = scope or compute_recovery_scope()
    structured = json.loads((ORIGINAL_DIR / "structured_agent_outputs.json").read_text())
    records = {r["claim_id"]: r for r in structured["records"]}
    alpha_matches = {m["claim_id"]: m for m in json.loads((ORIGINAL_DIR / "alpha_matches.json").read_text())["matches"]}
    calls = [
        json.loads(line)
        for line in (ORIGINAL_DIR / "llm_semantic_calls.jsonl").read_text().splitlines()
        if line.strip()
    ]
    alpha_calls = [c for c in calls if c["task"] == "alpha_classifier"]
    report = []
    for claim_id in scope["valid_llm_results_claim_ids"]:
        record = records[claim_id]
        same_text_claims = [cid for cid, r in records.items() if str(r.get("claim") or "") == str(record.get("claim") or "")]
        needs_recovery_set = set(scope["needs_recovery_claim_ids"])
        twins_to_reclassify = [cid for cid in same_text_claims if cid != claim_id and cid in needs_recovery_set]
        bound = [c for c in alpha_calls if c["input_payload"]["claim"] == str(record.get("claim") or "")]
        match = alpha_matches[claim_id]
        decision = bound[0]["validated_output"] if bound else None
        consistent = bool(
            bound
            and bound[0]["provider_status"] == "success"
            and bound[0]["validation_status"] == "accepted"
            and not bound[0]["fallback_used"]
            and decision is not None
            and (decision.get("selected_alpha_id") or None) == (match.get("matched_alpha") or None)
        )
        report.append({
            "claim_id": claim_id,
            "semantic_call_found": bool(bound),
            "semantic_call_id": bound[0]["call_id"] if bound else None,
            "call_provider_status": bound[0]["provider_status"] if bound else None,
            "call_validated_output": decision,
            "alpha_matches_matched_alpha": match.get("matched_alpha"),
            "result_consistent_with_call": consistent,
            "frozen_records_sharing_this_claim_text": len(same_text_claims),
            "exact_text_twins_inside_the_973_to_be_reclassified": twins_to_reclassify,
            "twin_disclosure": (
                "These twins have byte-identical request input but will receive their OWN fresh recovery decision "
                "(semantic cache keys include run_id, so the original result is never copied onto them). A model "
                "could in principle answer differently for identical input; that would be reported as-is, never "
                "overridden to match the reused result."
                if twins_to_reclassify else None
            ),
            "binding_note": (
                "bound by recorded claim text (original run predates claim_ids on semantic records); "
                f"{len(same_text_claims)} frozen record(s) share this exact text, all with identical request input"
                if bound else "NO matching semantic call -- must NOT be reused"
            ),
        })
    return report


def _read_audit_lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def preflight_gateway_config(gateway, *, hard_cap: int, concurrency: int) -> dict:
    """Refuses to start a recovery run on a Gateway that is not configured
    exactly as the frozen plan requires. Fail-closed, before any send:
      * application-level retries must be 0 (the repo's own .env sets
        COMQUTOR_WEEK2_LLM_MAX_RETRIES=1 and load_dotenv never overrides an
        exported value, so only an explicit launcher export keeps this at 0 --
        with a non-zero value alpha_classifier would silently get 1 retry,
        and evidence_stance_classifier would get max(value, 2));
      * the Gateway call cap must not exceed the independent request cap;
      * request/response audit must be on;
      * the concurrency requested must match the frozen value (4);
      * the request timeout must be exactly 45 seconds.
    Returns the effective configuration for the run report."""
    problems = []
    if gateway.max_retries != 0:
        problems.append(f"application max_retries={gateway.max_retries} (must be 0)")
    if gateway.max_calls > hard_cap:
        problems.append(f"gateway max_calls={gateway.max_calls} exceeds the independent cap {hard_cap}")
    if not getattr(gateway, "_audit_enabled", False):
        problems.append("request/response audit is not enabled")
    if concurrency != 4:
        problems.append(f"concurrency={concurrency} (frozen value is 4)")
    if gateway.model_name != EXPECTED_MODEL:
        problems.append(f"model={gateway.model_name!r} (frozen model is {EXPECTED_MODEL!r})")
    if float(gateway.timeout_seconds) != EXPECTED_TIMEOUT_SECONDS:
        problems.append(
            f"timeout_seconds={gateway.timeout_seconds} (frozen value is {EXPECTED_TIMEOUT_SECONDS}; the launcher "
            "must export COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS explicitly -- the repo .env value is not a freeze)"
        )
    if problems:
        raise RuntimeError("recovery preflight refused to start: " + "; ".join(problems))
    return {
        "application_max_retries": gateway.max_retries,
        "gateway_max_calls": gateway.max_calls,
        "hard_request_cap": hard_cap,
        "audit_enabled": True,
        "concurrency": concurrency,
        "timeout_seconds": gateway.timeout_seconds,
        "provider": gateway.provider,
        "model": gateway.model_name,
    }


EXPECTED_REQUEST_URL = "https://api.deepseek.com/chat/completions"
EXPECTED_REQUEST_BODY_KEYS = frozenset({"messages", "model", "stream"})  # the original run's request shape: no max_tokens, no thinking/reasoning
# Environment variables that change the request SHAPE or endpoint; they must be absent from the launch shell.
FORBIDDEN_REAL_ENV = ("COMQUTOR_WEEK2_ALPHA_CLASSIFIER_MAX_TOKENS", "COMQUTOR_WEEK2_LLM_BASE_URL")


def _request_config_problem(request_record: dict) -> str | None:
    """What one AUDITED request actually carried, against the frozen config: the endpoint, the body's exact
    key set and model, and the client's own timeout / retry-count headers (so the 45 s, the 0 client retries
    and the original request shape are verified on the wire, not only on the Gateway object). None when it
    matches."""
    try:
        body = json.loads(request_record["body"])
    except Exception:
        return "request body is not valid JSON"
    if str(request_record.get("url")) != EXPECTED_REQUEST_URL:
        return f"url={request_record.get('url')!r}"
    if set(body) != EXPECTED_REQUEST_BODY_KEYS or body.get("stream") is not False:
        return f"body keys={sorted(body)!r} stream={body.get('stream')!r}"
    model = body.get("model")
    if model != EXPECTED_MODEL:
        return f"model={model!r}"
    headers = {str(k).lower(): str(v) for k, v in (request_record.get("headers") or {}).items()}
    if headers.get("x-stainless-read-timeout") != str(EXPECTED_TIMEOUT_SECONDS):
        return f"read-timeout header={headers.get('x-stainless-read-timeout')!r}"
    if headers.get("x-stainless-retry-count") != "0":
        return f"retry-count header={headers.get('x-stainless-retry-count')!r}"
    return None


def stance_followup_budget(match_records) -> dict:
    """Zero-call sizing of the SECOND model task (evidence_stance_classifier)
    that the production flow runs after classification, applied only to
    claims that ended up with a matched Alpha. Computed from the recovered
    classification results with the production request builder; sends
    nothing. NOT part of the 973-request cap -- needs its own authorization
    once this count is known."""
    import math

    from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
    from comqutor_alpha.structure_engine import evidence_stance_llm as esl

    items = esl.build_stance_request_items(list(match_records), load_alpha_taxonomy())
    matched = sum(1 for m in match_records if m.get("matched_alpha"))
    return {
        "matched_claims": matched,
        "stance_items": len(items),
        "items_per_call": esl.BATCH_SIZE,
        "max_target_alphas_per_claim": esl.MAX_TARGET_ALPHAS_PER_CLAIM,
        "max_requests_with_zero_retries": math.ceil(len(items) / esl.BATCH_SIZE) if items else 0,
        "note": "requires COMQUTOR_WEEK2_LLM_MAX_RETRIES=0 exported; with a non-zero value this task gets max(value, 2) retries",
    }


def rematerialize_match_record(record: dict, decision: dict) -> dict:
    """Rebuilds one claim's FULL alpha-match record offline from an already
    audited real decision, with zero model calls: runs the production
    map_structured_records on that single record with a classifier callable
    that simply returns the saved decision. This is the same production
    mapping tail the gateway path uses, so the result is field-for-field what
    that path would have produced (asserted by a test). `decision` is the
    audited provider JSON: {"decision": "none"|"select", "selected_alpha_id"}."""
    from comqutor_alpha.structure_engine.alpha_mapper import map_structured_records

    if decision.get("decision") == "none":
        classified = {"outcome": "none", "alpha_id": ""}
    elif decision.get("decision") == "select":
        classified = {"outcome": "selected", "alpha_id": decision["selected_alpha_id"]}
    else:
        raise ValueError(f"not a valid audited decision: {decision!r}")
    (result,) = map_structured_records(
        [record], classifier=lambda request, timeout_seconds=None: classified,
        classifier_enabled=True, llm_gateway=None, concurrency=1,
    )
    return result


def load_match_records(records_path: Path) -> dict[str, dict]:
    if not Path(records_path).exists():
        return {}
    out: dict[str, dict] = {}
    for line in Path(records_path).read_text().splitlines():
        if line.strip():
            record = json.loads(line)
            out[record["claim_id"]] = record
    return out


def assemble_recovered_alpha_matches(
    original_payload: dict,
    scope: dict,
    *,
    records_by_id: dict[str, dict],
    full_match_records: dict[str, dict],
    audit_states: dict[str, dict],
) -> tuple[dict, dict]:
    """Rebuilds the complete alpha-matches payload for ALL original claims, in
    the original order, from the only sources allowed to carry a real result:

      reused      the two original valid results, kept verbatim;
      recovered   a full match record persisted right after its batch;
      rematerialized  a claim whose response was audited but whose batch
                  record was never persisted (crash between response and
                  checkpoint): rebuilt offline from the audited decision;
      kept_original  every other claim (failed, unknown_inflight, not yet
                  sent): the ORIGINAL failure record, untouched -- a failure
                  or an unknown is never turned into NONE or a match.

    Identity is preserved: the output has exactly the original claim ids in the
    original order, none dropped, none duplicated, none added. Raises if not."""
    original = original_payload["matches"]
    original_ids = [m["claim_id"] for m in original]
    reused = set(scope["valid_llm_results_claim_ids"])
    sources = {"reused": 0, "recovered": 0, "rematerialized": 0, "kept_original": 0}
    claim_sources: dict[str, str] = {}
    kept_original_by_state: dict[str, int] = {}
    matches = []
    for original_match in original:
        cid = original_match["claim_id"]
        if cid in reused:
            matches.append(original_match)
            sources["reused"] += 1
            claim_sources[cid] = "reused_original_valid_result"
        elif cid in full_match_records:
            record = full_match_records[cid]
            matches.append(record)
            sources["recovered"] += 1
            # A batch returns a record for EVERY claim it handled, including one whose call failed or timed out.
            # That record is an attempt, not a recovered classification, and must be labelled as such.
            valid = record.get("alpha_match_method") == "llm" and not record.get("alpha_match_fallback_reason")
            claim_sources[cid] = "recovered_real_classification" if valid else "attempted_failed_no_valid_result"
        elif audit_states.get(cid, {}).get("state") == "success":
            matches.append(rematerialize_match_record(records_by_id[cid], audit_states[cid]["decision"]))
            sources["rematerialized"] += 1
            claim_sources[cid] = "rematerialized_from_audited_response"
        else:
            matches.append(original_match)
            sources["kept_original"] += 1
            claim_sources[cid] = "kept_original_failure"
            state = audit_states.get(cid, {}).get("state", "not_sent")
            kept_original_by_state[state] = kept_original_by_state.get(state, 0) + 1
    assembled_ids = [m["claim_id"] for m in matches]
    if assembled_ids != original_ids:
        raise RuntimeError("assembled alpha matches do not preserve the original claim identities exactly")
    payload = {**original_payload, "matches": matches}
    report = {"total": len(matches), "sources": sources, "kept_original_by_audit_state": kept_original_by_state,
              "identity_preserved": True, "claim_sources": claim_sources}
    return payload, report


def run_staged_recovery(
    plan: list[dict],
    records_by_id: dict[str, dict],
    *,
    gateway,
    run_output_root: Path,
    run_id: str,
    checkpoint_path: Path,
    map_fn,
    checkpoint_origin: str,
    hard_cap: int = HARD_REQUEST_CAP,
    concurrency: int = 4,
    records_path: Path | None = None,
) -> dict:
    """Runs the frozen plan with the frozen stop rules. Full per-claim match
    records are appended to ``records_path`` (default: next to the checkpoint)
    right after each batch, so a later assemble_recovered_alpha_matches never
    has to guess. ``checkpoint_origin``
    is REQUIRED ("fake_http_test" or "real"): a fake-origin run refuses to
    touch outputs/runs/ and marks its directory; a real-origin run refuses a
    directory holding fake artifacts; and a checkpoint is never resumed under
    a different origin than the one that created it. Sends nothing itself
    other than through map_fn(batch, classifier_enabled=True, llm_gateway=
    gateway, concurrency=concurrency) -- the real production classifier.

    Stop rules (each stops SCHEDULING any new batch; the batch already in
    flight finishes and every call in it is individually finalized -- this
    never claims in-flight calls were cancelled):
      local_audit_failure   gateway audit could not be persisted
      auth_failure          a batch response was HTTP 401/403
      identity_failure      a batch request was audited with empty claim_ids
      config_failure        a batch request's model != the frozen model
      call_cap_would_be_exceeded   gateway call_count + next batch > hard cap
      stage_a_gate_failed   any of the first-4 parallel config-check claims is
                            not a protocol-complete (valid select / valid
                            NONE) result with a correctly-bound identity
    A single claim failure in a later stage is SAVED (reconciles as 'failed')
    and never auto-retried; the run continues. Claims whose state is
    unknown_inflight or failed from an earlier attempt are never re-sent.
    """
    from comqutor_alpha.classification_recovery import ALPHA_CLASSIFIER_TASK, TaskAllowlistGateway
    from comqutor_alpha.structure_engine.week2_llm import (
        PROVIDER_REQUEST_AUDIT_ARTIFACT_PATH,
        PROVIDER_RESPONSE_AUDIT_ARTIFACT_PATH,
    )

    if checkpoint_origin not in (CHECKPOINT_ORIGIN_FAKE, CHECKPOINT_ORIGIN_REAL):
        raise ValueError(f"unknown checkpoint_origin {checkpoint_origin!r}")
    effective_config = preflight_gateway_config(gateway, hard_cap=hard_cap, concurrency=concurrency)
    # Task isolation (round 15): classification may send ONLY alpha_classifier. Every call below goes
    # through this proxy, which refuses any other task before anything is forwarded; the per-batch
    # audit check further down is a second, independent line.
    guarded = gateway if isinstance(gateway, TaskAllowlistGateway) else TaskAllowlistGateway(gateway)
    if checkpoint_origin == CHECKPOINT_ORIGIN_FAKE:
        mark_fake_http_directory(run_output_root)
    else:
        assert_directory_holds_no_fake_http_artifacts(run_output_root)
        assert_directory_holds_no_fake_http_artifacts(Path(checkpoint_path).parent)
    req_path = run_output_root / run_id / PROVIDER_REQUEST_AUDIT_ARTIFACT_PATH
    resp_path = run_output_root / run_id / PROVIDER_RESPONSE_AUDIT_ARTIFACT_PATH
    # Requests already audited in this execution directory by an EARLIER process count against the cap:
    # a resume must never get a fresh 973.
    prior_sent = len(_read_audit_lines(req_path))
    records_path = Path(records_path) if records_path else Path(checkpoint_path).with_suffix(".records.jsonl")
    checkpoint = load_checkpoint(checkpoint_path)
    existing_origin = checkpoint.get("origin")
    if existing_origin not in (None, checkpoint_origin):
        raise RuntimeError(
            f"checkpoint {checkpoint_path} was created with origin={existing_origin!r}; refusing to resume it "
            f"as origin={checkpoint_origin!r} (fake and real results must never mix)"
        )
    checkpoint["origin"] = checkpoint_origin
    stop_reason: str | None = None
    stop_detail: dict | None = None
    batches_run = 0
    submitted: list[str] = []

    def reconcile_into_checkpoint() -> tuple[set[str], set[str]]:
        states = reconcile_claim_states_from_audit_log(run_output_root, run_id)
        unknown: set[str] = set()
        failed: set[str] = set()
        for claim_id, info in states.items():
            if claim_id == "__multi_attempt_warnings__":
                continue
            if info["state"] == "success":
                checkpoint["completed_claim_ids"].setdefault(claim_id, {
                    "alpha_match_method": "llm",
                    "matched_alpha": info["decision"].get("selected_alpha_id") or None,
                    "fallback_reason": None,
                    "recovered_from_audit_log": True,
                })
            elif info["state"] == "unknown_inflight":
                unknown.add(claim_id)
            elif info["state"] == "failed":
                failed.add(claim_id)
        return unknown, failed

    for stage in plan:
        pending_ids = list(stage["claim_ids"])
        stage_batch_size = stage["batch_size"]
        for offset in range(0, len(pending_ids), stage_batch_size):
            unknown, failed = reconcile_into_checkpoint()
            batch_ids = [
                cid for cid in pending_ids[offset: offset + stage_batch_size]
                if cid not in checkpoint["completed_claim_ids"] and cid not in unknown and cid not in failed
            ]
            if not batch_ids:
                continue
            if gateway.audit_write_failed:
                stop_reason, stop_detail = "local_audit_failure", {"before_batch": batches_run + 1}
                break
            if prior_sent + gateway.call_count + len(batch_ids) > hard_cap:
                stop_reason = "call_cap_would_be_exceeded"
                stop_detail = {"call_count": gateway.call_count, "prior_sent_by_earlier_processes": prior_sent,
                               "next_batch": len(batch_ids), "hard_cap": hard_cap}
                break

            req_before = len(_read_audit_lines(req_path))
            resp_before = len(_read_audit_lines(resp_path))
            submitted.extend(batch_ids)
            results = map_fn(
                [records_by_id[cid] for cid in batch_ids],
                classifier_enabled=True, llm_gateway=guarded, concurrency=concurrency,
            )
            batches_run += 1
            for result in results:
                checkpoint["completed_claim_ids"][result["claim_id"]] = {
                    "alpha_match_method": result.get("alpha_match_method"),
                    "matched_alpha": result.get("matched_alpha"),
                    "fallback_reason": result.get("alpha_match_fallback_reason"),
                }
            with open(records_path, "a") as fh:
                for result in results:
                    fh.write(json.dumps(result, default=str) + "\n")
            save_checkpoint(checkpoint_path, checkpoint)

            new_requests = _read_audit_lines(req_path)[req_before:]
            new_responses = _read_audit_lines(resp_path)[resp_before:]
            auth_hits = sorted({r["status_code"] for r in new_responses if r.get("status_code") in AUTH_FAILURE_STATUS_CODES})
            if gateway.audit_write_failed:
                stop_reason, stop_detail = "local_audit_failure", {"after_batch": batches_run}
            elif auth_hits:
                stop_reason, stop_detail = "auth_failure", {"status_codes": auth_hits, "after_batch": batches_run}
            elif guarded.refused_tasks or any(r.get("task") != ALPHA_CLASSIFIER_TASK for r in new_requests):
                stop_reason = "task_isolation_violation"
                stop_detail = {"refused_tasks": guarded.refused_tasks,
                               "observed_request_tasks": sorted({str(r.get("task")) for r in new_requests}),
                               "after_batch": batches_run}
            elif any(not r.get("claim_ids") for r in new_requests):
                stop_reason, stop_detail = "identity_failure", {"after_batch": batches_run}
            elif any(_request_config_problem(r) for r in new_requests):
                stop_reason = "config_failure"
                stop_detail = {"expected_model": EXPECTED_MODEL, "expected_timeout_seconds": EXPECTED_TIMEOUT_SECONDS,
                               "problems": sorted({p for r in new_requests if (p := _request_config_problem(r))}),
                               "after_batch": batches_run}

            if stop_reason:
                break
        if stop_reason is None and stage["gate"]:
            # Evaluated once the stage's batches are done, from the AUDIT LOG, so it also holds for a resumed
            # process: a stage-A claim that failed in an earlier process keeps the gate failed (it is never
            # re-sent, and it is never silently waved through either).
            states = reconcile_claim_states_from_audit_log(run_output_root, run_id)
            all_requests = _read_audit_lines(req_path)
            bad = {}
            for cid in stage["claim_ids"]:
                info = states.get(cid)
                request_ok = any(r.get("claim_ids") == [cid] for r in all_requests)
                if info is None or info["state"] != "success" or not request_ok:
                    bad[cid] = (info or {}).get("state", "not_sent")
            if bad:
                stop_reason, stop_detail = "stage_a_gate_failed", {"not_protocol_complete": bad}
        if stop_reason:
            break

    final_states = reconcile_claim_states_from_audit_log(run_output_root, run_id)
    final_states.pop("__multi_attempt_warnings__", None)
    all_plan_ids = [cid for stage in plan for cid in stage["claim_ids"]]
    buckets = {"success": 0, "failed": 0, "unknown_inflight": 0, "not_sent_or_cache_served": 0}
    for cid in all_plan_ids:
        state = final_states.get(cid, {}).get("state")
        if state in ("success", "failed", "unknown_inflight"):
            buckets[state] += 1
        else:
            buckets["not_sent_or_cache_served"] += 1
    from collections import Counter

    tasks_observed = Counter(str(r.get("task")) for r in _read_audit_lines(req_path))
    return {
        "effective_config": effective_config,
        "task_isolation": {
            "allowed_tasks": sorted(guarded.allowed_tasks),
            "refused_tasks": guarded.refused_tasks,
            "request_tasks_observed": dict(tasks_observed),
        },
        "requests_audited_total": sum(tasks_observed.values()),
        "records_path": str(records_path),
        "stop_reason": stop_reason,
        "stop_detail": stop_detail,
        "batches_run": batches_run,
        "submitted_claim_ids": submitted,
        "gateway_call_count": gateway.call_count,
        "audit_buckets_over_plan": buckets,
        "checkpoint_completed": len(checkpoint["completed_claim_ids"]),
        "plan_total": len(all_plan_ids),
    }


# ---------------------------------------------------------------------------
# 2026-10-06 (round 15): the real execution path -- written, tested against a
# fake transport, and GATED. Nothing below runs unless the operator's own shell
# exports an acknowledgement bound to THIS frozen plan's hash (so a changed
# plan, scope, cap, model, timeout, concurrency or task list invalidates it).
# The assistant never sets that variable; it is the operator's authorization.
# ---------------------------------------------------------------------------

REAL_EXECUTION_ACK_ENV = "COMQUTOR_RECOVERY_REAL_EXECUTION_ACK"
ROUND15_DIR = REPO_ROOT / "docs" / "audit_artifacts" / "round_source_linking_t0_t2" / "round15_recovery_prep_20261006"
FROZEN_CONCURRENCY = 4
# Exported explicitly by the launcher. MAX_CALLS is checked separately (it may be lower than the cap on a resume).
REQUIRED_REAL_ENV = {
    "COMQUTOR_WEEK2_LLM_ENABLED": "1",
    "COMQUTOR_WEEK2_LLM_PROVIDER": "deepseek",
    "COMQUTOR_WEEK2_LLM_MODEL": EXPECTED_MODEL,
    "COMQUTOR_WEEK2_LLM_MAX_RETRIES": "0",
    "COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS": "45",
    "COMQUTOR_WEEK2_LLM_CONCURRENCY": "4",
}


def frozen_plan_sha256(plan: list[dict]) -> str:
    material = {
        "original_run_id": ORIGINAL_RUN_ID,
        "stages": [{"name": st["name"], "claim_ids": st["claim_ids"], "batch_size": st["batch_size"], "gate": st["gate"]} for st in plan],
        "hard_request_cap": HARD_REQUEST_CAP,
        "model": EXPECTED_MODEL,
        "timeout_seconds": EXPECTED_TIMEOUT_SECONDS,
        "concurrency": FROZEN_CONCURRENCY,
        "retries": {"client_level": 0, "application_level": 0},
        "request_response_audit": True,
        "allowed_tasks": ["alpha_classifier"],
        "reused_original_results": 2,
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def expected_real_execution_ack(plan: list[dict]) -> str:
    total = sum(len(st["claim_ids"]) for st in plan)
    return f"recover-{total}-alpha-classifier-requests-plan-{frozen_plan_sha256(plan)[:16]}"


def real_execution_authorization_problem(plan: list[dict], environ=None) -> str | None:
    environ = os.environ if environ is None else environ
    given = environ.get(REAL_EXECUTION_ACK_ENV, "")
    if not given:
        return f"{REAL_EXECUTION_ACK_ENV} is not set in this shell"
    if given != expected_real_execution_ack(plan):
        return f"{REAL_EXECUTION_ACK_ENV} does not match the current frozen plan (a changed plan needs a new authorization)"
    return None


def real_environment_problems(prior_sent: int = 0, environ=None) -> list[str]:
    environ = os.environ if environ is None else environ
    problems = [f"{k} must be exported as {v!r} (found {environ.get(k)!r})" for k, v in REQUIRED_REAL_ENV.items() if environ.get(k) != v]
    try:
        max_calls = int(environ.get("COMQUTOR_WEEK2_LLM_MAX_CALLS", ""))
        if not 1 <= max_calls <= HARD_REQUEST_CAP - prior_sent:
            problems.append(f"COMQUTOR_WEEK2_LLM_MAX_CALLS={max_calls} must be between 1 and {HARD_REQUEST_CAP - prior_sent}")
    except ValueError:
        problems.append("COMQUTOR_WEEK2_LLM_MAX_CALLS must be exported explicitly as an integer")
    problems.extend(
        f"{name} is exported but the recovery must keep the original run's request shape (unset it)"
        for name in FORBIDDEN_REAL_ENV if environ.get(name)
    )
    if not environ.get("DEEPSEEK_API_KEY"):
        problems.append("DEEPSEEK_API_KEY is not exported")
    url = environ.get("COMQUTOR_DATABASE_URL")
    if not url:
        problems.append("COMQUTOR_DATABASE_URL must be exported explicitly (the isolated database the backend reads)")
    else:
        from sqlalchemy.engine import make_url

        try:
            database_name = make_url(url).database or ""
        except Exception:  # noqa: BLE001
            database_name = ""
            problems.append("COMQUTOR_DATABASE_URL is not parseable")
        if database_name and not database_name.endswith("_test"):
            problems.append(f"database {database_name!r} does not end in _test: refusing to write run rows into what looks like the main database")
        if database_name and environ.get("COMQUTOR_REQUIRE_DATABASE_NAME") != database_name:
            problems.append(f"COMQUTOR_REQUIRE_DATABASE_NAME must be exported as {database_name!r} (a second guard at the write connection)")
    return problems


def cache_served_claims(output_root: Path, execution_id: str) -> dict[str, str]:
    """claim_id -> source_call_id for every claim whose classification was served by the run-local exact
    response cache (an identical-input claim's real call) instead of its own Provider request. Read from the
    execution's own semantic-call ledger."""
    ledger = Path(output_root) / execution_id / "llm_semantic_calls.jsonl"
    served: dict[str, str] = {}
    if ledger.exists():
        for line in ledger.read_text().splitlines():
            if not line.strip():
                continue
            call = json.loads(line)
            cache = call.get("cache") or {}
            if cache.get("hit") and call.get("task") == "alpha_classifier":
                for claim_id in call.get("claim_ids") or []:
                    served[claim_id] = cache.get("source_call_id")
    return served


def execute_recovery(
    *,
    plan: list[dict],
    records_by_id: dict[str, dict],
    scope: dict,
    gateway,
    output_root: Path,
    base_run_id: str,
    execution_id: str,
    checkpoint_origin: str,
    hard_cap: int = HARD_REQUEST_CAP,
    concurrency: int = FROZEN_CONCURRENCY,
    repository=None,
) -> dict:
    """Send (through run_staged_recovery) -> assemble the 975 matches -> write the independent direction-task
    manifest -> finalize the derived run. Finalization happens only when no stop rule fired; a stopped run keeps
    its checkpoint and audit for a resume under the same execution id and creates no derived run."""
    from comqutor_alpha.classification_recovery import (
        STANCE_FOLLOWUP_MANIFEST_FILENAME,
        build_stance_followup_manifest,
        finalize_classification_recovery_execution,
    )
    from comqutor_alpha.storage.file_store import save_json_record
    from comqutor_alpha.structure_engine.alpha_mapper import map_structured_records

    output_root = Path(output_root)
    execution_dir = output_root / execution_id
    execution_dir.mkdir(parents=True, exist_ok=True)
    outcome = run_staged_recovery(
        plan, records_by_id, gateway=gateway, run_output_root=output_root, run_id=execution_id,
        checkpoint_path=execution_dir / "checkpoint_recovery.json", map_fn=map_structured_records,
        checkpoint_origin=checkpoint_origin, hard_cap=hard_cap, concurrency=concurrency,
        records_path=execution_dir / "recovery_match_records.jsonl",
    )
    runtime = getattr(gateway, "semantic_runtime", None)
    if runtime is not None:
        runtime.finalize_manifest(complete=outcome["stop_reason"] is None)
    if outcome["stop_reason"] is not None:
        return {"outcome": outcome, "finalized": None}

    original_payload = json.loads((output_root / base_run_id / "alpha_matches.json").read_text())
    audit_states = reconcile_claim_states_from_audit_log(output_root, execution_id)
    audit_states.pop("__multi_attempt_warnings__", None)
    payload, report = assemble_recovered_alpha_matches(
        original_payload, scope, records_by_id=records_by_id,
        full_match_records=load_match_records(Path(outcome["records_path"])), audit_states=audit_states)
    cache_sources = cache_served_claims(output_root, execution_id)
    for claim_id in cache_sources:
        if report["claim_sources"].get(claim_id) == "recovered_real_classification":
            report["claim_sources"][claim_id] = "recovered_via_identical_input_cache"
    stance_manifest = build_stance_followup_manifest(
        payload["matches"], base_run_id=base_run_id, execution_id=execution_id,
        base_match_records=original_payload["matches"])
    save_json_record(execution_id, STANCE_FOLLOWUP_MANIFEST_FILENAME, stance_manifest, output_root=output_root)
    finalized = finalize_classification_recovery_execution(
        base_run_id, execution_id, assembled_alpha_matches=payload,
        recovery_provenance={
            "checkpoint_origin": checkpoint_origin,
            "claim_sources": report["claim_sources"],
            "claim_cache_sources": cache_sources,
            "assembly_report": {k: v for k, v in report.items() if k != "claim_sources"},
            "frozen_plan_sha256": frozen_plan_sha256(plan),
            "hard_request_cap": hard_cap,
            "effective_config": outcome["effective_config"],
            "task_isolation": outcome["task_isolation"],
            "requests_audited_total": outcome["requests_audited_total"],
            "audit_buckets_over_plan": outcome["audit_buckets_over_plan"],
        },
        output_root=output_root, graph_repository=repository)
    return {"outcome": outcome, "assembly": {k: v for k, v in report.items() if k != "claim_sources"},
            "stance_followup": {k: stance_manifest[k] for k in (
                "matched_claims", "pairs_needing_request", "pairs_reusable_from_base_run", "independent_request_budget")},
            "finalized": finalized}


def _database_identity(url: str) -> str:
    """dialect + host:port/database only -- never the user or the password."""
    from sqlalchemy.engine import make_url

    parsed = make_url(url)
    return f"{parsed.drivername}://{parsed.host or ''}{':' + str(parsed.port) if parsed.port else ''}/{parsed.database}"


def run_real_recovery(execution_id: str | None, environ=None) -> int:
    """The --execute entry point. Order matters: authorization first, then environment, and only then is anything
    constructed. ``environ`` defaults to the live process environment (tests); the command line passes the
    pre-import shell snapshot. Returns a process exit code (0 only for a finalized run)."""
    environ = os.environ if environ is None else environ
    plan = build_recovery_plan()
    problem = real_execution_authorization_problem(plan, environ)
    if problem:
        print(f"BLOCKED: {problem}.\nThis script has sent nothing. The real run needs the operator's explicit acknowledgement "
              f"for plan {frozen_plan_sha256(plan)[:16]} (see the readiness report).", file=sys.stderr)
        return 1

    from comqutor_alpha.classification_recovery import new_recovery_execution_id
    from comqutor_alpha.llm_runtime.cache import InMemoryLLMResponseCache
    from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
    from comqutor_alpha.storage.db.repository import build_write_repository_from_env
    from comqutor_alpha.structure_engine.week2_llm import PROVIDER_REQUEST_AUDIT_ARTIFACT_PATH, build_server_week2_llm_gateway

    resuming = execution_id is not None
    execution_id = execution_id or new_recovery_execution_id()
    if not execution_id.startswith("recovery-"):
        print("BLOCKED: --execution-id must be a recovery-* id", file=sys.stderr)
        return 1
    execution_dir = OUTPUT_ROOT / execution_id
    if execution_dir.exists() != resuming:
        print(f"BLOCKED: {execution_dir} {'does not exist (cannot resume)' if resuming else 'already exists (pass --execution-id to resume)'}", file=sys.stderr)
        return 1
    if (execution_dir / "recovery_lineage.json").exists():
        print("BLOCKED: this execution is already finalized", file=sys.stderr)
        return 1
    prior_sent = len(_read_audit_lines(execution_dir / PROVIDER_REQUEST_AUDIT_ARTIFACT_PATH))
    env_problems = real_environment_problems(prior_sent, environ)
    if env_problems:
        print("BLOCKED: environment does not match the frozen configuration:\n  - " + "\n  - ".join(env_problems), file=sys.stderr)
        return 1

    scope = compute_recovery_scope()
    binding = verify_valid_results_binding(scope)
    if not all(row["result_consistent_with_call"] for row in binding):
        print("BLOCKED: a reused original result is not bound to a matching successful call", file=sys.stderr)
        return 1
    structured = json.loads((ORIGINAL_DIR / "structured_agent_outputs.json").read_text())
    records_by_id = {r["claim_id"]: r for r in structured["records"]}
    hard_cap = HARD_REQUEST_CAP
    hashes_before = {name: _sha256(ORIGINAL_DIR / name) for name in ("alpha_matches.json", "structured_agent_outputs.json", "source_registry.json")}

    execution_dir.mkdir(parents=True, exist_ok=True)
    gateway = build_server_week2_llm_gateway(execution_id, OUTPUT_ROOT, enable_request_response_audit=True)
    if gateway is None:
        print("BLOCKED: the production gateway builder returned no gateway (configuration)", file=sys.stderr)
        return 1
    gateway.attach_semantic_runtime(SemanticRuntimeSession(
        run_id=execution_id, output_directory=str(execution_dir), execution_mode="live",
        provider=gateway.provider, model=gateway.model_name, cache=InMemoryLLMResponseCache()))
    repository = build_write_repository_from_env(str(OUTPUT_ROOT))

    print(f"[recovery] execution_id={execution_id} based_on={ORIGINAL_RUN_ID} prior_sent={prior_sent} cap={hard_cap}", flush=True)
    print(f"[recovery] database={_database_identity(environ['COMQUTOR_DATABASE_URL'])} "
          f"required_database_name={environ.get('COMQUTOR_REQUIRE_DATABASE_NAME')!r}", flush=True)
    result = execute_recovery(
        plan=plan, records_by_id=records_by_id, scope=scope, gateway=gateway, output_root=OUTPUT_ROOT,
        base_run_id=ORIGINAL_RUN_ID, execution_id=execution_id, checkpoint_origin=CHECKPOINT_ORIGIN_REAL,
        hard_cap=hard_cap, concurrency=FROZEN_CONCURRENCY, repository=repository)
    result["original_run_input_hashes_unchanged"] = hashes_before == {name: _sha256(ORIGINAL_DIR / name) for name in hashes_before}
    ROUND15_DIR.mkdir(parents=True, exist_ok=True)
    report_path = ROUND15_DIR / f"recovery_execution_report_{execution_id}.json"
    report_path.write_text(json.dumps(result, indent=2, default=str))
    outcome = result["outcome"]
    print(f"[recovery] stop_reason={outcome['stop_reason']} requests_audited_total={outcome['requests_audited_total']} "
          f"batches={outcome['batches_run']} buckets={outcome['audit_buckets_over_plan']}")
    print(f"[recovery] report: {report_path}")
    finalized = result["finalized"]
    if finalized is None:
        print("[recovery] STOPPED before finalization; re-run with --execution-id to resume (failed/unknown claims are never auto-resent).", file=sys.stderr)
        return 2
    print(f"[recovery] derived run: {finalized}")
    return 0 if finalized.get("status") == "ok" else 3


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--new-run-id", default=f"{ORIGINAL_RUN_ID}-recovery-01")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fake-transport-test", action="store_true")
    parser.add_argument("--execute", action="store_true",
                        help=f"real recovery; refused unless {REAL_EXECUTION_ACK_ENV} matches the frozen plan")
    parser.add_argument("--execution-id", default=None, help="resume an existing recovery-* execution (with --execute)")
    args = parser.parse_args()

    if args.execute:
        sys.exit(run_real_recovery(args.execution_id, environ=_LAUNCH_ENV))
    elif args.fake_transport_test:
        run_fake_transport_test(args.new_run_id)
    else:
        run_dry_run(args.new_run_id)
