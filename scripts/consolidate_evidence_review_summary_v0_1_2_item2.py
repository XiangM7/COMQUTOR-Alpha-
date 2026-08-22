#!/usr/bin/env python3
"""v0.1.2 QA Closure, Item 2: additive consolidation only.

Adds a clearly-labeled, separately-scoped block to the existing, already-
committed ``evidence_review_summary.json`` (the 50-sample provisional
review from commit "QA Closure v0.1.2") describing the LATER 200-row
development re-review of the Blind Holdout #4 dataset. Does not touch,
rename, or recompute any existing top-level field in that file -- the
original 50-sample result (alpha_match_accuracy=0.72 FAIL, polarity_
accuracy=0.78 FAIL) stays exactly as committed.

Pure, deterministic, offline consolidation: reads two already-frozen
files and copies values across (with a validation check that they match
the expected figures) -- no Provider call, no re-review, no re-scoring,
no production code touched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

EXISTING_SUMMARY_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "evidence_review_summary.json"
DEV_METRICS_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_h4_reviewer_v2_dev_metrics.json"

NEW_BLOCK_KEY = "item2_200row_development_re_review"

EXPECTED_ALPHA = (154, 200, 77.00)
EXPECTED_POLARITY = (39, 47, 82.98)


class ConsolidationError(Exception):
    pass


def _round2(x: float) -> float:
    return round(x * 100, 2)


def main() -> int:
    existing = json.loads(EXISTING_SUMMARY_PATH.read_text(encoding="utf-8"))
    dev = json.loads(DEV_METRICS_PATH.read_text(encoding="utf-8"))

    if NEW_BLOCK_KEY in existing:
        raise ConsolidationError(f"{NEW_BLOCK_KEY} already present -- refusing to silently overwrite")

    alpha = dev["alpha_v2_development_result"]
    polarity = dev["polarity"]
    formal_h4 = dev["original_h4_formal_result"]

    alpha_tuple = (alpha["numerator"], alpha["denominator"], _round2(alpha["accuracy"]))
    polarity_tuple = (polarity["polarity_correct"], polarity["polarity_evaluable_denominator"], _round2(polarity["polarity_accuracy"]))
    if alpha_tuple != EXPECTED_ALPHA:
        raise ConsolidationError(f"alpha figures {alpha_tuple} != expected {EXPECTED_ALPHA}")
    if polarity_tuple != EXPECTED_POLARITY:
        raise ConsolidationError(f"polarity figures {polarity_tuple} != expected {EXPECTED_POLARITY}")

    new_block: dict[str, Any] = {
        "status": (
            "DEVELOPMENT RE-REVIEW -- NOT a formal QA acceptance result. "
            "Does not supersede, replace, or overwrite the formal Blind Holdout #4 "
            "acceptance result recorded below, nor the separate 50-sample provisional "
            "result recorded elsewhere in this file."
        ),
        "dataset": "docs/audit_artifacts/item2_blind_holdout4_frozen.csv (200-row blind holdout set)",
        "review_method": "corrected two-stage material-fit review protocol applied to the same frozen 200-row dataset",
        "formal_blind_holdout4_result": {
            "correct": formal_h4["numerator"],
            "total": formal_h4["denominator"],
            "accuracy": formal_h4["accuracy"],
            "accuracy_percent": _round2(formal_h4["accuracy"]),
            "threshold_percent": _round2(formal_h4["threshold"]),
            "status": "fail",
            "note": "Official acceptance-test result for this 200-row dataset. Unchanged, not overwritten by the development figures below.",
        },
        "alpha_match": {
            "correct": alpha["numerator"],
            "total": alpha["denominator"],
            "accuracy": alpha["accuracy"],
            "accuracy_percent": _round2(alpha["accuracy"]),
            "threshold_percent": _round2(alpha["threshold"]),
            "status": "pass",
            "note": "Development re-review figure, evaluated against all 200 rows. Not a formal acceptance-test result.",
        },
        "evidence_polarity": {
            "correct": polarity["polarity_correct"],
            "total": polarity["polarity_evaluable_denominator"],
            "accuracy": polarity["polarity_accuracy"],
            "accuracy_percent": _round2(polarity["polarity_accuracy"]),
            "threshold_percent": _round2(polarity["polarity_threshold"]),
            "status": "pass",
            "note": (
                "Evaluated only on the 47 of 200 rows where the development re-review found a "
                "materially-fitting Alpha; the remaining 153 rows had no material fit (NONE) and are "
                "not polarity-evaluable. Not a formal acceptance-test result."
            ),
        },
        "semantic_review_rule": (
            "Evidence is assigned to an Alpha only when it materially represents the "
            "Alpha's underlying causal/economic mechanism; evidence with no material fit "
            "remains NONE."
        ),
        "source_files": {
            "development_metrics": "docs/audit_artifacts/item2_h4_reviewer_v2_dev_metrics.json",
            "development_report": "docs/audit_artifacts/item2_h4_reviewer_v2_dev_report.md",
            "holdout_dataset": "docs/audit_artifacts/item2_blind_holdout4_frozen.csv",
        },
        "human_review_performed": False,
        "approved": False,
    }

    existing[NEW_BLOCK_KEY] = new_block
    EXISTING_SUMMARY_PATH.write_text(json.dumps(existing, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Added '{NEW_BLOCK_KEY}' block -> {EXISTING_SUMMARY_PATH}")
    print(json.dumps(new_block, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
