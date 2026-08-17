"""J3 semantic benchmark comparison (task section 6): independent J3 vs
original B1 LLM vs deterministic.v1, computed purely from three
already-existing categorical values per row -- never a new semantic
judgment, never a re-classification, never a modification of any saved
stance or production Evidence pool.

Inputs (all already-existing, read-only):
  * the J3 provisional semantic benchmark
    (``comqutor_alpha.evaluation.j3_semantic_benchmark``'s
    ``reviewed_stance``/``reviewed_counter_alpha_id`` per row)
  * the B1 final-combined 50-row comparison artifact
    (``docs/audit_artifacts/b1_llm_stance_50_validation_after_parser_fix.csv``'s
    ``llm_v1_stance``/``deterministic_v1_stance`` per row)
  * the canonical taxonomy (for counter-Alpha legality only)

This module never writes to any source artifact; its own output is purely
an in-memory/report-only statistics dict.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

DEFAULT_STANCE_COMPARISON_PATH = Path("docs/audit_artifacts/b1_llm_stance_50_validation_after_parser_fix.csv")

EXPECTED_ROW_COUNT = 50
EXPECTED_VS_B1_LLM_AGREEMENT_COUNT = 39
EXPECTED_VS_DETERMINISTIC_AGREEMENT_COUNT = 22
EXPECTED_BOTH_AGREE_COUNT = 18
EXPECTED_B1_LLM_ONLY_COUNT = 21
EXPECTED_DETERMINISTIC_ONLY_COUNT = 4
EXPECTED_NEITHER_COUNT = 7
EXPECTED_DISAGREEMENT_ROW_IDS = (
    "evrs-006",
    "evrs-007",
    "evrs-008",
    "evrs-013",
    "evrs-020",
    "evrs-026",
    "evrs-034",
    "evrs-036",
    "evrs-040",
    "evrs-042",
    "evrs-045",
)
EXPECTED_STRICT_REVERSAL_ROW_IDS = (
    "evrs-002",
    "evrs-003",
    "evrs-019",
    "evrs-027",
    "evrs-039",
    "evrs-043",
    "evrs-047",
)
EXPECTED_FALSE_SUPPORT_POSITIVE_COUNT = 0
EXPECTED_FALSE_SUPPORT_NEGATIVE_COUNT = 4
EXPECTED_FALSE_SUPPORT_NEGATIVE_IDS = ("evrs-020", "evrs-026", "evrs-034", "evrs-040")

SUPPORTS_ALPHA = "supports_alpha"


class J3SemanticComparisonMismatchError(Exception):
    """Raised when the historically-recorded comparison numbers (task
    section 6) cannot be reproduced from the located source data --
    signals a genuine data mismatch rather than silently reporting a
    conclusion the data does not support."""

    def __init__(self, reason_code: str, detail: str = "") -> None:
        self.reason_code = reason_code
        self.detail = detail
        super().__init__(f"{reason_code}: {detail}" if detail else reason_code)


def load_stance_comparison_rows(path: Path = DEFAULT_STANCE_COMPARISON_PATH) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    by_sample_id = {row["sample_id"]: row for row in rows}
    if len(by_sample_id) != len(rows):
        raise J3SemanticComparisonMismatchError(
            "J3_SOURCE_SAMPLE_MISMATCH", "duplicate sample_id in stance comparison CSV"
        )
    return by_sample_id


def compare_j3_benchmark(
    benchmark: dict[str, Any], stance_comparison_rows: dict[str, dict[str, str]]
) -> dict[str, Any]:
    """Computes the full section-6 comparison. Never mutates either input.
    Raises J3SemanticComparisonMismatchError if the located data cannot
    reproduce the historically-recorded numbers -- never silently reports
    a different conclusion as if it were the verified one."""
    benchmark_rows = benchmark["rows"]
    if len(benchmark_rows) != EXPECTED_ROW_COUNT:
        raise J3SemanticComparisonMismatchError(
            "J3_SOURCE_SAMPLE_MISMATCH", f"benchmark row_count={len(benchmark_rows)} (expected {EXPECTED_ROW_COUNT})"
        )

    missing_in_stance_source = [r["sample_id"] for r in benchmark_rows if r["sample_id"] not in stance_comparison_rows]
    if missing_in_stance_source:
        raise J3SemanticComparisonMismatchError(
            "J3_SOURCE_SAMPLE_MISMATCH", f"sample_ids missing from stance comparison source: {missing_in_stance_source}"
        )

    stance_distribution: dict[str, int] = {}
    confidence_distribution: dict[str, int] = {}
    both_agree_ids: list[str] = []
    b1_llm_only_ids: list[str] = []
    deterministic_only_ids: list[str] = []
    neither_ids: list[str] = []
    disagreement_ids: list[str] = []
    strict_reversal_ids: list[str] = []
    false_support_positive_ids: list[str] = []
    false_support_negative_ids: list[str] = []

    for row in benchmark_rows:
        sample_id = row["sample_id"]
        reviewed_stance = row["reviewed_stance"]
        stance_distribution[reviewed_stance] = stance_distribution.get(reviewed_stance, 0) + 1
        confidence_distribution[row["review_confidence"]] = confidence_distribution.get(row["review_confidence"], 0) + 1

        stance_row = stance_comparison_rows[sample_id]
        llm_stance = stance_row["llm_v1_stance"]
        deterministic_stance = stance_row["deterministic_v1_stance"]

        agrees_with_llm = reviewed_stance == llm_stance
        agrees_with_deterministic = reviewed_stance == deterministic_stance

        if agrees_with_llm and agrees_with_deterministic:
            both_agree_ids.append(sample_id)
        elif agrees_with_llm:
            b1_llm_only_ids.append(sample_id)
        elif agrees_with_deterministic:
            deterministic_only_ids.append(sample_id)
        else:
            neither_ids.append(sample_id)

        if not agrees_with_llm:
            disagreement_ids.append(sample_id)

        if {llm_stance, deterministic_stance} == {"supports_alpha", "opposes_alpha"}:
            strict_reversal_ids.append(sample_id)

        llm_supports = llm_stance == SUPPORTS_ALPHA
        j3_supports = reviewed_stance == SUPPORTS_ALPHA
        if j3_supports and not llm_supports:
            false_support_negative_ids.append(sample_id)
        if llm_supports and not j3_supports:
            false_support_positive_ids.append(sample_id)

    result = {
        "row_count": len(benchmark_rows),
        "stance_distribution": stance_distribution,
        "confidence_distribution": confidence_distribution,
        "independent_vs_b1_llm_agreement_count": len(both_agree_ids) + len(b1_llm_only_ids),
        "independent_vs_b1_llm_agreement_rate": (len(both_agree_ids) + len(b1_llm_only_ids)) / len(benchmark_rows),
        "independent_vs_deterministic_agreement_count": len(both_agree_ids) + len(deterministic_only_ids),
        "independent_vs_deterministic_agreement_rate": (
            (len(both_agree_ids) + len(deterministic_only_ids)) / len(benchmark_rows)
        ),
        "both_agree_count": len(both_agree_ids),
        "b1_llm_only_count": len(b1_llm_only_ids),
        "deterministic_only_count": len(deterministic_only_ids),
        "neither_count": len(neither_ids),
        "both_agree_rows": sorted(both_agree_ids),
        "b1_llm_only_rows": sorted(b1_llm_only_ids),
        "deterministic_only_rows": sorted(deterministic_only_ids),
        "neither_rows": sorted(neither_ids),
        "strict_reversal_rows": sorted(strict_reversal_ids),
        "disagreement_rows": sorted(disagreement_ids),
        "support_pool_changes": {
            "false_support_positive_count": len(false_support_positive_ids),
            "false_support_positive_rows": sorted(false_support_positive_ids),
            "false_support_negative_count": len(false_support_negative_ids),
            "false_support_negative_rows": sorted(false_support_negative_ids),
        },
    }

    _verify_historical_numbers(result)
    return result


def _verify_historical_numbers(result: dict[str, Any]) -> None:
    mismatches: list[str] = []
    if result["independent_vs_b1_llm_agreement_count"] != EXPECTED_VS_B1_LLM_AGREEMENT_COUNT:
        mismatches.append(
            f"independent_vs_b1_llm_agreement_count={result['independent_vs_b1_llm_agreement_count']} "
            f"(expected {EXPECTED_VS_B1_LLM_AGREEMENT_COUNT})"
        )
    if result["independent_vs_deterministic_agreement_count"] != EXPECTED_VS_DETERMINISTIC_AGREEMENT_COUNT:
        mismatches.append(
            f"independent_vs_deterministic_agreement_count={result['independent_vs_deterministic_agreement_count']} "
            f"(expected {EXPECTED_VS_DETERMINISTIC_AGREEMENT_COUNT})"
        )
    if result["both_agree_count"] != EXPECTED_BOTH_AGREE_COUNT:
        mismatches.append(f"both_agree_count={result['both_agree_count']} (expected {EXPECTED_BOTH_AGREE_COUNT})")
    if result["b1_llm_only_count"] != EXPECTED_B1_LLM_ONLY_COUNT:
        mismatches.append(f"b1_llm_only_count={result['b1_llm_only_count']} (expected {EXPECTED_B1_LLM_ONLY_COUNT})")
    if result["deterministic_only_count"] != EXPECTED_DETERMINISTIC_ONLY_COUNT:
        mismatches.append(
            f"deterministic_only_count={result['deterministic_only_count']} (expected {EXPECTED_DETERMINISTIC_ONLY_COUNT})"
        )
    if result["neither_count"] != EXPECTED_NEITHER_COUNT:
        mismatches.append(f"neither_count={result['neither_count']} (expected {EXPECTED_NEITHER_COUNT})")
    if tuple(result["disagreement_rows"]) != tuple(sorted(EXPECTED_DISAGREEMENT_ROW_IDS)):
        mismatches.append(f"disagreement_rows={result['disagreement_rows']} (expected {sorted(EXPECTED_DISAGREEMENT_ROW_IDS)})")
    if tuple(result["strict_reversal_rows"]) != tuple(sorted(EXPECTED_STRICT_REVERSAL_ROW_IDS)):
        mismatches.append(
            f"strict_reversal_rows={result['strict_reversal_rows']} (expected {sorted(EXPECTED_STRICT_REVERSAL_ROW_IDS)})"
        )
    support = result["support_pool_changes"]
    if support["false_support_positive_count"] != EXPECTED_FALSE_SUPPORT_POSITIVE_COUNT:
        mismatches.append(
            f"false_support_positive_count={support['false_support_positive_count']} "
            f"(expected {EXPECTED_FALSE_SUPPORT_POSITIVE_COUNT})"
        )
    if support["false_support_negative_count"] != EXPECTED_FALSE_SUPPORT_NEGATIVE_COUNT:
        mismatches.append(
            f"false_support_negative_count={support['false_support_negative_count']} "
            f"(expected {EXPECTED_FALSE_SUPPORT_NEGATIVE_COUNT})"
        )
    if tuple(support["false_support_negative_rows"]) != tuple(sorted(EXPECTED_FALSE_SUPPORT_NEGATIVE_IDS)):
        mismatches.append(
            f"false_support_negative_rows={support['false_support_negative_rows']} "
            f"(expected {sorted(EXPECTED_FALSE_SUPPORT_NEGATIVE_IDS)})"
        )
    if mismatches:
        raise J3SemanticComparisonMismatchError("J3_SOURCE_SAMPLE_MISMATCH", "; ".join(mismatches))


def verify_reversal_rows_support_b1_llm(
    benchmark: dict[str, Any], stance_comparison_rows: dict[str, dict[str, str]]
) -> bool:
    """Confirms the task's own claim: on all 7 strict reversal rows, the
    independent J3 verdict matches the original B1 LLM value (not
    deterministic.v1). Returns True only if this holds for every one of
    the 7 rows."""
    by_id = {r["sample_id"]: r for r in benchmark["rows"]}
    for sample_id in EXPECTED_STRICT_REVERSAL_ROW_IDS:
        reviewed = by_id[sample_id]["reviewed_stance"]
        llm = stance_comparison_rows[sample_id]["llm_v1_stance"]
        if reviewed != llm:
            return False
    return True


__all__ = [
    "DEFAULT_STANCE_COMPARISON_PATH",
    "EXPECTED_ROW_COUNT",
    "EXPECTED_VS_B1_LLM_AGREEMENT_COUNT",
    "EXPECTED_VS_DETERMINISTIC_AGREEMENT_COUNT",
    "EXPECTED_BOTH_AGREE_COUNT",
    "EXPECTED_B1_LLM_ONLY_COUNT",
    "EXPECTED_DETERMINISTIC_ONLY_COUNT",
    "EXPECTED_NEITHER_COUNT",
    "EXPECTED_DISAGREEMENT_ROW_IDS",
    "EXPECTED_STRICT_REVERSAL_ROW_IDS",
    "EXPECTED_FALSE_SUPPORT_POSITIVE_COUNT",
    "EXPECTED_FALSE_SUPPORT_NEGATIVE_COUNT",
    "EXPECTED_FALSE_SUPPORT_NEGATIVE_IDS",
    "J3SemanticComparisonMismatchError",
    "load_stance_comparison_rows",
    "compare_j3_benchmark",
    "verify_reversal_rows_support_b1_llm",
]
