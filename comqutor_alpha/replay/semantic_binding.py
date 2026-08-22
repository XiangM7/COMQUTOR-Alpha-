"""Exact, task-aware binding of saved semantic calls to saved artifacts.

No binding uses text similarity, array position, or call order.  A call must
match stable task identity plus exact structured fields and must own a unique
artifact decision.  Duplicate inputs therefore fail closed instead of being
disambiguated by occurrence order.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.replay.source_bundle import (
    EXACT_REPLAY_SEMANTIC_BINDING_MISSING,
    EXACT_REPLAY_SEMANTIC_BINDING_ORPHAN,
    EXACT_REPLAY_SEMANTIC_CALL_AMBIGUOUS,
    EXACT_REPLAY_SEMANTIC_INPUT_MISMATCH,
    EXACT_REPLAY_SEMANTIC_OUTPUT_MISMATCH,
    EXACT_REPLAY_SEMANTIC_TASK_UNSUPPORTED,
    EXACT_REPLAY_SEMANTIC_VERSION_MISMATCH,
    ExactReplayError,
    ExactSemanticSourceBundle,
    sha256_canonical_json,
)
from comqutor_alpha.structure_engine.evidence_stance_llm import (
    FALLBACK_DUPLICATE_RESULT,
    FALLBACK_MISSING_RESULT,
    LLM_CLASSIFIER_VERSION,
    LLM_TASK_NAME as EVIDENCE_STANCE_TASK_NAME,
    STANCE_METHOD_DETERMINISTIC_FALLBACK,
    STANCE_METHOD_LLM,
    StanceRequestItem,
    _validate_response_item,
)
from comqutor_alpha.structure_engine.week2_llm import (
    _TASK_RUNTIME_METADATA,
    Week2LLMGateway,
)

BINDING_AUDIT_SCHEMA_VERSION = "comqutor.semantic_binding_audit.v1"
BINDING_STATUS_PASS = "PASS"
BINDING_STATUS_FAIL = "FAIL"


def _live_identity(task: str, taxonomy_version: str | None) -> tuple[str, str, str, str, str | None]:
    """Reads the CURRENT canonical identity from week2_llm.py's own runtime
    metadata / prompt hashing -- never a hand-copied literal that can drift
    from the real, live production values."""
    metadata = _TASK_RUNTIME_METADATA[task]
    return (
        metadata["prompt_version"],
        Week2LLMGateway.prompt_identity_sha256(task),
        metadata["input_schema_version"],
        metadata["output_schema_version"],
        taxonomy_version,
    )


_TASK_BINDING_VERSIONS = {
    "structured_adapter": _live_identity("claim_batch_enrichment", None),
    # Re-derived live (Exact Semantic Replay B1 Binding Support task): the
    # prior hand-copied week2.alpha_classifier.v1 identity predates the
    # separately Product-Owner-authorized Alpha Mapper Authority Migration
    # (full-taxonomy LLM semantic primary, prompt_version bumped to v2).
    # Reading it live means this entry can never again silently drift from
    # the real production prompt the way the old literal did.
    "alpha_classifier": _live_identity("alpha_classifier", "alpha_taxonomy_v1"),
    "structure_extractor": _live_identity("structure_extractor", None),
    # Added (Exact Semantic Replay B1 Binding Support task): B1 Evidence
    # Stance's own LLM upgrade task, registered in the runtime task registry
    # by the prior Post-Alpha-Authority-Migration Cleanup task -- this entry
    # gives it real Exact Replay version-identity checking for the first
    # time, using its current, unmodified v3 identity.
    "evidence_stance_classifier": _live_identity(EVIDENCE_STANCE_TASK_NAME, "alpha_taxonomy_v1"),
}
# Version validation and task-binding support are deliberately separate
# concepts (task spec section 9): this is the sole source of truth for
# "does Exact Replay have a binding implementation for this task at all" --
# a task absent here is EXACT_REPLAY_SEMANTIC_TASK_UNSUPPORTED, never
# silently reported as a version mismatch.
_SUPPORTED_BINDING_TASKS = frozenset(_TASK_BINDING_VERSIONS)


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return result or "unknown"


def _display_factor(value: str, ticker: str) -> str:
    return f"{ticker} Revenue Growth" if value == "Revenue Growth" else value


def _as_dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _append_unique(audit: dict[str, Any], field: str, value: Any) -> None:
    if value not in audit[field]:
        audit[field].append(value)


def _claim_id(record: dict[str, Any]) -> str:
    return str(record.get("claim_id") or record.get("agent_output_id") or "")


def _adapter_segment_id(record: dict[str, Any]) -> str | None:
    source_output_id = record.get("source_agent_output_id")
    claim_index = record.get("claim_index")
    if not source_output_id or not isinstance(claim_index, int) or isinstance(claim_index, bool):
        return None
    return f"{source_output_id}:segment:{claim_index}"


def _new_audit(bundle: ExactSemanticSourceBundle) -> dict[str, Any]:
    records_by_task = dict.fromkeys(sorted(_SUPPORTED_BINDING_TASKS), 0)
    for record in bundle.semantic_calls:
        task = str(record.get("task") or "")
        if task in records_by_task:
            records_by_task[task] += 1
    return {
        "schema_version": BINDING_AUDIT_SCHEMA_VERSION,
        "source_run_id": bundle.source_run_id,
        "ticker": bundle.ticker,
        "total_semantic_records": len(bundle.semantic_calls),
        "records_by_task": records_by_task,
        "accepted_records": sum(
            record.get("validation_status") == "accepted"
            for record in bundle.semantic_calls
        ),
        "uniquely_bound_records": 0,
        "bound_call_ids": [],
        "bindings": [],
        "orphan_records": [],
        "missing_bindings": [],
        "ambiguous_bindings": [],
        "input_hash_mismatches": [],
        "output_hash_mismatches": [],
        "artifact_decision_mismatches": [],
        "version_mismatches": [],
        # Separate from version_mismatches: a task identity with no binding
        # implementation at all (task spec section 9).
        "unsupported_tasks": [],
        "final_status": BINDING_STATUS_FAIL,
    }


def _verify_record_hashes(record: dict[str, Any], audit: dict[str, Any]) -> bool:
    call_id = str(record.get("call_id") or "")
    try:
        actual_input = sha256_canonical_json(record.get("input_payload"))
    except Exception:
        actual_input = None
    if actual_input != record.get("input_sha256"):
        _append_unique(audit, "input_hash_mismatches", call_id)
    try:
        actual_output = sha256_canonical_json(record.get("validated_output"))
    except Exception:
        actual_output = None
    if actual_output != record.get("validated_output_sha256"):
        _append_unique(audit, "output_hash_mismatches", call_id)
    return actual_input == record.get("input_sha256") and actual_output == record.get(
        "validated_output_sha256"
    )


def _verify_binding_version(
    record: dict[str, Any],
    bundle: ExactSemanticSourceBundle,
) -> bool:
    expected = _TASK_BINDING_VERSIONS.get(str(record.get("task") or ""))
    actual = (
        record.get("prompt_version"),
        record.get("prompt_sha256"),
        record.get("input_schema_version"),
        record.get("output_schema_version"),
        record.get("taxonomy_version"),
    )
    return record.get("run_id") == bundle.source_run_id and actual == expected


def _register_binding(
    *,
    audit: dict[str, Any],
    call_id: str,
    task: str,
    decision_keys: list[str],
    decision_owners: dict[str, list[str]],
) -> None:
    for key in decision_keys:
        decision_owners.setdefault(key, []).append(call_id)
    audit["bound_call_ids"].append(call_id)
    audit["bindings"].append(
        {
            "call_id": call_id,
            "task": task,
            "artifact_decision_keys": sorted(decision_keys),
            "binding_basis": {
                "run_id": True,
                "task": True,
                "input_sha256": True,
                "prompt_version": True,
                "prompt_sha256": True,
                "input_schema_version": True,
                "output_schema_version": True,
                "taxonomy_version": True,
                "task_specific_stable_identity": True,
            },
        }
    )


def _bind_adapter(
    record: dict[str, Any],
    *,
    bundle: ExactSemanticSourceBundle,
    audit: dict[str, Any],
    structured_by_segment: dict[str, list[dict[str, Any]]],
    decision_owners: dict[str, list[str]],
) -> None:
    call_id = str(record.get("call_id") or "")
    request = record.get("input_payload")
    output = record.get("validated_output")
    if not isinstance(request, dict) or set(request) != {"ticker", "agent", "segments"}:
        _append_unique(audit, "artifact_decision_mismatches", call_id)
        return
    if str(request.get("ticker") or "").upper() != bundle.ticker:
        _append_unique(audit, "artifact_decision_mismatches", call_id)
        return
    segments = _as_dict_list(request.get("segments"))
    claims = _as_dict_list(output.get("claims")) if isinstance(output, dict) else []
    if not segments or len(segments) != len(claims):
        _append_unique(audit, "artifact_decision_mismatches", call_id)
        return
    segments_by_id = {str(item.get("segment_id") or ""): item for item in segments}
    claims_by_id = {str(item.get("segment_id") or ""): item for item in claims}
    if (
        "" in segments_by_id
        or "" in claims_by_id
        or len(segments_by_id) != len(segments)
        or len(claims_by_id) != len(claims)
        or set(segments_by_id) != set(claims_by_id)
    ):
        _append_unique(audit, "ambiguous_bindings", call_id)
        return

    decision_keys: list[str] = []
    for segment_id, segment in segments_by_id.items():
        candidate_records = structured_by_segment.get(segment_id, [])
        if not candidate_records:
            _append_unique(audit, "missing_bindings", f"{call_id}:{segment_id}")
            continue
        if len(candidate_records) != 1:
            _append_unique(audit, "ambiguous_bindings", f"{call_id}:{segment_id}")
            continue
        artifact_record = candidate_records[0]
        claim = claims_by_id[segment_id]
        preserved = all(
            claim.get(key) == segment.get(key) == artifact_record.get(key)
            for key in ("claim", "evidence", "source_section")
        )
        enriched = (
            claim.get("direction") == artifact_record.get("direction")
            and float(claim.get("confidence")) == float(artifact_record.get("confidence"))
            and {str(value) for value in claim.get("factors") or []}
            <= {str(value) for value in artifact_record.get("factors") or []}
        )
        if (
            not preserved
            or not enriched
            or artifact_record.get("agent") != request.get("agent")
            or str(artifact_record.get("ticker") or "").upper() != bundle.ticker
            or artifact_record.get("extraction_method") != "llm_strict_json"
        ):
            _append_unique(audit, "artifact_decision_mismatches", f"{call_id}:{segment_id}")
            continue
        decision_keys.append(f"structured:{_claim_id(artifact_record)}")
    if len(decision_keys) == len(segments):
        _register_binding(
            audit=audit,
            call_id=call_id,
            task="structured_adapter",
            decision_keys=decision_keys,
            decision_owners=decision_owners,
        )
    elif not any(call_id in str(value) for value in audit["missing_bindings"]):
        _append_unique(audit, "orphan_records", call_id)


def _bind_alpha(
    record: dict[str, Any],
    *,
    audit: dict[str, Any],
    structured_by_claim_id: dict[str, list[dict[str, Any]]],
    alpha_matches: list[dict[str, Any]],
    taxonomy: dict[str, Any],
    decision_owners: dict[str, list[str]],
) -> None:
    """Alpha Mapper Authority Migration note: the request payload is now the
    FULL canonical taxonomy (alpha_taxonomy), never a deterministically
    pre-restricted candidate/allowed_alpha_ids subset -- there is no
    eligibility-derived content left in the request to compare against
    eligible_candidates. The meaningful request-side check under the new
    architecture is instead "was the exact, unmodified, live taxonomy sent"
    (task spec section 13: never reintroduce an eligible-candidates
    assumption -- a matched Alpha may be entirely absent from deterministic
    eligible_candidates now)."""
    call_id = str(record.get("call_id") or "")
    request = record.get("input_payload")
    output = record.get("validated_output")
    if not isinstance(request, dict) or not isinstance(output, dict):
        _append_unique(audit, "artifact_decision_mismatches", call_id)
        return
    exact_candidates = [
        item
        for item in alpha_matches
        if item.get("claim") == request.get("claim")
        and item.get("evidence") == request.get("evidence")
        and item.get("factors") == request.get("factors")
        and item.get("direction") == request.get("direction")
    ]
    if not exact_candidates:
        _append_unique(audit, "missing_bindings", call_id)
        return
    if len(exact_candidates) != 1:
        _append_unique(audit, "ambiguous_bindings", call_id)
        return
    artifact_match = exact_candidates[0]
    claim_id = _claim_id(artifact_match)
    structured_candidates = structured_by_claim_id.get(claim_id, [])
    if len(structured_candidates) != 1:
        _append_unique(audit, "ambiguous_bindings", call_id)
        return

    expected_taxonomy = [
        {"alpha_id": alpha.alpha_id, "alpha_name": alpha.name_en, "definition": alpha.core_thesis}
        for alpha in sorted(taxonomy.values(), key=lambda item: item.alpha_id)
    ]
    known_alpha_ids = {entry["alpha_id"] for entry in expected_taxonomy}
    if _as_dict_list(request.get("alpha_taxonomy")) != expected_taxonomy:
        _append_unique(audit, "artifact_decision_mismatches", call_id)
        return

    classifier = artifact_match.get("classifier")
    decision = str(output.get("decision") or "")
    selected = output.get("selected_alpha_id")
    output_matches = False
    if isinstance(classifier, dict) and classifier.get("used") is True:
        if decision == "select" and selected in known_alpha_ids:
            output_matches = (
                artifact_match.get("matched_alpha") == selected
                and artifact_match.get("match_status") == "matched"
                and classifier.get("status") == "llm_selected"
                and artifact_match.get("alpha_match_method") == "llm"
                and artifact_match.get("alpha_match_fallback_reason") is None
            )
        elif decision == "none":
            # Pure-LLM Alpha semantic authority: "none" is a genuine,
            # successful LLM semantic decision (matched_alpha=None is the
            # semantic answer, not a fallback) -- alpha_match_method is
            # "llm" here exactly as it is for "select", never
            # "deterministic_fallback"/"llm_unavailable" (those belong only
            # to a call that was never accepted, and per Exact Replay's own
            # upstream readiness gate never reaches bundle.semantic_calls).
            output_matches = (
                selected in (None, "")
                and artifact_match.get("matched_alpha") is None
                and artifact_match.get("match_status") == "no_match"
                and classifier.get("status") == "llm_none"
                and artifact_match.get("alpha_match_method") == "llm"
                and artifact_match.get("alpha_match_fallback_reason") is None
            )
    if not output_matches:
        _append_unique(audit, "artifact_decision_mismatches", call_id)
        return
    _register_binding(
        audit=audit,
        call_id=call_id,
        task="alpha_classifier",
        decision_keys=[f"alpha:{claim_id}"],
        decision_owners=decision_owners,
    )


def _bind_evidence_stance(
    record: dict[str, Any],
    *,
    audit: dict[str, Any],
    alpha_matches_by_claim_id: dict[str, list[dict[str, Any]]],
    taxonomy: dict[str, Any],
    decision_owners: dict[str, list[str]],
) -> None:
    """A B1 evidence_stance_classifier call does not produce its own
    artifact -- it mutates candidate diagnostic dicts already inside
    alpha_matches.json's matches[].candidate_scores. One call may bind to
    several (claim_id, target_alpha_id) artifact locations (task spec
    section 7); every requested item must bind for the call itself to
    register as bound (section 7/8), matching _bind_adapter's existing
    multi-segment-per-call pattern.

    Candidate lookup uses candidate_scores exclusively -- the same, and
    only, surface evidence_stance_llm._candidate_for_alpha itself reads
    (never eligible_candidates/top_candidates, and never an assumption that
    the target Alpha was deterministically admitted -- task spec section
    13: the Alpha Mapper is LLM-primary now, so a bound target_alpha_id may
    be absent from deterministic eligible_candidates entirely).

    Per-item expected outcome is derived by re-applying
    evidence_stance_llm's own contract-only validator
    (_validate_response_item) to the persisted response item -- never a
    semantic re-judgment, never a Provider call, never deterministic B1
    recomputation (task spec section 15): purely replaying the same
    structural/vocabulary/counter-Alpha-legality check production already
    applied to this exact persisted (request, response) pair.
    """
    call_id = str(record.get("call_id") or "")
    request = record.get("input_payload")
    output = record.get("validated_output")
    if not isinstance(request, dict) or not isinstance(output, dict):
        _append_unique(audit, "artifact_decision_mismatches", call_id)
        return
    requested_items = _as_dict_list(request.get("items"))
    returned_items = _as_dict_list(output.get("items"))
    if not requested_items:
        _append_unique(audit, "artifact_decision_mismatches", call_id)
        return

    requested_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for item in requested_items:
        key = (str(item.get("claim_id") or ""), str(item.get("target_alpha_id") or ""))
        if key == ("", "") or key in requested_by_key:
            _append_unique(audit, "artifact_decision_mismatches", call_id)
            return
        requested_by_key[key] = item

    returned_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    duplicate_keys: set[tuple[str, str]] = set()
    for item in returned_items:
        if not isinstance(item, dict):
            continue
        key = (str(item.get("claim_id") or ""), str(item.get("target_alpha_id") or ""))
        if key not in requested_by_key:
            continue  # extra unrequested result -- never admitted, mirrors production's own rule
        if key in returned_by_key:
            duplicate_keys.add(key)
        else:
            returned_by_key[key] = item

    decision_keys: list[str] = []
    for claim_id, target_alpha_id in requested_by_key:
        item_label = f"{call_id}:{claim_id}:{target_alpha_id}"
        match_candidates = alpha_matches_by_claim_id.get(claim_id, [])
        if not match_candidates:
            _append_unique(audit, "missing_bindings", item_label)
            continue
        if len(match_candidates) != 1:
            _append_unique(audit, "ambiguous_bindings", item_label)
            continue
        artifact_match = match_candidates[0]

        candidate_hits = [
            candidate
            for candidate in _as_dict_list(artifact_match.get("candidate_scores"))
            if str(candidate.get("alpha_id") or "") == target_alpha_id
        ]
        if not candidate_hits:
            _append_unique(audit, "missing_bindings", item_label)
            continue
        if len(candidate_hits) != 1:
            _append_unique(audit, "ambiguous_bindings", item_label)
            continue
        artifact_candidate = candidate_hits[0]

        key = (claim_id, target_alpha_id)
        if key in duplicate_keys:
            expected_llm = False
            expected_reason = FALLBACK_DUPLICATE_RESULT
            expected_stance = expected_counter = None
        else:
            returned = returned_by_key.get(key)
            if returned is None:
                expected_llm = False
                expected_reason = FALLBACK_MISSING_RESULT
                expected_stance = expected_counter = None
            else:
                # payload/candidate are unused by _validate_response_item
                # (identity/vocabulary/counter-Alpha legality only) --
                # empty placeholders satisfy the real production type
                # without fabricating request/artifact content.
                pseudo_requested = StanceRequestItem(claim_id, target_alpha_id, {}, {})
                stance, counter_alpha_id, fallback_reason = _validate_response_item(
                    pseudo_requested, returned, taxonomy
                )
                if fallback_reason is not None:
                    expected_llm = False
                    expected_reason = fallback_reason
                    expected_stance = expected_counter = None
                else:
                    expected_llm = True
                    expected_reason = None
                    expected_stance, expected_counter = stance, counter_alpha_id

        if expected_llm:
            # Direct semantic decision (evidence_stance, counter_alpha_id)
            # plus the deterministic provenance/side-effect fields
            # _apply_llm_result always stamps on acceptance -- never a
            # second independent semantic judgment (task spec section 6).
            item_matches = (
                artifact_candidate.get("stance_method") == STANCE_METHOD_LLM
                and artifact_candidate.get("evidence_stance") == expected_stance
                and artifact_candidate.get("counter_alpha_id") == expected_counter
                and artifact_candidate.get("stance_fallback_reason") is None
                and artifact_candidate.get("evidence_stance_version") == LLM_CLASSIFIER_VERSION
                and artifact_candidate.get("stance_reason_codes") == []
                and artifact_candidate.get("stance_confidence_band") is None
                and artifact_candidate.get("requires_manual_review") is False
            )
        else:
            # Provenance only -- the fallback evidence_stance value itself
            # was produced by the earlier, separate deterministic.v1 pass,
            # not recomputed here (task spec section 15).
            item_matches = (
                artifact_candidate.get("stance_method") == STANCE_METHOD_DETERMINISTIC_FALLBACK
                and artifact_candidate.get("stance_fallback_reason") == expected_reason
            )
        if not item_matches:
            _append_unique(audit, "artifact_decision_mismatches", item_label)
            continue
        decision_keys.append(f"evidence_stance:{claim_id}:{target_alpha_id}")

    if len(decision_keys) == len(requested_by_key):
        _register_binding(
            audit=audit,
            call_id=call_id,
            task="evidence_stance_classifier",
            decision_keys=decision_keys,
            decision_owners=decision_owners,
        )
    elif not any(call_id in str(value) for value in audit["missing_bindings"]):
        _append_unique(audit, "orphan_records", call_id)


def _bind_extractor(
    record: dict[str, Any],
    *,
    bundle: ExactSemanticSourceBundle,
    audit: dict[str, Any],
    structured_by_claim_id: dict[str, list[dict[str, Any]]],
    extracted_edges: list[dict[str, Any]],
    decision_owners: dict[str, list[str]],
) -> None:
    call_id = str(record.get("call_id") or "")
    request = record.get("input_payload")
    output = record.get("validated_output")
    if not isinstance(request, dict) or not isinstance(output, dict):
        _append_unique(audit, "artifact_decision_mismatches", call_id)
        return
    claim_id = str(request.get("claim_id") or "")
    source_records = structured_by_claim_id.get(claim_id, [])
    if not source_records:
        _append_unique(audit, "missing_bindings", call_id)
        return
    if len(source_records) != 1:
        _append_unique(audit, "ambiguous_bindings", call_id)
        return
    source_record = source_records[0]
    if (
        request.get("claim") != source_record.get("claim")
        or request.get("evidence") != source_record.get("evidence")
    ):
        _append_unique(audit, "artifact_decision_mismatches", call_id)
        return
    provider_edges = _as_dict_list(output.get("edges"))
    artifact_edges = [
        edge
        for edge in extracted_edges
        if str(edge.get("source_record_id") or "") == claim_id
        and edge.get("extraction_method") == "llm_strict_json"
    ]
    if bool(provider_edges) != bool(artifact_edges):
        _append_unique(audit, "artifact_decision_mismatches", call_id)
        return

    expected_identities = []
    for edge in provider_edges:
        source_factor = str(edge.get("source_factor") or "")
        target_factor = str(edge.get("target_factor") or "")
        if source_factor not in request.get("allowed_factors", []) or target_factor not in request.get(
            "allowed_factors", []
        ):
            _append_unique(audit, "artifact_decision_mismatches", call_id)
            return
        source_label = _display_factor(source_factor, bundle.ticker)
        target_label = _display_factor(target_factor, bundle.ticker)
        expected_identities.append(
            (
                _slug(source_label),
                _slug(target_label),
                str(edge.get("edge_type") or ""),
                round(float(edge.get("confidence")), 4),
            )
        )
    actual_identities = [
        (
            str(edge.get("source") or ""),
            str(edge.get("target") or ""),
            str(edge.get("edge_type") or ""),
            round(float(edge.get("confidence")), 4),
        )
        for edge in artifact_edges
    ]
    if Counter(expected_identities) != Counter(actual_identities):
        _append_unique(audit, "artifact_decision_mismatches", call_id)
        return
    _register_binding(
        audit=audit,
        call_id=call_id,
        task="structure_extractor",
        decision_keys=[f"structure:{claim_id}"],
        decision_owners=decision_owners,
    )


def build_semantic_binding_audit(
    bundle: ExactSemanticSourceBundle,
) -> dict[str, Any]:
    """Build a complete binding report without weakening any mismatch."""

    audit = _new_audit(bundle)
    structured = _as_dict_list(bundle.structured_agent_outputs.get("records"))
    alpha_matches = _as_dict_list(bundle.alpha_matches.get("matches"))
    extracted_edges = _as_dict_list(bundle.extracted_structures.get("edges"))
    taxonomy = load_alpha_taxonomy()

    structured_by_segment: dict[str, list[dict[str, Any]]] = defaultdict(list)
    structured_by_claim_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in structured:
        segment_id = _adapter_segment_id(item)
        if segment_id:
            structured_by_segment[segment_id].append(item)
        if _claim_id(item):
            structured_by_claim_id[_claim_id(item)].append(item)

    alpha_matches_by_claim_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in alpha_matches:
        if _claim_id(item):
            alpha_matches_by_claim_id[_claim_id(item)].append(item)

    decision_owners: dict[str, list[str]] = {}
    for record in bundle.semantic_calls:
        call_id = str(record.get("call_id") or "")
        task = str(record.get("task") or "")
        # Task-support and version-identity validation are separate checks
        # (task spec section 9): an unrecognized task is never reported as
        # a version mismatch, and its version/hash is never even compared
        # against a nonexistent expected identity.
        if task not in _SUPPORTED_BINDING_TASKS:
            _append_unique(audit, "unsupported_tasks", call_id)
            continue
        if not _verify_binding_version(record, bundle):
            _append_unique(audit, "version_mismatches", call_id)
            continue
        if not _verify_record_hashes(record, audit):
            continue
        if task == "structured_adapter":
            _bind_adapter(
                record,
                bundle=bundle,
                audit=audit,
                structured_by_segment=structured_by_segment,
                decision_owners=decision_owners,
            )
        elif task == "alpha_classifier":
            _bind_alpha(
                record,
                audit=audit,
                structured_by_claim_id=structured_by_claim_id,
                alpha_matches=alpha_matches,
                taxonomy=taxonomy,
                decision_owners=decision_owners,
            )
        elif task == "structure_extractor":
            _bind_extractor(
                record,
                bundle=bundle,
                audit=audit,
                structured_by_claim_id=structured_by_claim_id,
                extracted_edges=extracted_edges,
                decision_owners=decision_owners,
            )
        elif task == "evidence_stance_classifier":
            _bind_evidence_stance(
                record,
                audit=audit,
                alpha_matches_by_claim_id=alpha_matches_by_claim_id,
                taxonomy=taxonomy,
                decision_owners=decision_owners,
            )

    for decision_key, owners in sorted(decision_owners.items()):
        if len(owners) > 1:
            _append_unique(
                audit,
                "ambiguous_bindings",
                {"artifact_decision_key": decision_key, "call_ids": sorted(owners)},
            )

    covered = set(decision_owners)
    expected_decisions = {
        f"structured:{_claim_id(item)}"
        for item in structured
        if item.get("extraction_method") == "llm_strict_json"
    }
    # Pre-existing staleness fixed in passing (same class as the FROZEN_HASHES
    # cleanup precedent): this status set still read the pre-Authority-
    # Migration "applied"/"confirmed_ambiguous" names, which no classifier
    # status value has produced since that migration shipped -- the set was
    # silently vacuous (never matched any real alpha_matches record, so a
    # genuinely missing alpha_classifier call binding could never be
    # flagged). Updated to the current Pure-LLM vocabulary's two successful,
    # accepted-decision status values.
    expected_decisions.update(
        f"alpha:{_claim_id(item)}"
        for item in alpha_matches
        if isinstance(item.get("classifier"), dict)
        and item["classifier"].get("used") is True
        and item["classifier"].get("status") in {"llm_selected", "llm_none"}
    )
    expected_decisions.update(
        f"structure:{str(item.get('source_record_id') or '')}"
        for item in extracted_edges
        if item.get("extraction_method") == "llm_strict_json"
    )
    # A candidate's stance_method is only ever "llm" as a direct, unambiguous
    # consequence of a real, accepted evidence_stance_classifier item (task
    # spec sections 4/6) -- mirrors the alpha_classifier expected-decision
    # rule above exactly. stance_method == "deterministic_fallback" is
    # deliberately excluded: a whole-batch fallback never reaches
    # bundle.semantic_calls at all (Exact Replay's own upstream readiness
    # gate requires every persisted call to be accepted), so requiring a
    # decision key for it here would always incorrectly report it missing.
    expected_decisions.update(
        f"evidence_stance:{_claim_id(match)}:{str(candidate.get('alpha_id') or '')}"
        for match in alpha_matches
        for candidate in _as_dict_list(match.get("candidate_scores"))
        if candidate.get("stance_method") == STANCE_METHOD_LLM
    )
    for missing in sorted(expected_decisions - covered):
        _append_unique(audit, "missing_bindings", missing)

    bound_ids = set(audit["bound_call_ids"])
    for record in bundle.semantic_calls:
        call_id = str(record.get("call_id") or "")
        if call_id not in bound_ids and not any(
            call_id in str(value)
            for field in (
                "missing_bindings",
                "ambiguous_bindings",
                "input_hash_mismatches",
                "output_hash_mismatches",
                "artifact_decision_mismatches",
                "version_mismatches",
                "unsupported_tasks",
            )
            for value in audit[field]
        ):
            _append_unique(audit, "orphan_records", call_id)

    invalid_owner_calls = {
        call_id for owners in decision_owners.values() if len(owners) > 1 for call_id in owners
    }
    audit["uniquely_bound_records"] = len(bound_ids - invalid_owner_calls)
    failure_fields = (
        "orphan_records",
        "missing_bindings",
        "ambiguous_bindings",
        "input_hash_mismatches",
        "output_hash_mismatches",
        "artifact_decision_mismatches",
        "version_mismatches",
        "unsupported_tasks",
    )
    audit["final_status"] = (
        BINDING_STATUS_PASS
        if audit["uniquely_bound_records"] == audit["total_semantic_records"]
        and not any(audit[field] for field in failure_fields)
        else BINDING_STATUS_FAIL
    )
    return audit


def verify_semantic_bindings(bundle: ExactSemanticSourceBundle) -> dict[str, Any]:
    """Return a PASS audit or raise the strongest stable failure code."""

    audit = build_semantic_binding_audit(bundle)
    if audit["final_status"] == BINDING_STATUS_PASS:
        return audit
    if audit["input_hash_mismatches"]:
        code = EXACT_REPLAY_SEMANTIC_INPUT_MISMATCH
    elif audit["unsupported_tasks"]:
        code = EXACT_REPLAY_SEMANTIC_TASK_UNSUPPORTED
    elif audit["output_hash_mismatches"] or audit["artifact_decision_mismatches"]:
        code = EXACT_REPLAY_SEMANTIC_OUTPUT_MISMATCH
    elif audit["version_mismatches"]:
        code = EXACT_REPLAY_SEMANTIC_VERSION_MISMATCH
    elif audit["ambiguous_bindings"]:
        code = EXACT_REPLAY_SEMANTIC_CALL_AMBIGUOUS
    elif audit["missing_bindings"]:
        code = EXACT_REPLAY_SEMANTIC_BINDING_MISSING
    else:
        code = EXACT_REPLAY_SEMANTIC_BINDING_ORPHAN
    raise ExactReplayError(code, details={"binding_audit": audit})


__all__ = [
    "BINDING_AUDIT_SCHEMA_VERSION",
    "BINDING_STATUS_PASS",
    "BINDING_STATUS_FAIL",
    "build_semantic_binding_audit",
    "verify_semantic_bindings",
]
