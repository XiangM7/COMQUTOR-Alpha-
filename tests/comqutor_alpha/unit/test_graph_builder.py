from __future__ import annotations

from uuid import UUID

import networkx as nx
import pytest

from comqutor_alpha.structure_engine.graph_builder import GraphBuilder
from comqutor_alpha.structure_engine.structure_schema import (
    AgentType,
    EdgeType,
    NodeType,
    StructureEdge,
    StructureExtractionResult,
    StructureNode,
)

RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
C1 = UUID("22222222-2222-4222-8222-222222222222")
C2 = UUID("33333333-3333-4333-8333-333333333333")


def _fragment(claim_id, agent, evidence, weight):
    return StructureExtractionResult(
        claim_id=claim_id,
        nodes=[
            StructureNode(
                node_id="ai-capex",
                canonical_label="ai capex",
                original_labels=["AI CapEx" if claim_id == C1 else "AI capital spending"],
                node_type=NodeType.FACTOR,
                alpha_ids=["A101"],
                claim_ids=[claim_id],
                evidence_references=[evidence],
                agents=[agent],
            ),
            StructureNode(
                node_id="gpu-demand",
                canonical_label="gpu demand",
                original_labels=["GPU demand"],
                node_type=NodeType.FACTOR,
                alpha_ids=["A101", "A201"],
                claim_ids=[claim_id],
                evidence_references=[evidence],
                agents=[agent],
            ),
        ],
        edges=[
            StructureEdge(
                edge_id=f"source-{claim_id}",
                source="ai-capex",
                target="gpu-demand",
                edge_type=EdgeType.CAUSAL,
                weight=weight,
                claim_ids=[claim_id],
                evidence_references=[evidence],
                agents=[agent],
            )
        ],
    )


@pytest.mark.unit
def test_graph_merge_unions_all_provenance_and_uses_networkx_digraph() -> None:
    fragments = [
        _fragment(C1, AgentType.NEWS, "claim:c1", 0.7),
        _fragment(C2, AgentType.FUNDAMENTALS, "claim:c2", 0.9),
    ]
    built = GraphBuilder().build(run_id=RUN_ID, ticker="NVDA", fragments=fragments)
    assert isinstance(built.graph, nx.DiGraph)
    assert len(built.document.nodes) == 2
    assert len(built.document.edges) == 1
    capex = next(node for node in built.document.nodes if node.node_id == "ai-capex")
    assert set(capex.original_labels) == {"AI CapEx", "AI capital spending"}
    assert set(capex.claim_ids) == {C1, C2}
    assert set(capex.evidence_references) == {"claim:c1", "claim:c2"}
    assert set(capex.agents) == {AgentType.NEWS, AgentType.FUNDAMENTALS}
    edge = built.document.edges[0]
    assert edge.weight == 0.9
    assert set(edge.claim_ids) == {C1, C2}
    assert built.document.graph_coherence_score == 35


@pytest.mark.unit
def test_input_order_does_not_change_serialized_semantics() -> None:
    fragments = [
        _fragment(C1, AgentType.NEWS, "claim:c1", 0.7),
        _fragment(C2, AgentType.FUNDAMENTALS, "claim:c2", 0.9),
    ]
    first = GraphBuilder().build(run_id=RUN_ID, ticker="NVDA", fragments=fragments)
    second = GraphBuilder().build(
        run_id=RUN_ID, ticker="NVDA", fragments=list(reversed(fragments))
    )
    assert first.document.model_dump(mode="json") == second.document.model_dump(mode="json")
    assert list(first.graph.nodes) == list(second.graph.nodes)
    assert list(first.graph.edges) == list(second.graph.edges)
