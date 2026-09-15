"""John's Primary vs Secondary Evidence Source-Role Qualification (Step 6).

Evidence QUALIFICATION for activation-input purposes only. These tests
verify: (1) the centralized role authority's qualification decisions in
isolation, (2) end-to-end wiring into Activation v2 (score_alpha_v2) and
Conflict Detector (detect_alpha_conflicts) so a Secondary agent's
restatement of an already-counted Primary fact cannot inflate either
activation or B2's unique_fact_count, and (3) the explicit invariants this
task requires: B1 stance labels, Alpha Mapper semantics, and every B2/B4
threshold VALUE are unchanged -- only which evidence inputs reach them
changes. Zero Provider calls, zero TradingAgents calls -- pure unit/
integration tests over hand-built fixtures.
"""

from __future__ import annotations

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.conflict_engine.conflict_admissibility import (
    ALPHA_SCORE_THRESHOLD,
    MIN_SUPPORTING_EVIDENCE_PER_SIDE,
    MIN_TICKER_SPECIFIC_SUPPORT_PER_SIDE,
)
from comqutor_alpha.conflict_engine.conflict_detector import detect_alpha_conflicts
from comqutor_alpha.graph_engine.activation_scorer_v2 import (
    AGENT_COVERAGE_DENOMINATOR,
    CROSS_AGENT_CONFIRMATION_DENOMINATOR,
    score_alpha_v2,
)
from comqutor_alpha.graph_engine.evidence_source_role import (
    PRIMARY_RESEARCH_AGENTS,
    REASON_PRIMARY_QUALIFIED,
    REASON_SECONDARY_CAUSALITY_UNPROVEN,
    REASON_SECONDARY_DUPLICATE_OF_PRIMARY,
    REASON_SECONDARY_NOT_TICKER_SPECIFIC,
    REASON_SECONDARY_QUALIFIED_CAUSAL_EVIDENCE,
    REASON_UNKNOWN_SOURCE_ROLE,
    SOURCE_ROLE_PRIMARY_RESEARCH,
    SOURCE_ROLE_SECONDARY_DECISION_OR_DEBATE,
    SOURCE_ROLE_UNKNOWN,
    qualify_evidence_group,
    source_role_for_agent,
)
from tests.fixtures.week4_conflict_cases import (
    activation_entry,
    activation_payload,
    match_record,
    two_alpha_taxonomy,
)

TAXONOMY = load_alpha_taxonomy()
AS_OF = "2026-06-30"
RUN_TS = "2026-06-30"


def _record(claim_id, agent, claim, *, alpha_id, relation="activation", assertion_status="asserted"):
    return {
        "run_id": "role_test_run",
        "ticker": "ACME",
        "agent": agent,
        "claim_id": claim_id,
        "source_agent_output_id": f"{agent}:{claim_id}",
        "claim": claim,
        "evidence": claim,
        "match_status": "matched",
        "matched_alpha": alpha_id,
        "score": 1.0,
        "assertion_status": assertion_status,
        "semantic_polarity": "activation",
        "factor_score": 1.0,
        "keyword_score": 1.0,
        "eligible_candidates": [
            {
                "alpha_id": alpha_id,
                "relation": relation,
                "matched_keywords": ["demand"],
                "matched_factors": ["Revenue Growth"],
            }
        ],
        "claim_quality": "analytical",
        "direction": "positive",
    }


def _payload(*records):
    return {"run_id": "role_test_run", "ticker": "ACME", "matches": list(records)}


def _score(alpha_id, payload):
    return score_alpha_v2(
        alpha_id, payload, TAXONOMY, ticker="ACME", run_timestamp=RUN_TS, as_of=AS_OF
    )


def _member(agent, *, relation="activation", assertion_status="asserted", claim_id="c1"):
    return {
        "claim_id": claim_id,
        "agent": agent,
        "relation": relation,
        "assertion_status": assertion_status,
    }


# ---------------------------------------------------------------------------
# 1-6: qualify_evidence_group unit tests (the centralized authority itself)
# ---------------------------------------------------------------------------


def test_1_primary_agent_alone_qualifies():
    """A PRIMARY_RESEARCH agent's claim qualifies under existing rules,
    unchanged -- reason PRIMARY_QUALIFIED."""
    members = [_member("fundamental_agent")]
    out = qualify_evidence_group(members, is_ticker_specific=lambda m: False)
    assert out[0]["source_role"] == SOURCE_ROLE_PRIMARY_RESEARCH
    assert out[0]["activation_eligible"] is True
    assert out[0]["activation_qualification_reason"] == REASON_PRIMARY_QUALIFIED


