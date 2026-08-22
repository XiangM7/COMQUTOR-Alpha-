#!/usr/bin/env python3
"""Alpha Mapper Pure-LLM Semantic Authority -- Holdout #3 Development
Re-Evaluation, offline summary phase: join the frozen CSV + the NEW Pure-LLM
system_alpha.json + the ORIGINAL (reused, not re-derived) reviewer labels +
the ORIGINAL (already-consumed) system_alpha.json, and compute the
development metric plus every required comparison/diagnostic (task spec
sections 23-29). Pure, deterministic, offline arithmetic -- no Provider
call. This is a DEVELOPMENT re-evaluation on already-consumed data, NOT a
blind acceptance result.
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

FROZEN_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout3_frozen.csv"
ORIGINAL_SYSTEM_ALPHA_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout3_system_alpha.json"
REVIEWER_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout3_alpha_review.json"
NEW_SYSTEM_ALPHA_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_holdout3_pure_llm_dev_system_alpha.json"

COMPARISON_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_holdout3_pure_llm_dev_comparison.csv"
METRICS_JSON_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_holdout3_pure_llm_dev_metrics.json"

DEVELOPMENT_TARGET = 0.75
ALL_ALPHA_IDS_PLUS_NONE = ["A001", "A003", "A101", "A102", "A103", "A201", "A301", "A304", "A501", "A601", "NONE"]


def _norm_alpha(value: Any) -> str:
    if value is None:
        return "NONE"
    text = str(value).strip()
    return text if text else "NONE"


def _rate(flags: list[int]) -> dict[str, Any]:
    return {"correct": sum(flags), "total": len(flags), "accuracy": (sum(flags) / len(flags)) if flags else None}


def main() -> int:
    with FROZEN_CSV_PATH.open(encoding="utf-8", newline="") as f:
        frozen_rows = {r["sample_id"]: r for r in csv.DictReader(f)}
    original_system = json.loads(ORIGINAL_SYSTEM_ALPHA_PATH.read_text(encoding="utf-8"))
    reviewer = json.loads(REVIEWER_PATH.read_text(encoding="utf-8"))
    new_system = json.loads(NEW_SYSTEM_ALPHA_PATH.read_text(encoding="utf-8"))

    ids = set(frozen_rows)
    assert ids == set(original_system) == set(reviewer) == set(new_system), (
        "sample_id set mismatch across frozen/original-system/reviewer/new-system sources"
    )
    n = len(ids)
    assert n == 152, f"expected exactly 152 frozen rows, found {n}"

    # ------------------------------------------------------------------
    # Per-row joined view.
    # ------------------------------------------------------------------
    rows: dict[str, dict[str, Any]] = {}
    for sid in ids:
        old = original_system[sid]
        new = new_system[sid]
        rev = reviewer[sid]
        reviewer_alpha = _norm_alpha(rev.get("reviewer_expected_alpha_id"))
        old_alpha = _norm_alpha(old.get("system_matched_alpha_id"))
        new_alpha = _norm_alpha(new.get("system_matched_alpha_id"))
        rows[sid] = {
            "sample_id": sid,
            "ticker": frozen_rows[sid]["ticker"],
            "claim_id": frozen_rows[sid]["claim_id"],
            "reviewer_alpha": reviewer_alpha,
            "reviewer_confidence": rev.get("confidence"),
            "old_alpha": old_alpha,
            "old_method": old.get("alpha_match_method"),
            "old_correct": old_alpha == reviewer_alpha,
            "new_alpha": new_alpha,
            "new_method": new.get("alpha_match_method"),
            "new_match_status": new.get("match_status"),
            "new_fallback_reason": new.get("alpha_match_fallback_reason"),
            "new_correct": new_alpha == reviewer_alpha,
            "was_original_defer_row": old.get("alpha_match_method") == "deterministic_fallback",
            "was_original_committed_row": old.get("alpha_match_method") == "llm",
        }

    development_correct = sum(1 for r in rows.values() if r["new_correct"])
    development_accuracy = development_correct / n

    # ------------------------------------------------------------------
    # Section 24: old (105/152) vs new vs deterministic counterfactual
    # (61.18%, referenced from the original, already-frozen metrics file --
    # not recomputed here, since recomputing would require a second
    # Provider-free pass this task's own no-retuning rule does not call
    # for; the number is a fixed historical fact of the already-consumed
    # Holdout #3 evaluation).
    # ------------------------------------------------------------------
    original_metrics = json.loads(
        (REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout3_metrics.json").read_text(encoding="utf-8")
    )
    original_accuracy = original_metrics["alpha_match_accuracy"]
    original_numerator = original_metrics["official_numerator"]
    original_denominator = original_metrics["official_denominator"]
    deterministic_counterfactual_accuracy = original_metrics["counterfactual_diagnostic"][
        "deterministic_counterfactual_accuracy_vs_reviewer"
    ]
    original_ai_family_accuracy = original_metrics["ai_family_accuracy"]
    original_mu_accuracy = original_metrics["accuracy_by_ticker"]["MU"]["accuracy"]

    wrong_to_correct: list[str] = []
    correct_to_wrong: list[str] = []
    wrong_to_different_wrong: list[str] = []
    unchanged_correct: list[str] = []
    unchanged_wrong: list[str] = []
    for sid, r in rows.items():
        if not r["old_correct"] and r["new_correct"]:
            wrong_to_correct.append(sid)
        elif r["old_correct"] and not r["new_correct"]:
            correct_to_wrong.append(sid)
        elif r["old_correct"] and r["new_correct"]:
            unchanged_correct.append(sid)
        else:
            if r["old_alpha"] != r["new_alpha"]:
                wrong_to_different_wrong.append(sid)
            else:
                unchanged_wrong.append(sid)
    assert len(wrong_to_correct) + len(correct_to_wrong) + len(wrong_to_different_wrong) + len(
        unchanged_correct
    ) + len(unchanged_wrong) == n

    # ------------------------------------------------------------------
    # Section 25: the exact original 54 defer rows.
    # ------------------------------------------------------------------
    defer_ids = [sid for sid, r in rows.items() if r["was_original_defer_row"]]
    assert len(defer_ids) == 54, f"expected exactly 54 original defer rows, found {len(defer_ids)}"
    defer_rows = [rows[sid] for sid in defer_ids]
    defer_now_selected = sum(1 for r in defer_rows if r["new_match_status"] == "matched")
    defer_now_none = sum(1 for r in defer_rows if r["new_match_status"] == "no_match")
    defer_now_unavailable = sum(1 for r in defer_rows if r["new_match_status"] == "unavailable")
    defer_new_correct = sum(1 for r in defer_rows if r["new_correct"])
    defer_old_correct = sum(1 for r in defer_rows if r["old_correct"])  # the historical 22/54
    defer_fallback_wrong_now_correct = sum(1 for r in defer_rows if not r["old_correct"] and r["new_correct"])
    defer_fallback_correct_now_wrong = sum(1 for r in defer_rows if r["old_correct"] and not r["new_correct"])
    defer_both_wrong = sum(1 for r in defer_rows if not r["old_correct"] and not r["new_correct"])
    defer_both_correct = sum(1 for r in defer_rows if r["old_correct"] and r["new_correct"])

    # ------------------------------------------------------------------
    # Section 26: the exact original 98 committed rows.
    # ------------------------------------------------------------------
    committed_ids = [sid for sid, r in rows.items() if r["was_original_committed_row"]]
    assert len(committed_ids) == 98, f"expected exactly 98 original committed rows, found {len(committed_ids)}"
    committed_rows = [rows[sid] for sid in committed_ids]
    committed_old_correct = sum(1 for r in committed_rows if r["old_correct"])  # the historical 83/98
    committed_new_correct = sum(1 for r in committed_rows if r["new_correct"])
    committed_wrong_now_correct = sum(1 for r in committed_rows if not r["old_correct"] and r["new_correct"])
    committed_correct_now_wrong = sum(1 for r in committed_rows if r["old_correct"] and not r["new_correct"])
    committed_both_wrong = sum(1 for r in committed_rows if not r["old_correct"] and not r["new_correct"])
    committed_both_correct = sum(1 for r in committed_rows if r["old_correct"] and r["new_correct"])

    # ------------------------------------------------------------------
    # Section 27: AI family (A101/A102/A103).
    # ------------------------------------------------------------------
    ai_rows = [r for r in rows.values() if r["reviewer_alpha"] in AI_ALPHA_IDS]
    ai_new_correct = [int(r["new_correct"]) for r in ai_rows]
    ai_by_alpha: dict[str, list[int]] = defaultdict(list)
    for r in ai_rows:
        ai_by_alpha[r["reviewer_alpha"]].append(int(r["new_correct"]))
    ai_previously_deferred = sum(1 for r in ai_rows if r["was_original_defer_row"])
    ai_now_selected = sum(1 for r in ai_rows if r["new_match_status"] == "matched")
    ai_now_none = sum(1 for r in ai_rows if r["new_match_status"] == "no_match")
    ai_confusion_within_family = Counter(
        (r["reviewer_alpha"], r["new_alpha"]) for r in ai_rows if r["new_alpha"] in AI_ALPHA_IDS and not r["new_correct"]
    )
    ai_confusion_outside_family = Counter(
        (r["reviewer_alpha"], r["new_alpha"])
        for r in ai_rows
        if r["new_alpha"] in {"A201", "A301", "A601", "A304"}
    )

    # ------------------------------------------------------------------
    # Section 28: MU ticker.
    # ------------------------------------------------------------------
    mu_rows = [r for r in rows.values() if r["ticker"] == "MU"]
    mu_new_correct = [int(r["new_correct"]) for r in mu_rows]
    mu_previous_defer_count = sum(1 for r in mu_rows if r["was_original_defer_row"])
    mu_new_none_count = sum(1 for r in mu_rows if r["new_match_status"] == "no_match")
    mu_reviewer_alpha_dist = Counter(r["reviewer_alpha"] for r in mu_rows)
    mu_system_alpha_dist = Counter(r["new_alpha"] for r in mu_rows)

    # ------------------------------------------------------------------
    # Section 29: NONE analysis.
    # ------------------------------------------------------------------
    system_none_rows = [r for r in rows.values() if r["new_alpha"] == "NONE" and r["new_match_status"] == "no_match"]
    reviewer_none_rows = [r for r in rows.values() if r["reviewer_alpha"] == "NONE"]
    none_none_correct = sum(1 for r in system_none_rows if r["reviewer_alpha"] == "NONE")
    system_none_reviewer_alpha = sum(1 for r in system_none_rows if r["reviewer_alpha"] != "NONE")
    system_alpha_reviewer_none = sum(
        1 for r in reviewer_none_rows if r["new_match_status"] == "matched"
    )
    unavailable_count = sum(1 for r in rows.values() if r["new_match_status"] == "unavailable")

    # ------------------------------------------------------------------
    # Write comparison CSV.
    # ------------------------------------------------------------------
    comparison_rows = [rows[sid] for sid in sorted(ids)]
    with COMPARISON_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        fieldnames = list(comparison_rows[0].keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(comparison_rows)

    metrics = {
        "task": "Alpha Mapper Pure-LLM Semantic Authority -- Holdout #3 Development Re-Evaluation",
        "is_blind_acceptance_result": False,
        "sample_count": n,
        "development_numerator": development_correct,
        "development_denominator": n,
        "development_alpha_match_accuracy": development_accuracy,
        "development_target": DEVELOPMENT_TARGET,
        "development_target_met": development_accuracy >= DEVELOPMENT_TARGET,
        "unavailable_count": unavailable_count,
        "unavailable_counts_as_wrong_for_accuracy": True,
        "original_holdout3_comparison": {
            "original_numerator": original_numerator,
            "original_denominator": original_denominator,
            "original_alpha_match_accuracy": original_accuracy,
            "deterministic_counterfactual_accuracy": deterministic_counterfactual_accuracy,
            "new_pure_llm_accuracy": development_accuracy,
            "absolute_percentage_point_change_vs_original": (development_accuracy - original_accuracy) * 100,
            "absolute_percentage_point_change_vs_deterministic_counterfactual": (
                development_accuracy - deterministic_counterfactual_accuracy
            )
            * 100,
        },
        "row_transitions": {
            "wrong_to_correct_count": len(wrong_to_correct),
            "correct_to_wrong_count": len(correct_to_wrong),
            "wrong_to_different_wrong_count": len(wrong_to_different_wrong),
            "unchanged_correct_count": len(unchanged_correct),
            "unchanged_wrong_count": len(unchanged_wrong),
            "wrong_to_correct_sample_ids": wrong_to_correct,
            "correct_to_wrong_sample_ids": correct_to_wrong,
        },
        "original_54_defer_rows_analysis": {
            "defer_row_count": len(defer_ids),
            "now_selected_count": defer_now_selected,
            "now_none_count": defer_now_none,
            "now_unavailable_count": defer_now_unavailable,
            "new_correct_count": defer_new_correct,
            "new_accuracy": defer_new_correct / len(defer_ids),
            "old_deterministic_fallback_correct_count": defer_old_correct,
            "old_deterministic_fallback_accuracy": defer_old_correct / len(defer_ids),
            "fallback_wrong_now_correct_count": defer_fallback_wrong_now_correct,
            "fallback_correct_now_wrong_count": defer_fallback_correct_now_wrong,
            "both_wrong_count": defer_both_wrong,
            "both_correct_count": defer_both_correct,
        },
        "original_98_committed_rows_analysis": {
            "committed_row_count": len(committed_ids),
            "old_correct_count": committed_old_correct,
            "old_accuracy": committed_old_correct / len(committed_ids),
            "new_correct_count": committed_new_correct,
            "new_accuracy": committed_new_correct / len(committed_ids),
            "wrong_now_correct_count": committed_wrong_now_correct,
            "correct_now_wrong_count": committed_correct_now_wrong,
            "both_wrong_count": committed_both_wrong,
            "both_correct_count": committed_both_correct,
        },
        "ai_family_analysis": {
            "reviewer_expected_ai_family_count": len(ai_rows),
            "new_accuracy_combined": _rate(ai_new_correct),
            "new_accuracy_by_alpha": {a: _rate(v) for a, v in sorted(ai_by_alpha.items())},
            "original_ai_family_accuracy": original_ai_family_accuracy,
            "previously_deferred_count": ai_previously_deferred,
            "now_selected_count": ai_now_selected,
            "now_none_count": ai_now_none,
            "confusion_within_ai_family": {f"{a}->{b}": c for (a, b), c in ai_confusion_within_family.items()},
            "confusion_into_a201_a301_a601_a304": {f"{a}->{b}": c for (a, b), c in ai_confusion_outside_family.items()},
        },
        "mu_ticker_analysis": {
            "mu_row_count": len(mu_rows),
            "new_accuracy": _rate(mu_new_correct),
            "original_mu_accuracy": original_mu_accuracy,
            "previous_defer_count": mu_previous_defer_count,
            "new_none_count": mu_new_none_count,
            "dominant_reviewer_alpha_families": mu_reviewer_alpha_dist.most_common(),
            "dominant_system_alpha_families": mu_system_alpha_dist.most_common(),
        },
        "none_analysis": {
            "system_none_count": len(system_none_rows),
            "reviewer_none_count": len(reviewer_none_rows),
            "none_none_correct_count": none_none_correct,
            "system_none_but_reviewer_alpha_count": system_none_reviewer_alpha,
            "system_alpha_but_reviewer_none_count": system_alpha_reviewer_none,
            "note": "NONE is a genuine semantic decision (no canonical Alpha materially fits), never a stand-in name for classifier uncertainty -- a high rate here is a semantic-behavior finding to analyze, not itself a defect.",
        },
    }
    METRICS_JSON_PATH.write_text(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"\nWrote {len(comparison_rows)} rows -> {COMPARISON_CSV_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
