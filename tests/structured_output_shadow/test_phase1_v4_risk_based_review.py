"""Phase 1 Master §5.1 v4 risk-based review: unit tests for the pure
functions in comqutor_alpha/evaluation/phase1_v4_risk_based_review.py
(product-owner-authorized RISK_BASED_HUMAN_REVIEW methodology). No Provider
calls, no network, no real evaluation-dir I/O -- all in-memory fixtures.
"""

from __future__ import annotations

import csv
import io

import pytest

from comqutor_alpha.evaluation.phase1_v4_risk_based_review import (
    CSV_FIELDS,
    FROZEN_PRODUCT_OWNER_POLICIES,
    GATE_THRESHOLDS,
    REASON_CODES,
    REQUIRED_PROMPT_VERSION,
    REVIEW_METHOD,
    RISK_CLASSIFICATIONS,
    SCREENING_AUTHORITY_DETERMINISTIC,
    SEMANTIC_SCOPE_NONE,
    RiskBasedReviewError,
    compute_gate,
    deterministic_triage_flags,
    map_risk_classification,
    merge_verdicts,
    render_json_report,
    render_markdown_report,
    render_risk_based_csv,
    select_adjudication_rows,
    select_stratified_low_risk_sample,
)


def _original_row(row_id: str, **overrides) -> dict[str, str]:
    row = {
        "review_row_id": row_id,
        "ticker": "NVDA",
        "agent": "fundamental_agent",
        "report_family": "fundamental",
        "claim_ordinal": "1",
        "shadow_claim_id": f"shadow-{row_id}",
        "claim_text": "Net income was $58.32B.",
        "shadow_evidence_text": "Net income was $58.32B.",
        "source_evidence_text": "Net income was $58.32B.",
        "source_spans": "Net income was $58.32B.",
        "source_context_before": "before",
        "source_context_after": "after",
        "entities": "[]",
        "factors": "[]",
        "direction": "positive",
        "confidence": "0.9",
        "legacy_claim_text": "",
        "legacy_evidence_text": "",
    }
    row.update(overrides)
    return row


def _pass_verdict(row_id: str, **overrides) -> dict:
    verdict = {
        "review_row_id": row_id,
        "semantic_fidelity": "PASS",
        "claim_boundary": "PASS",
        "evidence_correctness": "PASS",
        "entity_correctness": "NA",
        "factor_correctness": "NA",
        "direction_correctness": "PASS",
        "critical_error_type": "NONE",
        "risk_classification": "PASS",
        "reason_code": "NONE",
        "upstream_quality_issue": False,
        "recommend_owner_review": False,
        "notes": "",
        "triage_risk_flags": [],
        "semantic_reviewed": False,
        "semantic_review_scope": SEMANTIC_SCOPE_NONE,
        "screening_authority": SCREENING_AUTHORITY_DETERMINISTIC,
        "product_owner_adjudicated": False,
        "reviewer": "deterministic-test",
    }
    verdict.update(overrides)
    return verdict


def test_deterministic_triage_flags_known_and_marker_asymmetries():
    known = _original_row(
        "phase1-review-v4-e7fab1e2fd30bc7bec6ad9d7",
        claim_text="The band provided support.",
        source_evidence_text="The band may have provided support and did not break.",
    )
    flags = deterministic_triage_flags(known)
    assert "KNOWN_PRIOR_AUDIT_CANDIDATE" in flags
    assert "EPISTEMIC_MARKER_ASYMMETRY" in flags
    assert "NEGATION_MARKER_ASYMMETRY" in flags


