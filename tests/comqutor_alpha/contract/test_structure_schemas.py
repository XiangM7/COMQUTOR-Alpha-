from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from comqutor_alpha.alpha_library import load_taxonomy
from comqutor_alpha.structure_engine.structure_schema import (
    ActivationBreakdown,
    ActivationStatus,
    AdapterFailure,
    AgentType,
    AlphaMatch,
    Claim,
    ClaimBatch,
    ConflictComponentBreakdown,
    ConflictLevel,
    ConflictResult,
    Direction,
    EdgeType,
    MatchComponentBreakdown,
    MatchMethod,
    NodeType,
    RawAnalystReport,
    RawAnalystReportBundle,
    ResearchResult,
    RunStatus,
    ScoreComponent,
    SourceType,
    StructureEdge,
    StructureNode,
)

RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
CLAIM_ID = UUID("22222222-2222-4222-8222-222222222222")
MATCH_ID = UUID("33333333-3333-4333-8333-333333333333")
NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _report(agent: AgentType) -> RawAnalystReport:
    return RawAnalystReport(
        run_id=RUN_ID,
        ticker="NVDA",
        analysis_date=date(2026, 1, 15),
        agent=agent,
        report_text=f"{agent.value} evidence report",
        captured_at=NOW,
        source_field=f"{agent.value}_report",
    )


def _claim() -> Claim:
    return Claim(
        claim_id=CLAIM_ID,
        run_id=RUN_ID,
        ticker="NVDA",
        agent=AgentType.NEWS,
        claim="AI training is increasing GPU demand.",
        evidence="Cloud providers raised disclosed AI capital spending.",
        entities=["NVDA", "GPU"],
        factors=["AI training", "GPU demand"],
        direction=Direction.POSITIVE,
        confidence=0.82,
        source_type=SourceType.NEWS,
        source_refs=["raw_agent_outputs.json#news"],
        extraction_method="fake_structured_extractor_v1",
    )


def _components(raw: float = 50.0) -> dict[str, ScoreComponent]:
    weights = {
        "matched_evidence": 0.35,
        "agent_agreement": 0.20,
        "graph_coherence": 0.25,
        "recency": 0.10,
        "direction_strength": 0.10,
    }
    return {
        name: ScoreComponent(raw_value=raw, weight=weight, contribution=raw * weight)
        for name, weight in weights.items()
    }


def _activation() -> ActivationBreakdown:
    return ActivationBreakdown(
        alpha_id="A101",
        components=_components(),
        final_score=50.0,
        status=ActivationStatus.WATCH,
        direction=Direction.POSITIVE,
        evidence_references=["claim:22222222-2222-4222-8222-222222222222"],
    )


def _conflict() -> ConflictResult:
    return ConflictResult(
        alpha_a="A101",
        alpha_b="A304",
        bull_structure="A101 AI Expansion",
        bear_structure="A304 Multiple Compression",
        bull_evidence=["claim:bull"],
        bear_evidence=["claim:bear"],
        contradiction_weight=0.9,
        evidence_strength=0.8,
        components=ConflictComponentBreakdown(
            minimum_activation=50.0,
            contradiction_weight=0.9,
            evidence_strength=0.8,
        ),
        score=36.0,
        level=ConflictLevel.MEDIUM,
        explanation="AI demand is offset by valuation compression evidence.",
    )


