"""Deterministic-first Claim-to-Alpha mapping with optional fuzzy classifier."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid5

from comqutor_alpha.alpha_library.alpha_loader import AlphaTaxonomy
from comqutor_alpha.alpha_library.alpha_schema import AlphaDefinition
from comqutor_alpha.structure_engine.normalization import normalize_text, phrase_matches
from comqutor_alpha.structure_engine.structure_schema import (
    AlphaMatch,
    Claim,
    MatchComponentBreakdown,
    MatchMethod,
)

MATCH_ID_NAMESPACE = UUID("dca4d7b8-a4d2-4b84-92bb-b51522d1013a")


class AlphaClassifier(Protocol):
    def classify(self, claim: Claim, candidate_alpha_ids: Sequence[str]) -> Mapping[str, float]: ...


@dataclass(frozen=True, slots=True)
class _CandidateScore:
    alpha: AlphaDefinition
    keyword_score: float
    factor_score: float
    deterministic_score: float


@dataclass(frozen=True, slots=True)
class MappingEvaluation:
    reviewed_count: int
    correct_top1: int
    correct_top3: int
    abstentions: int
    errors: tuple[str, ...]

    @property
    def top1_accuracy(self) -> float:
        return self.correct_top1 / self.reviewed_count if self.reviewed_count else 0.0

    @property
    def top3_accuracy(self) -> float:
        return self.correct_top3 / self.reviewed_count if self.reviewed_count else 0.0

    @property
    def abstention_rate(self) -> float:
        return self.abstentions / self.reviewed_count if self.reviewed_count else 0.0


class AlphaMapper:
    def __init__(
        self,
        taxonomy: AlphaTaxonomy,
        *,
        classifier: AlphaClassifier | None = None,
        threshold: float = 0.35,
        fuzzy_lower: float = 0.20,
        top_k: int = 3,
    ):
        if not 0 <= fuzzy_lower <= threshold <= 1:
            raise ValueError("require 0 <= fuzzy_lower <= threshold <= 1")
        if top_k < 1:
            raise ValueError("top_k must be positive")
        self.taxonomy = taxonomy
        self.classifier = classifier
        self.threshold = threshold
        self.fuzzy_lower = fuzzy_lower
        self.top_k = top_k

    @staticmethod
    def _phrase_score(text: str, phrases: Sequence[str]) -> float:
        hits: list[float] = []
        for phrase in phrases:
            if phrase_matches(text, phrase):
                words = len(normalize_text(phrase).split())
                hits.append(0.35 if words == 1 else min(1.0, 0.55 + 0.2 * words))
        if not hits:
            return 0.0
        # Multiple independent hits are stronger than one generic token.  The
        # 0.15 increment lets two corroborating one-word terms (for example,
        # "datacenter" + "cooling") reach the public 0.35 combined threshold
        # without lowering that threshold or adding sentence-specific rules.
        return min(1.0, max(hits) + 0.15 * (len(hits) - 1))

    def _score(self, claim: Claim, alpha: AlphaDefinition) -> _CandidateScore:
        combined_text = " ".join((claim.claim, claim.evidence, *claim.factors))
        keyword = self._phrase_score(combined_text, alpha.keywords)
        factor_text = " ".join(claim.factors)
        factor_phrases = (*alpha.keywords, *alpha.trigger_signals, *alpha.confirmation_signals)
        factor = self._phrase_score(factor_text, factor_phrases) if factor_text else 0.0
        combined = min(1.0, keyword * 0.7 + factor * 0.3)
        return _CandidateScore(alpha, keyword, factor, combined)

    @staticmethod
    def _match_id(claim_id: UUID, alpha_id: str) -> UUID:
        return uuid5(MATCH_ID_NAMESPACE, f"{claim_id}|{alpha_id}")

    def map_claim(self, claim: Claim) -> tuple[AlphaMatch, ...]:
        candidates = [self._score(claim, alpha) for alpha in self.taxonomy.alphas]
        classifier_scores: Mapping[str, float] = {}
        fuzzy_ids = sorted(
            candidate.alpha.alpha_id
            for candidate in candidates
            if self.fuzzy_lower <= candidate.deterministic_score < self.threshold
        )
        if fuzzy_ids and self.classifier is not None:
            try:
                raw_scores = self.classifier.classify(claim, fuzzy_ids)
                classifier_scores = {
                    alpha_id: float(score)
                    for alpha_id, score in raw_scores.items()
                    if alpha_id in fuzzy_ids and 0 <= float(score) <= 1
                }
            except Exception:
                classifier_scores = {}

        matches: list[AlphaMatch] = []
        for candidate in candidates:
            llm_score = classifier_scores.get(candidate.alpha.alpha_id)
            final_score = max(candidate.deterministic_score, llm_score or 0.0)
            if final_score < self.threshold:
                continue
            method = (
                MatchMethod.LLM_CLASSIFIER
                if llm_score is not None and llm_score >= candidate.deterministic_score
                else MatchMethod.KEYWORD_FACTOR
            )
            matches.append(
                AlphaMatch(
                    match_id=self._match_id(claim.claim_id, candidate.alpha.alpha_id),
                    claim_id=claim.claim_id,
                    evidence_reference=f"claim:{claim.claim_id}",
                    alpha_id=candidate.alpha.alpha_id,
                    direction=claim.direction,
                    match_score=final_score,
                    method=method,
                    components=MatchComponentBreakdown(
                        keyword_score=candidate.keyword_score,
                        factor_score=candidate.factor_score,
                        llm_score=llm_score,
                        combined_score=final_score,
                    ),
                )
            )
        matches.sort(key=lambda match: (-match.match_score, match.alpha_id))
        return tuple(matches[: self.top_k])

    def map_claims(self, claims: Sequence[Claim]) -> tuple[AlphaMatch, ...]:
        matches = [match for claim in claims for match in self.map_claim(claim)]
        return tuple(sorted(matches, key=lambda match: (str(match.claim_id), -match.match_score, match.alpha_id)))


def evaluate_mapper_cases(
    mapper: AlphaMapper,
    cases: Sequence[tuple[str, Claim, Sequence[str]]],
) -> MappingEvaluation:
    top1 = 0
    top3 = 0
    abstentions = 0
    errors: list[str] = []
    for case_id, claim, expected in cases:
        matches = mapper.map_claim(claim)
        actual = [match.alpha_id for match in matches]
        expected_set = set(expected)
        if not actual:
            abstentions += 1
        if actual and actual[0] in expected_set:
            top1 += 1
        if expected_set & set(actual[:3]):
            top3 += 1
        else:
            errors.append(f"{case_id}: expected={sorted(expected_set)}, actual={actual}")
    return MappingEvaluation(len(cases), top1, top3, abstentions, tuple(errors))
