"""Activation v2 manual oracles and mutation tests.

Every expected numeric value below is an independent literal, hand-computed
directly from the frozen specification's own documented constants (weights
0.35/0.20/0.20/0.10/0.10/0.05, EvidenceQuality saturation 4.0,
LocalStructureSupport saturation 2.0, AgentIndependence denominators 3/2 and
shares 70%/30%, regime-gate thresholds). None of these literals are derived
by calling ``score_alpha_v2``/``score_alpha_activations_v2`` or by importing
the production module's weight/saturation constants -- a change to any of
those constants must make an oracle assertion fail, which the mutation
tests below verify directly.

All fixtures use a clearly synthetic ticker ("ACME") and synthetic agent
names -- no ticker-specific branching, no real-ticker hardcoding.
"""

from __future__ import annotations

import pytest

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.conflict_engine.conflict_detector import detect_alpha_conflicts
from comqutor_alpha.graph_engine import activation_scorer_v2
from comqutor_alpha.graph_engine.activation_scorer_v2 import score_alpha_v2

TAXONOMY = load_alpha_taxonomy()
AS_OF = "2026-06-30"
RUN_TS = "2026-06-30"


def _record(
    claim_id,
    agent,
    claim,
    *,
    alpha_id,
    match_score=1.0,
    relation="activation",
    assertion_status="asserted",
    factor_score=1.0,
    keyword_score=1.0,
    semantic_score=None,
    claim_quality="analytical",
    direction="positive",
):
    candidate = {
        "alpha_id": alpha_id,
        "relation": relation,
        "matched_keywords": ["demand"],
        "matched_factors": ["Revenue Growth"],
    }
    if semantic_score is not None:
        candidate["semantic_score"] = semantic_score
    return {
        "run_id": "oracle_run",
        "ticker": "ACME",
        "agent": agent,
        "claim_id": claim_id,
        "source_agent_output_id": f"{agent}:source",
        "claim": claim,
        "evidence": claim,
        "match_status": "matched",
        "matched_alpha": alpha_id,
        "score": match_score,
        "assertion_status": assertion_status,
        "semantic_polarity": "activation",
        "factor_score": factor_score,
        "keyword_score": keyword_score,
        "eligible_candidates": [candidate],
        # These oracles/mutation tests exercise the Activation v2 *formula*
        # in isolation (Unified Claim Admissibility Sprint's quality gate is
        # a separate, upstream concern), so every synthetic claim defaults
        # to an already-quality-gated "analytical" claim.
        "claim_quality": claim_quality,
        "direction": direction,
    }


def _edge(source, target, claim_ids, *, edge_type="causal", assertion_status="asserted"):
    return {
        "source": source,
        "target": target,
        "edge_type": edge_type,
        "assertion_status": assertion_status,
        "claim_ids": list(claim_ids),
    }


def _payload(*records):
    return {"run_id": "oracle_run", "ticker": "ACME", "matches": list(records)}


def _score(alpha_id, payload, *, graph_edges=()):
    return score_alpha_v2(
        alpha_id,
        payload,
        TAXONOMY,
        graph_edges=graph_edges,
        ticker="ACME",
        run_timestamp=RUN_TS,
        as_of=AS_OF,
    )


# ---------------------------------------------------------------------------
# Scenario A: high-quality, multi-agent, local-structure-backed evidence.
# ---------------------------------------------------------------------------
# 3 independent semantic groups (distinct claims), 3 distinct agents (no
# cross-agent overlap), 1 local causal edge linking two of the claims, all
# ticker-specific, all asserted/activation with match_score 1.0.
#
# EvidenceQuality: 3 groups x (1.0*1.0*1.0)=1.0 => sum=3.0
#   raw = min(100, 3.0/4.0*100) = 75.0        contribution = 75.0*0.35=26.25
# AgentIndependence: distinct_agents=3, coverage=min(3/3,1)*100=100
#   cross_agent_confirmed_groups=0 (no group has >=2 agents), confirmation=0
#   raw = 100*0.7 + 0*0.3 = 70.0               contribution = 70.0*0.20=14.0
# LocalStructureSupport: 1 asserted causal edge => contribution_sum=1.0
#   raw = min(100, 1.0/2.0*100) = 50.0          contribution = 50.0*0.20=10.0
# TickerSpecificity: 3/3 ticker-specific = 100  contribution = 100*0.10=10.0
# Recency: same-day => 100                     contribution = 100*0.10=10.0
# DirectionConsistency: all activation => avg=+1.0, raw=100
#                                                contribution = 100*0.05=5.0
# Uncapped = 26.25+14.0+10.0+10.0+10.0+5.0 = 75.25
# No caps trigger (unique=3>=2, agents=3>=2, ticker=3>0, local_edge=1>=1).
# Final = 75.25 -> band (70,85] = "dominant".


def _scenario_a_fixture():
    payload = _payload(
        _record(
            "a:claim:1",
            "analyst_one",
            "ACME datacenter revenue growth is accelerating on strong demand.",
            alpha_id="A101",
        ),
        _record(
            "a:claim:2",
            "analyst_two",
            "ACME's order backlog continues to expand this quarter.",
            alpha_id="A101",
        ),
        _record(
            "a:claim:3",
            "analyst_three",
            "ACME announced new supply agreements boosting output capacity.",
            alpha_id="A101",
        ),
    )
    edges = [_edge("factor_x", "factor_y", ["a:claim:1", "a:claim:2"])]
    return payload, edges


def test_scenario_a_high_quality_multi_agent_local_structure():
    """Also covers cap-contract test #10 (no eligible cap).

    Structure Integrity Repair Sprint, Track 2: EvidenceQuality/
    AgentIndependence now group evidence via the canonical Evidence Fact
    Index (shared with the Evidence Integrity shadow layer), which also
    merges two claims that back the exact same admitted structure-graph
    edge (priority 2 of the shared grouping algorithm -- see
    ``test_identical_relation_triple_does_merge`` in
    test_evidence_integrity.py for the validated, spec'd behavior this
    mirrors). This fixture's edge covers a:claim:1 and a:claim:2, so those
    two now form ONE Evidence Fact (2 groups total, not 3) -- a genuine,
    intentional behavior change, not a regression: two agents backing the
    identical graph relation are, by that edge's own definition, describing
    the same structural fact.
    """
    payload, edges = _scenario_a_fixture()
    result = _score("A101", payload, graph_edges=edges)

    eq = result["components"]["evidence_quality"]
    assert eq["unique_semantic_groups"] == 2
    assert eq["raw"] == pytest.approx(50.0, abs=0.01)
    assert eq["contribution"] == pytest.approx(17.5, abs=0.01)

    ai = result["components"]["agent_independence"]
    assert ai["raw"] == pytest.approx(85.0, abs=0.01)
    assert ai["contribution"] == pytest.approx(17.0, abs=0.01)
    assert ai["distinct_agents"] == 3
    assert ai["cross_agent_confirmed_groups"] == 1

    lss = result["components"]["local_structure_support"]
    assert lss["raw"] == pytest.approx(50.0, abs=0.01)
    assert lss["contribution"] == pytest.approx(10.0, abs=0.01)
    assert lss["local_edge_count"] == 1

    ts = result["components"]["ticker_specificity"]
    assert ts["contribution"] == pytest.approx(10.0, abs=0.01)

    assert result["uncapped_score"] == pytest.approx(69.5, abs=0.01)
    assert result["eligible_cap"] is None
    assert result["cap_was_binding"] is False
    assert result["cap_reason_codes"] == []
    assert result["binding_cap_reason_codes"] == []
    assert result["activation_score"] == pytest.approx(69.5, abs=0.01)
    assert result["status"] == "active"