@pytest.mark.contract
def test_all_domain_models_json_round_trip() -> None:
    reports = {agent: _report(agent) for agent in AgentType}
    bundle = RawAnalystReportBundle(
        run_id=RUN_ID,
        ticker="NVDA",
        analysis_date=date(2026, 1, 15),
        reports=reports,
    )
    failure = AdapterFailure(
        agent=AgentType.NEWS,
        error_code="timeout",
        message="provider timed out",
        attempt_count=2,
        retryable=True,
        raw_artifact_reference="raw_agent_outputs.json#news",
    )
    claim = _claim()
    batch = ClaimBatch(run_id=RUN_ID, ticker="NVDA", agent=AgentType.NEWS, claims=[claim])
    match = AlphaMatch(
        match_id=MATCH_ID,
        claim_id=CLAIM_ID,
        evidence_reference="claim:evidence",
        alpha_id="A101",
        direction=Direction.POSITIVE,
        match_score=0.8,
        method=MatchMethod.KEYWORD_FACTOR,
        components=MatchComponentBreakdown(
            keyword_score=1.0,
            factor_score=0.6,
            combined_score=0.8,
        ),
    )
    node = StructureNode(
        node_id="ai-training",
        canonical_label="AI Training",
        original_labels=["AI training"],
        node_type=NodeType.FACTOR,
        alpha_ids=["A101"],
        claim_ids=[CLAIM_ID],
        evidence_references=["claim:evidence"],
        agents=[AgentType.NEWS],
    )
    edge = StructureEdge(
        edge_id="ai-training--gpu-demand",
        source="ai-training",
        target="gpu-demand",
        edge_type=EdgeType.CAUSAL,
        weight=0.85,
        claim_ids=[CLAIM_ID],
        evidence_references=["claim:evidence"],
        agents=[AgentType.NEWS],
    )
    activation = _activation()
    conflict = _conflict()
    result = ResearchResult(
        run_id=RUN_ID,
        ticker="NVDA",
        analysis_date=date(2026, 1, 15),
        status=RunStatus.COMPLETE,
        dominant_alphas=[activation],
        main_conflict=conflict,
        conflicts=[conflict],
        graph_reference="structure_graph.json",
        summary="Research evidence shows structural support and valuation conflict.",
        evidence_coverage=1.0,
    )
    alpha = load_taxonomy().get("A101")

    for model in (
        *reports.values(),
        bundle,
        failure,
        claim,
        batch,
        match,
        node,
        edge,
        activation,
        conflict,
        result,
        alpha,
    ):
        assert type(model).model_validate_json(model.model_dump_json()) == model


@pytest.mark.contract
def test_invalid_domain_inputs_fail_closed() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 1"):
        _claim().model_copy(update={"confidence": 1.1}, deep=True).__class__.model_validate(
            {**_claim().model_dump(), "confidence": 1.1}
        )

    edge = {
        "edge_id": "bad",
        "source": "same",
        "target": "same",
        "edge_type": "causal",
        "weight": 0.5,
        "claim_ids": [str(CLAIM_ID)],
        "evidence_references": ["evidence"],
        "agents": ["news"],
    }
    with pytest.raises(ValidationError, match="self-loop"):
        StructureEdge.model_validate(edge)
    with pytest.raises(ValidationError, match="at least 1 item"):
        StructureEdge.model_validate({**edge, "target": "different", "evidence_references": []})

    components = _components()
    components["matched_evidence"] = ScoreComponent(
        raw_value=50, weight=0.35, contribution=17.5
    )
    with pytest.raises(ValidationError, match="final_score"):
        ActivationBreakdown(
            alpha_id="A101",
            components=components,
            final_score=99,
            status=ActivationStatus.DOMINANT,
            direction=Direction.POSITIVE,
            evidence_references=["evidence"],
        )

    with pytest.raises(ValidationError, match="conflict score"):
        ConflictResult.model_validate({**_conflict().model_dump(), "score": 99})


@pytest.mark.contract
def test_report_bundle_requires_explicit_four_agent_accounting() -> None:
    with pytest.raises(ValidationError, match="all four"):
        RawAnalystReportBundle(
            run_id=RUN_ID,
            ticker="NVDA",
            analysis_date=date(2026, 1, 15),
            reports={AgentType.NEWS: _report(AgentType.NEWS)},
        )
    with pytest.raises(ValidationError, match="timezone-aware"):
        RawAnalystReport.model_validate(
            {**_report(AgentType.NEWS).model_dump(), "captured_at": datetime(2026, 1, 1)}
        )
