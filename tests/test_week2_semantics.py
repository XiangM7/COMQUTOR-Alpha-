import json

import pytest

from comqutor_alpha.structure_engine.alpha_mapper import map_claim_to_alpha


def _record(text, *, factors=None, direction="neutral"):
    return {
        "run_id": "run1",
        "ticker": "NVDA",
        "agent": "news_agent",
        "claim": text,
        "evidence": text,
        "factors": factors or [],
        "direction": direction,
        "confidence": 0.8,
        "source_agent_output_id": "run1:news_agent:news_report",
    }


@pytest.mark.parametrize(
    ("text", "factors"),
    [
        (
            "Etched is a niche competitor and not an immediate threat to NVIDIA AI inference.",
            ["Inference Demand"],
        ),
        (
            "Hyperscalers are building custom silicon to reduce dependency on NVIDIA over time.",
            ["AI Demand"],
        ),
        (
            "An alternative accelerator could substitute for NVIDIA GPUs in this workload.",
            ["GPU Demand"],
        ),
    ],
)
def test_competition_and_substitution_do_not_force_ai_alpha(text, factors):
    result = map_claim_to_alpha(_record(text, factors=factors, direction="negative"))

    assert result["match_status"] == "no_match"
    assert result["matched_alpha"] is None
    assert result["taxonomy_gap_context"] == "competition_or_substitution"
    assert not {"A101", "A102"}.intersection(result["plausible_alphas"])


def test_low_and_falling_recession_risk_is_risk_relief():
    result = map_claim_to_alpha(
        _record(
            "Recession risk is low and falling as credit spreads tighten.",
            factors=["Recession Risk"],
            direction="positive",
        )
    )

    assert result["match_status"] == "matched"
    assert result["matched_alpha"] == "A501"
    assert result["semantic_polarity"] == "risk_relief"
    assert result["candidate_scores"][0]["relation"] == "risk_relief"


def test_negated_activation_is_not_forced_into_alpha():
    result = map_claim_to_alpha(
        _record(
            "There is no evidence that inference demand is increasing.",
            factors=["Inference Demand"],
        )
    )

    assert result["match_status"] == "no_match"
    assert result["assertion_status"] == "negated"
    assert result["semantic_polarity"] == "mention"


def test_conditional_claim_preserves_conditional_status():
    result = map_claim_to_alpha(
        _record(
            "If inflation softens, the Fed could cut rates and growth multiples may expand.",
            factors=["Rate Cut Cycle"],
            direction="positive",
        )
    )

    assert result["match_status"] == "matched"
    assert result["matched_alpha"] == "A001"
    assert result["assertion_status"] == "conditional"
    assert result["candidate_scores"][0]["relation"] == "conditional"


def test_mixed_claim_is_ambiguous_and_retains_bounded_candidates():
    result = map_claim_to_alpha(
        _record(
            "AI demand is strong, but rich valuation creates downside risk.",
            factors=["AI Demand", "Valuation Risk"],
        )
    )

    assert result["match_status"] == "ambiguous"
    assert result["matched_alpha"] is None
    assert {"A101", "A304"}.issubset(result["plausible_alphas"])
    assert len(result["eligible_candidates"]) <= 3


def test_supportive_multi_alpha_claim_keeps_secondary_without_forcing_ambiguity():
    result = map_claim_to_alpha(
        _record(
            "AI infrastructure spending drives GPU demand and supports revenue growth.",
            factors=["AI Infrastructure", "GPU Demand", "Revenue Growth"],
            direction="positive",
        )
    )

    assert result["match_status"] == "matched"
    assert result["matched_alpha"] in {"A101", "A103", "A301"}
    assert result["secondary_alphas"]


def test_technical_taxonomy_gap_remains_no_match():
    result = map_claim_to_alpha(
        _record("The 200-day SMA is acting as technical support.", direction="positive")
    )

    assert result["match_status"] == "no_match"
    assert result["taxonomy_gap_context"] == "technical_market_state"


def _ambiguous_record():
    return _record(
        "AI demand is strong, but rich valuation creates downside risk.",
        factors=["AI Demand", "Valuation Risk"],
    )


def test_optional_classifier_can_choose_only_from_deterministic_candidates():
    seen = {}

    def classifier(request, *, timeout_seconds):
        seen.update(request)
        assert timeout_seconds == 2.0
        return {"match_status": "matched", "alpha_id": "A101"}

    result = map_claim_to_alpha(
        _ambiguous_record(),
        classifier=classifier,
        classifier_enabled=True,
        classifier_timeout_seconds=2.0,
    )

    assert set(seen["allowed_alpha_ids"]) == {"A101", "A304"}
    assert result["match_status"] == "matched"
    assert result["matched_alpha"] == "A101"
    selected = next(
        item for item in result["eligible_candidates"] if item["alpha_id"] == "A101"
    )
    assert result["score"] == selected["score"]
    assert result["factor_score"] == selected["factor_score"]
    assert result["classifier"] == {"enabled": True, "used": True, "status": "applied"}


def test_optional_classifier_illegal_alpha_falls_back_without_leaking_response():
    def classifier(_request, *, timeout_seconds):
        del timeout_seconds
        return {
            "match_status": "matched",
            "alpha_id": "A999",
            "hidden_reasoning": "secret-provider-response",
        }

    result = map_claim_to_alpha(
        _ambiguous_record(), classifier=classifier, classifier_enabled=True
    )

    assert result["match_status"] == "ambiguous"
    assert result["matched_alpha"] is None
    assert result["classifier"]["status"] == "invalid_output"
    assert "secret-provider-response" not in json.dumps(result)


def test_optional_classifier_timeout_falls_back_safely():
    def classifier(_request, *, timeout_seconds):
        del timeout_seconds
        raise TimeoutError("provider timeout with sensitive details")

    result = map_claim_to_alpha(
        _ambiguous_record(), classifier=classifier, classifier_enabled=True
    )

    assert result["match_status"] == "ambiguous"
    assert result["classifier"]["status"] == "timeout"
    assert "sensitive details" not in json.dumps(result)


def test_classifier_is_disabled_by_default():
    calls = []

    def classifier(_request, *, timeout_seconds):
        calls.append(timeout_seconds)
        return {"match_status": "matched", "alpha_id": "A101"}

    result = map_claim_to_alpha(_ambiguous_record(), classifier=classifier)

    assert calls == []
    assert result["match_status"] == "ambiguous"
    assert result["classifier"]["status"] == "disabled"


def test_classifier_cannot_bypass_deterministic_no_match():
    calls = []

    def classifier(_request, *, timeout_seconds):
        calls.append(timeout_seconds)
        return {"match_status": "matched", "alpha_id": "A101"}

    result = map_claim_to_alpha(
        _record(
            "Hyperscalers are building custom silicon to reduce dependency on NVIDIA.",
            factors=["AI Demand"],
        ),
        classifier=classifier,
        classifier_enabled=True,
    )

    assert calls == []
    assert result["match_status"] == "no_match"
    assert result["classifier"]["status"] == "blocked_by_deterministic_no_match"
