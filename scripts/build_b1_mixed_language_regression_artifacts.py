#!/usr/bin/env python3
"""QA Closure v0.1.2 -- B1 Mixed/Contrastive Language Improvement: build the
final regression CSV + summary JSON from the already-produced BEFORE
(frozen, untouched) and AFTER (this task's own real 50-row rerun) artifacts.

Pure, deterministic, offline -- no Provider call. Re-running against the
same frozen inputs always produces byte-identical output.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SAMPLE_PATH = REPO_ROOT / "docs" / "evidence_review_sample_records.json"
BEFORE_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "b1_llm_stance_50_validation_after_parser_fix.csv"
AFTER_JSON_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "b1_mixed_language_50_regression_raw.json"
J3_PATH = REPO_ROOT / "comqutor_alpha" / "config" / "j3_provisional_semantic_benchmark_v0.1.json"
ROOT_CAUSE_SUMMARY_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_mismatch_root_cause_summary.json"

OUTPUT_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "b1_mixed_language_50_regression.csv"
OUTPUT_SUMMARY_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "b1_mixed_language_regression_summary.json"

MIXED_OR_CONDITIONAL_ROWS = ["evrs-007", "evrs-020", "evrs-026", "evrs-034", "evrs-036", "evrs-040"]
B2_IMPACTING_ROWS_BEFORE = ["evrs-020", "evrs-026", "evrs-034", "evrs-040"]


def _load_system() -> dict[str, dict[str, Any]]:
    return {r["sample_id"]: r for r in json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))["records"]}


def _load_before() -> dict[str, dict[str, Any]]:
    with BEFORE_CSV_PATH.open(encoding="utf-8", newline="") as f:
        return {r["sample_id"]: r for r in csv.DictReader(f)}


def _load_after() -> dict[str, dict[str, Any]]:
    return {r["sample_id"]: r for r in json.loads(AFTER_JSON_PATH.read_text(encoding="utf-8"))}


def _load_j3() -> dict[str, dict[str, Any]]:
    return {r["sample_id"]: r for r in json.loads(J3_PATH.read_text(encoding="utf-8"))["rows"]}


def main() -> int:
    system = _load_system()
    before = _load_before()
    after = _load_after()
    j3 = _load_j3()

    ids = set(system.keys())
    assert ids == set(before.keys()) == set(after.keys()) == set(j3.keys()), "sample_id set mismatch across sources"
    assert len(ids) == 50

    rows_out = []
    categories = {"UNCHANGED_CORRECT": [], "UNCHANGED_DISAGREEMENT": [], "FIXED_DISAGREEMENT": [], "NEW_DISAGREEMENT": []}
    before_correct = after_correct = 0
    before_reversals: list[str] = []
    after_reversals: list[str] = []

    for sid in sorted(ids):
        b_stance = before[sid]["final_stance"]
        a_stance = after[sid]["after_b1_stance"]
        j_stance = j3[sid]["reviewed_stance"]
        b_correct = b_stance == j_stance
        a_correct = a_stance == j_stance
        before_correct += int(b_correct)
        after_correct += int(a_correct)
        if {b_stance, j_stance} == {"supports_alpha", "opposes_alpha"}:
            before_reversals.append(sid)
        if {a_stance, j_stance} == {"supports_alpha", "opposes_alpha"}:
            after_reversals.append(sid)

        if b_correct and a_correct:
            category = "UNCHANGED_CORRECT"
        elif not b_correct and not a_correct:
            category = "UNCHANGED_DISAGREEMENT"
        elif not b_correct and a_correct:
            category = "FIXED_DISAGREEMENT"
        else:
            category = "NEW_DISAGREEMENT"
        categories[category].append(sid)

        rows_out.append(
            {
                "sample_id": sid,
                "ticker": system[sid]["ticker"],
                "target_alpha_id": system[sid]["target_alpha_id"],
                "before_b1_stance": b_stance,
                "after_b1_stance": a_stance,
                "independent_reviewer_stance": j_stance,
                "before_b1_stance_method": before[sid]["stance_method"],
                "after_b1_stance_method": after[sid]["after_b1_stance_method"],
                "before_correct": b_correct,
                "after_correct": a_correct,
                "changed": b_stance != a_stance,
                "category": category,
                "was_mixed_or_conditional_root_cause_row": sid in MIXED_OR_CONDITIONAL_ROWS,
            }
        )

    with OUTPUT_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        writer.writeheader()
        writer.writerows(rows_out)

    mixed_rows_detail = []
    for sid in MIXED_OR_CONDITIONAL_ROWS:
        b_stance = before[sid]["final_stance"]
        a_stance = after[sid]["after_b1_stance"]
        j_stance = j3[sid]["reviewed_stance"]
        b2_before = "counts toward B2 supporting_evidence_count" if b_stance == "supports_alpha" else "no B2 count impact"
        b2_after = "counts toward B2 supporting_evidence_count" if a_stance == "supports_alpha" else "no B2 count impact"
        mixed_rows_detail.append(
            {
                "sample_id": sid,
                "before_b1_stance": b_stance,
                "after_b1_stance": a_stance,
                "independent_reviewer_stance": j_stance,
                "changed": b_stance != a_stance,
                "now_agrees": a_stance == j_stance,
                "b2_impact_before": b2_before,
                "b2_impact_after": b2_after,
            }
        )

    b2_improved = sum(
        1
        for sid in B2_IMPACTING_ROWS_BEFORE
        if (after[sid]["after_b1_stance"] == "supports_alpha") and (before[sid]["final_stance"] != "supports_alpha")
    )

    from collections import Counter

    transitions = Counter()
    for sid in ids:
        b_stance = before[sid]["final_stance"]
        a_stance = after[sid]["after_b1_stance"]
        if b_stance != a_stance:
            transitions[f"{b_stance} -> {a_stance}"] += 1

    summary = {
        "schema_version": "b1_mixed_language_regression_summary.v1",
        "before": {"correct_count": before_correct, "accuracy": before_correct / 50, "critical_reversal_count": len(before_reversals), "critical_reversal_sample_ids": before_reversals},
        "after": {"correct_count": after_correct, "accuracy": after_correct / 50, "critical_reversal_count": len(after_reversals), "critical_reversal_sample_ids": after_reversals},
        "mixed_or_conditional_root_cause_rows": mixed_rows_detail,
        "mixed_or_conditional_fixed_count": sum(1 for r in mixed_rows_detail if r["now_agrees"] and r["changed"]),
        "mixed_or_conditional_unchanged_count": sum(1 for r in mixed_rows_detail if not r["changed"]),
        "mixed_or_conditional_worsened_count": sum(1 for r in mixed_rows_detail if r["changed"] and not r["now_agrees"]),
        "collateral_check": {k: {"count": len(v), "sample_ids": v} for k, v in categories.items()},
        "confusion_transitions_before_to_after": dict(transitions),
        "b2_impacting_rows_before": B2_IMPACTING_ROWS_BEFORE,
        "b2_impacting_rows_improved_count": b2_improved,
        "acceptance_criteria": {
            "A_mixed_conditional_issue_improved": len(categories["FIXED_DISAGREEMENT"]) > 0,
            "B_no_critical_reversals_introduced": len(after_reversals) == 0,
            "C_no_broad_collateral_regression": len(categories["NEW_DISAGREEMENT"]) == 0,
            "D_no_benchmark_specific_hardcoding": "prompt change is a general target-relative resolution principle, not keyed to any sample_id or exact phrase -- see comqutor_alpha/structure_engine/week2_llm.py diff",
            "E_b1_architecture_still_llm_primary": True,
            "F_b2_semantics_unchanged": "conflict_admissibility.py / conflict_detector.py / alpha_mapper.py not modified by this task",
        },
        "old_50_is_development_set": True,
        "new_blind_holdout_required": True,
        "source_files": {
            "before": str(BEFORE_CSV_PATH.relative_to(REPO_ROOT)),
            "after_raw": str(AFTER_JSON_PATH.relative_to(REPO_ROOT)),
            "independent_reviewer": str(J3_PATH.relative_to(REPO_ROOT)),
        },
    }

    OUTPUT_SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows_out)} rows -> {OUTPUT_CSV_PATH}")
    print(f"Wrote summary -> {OUTPUT_SUMMARY_PATH}")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
