"""T2 round 24: what the unified formal-acceptance entry says about a REQUIRED conflict pair, judged from the record the REAL detector and the REAL
B2 gate write -- not from a hand-made record.

The defect these tests close (reproduced read-only before the fix, 2026-10-07): the pair-level ``must_detect_if_evidence_present`` check treated "at
least one supporting fact on each side and not admitted" as a missed detection (FAIL), and treated a pair with no usable arbitration record as
"no evidence" (NOT_APPLICABLE). That inverted the cases: B2's correct rejections (one supporting fact per side, no ticker-specific support, a score
below the threshold) were reported as misses, while a pair that was never judged because an Alpha was not identified or not at an admissible
activation state was silently waved through.

SYNTHETIC FIXTURES (task sheet: "测试可以使用明确标注的合成 fixtures，但不能把它们计为真实市场验证样本"): the activation entries and claims below are built
by hand (tests/fixtures/week4_conflict_cases.py); the detector and B2 are the production code, called exactly as production calls them. Nothing here is
market data. The one hand-edited record (``test_controlled_modification_...``) is labelled as such: B2 cannot produce it.

Zero Provider calls.
"""

from __future__ import annotations

import pytest

from comqutor_alpha.alpha_library.alpha_schema import ConflictAlpha
from comqutor_alpha.conflict_engine.conflict_admissibility import MIN_SUPPORTING_EVIDENCE_PER_SIDE
from comqutor_alpha.conflict_engine.conflict_detector import detect_alpha_conflicts
from comqutor_alpha.regression.acceptance_engine import (
    PAIR_STATE_ADMITTED,
    PAIR_STATE_B2_NO_REASON,
    PAIR_STATE_B2_REJECTED,
    PAIR_STATE_NO_QUALIFYING_EVIDENCE,
    PAIR_STATE_NOT_EVALUATED,
    VERDICT_FAIL,
    VERDICT_NOT_APPLICABLE,
    VERDICT_NOT_EVALUABLE,
    VERDICT_PASS,
    evaluate_must_detect_if_evidence_present,
    pair_admissibility_lookup,
    pair_record_state,
    run_formal_acceptance,
)
from tests.fixtures.week4_conflict_cases import activation_entry, activation_payload, fake_alpha

RUN_ID, TICKER = "synthetic-b2-run", "NVDA"
TAXONOMY = {
    "A": fake_alpha("A", [ConflictAlpha(alpha_id="B", contradiction_weight=0.9)]),
    "B": fake_alpha("B", [ConflictAlpha(alpha_id="A", contradiction_weight=0.9)]),
}
A_SUPPORT = [("a1", "NVDA strong datacenter demand signal one."), ("a2", "NVDA new supply agreement signal two.")]
B_SUPPORT = [("b1", "NVDA strong valuation risk signal one."), ("b2", "NVDA margin compression signal two.")]
A_SUPPORT_NOT_TICKER_SPECIFIC = [("a1", "Strong datacenter demand signal one."), ("a2", "New supply agreement signal two.")]


def _claim(claim_id, alpha_id, evidence):
    return {
        "claim_id": claim_id,
        "source_agent_output_id": f"o_{claim_id}",
        "agent": "market_agent",
        "match_status": "matched",
        "matched_alpha": alpha_id,
        "matched_alpha_name": alpha_id,
        "score": 0.8,
        "direction": "positive",
        "assertion_status": "asserted",
        "semantic_polarity": "activation",
        "claim": evidence,
        "evidence": evidence,
        "reason": "test fixture",
        "plausible_alphas": [],
        "candidate_scores": [{"alpha_id": alpha_id, "score": 0.8, "relation": "activation", "evidence_stance": "supports_alpha"}],
        "claim_quality": "analytical",
        "factors": [],
    }


