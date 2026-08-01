"""Regime Evidence Integrity Shadow Layer tests.

Product Findings Closure and Regime Evidence Integrity Sprint, Track B.
"""

from __future__ import annotations

import inspect

from comqutor_alpha.graph_engine import evidence_integrity
from comqutor_alpha.graph_engine.evidence_integrity import (
    STATUS_CONSISTENT,
    STATUS_INSUFFICIENT_PRIMARY_EVIDENCE,
    STATUS_NOT_REGIME_CANDIDATE,
    STATUS_OVERLAP_RISK,
    STATUS_UNVERIFIED_EXPOSURE,
    build_alpha_evidence_integrity_payload,
    build_evidence_groups,
    evaluate_shadow_regime_verdict,
)


def _match(
    claim_id,
    matched_alpha,
    *,
    claim,
    agent="news_agent",
    score=0.8,
    factors=None,
    assertion_status="asserted",
    semantic_polarity="activation",
    evidence=None,
    source_agent_output_id=None,
    run_id="run1",
    ticker="NVDA",
    **extra,
):
    record = {
        "claim_id": claim_id,
        "matched_alpha": matched_alpha,
        "match_status": "matched",
        "claim": claim,
        "evidence": evidence or claim,
        "agent": agent,
        "score": score,
        "factors": factors or [],
        "entities": [ticker],
        "assertion_status": assertion_status,
        "semantic_polarity": semantic_polarity,
        "direction": "positive",
        "claim_quality": "analytical",
        "source_agent_output_id": source_agent_output_id or f"{run_id}:{agent}:report",
        "run_id": run_id,
        "ticker": ticker,
        # Evidence Integrity Completion Sprint, Track A: the shared
        # canonical eligibility selector requires a resolved relation in
        # {activation, conditional, mixed} (the same "supporting evidence"
        # definition Activation production scoring already enforces) --
        # default to a qualifying relation so this module's own tests
        # continue to exercise grouping/attribution, not eligibility, unless
        # a test explicitly overrides ``eligible_candidates``.
        "eligible_candidates": [{"alpha_id": matched_alpha, "relation": "activation"}],
    }
    record.update(extra)
    return record


def _matches_payload(records):
    return {"matches": records}


def _edge(source, target, *, claim_ids, edge_type="causal", assertion_status="asserted"):
    return {
        "source": source,
        "target": target,
        "edge_type": edge_type,
        "assertion_status": assertion_status,
        "claim_ids": list(claim_ids),
    }


# ---------------------------------------------------------------------------
# 1. Exact duplicate grouping
# ---------------------------------------------------------------------------


def test_exact_duplicate_group_id_merges():
    records = [
        _match("c1", "A101", claim="GPU demand is increasing.", agent="news_agent"),
        _match("c2", "A101", claim="Completely different wording here.", agent="market_agent"),
    ]
    structured_records = [
        {"claim_id": "c1", "duplicate_group_id": "dup-1"},
        {"claim_id": "c2", "duplicate_group_id": "dup-1"},
    ]
    groups = build_evidence_groups(
        _matches_payload(records), run_id="run1", ticker="NVDA", structured_records=structured_records
    )
    assert len(groups) == 1
    assert set(groups[0].claim_ids) == {"c1", "c2"}


def test_byte_identical_claim_text_merges():
    records = [
        _match("c1", "A101", claim="GPU demand is increasing.", agent="news_agent", factors=["GPU Demand"]),
        _match("c2", "A101", claim="GPU demand is increasing.", agent="market_agent", factors=["GPU Demand"]),
    ]
    groups = build_evidence_groups(_matches_payload(records), run_id="run1", ticker="NVDA")
    assert len(groups) == 1
    assert set(groups[0].claim_ids) == {"c1", "c2"}


# ---------------------------------------------------------------------------
# 2. Cross-agent paraphrase grouping
# ---------------------------------------------------------------------------


