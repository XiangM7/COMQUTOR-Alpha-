#!/usr/bin/env python3
"""Evidence Review v2 acceptance-contract cleanup (John Item 9).

Introduces a general, row-ID-agnostic directional Gold eligibility contract
and recomputes the *current acceptance* metrics (polarity accuracy, critical
support/opposition reversal count) from the eligible subset only. Pure,
deterministic, offline arithmetic over already-frozen artifacts -- no
Provider call, no TradingAgents call, no mutation of any frozen review label.

Eligibility is derived generically from whatever formal adjudication records
already exist in evidence_review_summary_v2.json's `critical_reversal_
adjudication` -- never by matching a hardcoded sample_id in this script. If a
future adjudication is added for a different row, this script picks it up
automatically via the same `outcome -> eligibility` mapping.
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

ARTIFACTS = REPO_ROOT / "docs" / "audit_artifacts"
REVIEW_FROZEN_PATH = ARTIFACTS / "item2_blind_holdout5_review_frozen.csv"
SYSTEM_POLARITY_PATH = ARTIFACTS / "item2_blind_holdout5_system_polarity.json"
V2_PATH = ARTIFACTS / "evidence_review_summary_v2.json"

# The four general eligibility classes (task section 1). Never row-specific.
DIRECTIONALLY_CLEAR = "DIRECTIONALLY_CLEAR"
AMBIGUOUS_DIRECTION = "AMBIGUOUS_DIRECTION"
INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"
NON_DIRECTIONAL = "NON_DIRECTIONAL"

# Generic mapping from a formal adjudication *outcome* (not a row ID) to the
# general eligibility class. Extending this to a new outcome value requires
# no change to which rows it applies to -- that's driven entirely by which
# rows carry that outcome in the adjudication registry below.
ADJUDICATION_OUTCOME_TO_ELIGIBILITY = {
    "BOTH_REASONABLE_AMBIGUOUS": AMBIGUOUS_DIRECTION,
    "SYSTEM_CORRECT_REVIEW_LABEL_WRONG": DIRECTIONALLY_CLEAR,
    "REVIEW_LABEL_CORRECT_SYSTEM_WRONG": DIRECTIONALLY_CLEAR,
    "INSUFFICIENT_CONTEXT_TO_ADJUDICATE": INSUFFICIENT_CONTEXT,
    "NOT_A_DIRECTIONAL_CLAIM": NON_DIRECTIONAL,
}


def _load_adjudication_registry(v2_existing: dict) -> dict[str, dict[str, Any]]:
    """Build {sample_id: adjudication_record} from every formal adjudication
    already present in the v2 artifact. Currently v2 stores a single
    adjudication object (`critical_reversal_adjudication`); this is read
    generically by its own `sample_id` field, not by a literal string
    constant, so a future second adjudication (a list) would be picked up
    the same way without any code change to the eligibility logic itself.
    """
    registry: dict[str, dict[str, Any]] = {}
    existing = v2_existing.get("critical_reversal_adjudication")
    records = existing if isinstance(existing, list) else ([existing] if existing else [])
    for record in records:
        sid = record.get("sample_id")
        if sid:
            registry[sid] = record
    return registry


def _eligibility_for(sample_id: str, registry: dict[str, dict[str, Any]]) -> tuple[str, str]:
    """Returns (eligibility_class, basis). Default (no formal adjudication
    record for this row) is DIRECTIONALLY_CLEAR: the frozen reviewer label
    is presumed a uniquely defensible directional ground truth absent
    specific adjudicated evidence to the contrary -- never the reverse
    default, which would silently exclude every disagreement from
    acceptance without evidence.
    """
    record = registry.get(sample_id)
    if record is None:
        return DIRECTIONALLY_CLEAR, "no_formal_adjudication_record_default_clear"
    outcome = record.get("outcome")
    eligibility = ADJUDICATION_OUTCOME_TO_ELIGIBILITY.get(outcome)
    if eligibility is None:
        raise ValueError(f"{sample_id}: unmapped adjudication outcome {outcome!r}")
    return eligibility, f"formal_adjudication_outcome:{outcome}"


def main() -> int:
    v2_existing = json.loads(V2_PATH.read_text(encoding="utf-8"))
    registry = _load_adjudication_registry(v2_existing)

    with REVIEW_FROZEN_PATH.open(encoding="utf-8", newline="") as f:
        review_rows = {r["sample_id"]: r for r in csv.DictReader(f)}
    system_polarity = json.loads(SYSTEM_POLARITY_PATH.read_text(encoding="utf-8"))

    material_ids = sorted(
        sid for sid, row in review_rows.items() if row["human_material_alpha_fit"].strip().lower() == "true"
    )
    assert len(material_ids) == 62, f"expected 62 material-fit rows, found {len(material_ids)}"
    assert set(material_ids) == set(system_polarity), "polarity system output set != polarity-evaluable review rows"

    per_row: list[dict[str, Any]] = []
    excluded_ambiguous: list[str] = []
    excluded_other: list[str] = []
    eligible_correct = 0
    eligible_total = 0
    eligible_critical_reversal_ids: list[str] = []

    for sid in material_ids:
        rev_polarity = review_rows[sid]["human_polarity"].strip()
        sys_polarity = system_polarity[sid].get("system_polarity")
        correct = sys_polarity == rev_polarity
        is_critical_reversal = {sys_polarity, rev_polarity} == {"supports_alpha", "opposes_alpha"}
        eligibility, basis = _eligibility_for(sid, registry)

        row_record = {
            "sample_id": sid,
            "ticker": review_rows[sid]["ticker"],
            "target_alpha_id": review_rows[sid]["human_expected_alpha_id"],
            "review_polarity": rev_polarity,
            "system_polarity": sys_polarity,
            "polarity_correct": correct,
            "raw_critical_reversal": is_critical_reversal,
            "directional_eligibility": eligibility,
            "eligibility_basis": basis,
        }
        per_row.append(row_record)

        if eligibility == DIRECTIONALLY_CLEAR:
            eligible_total += 1
            eligible_correct += int(correct)
            if is_critical_reversal:
                eligible_critical_reversal_ids.append(sid)
        elif eligibility == AMBIGUOUS_DIRECTION:
            excluded_ambiguous.append(sid)
        else:
            excluded_other.append(sid)

    eligible_accuracy = eligible_correct / eligible_total if eligible_total else None

    directional_eligibility_block = {
        "contract_version": "v1",
        "contract": {
            "DIRECTIONALLY_CLEAR": "eligible for polarity acceptance scoring and the critical support/opposition reversal gate",
            "AMBIGUOUS_DIRECTION": "retained in audit data; NOT eligible for polarity acceptance scoring or the critical reversal gate",
            "INSUFFICIENT_CONTEXT": "retained in audit data; NOT eligible for directional acceptance scoring",
            "NON_DIRECTIONAL": "retained in audit data; NOT eligible for directional acceptance scoring",
        },
        "eligibility_source": "Derived generically from formal adjudication records in critical_reversal_adjudication (outcome -> eligibility mapping) -- never from a row-ID special case. A row with no formal adjudication record defaults to DIRECTIONALLY_CLEAR.",
        "adjudication_outcome_to_eligibility_map": ADJUDICATION_OUTCOME_TO_ELIGIBILITY,
        "material_alpha_fit_row_count": len(material_ids),
        "per_row": per_row,
        "excluded_ambiguous_direction_sample_ids": excluded_ambiguous,
        "excluded_other_eligibility_sample_ids": excluded_other,
        "eligible_denominator": eligible_total,
        "eligible_correct": eligible_correct,
        "eligible_polarity_accuracy": eligible_accuracy,
        "eligible_polarity_accuracy_percent": round(eligible_accuracy * 100, 2) if eligible_accuracy is not None else None,
        "eligible_critical_reversal_count": len(eligible_critical_reversal_ids),
        "eligible_critical_reversal_sample_ids": eligible_critical_reversal_ids,
        "raw_critical_reversal_count_reference": v2_existing["raw_h5_metrics"]["critical_reversal_count"],
        "raw_critical_reversal_sample_ids_reference": v2_existing["raw_h5_metrics"]["critical_reversal_sample_ids"],
        "note": "The raw historical critical_reversal_count (see raw_h5_metrics / critical_reversal_adjudication) is preserved unmodified for audit provenance. It is NOT the current acceptance metric whenever a reversal's sole sample_id is excluded from eligibility -- the current acceptance metric is eligible_critical_reversal_count only.",
    }

    alpha = v2_existing["raw_h5_metrics"]["alpha_match_accuracy"]
    alpha_threshold = v2_existing["acceptance_thresholds"]["alpha_accuracy_threshold_percent"]
    polarity_threshold = v2_existing["acceptance_thresholds"]["polarity_accuracy_threshold_percent"]
    reversal_target = v2_existing["acceptance_thresholds"]["critical_reversal_target"]

    alpha_status = "PASS" if alpha["accuracy_percent"] >= alpha_threshold else "FAIL"
    polarity_status = "PASS" if (directional_eligibility_block["eligible_polarity_accuracy_percent"] or 0) >= polarity_threshold else "FAIL"
    reversal_status = "PASS" if directional_eligibility_block["eligible_critical_reversal_count"] == reversal_target else "FAIL"
    overall_mechanical_status = (
        "ELIGIBLE_ACCEPTANCE_CRITERIA_MET_PENDING_JOHN_APPROVAL"
        if alpha_status == polarity_status == reversal_status == "PASS"
        else "ELIGIBLE_ACCEPTANCE_CRITERIA_NOT_MET"
    )

    new_acceptance_results = {
        "alpha_accuracy_result": {
            "correct": alpha["correct"],
            "total": alpha["total"],
            "value_percent": alpha["accuracy_percent"],
            "threshold_percent": alpha_threshold,
            "status": alpha_status,
            "eligibility_basis": "Alpha-match accuracy is not directionally filtered -- it is not a polarity/reversal metric.",
        },
        "polarity_accuracy_result": {
            "correct": directional_eligibility_block["eligible_correct"],
            "eligible_denominator": directional_eligibility_block["eligible_denominator"],
            "raw_material_fit_denominator_reference": v2_existing["raw_h5_metrics"]["polarity_accuracy"]["total"],
            "excluded_ambiguous_count": len(excluded_ambiguous),
            "excluded_other_eligibility_count": len(excluded_other),
            "value_percent": directional_eligibility_block["eligible_polarity_accuracy_percent"],
            "threshold_percent": polarity_threshold,
            "status": polarity_status,
            "eligibility_basis": "DIRECTIONALLY_CLEAR rows only -- see directional_eligibility.",
        },
        "critical_reversal_result": {
            "eligible_value": directional_eligibility_block["eligible_critical_reversal_count"],
            "raw_historical_value": directional_eligibility_block["raw_critical_reversal_count_reference"],
            "excluded_ambiguous_sample_ids": excluded_ambiguous,
            "target": reversal_target,
            "status": reversal_status,
            "note": (
                "The raw historical reversal (see raw_h5_metrics.critical_reversal_sample_ids and "
                "critical_reversal_adjudication) is preserved for audit provenance but excluded from this "
                "acceptance metric because its formal adjudication outcome maps to AMBIGUOUS_DIRECTION, "
                "which is not Gold-eligible for the reversal gate under the directional eligibility contract."
            ),
        },
        "overall_mechanical_status": overall_mechanical_status,
    }

    v2_existing["directional_eligibility"] = directional_eligibility_block
    v2_existing["acceptance_results"] = new_acceptance_results
    # Mechanical criteria passage is never sufficient for approval -- keep
    # explicit, unconditionally false pending an actual John decision.
    v2_existing["john_approval_status"] = {
        "john_approved": False,
        "john_approval_status": "PENDING_JOHN_APPROVAL",
        "note": "Cannot be self-satisfied. Mechanical metric passage (alpha/polarity/reversal, including the new eligible-set recomputation) and Codex/assistant/user confirmation are never sufficient grounds to set this true.",
    }

    V2_PATH.write_text(json.dumps(v2_existing, ensure_ascii=False, indent=2, sort_keys=False) + "\n", encoding="utf-8")

    print(json.dumps(directional_eligibility_block, ensure_ascii=False, indent=2))
    print(json.dumps(new_acceptance_results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