# ---------------------------------------------------------------------------
# Scenario B: lots of evidence, but all the same semantic duplicate.
# ---------------------------------------------------------------------------
# 4 identical-text claims from 4 different agents (1 semantic group).
#
# EvidenceQuality: 1 group, best contribution=1.0 => sum=1.0 (NOT 4.0)
#   raw = min(100, 1.0/4.0*100) = 25.0          contribution = 25.0*0.35=8.75
# AgentIndependence: distinct_agents=4, coverage=min(4/3,1)*100=100
#   cross_agent_confirmed_groups=1 (the one group has 4 agents >=2)
#   confirmation = min(1/2,1)*100=50
#   raw = 100*0.7 + 50*0.3 = 85.0                contribution = 85.0*0.20=17.0
# LocalStructureSupport: no edges => raw=0       contribution = 0.0
# TickerSpecificity: 1/1 ticker-specific = 100   contribution = 100*0.10=10.0
# Recency: 100                                    contribution = 10.0
# DirectionConsistency: raw=100                   contribution = 5.0
# Uncapped = 8.75+17.0+0.0+10.0+10.0+5.0 = 50.75
# Caps: unique_evidence=1<2 -> INSUFFICIENT_UNIQUE_EVIDENCE (60);
#       local_edge_count=0 -> NO_LOCAL_STRUCTURE_SUPPORT (70).
# eligible_cap = min(60,70) = 60; uncapped(50.75) < 60 => cap_was_binding=False;
# activation_score = uncapped_score = 50.75; binding_cap_reason_codes=[].


def _scenario_b_fixture():
    text = "ACME cloud demand is broadly strong across the sector."
    payload = _payload(
        *(
            _record(f"b:claim:{i}", agent, text, alpha_id="A102")
            for i, agent in enumerate(("agent_a", "agent_b", "agent_c", "agent_d"), start=1)
        )
    )
    return payload


def test_scenario_b_duplicate_semantic_evidence_does_not_inflate_score():
    """Also covers cap-contract test #11 (eligible cap present, not binding)."""
    payload = _scenario_b_fixture()
    result = _score("A102", payload)

    eq = result["components"]["evidence_quality"]
    assert eq["unique_semantic_groups"] == 1
    assert eq["raw"] == pytest.approx(25.0, abs=0.01)  # not 100.0
    assert eq["contribution"] == pytest.approx(8.75, abs=0.01)

    ai = result["components"]["agent_independence"]
    assert ai["distinct_agents"] == 4
    assert ai["raw"] == pytest.approx(85.0, abs=0.01)

    assert result["uncapped_score"] == pytest.approx(50.75, abs=0.01)
    assert set(result["cap_reason_codes"]) == {
        "INSUFFICIENT_UNIQUE_EVIDENCE",
        "NO_LOCAL_STRUCTURE_SUPPORT",
    }
    assert result["eligible_cap"] == pytest.approx(60.0, abs=0.01)
    assert result["cap_was_binding"] is False
    assert result["binding_cap_reason_codes"] == []
    assert result["activation_score"] == pytest.approx(50.75, abs=0.01)


# ---------------------------------------------------------------------------
# Scenario C: the global graph has many edges, but none belong to this Alpha.
# ---------------------------------------------------------------------------
# 2 distinct groups, 2 distinct agents, ticker-specific, no local edge.
#
# EvidenceQuality: sum=2.0, raw=50.0             contribution=17.5
# AgentIndependence: coverage=min(2/3,1)*100=66.6667, cross=0
#   raw=66.6667*0.7=46.6667                      contribution=9.3333
# LocalStructureSupport: raw=0                    contribution=0.0
# TickerSpecificity: 2/2=100                      contribution=10.0
# Recency: 100                                    contribution=10.0
# DirectionConsistency: raw=100                   contribution=5.0
# Uncapped = 17.5+9.3333+0.0+10.0+10.0+5.0 = 51.8333
# Cap: local_edge_count=0 -> NO_LOCAL_STRUCTURE_SUPPORT (70); not binding.
#
# Adding graph edges whose claim_ids never intersect this Alpha's own
# qualifying claim_ids must not change any of the above.


def _scenario_c_fixture():
    payload = _payload(
        _record(
            "c:claim:1",
            "analyst_one",
            "ACME product demand remains resilient this quarter.",
            alpha_id="A103",
        ),
        _record(
            "c:claim:2",
            "analyst_two",
            "ACME supply chain constraints are easing steadily.",
            alpha_id="A103",
        ),
    )
    unrelated_edges = [
        _edge("other_factor_1", "other_factor_2", ["other:claim:1"]),
        _edge("other_factor_2", "other_factor_3", ["other:claim:2", "other:claim:3"]),
        _edge("other_factor_3", "other_factor_4", ["other:claim:4"]),
    ]
    return payload, unrelated_edges


def test_scenario_c_unrelated_global_edges_never_affect_local_alpha_score():
    payload, unrelated_edges = _scenario_c_fixture()

    result_no_edges = _score("A103", payload, graph_edges=())
    result_many_unrelated_edges = _score("A103", payload, graph_edges=unrelated_edges)

    for result in (result_no_edges, result_many_unrelated_edges):
        lss = result["components"]["local_structure_support"]
        assert lss["local_edge_count"] == 0
        assert lss["raw"] == pytest.approx(0.0, abs=0.01)
        assert "NO_LOCAL_STRUCTURE_SUPPORT" in result["cap_reason_codes"]
        assert result["uncapped_score"] == pytest.approx(51.8333, abs=0.01)
        assert result["activation_score"] == pytest.approx(51.8333, abs=0.01)
        assert result["cap_was_binding"] is False

    # Byte-for-byte identical regardless of how many unrelated edges exist.
    assert result_no_edges["activation_score"] == result_many_unrelated_edges["activation_score"]
    assert result_no_edges["components"] == result_many_unrelated_edges["components"]