def _detect(a_entry, b_entry, a_support, b_support):
    entries = [e for e in (a_entry, b_entry) if e is not None]
    matches = [_claim(cid, "A", text) for cid, text in a_support] + [_claim(cid, "B", text) for cid, text in b_support]
    return detect_alpha_conflicts(
        run_id=RUN_ID, ticker=TICKER, activation_payload=activation_payload(*entries), alpha_matches=matches, taxonomy=TAXONOMY
    )


A_ACTIVE = activation_entry("A", score=80.0, direction="positive")
B_ACTIVE = activation_entry("B", score=80.0, direction="negative")


def _must_detect(payload):
    lookup = pair_admissibility_lookup(payload)
    (result,) = evaluate_must_detect_if_evidence_present(
        ticker_v2_label={"required_conflicts": ["A__B"]},
        admissibility_lookup=lookup,
        declared_pair_count=payload["arbitration"]["declared_pair_count"],
    )
    return result, lookup["A__B"]


def _formal(payload):
    return run_formal_acceptance(
        ticker="TEST",
        ticker_v2_label={"required_conflicts": ["A__B"], "conditional_conflicts": [], "allowed_conflicts": []},
        label_block_v1={},
        evaluate_ticker_result={
            "ticker": "TEST",
            "run_selection_status": "selected",
            "offline_reprocess_status": "completed",
            "artifact_completeness": "pass",
            "artifact_missing_files": [],
            "admitted_conflicts": [c["conflict_id"] for c in payload["conflicts"]],
            "candidate_conflicts": [],
            "stance_source": "llm_semantic",
        },
        conflict_payload=payload,
        graph_payload={},
        alpha_matches_payload={"matches": [{"claim_id": "c", "match_status": "matched", "matched_alpha": "A"}]},
    )


# ---------------------------------------------------------------------------------------------------------------------------------------
# control: every condition B2 checks is met
# ---------------------------------------------------------------------------------------------------------------------------------------


def test_control_all_necessary_conditions_met_b2_admits_and_the_required_pair_passes():
    payload = _detect(A_ACTIVE, B_ACTIVE, A_SUPPORT, B_SUPPORT)
    result, entry = _must_detect(payload)
    assert entry["admissibility_status"] == "admitted" and entry["reason_codes"] == []
    assert (entry["bull_supporting_evidence_count"], entry["bear_supporting_evidence_count"]) == (2, 2)
    assert (result["state"], result["verdict"]) == (PAIR_STATE_ADMITTED, VERDICT_PASS)
    formal = _formal(payload)
    assert formal["formal_status"] == "pass" and formal["failure_reasons"] == [] and formal["coverage"]["pass_is_vacuous"] is False


# ---------------------------------------------------------------------------------------------------------------------------------------
# B2's correct rejections are not missed detections
# ---------------------------------------------------------------------------------------------------------------------------------------


def test_one_independent_supporting_fact_per_side_is_a_correct_b2_rejection_not_a_miss():
    payload = _detect(A_ACTIVE, B_ACTIVE, A_SUPPORT[:1], B_SUPPORT[:1])
    result, entry = _must_detect(payload)
    assert (entry["bull_supporting_evidence_count"], entry["bear_supporting_evidence_count"]) == (1, 1) < (MIN_SUPPORTING_EVIDENCE_PER_SIDE,) * 2
    assert {"INSUFFICIENT_BULL_SUPPORTING_EVIDENCE", "INSUFFICIENT_BEAR_SUPPORTING_EVIDENCE"} <= set(entry["reason_codes"])
    assert (result["state"], result["verdict"]) == (PAIR_STATE_B2_REJECTED, VERDICT_NOT_APPLICABLE)
    assert "not a missed detection" in result["detail"]
    formal = _formal(payload)
    assert formal["failure_reasons"] == [] and formal["formal_status"] != "fail"


