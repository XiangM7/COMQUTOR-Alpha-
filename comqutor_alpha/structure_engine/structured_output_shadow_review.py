"""Deterministic Shadow comparison signals and blank human-review templates."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

SHADOW_COMPARISON_SCHEMA_VERSION = "comqutor.structured_claim_shadow_comparison.v1"
SHADOW_REVIEW_TEMPLATE_VERSION = "comqutor.structured_claim_shadow_review.v1"

REVIEW_CSV_FIELDS = (
    "review_row_id",
    "source_run_id",
    "ticker",
    "agent",
    "agent_output_id",
    "source_report_sha256",
    "legacy_record_id",
    "shadow_claim_id",
    "review_dimension",
    "review_label",
    "severity",
    "reviewer",
    "review_timestamp",
    "notes",
)

REVIEW_LABELS = {
    "claim_boundary": (
        "correct",
        "over_merged",
        "over_split",
        "missing_claim",
        "spurious_claim",
        "uncertain",
    ),
    "evidence_pairing": (
        "correct",
        "partially_supported",
        "wrong_evidence",
        "missing_evidence",
        "invented_evidence",
        "uncertain",
    ),
    "semantic_fidelity": (
        "correct",
        "meaning_distorted",
        "negation_error",
        "modality_error",
        "attribution_error",
        "temporal_error",
        "uncertain",
    ),
    "entity_extraction": ("correct", "partial", "incorrect", "not_applicable", "uncertain"),
    "factor_extraction": ("correct", "partial", "incorrect", "not_applicable", "uncertain"),
    "direction": ("correct", "incorrect", "unclear", "not_applicable"),
    "overall_disposition": ("accept", "accept_with_minor_edit", "revise", "reject", "abstain"),
}
REVIEW_SEVERITIES = ("critical", "major", "minor", "none")


def _normalized_exact(value: Any) -> str:
    text = str(value or "").casefold()
    text = re.sub(r"[^\w%$]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def _records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    if isinstance(value, Mapping):
        for key in ("records", "structured_outputs", "agent_outputs", "claims"):
            nested = value.get(key)
            if isinstance(nested, list):
                return [dict(item) for item in nested if isinstance(item, Mapping)]
    return []


def _legacy_id(record: Mapping[str, Any], index: int) -> str:
    for key in ("claim_id", "record_id", "agent_output_id"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    digest = hashlib.sha256(
        f"{index}\n{record.get('claim', '')}\n{record.get('evidence', '')}".encode()
    ).hexdigest()
    return f"legacy-navigation-{digest[:20]}"


def _duplicates(records: Sequence[Mapping[str, Any]]) -> int:
    values = [(_normalized_exact(item.get("claim")), _normalized_exact(item.get("evidence"))) for item in records]
    return len(values) - len(set(values))


def _set_delta(
    legacy: Sequence[Mapping[str, Any]], shadow: Sequence[Mapping[str, Any]], field: str
) -> dict[str, list[str]]:
    legacy_values = {
        str(value)
        for record in legacy
        for value in (record.get(field) or [])
        if isinstance(value, str)
    }
    shadow_values = {
        str(value)
        for record in shadow
        for value in (record.get(field) or [])
        if isinstance(value, str)
    }
    return {
        "legacy_only": sorted(legacy_values - shadow_values),
        "shadow_only": sorted(shadow_values - legacy_values),
        "shared": sorted(legacy_values & shadow_values),
    }


def compare_legacy_and_shadow(
    legacy_outputs: Any, shadow_bundle: Mapping[str, Any]
) -> dict[str, Any]:
    """Emit navigation signals only; no signal is a gold label or semantic error."""

    legacy = _records(legacy_outputs)
    shadow = _records(shadow_bundle.get("claims") or [])
    legacy_rows = [(_legacy_id(record, index), record) for index, record in enumerate(legacy)]
    shadow_ids = [str(record.get("shadow_claim_id") or "") for record in shadow]

    overlaps: list[dict[str, str]] = []
    matched_legacy: set[str] = set()
    matched_shadow: set[str] = set()
    for legacy_id, legacy_record in legacy_rows:
        for shadow_record in shadow:
            shadow_id = str(shadow_record.get("shadow_claim_id") or "")
            claim_equal = _normalized_exact(legacy_record.get("claim")) == _normalized_exact(
                shadow_record.get("claim")
            )
            evidence_equal = _normalized_exact(legacy_record.get("evidence")) == _normalized_exact(
                shadow_record.get("evidence")
            )
            if claim_equal or evidence_equal:
                basis = "claim_and_evidence" if claim_equal and evidence_equal else (
                    "claim" if claim_equal else "evidence"
                )
                overlaps.append(
                    {
                        "legacy_record_id": legacy_id,
                        "shadow_claim_id": shadow_id,
                        "overlap_basis": basis,
                        "interpretation": "comparison_signal_not_quality_judgment",
                    }
                )
                matched_legacy.add(legacy_id)
                matched_shadow.add(shadow_id)

    lineage: list[dict[str, Any]] = []
    candidate_to_claims: dict[str, list[str]] = {}
    for record in shadow:
        claim_id = str(record.get("shadow_claim_id") or "")
        candidate_ids = [
            str(value) for value in record.get("candidate_segment_ids") or [] if isinstance(value, str)
        ]
        lineage.append({"shadow_claim_id": claim_id, "candidate_segment_ids": candidate_ids})
        for candidate_id in candidate_ids:
            candidate_to_claims.setdefault(candidate_id, []).append(claim_id)

    potential_over_merge = [
        {
            "shadow_claim_id": str(record.get("shadow_claim_id") or ""),
            "candidate_segment_ids": list(record.get("candidate_segment_ids") or []),
            "classification": "diagnostic_candidate",
        }
        for record in shadow
        if len(set(record.get("candidate_segment_ids") or [])) > 1
    ]
    potential_over_split = [
        {
            "candidate_segment_id": candidate_id,
            "shadow_claim_ids": sorted(set(claim_ids)),
            "classification": "diagnostic_candidate",
        }
        for candidate_id, claim_ids in sorted(candidate_to_claims.items())
        if len(set(claim_ids)) > 1
    ]
    direction_delta = []
    by_legacy_id = dict(legacy_rows)
    by_shadow_id = {
        str(record.get("shadow_claim_id") or ""): record for record in shadow
    }
    for overlap in overlaps:
        legacy_record = by_legacy_id[overlap["legacy_record_id"]]
        shadow_record = by_shadow_id[overlap["shadow_claim_id"]]
        if legacy_record.get("direction") != shadow_record.get("direction"):
            direction_delta.append(
                {
                    "legacy_record_id": overlap["legacy_record_id"],
                    "shadow_claim_id": overlap["shadow_claim_id"],
                    "legacy_direction": legacy_record.get("direction"),
                    "shadow_direction": shadow_record.get("direction"),
                    "classification": "comparison_signal",
                }
            )

    validation_summary = shadow_bundle.get("validation_summary")
    if not isinstance(validation_summary, Mapping):
        validation_summary = {}
    return {
        "schema_version": SHADOW_COMPARISON_SCHEMA_VERSION,
        "source_run_id": shadow_bundle.get("run_id"),
        "ticker": shadow_bundle.get("ticker"),
        "agent": shadow_bundle.get("agent"),
        "agent_output_id": shadow_bundle.get("agent_output_id"),
        "source_report_sha256": shadow_bundle.get("source_report_sha256"),
        "classification": "comparison_signals_and_diagnostic_candidates_only",
        "semantic_quality_judgment": False,
        "gold_labels": False,
        "legacy_claim_count": len(legacy),
        "shadow_claim_count": len(shadow),
        "exact_text_overlaps": overlaps,
        "candidate_to_shadow_lineage": lineage,
        "potential_legacy_over_merge": potential_over_merge,
        "potential_legacy_over_split": potential_over_split,
        "unmatched_legacy_claims": [
            legacy_id for legacy_id, _record in legacy_rows if legacy_id not in matched_legacy
        ],
        "unmatched_shadow_claims": [claim_id for claim_id in shadow_ids if claim_id not in matched_shadow],
        "evidence_span_validation": {
            "validator_status": validation_summary.get("status", "unknown"),
            "validator_valid": validation_summary.get("valid", False),
        },
        "entity_set_delta": _set_delta(legacy, shadow, "entities"),
        "factor_set_delta": _set_delta(legacy, shadow, "factors"),
        "direction_delta": direction_delta,
        "duplicate_counts": {"legacy": _duplicates(legacy), "shadow": _duplicates(shadow)},
        "abstention_count": len(shadow_bundle.get("abstentions") or []),
        "validation_failures": list(validation_summary.get("reason_codes") or []),
        "shadow_only": True,
        "production_authority": False,
    }


def build_blank_review_rows(
    *,
    comparison: Mapping[str, Any],
    legacy_outputs: Any,
    shadow_bundle: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Create identity/navigation rows with every human judgment field blank."""

    legacy = _records(legacy_outputs)
    legacy_ids = [_legacy_id(record, index) for index, record in enumerate(legacy)] or [""]
    shadow_ids = [str(record.get("shadow_claim_id") or "") for record in _records(shadow_bundle.get("claims") or [])] or [""]
    pairs = {
        (str(item.get("legacy_record_id") or ""), str(item.get("shadow_claim_id") or ""))
        for item in comparison.get("exact_text_overlaps") or []
        if isinstance(item, Mapping)
    }
    if not pairs:
        pairs = {(legacy_id, "") for legacy_id in legacy_ids} | {("", shadow_id) for shadow_id in shadow_ids}
    rows = []
    for index, (legacy_id, shadow_id) in enumerate(sorted(pairs)):
        material = (
            f"{shadow_bundle.get('run_id', '')}\n{shadow_bundle.get('agent_output_id', '')}"
            f"\n{legacy_id}\n{shadow_id}\n{index}"
        )
        rows.append(
            {
                "review_row_id": f"review-row-{hashlib.sha256(material.encode('utf-8')).hexdigest()[:24]}",
                "source_run_id": str(shadow_bundle.get("run_id") or ""),
                "ticker": str(shadow_bundle.get("ticker") or ""),
                "agent": str(shadow_bundle.get("agent") or ""),
                "agent_output_id": str(shadow_bundle.get("agent_output_id") or ""),
                "source_report_sha256": str(shadow_bundle.get("source_report_sha256") or ""),
                "legacy_record_id": legacy_id,
                "shadow_claim_id": shadow_id,
                "review_dimension": "",
                "review_label": "",
                "severity": "",
                "reviewer": "",
                "review_timestamp": "",
                "notes": "",
            }
        )
    return rows


def render_blank_review_csv(rows: Iterable[Mapping[str, Any]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=REVIEW_CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: str(row.get(field) or "") for field in REVIEW_CSV_FIELDS})
    return buffer.getvalue()


__all__ = [
    "REVIEW_CSV_FIELDS",
    "REVIEW_LABELS",
    "REVIEW_SEVERITIES",
    "SHADOW_COMPARISON_SCHEMA_VERSION",
    "SHADOW_REVIEW_TEMPLATE_VERSION",
    "build_blank_review_rows",
    "compare_legacy_and_shadow",
    "render_blank_review_csv",
]