# ---------------------------------------------------------------------------
# Scenario D: only one supporting agent.
# ---------------------------------------------------------------------------
# 3 distinct groups, all from a single agent, ticker-specific, 1 local edge.
#
# EvidenceQuality: sum=3.0, raw=75.0              contribution=26.25
# AgentIndependence: distinct_agents=1, coverage=min(1/3,1)*100=33.3333
#   cross=0 (only one agent exists, no group can have >=2 agents)
#   raw=33.3333*0.7=23.3333                       contribution=4.6667
# LocalStructureSupport: 1 asserted causal edge -> raw=50.0
#                                                  contribution=10.0
# TickerSpecificity: 3/3=100                       contribution=10.0
# Recency: 100                                     contribution=10.0
# DirectionConsistency: raw=100                     contribution=5.0
# Uncapped = 26.25+4.6667+10.0+10.0+10.0+5.0 = 65.9167
# Cap: distinct_agents=1<2 -> INSUFFICIENT_AGENT_INDEPENDENCE (70);
# uncapped(65.9167) < 70 => not binding; activation_score = uncapped.


def _scenario_d_fixture():
    payload = _payload(
        _record(
            "d:claim:1",
            "solo_agent",
            "ACME margin expansion continued for the third straight quarter.",
            alpha_id="A201",
        ),
        _record(
            "d:claim:2",
            "solo_agent",
            "ACME backlog conversion accelerated meaningfully in June.",
            alpha_id="A201",
        ),
        _record(
            "d:claim:3",
            "solo_agent",
            "ACME pricing power improved across every major product line.",
            alpha_id="A201",
        ),
    )
    edges = [_edge("factor_p", "factor_q", ["d:claim:1"])]
    return payload, edges


def test_scenario_d_single_agent_is_capped_on_agent_independence():
    payload, edges = _scenario_d_fixture()
    result = _score("A201", payload, graph_edges=edges)

    ai = result["components"]["agent_independence"]
    assert ai["distinct_agents"] == 1
    assert ai["raw"] == pytest.approx(23.3333, abs=0.01)
    assert ai["contribution"] == pytest.approx(4.6667, abs=0.01)

    assert result["uncapped_score"] == pytest.approx(65.9167, abs=0.01)
    assert result["cap_reason_codes"] == ["INSUFFICIENT_AGENT_INDEPENDENCE"]
    assert result["eligible_cap"] == pytest.approx(70.0, abs=0.01)
    # Cap does not bind numerically here -- final score equals uncapped.
    assert result["cap_was_binding"] is False
    assert result["binding_cap_reason_codes"] == []
    assert result["activation_score"] == pytest.approx(65.9167, abs=0.01)
    assert result["status"] == "active"


# ---------------------------------------------------------------------------
# Scenario E: no ticker-specific evidence.
# ---------------------------------------------------------------------------
# 2 distinct groups, 2 distinct agents, 1 local edge, but purely sector/macro
# language (no ticker/company mention).
#
# EvidenceQuality: sum=2.0, raw=50.0               contribution=17.5
# AgentIndependence: coverage=66.6667, cross=0, raw=46.6667
#                                                    contribution=9.3333
# LocalStructureSupport: 1 asserted causal edge, raw=50.0
#                                                    contribution=10.0
# TickerSpecificity: 0/2=0                          contribution=0.0
# Recency: 100                                      contribution=10.0
# DirectionConsistency: raw=100                      contribution=5.0
# Uncapped = 17.5+9.3333+10.0+0.0+10.0+5.0 = 51.8333
# Cap: ticker_specific_count=0 -> NO_TICKER_SPECIFIC_EVIDENCE (60); not binding.


def _scenario_e_fixture():
    payload = _payload(
        _record(
            "e:claim:1",
            "analyst_one",
            "Sector-wide semiconductor demand is broadly increasing amid macro tailwinds.",
            alpha_id="A301",
        ),
        _record(
            "e:claim:2",
            "analyst_two",
            "Industry-wide capacity utilization keeps climbing this cycle.",
            alpha_id="A301",
        ),
    )
    edges = [_edge("factor_m", "factor_n", ["e:claim:1"])]
    return payload, edges


def test_scenario_e_no_ticker_specific_evidence_is_capped():
    payload, edges = _scenario_e_fixture()
    result = _score("A301", payload, graph_edges=edges)

    ts = result["components"]["ticker_specificity"]
    assert ts["ticker_specific_evidence_count"] == 0
    assert ts["raw"] == pytest.approx(0.0, abs=0.01)

    assert result["uncapped_score"] == pytest.approx(51.8333, abs=0.01)
    assert result["cap_reason_codes"] == ["NO_TICKER_SPECIFIC_EVIDENCE"]
    assert result["eligible_cap"] == pytest.approx(60.0, abs=0.01)
    assert result["cap_was_binding"] is False
    assert result["binding_cap_reason_codes"] == []
    assert result["activation_score"] == pytest.approx(51.8333, abs=0.01)
    assert result["status"] == "active"


# ---------------------------------------------------------------------------
# Scenario F: score would exceed 86, but the regime gate is not satisfied
# (regime gate #4: ticker-specific evidence).
# ---------------------------------------------------------------------------
# 4 distinct groups, 3 distinct agents (2 groups cross-confirmed by 2 agents
# each), 2 local asserted causal edges, but only 1 of 4 groups is
# ticker-specific (gate requires >=2).
#
# EvidenceQuality: sum=4.0, raw=100.0               contribution=35.0 (max)
# AgentIndependence: coverage=100 (3/3), cross_agent_confirmed_groups=2,
#   confirmation=min(2/2,1)*100=100
#   raw=100*0.7+100*0.3=100                          contribution=20.0 (max)
# LocalStructureSupport: 2 asserted causal edges, sum=2.0, raw=100
#                                                     contribution=20.0 (max)
# TickerSpecificity: 1/4=25                          contribution=2.5
# Recency: 100                                       contribution=10.0
# DirectionConsistency: raw=100                       contribution=5.0
# Uncapped = 35.0+20.0+20.0+2.5+10.0+5.0 = 92.5
# No BASE cap triggers (unique=4>=2, agents=3>=2, ticker=1>0, local_edge=2>=1).
# Final = 92.5 -> band (85,100] = "regime_candidate" pre-gate.
# Regime gate: score>=86 OK; unique>=4 OK; agents>=3 OK;
#   ticker_specific>=2 FAILS (only 1); local_edge>=1 OK; LSS raw>=40 OK;
#   no integrity warnings OK.
# => regime_gate_passed=False (gate #4 alone), status resolves to "dominant"
#    (never silently "regime_level" -- covers test #26).


def _scenario_f_fixture():
    payload = _payload(
        _record("f:claim:1", "agent_x", "ACME AI infrastructure demand is expanding rapidly.", alpha_id="A601"),
        _record("f:claim:1b", "agent_y", "ACME AI infrastructure demand is expanding rapidly.", alpha_id="A601"),
        _record("f:claim:2", "agent_x", "Enterprise cloud spending continues to accelerate broadly.", alpha_id="A601"),
        _record("f:claim:2b", "agent_z", "Enterprise cloud spending continues to accelerate broadly.", alpha_id="A601"),
        _record("f:claim:3", "agent_y", "Datacenter buildout momentum remains firmly intact.", alpha_id="A601"),
        _record("f:claim:4", "agent_z", "Networking equipment orders keep trending upward industry-wide.", alpha_id="A601"),
    )
    edges = [
        _edge("factor_a", "factor_b", ["f:claim:1", "f:claim:1b"]),
        _edge("factor_b", "factor_c", ["f:claim:2", "f:claim:2b"]),
    ]
    return payload, edges


