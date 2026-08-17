"""Offline Phase 1 Master §5.1 v4 risk-based semantic review.

The Quality Gate is unchanged. Every claim receives deterministic triage;
all flagged claims and a deterministic stratified low-risk sample receive
sequential Codex semantic review. Deterministic-only rows are never described
as semantically or human reviewed. The original v4 CSV/HTML remain immutable.

This module has no Provider, gateway, cache, network, Redis, or database
dependency. It validates review provenance and coverage, computes the frozen
Quality Gate, and renders additive derivative artifacts.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from comqutor_alpha.evaluation.phase1_human_review_packet_v4 import (
    ALLOWED_REVIEW_VALUES,
    CSV_FIELDS as V4_CSV_FIELDS,
    REQUIRED_PROMPT_VERSION,
    REVIEW_FIELDS,
)

PACKET_SCHEMA_VERSION = "comqutor.phase1.risk_based_review_v4.v1"
REVIEW_METHOD = "RISK_BASED_HUMAN_REVIEW"
SCREENING_AUTHORITY_DETERMINISTIC = "DETERMINISTIC_FULL_CORPUS_TRIAGE"
SCREENING_AUTHORITY_CODEX = "CODEX_TARGETED_SEMANTIC_REVIEW"
SCREENING_AUTHORITY_OWNER = "PRODUCT_OWNER"

PROVENANCE_FAILURE = "RISK_BASED_REVIEW_V4_PROVENANCE_FAILURE"
COVERAGE_FAILURE = "RISK_BASED_REVIEW_V4_COVERAGE_FAILURE"

RISK_CLASSIFICATIONS = (
    "PASS",
    "MINOR",
    "MAJOR",
    "CRITICAL",
    "UPSTREAM_ONLY",
    "PRODUCT_DECISION_REQUIRED",
)

REASON_CODES = (
    "NONE",
    "EVIDENCE_ASSERTION_INCOMPLETE",
    "FACTOR_SEMANTIC_MISMATCH",
    "DIRECTION_SEMANTIC_MISMATCH",
    "UPSTREAM_REPORT_QUALITY_ISSUE",
    "CLAIM_BOUNDARY_MINOR",
    "UNCERTAINTY_COMPRESSION_MINOR",
    "OTHER_SEMANTIC_MINOR",
    "PRODUCT_DECISION_REQUIRED",
)

# New columns this module adds on top of the immutable v4 packet columns.
# REVIEW_FIELDS (semantic_fidelity .. notes) are the SAME existing columns
# the v4 packet already reserves -- here they are actually filled in
# (never left blank), unlike the pristine v4 packet.
RISK_REVIEW_FIELDS = (
    "triage_risk_flags",
    "semantic_reviewed",
    "semantic_review_scope",
    "risk_classification",
    "reason_code",
    "upstream_quality_issue",
    "recommend_owner_review",
    "adapter_quality_impact",
    *REVIEW_FIELDS,
    "review_method",
    "screening_authority",
    "product_owner_adjudicated",
)

_BASE_FIELDS = tuple(field for field in V4_CSV_FIELDS if field not in REVIEW_FIELDS)
CSV_FIELDS = (*_BASE_FIELDS, *RISK_REVIEW_FIELDS)

REQUIRED_VERDICT_FIELDS = (
    "review_row_id",
    "semantic_fidelity",
    "claim_boundary",
    "evidence_correctness",
    "entity_correctness",
    "factor_correctness",
    "direction_correctness",
    "critical_error_type",
    "risk_classification",
    "reason_code",
    "upstream_quality_issue",
    "recommend_owner_review",
    "notes",
    "triage_risk_flags",
    "semantic_reviewed",
    "semantic_review_scope",
    "screening_authority",
    "product_owner_adjudicated",
    "reviewer",
)

TRIAGE_FLAG_KNOWN_CANDIDATE = "KNOWN_PRIOR_AUDIT_CANDIDATE"
TRIAGE_FLAG_EPISTEMIC = "EPISTEMIC_MARKER_ASYMMETRY"
TRIAGE_FLAG_NEGATION = "NEGATION_MARKER_ASYMMETRY"
SEMANTIC_SCOPE_TARGETED = "TARGETED_FLAG_REVIEW"
SEMANTIC_SCOPE_SPOT_CHECK = "STRATIFIED_LOW_RISK_SPOT_CHECK"
SEMANTIC_SCOPE_NONE = "NOT_SEMANTICALLY_REVIEWED"

KNOWN_REVIEW_CANDIDATE_IDS = frozenset(
    {
        "phase1-review-v4-d150ab8158a8859b8db6bbbc",
        "phase1-review-v4-56513f93e10d8e9b8c010d60",
        "phase1-review-v4-43208b26e789ffa66e22aceb",
        "phase1-review-v4-c4e9f98e6356312bedb2dc63",
        "phase1-review-v4-6593b8f6068f6266d02a4200",
        "phase1-review-v4-a85c064d8b76509fe0868f1c",
        "phase1-review-v4-e7fab1e2fd30bc7bec6ad9d7",
        "phase1-review-v4-6e5b0ebdd3fb57e4d86aadc3",
        "phase1-review-v4-a55efe68ff8d71b6034c8833",
    }
)

_EPISTEMIC_MARKER = re.compile(
    r"\b(may|might|could|suggests?|appears?|likely|potential(?:ly)?|reportedly|"
    r"allegedly|analysts? (?:believe|expect)|expected to|described as)\b",
    re.IGNORECASE,
)
_NEGATION_MARKER = re.compile(
    r"\b(no|not|never|without|failed?|unlikely|cannot|can't|didn't|doesn't|won't)\b",
    re.IGNORECASE,
)

# The six frozen product-owner policy decisions (Phase 1 §5.1 v4 risk-based
# review task, section 8: "已有 Product Owner 决策必须记录"). These are
# authority for this and all future review passes -- never re-derived or
# re-asked.
FROZEN_PRODUCT_OWNER_POLICIES: dict[str, dict[str, str]] = {
    "DIRECTION_POLICY": {
        "value": "SEMANTIC_JUDGMENT_ALLOWED",
        "description": (
            "Direction may be set by LLM semantic judgment from claim + "
            "evidence + context, even for a bare numeric fact with no "
            "explicit sentiment word. Not mechanically forced to neutral "
            "just because the evidence is 'only a number'. Wrong only when "
            "the assigned direction is clearly opposite to the claim's "
            "meaning."
        ),
    },
    "FACTOR_POLICY": {
        "value": "STRICT_SEMANTIC_MATCH_OR_EMPTY",
        "description": (
            "A factor label must be a genuine semantic match, never a "
            "same-neighborhood guess (e.g. Net Margin must not be forced "
            "onto Revenue Growth just because both are financial metrics). "
            "An empty/unknown factor list when no label truly fits is "
            "correct behavior, not a defect -- factor extraction is "
            "best-effort, not mandatory forced classification, because a "
            "wrong factor pollutes the downstream §5.2 Alpha Mapper."
        ),
    },
    "UPSTREAM_ERROR_POLICY": {
        "value": "SEPARATE_FROM_ADAPTER_SEMANTIC_FAILURE",
        "description": (
            "Structured Output Adapter's job is faithful structuring of "
            "what the TradingAgents report says, not fact-checking "
            "TradingAgents. A source-report math/factual/logic/"
            "interpretation error that the Structured Claim faithfully "
            "represents is UPSTREAM_ONLY, not a semantic-fidelity failure "
            "-- but a claim that itself distorts a correct source is still "
            "a real §5.1 error."
        ),
    },
    "EVIDENCE_POLICY": {
        "value": "ASSERTION_COMPLETE_MULTI_SPAN_ALLOWED",
        "description": (
            "Every material assertion in a claim needs at least one "
            "admitted supporting quote (its own, or a quote covering "
            "several assertions at once). An assertion supported only by "
            "context (never admitted as evidence) is "
            "evidence_correctness=PARTIAL, default severity MINOR (MAJOR "
            "only if the missing part changes core meaning). Evidence "
            "should be minimal sufficient evidence, not the whole "
            "surrounding paragraph."
        ),
    },
    "UNCERTAINTY_POLICY": {
        "value": "MATERIAL_EPISTEMIC_STRENGTH_MUST_BE_PRESERVED",
        "description": (
            "Hedging language (suggests/may/could/reportedly/analysts "
            "believe) must survive into the claim at comparable epistemic "
            "strength. Slight, immaterial tightening is MINOR; a clear "
            "reversal (e.g. 'may X' -> 'X definitely happened') is "
            "ATTRIBUTION_LOSS, ordinarily CRITICAL."
        ),
    },
    "EXACT_MATCH_POLICY": {
        "value": "PROVENANCE_ONLY_NEVER_AUTO_PASS_SEMANTIC_SUPPORT",
        "description": (
            "The deterministic EvidenceQuoteResolver's exact-match success "
            "proves the quote is real, unique, verbatim report text. It "
            "proves nothing about semantic support. evidence_correctness "
            "is never auto-set to PASS merely because the quote resolved; "
            "an exact quote from the wrong section/metric/period is still "
            "FABRICATED_EVIDENCE."
        ),
    },
}

# Verbatim thresholds from docs/specs/phase1_master_execution_contract_v1.md
# section "Phase 1 Quality Gate (`QUALITY_GATE`)" -- not invented here and
# not altered by the RISK_BASED_HUMAN_REVIEW methodology change, which
# supersedes only how the underlying judgments are produced.
GATE_THRESHOLDS: dict[str, float | int] = {
    "disposition_accept_rate_min": 0.85,
    "semantic_fidelity_correct_rate_min": 0.90,
    "evidence_pairing_correct_rate_min": 0.90,
    "claim_boundary_correct_rate_min": 0.85,
    "critical_severity_errors_max": 0,
    "major_plus_critical_rate_max": 0.05,
    "overall_rejection_abstention_rate_max": 0.25,
    "per_family_rejection_abstention_rate_max": 0.40,
}

GATE_THRESHOLDS_SOURCE = (
    "docs/specs/phase1_master_execution_contract_v1.md#Phase-1-Quality-Gate"
)


class RiskBasedReviewError(RuntimeError):
    """Fail-closed error with a stable reason code."""

    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(f"{reason_code}: {detail}")
        self.reason_code = reason_code
        self.detail = detail


def deterministic_triage_flags(row: Mapping[str, str]) -> tuple[str, ...]:
    """Return cheap, explainable risk flags without making a semantic verdict."""

    flags: list[str] = []
    if row.get("review_row_id") in KNOWN_REVIEW_CANDIDATE_IDS:
        flags.append(TRIAGE_FLAG_KNOWN_CANDIDATE)
    claim = row.get("claim_text", "")
    evidence = row.get("source_evidence_text", "")
    if bool(_EPISTEMIC_MARKER.search(claim)) != bool(_EPISTEMIC_MARKER.search(evidence)):
        flags.append(TRIAGE_FLAG_EPISTEMIC)
    if bool(_NEGATION_MARKER.search(claim)) != bool(_NEGATION_MARKER.search(evidence)):
        flags.append(TRIAGE_FLAG_NEGATION)
    return tuple(flags)


def select_stratified_low_risk_sample(
    rows: Sequence[Mapping[str, str]],
    triage_by_row_id: Mapping[str, Sequence[str]],
    *,
    per_stratum: int = 2,
) -> tuple[str, ...]:
    """Select a stable sample per represented ticker/report-family stratum."""

    strata: dict[tuple[str, str], list[Mapping[str, str]]] = defaultdict(list)
    for row in rows:
        if triage_by_row_id.get(row["review_row_id"]):
            continue
        strata[(row["ticker"], row["report_family"])].append(row)
    selected: list[str] = []
    for stratum in sorted(strata):
        ranked = sorted(
            strata[stratum],
            key=lambda row: hashlib.sha256(
                f"phase1-v4-risk-sample|{row['review_row_id']}".encode()
            ).hexdigest(),
        )
        selected.extend(row["review_row_id"] for row in ranked[:per_stratum])
    return tuple(selected)


def map_risk_classification(risk_classification: str) -> dict[str, str]:
    """Deterministic mapping from the holistic risk_classification to the
    existing overall_disposition/severity vocabulary, so the disposition and
    severity strings are never independently agent-chosen (avoiding
    inconsistent combinations) -- only risk_classification itself, plus the
    six per-dimension judgments, are genuine per-claim AI judgments."""

    if risk_classification == "PASS":
        return {
            "overall_disposition": "ACCEPT",
            "severity": "NONE",
            "adapter_quality_impact": "NONE",
        }
    if risk_classification == "MINOR":
        return {
            "overall_disposition": "ACCEPT_WITH_MINOR_ISSUE",
            "severity": "MINOR",
            "adapter_quality_impact": "MINOR_ADAPTER_ISSUE",
        }
    if risk_classification == "MAJOR":
        return {
            "overall_disposition": "REJECT",
            "severity": "MAJOR",
            "adapter_quality_impact": "MAJOR_ADAPTER_ISSUE",
        }
    if risk_classification == "CRITICAL":
        return {
            "overall_disposition": "REJECT",
            "severity": "CRITICAL",
            "adapter_quality_impact": "CRITICAL_ADAPTER_ISSUE",
        }
    if risk_classification == "UPSTREAM_ONLY":
        # RULE E / UPSTREAM_ERROR_POLICY: faithful structuring of a bad
        # source is not an adapter defect -- from the adapter's own
        # quality perspective this is a clean accept.
        return {
            "overall_disposition": "ACCEPT",
            "severity": "NONE",
            "adapter_quality_impact": "NOT_ADAPTER_UPSTREAM_SOURCE",
        }
    if risk_classification == "PRODUCT_DECISION_REQUIRED":
        # Deliberately left undetermined -- never forced into ACCEPT/REJECT
        # or NONE/MAJOR. A real product-owner adjudication resolves this,
        # not this mapping.
        return {
            "overall_disposition": "",
            "severity": "",
            "adapter_quality_impact": "PENDING_ADJUDICATION",
        }
    raise ValueError(f"unknown risk_classification: {risk_classification}")


def _validate_verdict(verdict: Mapping[str, Any]) -> None:
    row_id = verdict.get("review_row_id")
    missing = [field for field in REQUIRED_VERDICT_FIELDS if field not in verdict]
    if missing:
        raise RiskBasedReviewError(
            PROVENANCE_FAILURE, f"verdict_missing_fields:{row_id}:{missing}"
        )
    for field in (
        "semantic_fidelity",
        "claim_boundary",
        "evidence_correctness",
        "entity_correctness",
        "factor_correctness",
        "direction_correctness",
        "critical_error_type",
    ):
        value = verdict[field]
        if value not in ALLOWED_REVIEW_VALUES[field]:
            raise RiskBasedReviewError(
                PROVENANCE_FAILURE,
                f"verdict_value_not_in_vocabulary:{row_id}:{field}:{value}",
            )
    if verdict["risk_classification"] not in RISK_CLASSIFICATIONS:
        raise RiskBasedReviewError(
            PROVENANCE_FAILURE,
            f"invalid_risk_classification:{row_id}:{verdict['risk_classification']}",
        )
    if verdict["reason_code"] not in REASON_CODES:
        raise RiskBasedReviewError(
            PROVENANCE_FAILURE, f"invalid_reason_code:{row_id}:{verdict['reason_code']}"
        )
    if not isinstance(verdict["upstream_quality_issue"], bool):
        raise RiskBasedReviewError(
            PROVENANCE_FAILURE, f"upstream_quality_issue_not_bool:{row_id}"
        )
    if not isinstance(verdict["recommend_owner_review"], bool):
        raise RiskBasedReviewError(
            PROVENANCE_FAILURE, f"recommend_owner_review_not_bool:{row_id}"
        )
    if not isinstance(verdict["semantic_reviewed"], bool):
        raise RiskBasedReviewError(PROVENANCE_FAILURE, f"semantic_reviewed_not_bool:{row_id}")
    if not isinstance(verdict["product_owner_adjudicated"], bool):
        raise RiskBasedReviewError(
            PROVENANCE_FAILURE, f"product_owner_adjudicated_not_bool:{row_id}"
        )
    if not isinstance(verdict["triage_risk_flags"], list):
        raise RiskBasedReviewError(PROVENANCE_FAILURE, f"triage_risk_flags_not_list:{row_id}")
    authority = verdict["screening_authority"]
    allowed_authorities = {
        SCREENING_AUTHORITY_DETERMINISTIC,
        SCREENING_AUTHORITY_CODEX,
        SCREENING_AUTHORITY_OWNER,
    }
    if authority not in allowed_authorities:
        raise RiskBasedReviewError(PROVENANCE_FAILURE, f"invalid_screening_authority:{row_id}")
    if verdict["semantic_reviewed"] and authority == SCREENING_AUTHORITY_DETERMINISTIC:
        raise RiskBasedReviewError(PROVENANCE_FAILURE, f"semantic_review_authority_mismatch:{row_id}")
    if verdict["product_owner_adjudicated"] != (authority == SCREENING_AUTHORITY_OWNER):
        raise RiskBasedReviewError(PROVENANCE_FAILURE, f"owner_authority_mismatch:{row_id}")
    if verdict["risk_classification"] != "PASS" and not str(verdict.get("notes", "")).strip():
        raise RiskBasedReviewError(PROVENANCE_FAILURE, f"missing_notes_for_non_pass:{row_id}")
    if verdict["risk_classification"] == "UPSTREAM_ONLY" and (
        verdict["semantic_fidelity"] != "PASS" or not verdict["upstream_quality_issue"]
    ):
        # UPSTREAM_ERROR_POLICY consistency: the adapter's own semantic
        # fidelity must read PASS when the defect is attributed upstream.
        raise RiskBasedReviewError(PROVENANCE_FAILURE, f"upstream_only_inconsistent:{row_id}")
    if verdict["critical_error_type"] != "NONE" and verdict["risk_classification"] not in (
        "MAJOR",
        "CRITICAL",
        "PRODUCT_DECISION_REQUIRED",
    ):
        raise RiskBasedReviewError(
            PROVENANCE_FAILURE,
            f"critical_error_type_without_major_or_critical_classification:{row_id}",
        )


def merge_verdicts(
    original_rows: Sequence[Mapping[str, str]],
    verdicts_by_row_id: Mapping[str, Mapping[str, Any]],
    *,
    generated_at: str,
    ai_reviewer_label: str | None = None,
) -> list[dict[str, Any]]:
    """Fail closed unless every original row has exactly one verdict, and
    every verdict is vocabulary-valid. Never silently drops or invents a
    row."""

    original_ids = [row["review_row_id"] for row in original_rows]
    original_id_set = set(original_ids)
    if len(original_id_set) != len(original_ids):
        raise RiskBasedReviewError(COVERAGE_FAILURE, "duplicate_review_row_id_in_original")
    verdict_ids = set(verdicts_by_row_id)
    if original_id_set != verdict_ids:
        missing = sorted(original_id_set - verdict_ids)
        unexpected = sorted(verdict_ids - original_id_set)
        raise RiskBasedReviewError(
            COVERAGE_FAILURE,
            f"verdict_coverage_mismatch:missing={len(missing)}:unexpected={len(unexpected)}:"
            f"missing_sample={missing[:5]}:unexpected_sample={unexpected[:5]}",
        )

    merged: list[dict[str, Any]] = []
    for row in original_rows:
        row_id = row["review_row_id"]
        verdict = verdicts_by_row_id[row_id]
        _validate_verdict(verdict)
        risk_classification = verdict["risk_classification"]
        mapped = map_risk_classification(risk_classification)
        merged_row: dict[str, Any] = dict(row)
        merged_row.update(
            {
                "semantic_fidelity": verdict["semantic_fidelity"],
                "claim_boundary": verdict["claim_boundary"],
                "evidence_correctness": verdict["evidence_correctness"],
                "entity_correctness": verdict["entity_correctness"],
                "factor_correctness": verdict["factor_correctness"],
                "direction_correctness": verdict["direction_correctness"],
                "critical_error_type": verdict["critical_error_type"],
                "overall_disposition": mapped["overall_disposition"],
                "severity": mapped["severity"],
                "reviewer": verdict["reviewer"] or ai_reviewer_label or "",
                "review_timestamp": generated_at,
                "notes": str(verdict.get("notes", "")),
                "triage_risk_flags": ";".join(verdict["triage_risk_flags"]),
                "semantic_reviewed": "true" if verdict["semantic_reviewed"] else "false",
                "semantic_review_scope": verdict["semantic_review_scope"],
                "risk_classification": risk_classification,
                "reason_code": verdict["reason_code"],
                "upstream_quality_issue": "true" if verdict["upstream_quality_issue"] else "false",
                "recommend_owner_review": "true" if verdict["recommend_owner_review"] else "false",
                "adapter_quality_impact": mapped["adapter_quality_impact"],
                "review_method": REVIEW_METHOD,
                "screening_authority": verdict["screening_authority"],
                "product_owner_adjudicated": (
                    "true" if verdict["product_owner_adjudicated"] else "false"
                ),
            }
        )
        merged.append(merged_row)
    return merged


def select_adjudication_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Only PRODUCT_DECISION_REQUIRED rows plus MAJOR/CRITICAL rows the
    screening itself flagged as a genuine boundary call -- never every
    MAJOR/CRITICAL finding, and never a clean PASS/MINOR/UPSTREAM_ONLY."""

    return [
        row
        for row in rows
        if row["risk_classification"] == "PRODUCT_DECISION_REQUIRED"
        or (
            row["risk_classification"] in ("MAJOR", "CRITICAL")
            and row.get("recommend_owner_review") == "true"
        )
    ]


