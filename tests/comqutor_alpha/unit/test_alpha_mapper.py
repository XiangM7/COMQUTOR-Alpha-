from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid5

import pytest
import yaml

from comqutor_alpha.alpha_library import load_taxonomy
from comqutor_alpha.structure_engine.alpha_mapper import AlphaMapper, evaluate_mapper_cases
from comqutor_alpha.structure_engine.structure_schema import (
    AgentType,
    Claim,
    Direction,
    SourceType,
)

RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
CLAIM_NAMESPACE = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
CASES_PATH = Path(__file__).parents[1] / "golden_cases/labeled_claims_v1.yaml"


def _claim(text: str, case_id: str, factors=()) -> Claim:
    return Claim(
        claim_id=uuid5(CLAIM_NAMESPACE, case_id),
        run_id=RUN_ID,
        ticker="NVDA",
        agent=AgentType.NEWS,
        claim=text,
        evidence=f"The source report provides evidence for this observation: {text}",
        entities=["NVDA"],
        factors=list(factors),
        direction=Direction.POSITIVE,
        confidence=0.8,
        source_type=SourceType.NEWS,
        source_refs=[f"fixture:{case_id}"],
        extraction_method="golden_fixture",
    )


@pytest.mark.golden
def test_development_plan_acceptance_sentences_exceed_accuracy_gate() -> None:
    raw = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))
    reviewed = [case for case in raw["cases"] if case["review_status"] == "reviewed"]
    cases = [
        (case["case_id"], _claim(case["claim"], case["case_id"]), case["expected_alpha_ids"])
        for case in reviewed
    ]
    evaluation = evaluate_mapper_cases(AlphaMapper(load_taxonomy()), cases)
    assert evaluation.reviewed_count == 8
    assert evaluation.top3_accuracy >= 0.80, evaluation.errors
    assert evaluation.top3_accuracy == 1.0
    assert evaluation.abstention_rate == 0.0
    assert evaluation.errors == ()


@pytest.mark.unit
def test_unrelated_claim_abstains_instead_of_forcing_match() -> None:
    claim = _claim("The company changed the color of its employee badges.", "unrelated")
    assert AlphaMapper(load_taxonomy()).map_claim(claim) == ()


class FuzzyClassifier:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def classify(self, claim, candidate_alpha_ids):
        self.calls.append((claim.claim_id, tuple(candidate_alpha_ids)))
        if self.fail:
            raise TimeoutError("classifier unavailable")
        return {alpha_id: 0.8 if alpha_id == "A001" else 0.0 for alpha_id in candidate_alpha_ids}


@pytest.mark.unit
def test_classifier_is_only_used_for_fuzzy_interval_and_failure_abstains() -> None:
    fuzzy_claim = _claim("Duration remains important.", "fuzzy")
    classifier = FuzzyClassifier()
    matches = AlphaMapper(load_taxonomy(), classifier=classifier).map_claim(fuzzy_claim)
    assert classifier.calls
    assert matches[0].alpha_id == "A001"
    assert matches[0].method.value == "llm_classifier"

    failed = FuzzyClassifier(fail=True)
    assert AlphaMapper(load_taxonomy(), classifier=failed).map_claim(fuzzy_claim) == ()
    assert len(failed.calls) == 1

    strong_claim = _claim("AI training is driving GPU demand.", "strong")
    no_call = FuzzyClassifier()
    result = AlphaMapper(load_taxonomy(), classifier=no_call).map_claim(strong_claim)
    assert result[0].alpha_id == "A101"
    assert no_call.calls == []


@pytest.mark.unit
def test_mapping_is_deterministic_and_score_components_are_preserved() -> None:
    mapper = AlphaMapper(load_taxonomy())
    claim = _claim(
        "Revenue growth followed strong demand and guidance raised.",
        "revenue",
        factors=["revenue growth", "customer demand"],
    )
    first = mapper.map_claim(claim)
    second = mapper.map_claim(claim)
    assert first == second
    assert first[0].alpha_id == "A301"
    assert first[0].match_score == first[0].components.combined_score
    assert 0 <= first[0].components.keyword_score <= 1