def test_scenario_f_high_score_but_regime_gate_fails_on_ticker_specificity():
    payload, edges = _scenario_f_fixture()
    result = _score("A601", payload, graph_edges=edges)

    assert result["components"]["evidence_quality"]["unique_semantic_groups"] == 4
    assert result["components"]["agent_independence"]["distinct_agents"] == 3
    assert result["components"]["local_structure_support"]["local_edge_count"] == 2
    assert result["components"]["ticker_specificity"]["ticker_specific_evidence_count"] == 1

    assert result["uncapped_score"] == pytest.approx(92.5, abs=0.01)
    assert result["eligible_cap"] is None  # no base cap triggers
    assert result["cap_was_binding"] is False
    assert result["activation_score"] == pytest.approx(92.5, abs=0.01)
    assert result["activation_score"] >= 86.0

    assert result["regime_gate_passed"] is False
    assert result["regime_gate_failures"] == ["INSUFFICIENT_TICKER_SPECIFIC_EVIDENCE_FOR_REGIME"]
    # A score in the regime band with a failed gate resolves to "dominant",
    # never silently to "regime_level".
    assert result["status"] == "dominant"


# ---------------------------------------------------------------------------
# Cap contract tests #12-15: eligible_cap / cap_was_binding / binding reasons.
# ---------------------------------------------------------------------------


def _cap_binding_single_fixture():
    """4 ticker-specific groups, 3 agents (no cross-confirm), zero local
    edges: only NO_LOCAL_STRUCTURE_SUPPORT (70) is eligible, and it binds.

    EQ: 4 groups -> raw=100 -> contribution=35.0
    AI: 3 agents, no cross-confirm -> raw=70 -> contribution=14.0
    LSS: 0 edges -> raw=0 -> contribution=0.0 (triggers the only cap)
    TS: 4/4 -> contribution=10.0
    Recency=10.0, Direction=5.0 (all activation)
    Uncapped = 35+14+0+10+10+5 = 74.0
    eligible_cap=70.0; 74.0>70 => binding; activation_score=70.0.
    """
    payload = _payload(
        _record("h:1", "agent_x", "ACME AI infrastructure demand accelerating broadly.", alpha_id="A101"),
        _record("h:2", "agent_y", "ACME cloud spend keeps rising this quarter.", alpha_id="A101"),
        _record("h:3", "agent_z", "ACME datacenter buildout momentum intact.", alpha_id="A101"),
        _record("h:4", "agent_x", "ACME networking orders trending upward broadly.", alpha_id="A101"),
    )
    return payload


def test_cap_contract_single_cap_binds():
    result = _score("A101", _cap_binding_single_fixture(), graph_edges=())
    assert result["uncapped_score"] == pytest.approx(74.0, abs=0.01)
    assert result["eligible_cap"] == pytest.approx(70.0, abs=0.01)
    assert result["cap_was_binding"] is True
    assert result["activation_score"] == pytest.approx(70.0, abs=0.01)
    assert result["cap_reason_codes"] == ["NO_LOCAL_STRUCTURE_SUPPORT"]
    assert result["binding_cap_reason_codes"] == ["NO_LOCAL_STRUCTURE_SUPPORT"]


def _cap_multiple_different_values_fixture():
    """4 groups, 3 agents (2 cross-confirmed, matching Scenario F's setup),
    zero ticker-specific evidence, zero local edges: two caps are eligible
    (NO_TICKER_SPECIFIC_EVIDENCE=60, NO_LOCAL_STRUCTURE_SUPPORT=70) and the
    *smaller* one (60) is the eligible_cap that binds.

    EQ=35.0 (max), AI=20.0 (max, 3 agents 2 cross-confirmed), LSS=0.0,
    TS=0.0 (no ticker mentions), Recency=10.0, Direction=5.0.
    Uncapped = 35+20+0+0+10+5 = 70.0
    eligible_cap=min(60,70)=60.0; 70.0>60 => binding; activation_score=60.0.
    binding_cap_reason_codes must contain ONLY the 60-value reason, never
    the 70-value one.
    """
    payload = _payload(
        _record("i:1", "agent_x", "AI infrastructure demand accelerating broadly across the sector.", alpha_id="A101"),
        _record("i:1b", "agent_y", "AI infrastructure demand accelerating broadly across the sector.", alpha_id="A101"),
        _record("i:2", "agent_x", "Cloud spend keeps rising this quarter industry-wide.", alpha_id="A101"),
        _record("i:2b", "agent_z", "Cloud spend keeps rising this quarter industry-wide.", alpha_id="A101"),
        _record("i:3", "agent_y", "Datacenter buildout momentum remains firmly intact.", alpha_id="A101"),
        _record("i:4", "agent_z", "Networking equipment orders keep trending upward broadly.", alpha_id="A101"),
    )
    return payload


def test_cap_contract_minimum_of_different_valued_caps_binds():
    result = _score("A101", _cap_multiple_different_values_fixture(), graph_edges=())
    assert result["uncapped_score"] == pytest.approx(70.0, abs=0.01)
    assert set(result["cap_reason_codes"]) == {
        "NO_TICKER_SPECIFIC_EVIDENCE",
        "NO_LOCAL_STRUCTURE_SUPPORT",
    }
    assert result["eligible_cap"] == pytest.approx(60.0, abs=0.01)
    assert result["cap_was_binding"] is True
    assert result["activation_score"] == pytest.approx(60.0, abs=0.01)
    # Only the 60-value cap's reason is binding -- the 70-value cap
    # (NO_LOCAL_STRUCTURE_SUPPORT) must never appear here.
    assert result["binding_cap_reason_codes"] == ["NO_TICKER_SPECIFIC_EVIDENCE"]


def _cap_tie_fixture():
    """1 semantic group (3 agents all repeating the same claim text), no
    ticker-specific evidence, 2 local edges (LSS maxed): two DIFFERENT
    caps -- INSUFFICIENT_UNIQUE_EVIDENCE and NO_TICKER_SPECIFIC_EVIDENCE --
    both happen to have the same value (60), a genuine tie.

    EQ: 1 group -> raw=25.0 -> contribution=8.75
    AI: 3 agents all on the one group -> coverage=100, cross_confirmed=1
      (only 1 group exists, so confirmation is capped at min(1/2,1)*100=50)
      raw=100*0.7+50*0.3=85.0 -> contribution=17.0
    LSS: 2 asserted causal edges -> raw=100 -> contribution=20.0
    TS: 0/1=0 -> contribution=0.0
    Recency=10.0, Direction=5.0 (all activation)
    Uncapped = 8.75+17.0+20.0+0+10.0+5.0 = 60.75
    eligible_cap=60.0 (both INSUFFICIENT_UNIQUE_EVIDENCE and
    NO_TICKER_SPECIFIC_EVIDENCE are exactly 60); 60.75>60 => binding;
    activation_score=60.0; binding_cap_reason_codes has BOTH reasons.
    """
    payload = _payload(
        _record("j:1", "agent_p", "Sector-wide product demand remains broadly resilient.", alpha_id="A101"),
        _record("j:2", "agent_q", "Sector-wide product demand remains broadly resilient.", alpha_id="A101"),
        _record("j:3", "agent_r", "Sector-wide product demand remains broadly resilient.", alpha_id="A101"),
    )
    edges = [
        _edge("factor_1", "factor_2", ["j:1"]),
        _edge("factor_2", "factor_3", ["j:2"]),
    ]
    return payload, edges