def compute_gate(
    rows: Sequence[Mapping[str, Any]],
    *,
    safety_gate_facts: Mapping[str, Any],
    operational_gate_facts: Mapping[str, Any],
) -> dict[str, Any]:
    """Compute the pre-registered Phase 1 Quality Gate from a fully-merged
    row set. ``safety_gate_facts``/``operational_gate_facts`` carry the
    already-established, structurally-guaranteed or previously-measured
    facts (schema validity, provenance, Exact Replay, response rate, ...);
    this function itself computes only what genuinely depends on the
    semantic screening: the two semantic safety checks (negation/attribution
    reversal) and all six Human semantic gates."""

    total = len(rows)
    if total == 0:
        raise RiskBasedReviewError(COVERAGE_FAILURE, "empty_row_set")

    counts = Counter(row["risk_classification"] for row in rows)
    product_decision_required = counts.get("PRODUCT_DECISION_REQUIRED", 0)
    reason_counts = Counter(row["reason_code"] for row in rows)
    critical_counts = Counter(
        row["critical_error_type"] for row in rows if row["critical_error_type"] != "NONE"
    )

    by_ticker: dict[str, Counter] = defaultdict(Counter)
    by_family: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        by_ticker[row["ticker"]][row["risk_classification"]] += 1
        by_family[row["report_family"]][row["risk_classification"]] += 1

    semantic_reviewed_count = sum(1 for row in rows if row["semantic_reviewed"] == "true")
    targeted_count = sum(
        1 for row in rows if row["semantic_review_scope"] == SEMANTIC_SCOPE_TARGETED
    )
    spot_check_count = sum(
        1 for row in rows if row["semantic_review_scope"] == SEMANTIC_SCOPE_SPOT_CHECK
    )
    owner_count = sum(1 for row in rows if row["product_owner_adjudicated"] == "true")
    triage_flag_counts = Counter(
        flag
        for row in rows
        for flag in str(row.get("triage_risk_flags", "")).split(";")
        if flag
    )

    negation_reversal_critical = sum(
        1
        for r in rows
        if r["critical_error_type"] == "NEGATION_REVERSAL" and r["severity"] == "CRITICAL"
    )
    attribution_reversal_critical = sum(
        1
        for r in rows
        if r["critical_error_type"] == "ATTRIBUTION_LOSS" and r["severity"] == "CRITICAL"
    )
    semantic_safety = {
        "negation_reversal_critical_errors": negation_reversal_critical,
        "negation_reversal_critical_errors_pass": negation_reversal_critical == 0,
        "attribution_reversal_critical_errors": attribution_reversal_critical,
        "attribution_reversal_critical_errors_pass": attribution_reversal_critical == 0,
    }

    result: dict[str, Any] = {
        "total_claims": total,
        "counts_by_risk_classification": {
            key: counts.get(key, 0) for key in RISK_CLASSIFICATIONS
        },
        "product_decision_required_count": product_decision_required,
        "review_coverage": {
            "full_corpus_risk_screened": f"{total}/{total}",
            "targeted_semantic_reviewed": targeted_count,
            "low_risk_spot_checked": spot_check_count,
            "semantic_reviewed_total": semantic_reviewed_count,
            "deterministic_only": total - semantic_reviewed_count,
            "product_owner_adjudicated": owner_count,
            "triage_flag_counts": dict(triage_flag_counts),
        },
        "reason_code_counts": {key: reason_counts.get(key, 0) for key in REASON_CODES},
        "critical_error_type_counts": dict(critical_counts),
        "fabricated_claim_count": sum(
            1 for r in rows if r["critical_error_type"] == "FABRICATED_CLAIM"
        ),
        "fabricated_evidence_count": sum(
            1 for r in rows if r["critical_error_type"] == "FABRICATED_EVIDENCE"
        ),
        "identity_error_count": sum(
            1 for r in rows if r["critical_error_type"] == "IDENTITY_ERROR"
        ),
        "evidence_assertion_incomplete_count": reason_counts.get(
            "EVIDENCE_ASSERTION_INCOMPLETE", 0
        ),
        "factor_semantic_mismatch_count": reason_counts.get("FACTOR_SEMANTIC_MISMATCH", 0),
        "direction_semantic_mismatch_count": reason_counts.get(
            "DIRECTION_SEMANTIC_MISMATCH", 0
        ),
        "uncertainty_compression_minor_count": reason_counts.get(
            "UNCERTAINTY_COMPRESSION_MINOR", 0
        ),
        "upstream_report_quality_issue_count": sum(
            1 for r in rows if r.get("upstream_quality_issue") == "true"
        ),
        "by_ticker": {
            ticker: {key: c.get(key, 0) for key in RISK_CLASSIFICATIONS}
            for ticker, c in by_ticker.items()
        },
        "by_agent_family": {
            family: {key: c.get(key, 0) for key in RISK_CLASSIFICATIONS}
            for family, c in by_family.items()
        },
        "safety_gates": {**dict(safety_gate_facts), **semantic_safety},
        "operational_gates": dict(operational_gate_facts),
    }

    if product_decision_required > 0:
        result["gate_outcome"] = "WAITING_FOR_PRODUCT_OWNER_ADJUDICATION"
        result["human_gates"] = None
        result["human_gates_pass"] = None
        result["safety_gates_pass"] = None
        result["operational_gates_pass"] = None
        result["overall_pass"] = None
        result["systemic_evidence_misalignment"] = None
        result["systemic_factor_error"] = None
        result["systemic_semantic_failure"] = None
        return result

    accept_like = sum(
        1 for r in rows if r["overall_disposition"] in ("ACCEPT", "ACCEPT_WITH_MINOR_ISSUE")
    )
    semantic_fidelity_correct = sum(1 for r in rows if r["semantic_fidelity"] == "PASS")
    evidence_pairing_ok = sum(
        1 for r in rows if r["evidence_correctness"] in ("PASS", "PARTIAL")
    )
    claim_boundary_correct = sum(1 for r in rows if r["claim_boundary"] == "PASS")
    critical_severity_errors = sum(1 for r in rows if r["severity"] == "CRITICAL")
    major_plus_critical = sum(1 for r in rows if r["severity"] in ("MAJOR", "CRITICAL"))

    human_gates = {
        "disposition_accept_rate": accept_like / total,
        "disposition_accept_rate_pass": (accept_like / total)
        >= GATE_THRESHOLDS["disposition_accept_rate_min"],
        "semantic_fidelity_correct_rate": semantic_fidelity_correct / total,
        "semantic_fidelity_correct_rate_pass": (semantic_fidelity_correct / total)
        >= GATE_THRESHOLDS["semantic_fidelity_correct_rate_min"],
        "evidence_pairing_correct_rate": evidence_pairing_ok / total,
        "evidence_pairing_correct_rate_pass": (evidence_pairing_ok / total)
        >= GATE_THRESHOLDS["evidence_pairing_correct_rate_min"],
        "claim_boundary_correct_rate": claim_boundary_correct / total,
        "claim_boundary_correct_rate_pass": (claim_boundary_correct / total)
        >= GATE_THRESHOLDS["claim_boundary_correct_rate_min"],
        "critical_severity_errors": critical_severity_errors,
        "critical_severity_errors_pass": critical_severity_errors
        <= GATE_THRESHOLDS["critical_severity_errors_max"],
        "major_plus_critical_rate": major_plus_critical / total,
        "major_plus_critical_rate_pass": (major_plus_critical / total)
        <= GATE_THRESHOLDS["major_plus_critical_rate_max"],
    }
    safety_pass = all(
        bool(v) for k, v in result["safety_gates"].items() if k.endswith("_pass")
    )
    operational_pass = all(
        bool(v) for k, v in operational_gate_facts.items() if k.endswith("_pass")
    )
    human_pass = all(v for k, v in human_gates.items() if k.endswith("_pass"))
    overall_pass = safety_pass and operational_pass and human_pass

    result["human_gates"] = human_gates
    result["human_gates_pass"] = human_pass
    result["safety_gates_pass"] = safety_pass
    result["operational_gates_pass"] = operational_pass
    result["overall_pass"] = overall_pass
    result["gate_outcome"] = "PASS" if overall_pass else "FAIL"

    distinct_reports_with_evidence_fail = {
        (r["ticker"], r["report_family"]) for r in rows if r["evidence_correctness"] == "FAIL"
    }
    distinct_reports_with_factor_fail = {
        (r["ticker"], r["report_family"]) for r in rows if r["factor_correctness"] == "FAIL"
    }
    distinct_reports_with_critical = {
        (r["ticker"], r["report_family"]) for r in rows if r["critical_error_type"] != "NONE"
    }
    result["systemic_evidence_misalignment"] = (
        sum(1 for r in rows if r["evidence_correctness"] == "FAIL") / total > 0.02
        or len(distinct_reports_with_evidence_fail) >= 3
    )
    result["systemic_factor_error"] = (
        sum(1 for r in rows if r["factor_correctness"] == "FAIL") / total > 0.02
        or len(distinct_reports_with_factor_fail) >= 3
    )
    result["systemic_semantic_failure"] = bool(
        not human_gates["major_plus_critical_rate_pass"] or len(distinct_reports_with_critical) >= 3
    )
    result["systemic_flag_definition"] = (
        "Diagnostic only, not a pre-registered gate: 'systemic' means the "
        "issue affects >2% of all 478 claims OR appears in >=3 distinct "
        "(ticker, report_family) reports."
    )
    return result