def test_two_facts_per_side_but_no_ticker_specific_support_is_a_correct_b2_rejection_not_a_miss():
    payload = _detect(A_ACTIVE, B_ACTIVE, A_SUPPORT_NOT_TICKER_SPECIFIC, B_SUPPORT)
    result, entry = _must_detect(payload)
    assert entry["bull_supporting_evidence_count"] == 2 and entry["bull_ticker_specific_support_count"] == 0
    assert entry["reason_codes"] == ["NO_BULL_TICKER_SPECIFIC_SUPPORT"]
    assert (result["state"], result["verdict"]) == (PAIR_STATE_B2_REJECTED, VERDICT_NOT_APPLICABLE)
    # the count alone (2 >= 2) would have said "evidence present": the ticker-specificity condition is part of the approved gate
    assert _formal(payload)["failure_reasons"] == []


def test_two_facts_per_side_but_a_score_below_the_threshold_is_a_correct_b2_rejection_not_a_miss():
    weak_a = activation_entry("A", score=40.0, status="candidate", direction="positive")
    payload = _detect(weak_a, B_ACTIVE, A_SUPPORT, B_SUPPORT)
    result, entry = _must_detect(payload)
    assert entry["bull_supporting_evidence_count"] == 2 and entry["bull_score"] == 40.0
    assert entry["reason_codes"] == ["BULL_SCORE_BELOW_THRESHOLD"]
    assert (result["state"], result["verdict"]) == (PAIR_STATE_B2_REJECTED, VERDICT_NOT_APPLICABLE)
    assert _formal(payload)["failure_reasons"] == []


# ---------------------------------------------------------------------------------------------------------------------------------------
# no supporting evidence: nothing is forced
# ---------------------------------------------------------------------------------------------------------------------------------------


def test_no_supporting_evidence_forces_nothing_and_is_recorded_as_the_detectors_own_absence_of_evidence():
    payload = _detect(A_ACTIVE, B_ACTIVE, [], [])
    result, entry = _must_detect(payload)
    assert entry["has_admissibility_block"] is False and "MISSING_LEFT_EVIDENCE" in entry["entry_reason_codes"]
    assert (result["state"], result["verdict"]) == (PAIR_STATE_NO_QUALIFYING_EVIDENCE, VERDICT_NOT_APPLICABLE)
    assert payload["conflicts"] == [] and payload["main_conflict"] is None  # no conflict was generated
    assert _formal(payload)["failure_reasons"] == []


# ---------------------------------------------------------------------------------------------------------------------------------------
# a pair that was never judged is not "no evidence" -- and not "conditions met" either
# ---------------------------------------------------------------------------------------------------------------------------------------


def test_an_alpha_that_was_never_identified_leaves_a_pair_that_is_not_evaluated_while_the_claims_that_support_it_are_still_in_the_record():
    payload = _detect(None, B_ACTIVE, A_SUPPORT, B_SUPPORT)  # Alpha A has claims in alpha_matches but no activation entry at all
    result, entry = _must_detect(payload)
    assert entry["has_admissibility_block"] is False and entry["entry_reason_codes"] == ["MISSING_LEFT_ACTIVATION"]
    assert entry["evidence_audit_counts"] == {"alpha_a": 2, "alpha_b": 2}  # the detector's own audit lists the supporting claims
    assert (result["state"], result["verdict"]) == (PAIR_STATE_NOT_EVALUATED, VERDICT_NOT_EVALUABLE)
    assert "not evidence of absence" in result["detail"] and "no evidence to require" not in result["detail"]
    formal = _formal(payload)
    assert formal["formal_status"] == "needs_review" and formal["failure_reasons"] == []
    assert [(r["family"], r["pair"], r["verdict"]) for r in formal["review_reasons"]] == [("must_detect_if_evidence_present", "A__B", "not_evaluable")]


