"""Schema for the versioned MVP-10 Alpha taxonomy."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from comqutor_alpha.structure_engine.structure_schema import (
    AlphaId,
    DomainModel,
    EdgeType,
    NonEmptyStr,
    UnitFloat,
)


class AlphaStatus(str, Enum):
    ACTIVE = "active"
    WATCH = "watch"
    INACTIVE = "inactive"


class TaxonomyRelationType(str, Enum):
    CAUSAL = "causal"
    SUPPORTIVE = "supportive"
    AMPLIFIES = "amplifies"
    RELIEVES = "relieves"


class AlphaCausalEdge(DomainModel):
    source: AlphaId
    target: AlphaId
    relation_type: TaxonomyRelationType
    weight: UnitFloat
    source_note: NonEmptyStr

    @model_validator(mode="after")
    def no_self_relation(self) -> AlphaCausalEdge:
        if self.source == self.target:
            raise ValueError("taxonomy relation cannot be a self-loop")
        return self


class ConflictAlpha(DomainModel):
    alpha_id: AlphaId
    contradiction_weight: UnitFloat
    source_note: NonEmptyStr
    review_status: Literal["reviewed", "pending_product_review"]


class AlphaDefinition(DomainModel):
    alpha_id: AlphaId
    name_cn: NonEmptyStr
    name_en: NonEmptyStr
    layer: NonEmptyStr
    status: AlphaStatus
    core_thesis: NonEmptyStr
    causal_graph: list[AlphaCausalEdge] = Field(default_factory=list)
    trigger_signals: list[NonEmptyStr] = Field(min_length=1)
    confirmation_signals: list[NonEmptyStr] = Field(min_length=1)
    beneficiary_assets: list[NonEmptyStr] = Field(default_factory=list)
    risk_assets: list[NonEmptyStr] = Field(default_factory=list)
    conflict_alphas: list[ConflictAlpha] = Field(default_factory=list)
    invalidation_conditions: list[NonEmptyStr] = Field(min_length=1)
    agent_sources: list[NonEmptyStr] = Field(min_length=1)
    keywords: list[NonEmptyStr] = Field(min_length=1)
    source_note: NonEmptyStr
    review_status: Literal["reviewed", "pending_product_review"]

    @model_validator(mode="after")
    def validate_internal_references(self) -> AlphaDefinition:
        if any(edge.source != self.alpha_id for edge in self.causal_graph):
            raise ValueError("causal_graph edge source must equal owning alpha_id")
        conflict_ids = [conflict.alpha_id for conflict in self.conflict_alphas]
        if len(conflict_ids) != len(set(conflict_ids)):
            raise ValueError("conflict_alphas must be unique per Alpha")
        return self


SchemaVersion = Annotated[str, StringConstraints(pattern=r"^alpha_taxonomy_v1$")]


class AlphaTaxonomyDocument(DomainModel):
    schema_version: SchemaVersion
    source_note: NonEmptyStr
    review_status: Literal["reviewed", "pending_product_review"]
    alphas: list[AlphaDefinition]


__all__ = [
    "AlphaCausalEdge",
    "AlphaDefinition",
    "AlphaStatus",
    "AlphaTaxonomyDocument",
    "ConflictAlpha",
    "EdgeType",
    "TaxonomyRelationType",
]
