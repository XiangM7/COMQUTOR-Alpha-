"""Taxonomy-bounded structural conflict arbitration."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from comqutor_alpha.alpha_library.alpha_loader import AlphaTaxonomy
from comqutor_alpha.structure_engine.structure_schema import (
    ActivationBreakdown,
    AlphaMatch,
    Claim,
    ConflictComponentBreakdown,
    ConflictLevel,
    ConflictResult,
    Direction,
)


def conflict_level(score: float) -> ConflictLevel:
    if score <= 25:
        return ConflictLevel.LOW
    if score <= 50:
        return ConflictLevel.MEDIUM
    if score <= 75:
        return ConflictLevel.MEDIUM_HIGH
    return ConflictLevel.HIGH


class ConflictDetector:
    def detect(
        self,
        *,
        taxonomy: AlphaTaxonomy,
        activations: Sequence[ActivationBreakdown],
        matches: Sequence[AlphaMatch],
        claims: Mapping[object, Claim],
    ) -> tuple[ConflictResult, ...]:
        by_alpha = {activation.alpha_id: activation for activation in activations}
        match_scores: dict[str, list[float]] = {}
        for match in matches:
            claim = claims.get(match.claim_id)
            if claim is not None and claim.evidence.strip():
                match_scores.setdefault(match.alpha_id, []).append(match.match_score)

        results: list[ConflictResult] = []
        for alpha_a, alpha_b, definition in taxonomy.conflict_pairs():
            activation_a = by_alpha.get(alpha_a)
            activation_b = by_alpha.get(alpha_b)
            if activation_a is None or activation_b is None:
                continue
            if not activation_a.evidence_references or not activation_b.evidence_references:
                continue
            if {activation_a.direction, activation_b.direction} != {
                Direction.POSITIVE,
                Direction.NEGATIVE,
            }:
                continue
            scores_a = match_scores.get(alpha_a, [])
            scores_b = match_scores.get(alpha_b, [])
            if not scores_a or not scores_b:
                continue
            strength_a = sum(scores_a) / len(scores_a)
            strength_b = sum(scores_b) / len(scores_b)
            evidence_strength = (strength_a + strength_b) / 2
            minimum = min(activation_a.final_score, activation_b.final_score)
            score = minimum * definition.contradiction_weight * evidence_strength
            bull = activation_a if activation_a.direction == Direction.POSITIVE else activation_b
            bear = activation_b if activation_b.direction == Direction.NEGATIVE else activation_a
            bull_definition = taxonomy.get(bull.alpha_id)
            bear_definition = taxonomy.get(bear.alpha_id)
            results.append(
                ConflictResult(
                    alpha_a=alpha_a,
                    alpha_b=alpha_b,
                    bull_structure=f"{bull.alpha_id} {bull_definition.name_en}",
                    bear_structure=f"{bear.alpha_id} {bear_definition.name_en}",
                    bull_evidence=bull.evidence_references,
                    bear_evidence=bear.evidence_references,
                    contradiction_weight=definition.contradiction_weight,
                    evidence_strength=evidence_strength,
                    components=ConflictComponentBreakdown(
                        minimum_activation=minimum,
                        contradiction_weight=definition.contradiction_weight,
                        evidence_strength=evidence_strength,
                    ),
                    score=score,
                    level=conflict_level(score),
                    explanation=(
                        f"{bull_definition.name_en} has supporting evidence while "
                        f"{bear_definition.name_en} supplies the opposing structural risk."
                    ),
                )
            )
        return tuple(sorted(results, key=lambda item: (-item.score, item.alpha_a, item.alpha_b)))
