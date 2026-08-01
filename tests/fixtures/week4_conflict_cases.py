"""Shared, hand-built fixtures for Week 4 Conflict Core tests.

Nothing here is copied from a real TradingAgents report or a protected
golden-label file -- these are synthetic records built directly in the
Week 2/Week 3 structured shapes the Conflict Detector actually consumes.
"""

from __future__ import annotations

from typing import Any

from comqutor_alpha.alpha_library.alpha_schema import AlphaDefinition, ConflictAlpha
from comqutor_alpha.graph_engine.graph_schema import ACTIVATION_FORMULA_VERSION


def activation_entry(
    alpha_id: str,
    *,
    score: float = 80.0,
    status: str = "active",
    direction: str = "positive",
    name: str | None = None,
) -> dict[str, Any]:
    return {
        "alpha_id": alpha_id,
        "alpha_name": name or alpha_id,
        "activation_score": score,
        "status": status,
        "direction": direction,
        "components": {},
        "evidence_count": 0,
        "distinct_supporting_agents": 0,
        "claim_ids": [],
        "evidence": [],
        "reason_codes": [],
    }


def activation_payload(*entries: dict[str, Any]) -> dict[str, Any]:
    return {
        "formula_version": ACTIVATION_FORMULA_VERSION,
        "weights": {},
        "run_timestamp": None,
        "as_of": None,
        "alphas": list(entries),
    }


def match_record(
    claim_id: str,
    matched_alpha: str | None,
    *,
    score: float = 0.8,
    relation: str = "activation",
    match_status: str = "matched",
    agent: str = "news_agent",
    evidence: str | None = None,
    source_agent_output_id: str | None = None,
    plausible_alphas: list[str] | None = None,
    candidate_alpha_ids: list[str] | None = None,
    direction: str = "positive",
    claim_quality: str = "analytical",
    factors: list[str] | None = None,
) -> dict[str, Any]:
    """Build one raw alpha_matches.json record (the exact JSON artifact
    shape, not the DB-row shape) -- the same shape
    activation_scorer._gather_alpha_evidence already consumes.

    ``claim_quality`` defaults to ``"analytical"``: these fixtures test the
    Conflict Detector's own admission/formula logic in isolation (Unified
    Claim Admissibility Sprint's quality gate is a separate, upstream
    concern), so every synthetic claim is already-quality-gated unless a
    test explicitly overrides it to exercise routing behavior."""
    evidence_text = evidence if evidence is not None else f"evidence for {claim_id}"
    candidate_ids = candidate_alpha_ids or ([matched_alpha] if matched_alpha else [])
    candidate_scores = [
        {"alpha_id": alpha_id, "score": score, "relation": relation} for alpha_id in candidate_ids
    ]
    return {
        "claim_id": claim_id,
        "source_agent_output_id": source_agent_output_id or f"o_{claim_id}",
        "agent": agent,
        "match_status": match_status,
        "matched_alpha": matched_alpha if match_status == "matched" else None,
        "matched_alpha_name": matched_alpha if match_status == "matched" else None,
        "score": score,
        "direction": direction,
        "assertion_status": "asserted",
        "semantic_polarity": relation,
        "claim": evidence_text,
        "evidence": evidence_text,
        "reason": "test fixture",
        "plausible_alphas": plausible_alphas or [],
        "candidate_scores": candidate_scores,
        "claim_quality": claim_quality,
        "factors": factors or [],
    }


def fake_alpha(alpha_id: str, conflicts: list[ConflictAlpha] | None = None) -> AlphaDefinition:
    """A minimal, valid AlphaDefinition for synthetic/adversarial taxonomy
    fixtures -- reuses the real dataclass rather than a parallel schema."""
    return AlphaDefinition(
        alpha_id=alpha_id,
        name_en=alpha_id,
        name_cn=alpha_id,
        layer="Test",
        status="active",
        core_thesis="synthetic fixture alpha",
        keywords=["test"],
        agent_sources=["news_agent"],
        conflict_alphas=conflicts or [],
    )


def two_alpha_taxonomy(
    alpha_a: str, alpha_b: str, *, weight_a_to_b: float = 0.9, weight_b_to_a: float | None = None
) -> dict[str, AlphaDefinition]:
    """A minimal two-alpha taxonomy declaring exactly one bidirectional pair."""
    if weight_b_to_a is None:
        weight_b_to_a = weight_a_to_b
    return {
        alpha_a: fake_alpha(alpha_a, [ConflictAlpha(alpha_id=alpha_b, contradiction_weight=weight_a_to_b)]),
        alpha_b: fake_alpha(alpha_b, [ConflictAlpha(alpha_id=alpha_a, contradiction_weight=weight_b_to_a)]),
    }