def test_an_alpha_not_at_an_admissible_activation_state_leaves_a_pair_that_is_not_evaluated():
    capped = activation_entry("A", score=60.0, status="capped_active", direction="positive")
    payload = _detect(capped, B_ACTIVE, A_SUPPORT, B_SUPPORT)
    result, entry = _must_detect(payload)
    assert entry["has_admissibility_block"] is False and "BELOW_ACTIVATION_THRESHOLD" in entry["entry_reason_codes"]
    assert (result["state"], result["verdict"]) == (PAIR_STATE_NOT_EVALUATED, VERDICT_NOT_EVALUABLE)
    assert _formal(payload)["formal_status"] == "needs_review"


def test_a_pair_the_run_never_recorded_is_not_evaluated_and_names_how_many_candidates_it_did_record():
    payload = _detect(A_ACTIVE, B_ACTIVE, A_SUPPORT, B_SUPPORT)
    payload["arbitration"]["candidate_evaluations"] = []  # the saved record does not list the pair at all
    lookup = pair_admissibility_lookup(payload)
    assert pair_record_state(lookup.get("A__B")) == "no_arbitration_record"
    (result,) = evaluate_must_detect_if_evidence_present(
        ticker_v2_label={"required_conflicts": ["A__B"]}, admissibility_lookup=lookup, declared_pair_count=payload["arbitration"]["declared_pair_count"]
    )
    assert result["verdict"] == VERDICT_NOT_EVALUABLE
    assert "1 declared candidate pairs were recorded" in result["detail"]


# ---------------------------------------------------------------------------------------------------------------------------------------
# a genuine omission is detected -- by CONTROLLED MODIFICATION of the control record
# ---------------------------------------------------------------------------------------------------------------------------------------


def test_controlled_modification_a_record_that_meets_every_condition_but_is_not_admitted_is_a_missed_required_conflict():
    """NOT a production B2 result. B2 admits a pair exactly when it records no rejection reason, so this record cannot occur; it is the control
    record with its outcome hand-edited to 'suppressed / candidate, no reason', to prove the check detects an omission when every necessary
    condition (score, supporting facts, ticker-specific support) is satisfied."""
    payload = _detect(A_ACTIVE, B_ACTIVE, A_SUPPORT, B_SUPPORT)
    (entry,) = payload["arbitration"]["candidate_evaluations"]
    entry["outcome"] = "suppressed"
    entry["admissibility"]["status"] = "candidate"
    entry["admissibility"]["reason_codes"] = []
    entry["reason_codes"] = []
    result, facts = _must_detect(payload)
    assert (facts["bull_supporting_evidence_count"], facts["bear_supporting_evidence_count"]) == (2, 2)
    assert (result["state"], result["verdict"]) == (PAIR_STATE_B2_NO_REASON, VERDICT_FAIL)
    formal = _formal({**payload, "conflicts": []})
    assert formal["formal_status"] == "fail"
    assert [(r["family"], r["pair"], r["state"]) for r in formal["failure_reasons"]] == [("must_detect_if_evidence_present", "A__B", PAIR_STATE_B2_NO_REASON)]


@pytest.mark.parametrize(
    "a_entry, a_support, b_support, expected_state",
    [
        (A_ACTIVE, A_SUPPORT, B_SUPPORT, PAIR_STATE_ADMITTED),
        (A_ACTIVE, A_SUPPORT[:1], B_SUPPORT[:1], PAIR_STATE_B2_REJECTED),
        (A_ACTIVE, [], [], PAIR_STATE_NO_QUALIFYING_EVIDENCE),
        (None, A_SUPPORT, B_SUPPORT, PAIR_STATE_NOT_EVALUATED),
    ],
)
def test_only_the_controlled_modification_ever_yields_a_fail_every_state_the_real_detector_writes_is_something_else(a_entry, a_support, b_support, expected_state):
    payload = _detect(a_entry, B_ACTIVE, a_support, b_support)
    result, _entry = _must_detect(payload)
    assert result["state"] == expected_state and result["verdict"] != VERDICT_FAIL