def test_cross_agent_paraphrase_with_shared_factor_signature_merges():
    """Same canonical factor, assertion status, and polarity, no numeric or
    date anchor to disagree on, but completely different agents and
    surface wording -- priority 3 (factor/event signature) should merge
    them, and both agents must be preserved on the resulting group."""
    records = [
        _match(
            "c1", "A101",
            claim="AMD leads chip selloff amid weakening risk appetite.",
            agent="news_agent", factors=["AI Demand"],
        ),
        _match(
            "c2", "A101",
            claim="AMD named in AI memory selloff as risk appetite weakens.",
            agent="sentiment_agent", factors=["AI Demand"],
        ),
    ]
    groups = build_evidence_groups(_matches_payload(records), run_id="run1", ticker="NVDA")
    assert len(groups) == 1
    group = groups[0]
    assert set(group.claim_ids) == {"c1", "c2"}
    assert set(group.agents) == {"news_agent", "sentiment_agent"}


def test_group_can_support_multiple_alphas_with_primary_and_secondary():
    """One evidence group's members may be individually matched to
    different alphas -- the group must keep every one of them as
    supported_alpha_ids, split into a primary and secondary(ies), never
    dropped."""
    records = [
        _match(
            "c1", "A101",
            claim="AI infrastructure demand is expanding across the sector.",
            agent="news_agent", factors=["AI Demand"], score=0.9,
        ),
        _match(
            "c2", "A103",
            claim="AI infrastructure demand is expanding across the sector.",
            agent="sentiment_agent", factors=["AI Demand"], score=0.6,
        ),
    ]
    groups = build_evidence_groups(_matches_payload(records), run_id="run1", ticker="NVDA")
    assert len(groups) == 1
    group = groups[0]
    assert set(group.supported_alpha_ids) == {"A101", "A103"}
    assert group.primary_alpha_id == "A101"  # higher match_score wins
    assert group.secondary_alpha_ids == ("A103",)


# ---------------------------------------------------------------------------
# 3-7. Must-not-merge guards
# ---------------------------------------------------------------------------


def test_different_numbers_never_merge():
    records = [
        _match("c1", "A301", claim="Revenue grew 20% year over year.", factors=["Revenue Growth"]),
        _match("c2", "A301", claim="Revenue grew 30% year over year.", factors=["Revenue Growth"]),
    ]
    groups = build_evidence_groups(_matches_payload(records), run_id="run1", ticker="NVDA")
    assert len(groups) == 2


def test_different_dates_never_merge():
    records = [
        _match("c1", "A301", claim="Guidance issued in January 2026.", factors=["Guidance"]),
        _match("c2", "A301", claim="Guidance issued in March 2026.", factors=["Guidance"]),
    ]
    groups = build_evidence_groups(_matches_payload(records), run_id="run1", ticker="NVDA")
    assert len(groups) == 2


def test_positive_and_negative_polarity_never_merge():
    records = [
        _match(
            "c1", "A304", claim="Valuation risk is real and creates downside.",
            factors=["Valuation Risk"], semantic_polarity="activation",
        ),
        _match(
            "c2", "A304", claim="Valuation risk is real and creates downside.",
            factors=["Valuation Risk"], semantic_polarity="invalidation",
        ),
    ]
    groups = build_evidence_groups(_matches_payload(records), run_id="run1", ticker="NVDA")
    assert len(groups) == 2


def test_asserted_and_negated_never_merge():
    """Evidence Integrity Completion Sprint, Track A: the shared canonical
    eligibility selector (shared with Activation production scoring) now
    excludes negated claims from evidence candidacy entirely -- a negated
    claim is counter-evidence, not a second independent supporting fact, so
    it contributes no group of its own (never merges with the asserted
    claim, and never appears as a rival singleton group either)."""
    records = [
        _match(
            "c1", "A304", claim="Valuation risk is real and creates downside.",
            factors=["Valuation Risk"], assertion_status="asserted",
        ),
        _match(
            "c2", "A304", claim="Valuation risk is real and creates downside.",
            factors=["Valuation Risk"], assertion_status="negated",
        ),
    ]
    groups = build_evidence_groups(_matches_payload(records), run_id="run1", ticker="NVDA")
    assert len(groups) == 1
    assert set(groups[0].claim_ids) == {"c1"}