def test_cap_contract_tied_minimum_caps_both_reported_as_binding():
    payload, edges = _cap_tie_fixture()
    result = _score("A101", payload, graph_edges=edges)
    assert result["uncapped_score"] == pytest.approx(60.75, abs=0.01)
    assert set(result["cap_reason_codes"]) == {
        "INSUFFICIENT_UNIQUE_EVIDENCE",
        "NO_TICKER_SPECIFIC_EVIDENCE",
    }
    assert result["eligible_cap"] == pytest.approx(60.0, abs=0.01)
    assert result["cap_was_binding"] is True
    assert result["activation_score"] == pytest.approx(60.0, abs=0.01)
    assert result["binding_cap_reason_codes"] == [
        "INSUFFICIENT_UNIQUE_EVIDENCE",
        "NO_TICKER_SPECIFIC_EVIDENCE",
    ]


# ---------------------------------------------------------------------------
# Regime gate tests #17-26: the seven frozen gates.
# ---------------------------------------------------------------------------
# Shared "near-maximal" fixture family: 4 semantic groups (2 cross-confirmed
# by pairs of the same 3 agents), 2 local asserted-causal edges (LSS maxed),
# used as the baseline that each single-gate-failure variant perturbs along
# exactly one axis.


def _regime_all_pass_fixture():
    """All seven gates pass: score=95.0, unique=4, agents=3, ticker=2,
    local_edge=2, LSS raw=100, no integrity warnings."""
    payload = _payload(
        _record("k:g0:0", "agent_x", "ACME AI infrastructure demand accelerating broadly.", alpha_id="A101"),
        _record("k:g0:1", "agent_y", "ACME AI infrastructure demand accelerating broadly.", alpha_id="A101"),
        _record("k:g1:0", "agent_x", "ACME cloud spend keeps rising this quarter.", alpha_id="A101"),
        _record("k:g1:1", "agent_z", "ACME cloud spend keeps rising this quarter.", alpha_id="A101"),
        _record("k:g2:0", "agent_y", "Datacenter buildout momentum remains intact worldwide.", alpha_id="A101"),
        _record("k:g3:0", "agent_z", "Networking orders keep trending upward broadly.", alpha_id="A101"),
    )
    edges = [
        _edge("factor_1", "factor_2", ["k:g0:0"]),
        _edge("factor_2", "factor_3", ["k:g1:0"]),
    ]
    return payload, edges


def test_regime_gate_all_seven_pass():
    payload, edges = _regime_all_pass_fixture()
    result = _score("A101", payload, graph_edges=edges)
    assert result["uncapped_score"] == pytest.approx(95.0, abs=0.01)
    assert result["activation_score"] == pytest.approx(95.0, abs=0.01)
    assert result["components"]["evidence_quality"]["unique_semantic_groups"] == 4
    assert result["components"]["agent_independence"]["distinct_agents"] == 3
    assert result["components"]["ticker_specificity"]["ticker_specific_evidence_count"] == 2
    assert result["components"]["local_structure_support"]["local_edge_count"] == 2
    assert result["components"]["local_structure_support"]["raw"] == pytest.approx(100.0, abs=0.01)
    assert result["evidence_integrity_warnings"] == []
    assert result["regime_gate_passed"] is True
    assert result["regime_gate_failures"] == []
    assert result["status"] == "regime_level"


def test_regime_gate_1_score_below_threshold_fails_alone():
    """Same structure as the all-pass fixture, but every match_score scaled
    to 0.73 (uniform, so DirectionConsistency's *signed average* is
    unaffected -- only EvidenceQuality's magnitude drops):
    EQ sum=4*0.73=2.92, raw=73.0, contribution=25.55.
    Total = 25.55+20.0+20.0+5.0+10.0+5.0 = 85.55 -- in (85,86), so it
    reaches the regime_candidate band but fails gate #1 alone."""
    payload, edges = _regime_all_pass_fixture()
    for record in payload["matches"]:
        record["score"] = 0.73
    result = _score("A101", payload, graph_edges=edges)
    assert result["uncapped_score"] == pytest.approx(85.55, abs=0.01)
    assert 85.0 < result["uncapped_score"] < 86.0
    assert result["regime_gate_passed"] is False
    assert result["regime_gate_failures"] == ["SCORE_BELOW_REGIME_THRESHOLD"]
    assert result["status"] == "dominant"


def test_regime_gate_2_insufficient_unique_evidence_fails_alone():
    """Only 3 semantic groups (one fewer than the all-pass fixture), still
    2 ticker-specific, 3 agents (2 cross-confirmed), 2 local edges.
    Uncapped = 26.25(EQ,3 groups)+20.0(AI)+20.0(LSS)+6.6667(TS,2/3)+10.0+5.0
             = 87.9167 -- passes gate #1, fails only gate #2."""
    payload = _payload(
        _record("l:g0:0", "agent_x", "ACME AI infrastructure demand accelerating broadly.", alpha_id="A101"),
        _record("l:g0:1", "agent_y", "ACME AI infrastructure demand accelerating broadly.", alpha_id="A101"),
        _record("l:g1:0", "agent_x", "ACME cloud spend keeps rising this quarter.", alpha_id="A101"),
        _record("l:g1:1", "agent_z", "ACME cloud spend keeps rising this quarter.", alpha_id="A101"),
        _record("l:g2:0", "agent_y", "Datacenter buildout momentum remains intact worldwide.", alpha_id="A101"),
    )
    edges = [
        _edge("factor_1", "factor_2", ["l:g0:0"]),
        _edge("factor_2", "factor_3", ["l:g1:0"]),
    ]
    result = _score("A101", payload, graph_edges=edges)
    assert result["components"]["evidence_quality"]["unique_semantic_groups"] == 3
    assert result["uncapped_score"] == pytest.approx(87.9167, abs=0.01)
    assert result["regime_gate_passed"] is False
    assert result["regime_gate_failures"] == ["INSUFFICIENT_UNIQUE_EVIDENCE_FOR_REGIME"]


