#!/usr/bin/env python3
"""QA Closure v0.1.2, Item 2 (corrected): build
``evidence_review_summary.json``.

POLARITY (``polarity_accuracy``/``correct_count``/``wrong_polarity_count``/
``critical_support_opposition_reversal_count``) compares the CURRENT,
FINAL B1 authoritative stance -- the same ``evidence_stance`` value B2
would consume in production, read from
``docs/audit_artifacts/b1_llm_stance_50_validation_after_parser_fix.csv``
(50/50 real LLM results, 0 deterministic fallbacks, verified current: see
this task's own report) -- against the frozen, unaltered independent J3
reviewer (``comqutor_alpha/config/j3_provisional_semantic_benchmark_v0.1.json``).
The OLD ``deterministic.v1`` baseline vs the same J3 reviewer is preserved
as a separate, clearly-labeled, non-primary figure for comparison --
never conflated with ``polarity_accuracy`` itself.

ALPHA MATCH (``alpha_match_accuracy``) is UNCHANGED from the prior version
of this script: the independent LLM provisional review's own
``llm_expected_alpha_id`` (``docs/audit_artifacts/evidence_review_llm_provisional.csv``)
vs the system's ``matched_alpha_id`` -- a separate Alpha Mapper benchmark,
untouched by this correction.

Pure, deterministic, offline: reads already-frozen files and performs
arithmetic only -- no Provider/LLM call, no re-adjudication, no re-sampling.
Re-running this script against the same frozen input files must always
produce byte-identical output.

Never touches ``docs/evidence_review_sample.csv`` or any ``reviewer_*``
field. ``review_source`` is always ``"independent_llm_provisional"`` --
this is a provisional QA proxy, never described as human review.
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

import yaml  # noqa: E402

SAMPLE_PATH = REPO_ROOT / "docs" / "evidence_review_sample_records.json"
LLM_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "evidence_review_llm_provisional.csv"
B1_CURRENT_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "b1_llm_stance_50_validation_after_parser_fix.csv"
TAXONOMY_PATH = REPO_ROOT / "comqutor_alpha" / "alpha_library" / "alpha_taxonomy_v1.yaml"
OUTPUT_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "evidence_review_summary.json"

REVIEW_SOURCE = "independent_llm_provisional"
POLARITY_SYSTEM_SOURCE = "current_b1_authoritative"
EXPECTED_ROW_COUNT = 50
POLARITY_TARGET = 0.80
ALPHA_MATCH_TARGET = 0.75

VALID_STANCES = frozenset(
    {"supports_alpha", "opposes_alpha", "mentions_alpha", "neutral_background", "supports_counter_alpha"}
)


class SummaryValidationError(Exception):
    def __init__(self, reason_code: str, detail: str = "") -> None:
        self.reason_code = reason_code
        self.detail = detail
        super().__init__(f"{reason_code}: {detail}" if detail else reason_code)


def _load_system_records() -> dict[str, dict[str, Any]]:
    data = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    records = data["records"]
    if len(records) != EXPECTED_ROW_COUNT:
        raise SummaryValidationError("SYSTEM_SAMPLE_ROW_COUNT_UNEXPECTED", str(len(records)))
    by_id = {r["sample_id"]: r for r in records}
    if len(by_id) != EXPECTED_ROW_COUNT:
        raise SummaryValidationError("SYSTEM_SAMPLE_DUPLICATE_SAMPLE_ID")
    return by_id


def _load_llm_rows() -> dict[str, dict[str, Any]]:
    with LLM_CSV_PATH.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if len(rows) != EXPECTED_ROW_COUNT:
        raise SummaryValidationError("LLM_REVIEW_ROW_COUNT_UNEXPECTED", str(len(rows)))
    by_id = {r["sample_id"]: r for r in rows}
    if len(by_id) != EXPECTED_ROW_COUNT:
        raise SummaryValidationError("LLM_REVIEW_DUPLICATE_SAMPLE_ID")
    return by_id


def _load_b1_current_stance() -> dict[str, dict[str, Any]]:
    """The CURRENT, final B1 authoritative stance per sample_id --
    ``final_stance``/``counter_alpha_id``/``stance_method`` from the
    post-parser-fix, 50/50-real-LLM combined artifact. This is the same
    ``evidence_stance`` value B2 would consume in production; it is NOT
    the stale ``deterministic.v1`` column in the original review sample."""
    with B1_CURRENT_CSV_PATH.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if len(rows) != EXPECTED_ROW_COUNT:
        raise SummaryValidationError("B1_CURRENT_ROW_COUNT_UNEXPECTED", str(len(rows)))
    by_id = {r["sample_id"]: r for r in rows}
    if len(by_id) != EXPECTED_ROW_COUNT:
        raise SummaryValidationError("B1_CURRENT_DUPLICATE_SAMPLE_ID")
    for sample_id, row in by_id.items():
        if row.get("stance_method") not in ("llm", "deterministic_fallback"):
            raise SummaryValidationError("B1_CURRENT_STANCE_METHOD_INVALID", f"{sample_id}: {row.get('stance_method')!r}")
        if row.get("final_stance") not in VALID_STANCES:
            raise SummaryValidationError("B1_CURRENT_STANCE_INVALID", f"{sample_id}: {row.get('final_stance')!r}")
    return by_id


def _load_taxonomy_and_legal_counter_alphas() -> tuple[frozenset[str], dict[str, frozenset[str]]]:
    payload = yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))
    known_ids = frozenset(a["alpha_id"] for a in payload["alphas"])
    legal_counter = {
        a["alpha_id"]: frozenset(c["alpha_id"] for c in (a.get("conflict_alphas") or []))
        for a in payload["alphas"]
    }
    return known_ids, legal_counter


def _as_bool(value: str) -> bool:
    return str(value).strip().lower() == "true"


def build_summary() -> dict[str, Any]:
    system_by_id = _load_system_records()
    llm_by_id = _load_llm_rows()
    b1_current_by_id = _load_b1_current_stance()
    known_alpha_ids, legal_counter_alphas = _load_taxonomy_and_legal_counter_alphas()

    system_ids = set(system_by_id.keys())
    llm_ids = set(llm_by_id.keys())
    b1_ids = set(b1_current_by_id.keys())
    if system_ids != llm_ids:
        raise SummaryValidationError(
            "SAMPLE_ID_MISMATCH",
            f"only-in-system={sorted(system_ids - llm_ids)}, only-in-llm={sorted(llm_ids - system_ids)}",
        )
    if system_ids != b1_ids:
        raise SummaryValidationError(
            "B1_CURRENT_SAMPLE_ID_MISMATCH",
            f"only-in-system={sorted(system_ids - b1_ids)}, only-in-b1-current={sorted(b1_ids - system_ids)}",
        )

    # PRIMARY polarity comparison (this correction): current, final B1
    # authoritative stance vs the frozen independent J3 reviewer.
    confusion: dict[str, dict[str, int]] = {s: dict.fromkeys(VALID_STANCES, 0) for s in VALID_STANCES}
    polarity_correct_count = 0
    critical_reversal_sample_ids: list[str] = []
    b1_llm_count = 0
    b1_fallback_count = 0
    b1_llm_correct_count = 0
    b1_fallback_correct_count = 0

    # SECONDARY, preserved-for-comparison: the old deterministic.v1
    # baseline vs the same frozen J3 reviewer -- never conflated with the
    # primary current-B1 metric above.
    deterministic_confusion: dict[str, dict[str, int]] = {s: dict.fromkeys(VALID_STANCES, 0) for s in VALID_STANCES}
    deterministic_correct_count = 0

    alpha_correct_count = 0
    wrong_alpha_sample_ids: list[str] = []
    too_generic_count = 0
    not_ticker_specific_count = 0
    llm_duplicate_count = 0
    system_duplicate_count = 0

    for sample_id in sorted(system_ids):
        system_row = system_by_id[sample_id]
        llm_row = llm_by_id[sample_id]
        b1_row = b1_current_by_id[sample_id]

        deterministic_v1_stance = system_row.get("evidence_stance")
        independent_reviewed_stance = llm_row.get("llm_expected_stance")
        current_b1_stance = b1_row.get("final_stance")
        current_b1_method = b1_row.get("stance_method")
        if deterministic_v1_stance not in VALID_STANCES:
            raise SummaryValidationError("SYSTEM_STANCE_INVALID", f"{sample_id}: {deterministic_v1_stance!r}")
        if independent_reviewed_stance not in VALID_STANCES:
            raise SummaryValidationError("LLM_STANCE_INVALID", f"{sample_id}: {independent_reviewed_stance!r}")

        # Primary: current B1 vs independent reviewer.
        confusion[current_b1_stance][independent_reviewed_stance] += 1
        is_correct = current_b1_stance == independent_reviewed_stance
        if is_correct:
            polarity_correct_count += 1
        if {current_b1_stance, independent_reviewed_stance} == {"supports_alpha", "opposes_alpha"}:
            critical_reversal_sample_ids.append(sample_id)
        if current_b1_method == "llm":
            b1_llm_count += 1
            b1_llm_correct_count += int(is_correct)
        elif current_b1_method == "deterministic_fallback":
            b1_fallback_count += 1
            b1_fallback_correct_count += int(is_correct)

        # Secondary: old deterministic.v1 baseline vs the same reviewer.
        deterministic_confusion[deterministic_v1_stance][independent_reviewed_stance] += 1
        if deterministic_v1_stance == independent_reviewed_stance:
            deterministic_correct_count += 1

        llm_counter_alpha_id = (llm_row.get("llm_counter_alpha_id") or "").strip() or None
        if independent_reviewed_stance == "supports_counter_alpha":
            if not llm_counter_alpha_id:
                raise SummaryValidationError("MISSING_COUNTER_ALPHA_ID", sample_id)
            if llm_counter_alpha_id not in known_alpha_ids:
                raise SummaryValidationError("UNKNOWN_COUNTER_ALPHA_ID", f"{sample_id}: {llm_counter_alpha_id!r}")
            target_alpha_id = system_row.get("target_alpha_id")
            if llm_counter_alpha_id not in legal_counter_alphas.get(target_alpha_id, frozenset()):
                raise SummaryValidationError(
                    "ILLEGAL_COUNTER_ALPHA_ID",
                    f"{sample_id}: {llm_counter_alpha_id!r} not a legal conflict Alpha of target {target_alpha_id!r}",
                )
        elif llm_counter_alpha_id is not None:
            raise SummaryValidationError(
                "UNEXPECTED_COUNTER_ALPHA_ID",
                f"{sample_id}: stance={independent_reviewed_stance!r} counter_alpha_id={llm_counter_alpha_id!r}",
            )

        system_matched_alpha_id = system_row.get("matched_alpha_id")
        llm_expected_alpha_id = llm_row.get("llm_expected_alpha_id")
        if llm_expected_alpha_id != "NONE" and llm_expected_alpha_id not in known_alpha_ids:
            raise SummaryValidationError("LLM_ALPHA_ID_INVALID", f"{sample_id}: {llm_expected_alpha_id!r}")
        if system_matched_alpha_id == llm_expected_alpha_id:
            alpha_correct_count += 1
        else:
            wrong_alpha_sample_ids.append(sample_id)

        if _as_bool(llm_row.get("llm_too_generic", "")):
            too_generic_count += 1
        if not _as_bool(llm_row.get("llm_ticker_specific", "")):
            not_ticker_specific_count += 1
        if _as_bool(llm_row.get("llm_duplicate", "")):
            llm_duplicate_count += 1
        if bool(system_row.get("duplicate_or_paraphrase_member")):
            system_duplicate_count += 1

        for field in ("llm_expected_stance", "llm_expected_alpha_id", "llm_should_be_admissible", "llm_confidence"):
            if not (llm_row.get(field) or "").strip():
                raise SummaryValidationError("MISSING_LLM_JUDGMENT", f"{sample_id}: {field}")
        if llm_row.get("review_source") != REVIEW_SOURCE:
            raise SummaryValidationError("REVIEW_SOURCE_MISMATCH", f"{sample_id}: {llm_row.get('review_source')!r}")

    reviewed_count = len(system_ids)
    wrong_polarity_count = reviewed_count - polarity_correct_count
    wrong_alpha_count = reviewed_count - alpha_correct_count
    if polarity_correct_count + wrong_polarity_count != reviewed_count:
        raise SummaryValidationError("POLARITY_COUNT_ARITHMETIC_MISMATCH")
    if alpha_correct_count + wrong_alpha_count != reviewed_count:
        raise SummaryValidationError("ALPHA_COUNT_ARITHMETIC_MISMATCH")
    if b1_llm_count + b1_fallback_count != reviewed_count:
        raise SummaryValidationError("B1_METHOD_COUNT_ARITHMETIC_MISMATCH")

    polarity_accuracy = polarity_correct_count / reviewed_count
    alpha_match_accuracy = alpha_correct_count / reviewed_count
    deterministic_v1_accuracy = deterministic_correct_count / reviewed_count

    return {
        # John's required fields (section 10) -- names and presence exactly
        # as specified, never removed or renamed. POLARITY fields
        # (correct_count/wrong_polarity_count/polarity_accuracy) compare
        # the CURRENT, final B1 authoritative stance against the
        # independent reviewer -- see polarity_system_source below. They
        # are NOT the old deterministic.v1-vs-reviewer figure (that is
        # preserved separately, under deterministic_v1_baseline).
        "reviewed_count": reviewed_count,
        "correct_count": polarity_correct_count,
        "wrong_alpha_count": wrong_alpha_count,
        "wrong_polarity_count": wrong_polarity_count,
        "too_generic_count": too_generic_count,
        "not_ticker_specific_count": not_ticker_specific_count,
        "duplicate_count": llm_duplicate_count,
        "polarity_accuracy": polarity_accuracy,
        "alpha_match_accuracy": alpha_match_accuracy,
        # Provenance fields (section 10) -- additive, never displacing the
        # required fields above.
        "review_source": REVIEW_SOURCE,
        "human_review_performed": False,
        "john_approved": False,
        "sample_count": reviewed_count,
        "polarity_target": POLARITY_TARGET,
        "alpha_match_target": ALPHA_MATCH_TARGET,
        "polarity_target_met": polarity_accuracy >= POLARITY_TARGET,
        "alpha_match_target_met": alpha_match_accuracy >= ALPHA_MATCH_TARGET,
        # Unambiguous prediction-source metadata (this correction, section
        # 9): which system output polarity_accuracy actually compares.
        "polarity_system_source": POLARITY_SYSTEM_SOURCE,
        "b1_llm_count": b1_llm_count,
        "b1_fallback_count": b1_fallback_count,
        "b1_llm_only_agreement": (
            {"correct_count": b1_llm_correct_count, "total_count": b1_llm_count, "accuracy": b1_llm_correct_count / b1_llm_count}
            if b1_llm_count > 0
            else None
        ),
        "b1_fallback_only_agreement": (
            {
                "correct_count": b1_fallback_correct_count,
                "total_count": b1_fallback_count,
                "accuracy": b1_fallback_correct_count / b1_fallback_count,
            }
            if b1_fallback_count > 0
            else None
        ),
        # Preserved historical baseline (this correction, section 7) --
        # old deterministic.v1 vs the same independent reviewer. Distinct
        # from, and never mixed into, polarity_accuracy above.
        "deterministic_v1_baseline": {
            "description": "old deterministic.v1 evidence_stance (docs/evidence_review_sample_records.json) vs independent J3 reviewer -- historical figure, NOT current B1 polarity_accuracy",
            "correct_count": deterministic_correct_count,
            "wrong_count": reviewed_count - deterministic_correct_count,
            "accuracy": deterministic_v1_accuracy,
            "confusion_matrix": {
                "axes": "rows=deterministic.v1 evidence_stance, columns=independent_reviewed_stance",
                "matrix": deterministic_confusion,
            },
        },
        # Additive transparency fields -- not required by section 10, but
        # needed to make wrong_alpha_count/wrong_polarity_count auditable
        # rather than opaque totals, and to keep the system's own
        # duplicate flag visible without silently substituting it for the
        # LLM's independent judgment (section 8).
        "polarity_correct_count": polarity_correct_count,
        "alpha_correct_count": alpha_correct_count,
        "critical_support_opposition_reversal_count": len(critical_reversal_sample_ids),
        "critical_support_opposition_reversal_sample_ids": critical_reversal_sample_ids,
        "wrong_alpha_sample_ids": wrong_alpha_sample_ids,
        "system_duplicate_or_paraphrase_member_count": system_duplicate_count,
        "stance_confusion_matrix": {
            "axes": "rows=current_b1_final_stance, columns=independent_reviewed_stance",
            "matrix": confusion,
        },
        "source_files": {
            "system_sample": str(SAMPLE_PATH.relative_to(REPO_ROOT)),
            "llm_provisional_review": str(LLM_CSV_PATH.relative_to(REPO_ROOT)),
            "b1_current_stance": str(B1_CURRENT_CSV_PATH.relative_to(REPO_ROOT)),
        },
    }


def main() -> int:
    summary = build_summary()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