def render_risk_based_csv(rows: Sequence[Mapping[str, Any]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})
    return buffer.getvalue()


_SECRET_PATTERNS = (
    re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"authorization\s*:\s*(?:bearer|basic)\s+\S+", re.IGNORECASE),
    re.compile(r"ANTHROPIC_API_KEY\s*=\s*\S+", re.IGNORECASE),
)


def _secret_findings(texts: Mapping[str, str]) -> list[str]:
    findings: list[str] = []
    for name, text in texts.items():
        for pattern in _SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(f"{name}:{pattern.pattern}")
    return findings


def render_json_report(
    *,
    gate: Mapping[str, Any],
    generated_at: str,
    evaluation_dir: str,
) -> dict[str, Any]:
    total = gate["total_claims"]
    return {
        "schema_version": PACKET_SCHEMA_VERSION,
        "generated_at": generated_at,
        "evaluation_dir": evaluation_dir,
        "review_method": REVIEW_METHOD,
        "prompt_version": REQUIRED_PROMPT_VERSION,
        "frozen_product_owner_policies": FROZEN_PRODUCT_OWNER_POLICIES,
        "gate_thresholds_source": GATE_THRESHOLDS_SOURCE,
        "gate_thresholds": GATE_THRESHOLDS,
        "full_corpus_screened": f"{total}/{total}",
        "product_owner_adjudicated_count": gate["review_coverage"][
            "product_owner_adjudicated"
        ],
        **gate,
    }


