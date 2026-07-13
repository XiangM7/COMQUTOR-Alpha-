"""Deterministic, evidence-deduplicated MVP Activation scoring."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

from comqutor_alpha.alpha_library.alpha_loader import AlphaTaxonomy
from comqutor_alpha.structure_engine.normalization import normalize_text
from comqutor_alpha.structure_engine.structure_schema import (
    ActivationBreakdown,
    ActivationStatus,
    AlphaMatch,
    Claim,
    Direction,
    ScoreComponent,
    StructureGraph,
)

WEIGHTS = {
    "matched_evidence": 0.35,
    "agent_agreement": 0.20,
    "graph_coherence": 0.25,
    "recency": 0.10,
    "direction_strength": 0.10,
}


def activation_status(score: float) -> ActivationStatus:
    if score <= 30:
        return ActivationStatus.INACTIVE
    if score <= 50:
        return ActivationStatus.WATCH
    if score <= 70:
        return ActivationStatus.ACTIVE
    if score <= 85:
        return ActivationStatus.DOMINANT
    return ActivationStatus.REGIME_LEVEL


def _recency_score(analysis_date: date, as_of: date) -> float:
    age = max(0, (as_of - analysis_date).days)
    if age <= 1:
        return 100.0
    if age <= 7:
        return 80.0
    if age <= 30:
        return 50.0
    return 20.0


def _component(raw: float, weight: float) -> ScoreComponent:
    bounded = max(0.0, min(100.0, raw))
    return ScoreComponent(
        raw_value=bounded,
        weight=weight,
        contribution=bounded * weight,
    )


class ActivationScorer:
    def score(
        self,
        *,
        taxonomy: AlphaTaxonomy,
        matches: Sequence[AlphaMatch],
        claims: Mapping[object, Claim],
        graph: StructureGraph,
        analysis_date: date,
        as_of: date,
    ) -> tuple[ActivationBreakdown, ...]:
        results: list[ActivationBreakdown] = []
        graph_alpha_ids = {alpha for node in graph.nodes for alpha in node.alpha_ids}
        for alpha in taxonomy.alphas:
            alpha_matches = sorted(
                (match for match in matches if match.alpha_id == alpha.alpha_id),
                key=lambda match: (str(match.claim_id), -match.match_score),
            )
            valid = [(match, claims.get(match.claim_id)) for match in alpha_matches]
            valid = [(match, claim) for match, claim in valid if claim is not None]
            evidence_refs = sorted({match.evidence_reference for match, _claim in valid})
            if not valid or not evidence_refs:
                zero_components = {
                    name: _component(0.0, weight) for name, weight in WEIGHTS.items()
                }
                results.append(
                    ActivationBreakdown(
                        alpha_id=alpha.alpha_id,
                        components=zero_components,
                        final_score=0.0,
                        status=ActivationStatus.INACTIVE,
                        direction=Direction.UNKNOWN,
                        evidence_references=[],
                    )
                )
                continue

            # Same-origin evidence is counted once even when several agents repeat it.
            independent: dict[str, tuple[AlphaMatch, Claim]] = {}
            for match, claim in valid:
                signature = normalize_text(claim.evidence)
                existing = independent.get(signature)
                if existing is None or match.match_score > existing[0].match_score:
                    independent[signature] = (match, claim)
            independent_values = list(independent.values())
            matched_evidence = (
                sum(match.match_score for match, _claim in independent_values)
                / len(independent_values)
                * 100
            )
            agents = {claim.agent for _match, claim in independent_values}
            agent_agreement = len(agents) / 4 * 100
            graph_coherence = (
                graph.graph_coherence_score if alpha.alpha_id in graph_alpha_ids else 0.0
            )
            recency = _recency_score(analysis_date, as_of)
            direction_value = 0.0
            for _match, claim in independent_values:
                sign = 1 if claim.direction == Direction.POSITIVE else -1 if claim.direction == Direction.NEGATIVE else 0
                direction_value += sign * claim.confidence
            direction_strength = abs(direction_value) / len(independent_values) * 100
            direction = (
                Direction.POSITIVE
                if direction_value > 0
                else Direction.NEGATIVE
                if direction_value < 0
                else Direction.NEUTRAL
            )
            raw_values = {
                "matched_evidence": matched_evidence,
                "agent_agreement": agent_agreement,
                "graph_coherence": graph_coherence,
                "recency": recency,
                "direction_strength": direction_strength,
            }
            components = {
                name: _component(raw_values[name], weight) for name, weight in WEIGHTS.items()
            }
            final_score = sum(component.contribution for component in components.values())
            results.append(
                ActivationBreakdown(
                    alpha_id=alpha.alpha_id,
                    components=components,
                    final_score=final_score,
                    status=activation_status(final_score),
                    direction=direction,
                    evidence_references=evidence_refs,
                )
            )
        return tuple(sorted(results, key=lambda result: result.alpha_id))