def test_2_secondary_agent_not_ticker_specific_excluded():
    """A Secondary-only group that fails the ticker-specific gate is
    ineligible -- SECONDARY_NOT_TICKER_SPECIFIC, never silently promoted."""
    members = [_member("trader", relation="activation", assertion_status="asserted")]
    out = qualify_evidence_group(members, is_ticker_specific=lambda m: False)
    assert out[0]["source_role"] == SOURCE_ROLE_SECONDARY_DECISION_OR_DEBATE
    assert out[0]["activation_eligible"] is False
    assert out[0]["activation_qualification_reason"] == REASON_SECONDARY_NOT_TICKER_SPECIFIC


def test_3_secondary_agent_ticker_specific_strong_causal_qualifies():
    """A Secondary agent's claim that IS independently ticker-specific and
    carries the strongest already-existing causal signal (relation
    'activation' + assertion_status 'asserted') qualifies --
    SECONDARY_QUALIFIED_CAUSAL_EVIDENCE, reusing existing fields rather than
    a new keyword classifier."""
    members = [_member("portfolio_manager", relation="activation", assertion_status="asserted")]
    out = qualify_evidence_group(members, is_ticker_specific=lambda m: True)
    assert out[0]["activation_eligible"] is True
    assert out[0]["activation_qualification_reason"] == REASON_SECONDARY_QUALIFIED_CAUSAL_EVIDENCE


def test_4_secondary_agent_ticker_specific_weak_relation_unproven():
    """Ticker-specific alone is not enough: a weaker relation
    ('conditional') fails the strong-causal bar -- conservative default
    SECONDARY_CAUSALITY_UNPROVEN, never promoted to eligible."""
    members = [_member("bull_researcher", relation="conditional", assertion_status="asserted")]
    out = qualify_evidence_group(members, is_ticker_specific=lambda m: True)
    assert out[0]["activation_eligible"] is False
    assert out[0]["activation_qualification_reason"] == REASON_SECONDARY_CAUSALITY_UNPROVEN


def test_5_secondary_agent_ticker_specific_non_asserted_unproven():
    """Ticker-specific + relation 'activation' but assertion_status not
    'asserted' (e.g. 'conditional') also fails the strong-causal bar --
    both fields must independently clear the bar, not just one."""
    members = [_member("research_manager", relation="activation", assertion_status="conditional")]
    out = qualify_evidence_group(members, is_ticker_specific=lambda m: True)
    assert out[0]["activation_eligible"] is False
    assert out[0]["activation_qualification_reason"] == REASON_SECONDARY_CAUSALITY_UNPROVEN


def test_6_unknown_agent_always_excluded_even_if_strong_and_ticker_specific():
    """An unrecognized/future agent name defaults-deny to UNKNOWN,
    regardless of how strong its ticker-specific/causal signal looks --
    never silently treated as PRIMARY."""
    members = [_member("some_future_agent", relation="activation", assertion_status="asserted")]
    out = qualify_evidence_group(members, is_ticker_specific=lambda m: True)
    assert out[0]["source_role"] == SOURCE_ROLE_UNKNOWN
    assert out[0]["activation_eligible"] is False
    assert out[0]["activation_qualification_reason"] == REASON_UNKNOWN_SOURCE_ROLE


# ---------------------------------------------------------------------------
# 7: duplication protection at the group level
# ---------------------------------------------------------------------------


def test_7_secondary_restatement_in_same_group_as_primary_is_duplicate_not_double_counted():
    """A trader restating a Primary analyst's fact WITHIN THE SAME Evidence
    Fact group does not independently qualify -- SECONDARY_DUPLICATE_OF_PRIMARY,
    ineligible -- so it cannot inflate the group's count. The Primary member
    itself remains eligible."""
    members = [
        _member("market_agent", claim_id="p1"),
        _member("trader", claim_id="s1"),
    ]
    out = qualify_evidence_group(members, is_ticker_specific=lambda m: True)
    by_claim = {m["claim_id"]: m for m in out}
    assert by_claim["p1"]["activation_eligible"] is True
    assert by_claim["p1"]["activation_qualification_reason"] == REASON_PRIMARY_QUALIFIED
    assert by_claim["s1"]["activation_eligible"] is False
    assert by_claim["s1"]["activation_qualification_reason"] == REASON_SECONDARY_DUPLICATE_OF_PRIMARY