def test_conditional_and_asserted_never_merge():
    records = [
        _match(
            "c1", "A304", claim="Valuation risk is real and creates downside.",
            factors=["Valuation Risk"], assertion_status="asserted",
        ),
        _match(
            "c2", "A304", claim="Valuation risk is real and creates downside.",
            factors=["Valuation Risk"], assertion_status="conditional",
        ),
    ]
    groups = build_evidence_groups(_matches_payload(records), run_id="run1", ticker="NVDA")
    assert len(groups) == 2


def test_different_relation_endpoints_never_merge():
    """Two claims sharing the same factor/assertion/polarity signature but
    backing two DIFFERENT admitted structure-graph edges must never merge,
    even though priority 3 would otherwise consider their signature a
    match."""
    records = [
        _match("c1", "A101", claim="AI demand drives GPU sales growth.", factors=["AI Demand"]),
        _match("c2", "A103", claim="AI demand drives GPU sales growth.", factors=["AI Demand"]),
    ]
    graph_edges = [
        _edge("ai_demand", "gpu_sales", claim_ids=["c1"]),
        _edge("ai_demand", "datacenter_capex", claim_ids=["c2"]),
    ]
    groups = build_evidence_groups(
        _matches_payload(records), run_id="run1", ticker="NVDA", graph_edges=graph_edges
    )
    assert len(groups) == 2


def test_identical_relation_triple_does_merge():
    """Control case for the above: two claims backing the exact SAME
    structure-graph edge must merge (priority 2)."""
    records = [
        _match("c1", "A101", claim="AI demand drives GPU sales growth.", factors=["AI Demand"]),
        _match("c2", "A101", claim="Totally different phrasing about the same effect.", factors=["AI Demand"]),
    ]
    graph_edges = [_edge("ai_demand", "gpu_sales", claim_ids=["c1", "c2"])]
    groups = build_evidence_groups(
        _matches_payload(records), run_id="run1", ticker="NVDA", graph_edges=graph_edges
    )
    assert len(groups) == 1
    assert set(groups[0].claim_ids) == {"c1", "c2"}


def test_shared_ai_keyword_alone_never_merges_unrelated_claims():
    """Spec's explicit anti-pattern: two claims must never merge merely
    because both happen to mention 'AI' -- everything else about them
    (factor, numbers) must differ here, so they must stay separate."""
    records = [
        _match("c1", "A101", claim="AI chip demand is strong this quarter.", factors=["AI Demand"]),
        _match(
            "c2", "A304", claim="AI valuation multiples look stretched at 45x earnings.",
            factors=["Valuation Risk"],
        ),
    ]
    groups = build_evidence_groups(_matches_payload(records), run_id="run1", ticker="NVDA")
    assert len(groups) == 2


def test_different_financial_facts_never_merge():
    """Revenue and margin are different financial facts even when
    otherwise similarly phrased -- distinct factors must block merging."""
    records = [
        _match("c1", "A301", claim="The company reported strong results this quarter.", factors=["Revenue Growth"]),
        _match("c2", "A301", claim="The company reported strong results this quarter.", factors=["Margin"]),
    ]
    groups = build_evidence_groups(_matches_payload(records), run_id="run1", ticker="NVDA")
    assert len(groups) == 2


# ---------------------------------------------------------------------------
# 8-9. Stable IDs and input-order independence
# ---------------------------------------------------------------------------


def test_group_id_is_stable_across_reruns():
    records = [
        _match("c1", "A101", claim="AI demand is expanding.", factors=["AI Demand"]),
    ]
    groups_a = build_evidence_groups(_matches_payload(records), run_id="run1", ticker="NVDA")
    groups_b = build_evidence_groups(_matches_payload(records), run_id="run1", ticker="NVDA")
    assert groups_a[0].evidence_group_id == groups_b[0].evidence_group_id


