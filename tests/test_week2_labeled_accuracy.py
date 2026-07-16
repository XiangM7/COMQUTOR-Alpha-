"""Standalone Formal Week 2 accuracy gate over the approved labeled set."""

from __future__ import annotations

import json
from pathlib import Path

from comqutor_alpha.structure_engine.alpha_mapper import map_claim_to_alpha

LABELED_CASES_PATH = Path(__file__).parent / "golden_cases" / "labeled_claims_v1.json"


def measure_labeled_accuracy():
    cases = json.loads(LABELED_CASES_PATH.read_text(encoding="utf-8"))
    results = []
    for case in cases:
        record = {
            "run_id": "week2_labeled_gate",
            "ticker": "NVDA",
            "agent": "news_agent",
            "claim": case["text"],
            "evidence": case["text"],
            "entities": ["NVDA"],
            "factors": [],
            "direction": case.get("expected_direction", "unknown"),
            "confidence": 0.8,
            "source_agent_output_id": f"week2:{case['id']}",
        }
        mapped = map_claim_to_alpha(record)
        correct = (
            mapped["match_status"] == "matched"
            and mapped["matched_alpha"] == case["expected_alpha"]
        )
        results.append(
            {
                "id": case["id"],
                "expected_alpha": case["expected_alpha"],
                "actual_status": mapped["match_status"],
                "actual_alpha": mapped["matched_alpha"],
                "correct": correct,
                "top_candidates": mapped["candidate_scores"][:3],
            }
        )
    correct_count = sum(item["correct"] for item in results)
    return {
        "case_count": len(results),
        "correct_count": correct_count,
        "accuracy": correct_count / len(results),
        "mismatches": [item for item in results if not item["correct"]],
    }


def test_approved_labeled_claim_accuracy_is_at_least_80_percent():
    metrics = measure_labeled_accuracy()
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    assert metrics["case_count"] == 20
    assert metrics["accuracy"] >= 0.80, metrics