def test_stratified_sample_is_stable_and_excludes_flagged_rows():
    rows = [
        _original_row("a", ticker="NVDA", report_family="news"),
        _original_row("b", ticker="NVDA", report_family="news"),
        _original_row("c", ticker="NVDA", report_family="news"),
        _original_row("d", ticker="QQQ", report_family="technical"),
        _original_row("e", ticker="QQQ", report_family="technical"),
        _original_row("f", ticker="QQQ", report_family="technical"),
    ]
    triage = {row["review_row_id"]: () for row in rows}
    triage["a"] = ("FLAG",)
    first = select_stratified_low_risk_sample(rows, triage, per_stratum=2)
    second = select_stratified_low_risk_sample(rows, triage, per_stratum=2)
    assert first == second
    assert len(first) == 4
    assert "a" not in first


# ---------------------------------------------------------------------------
# map_risk_classification
# ---------------------------------------------------------------------------


def test_map_pass_is_accept_none():
    mapped = map_risk_classification("PASS")
    assert mapped == {
        "overall_disposition": "ACCEPT",
        "severity": "NONE",
        "adapter_quality_impact": "NONE",
    }


def test_map_minor_is_accept_with_minor_issue():
    mapped = map_risk_classification("MINOR")
    assert mapped["overall_disposition"] == "ACCEPT_WITH_MINOR_ISSUE"
    assert mapped["severity"] == "MINOR"


def test_map_major_and_critical_are_reject():
    assert map_risk_classification("MAJOR")["overall_disposition"] == "REJECT"
    assert map_risk_classification("MAJOR")["severity"] == "MAJOR"
    assert map_risk_classification("CRITICAL")["overall_disposition"] == "REJECT"
    assert map_risk_classification("CRITICAL")["severity"] == "CRITICAL"


def test_map_upstream_only_is_accept_but_flagged_not_adapter():
    mapped = map_risk_classification("UPSTREAM_ONLY")
    assert mapped["overall_disposition"] == "ACCEPT"
    assert mapped["severity"] == "NONE"
    assert mapped["adapter_quality_impact"] == "NOT_ADAPTER_UPSTREAM_SOURCE"


def test_map_product_decision_required_leaves_disposition_and_severity_blank():
    mapped = map_risk_classification("PRODUCT_DECISION_REQUIRED")
    assert mapped["overall_disposition"] == ""
    assert mapped["severity"] == ""
    assert mapped["adapter_quality_impact"] == "PENDING_ADJUDICATION"


def test_map_unknown_classification_raises():
    with pytest.raises(ValueError):
        map_risk_classification("NOT_A_REAL_CLASSIFICATION")


# ---------------------------------------------------------------------------
# merge_verdicts
# ---------------------------------------------------------------------------


def test_merge_verdicts_happy_path_fills_all_new_fields():
    rows = [_original_row("r1")]
    verdicts = {"r1": _pass_verdict("r1")}
    merged = merge_verdicts(
        rows, verdicts, generated_at="2026-08-10T00:00:00Z", ai_reviewer_label="AI_RULE_BASED_SCREENING (test)"
    )
    assert len(merged) == 1
    row = merged[0]
    assert row["claim_text"] == "Net income was $58.32B."  # immutable field preserved verbatim
    assert row["risk_classification"] == "PASS"
    assert row["overall_disposition"] == "ACCEPT"
    assert row["severity"] == "NONE"
    assert row["review_method"] == REVIEW_METHOD
    assert row["screening_authority"] == SCREENING_AUTHORITY_DETERMINISTIC
    assert row["product_owner_adjudicated"] == "false"
    assert row["review_timestamp"] == "2026-08-10T00:00:00Z"


def test_merge_verdicts_missing_row_raises_coverage_failure():
    rows = [_original_row("r1"), _original_row("r2")]
    verdicts = {"r1": _pass_verdict("r1")}
    with pytest.raises(RiskBasedReviewError) as excinfo:
        merge_verdicts(rows, verdicts, generated_at="t", ai_reviewer_label="x")
    assert excinfo.value.reason_code == "RISK_BASED_REVIEW_V4_COVERAGE_FAILURE"


