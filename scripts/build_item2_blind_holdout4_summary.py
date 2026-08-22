#!/usr/bin/env python3
"""QA Closure v0.1.2 -- Item 2 Blind Holdout #4: join the frozen CSV + system
Pure-LLM Alpha result + independent blind reviewer labels, and compute the
FORMAL acceptance metric plus every required diagnostic (task spec sections
18-23). Pure, deterministic, offline arithmetic -- no Provider call.
Re-running against the same frozen inputs must always produce byte-identical
output. This script does not alter any label after the join; it is
report-only.

Primary metric (task spec section 18): exact Top-1 agreement,
system_matched_alpha_id vs reviewer_expected_alpha_id, "NONE" and Python
None normalized to the same canonical no-alpha value for comparison. No
partial credit, no Top-3 credit, no taxonomy-overlap credit, no post-hoc
exclusion. UNAVAILABLE counts as incorrect for the primary metric and is
separately reported as an operational-failure count.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from comqutor_alpha.structure_engine.ai_alpha_discriminator import AI_ALPHA_IDS  # noqa: E402

FROZEN_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout4_frozen.csv"
SYSTEM_ALPHA_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout4_system_alpha.json"
ALPHA_REVIEW_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout4_alpha_review.json"

COMPARISON_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout4_comparison.csv"
METRICS_JSON_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout4_metrics.json"

ACCEPTANCE_THRESHOLD = 0.75
ALL_ALPHA_IDS_PLUS_NONE = ["A001", "A003", "A101", "A102", "A103", "A201", "A301", "A304", "A501", "A601", "NONE"]

# Historical context only (task spec section 23) -- NOT recomputed, NOT a
# paired/causal comparison, different samples entirely.
HOLDOUT3_ORIGINAL_ACCURACY = 105 / 152
HOLDOUT3_ORIGINAL_NUMERATOR_DENOMINATOR = "105/152"
HOLDOUT3_PURE_LLM_DEV_ACCURACY = 119 / 152
HOLDOUT3_PURE_LLM_DEV_NUMERATOR_DENOMINATOR = "119/152"


def _norm_alpha(value: Any) -> str:
    """Canonicalize both system's Python None and reviewer's literal "NONE"
    string to the same "NONE" token for exact-match comparison."""
    if value is None:
        return "NONE"
    text = str(value).strip()
    return text if text else "NONE"


def _rate(flags: list[int]) -> dict[str, Any]:
    return {"correct": sum(flags), "total": len(flags), "accuracy": (sum(flags) / len(flags)) if flags else None}


def main() -> int:
    with FROZEN_CSV_PATH.open(encoding="utf-8", newline="") as f:
        frozen_rows = {r["sample_id"]: r for r in csv.DictReader(f)}
    system_results = json.loads(SYSTEM_ALPHA_PATH.read_text(encoding="utf-8"))
    reviewer_results = json.loads(ALPHA_REVIEW_PATH.read_text(encoding="utf-8"))

    ids = set(frozen_rows)
    assert ids == set(system_results) == set(reviewer_results), (
        "sample_id set mismatch across the three frozen/evaluated sources"
    )
    n = len(ids)
    assert n == 200, f"expected exactly 200 frozen H4 rows, found {n}"

    correct = 0
    unavailable_count = 0
    confusion: dict[str, dict[str, int]] = {a: dict.fromkeys(ALL_ALPHA_IDS_PLUS_NONE, 0) for a in ALL_ALPHA_IDS_PLUS_NONE}

    by_ticker: dict[str, list[int]] = defaultdict(list)
    by_agent: dict[str, list[int]] = defaultdict(list)
    by_reviewer_alpha: dict[str, list[int]] = defaultdict(list)
    by_system_alpha: dict[str, list[int]] = defaultdict(list)
    by_method: dict[str, list[int]] = defaultdict(list)
    by_confidence: dict[str, list[int]] = defaultdict(list)

    ai_rows: list[dict[str, Any]] = []
    non_ai_flags: list[int] = []

    llm_vs_reviewer: list[int] = []
    det_vs_reviewer: list[int] = []
    changed_rows: list[str] = []
    corrected_ids: list[str] = []
    worsened_ids: list[str] = []
    both_wrong_differently_ids: list[str] = []
    equivalent_ids: list[str] = []

    system_none_count = 0
    reviewer_none_count = 0
    none_none_correct = 0
    system_alpha_reviewer_none = 0
    system_none_reviewer_alpha = 0

    comparison_rows: list[dict[str, Any]] = []

    for sid in sorted(ids):
        frozen = frozen_rows[sid]
        system = system_results[sid]
        reviewer = reviewer_results[sid]

        system_alpha = _norm_alpha(system.get("system_matched_alpha_id"))
        reviewer_alpha = _norm_alpha(reviewer.get("reviewer_expected_alpha_id"))
        is_unavailable = system.get("match_status") == "unavailable"
        is_correct = (not is_unavailable) and (system_alpha == reviewer_alpha)
        correct += int(is_correct)
        unavailable_count += int(is_unavailable)
        confusion[system_alpha][reviewer_alpha] += 1

        ticker = frozen["ticker"]
        agent = frozen["agent"]
        by_ticker[ticker].append(int(is_correct))
        by_agent[agent].append(int(is_correct))
        by_reviewer_alpha[reviewer_alpha].append(int(is_correct))
        by_system_alpha[system_alpha].append(int(is_correct))

        method = system.get("alpha_match_method") or "unknown"
        by_method[method].append(int(is_correct))

        confidence = reviewer.get("confidence") or "unknown"
        by_confidence[confidence].append(int(is_correct))

        if reviewer_alpha in AI_ALPHA_IDS:
            ai_rows.append({"sample_id": sid, "reviewer_alpha": reviewer_alpha, "system_alpha": system_alpha, "correct": is_correct})
        elif reviewer_alpha != "NONE":
            non_ai_flags.append(int(is_correct))

        if system_alpha == "NONE" and not is_unavailable:
            system_none_count += 1
            if reviewer_alpha == "NONE":
                none_none_correct += 1
            else:
                system_none_reviewer_alpha += 1
        if reviewer_alpha == "NONE":
            reviewer_none_count += 1
            if system_alpha != "NONE" and not is_unavailable:
                system_alpha_reviewer_none += 1

        # Deterministic counterfactual (task spec section 22): the SAME
        # already-computed deterministic_top_alpha diagnostic, zero
        # additional Provider cost, compared to the same reviewer label.
        llm_alpha = "UNAVAILABLE" if is_unavailable else system_alpha
        det_alpha = _norm_alpha(system.get("deterministic_top_alpha"))
        llm_correct = (not is_unavailable) and (llm_alpha == reviewer_alpha)
        det_correct = det_alpha == reviewer_alpha
        llm_vs_reviewer.append(int(llm_correct))
        det_vs_reviewer.append(int(det_correct))

        if llm_alpha != det_alpha:
            changed_rows.append(sid)
            if det_correct and not llm_correct:
                worsened_ids.append(sid)
            elif llm_correct and not det_correct:
                corrected_ids.append(sid)
            elif not llm_correct and not det_correct:
                both_wrong_differently_ids.append(sid)
            else:
                equivalent_ids.append(sid)

        comparison_rows.append(
            {
                "sample_id": sid, "ticker": ticker, "agent": agent, "claim_id": frozen["claim_id"],
                "system_matched_alpha_id": system_alpha, "match_status": system.get("match_status"),
                "alpha_match_method": system.get("alpha_match_method"),
                "alpha_match_fallback_reason": system.get("alpha_match_fallback_reason"),
                "reviewer_expected_alpha_id": reviewer_alpha, "reviewer_confidence": confidence,
                "correct": is_correct, "is_unavailable": is_unavailable,
                "deterministic_top_alpha": det_alpha, "deterministic_correct": det_correct,
                "changed_from_deterministic": llm_alpha != det_alpha,
            }
        )

    accuracy = correct / n

    def _rate_table(d: dict[str, list[int]]) -> dict[str, dict[str, Any]]:
        return {k: {"correct": sum(v), "total": len(v), "accuracy": sum(v) / len(v)} for k, v in sorted(d.items())}

    # AI family diagnostic (task spec section 21).
    ai_by_alpha: dict[str, list[int]] = defaultdict(list)
    for r in ai_rows:
        ai_by_alpha[r["reviewer_alpha"]].append(int(r["correct"]))
    ai_confusion_within_family = Counter(
        (r["reviewer_alpha"], r["system_alpha"]) for r in ai_rows if r["system_alpha"] in AI_ALPHA_IDS and not r["correct"]
    )
    ai_confusion_outside_family = Counter(
        (r["reviewer_alpha"], r["system_alpha"]) for r in ai_rows if r["system_alpha"] in {"A201", "A301", "A304", "A601"}
    )
    ai_confusion_other = Counter(
        (r["reviewer_alpha"], r["system_alpha"])
        for r in ai_rows
        if r["system_alpha"] not in AI_ALPHA_IDS | {"A201", "A301", "A304", "A601"}
    )

    with COMPARISON_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        fieldnames = list(comparison_rows[0].keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(comparison_rows)

    llm_accuracy = sum(llm_vs_reviewer) / n
    det_accuracy = sum(det_vs_reviewer) / n

    metrics = {
        "task": "QA Closure v0.1.2 -- Item 2 Blind Holdout #4 -- Formal Acceptance of Pure-LLM Alpha Mapper",
        "is_blind_acceptance_result": True,
        "sample_count": n,
        "official_numerator": correct,
        "official_denominator": n,
        "alpha_match_accuracy": accuracy,
        "acceptance_threshold": ACCEPTANCE_THRESHOLD,
        "pass": accuracy >= ACCEPTANCE_THRESHOLD,
        "unavailable_count": unavailable_count,
        "unavailable_counted_as_incorrect": True,
        "confusion_matrix": {"axes": "rows=system_matched_alpha_id, columns=reviewer_expected_alpha_id", "matrix": confusion},
        "accuracy_by_ticker": _rate_table(by_ticker),
        "accuracy_by_agent": _rate_table(by_agent),
        "accuracy_by_reviewer_expected_alpha": _rate_table(by_reviewer_alpha),
        "accuracy_by_system_matched_alpha": _rate_table(by_system_alpha),
        "accuracy_by_alpha_match_method": _rate_table(by_method),
        "reviewer_confidence_agreement": _rate_table(by_confidence),
        "none_analysis": {
            "system_none_count": system_none_count,
            "reviewer_none_count": reviewer_none_count,
            "none_none_correct_count": none_none_correct,
            "system_alpha_but_reviewer_none_count": system_alpha_reviewer_none,
            "system_none_but_reviewer_alpha_count": system_none_reviewer_alpha,
            "unavailable_count": unavailable_count,
        },
        "ai_family_analysis": {
            "reviewer_expected_ai_family_count": len(ai_rows),
            "combined_accuracy": _rate([int(r["correct"]) for r in ai_rows]),
            "accuracy_by_alpha": {a: _rate(v) for a, v in sorted(ai_by_alpha.items())},
            "confusion_within_ai_family": {f"{a}->{b}": c for (a, b), c in ai_confusion_within_family.items()},
            "confusion_into_a201_a301_a304_a601": {f"{a}->{b}": c for (a, b), c in ai_confusion_outside_family.items()},
            "confusion_other": {f"{a}->{b}": c for (a, b), c in ai_confusion_other.items()},
            "non_ai_reviewer_expected_count": len(non_ai_flags),
            "non_ai_accuracy": (sum(non_ai_flags) / len(non_ai_flags)) if non_ai_flags else None,
        },
        "deterministic_counterfactual": {
            "description": "Section 22: final Pure-LLM system result vs the same already-computed deterministic_top_alpha diagnostic (zero additional Provider cost), both compared against the same blind reviewer label. Diagnostic only -- does not affect PASS/FAIL.",
            "pure_llm_accuracy_vs_reviewer": llm_accuracy,
            "deterministic_counterfactual_accuracy_vs_reviewer": det_accuracy,
            "rows_where_llm_differs_from_deterministic": len(changed_rows),
            "llm_corrected_deterministic_count": len(corrected_ids),
            "llm_worsened_deterministic_count": len(worsened_ids),
            "both_wrong_differently_count": len(both_wrong_differently_ids),
            "equivalent_count": len(equivalent_ids),
            "changed_row_sample_ids": changed_rows,
            "llm_corrected_sample_ids": corrected_ids,
            "llm_worsened_sample_ids": worsened_ids,
        },
        "holdout3_comparison_context_only_not_causal_not_paired": {
            "warning": "Holdout #3 and Holdout #4 use entirely different, non-overlapping samples (different rows, different sampling methodology -- H3's candidate pool was filtered to rows the prior deterministic/LLM system had already confidently matched; H4's is not, and is drawn from a much broader source pool including two tickers -- SNDK/TSM -- H3 treated as exhausted). This comparison is historical context ONLY, never a paired or causal claim about whether accuracy 'improved'.",
            "holdout3_original_accuracy": HOLDOUT3_ORIGINAL_ACCURACY,
            "holdout3_original_numerator_denominator": HOLDOUT3_ORIGINAL_NUMERATOR_DENOMINATOR,
            "holdout3_pure_llm_dev_accuracy": HOLDOUT3_PURE_LLM_DEV_ACCURACY,
            "holdout3_pure_llm_dev_numerator_denominator": HOLDOUT3_PURE_LLM_DEV_NUMERATOR_DENOMINATOR,
            "holdout4_accuracy": accuracy,
            "holdout4_numerator_denominator": f"{correct}/{n}",
        },
    }
    METRICS_JSON_PATH.write_text(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"\nWrote {len(comparison_rows)} rows -> {COMPARISON_CSV_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
