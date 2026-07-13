from __future__ import annotations

from uuid import UUID, uuid5

import pytest

from comqutor_alpha.alpha_library import load_taxonomy
from comqutor_alpha.structure_engine.conflict_detector import (
    ConflictDetector,
    conflict_level,
)
from comqutor_alpha.structure_engine.structure_schema import (
    ActivationBreakdown,
    ActivationStatus,
    AgentType,
    AlphaMatch,
    Claim,
    ConflictLevel,
    Direction,
    MatchComponentBreakdown,
    MatchMethod,
    ScoreComponent,
    SourceType,
)

RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
NAMESPACE = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def _components(raw=60.0):
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


def _activation(alpha_id, direction, evidence=True):
    return ActivationBreakdown(
        alpha_id=alpha_id,
        components=_components(60 if evidence else 0),
        final_score=60 if evidence else 0,
        status=ActivationStatus.ACTIVE if evidence else ActivationStatus.INACTIVE,
        direction=Direction(direction),
        evidence_references=[f"claim:{alpha_id}"] if evidence else [],
    )


def _claim_match(alpha_id, direction, score):
    claim_id = uuid5(NAMESPACE, alpha_id)
    claim = Claim(
        claim_id=claim_id,
        run_id=RUN_ID,
        ticker="NVDA",
        agent=AgentType.NEWS,
        claim=f"Claim for {alpha_id}",
        evidence=f"Independent evidence for {alpha_id}",
        direction=Direction(direction),
        confidence=score,
        source_type=SourceType.NEWS,
        extraction_method="fixture",
    )
    match = AlphaMatch(
        match_id=uuid5(NAMESPACE, f"match-{alpha_id}"),
        claim_id=claim_id,
        evidence_reference=f"claim:{alpha_id}",
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


@pytest.mark.unit
def test_taxonomy_declared_conflict_has_exact_formula_and_both_evidence_sides() -> None:
    bull_claim, bull_match = _claim_match("A101", "positive", 0.8)
    bear_claim, bear_match = _claim_match("A304", "negative", 0.7)
    results = ConflictDetector().detect(
        taxonomy=load_taxonomy(),
        activations=[
            _activation("A101", "positive"),
            _activation("A304", "negative"),
        ],
        matches=[bull_match, bear_match],
        claims={bull_claim.claim_id: bull_claim, bear_claim.claim_id: bear_claim},
    )
    assert len(results) == 1
    conflict = results[0]
    assert conflict.bull_structure.startswith("A101")
    assert conflict.bear_structure.startswith("A304")
    assert conflict.evidence_strength == pytest.approx(0.75)
    assert conflict.score == pytest.approx(60 * 0.9 * 0.75)
    assert conflict.level == ConflictLevel.MEDIUM
    assert conflict.bull_evidence and conflict.bear_evidence


@pytest.mark.unit
def test_undeclared_pair_and_missing_side_do_not_create_conflict() -> None:
    a102_claim, a102_match = _claim_match("A102", "positive", 0.9)
    a304_claim, a304_match = _claim_match("A304", "negative", 0.9)
    detector = ConflictDetector()
    assert detector.detect(
        taxonomy=load_taxonomy(),
        activations=[_activation("A102", "positive"), _activation("A304", "negative")],
        matches=[a102_match, a304_match],
        claims={a102_claim.claim_id: a102_claim, a304_claim.claim_id: a304_claim},
    ) == ()
    assert detector.detect(
        taxonomy=load_taxonomy(),
        activations=[_activation("A101", "positive"), _activation("A304", "negative", False)],
        matches=[],
        claims={},
    ) == ()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("score", "level"),
    [
        (0, ConflictLevel.LOW),
        (25, ConflictLevel.LOW),
        (25.1, ConflictLevel.MEDIUM),
        (50, ConflictLevel.MEDIUM),
        (50.1, ConflictLevel.MEDIUM_HIGH),
        (75, ConflictLevel.MEDIUM_HIGH),
        (75.1, ConflictLevel.HIGH),
        (100, ConflictLevel.HIGH),
    ],
)
def test_conflict_level_has_no_decimal_gaps(score, level) -> None:
    assert conflict_level(score) == level
