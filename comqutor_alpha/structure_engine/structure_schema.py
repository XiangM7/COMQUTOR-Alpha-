"""Pydantic v2 domain contracts for COMQUTOR Alpha.

These models deliberately have no FastAPI, SQLAlchemy, LangChain, or UI
dependencies.  They are the serialization boundary shared by every layer.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from enum import Enum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
AlphaId = Annotated[str, StringConstraints(pattern=r"^A\d{3}$")]
UnitFloat = Annotated[float, Field(ge=0.0, le=1.0)]
Score = Annotated[float, Field(ge=0.0, le=100.0)]


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class AgentType(str, Enum):
    MARKET = "market"
    SENTIMENT = "sentiment"
    NEWS = "news"
    FUNDAMENTALS = "fundamentals"


ALL_AGENTS = frozenset(AgentType)


class Direction(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


class SourceType(str, Enum):
    NEWS = "news"
    FILING = "filing"
    PRICE = "price"
    ANALYST = "analyst"
    SOCIAL = "social"
    TECHNICAL = "technical"
    MACRO = "macro"
    UNKNOWN = "unknown"


class RunStatus(str, Enum):
    COMPLETE = "complete"
    DEGRADED = "degraded"
    FAILED = "failed"


class RawAnalystReport(DomainModel):
    run_id: UUID
    ticker: NonEmptyStr
    analysis_date: date
    agent: AgentType
    report_text: NonEmptyStr
    captured_at: datetime
    source_field: NonEmptyStr

    @model_validator(mode="after")
    def require_aware_timestamp(self) -> RawAnalystReport:
        if self.captured_at.tzinfo is None:
            raise ValueError("captured_at must be timezone-aware")
        return self


class RawAnalystReportBundle(DomainModel):
    run_id: UUID
    ticker: NonEmptyStr
    analysis_date: date
    reports: dict[AgentType, RawAnalystReport] = Field(default_factory=dict)
    missing_agents: list[AgentType] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_complete_accounting(self) -> RawAnalystReportBundle:
        report_agents = set(self.reports)
        missing = set(self.missing_agents)
        if report_agents & missing:
            raise ValueError("an agent cannot be both present and missing")
        if report_agents | missing != ALL_AGENTS:
            raise ValueError("all four analyst types must be present or explicitly missing")
        if len(missing) != len(self.missing_agents):
            raise ValueError("missing_agents must be unique")
        for agent, report in self.reports.items():
            if report.agent != agent:
                raise ValueError("report map key must match report.agent")
            if (report.run_id, report.ticker, report.analysis_date) != (
                self.run_id,
                self.ticker,
                self.analysis_date,
            ):
                raise ValueError("report metadata must match bundle metadata")
        return self


class AdapterFailure(DomainModel):
    agent: AgentType
    error_code: NonEmptyStr
    message: NonEmptyStr
    attempt_count: int = Field(ge=1)
    retryable: bool
    raw_artifact_reference: NonEmptyStr


class Claim(DomainModel):
    claim_id: UUID
    run_id: UUID
    ticker: NonEmptyStr
    agent: AgentType
    claim: NonEmptyStr
    evidence: NonEmptyStr
    entities: list[NonEmptyStr] = Field(default_factory=list)
    factors: list[NonEmptyStr] = Field(default_factory=list)
    direction: Direction
    confidence: UnitFloat
    source_type: SourceType
    source_refs: list[NonEmptyStr] = Field(default_factory=list)
    extraction_method: NonEmptyStr


class ClaimBatch(DomainModel):
    run_id: UUID
    ticker: NonEmptyStr
    agent: AgentType
    claims: list[Claim] = Field(default_factory=list)
    failure: AdapterFailure | None = None

    @model_validator(mode="after")
    def validate_batch(self) -> ClaimBatch:
        if self.failure is not None and self.failure.agent != self.agent:
            raise ValueError("failure agent must match batch agent")
        ids: set[UUID] = set()
        for claim in self.claims:
            if (claim.run_id, claim.ticker, claim.agent) != (
                self.run_id,
                self.ticker,
                self.agent,
            ):
                raise ValueError("claim metadata must match batch metadata")
            if claim.claim_id in ids:
                raise ValueError("claim_id must be unique within a batch")
            ids.add(claim.claim_id)
        return self


class AdapterRunResult(DomainModel):
    run_id: UUID
    ticker: NonEmptyStr
    status: RunStatus
    batches: list[ClaimBatch]

    @model_validator(mode="after")
    def validate_status(self) -> AdapterRunResult:
        if {batch.agent for batch in self.batches} != ALL_AGENTS or len(self.batches) != 4:
            raise ValueError("adapter result must contain exactly one batch per analyst")
        successes = sum(bool(batch.claims) for batch in self.batches)
        failures = sum(batch.failure is not None for batch in self.batches)
        expected = (
            RunStatus.FAILED
            if successes == 0
            else RunStatus.DEGRADED
            if failures
            else RunStatus.COMPLETE
        )
        if self.status != expected:
            raise ValueError(f"adapter status must be {expected.value}")
        return self


class MatchMethod(str, Enum):
    KEYWORD_FACTOR = "keyword_factor"
    LLM_CLASSIFIER = "llm_classifier"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"


class MatchComponentBreakdown(DomainModel):
    keyword_score: UnitFloat
    factor_score: UnitFloat
    llm_score: UnitFloat | None = None
    combined_score: UnitFloat


class AlphaMatch(DomainModel):
    match_id: UUID
    claim_id: UUID
    evidence_reference: NonEmptyStr
    alpha_id: AlphaId
    direction: Direction
    match_score: UnitFloat
    method: MatchMethod
    components: MatchComponentBreakdown

    @model_validator(mode="after")
    def score_matches_breakdown(self) -> AlphaMatch:
        if not math.isclose(self.match_score, self.components.combined_score, abs_tol=1e-9):
            raise ValueError("match_score must equal components.combined_score")
        return self


class NodeType(str, Enum):
    ENTITY = "entity"
    FACTOR = "factor"
    FUNDAMENTAL = "fundamental"
    MACRO = "macro"
    THEME = "theme"
    VALUATION = "valuation"
    BEHAVIORAL = "behavioral"
    UNKNOWN = "unknown"


class EdgeType(str, Enum):
    CAUSAL = "causal"
    SUPPORTIVE = "supportive"
    CONFLICTING = "conflicting"


class StructureNode(DomainModel):
    node_id: NonEmptyStr
    canonical_label: NonEmptyStr
    original_labels: list[NonEmptyStr] = Field(min_length=1)
    node_type: NodeType
    alpha_ids: list[AlphaId] = Field(default_factory=list)
    claim_ids: list[UUID] = Field(min_length=1)
    evidence_references: list[NonEmptyStr] = Field(min_length=1)
    agents: list[AgentType] = Field(min_length=1)


class StructureEdge(DomainModel):
    edge_id: NonEmptyStr
    source: NonEmptyStr
    target: NonEmptyStr
    edge_type: EdgeType
    weight: UnitFloat
    claim_ids: list[UUID] = Field(min_length=1)
    evidence_references: list[NonEmptyStr] = Field(min_length=1)
    agents: list[AgentType] = Field(min_length=1)

    @model_validator(mode="after")
    def reject_self_loop(self) -> StructureEdge:
        if self.source == self.target:
            raise ValueError("self-loop edges are not admissible")
        return self


class StructureExtractionFailure(DomainModel):
    claim_id: UUID
    error_code: NonEmptyStr
    message: NonEmptyStr
    retryable: bool = False


class StructureExtractionResult(DomainModel):
    claim_id: UUID
    nodes: list[StructureNode] = Field(default_factory=list)
    edges: list[StructureEdge] = Field(default_factory=list)
    failure: StructureExtractionFailure | None = None

    @model_validator(mode="after")
    def validate_graph_fragment(self) -> StructureExtractionResult:
        node_ids = {node.node_id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("extraction node_id values must be unique")
        edge_ids = {edge.edge_id for edge in self.edges}
        if len(edge_ids) != len(self.edges):
            raise ValueError("extraction edge_id values must be unique")
        dangling = [
            edge.edge_id
            for edge in self.edges
            if edge.source not in node_ids or edge.target not in node_ids
        ]
        if dangling:
            raise ValueError(f"dangling extraction edges: {dangling}")
        return self


class StructureGraph(DomainModel):
    run_id: UUID
    ticker: NonEmptyStr
    nodes: list[StructureNode]
    edges: list[StructureEdge]
    graph_coherence_score: Score

    @model_validator(mode="after")
    def validate_graph(self) -> StructureGraph:
        node_ids = {node.node_id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("graph node_id values must be unique")
        if len({edge.edge_id for edge in self.edges}) != len(self.edges):
            raise ValueError("graph edge_id values must be unique")
        if any(edge.source not in node_ids or edge.target not in node_ids for edge in self.edges):
            raise ValueError("graph contains a dangling edge")
        return self


class ScoreComponent(DomainModel):
    raw_value: Score
    weight: UnitFloat
    contribution: Score

    @model_validator(mode="after")
    def validate_contribution(self) -> ScoreComponent:
        expected = self.raw_value * self.weight
        if not math.isclose(self.contribution, expected, abs_tol=1e-6):
            raise ValueError("contribution must equal raw_value * weight")
        return self


class ActivationStatus(str, Enum):
    INACTIVE = "inactive"
    WATCH = "watch"
    ACTIVE = "active"
    DOMINANT = "dominant"
    REGIME_LEVEL = "regime_level"


ACTIVATION_COMPONENTS = frozenset(
    {"matched_evidence", "agent_agreement", "graph_coherence", "recency", "direction_strength"}
)


class ActivationBreakdown(DomainModel):
    alpha_id: AlphaId
    components: dict[NonEmptyStr, ScoreComponent]
    final_score: Score
    status: ActivationStatus
    direction: Direction
    evidence_references: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_components(self) -> ActivationBreakdown:
        if set(self.components) != ACTIVATION_COMPONENTS:
            raise ValueError("activation must contain exactly the five MVP components")
        total = sum(component.contribution for component in self.components.values())
        if not math.isclose(self.final_score, total, abs_tol=1e-6):
            raise ValueError("final_score must equal component contributions")
        expected_status = (
            ActivationStatus.INACTIVE
            if self.final_score <= 30
            else ActivationStatus.WATCH
            if self.final_score <= 50
            else ActivationStatus.ACTIVE
            if self.final_score <= 70
            else ActivationStatus.DOMINANT
            if self.final_score <= 85
            else ActivationStatus.REGIME_LEVEL
        )
        if self.status != expected_status:
            raise ValueError(f"activation status must be {expected_status.value}")
        if not self.evidence_references and self.final_score != 0:
            raise ValueError("activation without evidence must have score zero")
        return self


class ConflictLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    MEDIUM_HIGH = "medium_high"
    HIGH = "high"


class ConflictComponentBreakdown(DomainModel):
    minimum_activation: Score
    contradiction_weight: UnitFloat
    evidence_strength: UnitFloat


class ConflictResult(DomainModel):
    alpha_a: AlphaId
    alpha_b: AlphaId
    bull_structure: NonEmptyStr
    bear_structure: NonEmptyStr
    bull_evidence: list[NonEmptyStr] = Field(min_length=1)
    bear_evidence: list[NonEmptyStr] = Field(min_length=1)
    contradiction_weight: UnitFloat
    evidence_strength: UnitFloat
    components: ConflictComponentBreakdown
    score: Score
    level: ConflictLevel
    explanation: NonEmptyStr

    @model_validator(mode="after")
    def validate_conflict_score(self) -> ConflictResult:
        expected = (
            self.components.minimum_activation
            * self.components.contradiction_weight
            * self.components.evidence_strength
        )
        if not math.isclose(self.score, expected, abs_tol=1e-6):
            raise ValueError("conflict score must equal its deterministic formula")
        if not math.isclose(
            self.contradiction_weight,
            self.components.contradiction_weight,
            abs_tol=1e-9,
        ) or not math.isclose(
            self.evidence_strength, self.components.evidence_strength, abs_tol=1e-9
        ):
            raise ValueError("conflict top-level values must match components")
        expected_level = (
            ConflictLevel.LOW
            if self.score <= 25
            else ConflictLevel.MEDIUM
            if self.score <= 50
            else ConflictLevel.MEDIUM_HIGH
            if self.score <= 75
            else ConflictLevel.HIGH
        )
        if self.level != expected_level:
            raise ValueError(f"conflict level must be {expected_level.value}")
        return self


class ResearchError(DomainModel):
    error_code: NonEmptyStr
    message: NonEmptyStr
    stage: NonEmptyStr
    retryable: bool = False


class ResearchResult(DomainModel):
    run_id: UUID
    ticker: NonEmptyStr
    analysis_date: date
    status: RunStatus
    dominant_alphas: list[ActivationBreakdown] = Field(default_factory=list)
    main_conflict: ConflictResult | None = None
    conflicts: list[ConflictResult] = Field(default_factory=list)
    graph_reference: NonEmptyStr | None = None
    summary: NonEmptyStr
    evidence_coverage: UnitFloat
    degraded_reasons: list[NonEmptyStr] = Field(default_factory=list)
    errors: list[ResearchError] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_result_state(self) -> ResearchResult:
        if self.status == RunStatus.COMPLETE and (self.degraded_reasons or self.errors):
            raise ValueError("complete results cannot contain degradation reasons or errors")
        if self.main_conflict is not None and self.main_conflict not in self.conflicts:
            raise ValueError("main_conflict must also appear in conflicts")
        return self


class ExposureStatus(str, Enum):
    SEEDED = "seeded"
    NO_SEED = "no_seed"


class ExposureResult(DomainModel):
    ticker: NonEmptyStr
    alpha_id: AlphaId
    status: ExposureStatus
    historical_mapping: UnitFloat | None = None
    current_evidence: UnitFloat
    agent_confidence: UnitFloat
    exposure_score: UnitFloat | None = None
    evidence_references: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_exposure(self) -> ExposureResult:
        if self.status == ExposureStatus.NO_SEED:
            if self.historical_mapping is not None or self.exposure_score is not None:
                raise ValueError("no_seed exposure cannot contain guessed values")
            return self
        if self.historical_mapping is None or self.exposure_score is None:
            raise ValueError("seeded exposure requires historical_mapping and exposure_score")
        expected = (
            self.historical_mapping * 0.5
            + self.current_evidence * 0.3
            + self.agent_confidence * 0.2
        )
        if not math.isclose(self.exposure_score, expected, abs_tol=1e-9):
            raise ValueError("exposure_score must equal the MVP formula")
        return self


ReviewStatus = Literal["reviewed", "pending_product_review"]
