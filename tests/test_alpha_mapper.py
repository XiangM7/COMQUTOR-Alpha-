import inspect
import json
from pathlib import Path

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
    taxonomy = load_alpha_taxonomy()
    cases = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    correct = 0
    mismatches = []
    for case in cases:
        result = map_claim_to_alpha(
            _record(case["text"], direction=case.get("expected_direction", "unknown")),
            taxonomy,
        )
        top_alpha = result["candidate_scores"][0]["alpha_id"] if result["candidate_scores"] else None
        if case["expected_alpha"] in {result["matched_alpha"], top_alpha}:
            correct += 1
        else:
            mismatches.append(
                {
                    "id": case["id"],
                    "expected": case["expected_alpha"],
                    "matched": result["matched_alpha"],
                    "top": top_alpha,
                    "status": result["match_status"],
                }
            )

    accuracy = correct / len(cases)
    assert accuracy >= 0.80, {"accuracy": accuracy, "mismatches": mismatches}


def test_no_match_does_not_force_bad_alpha():
    result = map_claim_to_alpha(
        _record("The company signed an ordinary office lease with no market signal.")
    )

    assert result["match_status"] == "no_match"
    assert result["matched_alpha"] is None


def test_ambiguous_match_is_explicit():
    result = map_claim_to_alpha(
        _record(
            "AI demand is strong, but rich valuation creates downside risk for NVDA.",
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

    assert payload["schema_version"] == "week2.alpha_matches.v1"
    assert payload["matches"][0]["matched_alpha"] == "A101"
    assert (run_dir / "alpha_matches.json").exists()