def _fmt_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def render_markdown_report(
    *,
    gate: Mapping[str, Any],
    generated_at: str,
    evaluation_dir: str,
    adjudication_row_count: int,
) -> str:
    total = gate["total_claims"]
    counts = gate["counts_by_risk_classification"]
    outcome = gate["gate_outcome"]

    lines: list[str] = []
    lines.append("# Phase 1 §5.1 v4 Risk-Based Review Report")
    lines.append("")
    lines.append(
        f"Generated: {generated_at}  \nEvaluation dir: `{evaluation_dir}`  \n"
        f"Prompt version: `{REQUIRED_PROMPT_VERSION}`  \nReview method: `{REVIEW_METHOD}`"
    )
    lines.append("")
    lines.append(
        "This report supersedes only the **execution method** of the Phase 1 "
        "Human Review checkpoint (product-owner decision, "
        "RISK_BASED_HUMAN_REVIEW): deterministic full-corpus triage, sequential "
        "Codex review of every flagged row, and a deterministic stratified "
        "low-risk spot check. The "
        "underlying Phase 1 Quality Gate thresholds "
        f"(`{GATE_THRESHOLDS_SOURCE}`) are unchanged."
    )
    lines.append("")
    lines.append(f"**FULL_CORPUS_SCREENED = {total}/{total}**  ")
    coverage = gate["review_coverage"]
    lines.append(f"**TARGETED_SEMANTIC_REVIEWED = {coverage['targeted_semantic_reviewed']}**  ")
    lines.append(f"**LOW_RISK_SPOT_CHECKED = {coverage['low_risk_spot_checked']}**  ")
    lines.append(
        f"**PRODUCT_OWNER_ADJUDICATED = {coverage['product_owner_adjudicated']}**"
    )
    lines.append(f"**PHASE_1_FINAL_GATE = {outcome}**")
    lines.append("")

    lines.append("## Classification counts")
    lines.append("")
    lines.append("| Classification | Count | % |")
    lines.append("|---|---:|---:|")
    for key in RISK_CLASSIFICATIONS:
        c = counts.get(key, 0)
        lines.append(f"| {key} | {c} | {_fmt_pct(c / total)} |")
    lines.append("")

    lines.append("## Diagnostic reason codes")
    lines.append("")
    lines.append("| Reason code | Count |")
    lines.append("|---|---:|")
    for key, value in gate["reason_code_counts"].items():
        if value:
            lines.append(f"| {key} | {value} |")
    lines.append("")

    lines.append("## Critical error taxonomy")
    lines.append("")
    if gate["critical_error_type_counts"]:
        lines.append("| Critical error type | Count |")
        lines.append("|---|---:|")
        for key, value in sorted(gate["critical_error_type_counts"].items()):
            lines.append(f"| {key} | {value} |")
    else:
        lines.append("None found.")
    lines.append("")

    if gate["product_decision_required_count"] > 0:
        lines.append("## Gate outcome: WAITING_FOR_PRODUCT_OWNER_ADJUDICATION")
        lines.append("")
        lines.append(
            f"{gate['product_decision_required_count']} claim(s) are genuinely "
            "rule-ambiguous and require real product-owner adjudication "
            "before the final Quality Gate can be computed. See "
            "`phase1_v4_product_owner_adjudication_required.csv` "
            f"({adjudication_row_count} row(s) total, including any flagged "
            "MAJOR/CRITICAL boundary cases)."
        )
        lines.append("")
        return "\n".join(lines)

    lines.append("## Safety gates")
    lines.append("")
    lines.append("| Gate | Result |")
    lines.append("|---|---|")
    for key, value in gate["safety_gates"].items():
        if key.endswith("_pass"):
            continue
        pass_key = f"{key}_pass"
        pass_value = gate["safety_gates"].get(pass_key)
        suffix = f" ({'PASS' if pass_value else 'FAIL'})" if pass_key in gate["safety_gates"] else ""
        lines.append(f"| {key} | {value}{suffix} |")
    lines.append(f"| **safety_gates_pass** | **{gate['safety_gates_pass']}** |")
    lines.append("")

    lines.append("## Human semantic gates")
    lines.append("")
    lines.append("| Gate | Value | Threshold | Result |")
    lines.append("|---|---:|---:|---|")
    hg = gate["human_gates"]
    lines.append(
        f"| disposition accept+minor_issue | {_fmt_pct(hg['disposition_accept_rate'])} | "
        f">= {_fmt_pct(GATE_THRESHOLDS['disposition_accept_rate_min'])} | "
        f"{'PASS' if hg['disposition_accept_rate_pass'] else 'FAIL'} |"
    )
    lines.append(
        f"| semantic fidelity correct | {_fmt_pct(hg['semantic_fidelity_correct_rate'])} | "
        f">= {_fmt_pct(GATE_THRESHOLDS['semantic_fidelity_correct_rate_min'])} | "
        f"{'PASS' if hg['semantic_fidelity_correct_rate_pass'] else 'FAIL'} |"
    )
    lines.append(
        f"| evidence pairing correct+partial | {_fmt_pct(hg['evidence_pairing_correct_rate'])} | "
        f">= {_fmt_pct(GATE_THRESHOLDS['evidence_pairing_correct_rate_min'])} | "
        f"{'PASS' if hg['evidence_pairing_correct_rate_pass'] else 'FAIL'} |"
    )
    lines.append(
        f"| claim boundary correct | {_fmt_pct(hg['claim_boundary_correct_rate'])} | "
        f">= {_fmt_pct(GATE_THRESHOLDS['claim_boundary_correct_rate_min'])} | "
        f"{'PASS' if hg['claim_boundary_correct_rate_pass'] else 'FAIL'} |"
    )
    lines.append(
        f"| critical severity errors | {hg['critical_severity_errors']} | "
        f"<= {GATE_THRESHOLDS['critical_severity_errors_max']} | "
        f"{'PASS' if hg['critical_severity_errors_pass'] else 'FAIL'} |"
    )
    lines.append(
        f"| major+critical rate | {_fmt_pct(hg['major_plus_critical_rate'])} | "
        f"<= {_fmt_pct(GATE_THRESHOLDS['major_plus_critical_rate_max'])} | "
        f"{'PASS' if hg['major_plus_critical_rate_pass'] else 'FAIL'} |"
    )
    lines.append(f"| **human_gates_pass** | | | **{gate['human_gates_pass']}** |")
    lines.append("")

    lines.append("## Operational gates")
    lines.append("")
    lines.append("| Gate | Result |")
    lines.append("|---|---|")
    for key, value in gate["operational_gates"].items():
        lines.append(f"| {key} | {value} |")
    lines.append(f"| **operational_gates_pass** | **{gate['operational_gates_pass']}** |")
    lines.append("")

    lines.append("## Systemic flags")
    lines.append("")
    lines.append(f"- SYSTEMIC_EVIDENCE_MISALIGNMENT = {'YES' if gate['systemic_evidence_misalignment'] else 'NO'}")
    lines.append(f"- SYSTEMIC_FACTOR_ERROR = {'YES' if gate['systemic_factor_error'] else 'NO'}")
    lines.append(f"- SYSTEMIC_SEMANTIC_FAILURE = {'YES' if gate['systemic_semantic_failure'] else 'NO'}")
    lines.append(f"- ({gate['systemic_flag_definition']})")
    lines.append("")

    lines.append("## By ticker")
    lines.append("")
    lines.append("| Ticker | " + " | ".join(RISK_CLASSIFICATIONS) + " |")
    lines.append("|---|" + "---:|" * len(RISK_CLASSIFICATIONS))
    for ticker, breakdown in sorted(gate["by_ticker"].items()):
        lines.append(
            f"| {ticker} | " + " | ".join(str(breakdown.get(k, 0)) for k in RISK_CLASSIFICATIONS) + " |"
        )
    lines.append("")

    lines.append("## By agent family")
    lines.append("")
    lines.append("| Family | " + " | ".join(RISK_CLASSIFICATIONS) + " |")
    lines.append("|---|" + "---:|" * len(RISK_CLASSIFICATIONS))
    for family, breakdown in sorted(gate["by_agent_family"].items()):
        lines.append(
            f"| {family} | " + " | ".join(str(breakdown.get(k, 0)) for k in RISK_CLASSIFICATIONS) + " |"
        )
    lines.append("")

    lines.append(f"**PHASE_1_FINAL_GATE = {outcome}**")
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "ALLOWED_REVIEW_VALUES",
    "COVERAGE_FAILURE",
    "CSV_FIELDS",
    "FROZEN_PRODUCT_OWNER_POLICIES",
    "GATE_THRESHOLDS",
    "GATE_THRESHOLDS_SOURCE",
    "PACKET_SCHEMA_VERSION",
    "PROVENANCE_FAILURE",
    "REASON_CODES",
    "REQUIRED_PROMPT_VERSION",
    "REQUIRED_VERDICT_FIELDS",
    "REVIEW_METHOD",
    "RISK_CLASSIFICATIONS",
    "RISK_REVIEW_FIELDS",
    "RiskBasedReviewError",
    "KNOWN_REVIEW_CANDIDATE_IDS",
    "SCREENING_AUTHORITY_CODEX",
    "SCREENING_AUTHORITY_DETERMINISTIC",
    "SCREENING_AUTHORITY_OWNER",
    "SEMANTIC_SCOPE_NONE",
    "SEMANTIC_SCOPE_SPOT_CHECK",
    "SEMANTIC_SCOPE_TARGETED",
    "compute_gate",
    "deterministic_triage_flags",
    "map_risk_classification",
    "merge_verdicts",
    "render_json_report",
    "render_markdown_report",
    "render_risk_based_csv",
    "select_adjudication_rows",
    "select_stratified_low_risk_sample",
    "_secret_findings",
]