def test_merge_verdicts_unexpected_extra_verdict_raises_coverage_failure():
    rows = [_original_row("r1")]
    verdicts = {"r1": _pass_verdict("r1"), "r2": _pass_verdict("r2")}
    with pytest.raises(RiskBasedReviewError):
        merge_verdicts(rows, verdicts, generated_at="t", ai_reviewer_label="x")


def test_merge_verdicts_bad_vocabulary_value_raises():
    rows = [_original_row("r1")]
    verdicts = {"r1": _pass_verdict("r1", semantic_fidelity="SORTA")}
    with pytest.raises(RiskBasedReviewError):
        merge_verdicts(rows, verdicts, generated_at="t", ai_reviewer_label="x")


def test_merge_verdicts_missing_notes_for_non_pass_raises():
    rows = [_original_row("r1")]
    verdicts = {
        "r1": _pass_verdict(
            "r1", risk_classification="MINOR", reason_code="UNCERTAINTY_COMPRESSION_MINOR", notes=""
        )
    }
    with pytest.raises(RiskBasedReviewError) as excinfo:
        merge_verdicts(rows, verdicts, generated_at="t", ai_reviewer_label="x")
    assert "missing_notes_for_non_pass" in str(excinfo.value)


def test_merge_verdicts_upstream_only_requires_pass_fidelity_and_flag():
    rows = [_original_row("r1")]
    bad_verdict = _pass_verdict(
        "r1",
        risk_classification="UPSTREAM_ONLY",
        reason_code="UPSTREAM_REPORT_QUALITY_ISSUE",
        semantic_fidelity="FAIL",  # inconsistent
        upstream_quality_issue=True,
        notes="source math error",
    )
    with pytest.raises(RiskBasedReviewError) as excinfo:
        merge_verdicts(rows, {"r1": bad_verdict}, generated_at="t", ai_reviewer_label="x")
    assert "upstream_only_inconsistent" in str(excinfo.value)

    good_verdict = dict(bad_verdict, semantic_fidelity="PASS")
    merged = merge_verdicts(rows, {"r1": good_verdict}, generated_at="t", ai_reviewer_label="x")
    assert merged[0]["upstream_quality_issue"] == "true"
    assert merged[0]["overall_disposition"] == "ACCEPT"


def test_merge_verdicts_critical_error_type_requires_major_or_critical_classification():
    rows = [_original_row("r1")]
    bad_verdict = _pass_verdict(
        "r1",
        critical_error_type="FABRICATED_EVIDENCE",
        risk_classification="MINOR",  # inconsistent -- should be MAJOR/CRITICAL
        reason_code="OTHER_SEMANTIC_MINOR",
        notes="wrong section quoted",
    )
    with pytest.raises(RiskBasedReviewError):
        merge_verdicts(rows, {"r1": bad_verdict}, generated_at="t", ai_reviewer_label="x")


def test_merge_verdicts_product_decision_required_leaves_disposition_severity_blank():
    rows = [_original_row("r1")]
    verdict = _pass_verdict(
        "r1",
        risk_classification="PRODUCT_DECISION_REQUIRED",
        reason_code="PRODUCT_DECISION_REQUIRED",
        notes="genuinely ambiguous case not covered by rules A-F",
    )
    merged = merge_verdicts(rows, {"r1": verdict}, generated_at="t", ai_reviewer_label="x")
    assert merged[0]["overall_disposition"] == ""
    assert merged[0]["severity"] == ""


# ---------------------------------------------------------------------------
# select_adjudication_rows
# ---------------------------------------------------------------------------


