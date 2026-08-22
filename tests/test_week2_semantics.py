import json
import time

import pytest

from comqutor_alpha.structure_engine.alpha_mapper import (
    DEFAULT_CLASSIFIER_TIMEOUT_SECONDS,
    map_claim_to_alpha,
)


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


# These tests exercise the DETERMINISTIC scoring/semantics layer only (no
# classifier_enabled/llm_gateway): under Pure-LLM Alpha semantic authority,
# the top-level match_status/matched_alpha fields are now always an LLM-only
# result (here, always "unavailable"/None, since the classifier is never
# enabled) -- see tests/test_alpha_mapper_llm_authority.py for that
# contract. The deterministic conclusion these tests actually care about
# remains fully inspectable via deterministic_top_alpha/
# deterministic_match_status, which mirror matched_alpha/match_status's own
# shape and are computed by the same, unmodified deterministic scoring code.
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

    assert result["deterministic_match_status"] == "no_match"
    assert result["deterministic_top_alpha"] is None
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

    assert result["deterministic_match_status"] == "matched"
    assert result["deterministic_top_alpha"] == "A501"
    assert result["semantic_polarity"] == "risk_relief"
    assert result["candidate_scores"][0]["relation"] == "risk_relief"


def test_negated_activation_is_not_forced_into_alpha():
    result = map_claim_to_alpha(
        _record(
            "There is no evidence that inference demand is increasing.",
            factors=["Inference Demand"],
        )
    )

    assert result["deterministic_match_status"] == "no_match"
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

    assert result["deterministic_match_status"] == "matched"
    assert result["deterministic_top_alpha"] == "A001"
    assert result["assertion_status"] == "conditional"
    assert result["candidate_scores"][0]["relation"] == "conditional"


def test_mixed_claim_is_ambiguous_and_retains_bounded_candidates():
    result = map_claim_to_alpha(
        _record(
            "AI training demand is rising, but rich valuation creates downside risk.",
            factors=["AI Demand", "Valuation Risk"],
        )
    )

    assert result["deterministic_match_status"] == "ambiguous"
    assert result["deterministic_top_alpha"] is None
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

    assert result["deterministic_match_status"] == "matched"
    assert result["deterministic_top_alpha"] in {"A101", "A103", "A301"}
    # secondary_alphas is computed from deterministic candidates before the
    # LLM outcome is ever applied, so it is unaffected by classifier_enabled.
    assert result["secondary_alphas"]


def test_technical_taxonomy_gap_remains_no_match():
    result = map_claim_to_alpha(
        _record("The 200-day SMA is acting as technical support.", direction="positive")
    )

    assert result["deterministic_match_status"] == "no_match"
    assert result["taxonomy_gap_context"] == "technical_market_state"


def _ambiguous_record():
    return _record(
        "AI training demand is rising, but rich valuation creates downside risk.",
        factors=["AI Demand", "Valuation Risk"],
    )


def test_optional_classifier_receives_full_taxonomy_not_restricted_candidates():
    """Pure-LLM Alpha semantic authority: the classifier request must carry
    the FULL canonical taxonomy (every Alpha, unrestricted), never a
    deterministically pre-admitted candidate subset -- see
    tests/test_alpha_mapper_llm_authority.py for the full acceptance suite.
    """
    seen = {}

    def classifier(request, *, timeout_seconds):
        seen.update(request)
        assert timeout_seconds == 2.0
        return {"outcome": "selected", "alpha_id": "A101"}

    result = map_claim_to_alpha(
        _ambiguous_record(),
        classifier=classifier,
        classifier_enabled=True,
        classifier_timeout_seconds=2.0,
    )

    assert "allowed_alpha_ids" not in seen
    assert "candidates" not in seen
    taxonomy_ids = {item["alpha_id"] for item in seen["alpha_taxonomy"]}
    assert taxonomy_ids == {
        "A001", "A003", "A101", "A102", "A103", "A201", "A301", "A304", "A501", "A601",
    }
    assert all(item["alpha_name"] and item["definition"] for item in seen["alpha_taxonomy"])
    assert seen["evidence"]
    assert seen["ticker"] == "NVDA"
    assert set(seen["factors"]) == {"AI Demand", "Valuation Risk"}
    assert result["match_status"] == "matched"
    assert result["matched_alpha"] == "A101"
    assert result["alpha_match_method"] == "llm"
    assert result["alpha_match_fallback_reason"] is None
    matched = next(item for item in result["candidate_scores"] if item["alpha_id"] == "A101")
    assert result["score"] == matched["score"]
    assert result["factor_score"] == matched["factor_score"]
    assert result["classifier"] == {"enabled": True, "used": True, "status": "llm_selected"}


