"""Part 7 (2026-10-06, limited real-verification round): independent AMD
recompute using the REAL, already-produced content-support results for
all 21 claims -- ZERO new Provider calls in this script. Reuses the REAL
production scoring chain (_run_week3_graph_pipeline, the exact function
trigger_content_support_reevaluation itself calls) rather than
reimplementing it.

v2 fix (found while building this round's merge, corrects a real error in
the PREVIOUS recompute, review-20261006T001911Z-14407742): that earlier
recompute used claim:66's RAW on-disk record from execution phase-c-
20261005T233842Z-1b2550ac, which is REJECTED (content_support_status=
PENDING_REVIEW, fallback_reason=quote_or_data_not_found) -- that
rejection was caused by the multi-field-citation bug fixed LATER the same
day. The CORRECTED result (content_support_status=CONDITIONAL) was only
ever demonstrated inside a unit test's own in-memory replay -- it was
NEVER persisted as a real execution artifact, so the previous recompute
silently used the stale, pre-fix rejection instead of the corrected
result. Fixed here by actually PERSISTING a proper, explicitly-labeled
offline replay: the ORIGINAL real Provider response (read verbatim from
the real wire-level audit log) is reprocessed through the CURRENT,
real, unmodified _process_batch -- a deterministic, zero-cost
reprocessing of already-real data under corrected code, never a new
Provider call, and never presented as if it were.

Per-claim source selection (most recent REAL, VALID result wins; a
truncated/failed retry attempt never erases an earlier real success):
  - The 3 of this round's 6 claims that got a real, validated v2.1
    response (aggressive:42, fundamental:119, bull:61): use execution
    phase-c-20261006T034452Z-1ab992d0 (this round).
  - The 2 of this round's 6 that truncated again (fundamental:29,
    portfolio:38): their most recent REAL, VALID result is still the
    earlier v1 one from phase-c-20261006T000643Z-bb63dfd7 -- used as-is,
    this round's own failed retry does not erase it.
  - bear:66 (truncated again this round, and its own original attempt was
    rejected pre-fix): uses the offline replay described above.
  - The remaining 14 claims: unaffected by this round, use their existing
    v1 result from phase-c-20261006T000643Z-bb63dfd7 exactly as before.
Every selection's provenance (which execution, which post-processing
version, real vs. offline-replayed) is recorded explicitly in this
execution's own metadata.json.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

ORIGINAL_RUN_ID = "1bad76a7-72ac-4c8b-8189-2e5c0f1a6105"
REEVAL_RUN_ID = "automated-eligibility-reeval-20261005T190101Z-d9b7fdba"
OUTPUT_ROOT = REPO_ROOT / "outputs" / "runs"
ROUND10_DIR = Path(__file__).resolve().parent

EXECUTION_20_ID = "phase-c-20261006T000643Z-bb63dfd7"
EXECUTION_1_ID = "phase-c-20261005T233842Z-1b2550ac"
EXECUTION_6_ID = "phase-c-20261006T034452Z-1ab992d0"
EXECUTION_20_PATH = ROUND10_DIR / "executions" / f"{EXECUTION_20_ID}.json"
EXECUTION_6_PATH = ROUND10_DIR / "executions" / f"{EXECUTION_6_ID}.json"
FROZEN_20_SCOPE_PATH = ROUND10_DIR / "09_frozen_20_claim_scope_20261006.json"
FROZEN_6_SCOPE_PATH = ROUND10_DIR / "14_frozen_6_claim_scope_20261006.json"

CLAIM_66 = "1bad76a7-72ac-4c8b-8189-2e5c0f1a6105:bear_researcher:investment_debate_state.bear_history:claim:66"
REAL_RESPONSE_AUDIT_PATH = "outputs/runs/phase-c-amd-21-claim-verification/error_logs/week2_llm_provider_response_audit.jsonl"


def _fail(message: str) -> dict:
    return {"status": "failed", "error_code": message}


def _replay_claim66_original_response_under_current_validator() -> dict:
    """Reads the REAL, original Provider response for claim:66 (execution
    phase-c-20261005T233842Z-1b2550ac) verbatim from the real wire-level
    audit log, and reprocesses it through the CURRENT, real, unmodified
    content_support_llm._process_batch -- the exact same function every
    real execution uses. No network call; the "gateway" here is a plain
    replay stand-in returning the literal already-saved response. This is
    a deterministic function of already-real data, not a new judgment.

    ACTUAL finding from running this (2026-10-06, same round): the result
    is FALLBACK_INTERNAL_CONTRADICTION, not the CONDITIONAL result an
    earlier, pre-v2-contract test once demonstrated for this same response
    -- because that original response is v1-shaped (no support_basis/
    unsupported_remainder_materiality at all), and _process_batch now
    ALSO runs the v2.1 structural self-consistency check unconditionally.
    This is the correct, honest outcome: an old v1 answer is never allowed
    to pass as if it were a v2.1 judgment just because its citation was
    real. claim:66's real v2.1 status remains genuinely UNRESOLVED -- both
    the original attempt and this round's fresh retry failed to produce
    usable v2.1-compliant data (see Part 五/六 report for the full
    account) -- so this function's result correctly keeps claim:66 at
    PENDING_REVIEW, never silently upgraded."""
    from comqutor_alpha.structure_engine.content_support_llm import (
        ContentSupportRunStats,
        _process_batch,
        build_content_support_request_items,
    )

    reeval_structured = json.loads((OUTPUT_ROOT / REEVAL_RUN_ID / "structured_agent_outputs.json").read_text())
    sources = json.loads((OUTPUT_ROOT / REEVAL_RUN_ID / "source_registry.json").read_text())["sources"]
    record = next(r for r in reeval_structured["records"] if r["claim_id"] == CLAIM_66)
    items = build_content_support_request_items([record], sources)
    assert len(items) == 1, "claim:66 must resolve to exactly one request item"

    resps = [json.loads(line) for line in (REPO_ROOT / REAL_RESPONSE_AUDIT_PATH).read_text().splitlines()]
    resp = next(r for r in resps if r["execution_id"] == EXECUTION_1_ID)
    content = json.loads(resp["body"])["choices"][0]["message"]["content"]
    returned_items = json.loads(content)["items"]

    class _ReplayGateway:
        model_name = "deepseek-v4-flash"
        provider = "deepseek"

        def invoke_json_with_trace(self, task, payload, validator):
            validated = validator({"items": returned_items})
            return SimpleNamespace(
                provider_attempt_count=1, provider_status="success", error_code=None,
                cache_hit=False, validation_accepted=True, request_control=None,
                provider_response_metadata=None, token_usage=None, attempt_history=(),
                validated_output=validated,
            )

        def finalize_semantic_invocation(self, invocation, accepted, fallback_reason=None):
            pass

    stats = ContentSupportRunStats()
    results: dict[str, dict] = {}
    _process_batch(items, _ReplayGateway(), stats, results)
    return results[CLAIM_66]


def build_merged_structured_payload() -> tuple[dict, dict, list[dict]]:
    """Returns (merged_structured_payload, provenance_by_claim_id,
    sources). Base is the REEVAL run's own structured_agent_outputs.json;
    every record NOT among the 21 target claims is carried through
    completely unchanged. Each of the 21 is replaced with its own most
    recent REAL, VALID result -- see module docstring for the exact
    per-claim selection and why."""
    scope20 = json.loads(FROZEN_20_SCOPE_PATH.read_text())
    scope6 = json.loads(FROZEN_6_SCOPE_PATH.read_text())
    remaining_20_ids = scope20["remaining_20_claim_ids"]
    already_verified_id = scope20["already_verified_claim_id"]
    six_claim_ids = set(scope6["short_to_full"].values())
    all_21_ids = set(remaining_20_ids) | {already_verified_id}
    assert len(all_21_ids) == 21
    assert six_claim_ids <= all_21_ids

    base_structured = json.loads((OUTPUT_ROOT / REEVAL_RUN_ID / "structured_agent_outputs.json").read_text())
    sources = json.loads((OUTPUT_ROOT / REEVAL_RUN_ID / "source_registry.json").read_text())["sources"]

    exec20_by_id = {r["claim_id"]: r for r in json.loads(EXECUTION_20_PATH.read_text())["records"]}
    exec6_by_id = {r["claim_id"]: r for r in json.loads(EXECUTION_6_PATH.read_text())["records"]}

    updated_by_id: dict[str, dict] = {}
    provenance: dict[str, dict] = {}

    # claim:66 is the one claim NOT in exec20 at all (it was verified
    # separately, as the single-claim execution) -- handle it first via
    # the explicit offline replay, never the stale on-disk rejection.
    replayed_66 = _replay_claim66_original_response_under_current_validator()
    updated_by_id[CLAIM_66] = replayed_66
    provenance[CLAIM_66] = {
        "execution_id": EXECUTION_1_ID,
        "post_processing_version": "content_support.llm.v2.1",
        "note": (
            "OFFLINE REPLAY (zero-cost, no new Provider call): the real original v1-shaped Provider "
            "response from execution_id=" + EXECUTION_1_ID + " was reprocessed through the current, "
            "real, unmodified _process_batch (which now also runs v2.1's structural self-consistency "
            "check). Result: FALLBACK_INTERNAL_CONTRADICTION -- the old response lacks the v2.1-"
            "required support_basis/unsupported_remainder_materiality fields, so it cannot be "
            "resolved as a v2.1 judgment; content_support_status correctly remains PENDING_REVIEW, "
            "never upgraded. This round's own fresh retry on claim:66 (execution " + EXECUTION_6_ID +
            ") also truncated and produced no new data. claim:66's real v2.1 status remains genuinely "
            "UNRESOLVED -- determining it requires a new, real v2.1 Provider call, not covered by "
            "this round's authorization."
        ),
    }

    for cid in remaining_20_ids:
        if cid in six_claim_ids and exec6_by_id[cid].get("content_support_llm_fallback_reason") is None:
            # This round produced a real, validated v2.1 result for this claim -- use it.
            updated_by_id[cid] = exec6_by_id[cid]
            provenance[cid] = {
                "execution_id": EXECUTION_6_ID,
                "post_processing_version": "content_support.llm.v2.1",
                "note": "real, validated result from this round's 6-claim limited verification",
            }
        else:
            # Either not part of this round's 6, or this round's retry
            # truncated/failed -- the existing v1 result (if any) from the
            # 20-claim execution is the most recent REAL, VALID one, and a
            # failed retry must never erase it.
            updated_by_id[cid] = exec20_by_id[cid]
            retried_note = (
                " (this round attempted a v2.1 retry, which truncated and produced no new data -- "
                "the earlier real v1 result is retained, not erased)"
                if cid in six_claim_ids
                else ""
            )
            provenance[cid] = {
                "execution_id": EXECUTION_20_ID,
                "post_processing_version": "content_support.llm.v1 (with 2026-10-06 multi-field citation fix)",
                "note": "real v1 result" + retried_note,
            }

    assert set(updated_by_id) == all_21_ids, f"missing/extra claim_ids: {all_21_ids ^ set(updated_by_id)}"

    merged = copy.deepcopy(base_structured)
    replaced_count = 0
    for i, record in enumerate(merged.get("records", [])):
        cid = record.get("claim_id")
        if cid in updated_by_id:
            merged["records"][i] = updated_by_id[cid]
            replaced_count += 1
    assert replaced_count == 21, f"expected to replace exactly 21 records, replaced {replaced_count}"

    return merged, provenance, sources


def run_recompute() -> dict:
    # Explicit guard (required this round too): zero new Provider sends
    # possible from inside _run_week3_graph_pipeline, regardless of what
    # internal code path might otherwise try to build a gateway.
    os.environ["COMQUTOR_WEEK2_LLM_ENABLED"] = "0"

    from comqutor_alpha.api.routes_research import (
        _new_review_execution_id,
        _rebase_run_id_for_reevaluation_execution,
        _run_week3_graph_pipeline,
        WEEK3_PIPELINE_STATUS_ARTIFACT_FILENAME,
    )
    from comqutor_alpha.storage.file_store import (
        load_json_record,
        load_json_record_if_exists,
        save_json_record,
        run_dir_for,
    )

    try:
        original_metadata = load_json_record(ORIGINAL_RUN_ID, "metadata.json", output_root=OUTPUT_ROOT)
        alpha_matches_payload = load_json_record(ORIGINAL_RUN_ID, "alpha_matches.json", output_root=OUTPUT_ROOT)
        extracted_structures_payload = load_json_record(
            ORIGINAL_RUN_ID, "extracted_structures.json", output_root=OUTPUT_ROOT
        )
    except Exception as exc:
        return _fail(f"ORIGINAL_RUN_INPUTS_UNAVAILABLE: {exc}")

    merged_structured, provenance, sources = build_merged_structured_payload()

    execution_id = _new_review_execution_id()
    rebased_structured, rebased_alpha_matches, rebased_extracted_structures = (
        _rebase_run_id_for_reevaluation_execution(
            structured_payload=merged_structured,
            alpha_matches_payload=alpha_matches_payload,
            extracted_structures_payload=extracted_structures_payload,
            execution_id=execution_id,
        )
    )

    execution_metadata = {
        **original_metadata,
        "run_id": execution_id,
        "based_on_run_id": ORIGINAL_RUN_ID,
        "execution_type": "round10_llm_content_support_independent_recompute_v2",
        "claim_provenance": provenance,
        "input_structured_agent_outputs_source": REEVAL_RUN_ID,
        "input_structured_agent_outputs_sha256": hashlib.sha256(
            (OUTPUT_ROOT / REEVAL_RUN_ID / "structured_agent_outputs.json").read_bytes()
        ).hexdigest(),
    }

    save_json_record(execution_id, "metadata.json", execution_metadata, output_root=OUTPUT_ROOT)
    save_json_record(execution_id, "alpha_matches.json", rebased_alpha_matches, output_root=OUTPUT_ROOT)
    save_json_record(execution_id, "extracted_structures.json", rebased_extracted_structures, output_root=OUTPUT_ROOT)
    save_json_record(execution_id, "structured_agent_outputs.json", rebased_structured, output_root=OUTPUT_ROOT)
    rebased_registry = {"run_id": execution_id, "sources": sources}
    save_json_record(execution_id, "source_registry.json", rebased_registry, output_root=OUTPUT_ROOT)

    execution_run_dir = run_dir_for(execution_id, OUTPUT_ROOT)
    try:
        _run_week3_graph_pipeline(execution_run_dir, graph_repository=None, require_verified_evidence_gate=True)
    except Exception as exc:
        return _fail(f"RECOMPUTE_PIPELINE_RAISED: {exc}")

    status = load_json_record_if_exists(execution_id, WEEK3_PIPELINE_STATUS_ARTIFACT_FILENAME, output_root=OUTPUT_ROOT)
    return {
        "status": "ok" if status.get("outcome") == "success" else "failed",
        "execution_id": execution_id,
        "based_on_run_id": ORIGINAL_RUN_ID,
        "pipeline_status": status,
        "claim_provenance": provenance,
    }


if __name__ == "__main__":
    result = run_recompute()
    print(json.dumps(result, indent=2, default=str))
