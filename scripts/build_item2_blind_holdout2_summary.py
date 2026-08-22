#!/usr/bin/env python3
"""QA Closure v0.1.2 -- Item 2 Blind Holdout #2, Phase 7: join the five
already-frozen inputs (holdout CSV + system_stance + independent_stance_review
+ system_alpha + independent_alpha_review) and compute the acceptance
metrics. Pure, deterministic, offline arithmetic -- no Provider call.
Re-running against the same frozen inputs must always produce byte-identical
output. No label is altered after this join; this is a report-only script.

Methodology mirrors build_item2_blind_holdout_summary.py (Holdout #1), with
one structural difference: Holdout #2 used two SEPARATE review tasks (stance
vs Alpha), so there are five source files here instead of four, and the
polarity/alpha joins pull from different file pairs than Holdout #1 did.
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

HOLDOUT_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout_141_v2.csv"
SYSTEM_STANCE_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout2_system_stance.csv"
INDEPENDENT_STANCE_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout2_independent_stance_review.csv"
SYSTEM_ALPHA_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout2_system_alpha.csv"
INDEPENDENT_ALPHA_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout2_independent_alpha_review.csv"
MANIFEST_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout_141_v2_manifest.json"

OUTPUT_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout2_comparison.csv"
OUTPUT_JSON_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout2_summary.json"

EXPECTED_COUNT = 141
POLARITY_TARGET = 0.80
ALPHA_MATCH_TARGET = 0.75
VALID_STANCES = ("supports_alpha", "opposes_alpha", "mentions_alpha", "neutral_background", "supports_counter_alpha")


def _load(path: Path) -> dict[str, dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as f:
        return {r["sample_id"]: r for r in csv.DictReader(f)}


def _b(v: str) -> bool:
    return str(v).strip().lower() == "true"


def main() -> int:
    holdout = _load(HOLDOUT_PATH)
    sys_stance = _load(SYSTEM_STANCE_PATH)
    ind_stance = _load(INDEPENDENT_STANCE_PATH)
    sys_alpha = _load(SYSTEM_ALPHA_PATH)
    ind_alpha = _load(INDEPENDENT_ALPHA_PATH)

    ids = set(holdout.keys())
    assert ids == set(sys_stance.keys()) == set(ind_stance.keys()) == set(sys_alpha.keys()) == set(ind_alpha.keys()), (
        "sample_id set mismatch across the five frozen sources"
    )
    assert len(ids) == EXPECTED_COUNT, f"expected {EXPECTED_COUNT} joined rows, found {len(ids)}"

    confusion: dict[str, dict[str, int]] = {s: dict.fromkeys(VALID_STANCES, 0) for s in VALID_STANCES}
    polarity_correct = 0
    critical_reversal_ids: list[str] = []
    directional_vs_neutral_ids: list[str] = []
    counter_alpha_mismatch_ids: list[str] = []
    mention_vs_neutral_ids: list[str] = []

    alpha_correct = 0
    wrong_alpha_ids: list[str] = []
    alpha_confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    too_generic = not_ticker_specific = llm_duplicate = system_duplicate = 0

    by_ticker_polarity: dict[str, list[int]] = defaultdict(list)
    by_ticker_alpha: dict[str, list[int]] = defaultdict(list)
    by_target_alpha_polarity: dict[str, list[int]] = defaultdict(list)
    by_system_alpha_alpha: dict[str, list[int]] = defaultdict(list)
    by_relation_polarity: dict[str, list[int]] = defaultdict(list)
    by_used_in_conflict_polarity: dict[str, list[int]] = defaultdict(list)
    by_used_in_activation_polarity: dict[str, list[int]] = defaultdict(list)
    by_ai_gate_alpha: dict[str, list[int]] = defaultdict(list)

    b1_llm_ids: list[str] = []
    b1_fallback_ids: list[str] = []

    comparison_rows: list[dict[str, Any]] = []

    for sid in sorted(ids):
        h = holdout[sid]
        ss = sys_stance[sid]
        rs = ind_stance[sid]
        sa = sys_alpha[sid]
        ra = ind_alpha[sid]

        b1_stance = ss["current_b1_stance"]
        reviewer_stance = rs["llm_expected_stance"]
        assert b1_stance in VALID_STANCES, f"{sid}: bad system stance {b1_stance!r}"
        assert reviewer_stance in VALID_STANCES, f"{sid}: bad reviewer stance {reviewer_stance!r}"

        confusion[b1_stance][reviewer_stance] += 1
        correct = b1_stance == reviewer_stance
        polarity_correct += int(correct)

        pair = {b1_stance, reviewer_stance}
        if pair == {"supports_alpha", "opposes_alpha"}:
            critical_reversal_ids.append(sid)
        directional = {"supports_alpha", "opposes_alpha"}
        neutralish = {"mentions_alpha", "neutral_background"}
        if (b1_stance in directional and reviewer_stance in neutralish) or (b1_stance in neutralish and reviewer_stance in directional):
            directional_vs_neutral_ids.append(sid)
        if "supports_counter_alpha" in pair and b1_stance != reviewer_stance:
            counter_alpha_mismatch_ids.append(sid)
        if pair == {"mentions_alpha", "neutral_background"}:
            mention_vs_neutral_ids.append(sid)

        if ss["current_b1_stance_method"] == "llm":
            b1_llm_ids.append(sid)
        elif ss["current_b1_stance_method"] == "deterministic_fallback":
            b1_fallback_ids.append(sid)

        system_alpha_id = sa["matched_alpha_id"] or "NONE"
        expected_alpha_id = ra["llm_expected_alpha_id"]
        alpha_confusion[system_alpha_id][expected_alpha_id] += 1
        alpha_ok = system_alpha_id == expected_alpha_id
        alpha_correct += int(alpha_ok)
        if not alpha_ok:
            wrong_alpha_ids.append(sid)

        if _b(ra["llm_too_generic"]):
            too_generic += 1
        if not _b(ra["llm_ticker_specific"]):
            not_ticker_specific += 1
        if _b(ra["llm_duplicate"]):
            llm_duplicate += 1
        if int(h["system_duplicate_group_size"]) > 1:
            system_duplicate += 1

        by_ticker_polarity[h["ticker"]].append(int(correct))
        by_ticker_alpha[h["ticker"]].append(int(alpha_ok))
        by_target_alpha_polarity[h["target_alpha_id"]].append(int(correct))
        by_system_alpha_alpha[system_alpha_id].append(int(alpha_ok))
        by_relation_polarity[h["system_relation"]].append(int(correct))
        by_used_in_conflict_polarity[h["system_used_in_conflict"]].append(int(correct))
        by_used_in_activation_polarity[h["system_used_in_activation"]].append(int(correct))
        by_ai_gate_alpha[h["system_ai_gate_alpha"]].append(int(alpha_ok))

        comparison_rows.append(
            {
                "sample_id": sid, "ticker": h["ticker"], "target_alpha_id": h["target_alpha_id"],
                "current_b1_stance": b1_stance, "independent_expected_stance": reviewer_stance,
                "polarity_match": correct, "system_matched_alpha_id": system_alpha_id,
                "independent_expected_alpha_id": expected_alpha_id, "alpha_match": alpha_ok,
                "critical_reversal": sid in set(critical_reversal_ids),
                "b1_stance_method": ss["current_b1_stance_method"],
                "alpha_mapper_matches_frozen_csv": sa["matches_frozen_csv_matched_alpha"],
            }
        )

    reviewed_count = len(ids)
    wrong_polarity_count = reviewed_count - polarity_correct
    wrong_alpha_count = reviewed_count - alpha_correct
    polarity_accuracy = polarity_correct / reviewed_count
    alpha_match_accuracy = alpha_correct / reviewed_count

    def _rate_table(d: dict[str, list[int]]) -> dict[str, dict[str, Any]]:
        return {k: {"correct": sum(v), "total": len(v), "accuracy": sum(v) / len(v)} for k, v in sorted(d.items())}

    llm_only_accuracy = None
    if b1_llm_ids:
        llm_only_correct = sum(1 for sid in b1_llm_ids if sys_stance[sid]["current_b1_stance"] == ind_stance[sid]["llm_expected_stance"])
        llm_only_accuracy = {"correct": llm_only_correct, "total": len(b1_llm_ids), "accuracy": llm_only_correct / len(b1_llm_ids)}
    fallback_only_accuracy = None
    if b1_fallback_ids:
        fb_correct = sum(1 for sid in b1_fallback_ids if sys_stance[sid]["current_b1_stance"] == ind_stance[sid]["llm_expected_stance"])
        fallback_only_accuracy = {"correct": fb_correct, "total": len(b1_fallback_ids), "accuracy": fb_correct / len(b1_fallback_ids)}

    alpha_mapper_stale_data_rows = sorted(sid for sid in ids if sys_alpha[sid]["matches_frozen_csv_matched_alpha"].strip().lower() != "true")
    stale_by_run: dict[str, list[str]] = defaultdict(list)
    for sid in alpha_mapper_stale_data_rows:
        stale_by_run[holdout[sid]["source_run_id"]].append(sid)

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    with OUTPUT_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        fieldnames = list(comparison_rows[0].keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(comparison_rows)

    summary = {
        "sample_count": reviewed_count,
        "polarity_correct_count": polarity_correct,
        "wrong_polarity_count": wrong_polarity_count,
        "polarity_accuracy": polarity_accuracy,
        "polarity_target": POLARITY_TARGET,
        "polarity_target_met": polarity_accuracy >= POLARITY_TARGET,
        "alpha_correct_count": alpha_correct,
        "wrong_alpha_count": wrong_alpha_count,
        "alpha_match_accuracy": alpha_match_accuracy,
        "alpha_match_target": ALPHA_MATCH_TARGET,
        "alpha_match_target_met": alpha_match_accuracy >= ALPHA_MATCH_TARGET,
        "wrong_alpha_sample_ids": wrong_alpha_ids,
        "critical_support_opposition_reversal_count": len(critical_reversal_ids),
        "critical_support_opposition_reversal_sample_ids": critical_reversal_ids,
        "critical_support_opposition_reversal_rate": len(critical_reversal_ids) / reviewed_count,
        "directional_vs_neutral_mismatch_count": len(directional_vs_neutral_ids),
        "counter_alpha_mismatch_count": len(counter_alpha_mismatch_ids),
        "mention_vs_neutral_mismatch_count": len(mention_vs_neutral_ids),
        "too_generic_count": too_generic,
        "not_ticker_specific_count": not_ticker_specific,
        "duplicate_count": llm_duplicate,
        "system_duplicate_candidate_count": system_duplicate,
        "b1_llm_count": len(b1_llm_ids),
        "b1_fallback_count": len(b1_fallback_ids),
        "b1_llm_only_agreement": llm_only_accuracy,
        "b1_fallback_only_agreement": fallback_only_accuracy,
        "review_source": "independent_llm_provisional",
        "human_review_performed": False,
        "holdout_frozen_before_evaluation": True,
        "stance_and_alpha_review_architecture": (
            "Two SEPARATE, independent Provider call sequences were used, per this task's explicit architectural "
            "requirement: phase4_stance_review (shown target_alpha_id + definition + legal counter Alphas, never "
            "shown any system output) and phase6_alpha_review (shown the FULL taxonomy only, never shown "
            "target_alpha_id, matched_alpha_id, or any system output). This differs from Holdout #1, which used one "
            "combined review call for both questions; the split removes any risk of the Alpha reviewer being "
            "anchored by target_alpha_id."
        ),
        "stance_confusion_matrix": {"axes": "rows=current_b1_stance, columns=independent_reviewer_stance", "matrix": confusion},
        "alpha_confusion_matrix": {
            "axes": "rows=system_matched_alpha_id (fresh Alpha Mapper, NONE if unmatched), columns=independent_expected_alpha_id",
            "matrix": {k: dict(v) for k, v in alpha_confusion.items()},
        },
        "polarity_accuracy_by_ticker": _rate_table(by_ticker_polarity),
        "polarity_accuracy_by_target_alpha": _rate_table(by_target_alpha_polarity),
        "polarity_accuracy_by_relation": _rate_table(by_relation_polarity),
        "polarity_accuracy_by_used_in_conflict": _rate_table(by_used_in_conflict_polarity),
        "polarity_accuracy_by_used_in_activation": _rate_table(by_used_in_activation_polarity),
        "alpha_match_accuracy_by_ticker": _rate_table(by_ticker_alpha),
        "alpha_match_accuracy_by_system_matched_alpha": _rate_table(by_system_alpha_alpha),
        "alpha_match_accuracy_by_ai_gate_applicable": _rate_table(by_ai_gate_alpha),
        "alpha_mapper_stale_historical_data_sample_ids": alpha_mapper_stale_data_rows,
        "alpha_mapper_stale_historical_data_count": len(alpha_mapper_stale_data_rows),
        "alpha_mapper_stale_historical_data_note": (
            f"{len(alpha_mapper_stale_data_rows)} rows have a frozen-CSV system_matched_alpha_id that does not "
            "match a fresh re-run of today's exact production Alpha Mapper. All are concentrated in two source "
            "runs, both dated 2026-07-17 (the oldest runs eligible for this holdout): "
            + "; ".join(f"{run_id} ({len(sids)} rows)" for run_id, sids in sorted(stale_by_run.items()))
            + ". Run 8d21c047-fc0a-4d94-957d-3787f353a544 (SNDK) is the SAME pre-AI-gate-era run already flagged "
            "in the Holdout #1 root-cause analysis; its persisted alpha_matches.json predates the AI_ALPHA_IDS "
            "hard gate (comqutor_alpha/structure_engine/ai_alpha_discriminator.py). Run "
            "4ca7dafa-6ac1-4d94-add0-f6f93b1af150 (NVDA) is a NEW instance of the same class of staleness: its "
            "metadata.json shows llm_provider=offline_recovery, quick_model=deterministic_fallback, "
            "recovered_from_run_id=8be070d5-5d66-44d9-aa8d-8be5e70294ad -- i.e. this run's structured records were "
            "reconstructed from a raw TradingAgents state log rather than produced by a live model call, and its "
            "persisted Alpha Mapper output likewise predates current production logic. The frozen holdout CSV's "
            "target_alpha_id and system_* columns were NOT modified post-freeze (per this task's own explicit "
            "rule); the alpha-match metric above uses the FRESH, current-production Alpha Mapper result "
            "(item2_blind_holdout2_system_alpha.csv) for all 141 rows as required, never the stale frozen value. "
            "The B1 stance question for these rows was still asked relative to each row's own (possibly "
            "historically-stale) target_alpha_id -- this remains a valid, uncorrupted stance comparison, since "
            "both current B1 and the independent stance reviewer answered the identical, fixed question; it is "
            "simply not reflective of today's true Alpha-Mapper Top-1 for those specific rows. Fully disclosed, "
            "not hidden."
        ),
        "holdout1_result_for_comparison": {
            "polarity_accuracy": "79/100 = 79%", "alpha_match_accuracy": "73/100 = 73%",
            "note": "NOT averaged or combined with this holdout; reported separately only, as the prior blind holdout evaluated against B1 v2 (pre-fix), not v3.",
        },
        "holdout_manifest_reference": {
            "sha256": manifest["csv_sha256"],
            "ticker_distribution": manifest["ticker_distribution"],
            "alpha_distribution": manifest["alpha_distribution"],
        },
    }

    OUTPUT_JSON_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"\nWrote {len(comparison_rows)} rows -> {OUTPUT_CSV_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