def test_group_id_is_not_a_random_uuid():
    """Same member claim_ids -> same id, regardless of how many times or
    in what surrounding context the group is built."""
    records = [
        _match("c1", "A101", claim="AI demand is expanding.", factors=["AI Demand"]),
        _match("c2", "A101", claim="AI demand is expanding.", factors=["AI Demand"], agent="market_agent"),
    ]
    groups_first = build_evidence_groups(_matches_payload(records), run_id="run1", ticker="NVDA")
    groups_again = build_evidence_groups(_matches_payload(list(reversed(records))), run_id="run1", ticker="NVDA")
    assert groups_first[0].evidence_group_id == groups_again[0].evidence_group_id


def test_input_order_independence():
    records = [
        _match("c1", "A101", claim="AI demand is expanding fast.", factors=["AI Demand"], agent="news_agent"),
        _match("c2", "A103", claim="Datacenter capex is rising sharply.", factors=["AI CapEx"], agent="market_agent"),
        _match("c3", "A101", claim="AI demand is expanding fast.", factors=["AI Demand"], agent="sentiment_agent"),
    ]
    forward = build_evidence_groups(_matches_payload(records), run_id="run1", ticker="NVDA")
    backward = build_evidence_groups(_matches_payload(list(reversed(records))), run_id="run1", ticker="NVDA")

    def _summary(groups):
        return sorted((g.evidence_group_id, g.claim_ids, g.supported_alpha_ids) for g in groups)

    assert _summary(forward) == _summary(backward)


# ---------------------------------------------------------------------------
# 10. Primary/secondary stable tie-break
# ---------------------------------------------------------------------------


def test_primary_secondary_tie_break_is_stable_alpha_id_order():
    """Equal match score and equal matched-factor count -- the tie-break
    must be the alpha_id itself, deterministically, never dict/set
    iteration order."""
    records = [
        _match("c1", "A301", claim="Shared fact statement.", factors=["Revenue Growth"], score=0.7),
        _match("c2", "A103", claim="Shared fact statement.", factors=["Revenue Growth"], score=0.7),
    ]
    groups = build_evidence_groups(_matches_payload(records), run_id="run1", ticker="NVDA")
    assert len(groups) == 1
    assert groups[0].primary_alpha_id == "A103"  # "A103" < "A301" lexicographically
    assert groups[0].secondary_alpha_ids == ("A301",)


def test_primary_secondary_prefers_higher_match_score():
    records = [
        _match("c1", "A301", claim="Shared fact statement.", factors=["Revenue Growth"], score=0.9),
        _match("c2", "A103", claim="Shared fact statement.", factors=["Revenue Growth"], score=0.3),
    ]
    groups = build_evidence_groups(_matches_payload(records), run_id="run1", ticker="NVDA")
    assert groups[0].primary_alpha_id == "A301"


def test_primary_secondary_prefers_more_matched_factors_when_scores_tie():
    records = [
        _match("c1", "A301", claim="Shared fact statement.", factors=["Revenue Growth"], score=0.5),
        _match(
            "c2", "A103", claim="Shared fact statement.",
            factors=["AI CapEx", "Datacenter Demand"], score=0.5,
        ),
    ]
    groups = build_evidence_groups(_matches_payload(records), run_id="run1", ticker="NVDA")
    assert groups[0].primary_alpha_id == "A103"


# ---------------------------------------------------------------------------
# 11-12. Independent count and overlap ratio
# ---------------------------------------------------------------------------


def test_independent_evidence_group_count_and_overlap_ratio():
    records = [
        _match("c1", "A101", claim="AI demand is expanding fast.", factors=["AI Demand"]),
        _match("c2", "A101", claim="AI demand is expanding fast.", factors=["AI Demand"], agent="market_agent"),
        _match("c3", "A101", claim="Valuation looks stretched at current levels.", factors=["Valuation Risk"], score=0.4),
    ]
    groups = build_evidence_groups(_matches_payload(records), run_id="run1", ticker="NVDA")
    payload = build_alpha_evidence_integrity_payload(
        run_id="run1",
        ticker="NVDA",
        alpha_matches_payload=_matches_payload(records),
        activation_v2_alphas=[{"alpha_id": "A101", "status": "watch", "activation_score": 40.0}],
    )
    entry = next(a for a in payload["alphas"] if a["alpha_id"] == "A101")
    metrics = entry["metrics"]
    assert metrics["raw_evidence_claim_count"] == 3
    # c1/c2 merge (byte-identical text); c3 stays independent -> 2 groups.
    assert metrics["independent_evidence_group_count"] == 2
    assert metrics["overlap_ratio"] == round(1 - 2 / 3, 4)
    assert len(groups) == 2