# ---------------------------------------------------------------------------
# 8-9: end-to-end Activation v2 integration
# ---------------------------------------------------------------------------


def test_8_trader_restating_primary_claim_does_not_inflate_activation_evidence_count():
    """Integration: a trader claim that is a near-identical restatement of a
    Primary analyst's claim (same semantic group, both ticker-specific) must
    not add a second unique evidence fact to the activation score -- the
    unique_evidence_count with the trader restatement present must equal the
    count without it."""
    primary_only = _payload(
        _record("p1", "market_agent", "ACME datacenter demand is accelerating broadly.", alpha_id="A101"),
    )
    with_secondary_restatement = _payload(
        _record("p1", "market_agent", "ACME datacenter demand is accelerating broadly.", alpha_id="A101"),
        _record("s1", "trader", "ACME datacenter demand is accelerating broadly.", alpha_id="A101"),
    )
    result_primary_only = _score("A101", primary_only)
    result_with_secondary = _score("A101", with_secondary_restatement)
    assert result_primary_only["unique_evidence_count"] == 1
    assert result_with_secondary["unique_evidence_count"] == 1
    assert result_primary_only["activation_score"] == result_with_secondary["activation_score"]


def test_9_portfolio_manager_recommendation_without_independent_evidence_excluded_from_activation():
    """A portfolio_manager-only claim with no ticker-specific/strong-causal
    signal of its own contributes zero activation evidence -- activation
    stays inactive (0), never silently promoted because it came from a
    real, recognized agent."""
    payload = _payload(
        _record(
            "s1", "portfolio_manager", "We recommend increasing exposure here.",
            alpha_id="A101", relation="mixed", assertion_status="conditional",
        ),
    )
    result = _score("A101", payload)
    assert result["unique_evidence_count"] == 0
    assert result["activation_score"] == 0.0
    assert result["status"] == "inactive"


# ---------------------------------------------------------------------------
# 10: end-to-end Conflict Detector / B2 integration
# ---------------------------------------------------------------------------


def test_10_bull_bear_debate_restatement_does_not_inflate_b2_unique_fact_count():
    """Integration: bull_researcher restating a Primary fact (same semantic
    group) must not push a side over B2's >=2 unique supports_alpha facts
    threshold on its own -- the side must still fail on insufficient
    evidence with only one genuinely independent fact plus one duplicate
    restatement."""
    taxonomy = two_alpha_taxonomy("A", "B")
    activation = activation_payload(
        activation_entry("A", score=90.0, direction="positive"),
        activation_entry("B", score=90.0, direction="negative"),
    )
    matches = [
        match_record("a1", "A", agent="market_agent", ticker_specific_text="ACME"),
        match_record(
            "a1b", "A", agent="bull_researcher", ticker_specific_text="ACME",
            evidence="ACME evidence for a1",  # identical text -> same semantic group as a1
        ),
        match_record("b1", "B", agent="market_agent", ticker_specific_text="ACME"),
        match_record("b2", "B", agent="news_agent", ticker_specific_text="ACME"),
    ]
    result = detect_alpha_conflicts(
        run_id="role_conflict_run", ticker="ACME", activation_payload=activation,
        alpha_matches=matches, taxonomy=taxonomy,
    )
    conflict = next((c for c in result["conflicts"] if c["conflict_id"] == "A__B"), None)
    evaluation = next(
        c for c in result["arbitration"]["candidate_evaluations"] if c["alpha_a"] == "A" and c["alpha_b"] == "B"
    )
    # Side A has only ONE genuinely unique qualifying fact (a1; a1b is a
    # duplicate restatement of it) -- B2 admission must fail for A/B.
    assert conflict is None
    assert evaluation["outcome"] == "suppressed"
    assert evaluation["admissibility"]["bull_supporting_evidence_count"] == 1


# ---------------------------------------------------------------------------
# 11-12: role is not a score multiplier
# ---------------------------------------------------------------------------


