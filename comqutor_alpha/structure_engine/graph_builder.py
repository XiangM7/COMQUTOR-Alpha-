"""Order-independent networkx DiGraph construction with provenance union."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import networkx as nx

from comqutor_alpha.structure_engine.structure_schema import (
    NodeType,
    StructureEdge,
    StructureExtractionResult,
    StructureGraph,
    StructureNode,
)


@dataclass(frozen=True, slots=True)
class BuiltStructureGraph:
    graph: nx.DiGraph
    document: StructureGraph


class GraphBuilder:
    def build(
        self,
        *,
        run_id: UUID,
        ticker: str,
        fragments: tuple[StructureExtractionResult, ...] | list[StructureExtractionResult],
    ) -> BuiltStructureGraph:
        node_groups: dict[str, list[StructureNode]] = {}
        edge_groups: dict[tuple[str, str, str], list[StructureEdge]] = {}
        for fragment in fragments:
            if fragment.failure is not None:
                continue
            for node in fragment.nodes:
                node_groups.setdefault(node.node_id, []).append(node)
            for edge in fragment.edges:
                edge_groups.setdefault(
                    (edge.source, edge.target, edge.edge_type.value), []
                ).append(edge)

        nodes: list[StructureNode] = []
        for node_id, group in sorted(node_groups.items()):
            types = sorted(
                {node.node_type for node in group if node.node_type != NodeType.UNKNOWN},
                key=lambda item: item.value,
            )
            nodes.append(
                StructureNode(
                    node_id=node_id,
                    canonical_label=sorted({node.canonical_label for node in group})[0],
                    original_labels=sorted(
                        {label for node in group for label in node.original_labels},
                        key=str.casefold,
                    ),
                    node_type=types[0] if types else NodeType.UNKNOWN,
                    alpha_ids=sorted({alpha for node in group for alpha in node.alpha_ids}),
                    claim_ids=sorted(
                        {claim for node in group for claim in node.claim_ids}, key=str
                    ),
                    evidence_references=sorted(
                        {ref for node in group for ref in node.evidence_references}
                    ),
                    agents=sorted(
                        {agent for node in group for agent in node.agents},
                        key=lambda item: item.value,
                    ),
                )
            )

        node_ids = {node.node_id for node in nodes}
        edges: list[StructureEdge] = []
        for (source, target, edge_type), group in sorted(edge_groups.items()):
            if source not in node_ids or target not in node_ids:
                continue
            prototype = group[0]
            edges.append(
                StructureEdge(
                    edge_id=f"{source}--{edge_type}--{target}",
                    source=source,
                    target=target,
                    edge_type=prototype.edge_type,
                    weight=max(edge.weight for edge in group),
                    claim_ids=sorted(
                        {claim for edge in group for claim in edge.claim_ids}, key=str
                    ),
                    evidence_references=sorted(
                        {ref for edge in group for ref in edge.evidence_references}
                    ),
                    agents=sorted(
                        {agent for edge in group for agent in edge.agents},
                        key=lambda item: item.value,
                    ),
                )
            )

        alpha_covered = {alpha for node in nodes for alpha in node.alpha_ids}
        coherence = float(min(100, len(edges) * 15 + len(alpha_covered) * 10))
        document = StructureGraph(
            run_id=run_id,
            ticker=ticker,
            nodes=nodes,
            edges=edges,
            graph_coherence_score=coherence,
        )
        graph = nx.DiGraph(run_id=str(run_id), ticker=ticker, coherence=coherence)
        for node in nodes:
            graph.add_node(node.node_id, **node.model_dump(mode="json"))
        for edge in edges:
            current = graph.get_edge_data(edge.source, edge.target, default={})
            records = list(current.get("edge_records", []))
            records.append(edge.model_dump(mode="json"))
            records.sort(key=lambda record: record["edge_id"])
            graph.add_edge(edge.source, edge.target, edge_records=records)
        return BuiltStructureGraph(graph=graph, document=document)
