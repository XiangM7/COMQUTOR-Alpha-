from __future__ import annotations

from datetime import date
from uuid import UUID, uuid5

import pytest

from comqutor_alpha.alpha_library import load_taxonomy
from comqutor_alpha.structure_engine.activation_scorer import (
    ActivationScorer,
    activation_status,
)
from comqutor_alpha.structure_engine.structure_schema import (
    ActivationStatus,
    AgentType,
    AlphaMatch,
    Claim,
    Direction,
    MatchComponentBreakdown,
    MatchMethod,
    NodeType,
    SourceType,
    StructureGraph,
    StructureNode,
)

RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
NAMESPACE = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0, ActivationStatus.INACTIVE),
        (30, ActivationStatus.INACTIVE),
        (30.1, ActivationStatus.WATCH),
        (31, ActivationStatus.WATCH),
        (50, ActivationStatus.WATCH),
        (50.1, ActivationStatus.ACTIVE),
        (51, ActivationStatus.ACTIVE),
        (70, ActivationStatus.ACTIVE),
        (70.1, ActivationStatus.DOMINANT),
        (85, ActivationStatus.DOMINANT),
        (85.1, ActivationStatus.REGIME_LEVEL),
        (100, ActivationStatus.REGIME_LEVEL),
    ],
)
def test_decimal_safe_activation_boundaries(score, expected) -> None:
    assert activation_status(score) == expected


def _claim(alpha_id: str, score: float, agent: AgentType, evidence: str, direction="positive"):
    claim_id = uuid5(NAMESPACE, f"{alpha_id}|{score}|{agent.value}|{evidence}")
    claim = Claim(
        claim_id=claim_id,
        run_id=RUN_ID,
        ticker="NVDA",
        agent=agent,
        claim=f"Evidence for {alpha_id}",
        evidence=evidence,
        entities=["NVDA"],
        factors=[alpha_id],
        direction=Direction(direction),
        confidence=score,
        source_type=SourceType.ANALYST,
        source_refs=[f"fixture:{claim_id}"],
        extraction_method="fixture",
    )
    match = AlphaMatch(
        match_id=uuid5(NAMESPACE, f"match|{claim_id}"),
        claim_id=claim_id,
        evidence_reference=f"claim:{claim_id}",
        alpha_id=alpha_id,
        direction=Direction(direction),
        match_score=score,
        method=MatchMethod.KEYWORD_FACTOR,
        components=MatchComponentBreakdown(
            keyword_score=score,
            factor_score=score,
            combined_score=score,
        ),
    )
    return claim, match


def _graph(alpha_ids):
    nodes = [
        StructureNode(
            node_id=f"node-{alpha_id.lower()}",
            canonical_label=f"node {alpha_id}",
            original_labels=[f"Node {alpha_id}"],
            node_type=NodeType.FACTOR,
            alpha_ids=[alpha_id],
            claim_ids=[uuid5(NAMESPACE, f"graph|{alpha_id}")],
            evidence_references=[f"graph:{alpha_id}"],
            agents=[AgentType.NEWS],
        )
        for alpha_id in alpha_ids
    ]
    return StructureGraph(
        run_id=RUN_ID,
        ticker="NVDA",
        nodes=nodes,
        edges=[],
        graph_coherence_score=80,
    )


@pytest.mark.unit
def test_nvda_relevant_alphas_have_differentiated_deterministic_scores() -> None:
    specs = [
        ("A101", 0.95, AgentType.NEWS),
        ("A103", 0.82, AgentType.FUNDAMENTALS),
        ("A201", 0.76, AgentType.MARKET),
        ("A301", 0.88, AgentType.FUNDAMENTALS),
        ("A304", 0.70, AgentType.MARKET),
        ("A601", 0.80, AgentType.SENTIMENT),
    ]
    pairs = [
        _claim(alpha_id, confidence, agent, f"Independent evidence {alpha_id}")
        for alpha_id, confidence, agent in specs
    ]
    claims = {claim.claim_id: claim for claim, _match in pairs}
    matches = [match for _claim_value, match in pairs]
    scorer = ActivationScorer()
    kwargs = {
        "taxonomy": load_taxonomy(),
        "claims": claims,
        "graph": _graph([item[0] for item in specs]),
        "analysis_date": date(2026, 1, 15),
        "as_of": date(2026, 1, 15),
    }
    first = scorer.score(matches=matches, **kwargs)
    second = scorer.score(matches=list(reversed(matches)), **kwargs)
    assert first == second
    relevant = {item.alpha_id: item.final_score for item in first if item.alpha_id in {s[0] for s in specs}}
    assert len(set(relevant.values())) > 1
    assert all(0 <= score <= 100 for score in relevant.values())
    no_evidence = next(item for item in first if item.alpha_id == "A001")
    assert no_evidence.final_score == 0
    assert no_evidence.evidence_references == []


@pytest.mark.unit
def test_duplicate_same_origin_evidence_is_not_counted_twice() -> None:
    first_claim, first_match = _claim(
        "A101", 0.9, AgentType.NEWS, "Cloud capex evidence is the same."
    )
    second_claim, second_match = _claim(
        "A101", 0.8, AgentType.SENTIMENT, "Cloud capex evidence is the same."
    )
    result = ActivationScorer().score(
        taxonomy=load_taxonomy(),
        matches=[first_match, second_match],
        claims={first_claim.claim_id: first_claim, second_claim.claim_id: second_claim},
        graph=_graph(["A101"]),
        analysis_date=date(2026, 1, 15),
        as_of=date(2026, 1, 15),
    )
    activation = next(item for item in result if item.alpha_id == "A101")
    assert activation.components["matched_evidence"].raw_value == 90
    assert activation.components["agent_agreement"].raw_value == 25
    assert len(activation.evidence_references) == 2