def test_11_eligible_secondary_evidence_contributes_identically_to_eligible_primary_evidence():
    """Eligibility is binary, never a role-based multiplier: a
    Secondary-only claim that DOES independently qualify
    (SECONDARY_QUALIFIED_CAUSAL_EVIDENCE) contributes to
    EvidenceQuality/AgentIndependence using the exact same match_score/
    relation/assertion_status weighting formula as an otherwise-identical
    Primary claim -- no 1.0/0.5-style discount."""
    primary_payload = _payload(
        _record("p1", "market_agent", "ACME datacenter demand is accelerating broadly.", alpha_id="A101"),
    )
    secondary_payload = _payload(
        _record("s1", "portfolio_manager", "ACME datacenter demand is accelerating broadly.", alpha_id="A101"),
    )
    primary_result = _score("A101", primary_payload)
    secondary_result = _score("A101", secondary_payload)
    assert primary_result["components"]["evidence_quality"]["raw"] == (
        secondary_result["components"]["evidence_quality"]["raw"]
    )
    assert primary_result["unique_evidence_count"] == secondary_result["unique_evidence_count"] == 1


def test_12_genuinely_independent_secondary_evidence_does_count_when_no_primary_exists():
    """A Secondary-only group with no Primary member at all, that clears the
    ticker-specific + strong-causal bar, is real qualifying evidence -- Step
    6 does not delete Secondary agents' value, it only stops UNQUALIFIED
    restatement from inflating counts that a Primary fact already covers."""
    payload = _payload(
        _record(
            "s1", "conservative_risk_analyst", "ACME leverage risk is contained given strong cash flow.",
            alpha_id="A301",
        ),
    )
    result = _score("A301", payload)
    assert result["unique_evidence_count"] == 1
    assert result["activation_score"] > 0.0


# ---------------------------------------------------------------------------
# 13-14: invariants -- nothing is destructively changed
# ---------------------------------------------------------------------------


def test_13_qualification_never_mutates_existing_stance_relation_or_assertion_fields():
    """qualify_evidence_group only ADDS fields -- it never rewrites B1
    stance, relation, or assertion_status, and it never reinterprets them by
    role (John's explicit non-negotiable)."""
    original = _member("bull_researcher", relation="conditional", assertion_status="conditional", claim_id="c9")
    out = qualify_evidence_group([dict(original)], is_ticker_specific=lambda m: True)
    for key, value in original.items():
        assert out[0][key] == value


def test_14_evidence_fact_schema_remains_backwards_readable():
    """The four additive fields never replace or remove any pre-existing
    key -- a consumer reading only the original schema still finds every
    field it always had, on both eligible and ineligible members."""
    members = [_member("market_agent", claim_id="p1"), _member("trader", claim_id="s1")]
    out = qualify_evidence_group(members, is_ticker_specific=lambda m: True)
    for original, qualified in zip(members, out):
        assert set(original.keys()) <= set(qualified.keys())
    for qualified in out:
        assert {
            "source_agent",
            "source_role",
            "activation_eligible",
            "activation_qualification_reason",
        } <= set(qualified.keys())


# ---------------------------------------------------------------------------
# 15: B1/B2/B4 threshold VALUES are unchanged
# ---------------------------------------------------------------------------


def test_15_b2_and_b4_threshold_constants_are_unchanged_in_value():
    """Step 6 only changes WHICH evidence inputs are eligible, never any
    B2/B4 threshold value -- this pins the exact frozen literals John
    specified so a future change to these constants (not just to this
    qualification layer) would be caught immediately."""
    assert ALPHA_SCORE_THRESHOLD == 50.0
    assert MIN_SUPPORTING_EVIDENCE_PER_SIDE == 2
    assert MIN_TICKER_SPECIFIC_SUPPORT_PER_SIDE == 1
    assert AGENT_COVERAGE_DENOMINATOR == 3
    assert CROSS_AGENT_CONFIRMATION_DENOMINATOR == 2


# ---------------------------------------------------------------------------
# Bonus: role-mapping sanity (real production agent inventory, Section 3)
# ---------------------------------------------------------------------------


def test_real_production_agent_inventory_maps_as_designed():
    for agent in ("fundamental_agent", "market_agent", "sentiment_agent", "news_agent"):
        assert source_role_for_agent(agent) == SOURCE_ROLE_PRIMARY_RESEARCH
    for agent in (
        "bull_researcher", "bear_researcher", "research_manager", "trader",
        "portfolio_manager", "conservative_risk_analyst", "neutral_risk_analyst",
        "aggressive_risk_analyst",
    ):
        assert source_role_for_agent(agent) == SOURCE_ROLE_SECONDARY_DECISION_OR_DEBATE
    assert source_role_for_agent("") == SOURCE_ROLE_UNKNOWN
    assert source_role_for_agent(None) == SOURCE_ROLE_UNKNOWN
    assert PRIMARY_RESEARCH_AGENTS.isdisjoint(
        {"bull_researcher", "bear_researcher", "trader", "portfolio_manager"}
    )