def test_select_adjudication_rows_includes_product_decision_required_and_flagged_major_critical():
    rows = [
        {"review_row_id": "a", "risk_classification": "PASS", "recommend_owner_review": "false"},
        {"review_row_id": "b", "risk_classification": "MINOR", "recommend_owner_review": "false"},
        {"review_row_id": "c", "risk_classification": "MAJOR", "recommend_owner_review": "false"},
        {"review_row_id": "d", "risk_classification": "MAJOR", "recommend_owner_review": "true"},
        {"review_row_id": "e", "risk_classification": "CRITICAL", "recommend_owner_review": "true"},
        {"review_row_id": "f", "risk_classification": "PRODUCT_DECISION_REQUIRED", "recommend_owner_review": "false"},
        {"review_row_id": "g", "risk_classification": "UPSTREAM_ONLY", "recommend_owner_review": "false"},
    ]
    selected_ids = {row["review_row_id"] for row in select_adjudication_rows(rows)}
    assert selected_ids == {"d", "e", "f"}


def test_select_adjudication_rows_empty_when_nothing_flagged():
    rows = [
        {"review_row_id": "a", "risk_classification": "PASS", "recommend_owner_review": "false"},
        {"review_row_id": "b", "risk_classification": "MAJOR", "recommend_owner_review": "false"},
    ]
    assert select_adjudication_rows(rows) == []


# ---------------------------------------------------------------------------
# compute_gate
# ---------------------------------------------------------------------------


_SAFETY_FACTS = {
    "schema_valid_admitted_output_pct": 1.0,
    "schema_valid_admitted_output_pct_pass": True,
    "source_span_validity_pct": 1.0,
    "source_span_validity_pct_pass": True,
    "evidence_provenance_validity_pct": 1.0,
    "evidence_provenance_validity_pct_pass": True,
    "identity_validity_pct": 1.0,
    "identity_validity_pct_pass": True,
    "fabricated_source_ref_admitted": 0,
    "fabricated_source_ref_admitted_pass": True,
    "invented_evidence_admitted": 0,
    "invented_evidence_admitted_pass": True,
    "malformed_json_propagation": 0,
    "malformed_json_propagation_pass": True,
    "secret_persistence": 0,
    "secret_persistence_pass": True,
}
_OPERATIONAL_FACTS = {
    "overall_rejection_abstention_rate": 0.125,
    "overall_rejection_abstention_rate_pass": True,
    "max_per_family_rejection_abstention_rate": 0.167,
    "max_per_family_rejection_abstention_rate_pass": True,
    "exact_replay_success_pct": 1.0,
    "exact_replay_success_pct_pass": True,
}


def _merged_row(row_id: str, risk_classification: str, **field_overrides) -> dict:
    base = _original_row(row_id)
    verdict = _pass_verdict(row_id, risk_classification=risk_classification)
    if risk_classification not in ("PASS",):
        verdict["notes"] = "test fixture"
    verdict.update(field_overrides)
    merged = merge_verdicts([base], {row_id: verdict}, generated_at="t", ai_reviewer_label="x")
    return merged[0]


def test_compute_gate_all_pass_yields_gate_pass():
    rows = [_merged_row(f"r{i}", "PASS") for i in range(20)]
    gate = compute_gate(rows, safety_gate_facts=_SAFETY_FACTS, operational_gate_facts=_OPERATIONAL_FACTS)
    assert gate["gate_outcome"] == "PASS"
    assert gate["overall_pass"] is True
    assert gate["human_gates"]["disposition_accept_rate"] == 1.0
    assert gate["human_gates"]["critical_severity_errors"] == 0


def test_compute_gate_product_decision_required_short_circuits():
    rows = [_merged_row("r0", "PASS")] + [
        _merged_row(
            "r1",
            "PRODUCT_DECISION_REQUIRED",
            reason_code="PRODUCT_DECISION_REQUIRED",
        )
    ]
    gate = compute_gate(rows, safety_gate_facts=_SAFETY_FACTS, operational_gate_facts=_OPERATIONAL_FACTS)
    assert gate["gate_outcome"] == "WAITING_FOR_PRODUCT_OWNER_ADJUDICATION"
    assert gate["human_gates"] is None
    assert gate["overall_pass"] is None
    assert gate["product_decision_required_count"] == 1