def test_overlap_ratio_zero_when_all_evidence_independent():
    records = [
        _match("c1", "A101", claim="First independent fact.", factors=["AI Demand"]),
        _match("c2", "A101", claim="Second, unrelated fact entirely.", factors=["GPU Demand"]),
    ]
    payload = build_alpha_evidence_integrity_payload(
        run_id="run1",
        ticker="NVDA",
        alpha_matches_payload=_matches_payload(records),
        activation_v2_alphas=[{"alpha_id": "A101", "status": "watch", "activation_score": 30.0}],
    )
    entry = next(a for a in payload["alphas"] if a["alpha_id"] == "A101")
    assert entry["metrics"]["overlap_ratio"] == 0.0
    assert entry["metrics"]["raw_evidence_claim_count"] == 2
    assert entry["metrics"]["independent_evidence_group_count"] == 2


def test_raw_deduplicated_and_independent_counts_are_all_preserved():
    """The three tiers (raw, exact-duplicate-deduplicated, fully
    grouped/independent) must never collapse into one number."""
    records = [
        _match("c1", "A101", claim="Same exact text.", factors=["AI Demand"]),
        _match("c2", "A101", claim="Same exact text.", factors=["AI Demand"], agent="market_agent"),
        _match("c3", "A101", claim="Paraphrase of the same underlying story.", factors=["AI Demand"], agent="sentiment_agent"),
    ]
    payload = build_alpha_evidence_integrity_payload(
        run_id="run1",
        ticker="NVDA",
        alpha_matches_payload=_matches_payload(records),
        activation_v2_alphas=[{"alpha_id": "A101", "status": "watch", "activation_score": 30.0}],
    )
    metrics = next(a for a in payload["alphas"] if a["alpha_id"] == "A101")["metrics"]
    assert metrics["raw_evidence_claim_count"] == 3
    assert metrics["deduplicated_claim_count"] == 2  # c1/c2 exact-text dedup only
    assert metrics["independent_evidence_group_count"] == 1  # c1/c2/c3 all one factor-signature group


# ---------------------------------------------------------------------------
# 13. Production status/score never touched
# ---------------------------------------------------------------------------


def test_shadow_verdict_never_mutates_production_alpha_result():
    production_alpha = {
        "alpha_id": "A101",
        "status": "regime_level",
        "activation_score": 90.0,
        "distinct_supporting_agents": 5,
        "ticker_specific_evidence_count": 5,
        "local_edge_count": 3,
        "components": {"local_structure_support": {"raw": 80.0}},
        "evidence_integrity_warnings": [],
    }
    before = dict(production_alpha)
    evaluate_shadow_regime_verdict(
        alpha_id="A101",
        production_alpha_result=production_alpha,
        independent_evidence_group_count=1,
        primary_evidence_group_count=1,
        exposure_value=0.5,
    )
    assert production_alpha == before


def test_payload_reports_production_score_and_status_unchanged():
    records = [_match("c1", "A101", claim="AI demand is expanding.", factors=["AI Demand"])]
    production_alphas = [
        {"alpha_id": "A101", "status": "watch", "activation_score": 42.5},
    ]
    payload = build_alpha_evidence_integrity_payload(
        run_id="run1", ticker="NVDA",
        alpha_matches_payload=_matches_payload(records),
        activation_v2_alphas=production_alphas,
    )
    entry = next(a for a in payload["alphas"] if a["alpha_id"] == "A101")
    assert entry["production_score"] == 42.5
    assert entry["production_status"] == "watch"


# ---------------------------------------------------------------------------
# 14-15. Shadow regime verdict statuses
# ---------------------------------------------------------------------------


