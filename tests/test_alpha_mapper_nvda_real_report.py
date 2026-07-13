"""Robustness test for real NVDA TradingAgents report claims.

Copy `nvda_real_report_labeled_claims_v1.json` to:
    tests/golden_cases/nvda_real_report_labeled_claims_v1.json

Copy this file to:
    tests/test_alpha_mapper_nvda_real_report.py

Run diagnostic mode:
    python -m pytest tests/test_alpha_mapper_nvda_real_report.py -q -s

Optional enforced gate:
    COMQUTOR_ENFORCE_REAL_NVDA_GATE=1 \
    COMQUTOR_REAL_NVDA_MIN_STRICT=0.50 \
    COMQUTOR_REAL_NVDA_MIN_ALLOWED=0.65 \
    python -m pytest tests/test_alpha_mapper_nvda_real_report.py -q -s
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from comqutor_alpha.structure_engine.alpha_mapper import map_claim_to_alpha


DATA_PATH = Path(__file__).parent / "golden_cases" / "nvda_real_report_labeled_claims_v1.json"


def _load_cases() -> list[dict[str, Any]]:
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    assert cases, "nvda_real_report_labeled_claims_v1.json must contain non-empty cases"
    return cases


def _record_from_case(case: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "run_id": "manual_nvda_real_report_v1",
        "ticker": "NVDA",
        "agent": case.get("source_agent", "manual_label"),
        "claim": case["text"],
        "evidence": case["text"],
        "factors": case.get("factors", []),
        "direction": case.get("expected_direction", "neutral"),
        "confidence": 0.80,
        "source_type": "analyst",
        "source_refs": [],
    }


def _is_strict_correct(case: Mapping[str, Any], result: Mapping[str, Any]) -> bool:
    expected_status = case.get("expected_match_status", "matched")
    expected_alpha = case.get("expected_alpha")
    actual_status = result.get("match_status")
    actual_alpha = result.get("matched_alpha")

    if expected_status == "matched":
        return actual_status == "matched" and actual_alpha == expected_alpha

    if expected_status == "no_match":
        return actual_status == "no_match" and actual_alpha is None

    if expected_status == "ambiguous":
        return actual_status == "ambiguous" and actual_alpha is None

    raise AssertionError(f"Unsupported expected_match_status: {expected_status}")


def _is_allowed_correct(case: Mapping[str, Any], result: Mapping[str, Any]) -> bool:
    expected_status = case.get("expected_match_status", "matched")
    allowed = set(case.get("allowed_alpha_ids") or [])
    actual_status = result.get("match_status")
    actual_alpha = result.get("matched_alpha")

    if expected_status == "matched":
        return actual_status == "matched" and actual_alpha in allowed

    if expected_status == "no_match":
        # For robustness, ambiguous/no committed alpha is acceptable when the human label says
        # the claim should not be forced into one MVP alpha.
        return actual_status in {"no_match", "ambiguous"} and actual_alpha is None

    if expected_status == "ambiguous":
        # Ambiguous is ideal; a committed alpha is acceptable only if it is in the human-allowed set.
        return (
            actual_status == "ambiguous" and actual_alpha is None
        ) or (
            actual_status == "matched" and actual_alpha in allowed
        )

    raise AssertionError(f"Unsupported expected_match_status: {expected_status}")


def test_real_nvda_labeled_claims_schema_is_valid() -> None:
    cases = _load_cases()
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids)), "case ids must be unique"

    for case in cases:
        assert isinstance(case["text"], str) and case["text"].strip()
        assert case["expected_match_status"] in {"matched", "ambiguous", "no_match"}
        assert "allowed_alpha_ids" in case
        if case["expected_match_status"] == "matched":
            assert case["expected_alpha"], f"{case['id']} requires expected_alpha"


def test_real_nvda_labeled_claim_accuracy_diagnostic() -> None:
    cases = _load_cases()

    results = []
    strict_correct = 0
    allowed_correct = 0

    for case in cases:
        result = map_claim_to_alpha(_record_from_case(case))
        strict = _is_strict_correct(case, result)
        allowed = _is_allowed_correct(case, result)

        strict_correct += int(strict)
        allowed_correct += int(allowed)

        results.append(
            {
                "id": case["id"],
                "expected_status": case["expected_match_status"],
                "expected_alpha": case.get("expected_alpha"),
                "allowed_alpha_ids": case.get("allowed_alpha_ids"),
                "actual_status": result.get("match_status"),
                "actual_alpha": result.get("matched_alpha"),
                "strict_correct": strict,
                "allowed_correct": allowed,
                "top_candidates": result.get("candidate_scores", [])[:3],
                "claim": case["text"],
            }
        )

    strict_accuracy = strict_correct / len(cases)
    allowed_accuracy = allowed_correct / len(cases)

    print(
        json.dumps(
            {
                "case_count": len(cases),
                "strict_correct": strict_correct,
                "strict_accuracy": strict_accuracy,
                "allowed_correct": allowed_correct,
                "allowed_accuracy": allowed_accuracy,
                "mismatches": [item for item in results if not item["allowed_correct"]],
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if os.getenv("COMQUTOR_ENFORCE_REAL_NVDA_GATE") == "1":
        min_strict = float(os.getenv("COMQUTOR_REAL_NVDA_MIN_STRICT", "0.50"))
        min_allowed = float(os.getenv("COMQUTOR_REAL_NVDA_MIN_ALLOWED", "0.65"))
        assert strict_accuracy >= min_strict
        assert allowed_accuracy >= min_allowed

