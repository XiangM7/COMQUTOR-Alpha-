#!/usr/bin/env python3
"""H4 Reviewer-v2 Development Re-Review: join all frozen/produced inputs and
compute the DEVELOPMENT Alpha match metric, reviewer label drift analysis,
the 12-case A601 disposition, and the DEVELOPMENT B1 polarity metric. Pure,
deterministic, offline arithmetic -- no Provider call. Does not overwrite
or alter any original H4 formal artifact.
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
ORIGINAL_ALPHA_REVIEW_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout4_alpha_review.json"
SYSTEM_ALPHA_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout4_system_alpha.json"
REVIEWER_V2_ALPHA_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_h4_reviewer_v2_dev_alpha_review.json"
POLARITY_REVIEW_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_h4_reviewer_v2_dev_polarity_review.json"
POLARITY_SYSTEM_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_h4_reviewer_v2_dev_polarity_system.json"

ALPHA_COMPARISON_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_h4_reviewer_v2_dev_alpha_comparison.csv"
METRICS_JSON_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_h4_reviewer_v2_dev_metrics.json"

ALPHA_THRESHOLD = 0.75
POLARITY_THRESHOLD = 0.80
ALL_ALPHA_IDS_PLUS_NONE = ["A001", "A003", "A101", "A102", "A103", "A201", "A301", "A304", "A501", "A601", "NONE"]
VALID_STANCES = ["supports_alpha", "opposes_alpha", "mentions_alpha", "neutral_background", "supports_counter_alpha"]

# Historical context only -- fixed facts, not recomputed.
ORIGINAL_H4_NUMERATOR = 148
ORIGINAL_H4_DENOMINATOR = 200
ORIGINAL_H4_ACCURACY = ORIGINAL_H4_NUMERATOR / ORIGINAL_H4_DENOMINATOR
FORMAL_B1_H2_NUMERATOR = 123
FORMAL_B1_H2_DENOMINATOR = 141
FORMAL_B1_H2_ACCURACY = FORMAL_B1_H2_NUMERATOR / FORMAL_B1_H2_DENOMINATOR

A601_CASE_SAMPLE_IDS = [
    "holdout4-008", "holdout4-033", "holdout4-036", "holdout4-053", "holdout4-054", "holdout4-060",
    "holdout4-094", "holdout4-114", "holdout4-119", "holdout4-126", "holdout4-175", "holdout4-199",
]


def _norm_alpha(value: Any) -> str:
    if value is None:
        return "NONE"
    text = str(value).strip()
    return text if text else "NONE"


def _rate(flags: list[int]) -> dict[str, Any]:
    return {"correct": sum(flags), "total": len(flags), "accuracy": (sum(flags) / len(flags)) if flags else None}


def main() -> int:
    with FROZEN_CSV_PATH.open(encoding="utf-8", newline="") as f:
        frozen = {r["sample_id"]: r for r in csv.DictReader(f)}
    original_review = json.loads(ORIGINAL_ALPHA_REVIEW_PATH.read_text(encoding="utf-8"))
    system_alpha = json.loads(SYSTEM_ALPHA_PATH.read_text(encoding="utf-8"))
    reviewer_v2 = json.loads(REVIEWER_V2_ALPHA_PATH.read_text(encoding="utf-8"))

    ids = set(frozen)
    assert ids == set(original_review) == set(system_alpha) == set(reviewer_v2), "sample_id set mismatch"
    n = len(ids)
    assert n == 200, f"expected 200 H4 rows, found {n}"

    # ------------------------------------------------------------------
    # Section 13: new Alpha match metric (system vs reviewer-v2).
    # ------------------------------------------------------------------
    alpha_correct = 0
    confusion: dict[str, dict[str, int]] = {a: dict.fromkeys(ALL_ALPHA_IDS_PLUS_NONE, 0) for a in ALL_ALPHA_IDS_PLUS_NONE}
    by_ticker: dict[str, list[int]] = defaultdict(list)
    by_reviewer_v2_alpha: dict[str, list[int]] = defaultdict(list)
    by_system_alpha: dict[str, list[int]] = defaultdict(list)

    system_none_count = 0
    reviewer_v2_none_count = 0
    none_none_correct = 0
    system_alpha_reviewer_v2_none = 0
    system_none_reviewer_v2_alpha = 0

    old_system_none_reviewer_alpha_ids = set()  # original 26-row bucket, for direct pre/post comparison
    new_system_none_reviewer_v2_alpha_ids = set()
    old_system_alpha_reviewer_none_ids = set()
    new_system_alpha_reviewer_v2_none_ids = set()

    ai_rows = []
    alpha_comparison_rows: list[dict[str, Any]] = []

    for sid in sorted(ids):
        sys_row = system_alpha[sid]
        sys_alpha_id = _norm_alpha(sys_row.get("system_matched_alpha_id"))
        is_unavailable = sys_row.get("match_status") == "unavailable"
        v2 = reviewer_v2[sid]
        v2_alpha_id = _norm_alpha(v2["reviewer_v2_expected_alpha_id"])
        orig = original_review[sid]
        orig_alpha_id = _norm_alpha(orig["reviewer_expected_alpha_id"])

        is_correct = (not is_unavailable) and (sys_alpha_id == v2_alpha_id)
        alpha_correct += int(is_correct)
        confusion[sys_alpha_id][v2_alpha_id] += 1

        ticker = frozen[sid]["ticker"]
        by_ticker[ticker].append(int(is_correct))
        by_reviewer_v2_alpha[v2_alpha_id].append(int(is_correct))
        by_system_alpha[sys_alpha_id].append(int(is_correct))

        if v2_alpha_id in AI_ALPHA_IDS:
            ai_rows.append({"sample_id": sid, "reviewer_v2_alpha": v2_alpha_id, "system_alpha": sys_alpha_id, "correct": is_correct})

        if sys_alpha_id == "NONE" and not is_unavailable:
            system_none_count += 1
            if v2_alpha_id == "NONE":
                none_none_correct += 1
            else:
                system_none_reviewer_v2_alpha += 1
                new_system_none_reviewer_v2_alpha_ids.add(sid)
        if v2_alpha_id == "NONE":
            reviewer_v2_none_count += 1
            if sys_alpha_id != "NONE" and not is_unavailable:
                system_alpha_reviewer_v2_none += 1
                new_system_alpha_reviewer_v2_none_ids.add(sid)

        if sys_alpha_id == "NONE" and not is_unavailable and orig_alpha_id != "NONE":
            old_system_none_reviewer_alpha_ids.add(sid)
        if sys_alpha_id != "NONE" and not is_unavailable and orig_alpha_id == "NONE":
            old_system_alpha_reviewer_none_ids.add(sid)

        alpha_comparison_rows.append(
            {
                "sample_id": sid, "ticker": ticker, "claim_id": frozen[sid]["claim_id"],
                "system_matched_alpha_id": sys_alpha_id, "match_status": sys_row.get("match_status"),
                "original_reviewer_expected_alpha_id": orig_alpha_id, "original_reviewer_confidence": orig["confidence"],
                "reviewer_v2_material_fit": v2["reviewer_v2_material_fit"],
                "reviewer_v2_expected_alpha_id": v2_alpha_id, "reviewer_v2_alpha_confidence": v2["reviewer_v2_alpha_confidence"],
                "alpha_v2_correct": is_correct,
                "label_changed_orig_to_v2": orig_alpha_id != v2_alpha_id,
            }
        )

    alpha_v2_accuracy = alpha_correct / n

    def _rate_table(d: dict[str, list[int]]) -> dict[str, dict[str, Any]]:
        return {k: {"correct": sum(v), "total": len(v), "accuracy": sum(v) / len(v)} for k, v in sorted(d.items())}

    with ALPHA_COMPARISON_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        fieldnames = list(alpha_comparison_rows[0].keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(alpha_comparison_rows)

    # ------------------------------------------------------------------
    # Section 14: reviewer label drift analysis.
    # ------------------------------------------------------------------
    orig_alpha_dist = Counter(_norm_alpha(v["reviewer_expected_alpha_id"]) for v in original_review.values())
    v2_alpha_dist = Counter(_norm_alpha(v["reviewer_v2_expected_alpha_id"]) for v in reviewer_v2.values())

    labels_unchanged = labels_changed = 0
    old_alpha_to_none = old_none_to_alpha = old_alpha_to_diff_alpha = 0
    changed_by_orig_confidence: dict[str, int] = defaultdict(int)
    total_by_orig_confidence: dict[str, int] = defaultdict(int)

    for sid in ids:
        orig_alpha = _norm_alpha(original_review[sid]["reviewer_expected_alpha_id"])
        v2_alpha = _norm_alpha(reviewer_v2[sid]["reviewer_v2_expected_alpha_id"])
        orig_conf = original_review[sid]["confidence"]
        total_by_orig_confidence[orig_conf] += 1
        if orig_alpha == v2_alpha:
            labels_unchanged += 1
            continue
        labels_changed += 1
        changed_by_orig_confidence[orig_conf] += 1
        if orig_alpha != "NONE" and v2_alpha == "NONE":
            old_alpha_to_none += 1
        elif orig_alpha == "NONE" and v2_alpha != "NONE":
            old_none_to_alpha += 1
        elif orig_alpha != "NONE" and v2_alpha != "NONE":
            old_alpha_to_diff_alpha += 1

    # ------------------------------------------------------------------
    # Section 15: the 12 prior "system NONE / original reviewer A601" cases.
    # ------------------------------------------------------------------
    a601_case_studies = []
    verified_case_ids = []
    for sid in A601_CASE_SAMPLE_IDS:
        if sid not in ids:
            continue
        sys_row = system_alpha[sid]
        orig = original_review[sid]
        v2 = reviewer_v2[sid]
        actually_matches_expected_pattern = (
            _norm_alpha(sys_row.get("system_matched_alpha_id")) == "NONE"
            and sys_row.get("match_status") != "unavailable"
            and _norm_alpha(orig["reviewer_expected_alpha_id"]) == "A601"
        )
        if actually_matches_expected_pattern:
            verified_case_ids.append(sid)
        a601_case_studies.append(
            {
                "sample_id": sid,
                "matches_expected_system_none_original_a601_pattern": actually_matches_expected_pattern,
                "ticker": frozen[sid]["ticker"],
                "claim": frozen[sid]["claim"],
                "evidence": frozen[sid]["evidence"],
                "original_reviewer_alpha": _norm_alpha(orig["reviewer_expected_alpha_id"]),
                "original_reviewer_confidence": orig["confidence"],
                "reviewer_v2_material_fit": v2["reviewer_v2_material_fit"],
                "reviewer_v2_alpha": _norm_alpha(v2["reviewer_v2_expected_alpha_id"]),
                "reviewer_v2_confidence": v2["reviewer_v2_alpha_confidence"],
                "system_alpha": _norm_alpha(sys_row.get("system_matched_alpha_id")),
                "changed_from_original": _norm_alpha(orig["reviewer_expected_alpha_id"]) != _norm_alpha(v2["reviewer_v2_expected_alpha_id"]),
                "reviewer_v2_reason": v2["reviewer_v2_alpha_reason"],
            }
        )

    # AI family diagnostic (vs reviewer-v2, descriptive).
    ai_by_alpha: dict[str, list[int]] = defaultdict(list)
    for r in ai_rows:
        ai_by_alpha[r["reviewer_v2_alpha"]].append(int(r["correct"]))

    # ------------------------------------------------------------------
    # Polarity phase (sections 16-21), only if the polarity artifacts exist.
    # ------------------------------------------------------------------
    polarity_section: dict[str, Any] = {"computed": False}
    if POLARITY_REVIEW_PATH.exists() and POLARITY_SYSTEM_PATH.exists():
        polarity_review = json.loads(POLARITY_REVIEW_PATH.read_text(encoding="utf-8"))
        polarity_system = json.loads(POLARITY_SYSTEM_PATH.read_text(encoding="utf-8"))
        eval_ids = set(polarity_review)
        assert eval_ids == set(polarity_system), "polarity sample_id set mismatch between reviewer and system"
        expected_eval_ids = {sid for sid in ids if reviewer_v2[sid]["reviewer_v2_material_fit"]}
        assert eval_ids == expected_eval_ids, "polarity-evaluable set does not match reviewer_v2_material_fit=true rows"
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
        polarity_comparison_rows: list[dict[str, Any]] = []

        for sid in sorted(eval_ids):
            sys_p = polarity_system[sid]
            rev_p = polarity_review[sid]
            sys_stance = sys_p["system_b1_stance"]
            rev_stance = rev_p["reviewer_v2_b1_stance"]
            assert sys_stance in VALID_STANCES, f"{sid}: bad system stance {sys_stance!r}"
            assert rev_stance in VALID_STANCES, f"{sid}: bad reviewer stance {rev_stance!r}"
            polarity_confusion[sys_stance][rev_stance] += 1
            correct = sys_stance == rev_stance
            polarity_correct += int(correct)
            by_stance_class[rev_stance].append(int(correct))
            by_polarity_alpha[reviewer_v2[sid]["reviewer_v2_expected_alpha_id"]].append(int(correct))
            by_polarity_ticker[frozen[sid]["ticker"]].append(int(correct))
            if {sys_stance, rev_stance} == {"supports_alpha", "opposes_alpha"}:
                critical_reversal_ids.append(sid)
            if rev_stance == "supports_counter_alpha":
                supports_counter_alpha_count += 1
            if rev_stance == "neutral_background":
                neutral_background_count += 1
            if rev_stance == "mentions_alpha":
                mentions_alpha_count += 1
            polarity_comparison_rows.append(
                {
                    "sample_id": sid, "ticker": frozen[sid]["ticker"], "target_alpha_id": reviewer_v2[sid]["reviewer_v2_expected_alpha_id"],
                    "system_b1_stance": sys_stance, "reviewer_v2_b1_stance": rev_stance, "polarity_correct": correct,
                    "system_b1_stance_method": sys_p.get("system_b1_stance_method"),
                }
            )

        polarity_accuracy = polarity_correct / n_polarity if n_polarity else None
        polarity_section = {
            "computed": True,
            "polarity_evaluable_denominator": n_polarity,
            "polarity_evaluable_denominator_source": "count(reviewer_v2_material_fit == true) over the 200 frozen H4 rows",
            "polarity_correct": polarity_correct,
            "polarity_accuracy": polarity_accuracy,
            "polarity_threshold": POLARITY_THRESHOLD,
            "development_polarity_target_met": (polarity_accuracy or 0) >= POLARITY_THRESHOLD,
            "confusion_matrix": {"axes": "rows=system_b1_stance, columns=reviewer_v2_b1_stance", "matrix": polarity_confusion},
            "accuracy_by_stance_class": _rate_table(by_stance_class),
            "accuracy_by_target_alpha": _rate_table(by_polarity_alpha),
            "accuracy_by_ticker": _rate_table(by_polarity_ticker),
            "critical_supports_opposes_reversal_count": len(critical_reversal_ids),
            "critical_reversal_sample_ids": critical_reversal_ids,
            "supports_counter_alpha_count": supports_counter_alpha_count,
            "neutral_background_count": neutral_background_count,
            "mentions_alpha_count": mentions_alpha_count,
        }
        polarity_comparison_path = REPO_ROOT / "docs" / "audit_artifacts" / "item2_h4_reviewer_v2_dev_polarity_comparison.csv"
        with polarity_comparison_path.open("w", encoding="utf-8", newline="") as f:
            fieldnames = list(polarity_comparison_rows[0].keys())
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(polarity_comparison_rows)

    metrics = {
        "task": "H4 Reviewer-v2 Development Re-Review -- Alpha Match + B1 Polarity Joint Evaluation",
        "status": "DEVELOPMENT RE-EVALUATION -- NOT A NEW BLIND HOLDOUT",
        "sample_count": n,
        "original_h4_formal_result": {
            "numerator": ORIGINAL_H4_NUMERATOR, "denominator": ORIGINAL_H4_DENOMINATOR,
            "accuracy": ORIGINAL_H4_ACCURACY, "threshold": ALPHA_THRESHOLD, "verdict": "FAIL",
            "note": "UNCHANGED. This development re-review does not retroactively alter the formal H4 verdict.",
        },
        "alpha_v2_development_result": {
            "numerator": alpha_correct, "denominator": n, "accuracy": alpha_v2_accuracy,
            "threshold": ALPHA_THRESHOLD, "development_target_met": alpha_v2_accuracy >= ALPHA_THRESHOLD,
            "delta_percentage_points_vs_original_h4": (alpha_v2_accuracy - ORIGINAL_H4_ACCURACY) * 100,
        },
        "alpha_confusion_matrix": {"axes": "rows=system_matched_alpha_id, columns=reviewer_v2_expected_alpha_id", "matrix": confusion},
        "alpha_accuracy_by_ticker": _rate_table(by_ticker),
        "alpha_accuracy_by_reviewer_v2_alpha": _rate_table(by_reviewer_v2_alpha),
        "alpha_accuracy_by_system_alpha": _rate_table(by_system_alpha),
        "ai_family_accuracy_vs_reviewer_v2": {
            "combined": _rate([int(r["correct"]) for r in ai_rows]),
            "by_alpha": {a: _rate(v) for a, v in sorted(ai_by_alpha.items())},
        },
        "none_analysis": {
            "system_none_count": system_none_count,
            "reviewer_v2_none_count": reviewer_v2_none_count,
            "none_none_correct_count": none_none_correct,
            "system_alpha_but_reviewer_v2_none_count": system_alpha_reviewer_v2_none,
            "system_none_but_reviewer_v2_alpha_count": system_none_reviewer_v2_alpha,
        },
        "over_abstention_before_after_comparison": {
            "description": "Section 4 of this task's own directive: did the system's apparent over-abstention (system NONE / reviewer Alpha) survive the reviewer-protocol fix?",
            "original_system_none_reviewer_alpha_count": len(old_system_none_reviewer_alpha_ids),
            "reviewer_v2_system_none_reviewer_v2_alpha_count": len(new_system_none_reviewer_v2_alpha_ids),
            "original_system_alpha_reviewer_none_count": len(old_system_alpha_reviewer_none_ids),
            "reviewer_v2_system_alpha_reviewer_v2_none_count": len(new_system_alpha_reviewer_v2_none_ids),
        },
        "reviewer_label_drift": {
            "original_reviewer_alpha_distribution": dict(orig_alpha_dist.most_common()),
            "reviewer_v2_alpha_distribution": dict(v2_alpha_dist.most_common()),
            "original_reviewer_none_count": orig_alpha_dist.get("NONE", 0),
            "reviewer_v2_none_count": v2_alpha_dist.get("NONE", 0),
            "original_reviewer_a601_count": orig_alpha_dist.get("A601", 0),
            "reviewer_v2_a601_count": v2_alpha_dist.get("A601", 0),
            "labels_unchanged": labels_unchanged,
            "labels_changed": labels_changed,
            "old_alpha_to_new_none": old_alpha_to_none,
            "old_none_to_new_alpha": old_none_to_alpha,
            "old_alpha_to_different_new_alpha": old_alpha_to_diff_alpha,
            "labels_changed_by_original_confidence": dict(changed_by_orig_confidence),
            "labels_total_by_original_confidence": dict(total_by_orig_confidence),
        },
        "a601_twelve_case_disposition": {
            "requested_sample_ids": A601_CASE_SAMPLE_IDS,
            "sample_ids_verified_present_in_h4": [c["sample_id"] for c in a601_case_studies],
            "sample_ids_actually_matching_system_none_original_a601_pattern": verified_case_ids,
            "count_matching_expected_pattern": len(verified_case_ids),
            "note": "Verified from artifacts, not blindly trusted from the task's own suggested ID list (task spec section 15's own instruction).",
            "cases": a601_case_studies,
        },
        "polarity": polarity_section,
        "formal_b1_holdout2_historical": {
            "numerator": FORMAL_B1_H2_NUMERATOR, "denominator": FORMAL_B1_H2_DENOMINATOR,
            "accuracy": FORMAL_B1_H2_ACCURACY, "threshold": POLARITY_THRESHOLD, "verdict": "PASS",
            "note": "UNCHANGED historical formal result. Not replaced by this development polarity evaluation.",
        },
    }
    METRICS_JSON_PATH.write_text(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"\nWrote {len(alpha_comparison_rows)} rows -> {ALPHA_COMPARISON_CSV_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
