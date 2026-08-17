"""J2 v0.2 evaluation contract application (task section 9): re-interprets
an already-computed :func:`comqutor_alpha.regression.evaluator.evaluate_ticker`
result through the v0.2 label's five-category contract
(:mod:`comqutor_alpha.regression.labels_v2`).

This module never re-replays, never re-derives Alpha/Conflict data, never
lowers a B2 threshold, never changes an Alpha score, never modifies a
stance, never modifies the taxonomy, and never promotes a candidate
conflict to admitted -- it only classifies the *already-computed*
``evaluate_ticker`` result's conflict pairs into the v0.2 categories and
assigns the formal per-pair/per-ticker status task section 9 defines:

  * a ``required_conflicts`` miss -> ``fail``
  * a ``conditional_conflicts`` miss -> ``informational``
  * a ``product_decision_pending`` pair -> ``unresolved`` (never pass/fail)
  * an incomplete source artifact -> ``not_evaluable`` for the whole ticker
  * an undeclared executable pair -> rejected at label load time
    (:mod:`comqutor_alpha.regression.labels_v2`), never reached here
  * a structural Alpha absent from one run's detected set -> never an
    automatic fail
  * a candidate conflict -> never counted as admitted or as a main-conflict
    match
  * the main conflict -> still only ever read from
    ``evaluate_ticker``'s own ``admitted_conflicts``-derived result
"""

from __future__ import annotations

from typing import Any

STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_INFORMATIONAL = "informational"
STATUS_UNRESOLVED = "unresolved"
STATUS_NOT_EVALUABLE = "not_evaluable"
STATUS_MATCH = "match"
STATUS_MISMATCH_INFORMATIONAL = "informational_mismatch"


def _ticker_is_evaluable(evaluate_ticker_result: dict[str, Any]) -> bool:
    return (
        evaluate_ticker_result.get("run_selection_status") == "selected"
        and evaluate_ticker_result.get("offline_reprocess_status") == "completed"
        and evaluate_ticker_result.get("artifact_completeness") == "pass"
    )


def _pair_status(pair: str, evaluate_ticker_result: dict[str, Any]) -> str:
    """Reads the already-computed pair status straight off
    ``evaluate_ticker``'s own ``expected_pair_status``/``admitted_conflicts``/
    ``candidate_conflicts`` -- never a second admissibility judgment. A
    pair the underlying result never even lists as "expected" (this
    module evaluates arbitrary v0.2 categories, not just v0.1's
    ``allowed_main_conflicts``) is derived directly from the admitted/
    candidate sets instead."""
    if pair in (evaluate_ticker_result.get("admitted_conflicts") or ()):
        return "admitted"
    if pair in (evaluate_ticker_result.get("candidate_conflicts") or ()):
        return "candidate"
    return "not_reached"


def apply_v2_contract(
    *,
    ticker: str,
    ticker_v2_label: dict[str, Any] | None,
    evaluate_ticker_result: dict[str, Any],
) -> dict[str, Any]:
    """Applies the v0.2 contract to one ticker's already-computed
    evaluation result. Returns a report-only dict; never mutates
    ``evaluate_ticker_result``."""
    evaluable = _ticker_is_evaluable(evaluate_ticker_result)

    required_results: list[dict[str, Any]] = []
    conditional_results: list[dict[str, Any]] = []
    allowed_results: list[dict[str, Any]] = []
    pending_results: list[dict[str, Any]] = []
    structural_results: dict[str, Any] = {}
    removed_pairs: list[str] = []

    label = ticker_v2_label or {}
    detected_alphas = set(evaluate_ticker_result.get("detected_alphas") or ())

    if evaluable:
        for pair in label.get("required_conflicts") or ():
            pair_status = _pair_status(pair, evaluate_ticker_result)
            required_results.append(
                {
                    "pair": pair,
                    "observed_status": pair_status,
                    "result": STATUS_PASS if pair_status == "admitted" else STATUS_FAIL,
                }
            )
        for pair in label.get("conditional_conflicts") or ():
            pair_status = _pair_status(pair, evaluate_ticker_result)
            conditional_results.append(
                {
                    "pair": pair,
                    "observed_status": pair_status,
                    "result": STATUS_MATCH if pair_status == "admitted" else STATUS_MISMATCH_INFORMATIONAL,
                }
            )
        for pair in label.get("allowed_conflicts") or ():
            allowed_results.append({"pair": pair, "observed_status": _pair_status(pair, evaluate_ticker_result)})

        structural = label.get("structural_expectations") or {}
        structural_results = {
            "positive_alphas_detected": sorted(set(structural.get("positive_alphas") or ()) & detected_alphas),
            "positive_alphas_not_detected": sorted(set(structural.get("positive_alphas") or ()) - detected_alphas),
            "negative_alphas_detected": sorted(set(structural.get("negative_alphas") or ()) & detected_alphas),
            "negative_alphas_not_detected": sorted(set(structural.get("negative_alphas") or ()) - detected_alphas),
            "note": "informational only -- a structural Alpha's absence in any one run never fails that run",
        }

    for entry in label.get("product_decision_pending") or ():
        pending_results.append(
            {"pair_id": entry.get("pair_id"), "reason": entry.get("reason"), "result": STATUS_UNRESOLVED}
        )

    removed_pairs = list(label.get("remove_while_undeclared") or ())

    required_failed = [r for r in required_results if r["result"] == STATUS_FAIL]
    if not evaluable:
        ticker_status = STATUS_NOT_EVALUABLE
    elif required_failed or evaluate_ticker_result.get("ticker_consistency") == "fail":
        ticker_status = STATUS_FAIL
    else:
        ticker_status = STATUS_PASS

    return {
        "ticker": ticker,
        "evaluation_status": STATUS_NOT_EVALUABLE if not evaluable else "evaluated",
        "ticker_status": ticker_status,
        "artifact_completeness": evaluate_ticker_result.get("artifact_completeness"),
        "required_conflict_results": required_results,
        "conditional_conflict_results": conditional_results,
        "allowed_conflict_results": allowed_results,
        "product_decision_pending_results": pending_results,
        "removed_while_undeclared_pairs": removed_pairs,
        "structural_expectation_results": structural_results,
        "run_bound_expectations": label.get("run_bound_expectations"),
    }


__all__ = [
    "STATUS_PASS",
    "STATUS_FAIL",
    "STATUS_INFORMATIONAL",
    "STATUS_UNRESOLVED",
    "STATUS_NOT_EVALUABLE",
    "STATUS_MATCH",
    "STATUS_MISMATCH_INFORMATIONAL",
    "apply_v2_contract",
]