def test_optional_classifier_malformed_response_falls_unavailable_without_leaking_response():
    def classifier(_request, *, timeout_seconds):
        del timeout_seconds
        return {
            "outcome": "selected",
            "alpha_id": "A999",
            "hidden_reasoning": "secret-provider-response",
        }

    result = map_claim_to_alpha(
        _ambiguous_record(), classifier=classifier, classifier_enabled=True
    )

    assert result["match_status"] == "unavailable"
    assert result["matched_alpha"] is None
    assert result["alpha_match_method"] == "llm_unavailable"
    assert result["classifier"]["status"] == "invalid_output"
    assert "secret-provider-response" not in json.dumps(result)


def test_optional_classifier_timeout_falls_unavailable_safely():
    def classifier(_request, *, timeout_seconds):
        del timeout_seconds
        raise TimeoutError("provider timeout with sensitive details")

    result = map_claim_to_alpha(
        _ambiguous_record(), classifier=classifier, classifier_enabled=True
    )

    assert result["match_status"] == "unavailable"
    assert result["matched_alpha"] is None
    assert result["alpha_match_method"] == "llm_unavailable"
    assert result["classifier"]["status"] == "provider_timeout"
    assert "sensitive details" not in json.dumps(result)


def test_classifier_is_disabled_by_default():
    calls = []

    def classifier(_request, *, timeout_seconds):
        calls.append(timeout_seconds)
        return {"outcome": "selected", "alpha_id": "A101"}

    result = map_claim_to_alpha(_ambiguous_record(), classifier=classifier)

    assert calls == []
    assert result["match_status"] == "unavailable"
    assert result["matched_alpha"] is None
    assert result["alpha_match_method"] == "llm_unavailable"
    assert result["alpha_match_fallback_reason"] == "disabled"
    assert result["classifier"]["status"] == "disabled"
    # The deterministic conclusion (ambiguous, per the shared fixture claim)
    # remains fully inspectable even though the classifier never ran.
    assert result["deterministic_match_status"] == "ambiguous"


def test_classifier_is_consulted_even_on_deterministic_no_match():
    """Pure-LLM Alpha semantic authority (core acceptance criterion): the
    LLM must be consulted -- and its valid selection applied -- even when
    deterministic candidate generation alone would have concluded
    "no_match". See tests/test_alpha_mapper_llm_authority.py for the
    canonical, more complete version of this same acceptance criterion
    using the llm_gateway integration path.
    """
    calls = []

    def classifier(_request, *, timeout_seconds):
        calls.append(timeout_seconds)
        return {"outcome": "selected", "alpha_id": "A101"}

    result = map_claim_to_alpha(
        _record(
            "Hyperscalers are building custom silicon to reduce dependency on NVIDIA.",
            factors=["AI Demand"],
        ),
        classifier=classifier,
        classifier_enabled=True,
    )

    assert calls == [DEFAULT_CLASSIFIER_TIMEOUT_SECONDS]
    assert result["match_status"] == "matched"
    assert result["matched_alpha"] == "A101"
    assert result["alpha_match_method"] == "llm"
    assert result["classifier"]["status"] == "llm_selected"
    assert result["deterministic_match_status"] == "no_match"


def test_mapper_uses_evidence_and_preserves_top_three_contract():
    record = _record("Management discussed demand conditions.")
    record["evidence"] = (
        "AI training demand is accelerating and cloud providers are buying more GPUs."
    )

    result = map_claim_to_alpha(record)

    assert result["deterministic_match_status"] == "matched"
    assert result["deterministic_top_alpha"] == "A101"
    assert result["evidence"] == record["evidence"]
    assert 1 <= len(result["top_candidates"]) <= 3
    assert result["top_candidates"] == result["candidate_scores"][:3]
    assert result["top_candidates"][0]["matched_keywords"]


def test_injected_classifier_has_a_real_caller_side_timeout():
    def classifier(_request, *, timeout_seconds):
        del timeout_seconds
        time.sleep(0.2)
        return {"outcome": "selected", "alpha_id": "A101"}

    started = time.monotonic()
    result = map_claim_to_alpha(
        _ambiguous_record(),
        classifier=classifier,
        classifier_enabled=True,
        classifier_timeout_seconds=0.02,
    )

    assert result["match_status"] == "unavailable"
    assert result["matched_alpha"] is None
    assert result["classifier"]["status"] == "provider_timeout"
    assert time.monotonic() - started < 0.15
