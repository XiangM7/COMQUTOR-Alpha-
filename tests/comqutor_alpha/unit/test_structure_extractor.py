from __future__ import annotations

from uuid import UUID

import pytest

from comqutor_alpha.structure_engine.structure_extractor import StructureExtractor
from comqutor_alpha.structure_engine.structure_schema import (
    AgentType,
    AlphaMatch,
    Claim,
    Direction,
    MatchComponentBreakdown,
    MatchMethod,
    SourceType,
)

RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
CLAIM_ID = UUID("22222222-2222-4222-8222-222222222222")


def _claim() -> Claim:
    return Claim(
        claim_id=CLAIM_ID,
        run_id=RUN_ID,
        ticker="NVDA",
        agent=AgentType.NEWS,
        claim="AI capex drives GPU demand and supports NVDA revenue growth.",
        evidence="Cloud providers raised AI capex and reported stronger GPU demand.",
        entities=["NVDA", "GPU"],
        factors=["AI CapEx", "GPU Demand", "Revenue Growth"],
        direction=Direction.POSITIVE,
        confidence=0.85,
        source_type=SourceType.NEWS,
        source_refs=["fixture:news"],
        extraction_method="fixture",
    )


def _match() -> AlphaMatch:
    return AlphaMatch(
        match_id=UUID("33333333-3333-4333-8333-333333333333"),
        claim_id=CLAIM_ID,
        evidence_reference=f"claim:{CLAIM_ID}",
        alpha_id="A101",
        direction=Direction.POSITIVE,
        match_score=0.9,
        method=MatchMethod.KEYWORD_FACTOR,
        components=MatchComponentBreakdown(
            keyword_score=0.9,
            factor_score=0.9,
            combined_score=0.9,
        ),
    )


class FakeRelationExtractor:
    def __init__(self, payload):
        self.payload = payload

    def extract(self, claim):
        del claim
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


@pytest.mark.unit
def test_simple_causal_chain_and_synonym_merge_preserve_provenance() -> None:
    payload = {
        "nodes": [
            {"label": "AI CapEx", "node_type": "factor"},
            {"label": "AI capital spending", "node_type": "factor"},
            {"label": "GPU Demand", "node_type": "factor"},
            {"label": "NVDA Revenue Growth", "node_type": "fundamental"},
        ],
        "edges": [
            {"source": "AI capital spending", "target": "GPU Demand", "edge_type": "causal", "weight": 0.85},
            {"source": "GPU Demand", "target": "NVDA Revenue Growth", "edge_type": "causal", "weight": 0.80},
        ],
    }
    result = StructureExtractor(FakeRelationExtractor(payload)).extract_claim(_claim(), [_match()])
    assert result.failure is None
    assert len(result.nodes) == 3
    assert len(result.edges) == 2
    capex = next(node for node in result.nodes if node.node_id == "ai-capex")
    assert set(capex.original_labels) == {"AI CapEx", "AI capital spending"}
    assert capex.alpha_ids == ["A101"]
    for edge in result.edges:
        assert edge.claim_ids == [CLAIM_ID]
        assert edge.evidence_references == [f"claim:{CLAIM_ID}"]
        assert edge.agents == [AgentType.NEWS]


@pytest.mark.unit
@pytest.mark.parametrize(
    "payload",
    [
        {"nodes": [], "edges": []},
        {
            "nodes": [{"label": "A", "node_type": "factor"}],
            "edges": [{"source": "A", "target": "B", "edge_type": "causal", "weight": 0.5}],
        },
        {
            "nodes": [{"label": "A", "node_type": "factor"}],
            "edges": [{"source": "A", "target": "A", "edge_type": "causal", "weight": 0.5}],
        },
        "not-json",
        TimeoutError("provider timeout"),
    ],
)
def test_invalid_or_empty_extraction_fails_soft_without_edges(payload) -> None:
    result = StructureExtractor(FakeRelationExtractor(payload)).extract_claim(_claim())
    assert result.nodes == []
    assert result.edges == []
    assert result.failure is not None
    assert result.failure.error_code == "structure_extraction_failed"


@pytest.mark.unit
def test_extraction_order_is_stable() -> None:
    payload = {
        "nodes": [
            {"label": "Zeta", "node_type": "factor"},
            {"label": "Alpha", "node_type": "factor"},
        ],
        "edges": [
            {"source": "Zeta", "target": "Alpha", "edge_type": "supportive", "weight": 0.7}
        ],
    }
    result = StructureExtractor(FakeRelationExtractor(payload)).extract_claim(_claim())
    assert [node.node_id for node in result.nodes] == ["alpha", "zeta"]
    assert [edge.edge_id for edge in result.edges] == ["zeta--supportive--alpha"]