def test_regime_gate_3_insufficient_supporting_agents_fails_alone():
    """Only 2 distinct agents (both cross-confirming both of the first two
    groups), 4 groups total, 2 ticker-specific, 2 local edges.
    AI: coverage=min(2/3,1)*100=66.6667, cross_confirmed_groups=2,
        confirmation=100 -> raw=66.6667*0.7+100*0.3=76.6667 -> contrib=15.3333
    Uncapped = 35.0(EQ)+15.3333(AI)+20.0(LSS)+5.0(TS,2/4)+10.0+5.0 = 90.3333
    -- passes gates 1/2/4/5/6/7, fails only gate #3."""
    payload = _payload(
        _record("m:g0:0", "agent_x", "ACME AI infrastructure demand accelerating broadly.", alpha_id="A101"),
        _record("m:g0:1", "agent_y", "ACME AI infrastructure demand accelerating broadly.", alpha_id="A101"),
        _record("m:g1:0", "agent_x", "ACME cloud spend keeps rising this quarter.", alpha_id="A101"),
        _record("m:g1:1", "agent_y", "ACME cloud spend keeps rising this quarter.", alpha_id="A101"),
        _record("m:g2:0", "agent_y", "Datacenter buildout momentum remains intact worldwide.", alpha_id="A101"),
        _record("m:g3:0", "agent_x", "Networking orders keep trending upward broadly.", alpha_id="A101"),
    )
    edges = [
        _edge("factor_1", "factor_2", ["m:g0:0"]),
        _edge("factor_2", "factor_3", ["m:g1:0"]),
    ]
    result = _score("A101", payload, graph_edges=edges)
    assert result["components"]["agent_independence"]["distinct_agents"] == 2
    assert result["uncapped_score"] == pytest.approx(90.3333, abs=0.01)
    assert result["regime_gate_passed"] is False
    assert result["regime_gate_failures"] == ["INSUFFICIENT_SUPPORTING_AGENTS_FOR_REGIME"]


def test_regime_gate_4_insufficient_ticker_specific_evidence_fails_alone():
    """Scenario F is exactly this case: score=92.5, only gate #4 fails."""
    payload, edges = _scenario_f_fixture()
    result = _score("A601", payload, graph_edges=edges)
    assert result["regime_gate_passed"] is False
    assert result["regime_gate_failures"] == ["INSUFFICIENT_TICKER_SPECIFIC_EVIDENCE_FOR_REGIME"]


def test_regime_gate_5_no_local_structure_is_structurally_unreachable_via_the_scorer():
    """Gate #5 (local_edge_count >= 1) can never be observed as the SOLE
    regime-gate failure via the real scorer: with zero local edges,
    LocalStructureSupport's raw score is necessarily 0 (< 40), so gate #6
    always fails alongside it. More fundamentally, the *base* score cap
    NO_LOCAL_STRUCTURE_SUPPORT (70.0) always caps activation_score at or
    below 70 whenever local_edge_count is 0 -- strictly below the regime
    gate's own 86.0 threshold -- so the regime gate is never even reached
    with legitimate evidence. This is proven directly (not asserted from a
    hardcoded belief): every component maxed except LocalStructureSupport
    yields an uncapped ceiling of exactly 80.0, and the base cap still
    drives the *final* score down to 70.0.

    Gate #5's own check is still verified directly against
    ``_evaluate_regime_gate`` in the next test (a legitimate unit-level
    seam, not a workaround) since it cannot be exercised end-to-end.
    """
    payload = _payload(
        _record("n:g0:0", "agent_x", "ACME AI infrastructure demand accelerating broadly.", alpha_id="A101"),
        _record("n:g0:1", "agent_y", "ACME AI infrastructure demand accelerating broadly.", alpha_id="A101"),
        _record("n:g1:0", "agent_x", "ACME cloud spend keeps rising this quarter.", alpha_id="A101"),
        _record("n:g1:1", "agent_z", "ACME cloud spend keeps rising this quarter.", alpha_id="A101"),
        _record("n:g2:0", "agent_y", "ACME datacenter buildout momentum remains intact.", alpha_id="A101"),
        _record("n:g3:0", "agent_z", "ACME networking orders keep trending upward broadly.", alpha_id="A101"),
    )
    result = _score("A101", payload, graph_edges=())
    assert result["components"]["local_structure_support"]["local_edge_count"] == 0
    assert result["uncapped_score"] == pytest.approx(80.0, abs=0.01)
    assert result["eligible_cap"] == pytest.approx(70.0, abs=0.01)
    assert result["cap_was_binding"] is True
    assert result["activation_score"] == pytest.approx(70.0, abs=0.01)
    # The base cap keeps this alpha at or below "active"/"dominant" --
    # never even reaching the regime_candidate band, so the regime gate
    # (and gate #5's reason code) is never evaluated at all here.
    assert result["status"] in ("dominant", "active")
    assert result["regime_gate_passed"] is False
    assert result["regime_gate_failures"] == []


def test_regime_gate_5_reason_code_directly_via_evaluate_regime_gate():
    """Unit-level seam test: calls the private gate evaluator directly to
    verify gate #5's own check and reason code, since (per the previous
    test) it is unreachable through score_alpha_v2 given the current
    weights. Also exercises test #25 (multiple simultaneous failures, fixed
    order) -- with local_structure_raw forced to 0, gate #6 necessarily
    fails alongside gate #5, and both reason codes must appear in the fixed
    declared order (gate #5 before gate #6)."""
    passed, failures = activation_scorer_v2._evaluate_regime_gate(
        activation_score=90.0,
        unique_evidence_count=5,
        distinct_agents=4,
        ticker_specific_count=3,
        local_edge_count=0,
        local_structure_raw=0.0,
        integrity_warnings=(),
    )
    assert passed is False
    assert failures == [
        "NO_LOCAL_STRUCTURE_FOR_REGIME",
        "INSUFFICIENT_LOCAL_STRUCTURE_STRENGTH_FOR_REGIME",
    ]


def test_regime_gate_6_insufficient_local_structure_strength_fails_alone():
    """4 groups (all ticker-specific), 3 agents (2 cross-confirmed), but the
    two local edges are weak (one conditional-causal=0.50, one
    causal-mixed=0.25): contribution_sum=0.75, raw=37.5 (< 40), while
    local_edge_count=2 (>=1, gate #5 passes).
    Uncapped = 35.0(EQ)+20.0(AI)+7.5(LSS,raw37.5*0.2)+10.0(TS,4/4)+10.0+5.0
             = 87.5 -- passes every gate except #6."""
    payload = _payload(
        _record("o:g0:0", "agent_x", "ACME AI infrastructure demand accelerating broadly.", alpha_id="A101"),
        _record("o:g0:1", "agent_y", "ACME AI infrastructure demand accelerating broadly.", alpha_id="A101"),
        _record("o:g1:0", "agent_x", "ACME cloud spend keeps rising this quarter.", alpha_id="A101"),
        _record("o:g1:1", "agent_z", "ACME cloud spend keeps rising this quarter.", alpha_id="A101"),
        _record("o:g2:0", "agent_y", "ACME datacenter buildout momentum remains intact.", alpha_id="A101"),
        _record("o:g3:0", "agent_z", "ACME networking orders keep trending upward broadly.", alpha_id="A101"),
    )
    edges = [
        _edge("factor_1", "factor_2", ["o:g0:0"], assertion_status="conditional"),
        _edge("factor_2", "factor_3", ["o:g1:0"], assertion_status="mixed"),
    ]
    result = _score("A101", payload, graph_edges=edges)
    assert result["components"]["local_structure_support"]["local_edge_count"] == 2
    assert result["components"]["local_structure_support"]["raw"] == pytest.approx(37.5, abs=0.01)
    assert result["uncapped_score"] == pytest.approx(87.5, abs=0.01)
    assert result["regime_gate_passed"] is False
    assert result["regime_gate_failures"] == ["INSUFFICIENT_LOCAL_STRUCTURE_STRENGTH_FOR_REGIME"]