def test_compute_gate_fails_on_critical_severity_error():
    rows = [_merged_row(f"r{i}", "PASS") for i in range(19)] + [
        _merged_row(
            "r_critical",
            "CRITICAL",
            critical_error_type="NEGATION_REVERSAL",
        )
    ]
    gate = compute_gate(rows, safety_gate_facts=_SAFETY_FACTS, operational_gate_facts=_OPERATIONAL_FACTS)
    assert gate["gate_outcome"] == "FAIL"
    assert gate["human_gates"]["critical_severity_errors"] == 1
    assert gate["human_gates"]["critical_severity_errors_pass"] is False
    assert gate["safety_gates"]["negation_reversal_critical_errors"] == 1
    assert gate["safety_gates"]["negation_reversal_critical_errors_pass"] is False


def test_compute_gate_fails_on_low_disposition_accept_rate():
    # 5 PASS, 15 MAJOR (REJECT) -> accept rate 25% < 85%
    rows = [_merged_row(f"p{i}", "PASS") for i in range(5)] + [
        _merged_row(f"m{i}", "MAJOR") for i in range(15)
    ]
    gate = compute_gate(rows, safety_gate_facts=_SAFETY_FACTS, operational_gate_facts=_OPERATIONAL_FACTS)
    assert gate["gate_outcome"] == "FAIL"
    assert gate["human_gates"]["disposition_accept_rate_pass"] is False


def test_compute_gate_major_plus_critical_rate_threshold():
    # exactly 5% major -> should still pass (<=5%); one more should fail.
    rows = [_merged_row(f"p{i}", "PASS") for i in range(19)] + [_merged_row("m0", "MAJOR")]
    gate = compute_gate(rows, safety_gate_facts=_SAFETY_FACTS, operational_gate_facts=_OPERATIONAL_FACTS)
    assert gate["human_gates"]["major_plus_critical_rate"] == pytest.approx(0.05)
    assert gate["human_gates"]["major_plus_critical_rate_pass"] is True

    rows_fail = rows + [_merged_row("m1", "MAJOR")]
    gate_fail = compute_gate(
        rows_fail, safety_gate_facts=_SAFETY_FACTS, operational_gate_facts=_OPERATIONAL_FACTS
    )
    assert gate_fail["human_gates"]["major_plus_critical_rate_pass"] is False
    assert gate_fail["gate_outcome"] == "FAIL"


def test_compute_gate_upstream_only_counts_as_accept_and_pass_fidelity():
    rows = [_merged_row(f"p{i}", "PASS") for i in range(10)] + [
        _merged_row(
            "u0",
            "UPSTREAM_ONLY",
            reason_code="UPSTREAM_REPORT_QUALITY_ISSUE",
            upstream_quality_issue=True,
        )
    ]
    gate = compute_gate(rows, safety_gate_facts=_SAFETY_FACTS, operational_gate_facts=_OPERATIONAL_FACTS)
    assert gate["human_gates"]["disposition_accept_rate"] == 1.0
    assert gate["human_gates"]["semantic_fidelity_correct_rate"] == 1.0
    assert gate["counts_by_risk_classification"]["UPSTREAM_ONLY"] == 1
    assert gate["upstream_report_quality_issue_count"] == 1


def test_compute_gate_negation_reversal_only_counts_when_severity_critical():
    # A MAJOR-graded (not CRITICAL) borderline negation-adjacent case must
    # not trip the negation_reversal_critical_errors safety gate.
    rows = [_merged_row(f"p{i}", "PASS") for i in range(10)] + [
        _merged_row(
            "m0",
            "MAJOR",
            critical_error_type="NEGATION_REVERSAL",
        )
    ]
    gate = compute_gate(rows, safety_gate_facts=_SAFETY_FACTS, operational_gate_facts=_OPERATIONAL_FACTS)
    assert gate["safety_gates"]["negation_reversal_critical_errors"] == 0
    assert gate["safety_gates"]["negation_reversal_critical_errors_pass"] is True


