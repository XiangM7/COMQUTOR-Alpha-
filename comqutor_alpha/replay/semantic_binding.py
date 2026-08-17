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

from comqutor_alpha.replay.source_bundle import (
    EXACT_REPLAY_SEMANTIC_BINDING_MISSING,
    EXACT_REPLAY_SEMANTIC_BINDING_ORPHAN,
    EXACT_REPLAY_SEMANTIC_CALL_AMBIGUOUS,
    EXACT_REPLAY_SEMANTIC_INPUT_MISMATCH,
    EXACT_REPLAY_SEMANTIC_OUTPUT_MISMATCH,
    EXACT_REPLAY_SEMANTIC_VERSION_MISMATCH,
    ExactReplayError,
    ExactSemanticSourceBundle,
    sha256_canonical_json,
)

BINDING_AUDIT_SCHEMA_VERSION = "comqutor.semantic_binding_audit.v1"
BINDING_STATUS_PASS = "PASS"
BINDING_STATUS_FAIL = "FAIL"
_TASK_BINDING_VERSIONS = {
    "structured_adapter": (
        "week2.claim_batch_enrichment.v1",
        "c6822099e2171c6fbad72c36bf2881bcd59bd4d4ad2fc20e10ab62af50b5bfd9",
        "week2.claim_batch_enrichment.input.v1",
        "week2.claim_batch_enrichment.output.v1",
        None,
    ),
    "alpha_classifier": (
        "week2.alpha_classifier.v1",
        "f21a9a14007e7b1e5d60cba99671c9daa68f0a8dba4e539930782913c88a3e30",
        "week2.alpha_classifier.input.v1",
        "week2.alpha_classifier.output.v1",
        "alpha_taxonomy_v1",
    ),
    "structure_extractor": (
        "week2.structure_extractor.v1",
        "326622a1786be03909e3d6dbcfca5069fe3cd4b31f0aab2da36bf8be324edbbc",
        "week2.structure_extractor.input.v1",
        "week2.structure_extractor.output.v1",
        None,
    ),
}


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
    records_by_task = dict.fromkeys(
        ("structured_adapter", "alpha_classifier", "structure_extractor"), 0
    )
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


def _candidate_identity_matches(
    request_candidate: dict[str, Any], artifact_candidate: dict[str, Any]
) -> bool:
    if any(
        request_candidate.get(key) != artifact_candidate.get(key)
        for key in (
            "alpha_id",
            "alpha_name",
            "score",
            "relation",
            "matched_keywords",
            "matched_factors",
        )
    ):
        return False
    components = request_candidate.get("score_components")
    if not isinstance(components, dict):
        return False
    return components == {
        "keyword": artifact_candidate.get("keyword_score"),
        "factor": artifact_candidate.get("factor_score"),
        "direction": artifact_candidate.get("direction_score"),
        "semantic": artifact_candidate.get("semantic_score"),
    }


def _bind_alpha(
    record: dict[str, Any],
    *,
    audit: dict[str, Any],
    structured_by_claim_id: dict[str, list[dict[str, Any]]],
    alpha_matches: list[dict[str, Any]],
    decision_owners: dict[str, list[str]],
) -> None:
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

    artifact_candidates = _as_dict_list(artifact_match.get("eligible_candidates"))
    request_candidates = _as_dict_list(request.get("candidates"))
    allowed = sorted(str(value) for value in request.get("allowed_alpha_ids") or [])
    if (
        allowed != sorted(str(item.get("alpha_id") or "") for item in artifact_candidates)
        or len(request_candidates) != len(artifact_candidates)
        or not all(
            _candidate_identity_matches(left, right)
            for left, right in zip(request_candidates, artifact_candidates, strict=True)
        )
    ):
        _append_unique(audit, "artifact_decision_mismatches", call_id)
        return

    classifier = artifact_match.get("classifier")
    decision = str(output.get("decision") or "")
    selected = output.get("selected_alpha_id")
    output_matches = False
    if isinstance(classifier, dict) and classifier.get("used") is True:
        if decision == "select":
            output_matches = (
                selected in allowed
                and artifact_match.get("matched_alpha") == selected
                and artifact_match.get("match_status") == "matched"
                and classifier.get("status") == "applied"
            )
        elif decision == "defer":
            output_matches = (
                selected in (None, "")
                and artifact_match.get("matched_alpha") is None
                and artifact_match.get("match_status") == "ambiguous"
                and classifier.get("status") == "confirmed_ambiguous"
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

    structured_by_segment: dict[str, list[dict[str, Any]]] = defaultdict(list)
    structured_by_claim_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in structured:
        segment_id = _adapter_segment_id(item)
        if segment_id:
            structured_by_segment[segment_id].append(item)
        if _claim_id(item):
            structured_by_claim_id[_claim_id(item)].append(item)

    decision_owners: dict[str, list[str]] = {}
    for record in bundle.semantic_calls:
        call_id = str(record.get("call_id") or "")
        if not _verify_binding_version(record, bundle):
            _append_unique(audit, "version_mismatches", call_id)
            continue
        if not _verify_record_hashes(record, audit):
            continue
        task = record.get("task")
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
        else:
            _append_unique(audit, "version_mismatches", call_id)

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
    expected_decisions.update(
        f"alpha:{_claim_id(item)}"
        for item in alpha_matches
        if isinstance(item.get("classifier"), dict)
        and item["classifier"].get("used") is True
        and item["classifier"].get("status") in {"applied", "confirmed_ambiguous"}
    )
    expected_decisions.update(
        f"structure:{str(item.get('source_record_id') or '')}"
        for item in extracted_edges
        if item.get("extraction_method") == "llm_strict_json"
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