def test_regime_gate_7_evidence_integrity_warning_fails_alone():
    """All-pass fixture plus one extra record with an out-of-range match
    score (1.5): that record is excluded from qualifying evidence entirely
    (so every other component is untouched, score stays 95.0) but adds an
    integrity warning, failing gate #7 alone."""
    payload, edges = _regime_all_pass_fixture()
    payload["matches"].append(
        _record(
            "k:bad",
            "agent_w",
            "ACME something else happened entirely.",
            alpha_id="A101",
            match_score=1.5,
        )
    )
    result = _score("A101", payload, graph_edges=edges)
    assert result["uncapped_score"] == pytest.approx(95.0, abs=0.01)
    assert result["evidence_integrity_warnings"] == ["NON_FINITE_OR_OUT_OF_RANGE_MATCH_SCORE"]
    assert result["regime_gate_passed"] is False
    assert result["regime_gate_failures"] == ["EVIDENCE_INTEGRITY_WARNING"]
    assert result["status"] == "dominant"


def test_regime_gate_failure_order_is_fixed_not_dict_iteration():
    """Direct unit test (test #25): every gate failing simultaneously must
    be reported in the fixed declared order (1-7), regardless of the order
    parameters are supplied in, and reproducibly across repeated calls."""
    kwargs = {
        "activation_score": 10.0,
        "unique_evidence_count": 0,
        "distinct_agents": 0,
        "ticker_specific_count": 0,
        "local_edge_count": 0,
        "local_structure_raw": 0.0,
        "integrity_warnings": ("SOME_WARNING",),
    }
    expected = [
        "SCORE_BELOW_REGIME_THRESHOLD",
        "INSUFFICIENT_UNIQUE_EVIDENCE_FOR_REGIME",
        "INSUFFICIENT_SUPPORTING_AGENTS_FOR_REGIME",
        "INSUFFICIENT_TICKER_SPECIFIC_EVIDENCE_FOR_REGIME",
        "NO_LOCAL_STRUCTURE_FOR_REGIME",
        "INSUFFICIENT_LOCAL_STRUCTURE_STRENGTH_FOR_REGIME",
        "EVIDENCE_INTEGRITY_WARNING",
    ]
    for _ in range(5):
        passed, failures = activation_scorer_v2._evaluate_regime_gate(**kwargs)
        assert passed is False
        assert failures == expected


# ===========================================================================
# Mutation tests: each proves a passing oracle above would fail if the named
# piece of production logic were broken.
# ===========================================================================


def test_mutation_evidence_quality_saturation_change_breaks_oracle(monkeypatch):
    monkeypatch.setattr(activation_scorer_v2, "EVIDENCE_QUALITY_SATURATION", 2.0)
    payload, edges = _scenario_a_fixture()
    result = _score("A101", payload, graph_edges=edges)
    with pytest.raises(AssertionError):
        assert result["components"]["evidence_quality"]["raw"] == pytest.approx(75.0, abs=0.01)


def test_mutation_local_structure_using_global_edges_breaks_oracle(monkeypatch):
    original = activation_scorer_v2._local_structure_component

    def _all_edges_count(qualifying, graph_edges, alpha_id):
        # Deliberately ignores claim_id intersection -- every global edge
        # counts toward this alpha's local_edge_count, not just its own.
        raw, meta = original(qualifying, graph_edges, alpha_id)
        meta = dict(meta)
        meta["local_edge_count"] = len(list(graph_edges))
        return raw, meta

    monkeypatch.setattr(activation_scorer_v2, "_local_structure_component", _all_edges_count)
    payload, unrelated_edges = _scenario_c_fixture()
    result = _score("A103", payload, graph_edges=unrelated_edges)
    with pytest.raises(AssertionError):
        assert result["components"]["local_structure_support"]["local_edge_count"] == 0


def test_mutation_semantic_group_double_counting_breaks_oracle(monkeypatch):
    # Disable Evidence Fact Index grouping (Structure Integrity Repair
    # Sprint, Track 2): every claim_id becomes its own singleton group, so
    # the 4 duplicate claims in Scenario B are no longer deduplicated --
    # this reproduces the exact production/shadow "double truth" defect the
    # sprint fixed (production counting near-paraphrases as independent
    # facts).
    monkeypatch.setattr(
        activation_scorer_v2,
        "group_evidence_candidates",
        lambda candidates, ticker="": [[c] for c in candidates],
    )
    payload = _scenario_b_fixture()
    result = _score("A102", payload)
    with pytest.raises(AssertionError):
        assert result["components"]["evidence_quality"]["raw"] == pytest.approx(25.0, abs=0.01)


def test_mutation_agent_denominator_change_breaks_oracle(monkeypatch):
    # Scenario A's 3 agents already saturate both denominator=3 and a
    # smaller denominator at the min(...,1.0) ceiling, so it cannot detect
    # this mutation. Scenario D's single agent does not saturate either
    # value, so denominator=2 measurably changes its coverage (and this is
    # exactly the "taxonomy expected_agents used as too-small a denominator"
    # regression the frozen spec forbids).
    monkeypatch.setattr(activation_scorer_v2, "AGENT_COVERAGE_DENOMINATOR", 2)
    payload, edges = _scenario_d_fixture()
    result = _score("A201", payload, graph_edges=edges)
    with pytest.raises(AssertionError):
        assert result["components"]["agent_independence"]["raw"] == pytest.approx(23.3333, abs=0.01)


def test_mutation_disabling_score_caps_breaks_oracle(monkeypatch):
    monkeypatch.setattr(
        activation_scorer_v2,
        "_apply_caps",
        lambda uncapped_score, **kwargs: (uncapped_score, None, False, [], []),
    )
    payload = _scenario_b_fixture()
    result = _score("A102", payload)
    with pytest.raises(AssertionError):
        assert result["eligible_cap"] == pytest.approx(60.0, abs=0.01)


def test_mutation_disabling_regime_gate_breaks_oracle(monkeypatch):
    monkeypatch.setattr(
        activation_scorer_v2,
        "_evaluate_regime_gate",
        lambda **kwargs: (True, []),
    )
    payload, edges = _scenario_f_fixture()
    result = _score("A601", payload, graph_edges=edges)
    with pytest.raises(AssertionError):
        assert result["regime_gate_passed"] is False


