#!/usr/bin/env python3
"""QA Closure v0.1.2 -- Item 2 Blind Holdout #3, Phase 7: join the three
frozen/evaluated inputs (frozen CSV + system_alpha.json + alpha_review.json)
and compute the acceptance metric plus all required diagnostics. Pure,
deterministic, offline arithmetic -- no Provider call. Re-running against
the same frozen inputs must always produce byte-identical output. This
script does not alter any label after the join; it is report-only.

Primary metric definition (task spec section 13): exact Top-1 agreement,
system_matched_alpha_id vs reviewer_expected_alpha_id, "NONE" and Python
None normalized to the same canonical no-alpha value for comparison. No
partial credit, no Top-3 credit, no taxonomy-overlap credit, no post-hoc
exclusion of "ambiguous" mismatches.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from comqutor_alpha.structure_engine.ai_alpha_discriminator import AI_ALPHA_IDS  # noqa: E402

FROZEN_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout3_frozen.csv"
SYSTEM_ALPHA_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout3_system_alpha.json"
ALPHA_REVIEW_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout3_alpha_review.json"
SAMPLING_METADATA_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout3_sampling_metadata.json"

COMPARISON_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout3_comparison.csv"
METRICS_JSON_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout3_metrics.json"

ACCEPTANCE_THRESHOLD = 0.75
HOLDOUT2_ACCURACY = 84 / 141
ALL_ALPHA_IDS_PLUS_NONE = ["A001", "A003", "A101", "A102", "A103", "A201", "A301", "A304", "A501", "A601", "NONE"]


def _norm_alpha(value: Any) -> str:
    """Canonicalize both system's Python None and reviewer's literal "NONE"
    string to the same "NONE" token for exact-match comparison."""
    if value is None:
        return "NONE"
    text = str(value).strip()
    return text if text else "NONE"


def main() -> int:
    with FROZEN_CSV_PATH.open(encoding="utf-8", newline="") as f:
        frozen_rows = {r["sample_id"]: r for r in csv.DictReader(f)}
    system_results = json.loads(SYSTEM_ALPHA_PATH.read_text(encoding="utf-8"))
    reviewer_results = json.loads(ALPHA_REVIEW_PATH.read_text(encoding="utf-8"))
    sampling_metadata = json.loads(SAMPLING_METADATA_PATH.read_text(encoding="utf-8"))

    ids = set(frozen_rows)
    assert ids == set(system_results) == set(reviewer_results), "sample_id set mismatch across the three frozen/evaluated sources"
    n = len(ids)

    correct = 0
    confusion: dict[str, dict[str, int]] = {a: dict.fromkeys(ALL_ALPHA_IDS_PLUS_NONE, 0) for a in ALL_ALPHA_IDS_PLUS_NONE}

    by_ticker: dict[str, list[int]] = defaultdict(list)
    by_reviewer_alpha: dict[str, list[int]] = defaultdict(list)
    by_system_alpha: dict[str, list[int]] = defaultdict(list)
    by_method: dict[str, list[int]] = defaultdict(list)
    by_confidence: dict[str, list[int]] = defaultdict(list)
    ai_family_flags: list[int] = []
    non_ai_flags: list[int] = []

    llm_primary_vs_reviewer: list[int] = []
    deterministic_counterfactual_vs_reviewer: list[int] = []
    changed_rows: list[str] = []
    corrected_ids: list[str] = []
    worsened_ids: list[str] = []
    both_wrong_differently_ids: list[str] = []
    equivalent_ids: list[str] = []

    system_none_count = 0
    reviewer_none_count = 0
    system_none_correct = 0

    comparison_rows: list[dict[str, Any]] = []

    for sid in sorted(ids):
        frozen = frozen_rows[sid]
        system = system_results[sid]
        reviewer = reviewer_results[sid]

        system_alpha = _norm_alpha(system.get("system_matched_alpha_id"))
        reviewer_alpha = _norm_alpha(reviewer.get("reviewer_expected_alpha_id"))
        is_correct = system_alpha == reviewer_alpha
        correct += int(is_correct)
        confusion[system_alpha][reviewer_alpha] += 1

        ticker = frozen["ticker"]
        by_ticker[ticker].append(int(is_correct))
        by_reviewer_alpha[reviewer_alpha].append(int(is_correct))
        by_system_alpha[system_alpha].append(int(is_correct))

        method = system.get("alpha_match_method") or "unknown"
        by_method[method].append(int(is_correct))

        confidence = reviewer.get("confidence") or "unknown"
        by_confidence[confidence].append(int(is_correct))

        if reviewer_alpha in AI_ALPHA_IDS:
            ai_family_flags.append(int(is_correct))
        elif reviewer_alpha != "NONE":
            non_ai_flags.append(int(is_correct))

        if system_alpha == "NONE":
            system_none_count += 1
            system_none_correct += int(is_correct)
        if reviewer_alpha == "NONE":
            reviewer_none_count += 1

        # Counterfactual diagnostic (task spec section 17): LLM-primary
        # final answer vs the same real production function's deterministic-
        # only counterfactual, both compared against the same reviewer label.
        llm_alpha = system_alpha  # the final, LLM-primary system answer
        det_alpha = _norm_alpha(system.get("deterministic_counterfactual_matched_alpha_id"))
        llm_correct = llm_alpha == reviewer_alpha
        det_correct = det_alpha == reviewer_alpha
        llm_primary_vs_reviewer.append(int(llm_correct))
        deterministic_counterfactual_vs_reviewer.append(int(det_correct))

        if llm_alpha != det_alpha:
            changed_rows.append(sid)
            if det_correct and not llm_correct:
                worsened_ids.append(sid)
            elif llm_correct and not det_correct:
                corrected_ids.append(sid)
            elif not llm_correct and not det_correct:
                both_wrong_differently_ids.append(sid)
            else:
                # Mathematically unreachable under exact-Top-1 comparison:
                # det_correct and llm_correct both true would require
                # det_alpha == reviewer_alpha == llm_alpha, contradicting
                # llm_alpha != det_alpha above. Reported, not fabricated.
                equivalent_ids.append(sid)

        comparison_rows.append(
            {
                "sample_id": sid, "ticker": ticker, "claim_id": frozen["claim_id"],
                "system_matched_alpha_id": system_alpha, "reviewer_expected_alpha_id": reviewer_alpha,
                "correct": is_correct, "alpha_match_method": method,
                "reviewer_confidence": confidence,
                "deterministic_counterfactual_matched_alpha_id": det_alpha,
                "deterministic_counterfactual_correct": det_correct,
                "changed_from_deterministic": llm_alpha != det_alpha,
                "historical_matched_alpha_id_not_official_label": sampling_metadata.get(sid, {}).get("historical_matched_alpha_id_not_official_label"),
            }
        )

    accuracy = correct / n

    def _rate_table(d: dict[str, list[int]]) -> dict[str, dict[str, Any]]:
        return {k: {"correct": sum(v), "total": len(v), "accuracy": sum(v) / len(v)} for k, v in sorted(d.items())}

    llm_primary_accuracy = sum(llm_primary_vs_reviewer) / n
    det_counterfactual_accuracy = sum(deterministic_counterfactual_vs_reviewer) / n

    with COMPARISON_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        fieldnames = list(comparison_rows[0].keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(comparison_rows)

    metrics = {
        "sample_count": n,
        "official_numerator": correct,
        "official_denominator": n,
        "alpha_match_accuracy": accuracy,
        "acceptance_threshold": ACCEPTANCE_THRESHOLD,
        "pass": accuracy >= ACCEPTANCE_THRESHOLD,
        "confusion_matrix": {"axes": "rows=system_matched_alpha_id, columns=reviewer_expected_alpha_id", "matrix": confusion},
        "accuracy_by_ticker": _rate_table(by_ticker),
        "accuracy_by_reviewer_expected_alpha": _rate_table(by_reviewer_alpha),
        "accuracy_by_system_matched_alpha": _rate_table(by_system_alpha),
        "system_none_count": system_none_count,
        "system_none_accuracy": (system_none_correct / system_none_count) if system_none_count else None,
        "reviewer_none_count": reviewer_none_count,
        "llm_primary_count": len(by_method.get("llm", [])),
        "llm_primary_accuracy_within_llm_rows": (sum(by_method["llm"]) / len(by_method["llm"])) if by_method.get("llm") else None,
        "deterministic_fallback_count": len(by_method.get("deterministic_fallback", [])),
        "deterministic_fallback_accuracy_within_fallback_rows": (sum(by_method["deterministic_fallback"]) / len(by_method["deterministic_fallback"])) if by_method.get("deterministic_fallback") else None,
        "ai_family_reviewer_expected_count": len(ai_family_flags),
        "ai_family_accuracy": (sum(ai_family_flags) / len(ai_family_flags)) if ai_family_flags else None,
        "non_ai_reviewer_expected_count": len(non_ai_flags),
        "non_ai_accuracy": (sum(non_ai_flags) / len(non_ai_flags)) if non_ai_flags else None,
        "reviewer_confidence_agreement": _rate_table(by_confidence),
        "counterfactual_diagnostic": {
            "description": "Section 17: final LLM-primary system answer vs the same real production function's deterministic-only counterfactual (classifier_enabled=False), both compared against the same reviewer label. Offline diagnostic only; does not alter PASS/FAIL.",
            "llm_primary_accuracy_vs_reviewer": llm_primary_accuracy,
            "deterministic_counterfactual_accuracy_vs_reviewer": det_counterfactual_accuracy,
            "rows_where_llm_changed_deterministic_answer": len(changed_rows),
            "llm_corrected_deterministic_count": len(corrected_ids),
            "llm_worsened_deterministic_count": len(worsened_ids),
            "both_wrong_differently_count": len(both_wrong_differently_ids),
            "equivalent_count": len(equivalent_ids),
            "equivalent_count_note": "Mathematically unreachable under exact-Top-1 comparison for a row where llm_alpha != det_alpha by definition (a 'changed' row) -- both-correct would require det_alpha == reviewer == llm_alpha, contradicting the change. Reported as 0, not omitted.",
            "changed_row_sample_ids": changed_rows,
            "llm_corrected_sample_ids": corrected_ids,
            "llm_worsened_sample_ids": worsened_ids,
            "both_wrong_differently_sample_ids": both_wrong_differently_ids,
        },
        "holdout2_comparison": {
            "holdout2_alpha_match_accuracy": HOLDOUT2_ACCURACY,
            "holdout2_numerator_denominator": "84/141",
            "holdout3_alpha_match_accuracy": accuracy,
            "holdout3_numerator_denominator": f"{correct}/{n}",
            "warning": "Holdout #2 and Holdout #3 use different, non-overlapping samples (different rows, different tickers in part, different evaluation protocol architecture -- Holdout #2 predates the Exact Semantic Replay B1 binding work and used a combined single-track reviewer for some fields). This comparison is NOT a controlled before/after causal claim; it only checks whether the CURRENT frozen architecture clears the CURRENT >=75% threshold on genuinely new data.",
        },
    }
    METRICS_JSON_PATH.write_text(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"\nWrote {len(comparison_rows)} rows -> {COMPARISON_CSV_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
