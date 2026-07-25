import inspect
import json
from pathlib import Path

import pytest

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.structure_engine import alpha_mapper
from comqutor_alpha.structure_engine.alpha_mapper import (
    factor_score,
    keyword_score,
    map_claim_to_alpha,
    save_alpha_matches,
)


GOLDEN_PATH = Path(__file__).parent / "golden_cases" / "labeled_claims_v1.json"


def _record(text, direction="positive", factors=None):
    return {
        "run_id": "run1",
        "ticker": "NVDA",
        "agent": "news_agent",
        "claim": text,
        "evidence": text,
        "entities": ["NVDA"],
        "factors": factors or [],
        "direction": direction,
        "confidence": 0.8,
        "source_agent_output_id": "run1:news_agent:news_report",
    }


def test_keyword_score_rewards_relevant_terms():
    taxonomy = load_alpha_taxonomy()
    score = keyword_score(
        "AI training demand is increasing as cloud providers buy more accelerators.",
        taxonomy["A101"],
    )

    assert score > 0.5


def test_factor_score_uses_structured_factors():
    taxonomy = load_alpha_taxonomy()
    record = _record("Demand is improving.", factors=["Valuation Risk"])

    assert factor_score(record, taxonomy["A304"]) == 1.0
    assert factor_score(record, taxonomy["A101"]) == 0.0


def test_factor_score_handles_ai_demand_alias_lowercase():
    """factor_score must normalize a raw "AI demand" alias in record["factors"]
    the same way it normalizes claim text, instead of silently dropping it
    because it does not exactly match the canonical "AI Demand" key.
    """
    taxonomy = load_alpha_taxonomy()
    record = _record("Demand is improving.", factors=["AI demand"])

    assert factor_score(record, taxonomy["A101"]) == 1.0


def test_factor_score_handles_artificial_intelligence_demand_alias():
    taxonomy = load_alpha_taxonomy()
    record = _record("Demand is improving.", factors=["artificial intelligence demand"])

    assert factor_score(record, taxonomy["A101"]) == 1.0


def test_clear_ai_demand_claim_maps_to_ai_expansion():
    result = map_claim_to_alpha(
        _record(
            "AI training demand is accelerating and GPU demand is rising for NVDA.",
            factors=["AI Demand", "GPU Demand"],
        )
    )

    assert result["match_status"] == "matched"
    assert result["matched_alpha"] == "A101"


def test_clear_valuation_risk_claim_maps_to_multiple_compression():
    result = map_claim_to_alpha(
        _record(
            "Rich valuation creates downside risk and could trigger multiple compression.",
            direction="negative",
            factors=["Valuation Risk"],
        )
    )

    assert result["match_status"] == "matched"
    assert result["matched_alpha"] == "A304"


def test_labeled_claim_accuracy_is_at_least_80_percent():
    """Official Week 2 gate: a claim only counts as correct when the mapper
    actually committed to a match (match_status == "matched") on the right
    alpha. Counting a claim as correct just because the right alpha happened
    to be the top candidate (even under no_match/ambiguous) would be too
    loose for the official gate, so that is tracked separately as a
    diagnostic-only metric below.
    """
    taxonomy = load_alpha_taxonomy()
    cases = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    strict_correct = 0
    top_candidate_correct = 0
    mismatches = []
    for case in cases:
        result = map_claim_to_alpha(
            _record(case["text"], direction=case.get("expected_direction", "unknown")),
            taxonomy,
        )
        top_candidate = result["candidate_scores"][0] if result["candidate_scores"] else None
        top_alpha = top_candidate["alpha_id"] if top_candidate else None
        is_strict_correct = (
            result["match_status"] == "matched"
            and result["matched_alpha"] == case["expected_alpha"]
        )
        if is_strict_correct:
            strict_correct += 1
        if case["expected_alpha"] == top_alpha:
            top_candidate_correct += 1
        if not is_strict_correct:
            mismatches.append(
                {
                    "id": case["id"],
                    "text": case["text"],
                    "expected_alpha": case["expected_alpha"],
                    "matched_alpha": result["matched_alpha"],
                    "match_status": result["match_status"],
                    "top_candidate": top_candidate,
                    "candidate_scores": result["candidate_scores"],
                }
            )

    strict_accuracy = strict_correct / len(cases)
    top_candidate_accuracy = top_candidate_correct / len(cases)  # diagnostic only, not the gate

    assert strict_accuracy >= 0.80, {
        "strict_accuracy": strict_accuracy,
        "top_candidate_accuracy": top_candidate_accuracy,
        "mismatches": mismatches,
    }


