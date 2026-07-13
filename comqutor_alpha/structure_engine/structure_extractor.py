"""Strict, fail-soft extraction of evidence-provenance graph fragments."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from pydantic import Field

from comqutor_alpha.structure_engine.normalization import (
    canonicalize_label,
    stable_node_id,
)
from comqutor_alpha.structure_engine.structure_schema import (
    AlphaMatch,
    Claim,
    DomainModel,
    EdgeType,
    NodeType,
    NonEmptyStr,
    StructureEdge,
    StructureExtractionFailure,
    StructureExtractionResult,
    StructureNode,
    UnitFloat,
)


class ExtractedNode(DomainModel):
    label: NonEmptyStr
    node_type: NodeType = NodeType.UNKNOWN


class ExtractedEdge(DomainModel):
    source: NonEmptyStr
    target: NonEmptyStr
    edge_type: EdgeType
    weight: UnitFloat


class ExtractedStructure(DomainModel):
    nodes: list[ExtractedNode] = Field(default_factory=list)
    edges: list[ExtractedEdge] = Field(default_factory=list)


class RelationExtractor(Protocol):
    def extract(self, claim: Claim) -> Any: ...


class StructureExtractor:
    def __init__(self, extractor: RelationExtractor):
        self.extractor = extractor

    @staticmethod
    def _payload(value: Any) -> ExtractedStructure:
        if isinstance(value, ExtractedStructure):
            return value
        if isinstance(value, str):
            return ExtractedStructure.model_validate_json(value)
        if isinstance(value, Mapping):
            return ExtractedStructure.model_validate(value)
        if hasattr(value, "model_dump"):
            return ExtractedStructure.model_validate(value.model_dump())
        raise TypeError(f"unsupported structure payload: {type(value).__name__}")

    def extract_claim(
        self,
        claim: Claim,
        matches: Sequence[AlphaMatch] = (),
    ) -> StructureExtractionResult:
        try:
            payload = self._payload(self.extractor.extract(claim))
            if not payload.nodes:
                raise ValueError("extractor returned no structure nodes")
            alpha_ids = sorted({match.alpha_id for match in matches if match.claim_id == claim.claim_id})
            nodes_by_id: dict[str, StructureNode] = {}
            for item in payload.nodes:
                node_id = stable_node_id(item.label)
                existing = nodes_by_id.get(node_id)
                if existing is None:
                    nodes_by_id[node_id] = StructureNode(
                        node_id=node_id,
                        canonical_label=canonicalize_label(item.label),
                        original_labels=[item.label],
                        node_type=item.node_type,
                        alpha_ids=alpha_ids,
                        claim_ids=[claim.claim_id],
                        evidence_references=[f"claim:{claim.claim_id}"],
                        agents=[claim.agent],
                    )
                elif item.label not in existing.original_labels:
                    existing.original_labels.append(item.label)

            edges_by_id: dict[str, StructureEdge] = {}
            for item in payload.edges:
                source = stable_node_id(item.source)
                target = stable_node_id(item.target)
                if source not in nodes_by_id or target not in nodes_by_id:
                    raise ValueError(f"dangling edge {item.source!r} -> {item.target!r}")
                edge_id = f"{source}--{item.edge_type.value}--{target}"
                if edge_id in edges_by_id:
                    continue
                edges_by_id[edge_id] = StructureEdge(
                    edge_id=edge_id,
                    source=source,
                    target=target,
                    edge_type=item.edge_type,
                    weight=item.weight,
                    claim_ids=[claim.claim_id],
                    evidence_references=[f"claim:{claim.claim_id}"],
                    agents=[claim.agent],
                )
            return StructureExtractionResult(
                claim_id=claim.claim_id,
                nodes=sorted(nodes_by_id.values(), key=lambda node: node.node_id),
                edges=sorted(edges_by_id.values(), key=lambda edge: edge.edge_id),
            )
        except Exception as exc:
            return StructureExtractionResult(
                claim_id=claim.claim_id,
                nodes=[],
                edges=[],
                failure=StructureExtractionFailure(
                    claim_id=claim.claim_id,
                    error_code="structure_extraction_failed",
                    message=f"{type(exc).__name__}: {exc}",
                    retryable=False,
                ),
            )

    def extract_claims(
        self,
        claims: Sequence[Claim],
        matches: Sequence[AlphaMatch] = (),
    ) -> tuple[StructureExtractionResult, ...]:
        matches_by_claim: dict[Any, list[AlphaMatch]] = {}
        for match in matches:
            matches_by_claim.setdefault(match.claim_id, []).append(match)
        return tuple(
            self.extract_claim(claim, matches_by_claim.get(claim.claim_id, ()))
            for claim in claims
        )