def test_compute_gate_systemic_evidence_misalignment_flags_when_widespread():
    rows = []
    families = ["fundamental", "news", "sentiment"]
    for i, fam in enumerate(families):
        rows.append(
            _merged_row(
                f"e{i}",
                "MAJOR",
                evidence_correctness="FAIL",
                reason_code="OTHER_SEMANTIC_MINOR",
            )
        )
        rows[-1]["report_family"] = fam
        rows[-1]["ticker"] = f"T{i}"
    rows += [_merged_row(f"p{i}", "PASS") for i in range(20)]
    gate = compute_gate(rows, safety_gate_facts=_SAFETY_FACTS, operational_gate_facts=_OPERATIONAL_FACTS)
    assert gate["systemic_evidence_misalignment"] is True


def test_compute_gate_no_systemic_flags_for_single_isolated_issue():
    # 1 isolated FAIL out of 61 claims (~1.6%) must stay under the 2%/
    # >=3-reports "systemic" diagnostic threshold.
    rows = [_merged_row(f"p{i}", "PASS") for i in range(60)] + [
        _merged_row("f0", "MINOR", factor_correctness="FAIL", reason_code="FACTOR_SEMANTIC_MISMATCH")
    ]
    gate = compute_gate(rows, safety_gate_facts=_SAFETY_FACTS, operational_gate_facts=_OPERATIONAL_FACTS)
    assert gate["systemic_factor_error"] is False
    assert gate["systemic_evidence_misalignment"] is False


def test_compute_gate_raises_on_empty_rows():
    with pytest.raises(RiskBasedReviewError):
        compute_gate([], safety_gate_facts=_SAFETY_FACTS, operational_gate_facts=_OPERATIONAL_FACTS)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def test_render_risk_based_csv_round_trips_and_has_all_fields():
    rows = [_merged_row("r1", "PASS")]
    text = render_risk_based_csv(rows)
    reader = csv.DictReader(io.StringIO(text))
    assert reader.fieldnames == list(CSV_FIELDS)
    parsed = list(reader)
    assert parsed[0]["risk_classification"] == "PASS"
    assert parsed[0]["review_method"] == REVIEW_METHOD


def test_csv_fields_has_no_duplicates_and_includes_new_columns():
    assert len(CSV_FIELDS) == len(set(CSV_FIELDS))
    for field in ("risk_classification", "reason_code", "screening_authority", "product_owner_adjudicated"):
        assert field in CSV_FIELDS


def test_render_json_report_contains_frozen_policies_and_thresholds():
    rows = [_merged_row(f"p{i}", "PASS") for i in range(10)]
    gate = compute_gate(rows, safety_gate_facts=_SAFETY_FACTS, operational_gate_facts=_OPERATIONAL_FACTS)
    report = render_json_report(gate=gate, generated_at="t", evaluation_dir="d")
    assert report["frozen_product_owner_policies"]["DIRECTION_POLICY"]["value"] == "SEMANTIC_JUDGMENT_ALLOWED"
    assert report["frozen_product_owner_policies"]["FACTOR_POLICY"]["value"] == "STRICT_SEMANTIC_MATCH_OR_EMPTY"
    assert report["gate_thresholds"] == GATE_THRESHOLDS
    assert report["full_corpus_screened"] == "10/10"
    assert report["product_owner_adjudicated_count"] == 0
    assert report["prompt_version"] == REQUIRED_PROMPT_VERSION


def test_render_markdown_report_pass_path_mentions_final_gate_and_tables():
    rows = [_merged_row(f"p{i}", "PASS") for i in range(20)]
    gate = compute_gate(rows, safety_gate_facts=_SAFETY_FACTS, operational_gate_facts=_OPERATIONAL_FACTS)
    text = render_markdown_report(
        gate=gate, generated_at="t", evaluation_dir="d", adjudication_row_count=0
    )
    assert "PHASE_1_FINAL_GATE = PASS" in text
    assert "Human semantic gates" in text
    assert "Safety gates" in text
    assert "Systemic flags" in text


