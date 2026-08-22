#!/usr/bin/env python3
"""Blind Holdout #5: join the frozen review snapshot against the real
production Alpha/B1 system outputs and compute the formal Alpha Match
Accuracy (denominator 200) and Evidence Polarity Accuracy (denominator =
polarity-evaluable count only), plus all required diagnostics. Pure,
deterministic, offline arithmetic -- no Provider call.
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

FROZEN_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout5_frozen.csv"
REVIEW_FROZEN_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout5_review_frozen.csv"
SYSTEM_ALPHA_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout5_system_alpha.json"
SYSTEM_POLARITY_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout5_system_polarity.json"

COMPARISON_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout5_comparison.csv"
METRICS_JSON_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout5_metrics.json"

ALPHA_THRESHOLD = 0.75
POLARITY_THRESHOLD = 0.80
ALL_ALPHA_IDS_PLUS_NONE = ["A001", "A003", "A101", "A102", "A103", "A201", "A301", "A304", "A501", "A601", "NONE"]
VALID_STANCES = ["supports_alpha", "opposes_alpha", "mentions_alpha", "neutral_background", "supports_counter_alpha"]


def _norm_alpha(value: Any) -> str:
    if value is None:
        return "NONE"
    text = str(value).strip()
    return text if text else "NONE"


def _rate_table(d: dict[str, list[int]]) -> dict[str, dict[str, Any]]:
    return {k: {"correct": sum(v), "total": len(v), "accuracy": sum(v) / len(v)} for k, v in sorted(d.items())}


def main() -> int:
    with FROZEN_CSV_PATH.open(encoding="utf-8", newline="") as f:
        frozen = {r["sample_id"]: r for r in csv.DictReader(f)}
    with REVIEW_FROZEN_PATH.open(encoding="utf-8", newline="") as f:
        review = {r["sample_id"]: r for r in csv.DictReader(f)}
    system_alpha = json.loads(SYSTEM_ALPHA_PATH.read_text(encoding="utf-8"))
    system_polarity = json.loads(SYSTEM_POLARITY_PATH.read_text(encoding="utf-8")) if SYSTEM_POLARITY_PATH.exists() else {}

    ids = set(frozen)
    assert ids == set(review) == set(system_alpha), "sample_id set mismatch"
    n = len(ids)
    assert n == 200, f"expected 200 H5 rows, found {n}"

    alpha_correct = 0
    unavailable_count = 0
    confusion: dict[str, dict[str, int]] = {a: dict.fromkeys(ALL_ALPHA_IDS_PLUS_NONE, 0) for a in ALL_ALPHA_IDS_PLUS_NONE}
    by_ticker: dict[str, list[int]] = defaultdict(list)
    by_reviewed_alpha: dict[str, list[int]] = defaultdict(list)
    by_system_alpha: dict[str, list[int]] = defaultdict(list)

    system_none_reviewed_alpha = 0
    system_alpha_reviewed_none = 0
    system_alpha_a_reviewed_alpha_b = 0

    reviewed_none_count = 0
    reviewed_material_alpha_count = 0
    system_none_count = 0

    material_alpha_correct = 0

    comparison_rows: list[dict[str, Any]] = []

    for sid in sorted(ids):
        sys_row = system_alpha[sid]
        sys_alpha_id = _norm_alpha(sys_row.get("system_matched_alpha_id"))
        is_unavailable = sys_row.get("match_status") == "unavailable"
        rev = review[sid]
        material_fit = str(rev["human_material_alpha_fit"]).strip().lower() == "true"
        rev_alpha_id = _norm_alpha(rev["human_expected_alpha_id"])

        if is_unavailable:
            unavailable_count += 1
        is_correct = (not is_unavailable) and (sys_alpha_id == rev_alpha_id)
        alpha_correct += int(is_correct)
        confusion[sys_alpha_id][rev_alpha_id] += 1

        ticker = frozen[sid]["ticker"]
        by_ticker[ticker].append(int(is_correct))
        by_reviewed_alpha[rev_alpha_id].append(int(is_correct))
        by_system_alpha[sys_alpha_id].append(int(is_correct))

        if sys_alpha_id == "NONE" and not is_unavailable:
            system_none_count += 1
            if rev_alpha_id != "NONE":
                system_none_reviewed_alpha += 1
        if rev_alpha_id == "NONE":
            reviewed_none_count += 1
            if sys_alpha_id != "NONE" and not is_unavailable:
                system_alpha_reviewed_none += 1
        if sys_alpha_id != "NONE" and rev_alpha_id != "NONE" and sys_alpha_id != rev_alpha_id and not is_unavailable:
            system_alpha_a_reviewed_alpha_b += 1

        if material_fit:
            reviewed_material_alpha_count += 1
            material_alpha_correct += int(is_correct)

        sys_pol = system_polarity.get(sid)
        rev_polarity = rev.get("human_polarity") or ""
        comparison_rows.append(
            {
                "sample_id": sid, "ticker": ticker, "agent": frozen[sid]["agent"],
                "claim": frozen[sid]["claim"], "evidence": frozen[sid]["evidence"],
                "review_material_alpha_fit": material_fit, "review_expected_alpha_id": rev_alpha_id,
                "review_alpha_confidence": rev["human_alpha_confidence"],
                "system_matched_alpha_id": sys_alpha_id, "alpha_correct": is_correct,
                "review_polarity": rev_polarity if rev_alpha_id != "NONE" else "",
                "system_polarity": (sys_pol or {}).get("system_polarity") if sys_pol else "",
                "polarity_correct": (
                    (sys_pol or {}).get("system_polarity") == rev_polarity
                    if (rev_alpha_id != "NONE" and sys_pol is not None)
                    else ""
                ),
            }
        )

    alpha_accuracy = alpha_correct / n
    material_alpha_exact_accuracy = (material_alpha_correct / reviewed_material_alpha_count) if reviewed_material_alpha_count else None

    with COMPARISON_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        fieldnames = list(comparison_rows[0].keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(comparison_rows)

    polarity_section: dict[str, Any] = {"computed": False}
    if system_polarity:
        eval_ids = {sid for sid in ids if _norm_alpha(review[sid]["human_expected_alpha_id"]) != "NONE"}
        assert set(system_polarity.keys()) == eval_ids, "polarity system output set != polarity-evaluable review rows"
        n_polarity = len(eval_ids)

        polarity_correct = 0
        polarity_confusion = {s: dict.fromkeys(VALID_STANCES, 0) for s in VALID_STANCES}
        by_stance_class: dict[str, list[int]] = defaultdict(list)
        by_polarity_alpha: dict[str, list[int]] = defaultdict(list)
        by_polarity_ticker: dict[str, list[int]] = defaultdict(list)
        critical_reversal_ids: list[str] = []
        supports_counter_alpha_count = 0
        neutral_background_count = 0
        mentions_alpha_count = 0

        for sid in sorted(eval_ids):
            sys_p = system_polarity[sid]
            rev_stance = review[sid]["human_polarity"]
            sys_stance = sys_p.get("system_polarity")
            assert rev_stance in VALID_STANCES, f"{sid}: bad reviewed stance {rev_stance!r}"
            if sys_stance not in VALID_STANCES:
                continue
            polarity_confusion[sys_stance][rev_stance] += 1
            correct = sys_stance == rev_stance
            polarity_correct += int(correct)
            by_stance_class[rev_stance].append(int(correct))
            by_polarity_alpha[review[sid]["human_expected_alpha_id"]].append(int(correct))
            by_polarity_ticker[frozen[sid]["ticker"]].append(int(correct))
            if {sys_stance, rev_stance} == {"supports_alpha", "opposes_alpha"}:
                critical_reversal_ids.append(sid)
            if rev_stance == "supports_counter_alpha":
                supports_counter_alpha_count += 1
            if rev_stance == "neutral_background":
                neutral_background_count += 1
            if rev_stance == "mentions_alpha":
                mentions_alpha_count += 1

        polarity_accuracy = polarity_correct / n_polarity if n_polarity else None
        polarity_section = {
            "computed": True,
            "polarity_evaluable_denominator": n_polarity,
            "polarity_evaluable_denominator_source": "count(review.human_expected_alpha_id != NONE) over the 200 frozen H5 rows",
            "polarity_correct": polarity_correct,
            "polarity_accuracy": polarity_accuracy,
            "polarity_threshold": POLARITY_THRESHOLD,
            "polarity_target_met": (polarity_accuracy or 0) >= POLARITY_THRESHOLD,
            "confusion_matrix": {"axes": "rows=system_polarity, columns=review_polarity", "matrix": polarity_confusion},
            "accuracy_by_stance_class": _rate_table(by_stance_class),
            "accuracy_by_target_alpha": _rate_table(by_polarity_alpha),
            "accuracy_by_ticker": _rate_table(by_polarity_ticker),
            "critical_supports_opposes_reversal_count": len(critical_reversal_ids),
            "critical_reversal_sample_ids": critical_reversal_ids,
            "supports_counter_alpha_count": supports_counter_alpha_count,
            "neutral_background_count": neutral_background_count,
            "mentions_alpha_count": mentions_alpha_count,
        }

    metrics = {
        "task": "Blind Holdout #5 -- Alpha Match + Evidence Polarity Accuracy",
        "sample_count": n,
        "alpha_match_result": {
            "correct": alpha_correct, "total": n, "accuracy": alpha_accuracy,
            "accuracy_percent": round(alpha_accuracy * 100, 2),
            "threshold": ALPHA_THRESHOLD, "threshold_percent": ALPHA_THRESHOLD * 100,
            "target_met": alpha_accuracy >= ALPHA_THRESHOLD,
            "status": "pass" if alpha_accuracy >= ALPHA_THRESHOLD else "fail",
        },
        "alpha_confusion_matrix": {"axes": "rows=system_matched_alpha_id, columns=review_expected_alpha_id", "matrix": confusion},
        "alpha_accuracy_by_ticker": _rate_table(by_ticker),
        "alpha_accuracy_by_reviewed_alpha": _rate_table(by_reviewed_alpha),
        "alpha_accuracy_by_system_alpha": _rate_table(by_system_alpha),
        "diagnostic_error_buckets": {
            "system_none_reviewed_alpha": system_none_reviewed_alpha,
            "system_alpha_reviewed_none": system_alpha_reviewed_none,
            "system_alpha_a_reviewed_alpha_b": system_alpha_a_reviewed_alpha_b,
            "unavailable_count": unavailable_count,
        },
        "reviewed_none_count": reviewed_none_count,
        "reviewed_material_alpha_count": reviewed_material_alpha_count,
        "system_none_count": system_none_count,
        "material_alpha_subset_diagnostic": {
            "description": "Diagnostic only -- does NOT replace the formal 200-row Alpha Match metric.",
            "material_alpha_count": reviewed_material_alpha_count,
            "material_alpha_correct": material_alpha_correct,
            "material_alpha_exact_accuracy": material_alpha_exact_accuracy,
        },
        "polarity": polarity_section,
    }
    METRICS_JSON_PATH.write_text(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"\nWrote {len(comparison_rows)} rows -> {COMPARISON_CSV_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