@pytest.mark.parametrize(
    ("text", "direction", "expected_alpha"),
    [
        ("GPU demand is increasing due to AI training.", "positive", "A101"),
        (
            "Enterprise AI applications are driving inference workloads.",
            "positive",
            "A102",
        ),
        ("Datacenter power and cooling demand is rising.", "positive", "A103"),
        (
            "Semiconductor inventory is improving and chip demand is recovering.",
            "positive",
            "A201",
        ),
        (
            "Revenue guidance was raised due to strong customer demand.",
            "positive",
            "A301",
        ),
        ("High valuation is creating downside risk.", "negative", "A304"),
        (
            "Credit spreads are widening and recession risk is rising.",
            "negative",
            "A501",
        ),
        (
            "AI stocks are rising due to strong investor attention.",
            "positive",
            "A601",
        ),
    ],
)
def test_development_plan_acceptance_sentence_maps_strictly(
    text, direction, expected_alpha
):
    result = map_claim_to_alpha(_record(text, direction=direction))

    assert result["match_status"] == "matched"
    assert result["matched_alpha"] == expected_alpha


def test_no_match_does_not_force_bad_alpha():
    result = map_claim_to_alpha(
        _record("The company signed an ordinary office lease with no market signal.")
    )

    assert result["match_status"] == "no_match"
    assert result["matched_alpha"] is None


def test_legacy_v1_identity_remains_traceable():
    record = _record(
        "AI training demand is accelerating and GPU demand is rising.",
        factors=["AI Demand", "GPU Demand"],
    )
    record.pop("source_agent_output_id")
    record["agent_output_id"] = "legacy_raw_output_id"

    result = map_claim_to_alpha(record)

    assert result["claim_id"] == "legacy_raw_output_id"
    assert result["source_agent_output_id"] == "legacy_raw_output_id"


def test_ambiguous_match_is_explicit():
    result = map_claim_to_alpha(
        _record(
            "AI training demand is rising, but rich valuation creates downside risk for NVDA.",
            direction="neutral",
            factors=["AI Demand", "Valuation Risk"],
        )
    )

    assert result["match_status"] == "ambiguous"
    assert result["matched_alpha"] is None
    assert len(result["candidate_scores"]) >= 2


def test_mapper_has_no_llm_network_or_tradingagents_dependency():
    source = inspect.getsource(alpha_mapper)

    assert "tradingagents" not in source.lower()
    assert "requests" not in source.lower()
    assert "socket" not in source.lower()


def test_save_alpha_matches_writes_week2_artifact(tmp_path):
    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    (run_dir / "structured_agent_outputs.json").write_text(
        json.dumps(
            {
                "schema_version": "week1a.structured_agent_outputs.v1",
                "run_id": "run1",
                "ticker": "NVDA",
                "records": [
                    _record(
                        "AI training demand is accelerating and GPU demand is rising.",
                        factors=["AI Demand", "GPU Demand"],
                    )
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = save_alpha_matches("run1", output_root=tmp_path)

    assert payload["schema_version"] == "week2.alpha_matches.v2"
    assert payload["matches"][0]["matched_alpha"] == "A101"
    assert (run_dir / "alpha_matches.json").exists()