def test_render_markdown_report_waiting_path_short_circuits_before_gate_tables():
    rows = [_merged_row("p0", "PASS")] + [
        _merged_row("d0", "PRODUCT_DECISION_REQUIRED", reason_code="PRODUCT_DECISION_REQUIRED")
    ]
    gate = compute_gate(rows, safety_gate_facts=_SAFETY_FACTS, operational_gate_facts=_OPERATIONAL_FACTS)
    text = render_markdown_report(
        gate=gate, generated_at="t", evaluation_dir="d", adjudication_row_count=1
    )
    assert "WAITING_FOR_PRODUCT_OWNER_ADJUDICATION" in text
    assert "Human semantic gates" not in text


# ---------------------------------------------------------------------------
# Constants sanity
# ---------------------------------------------------------------------------


def test_frozen_policies_match_task_spec_exactly():
    assert FROZEN_PRODUCT_OWNER_POLICIES["DIRECTION_POLICY"]["value"] == "SEMANTIC_JUDGMENT_ALLOWED"
    assert FROZEN_PRODUCT_OWNER_POLICIES["FACTOR_POLICY"]["value"] == "STRICT_SEMANTIC_MATCH_OR_EMPTY"
    assert (
        FROZEN_PRODUCT_OWNER_POLICIES["UPSTREAM_ERROR_POLICY"]["value"]
        == "SEPARATE_FROM_ADAPTER_SEMANTIC_FAILURE"
    )
    assert (
        FROZEN_PRODUCT_OWNER_POLICIES["EVIDENCE_POLICY"]["value"]
        == "ASSERTION_COMPLETE_MULTI_SPAN_ALLOWED"
    )
    assert (
        FROZEN_PRODUCT_OWNER_POLICIES["UNCERTAINTY_POLICY"]["value"]
        == "MATERIAL_EPISTEMIC_STRENGTH_MUST_BE_PRESERVED"
    )


def test_gate_thresholds_match_execution_contract_verbatim():
    assert GATE_THRESHOLDS["disposition_accept_rate_min"] == 0.85
    assert GATE_THRESHOLDS["semantic_fidelity_correct_rate_min"] == 0.90
    assert GATE_THRESHOLDS["evidence_pairing_correct_rate_min"] == 0.90
    assert GATE_THRESHOLDS["claim_boundary_correct_rate_min"] == 0.85
    assert GATE_THRESHOLDS["critical_severity_errors_max"] == 0
    assert GATE_THRESHOLDS["major_plus_critical_rate_max"] == 0.05
    assert GATE_THRESHOLDS["overall_rejection_abstention_rate_max"] == 0.25
    assert GATE_THRESHOLDS["per_family_rejection_abstention_rate_max"] == 0.40


def test_risk_classifications_and_reason_codes_are_the_task_specified_sets():
    assert RISK_CLASSIFICATIONS == (
        "PASS",
        "MINOR",
        "MAJOR",
        "CRITICAL",
        "UPSTREAM_ONLY",
        "PRODUCT_DECISION_REQUIRED",
    )
    assert set(REASON_CODES) == {
        "NONE",
        "EVIDENCE_ASSERTION_INCOMPLETE",
        "FACTOR_SEMANTIC_MISMATCH",
        "DIRECTION_SEMANTIC_MISMATCH",
        "UPSTREAM_REPORT_QUALITY_ISSUE",
        "CLAIM_BOUNDARY_MINOR",
        "UNCERTAINTY_COMPRESSION_MINOR",
        "OTHER_SEMANTIC_MINOR",
        "PRODUCT_DECISION_REQUIRED",
    }