def test_not_regime_candidate_when_production_status_is_not_regime_level():
    verdict = evaluate_shadow_regime_verdict(
        alpha_id="A101",
        production_alpha_result={"alpha_id": "A101", "status": "dominant", "activation_score": 80.0},
        independent_evidence_group_count=10,
        primary_evidence_group_count=10,
        exposure_value=0.5,
    )
    assert verdict.regime_evidence_integrity_status == STATUS_NOT_REGIME_CANDIDATE
    assert verdict.shadow_regime_eligible is None
    assert verdict.production_regime_eligible is False


def test_missing_exposure_yields_unverified_exposure_never_assumed_zero_or_one():
    production_alpha = {
        "alpha_id": "A101",
        "status": "regime_level",
        "activation_score": 90.0,
        "distinct_supporting_agents": 5,
        "ticker_specific_evidence_count": 5,
        "local_edge_count": 3,
        "components": {"local_structure_support": {"raw": 80.0}},
        "evidence_integrity_warnings": [],
    }
    verdict = evaluate_shadow_regime_verdict(
        alpha_id="A101",
        production_alpha_result=production_alpha,
        independent_evidence_group_count=1,  # would fail the gate if evaluated
        primary_evidence_group_count=1,
        exposure_value=None,
    )
    assert verdict.regime_evidence_integrity_status == STATUS_UNVERIFIED_EXPOSURE
    assert verdict.shadow_regime_eligible is None


def test_production_regime_level_but_thin_independent_evidence_is_overlap_risk():
    """Production passed all 7 gates with its own (less-deduplicated)
    unique_evidence_count, but the shadow group count is below John's
    evidence threshold -- OVERLAP_RISK, and exactly the evidence-count gate
    is the one that fails (every other input is pinned to production's own
    already-passing value)."""
    production_alpha = {
        "alpha_id": "A101",
        "status": "regime_level",
        "activation_score": 90.0,
        "distinct_supporting_agents": 5,
        "ticker_specific_evidence_count": 5,
        "local_edge_count": 3,
        "components": {"local_structure_support": {"raw": 80.0}},
        "evidence_integrity_warnings": [],
    }
    verdict = evaluate_shadow_regime_verdict(
        alpha_id="A101",
        production_alpha_result=production_alpha,
        independent_evidence_group_count=2,  # John's threshold is 4
        primary_evidence_group_count=2,
        exposure_value=0.5,
    )
    assert verdict.regime_evidence_integrity_status == STATUS_OVERLAP_RISK
    assert verdict.shadow_regime_eligible is False
    assert "INSUFFICIENT_INDEPENDENT_EVIDENCE_FOR_REGIME" in verdict.shadow_regime_failures


def test_production_and_shadow_both_pass_is_consistent():
    production_alpha = {
        "alpha_id": "A101",
        "status": "regime_level",
        "activation_score": 90.0,
        "distinct_supporting_agents": 5,
        "ticker_specific_evidence_count": 5,
        "local_edge_count": 3,
        "components": {"local_structure_support": {"raw": 80.0}},
        "evidence_integrity_warnings": [],
    }
    verdict = evaluate_shadow_regime_verdict(
        alpha_id="A101",
        production_alpha_result=production_alpha,
        independent_evidence_group_count=5,
        primary_evidence_group_count=5,
        exposure_value=0.5,
    )
    assert verdict.regime_evidence_integrity_status == STATUS_CONSISTENT
    assert verdict.shadow_regime_eligible is True
    assert verdict.shadow_regime_failures == ()


def test_insufficient_primary_evidence_is_diagnostic_only_not_a_new_gate():
    """The alpha clears the group-count bar only via secondary-attributed
    groups -- INSUFFICIENT_PRIMARY_EVIDENCE is reported, but
    shadow_regime_eligible still reflects the numeric gate result (True):
    this status must never become a second, independent gate."""
    production_alpha = {
        "alpha_id": "A101",
        "status": "regime_level",
        "activation_score": 90.0,
        "distinct_supporting_agents": 5,
        "ticker_specific_evidence_count": 5,
        "local_edge_count": 3,
        "components": {"local_structure_support": {"raw": 80.0}},
        "evidence_integrity_warnings": [],
    }
    verdict = evaluate_shadow_regime_verdict(
        alpha_id="A101",
        production_alpha_result=production_alpha,
        independent_evidence_group_count=5,  # passes John's threshold (>=4)
        primary_evidence_group_count=1,  # but mostly via secondary attribution
        exposure_value=0.5,
    )
    assert verdict.regime_evidence_integrity_status == STATUS_INSUFFICIENT_PRIMARY_EVIDENCE
    assert verdict.shadow_regime_eligible is True


