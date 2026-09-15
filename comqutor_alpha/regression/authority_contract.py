"""Regression QA authority contract (COMQUTOR Alpha v0.1.2.1, Step 3:
Regression QA Contract Cleanup + Current Run Alignment).

Wraps ALREADY-COMPUTED comparison results (``evaluator.conflict_comparison``/
``alpha_comparison`` output, or the equivalent fields already persisted in
``outputs/regression/regression_report.json``) with an explicit authority
classification sourced from the Step 1 Regression Label Authority Audit
(``docs/audit_artifacts/regression_label_authority_audit_v0.1.2.1.json`` --
the single source of truth for whether any given expected Alpha or expected
Main Conflict is APPROVED_GOLD, DOCUMENTED_EXPECTATION,
PROVISIONAL_AI_PREDICTED, REJECTED_OR_SUPERSEDED, or UNKNOWN).

This module NEVER re-evaluates Alpha/Conflict/B1/B2/B4 production behavior,
never calls a Provider, never reruns TradingAgents or the six-ticker
regression, and never modifies any label YAML file. It only reclassifies an
already-computed comparison result's ACCEPTANCE SEMANTICS so a provisional
or rejected expectation can never silently masquerade as a production
PASS/FAIL. j2_provisional_regression_labels_v0.2.yaml is not treated as
approved gold here either (task section 6) -- only Step 1's own
APPROVED_GOLD classification (currently zero cases) may produce a
GOLD_ACCEPTANCE result.

Acceptance status vocabulary (task section 5):
  GOLD_ACCEPTANCE         -- only an APPROVED_GOLD expectation may produce this.
  DOCUMENTED_DIAGNOSTIC   -- Development-Plan-sourced; diagnostic only, cannot
                             fail production acceptance unless formally promoted.
  PROVISIONAL_DIAGNOSTIC  -- AI-predicted; diagnostic comparison only.
  REJECTED_OR_SUPERSEDED  -- must never be counted as an expected production
                             outcome; tracked instead as a negative constraint.
  NOT_GOLD_EVALUABLE      -- no approved exact gold exists for this case.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _PACKAGE_ROOT.parent

DEFAULT_AUTHORITY_AUDIT_PATH = (
    _REPO_ROOT / "docs" / "audit_artifacts" / "regression_label_authority_audit_v0.1.2.1.json"
)

# Step 1's five authority levels (task section 1 / section 2 of Step 1) --
# reused verbatim, never independently reclassified in this module.
APPROVED_GOLD = "APPROVED_GOLD"
DOCUMENTED_EXPECTATION = "DOCUMENTED_EXPECTATION"
PROVISIONAL_AI_PREDICTED = "PROVISIONAL_AI_PREDICTED"
REJECTED_OR_SUPERSEDED = "REJECTED_OR_SUPERSEDED"
UNKNOWN = "UNKNOWN"
VALID_AUTHORITY_LEVELS = frozenset(
    {APPROVED_GOLD, DOCUMENTED_EXPECTATION, PROVISIONAL_AI_PREDICTED, REJECTED_OR_SUPERSEDED, UNKNOWN}
)

# This task's (Step 3, section 5) acceptance-status vocabulary.
ACCEPTANCE_GOLD = "GOLD_ACCEPTANCE"
ACCEPTANCE_DOCUMENTED_DIAGNOSTIC = "DOCUMENTED_DIAGNOSTIC"
ACCEPTANCE_PROVISIONAL_DIAGNOSTIC = "PROVISIONAL_DIAGNOSTIC"
ACCEPTANCE_REJECTED = "REJECTED_OR_SUPERSEDED"
ACCEPTANCE_NOT_GOLD_EVALUABLE = "NOT_GOLD_EVALUABLE"

_AUTHORITY_TO_ACCEPTANCE = {
    APPROVED_GOLD: ACCEPTANCE_GOLD,
    DOCUMENTED_EXPECTATION: ACCEPTANCE_DOCUMENTED_DIAGNOSTIC,
    PROVISIONAL_AI_PREDICTED: ACCEPTANCE_PROVISIONAL_DIAGNOSTIC,
    REJECTED_OR_SUPERSEDED: ACCEPTANCE_REJECTED,
    UNKNOWN: ACCEPTANCE_NOT_GOLD_EVALUABLE,
}

EXPECTED_ALPHA_HIT_RATE_TARGET = 0.75
MAIN_CONFLICT_MATCH_TARGET_DISPLAY = ">=4/6"


class AuthorityContractError(Exception):
    pass


def acceptance_status_for_authority(authority_level: str) -> str:
    """Task section 5's exact A-E mapping. An authority level outside Step
    1's five-value vocabulary is a hard error -- never silently defaulted,
    since a typo here could otherwise let a rejected pair read as gold."""
    if authority_level not in VALID_AUTHORITY_LEVELS:
        raise AuthorityContractError(f"unknown authority level: {authority_level!r}")
    return _AUTHORITY_TO_ACCEPTANCE[authority_level]


def load_authority_audit(path: Path | str | None = None) -> dict[str, Any]:
    resolved = Path(path) if path is not None else DEFAULT_AUTHORITY_AUDIT_PATH
    return json.loads(resolved.read_text(encoding="utf-8"))


def main_conflict_expectations_for_ticker(audit: dict[str, Any], ticker: str) -> list[dict[str, Any]]:
    """Every currently-referenced expected main conflict for ``ticker``,
    each carrying its Step 1 authority level and exact-gold verdict
    verbatim -- never reclassified here."""
    ticker_block = (audit.get("tickers") or {}).get(ticker) or {}
    return [
        {
            "pair": e["expected_conflict"],
            "authority": e["authority_level"],
            "exact_gold": bool(e["valid_as_exact_regression_gold"]),
        }
        for e in ticker_block.get("expected_main_conflicts", [])
    ]


def alpha_expectations_for_ticker(audit: dict[str, Any], ticker: str) -> list[dict[str, Any]]:
    ticker_block = (audit.get("tickers") or {}).get(ticker) or {}
    return [
        {
            "alpha_id": e["alpha_id"],
            "authority": e["authority_level"],
            "exact_gold": bool(e["valid_as_exact_regression_gold"]),
        }
        for e in ticker_block.get("expected_alphas", [])
    ]


def apply_main_conflict_authority(
    *, ticker: str, detected_main_conflict: str | None, expectations: list[dict[str, Any]]
) -> dict[str, Any]:
    """Task section 7. ``detected_main_conflict`` must already be the
    production system's own already-computed
    ``conflict_comparison()['main_conflict']`` -- never recomputed here."""
    per_expectation = []
    for exp in expectations:
        authority = exp["authority"]
        acceptance_status = acceptance_status_for_authority(authority)
        diagnostic_match = detected_main_conflict is not None and detected_main_conflict == exp["pair"]
        per_expectation.append(
            {
                "expected_main_conflict": exp["pair"],
                "expectation_authority": authority,
                "exact_gold": exp["exact_gold"],
                "detected_main_conflict": detected_main_conflict,
                "evaluation_mode": "acceptance" if acceptance_status == ACCEPTANCE_GOLD else "diagnostic",
                "diagnostic_match": diagnostic_match,
                # Task section 7's own worked example: a rejected/provisional
                # mismatch is reported as NOT_GOLD_EVALUABLE, never FAIL.
                "acceptance_status": acceptance_status,
            }
        )

    gold_expectations = [e for e in per_expectation if e["acceptance_status"] == ACCEPTANCE_GOLD]
    if gold_expectations:
        ticker_acceptance_status = ACCEPTANCE_GOLD
        ticker_acceptance_result = "PASS" if any(e["diagnostic_match"] for e in gold_expectations) else "FAIL"
    else:
        ticker_acceptance_status = ACCEPTANCE_NOT_GOLD_EVALUABLE
        ticker_acceptance_result = None

    return {
        "ticker": ticker,
        "detected_main_conflict": detected_main_conflict,
        "expectations": per_expectation,
        # Rejected/superseded expectations never contribute to a positive
        # acceptance denominator (task section 7's closing rule).
        "excluded_from_acceptance_denominator": [
            e["expected_main_conflict"] for e in per_expectation if e["acceptance_status"] == ACCEPTANCE_REJECTED
        ],
        "ticker_acceptance_status": ticker_acceptance_status,
        "ticker_acceptance_result": ticker_acceptance_result,
    }


def apply_alpha_authority(
    *, ticker: str, detected_alphas: list[str], expectations: list[dict[str, Any]]
) -> dict[str, Any]:
    """Task section 8. Separates diagnostic-only expected Alphas from
    approved-gold expected Alphas; a rejected Alpha expectation (none exist
    today, but the contract must not assume that forever) is excluded from
    both positive lists and tracked only as a negative constraint."""
    detected = set(detected_alphas or ())
    diagnostic_expected: list[dict[str, Any]] = []
    gold_expected: list[dict[str, Any]] = []
    rejected_expected: list[dict[str, Any]] = []

    for exp in expectations:
        authority = exp["authority"]
        acceptance_status = acceptance_status_for_authority(authority)
        entry = {"alpha_id": exp["alpha_id"], "authority": authority, "acceptance_status": acceptance_status}
        if acceptance_status == ACCEPTANCE_GOLD:
            gold_expected.append(entry)
        elif acceptance_status == ACCEPTANCE_REJECTED:
            rejected_expected.append(entry)
        else:
            diagnostic_expected.append(entry)

    diagnostic_ids = [e["alpha_id"] for e in diagnostic_expected]
    gold_ids = [e["alpha_id"] for e in gold_expected]

    diagnostic_hit = sorted(set(diagnostic_ids) & detected)
    diagnostic_hit_rate = (len(diagnostic_hit) / len(diagnostic_ids)) if diagnostic_ids else None

    if gold_ids:
        gold_hit = sorted(set(gold_ids) & detected)
        gold_acceptance_hit_rate = len(gold_hit) / len(gold_ids)
        gold_acceptance_status = ACCEPTANCE_GOLD
    else:
        # Task section 8: zero approved-gold Alphas means the denominator
        # does not exist -- null, never a misleading 0%.
        gold_acceptance_hit_rate = None
        gold_acceptance_status = ACCEPTANCE_NOT_GOLD_EVALUABLE

    return {
        "ticker": ticker,
        "detected_alphas": sorted(detected),
        "diagnostic_expected_alphas": diagnostic_ids,
        "approved_gold_expected_alphas": gold_ids,
        "rejected_expected_alphas": [e["alpha_id"] for e in rejected_expected],
        "diagnostic_hit_rate": diagnostic_hit_rate,
        "gold_acceptance_hit_rate": gold_acceptance_hit_rate,
        "gold_acceptance_status": gold_acceptance_status,
    }


def expected_alpha_gate(gold_acceptance_hit_rates: list[float | None]) -> dict[str, Any]:
    """John's requested >=75% expected-Alpha hit-rate gate (task section
    9). Never deleted -- represented truthfully as pending a valid gold
    denominator until at least one ticker has approved-gold expected
    Alphas. Never collapses a missing denominator to 0%."""
    evaluable = [r for r in gold_acceptance_hit_rates if r is not None]
    if not evaluable:
        return {
            "target": EXPECTED_ALPHA_HIT_RATE_TARGET,
            "current_status": "PENDING_APPROVED_GOLD_OR_VALIDATED_CONTRACT",
            "current_gold_hit_rate": None,
            "gate_result": None,
        }
    current = sum(evaluable) / len(evaluable)
    return {
        "target": EXPECTED_ALPHA_HIT_RATE_TARGET,
        "current_status": "ACTIVE",
        "current_gold_hit_rate": current,
        "gate_result": "PASS" if current >= EXPECTED_ALPHA_HIT_RATE_TARGET else "FAIL",
    }


def main_conflict_gate(ticker_acceptance_results: dict[str, str | None]) -> dict[str, Any]:
    """John's requested >=4/6 main-conflict match gate (task section 10).
    ``ticker_acceptance_results`` maps ticker -> "PASS"/"FAIL"/None (None
    when that ticker has no gold expectation, per
    ``apply_main_conflict_authority``'s own ``ticker_acceptance_result``)."""
    evaluable = {t: r for t, r in ticker_acceptance_results.items() if r is not None}
    if not evaluable:
        return {
            "requested_target": MAIN_CONFLICT_MATCH_TARGET_DISPLAY,
            "current_evaluable_gold_cases": 0,
            "status": "PENDING_GOLD_CONTRACT",
            "use_for_current_production_acceptance": False,
            "gate_result": None,
        }
    passed = sum(1 for r in evaluable.values() if r == "PASS")
    return {
        "requested_target": MAIN_CONFLICT_MATCH_TARGET_DISPLAY,
        "current_evaluable_gold_cases": len(evaluable),
        "status": "ACTIVE",
        "use_for_current_production_acceptance": True,
        "gate_result": f"{passed}/{len(evaluable)}",
    }


def check_negative_constraints(
    *,
    ticker: str,
    admitted_conflicts: list[str],
    candidate_conflicts: list[str],
    rejected_pairs: list[str],
) -> dict[str, Any]:
    """Task section 11: absence of positive exact gold never disables
    negative canonical checks. A REJECTED_OR_SUPERSEDED (or otherwise
    non-canonical) pair must never appear as an admitted OR candidate
    conflict for this ticker; if it does, that is a valid QA failure,
    independent of any positive gold denominator."""
    produced = set(admitted_conflicts or ()) | set(candidate_conflicts or ())
    violations = sorted(produced & set(rejected_pairs or ()))
    return {
        "ticker": ticker,
        "checked_rejected_pairs": sorted(rejected_pairs or ()),
        "violations": violations,
        "negative_constraint_status": "FAIL" if violations else "PASS",
    }