def test_mutation_unrelated_edge_changing_score_breaks_oracle(monkeypatch):
    # Force every edge's claim set to appear to intersect this alpha's own
    # qualifying claims -- reproduces "global structure leaks into a
    # per-alpha score" exactly, so an unrelated edge now changes the score.
    original = activation_scorer_v2._local_structure_component

    def _leak_all_edges(qualifying, graph_edges, alpha_id):
        alpha_claim_ids = [item["claim_id"] for item in qualifying]
        patched_edges = [
            {**edge, "claim_ids": list(edge.get("claim_ids") or []) + alpha_claim_ids[:1]}
            for edge in graph_edges
        ]
        return original(qualifying, patched_edges, alpha_id)

    monkeypatch.setattr(activation_scorer_v2, "_local_structure_component", _leak_all_edges)

    payload, unrelated_edges = _scenario_c_fixture()
    result_no_edges = _score("A103", payload, graph_edges=())
    result_many_unrelated_edges = _score("A103", payload, graph_edges=unrelated_edges)
    with pytest.raises(AssertionError):
        assert (
            result_no_edges["activation_score"] == result_many_unrelated_edges["activation_score"]
        )


def test_mutation_conflict_formula_min_to_max_still_fails_existing_tests():
    """The Conflict Score formula (min(activation_a, activation_b) x
    contradiction_weight x evidence_strength) must stay unchanged. Proves an
    attempted min->max substitution breaks conflict_detector's own
    formula-level behavior: the conflict score would then key off whichever
    alpha scores *higher*, not lower."""
    activation_payload = {
        "formula_version": activation_scorer_v2.ACTIVATION_V2_FORMULA_VERSION,
        "alphas": [
            {
                "alpha_id": "A101",
                "alpha_name": "A101",
                "activation_score": 90.0,
                "status": "regime_level",
                "direction": "positive",
                "components": {},
                "evidence_count": 1,
                "distinct_supporting_agents": 1,
                "claim_ids": ["c1"],
                "evidence": ["e1"],
                "reason_codes": [],
            },
            {
                "alpha_id": "A304",
                "alpha_name": "A304",
                # B2's own score threshold is 50.0 -- 55.0 keeps this
                # clearly the LOWER of the two scores (preserving the
                # min()-vs-max() distinction this test proves) while also
                # clearing B2 admission.
                "activation_score": 55.0,
                "status": "watch",
                "direction": "negative",
                "components": {},
                "evidence_count": 1,
                "distinct_supporting_agents": 1,
                "claim_ids": ["c2"],
                "evidence": ["e2"],
                "reason_codes": [],
            },
        ],
    }
    # John's B2 Conflict Evidence Admissibility gate: each side needs >=2
    # unique, ticker-specific, supports_alpha Evidence Facts to be admitted
    # at all -- c1b/c2b are additional, genuinely distinct claims added
    # purely to clear that bar (their own activation_score above is
    # hand-fixed at 90.0/40.0 regardless of claim count, so this does not
    # touch the min()-vs-max() formula behavior this test actually proves).
    alpha_matches = [
        {
            "claim_id": "c1",
            "agent": "agent_one",
            "claim": "ACME AI expansion evidence.",
            "evidence": "ACME AI expansion evidence.",
            "match_status": "matched",
            "matched_alpha": "A101",
            "score": 0.9,
            "assertion_status": "asserted",
            "eligible_candidates": [
                {"alpha_id": "A101", "relation": "activation", "evidence_stance": "supports_alpha"}
            ],
            "claim_quality": "analytical",
            "direction": "positive",
        },
        {
            "claim_id": "c1b",
            "agent": "agent_three",
            "claim": "ACME datacenter demand is accelerating.",
            "evidence": "ACME datacenter demand is accelerating.",
            "match_status": "matched",
            "matched_alpha": "A101",
            "score": 0.9,
            "assertion_status": "asserted",
            "eligible_candidates": [
                {"alpha_id": "A101", "relation": "activation", "evidence_stance": "supports_alpha"}
            ],
            "claim_quality": "analytical",
            "direction": "positive",
        },
        {
            "claim_id": "c2",
            "agent": "agent_two",
            "claim": "ACME multiple compression evidence.",
            "evidence": "ACME multiple compression evidence.",
            "match_status": "matched",
            "matched_alpha": "A304",
            "score": 0.9,
            "assertion_status": "asserted",
            "eligible_candidates": [
                {"alpha_id": "A304", "relation": "activation", "evidence_stance": "supports_alpha"}
            ],
            "claim_quality": "analytical",
            "direction": "negative",
        },
        {
            "claim_id": "c2b",
            "agent": "agent_four",
            "claim": "ACME margin compression was flagged by analysts.",
            "evidence": "ACME margin compression was flagged by analysts.",
            "match_status": "matched",
            "matched_alpha": "A304",
            "score": 0.9,
            "assertion_status": "asserted",
            "eligible_candidates": [
                {"alpha_id": "A304", "relation": "activation", "evidence_stance": "supports_alpha"}
            ],
            "claim_quality": "analytical",
            "direction": "negative",
        },
    ]
    result = detect_alpha_conflicts(
        run_id="min_max_run",
        ticker="ACME",
        activation_payload=activation_payload,
        alpha_matches=alpha_matches,
    )
    conflict = next((c for c in result["conflicts"] if c["conflict_id"] == "A101__A304"), None)
    assert conflict is not None
    # Correct min() formula: minimum_activation must be 55.0 (the lower of
    # the two), never 90.0.
    assert conflict["components"]["minimum_activation"] == 55.0

    # Simulate the forbidden min->max substitution directly (not by
    # monkeypatching the builtin, which conflict_detector does not expose
    # as an overridable seam) and prove it disagrees with the real result --
    # i.e. an existing correctness assertion on the real formula would fail
    # under a min->max change.
    simulated_max_variant_minimum_activation = max(90.0, 55.0)
    with pytest.raises(AssertionError):
        assert conflict["components"]["minimum_activation"] == simulated_max_variant_minimum_activation


# ---------------------------------------------------------------------------
# Unified Claim Admissibility and Context-Only Routing Sprint
# ---------------------------------------------------------------------------


def test_context_only_claim_contributes_no_activation_evidence():
    """Spec test #2: a context_only claim -- even one fully matched to an
    alpha with an 'activation' relation -- must not count as Activation
    evidence."""
    record = _record(
        "c1", "agent_x", "The company reported quarterly revenue of $2.3 billion.", alpha_id="A101"
    )
    record["claim_quality"] = "context_only"
    payload = _payload(record)

    result = _score("A101", payload)

    assert result["unique_evidence_count"] == 0
    assert result["activation_score"] == 0.0
    assert result["cap_reason_codes"] == ["NO_QUALIFYING_EVIDENCE"]


def test_analytical_claim_with_the_same_relation_does_contribute():
    """Control: the identical record shape, tagged analytical instead,
    behaves exactly as it always did -- proving the exclusion above is
    caused by claim_quality, not by some other change."""
    record = _record(
        "c1", "agent_x", "The company reported quarterly revenue of $2.3 billion.", alpha_id="A101"
    )
    record["claim_quality"] = "analytical"
    payload = _payload(record)

    result = _score("A101", payload)

    assert result["unique_evidence_count"] == 1
    assert result["activation_score"] > 0.0