def test_evidence_integrity_warning_still_fails_shadow_gate():
    production_alpha = {
        "alpha_id": "A101",
        "status": "regime_level",
        "activation_score": 90.0,
        "distinct_supporting_agents": 5,
        "ticker_specific_evidence_count": 5,
        "local_edge_count": 3,
        "components": {"local_structure_support": {"raw": 80.0}},
        "evidence_integrity_warnings": ["NON_FINITE_OR_OUT_OF_RANGE_MATCH_SCORE"],
    }
    verdict = evaluate_shadow_regime_verdict(
        alpha_id="A101",
        production_alpha_result=production_alpha,
        independent_evidence_group_count=5,
        primary_evidence_group_count=5,
        exposure_value=0.5,
    )
    assert verdict.regime_evidence_integrity_status == STATUS_OVERLAP_RISK
    assert "EVIDENCE_INTEGRITY_WARNING" in verdict.shadow_regime_failures


# ---------------------------------------------------------------------------
# 16. SNDK positive edge preserved (real-data regression guard)
# ---------------------------------------------------------------------------


def test_sndk_positive_edge_claim_forms_a_grounded_single_alpha_group():
    """The SNDK claim sentiment_agent:sentiment_report:claim:49 (AI
    infrastructure demand driving NAND/storage demand) must still resolve
    to a relation-grounded evidence group attributing A103 as primary, and
    must not be deleted or merged away."""
    claim_id = "run1:sentiment_agent:sentiment_report:claim:49"
    records = [
        _match(
            claim_id,
            "A103",
            claim=(
                "AI infrastructure demand driving memory -- NAND flash and storage "
                "demand from AI data center buildout is the fundamental bull thesis."
            ),
            agent="sentiment_agent",
            factors=["AI Infrastructure", "Datacenter CapEx", "Semiconductor Cycle"],
            score=0.84,
        ),
    ]
    graph_edges = [
        _edge("ai_infrastructure", "semiconductor_cycle", claim_ids=[claim_id]),
    ]
    groups = build_evidence_groups(
        _matches_payload(records), run_id="run1", ticker="SNDK", graph_edges=graph_edges
    )
    assert len(groups) == 1
    group = groups[0]
    assert group.claim_ids == (claim_id,)
    assert group.supported_alpha_ids == ("A103",)
    assert group.primary_alpha_id == "A103"
    assert group.relation_signature == "ai_infrastructure>causal>semiconductor_cycle>asserted"


# ---------------------------------------------------------------------------
# Additional structural guards
# ---------------------------------------------------------------------------


def test_non_substantive_and_context_only_claims_never_enter_evidence_groups():
    records = [
        _match("c1", "A101", claim="AI demand is expanding.", factors=["AI Demand"], claim_quality="analytical"),
        _match("c2", "A101", claim="unknown", factors=[], claim_quality="non_substantive"),
        _match("c3", "A101", claim="The company operates three facilities.", factors=[], claim_quality="context_only"),
    ]
    groups = build_evidence_groups(_matches_payload(records), run_id="run1", ticker="NVDA")
    all_claim_ids = {cid for g in groups for cid in g.claim_ids}
    assert all_claim_ids == {"c1"}


def test_no_ticker_or_alpha_specific_hardcoding_in_source():
    source = inspect.getsource(evidence_integrity)
    for forbidden in ("SNDK", "NVDA", "AMD", "MU "):
        assert forbidden not in source


def test_module_performs_no_io_or_network():
    source = inspect.getsource(evidence_integrity)
    for forbidden in ("open(", "requests", "socket", "urllib", "sqlite3", "sqlalchemy"):
        assert forbidden not in source
