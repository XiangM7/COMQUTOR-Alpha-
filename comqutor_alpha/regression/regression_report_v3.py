"""Regression Report v3 (v0.1.3 QA Closure, Item 1).

John's complaint: the current material shows EXPECTED labels but not ACTUAL
regression RESULTS. This module builds the single per-ticker entry schema
that always carries both -- actual detected Alphas/main conflict alongside
whatever authoritative expectation (if any) exists for this ticker -- and
never fabricates a gold PASS from a non-gold expectation.

Pure, deterministic, offline arithmetic over already-computed inputs: a
run's own already-built ``run_audit.json`` payload (as returned by
``comqutor_alpha.api.routes_research.build_run_audit_payload``), the Step 1
Regression Label Authority Audit (via ``authority_contract``), and
optionally an already-computed semantic execution health summary (via
``semantic_execution_health.compute_semantic_execution_health``, called by
the caller -- this module does no filesystem I/O itself, so every function
here can be exercised against synthetic fixtures without a real run on
disk). No Provider call, no TradingAgents call, no re-evaluation of B1/B2/
B4/Conflict Detector production semantics.
"""

from __future__ import annotations

from typing import Any

from comqutor_alpha.regression.authority_contract import (
    alpha_expectations_for_ticker,
    apply_alpha_authority,
    apply_main_conflict_authority,
    main_conflict_expectations_for_ticker,
)

REGRESSION_REPORT_V3_SCHEMA_VERSION = "regression_report.v3"

# The three canonical qualified levels that count as a "detected" Alpha for
# regression purposes -- a plain "candidate" (including one gated down from
# active by Section C's fix) never counts as detected, matching the same
# vocabulary already frozen in alpha_level_classifier.py.
_DETECTED_LEVELS = frozenset({"active", "dominant", "regime_level"})


def _detected_alphas(activation_summary: dict[str, Any] | None) -> list[str]:
    per_alpha = (activation_summary or {}).get("per_alpha") or {}
    return sorted(
        alpha_id
        for alpha_id, entry in per_alpha.items()
        if isinstance(entry, dict) and entry.get("level") in _DETECTED_LEVELS
    )


def build_regression_report_v3_entry(
    *,
    ticker: str,
    selected_run_id: str | None,
    run_status: str | None,
    run_audit: dict[str, Any],
    authority_audit: dict[str, Any],
    semantic_health: dict[str, Any] | None = None,
    artifact_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one ticker's regression_report_v3 entry.

    ``run_audit`` is the full payload returned by ``build_run_audit_payload``
    for ``selected_run_id`` (or ``{}`` if no run is selected/available for
    this ticker -- every field below then degrades to an honest ``None``,
    never a fabricated PASS). ``authority_audit`` is the loaded Step 1
    Regression Label Authority Audit dict (``authority_contract.
    load_authority_audit()``). ``semantic_health`` is the caller's own
    already-computed ``semantic_execution_health.
    compute_semantic_execution_health(run_dir=...)`` result, or ``None`` if
    not available for this entry. ``artifact_manifest`` is the run's own
    separately-persisted ``artifact_manifest.json`` (Sprint 1 Track A2 --
    NOT the same as ``run_audit["artifact_manifest"]``, which is a
    different, unrelated per-file record list from Run Audit v2's own
    Track A), carrying the authoritative ``artifact_completeness`` field."""
    activation_summary = run_audit.get("activation_summary") if isinstance(run_audit, dict) else None
    conflict_summary = run_audit.get("conflict_summary") if isinstance(run_audit, dict) else None
    graph = run_audit.get("graph") if isinstance(run_audit, dict) else None

    detected_alphas = _detected_alphas(activation_summary)
    detected_main_conflict = (conflict_summary or {}).get("main_conflict_id")

    alpha_expectations = alpha_expectations_for_ticker(authority_audit, ticker)
    alpha_result = apply_alpha_authority(
        ticker=ticker, detected_alphas=detected_alphas, expectations=alpha_expectations
    )

    main_conflict_expectations = main_conflict_expectations_for_ticker(authority_audit, ticker)
    main_conflict_result = apply_main_conflict_authority(
        ticker=ticker,
        detected_main_conflict=detected_main_conflict,
        expectations=main_conflict_expectations,
    )

    # "expected main conflict only where an authoritative expectation
    # exists" -- i.e. only the GOLD_ACCEPTANCE-evaluable expectation(s), if
    # any. A DOCUMENTED/PROVISIONAL/REJECTED/UNKNOWN-only ticker reports
    # expected_main_conflict=None here, never a diagnostic guess presented
    # as if it were gold.
    gold_conflict_expectations = [
        e for e in main_conflict_result["expectations"] if e["evaluation_mode"] == "acceptance"
    ]
    expected_main_conflict = gold_conflict_expectations[0]["expected_main_conflict"] if gold_conflict_expectations else None

    return {
        "schema_version": REGRESSION_REPORT_V3_SCHEMA_VERSION,
        "ticker": ticker,
        "selected_run_id": selected_run_id,
        "run_status": run_status,
        "actual_detected_alphas": detected_alphas,
        "expected_alphas": {
            "diagnostic": alpha_result["diagnostic_expected_alphas"],
            "approved_gold": alpha_result["approved_gold_expected_alphas"],
            "rejected": alpha_result["rejected_expected_alphas"],
        },
        "expected_alpha_hits": sorted(set(alpha_result["approved_gold_expected_alphas"]) & set(detected_alphas))
        if alpha_result["approved_gold_expected_alphas"]
        else sorted(set(alpha_result["diagnostic_expected_alphas"]) & set(detected_alphas)),
        "expected_alpha_misses": sorted(set(alpha_result["approved_gold_expected_alphas"]) - set(detected_alphas))
        if alpha_result["approved_gold_expected_alphas"]
        else sorted(set(alpha_result["diagnostic_expected_alphas"]) - set(detected_alphas)),
        "actual_alpha_hit_rate": (
            alpha_result["gold_acceptance_hit_rate"]
            if alpha_result["gold_acceptance_status"] == "GOLD_ACCEPTANCE"
            else alpha_result["diagnostic_hit_rate"]
        ),
        "alpha_hit_rate_evaluation_mode": (
            "acceptance" if alpha_result["gold_acceptance_status"] == "GOLD_ACCEPTANCE" else "diagnostic"
        ),
        "actual_admitted_main_conflict": detected_main_conflict,
        "expected_main_conflict": expected_main_conflict,
        "main_conflict_match_result": (
            "PASS"
            if main_conflict_result["ticker_acceptance_result"] == "PASS"
            else "FAIL"
            if main_conflict_result["ticker_acceptance_result"] == "FAIL"
            else "NOT_GOLD_EVALUABLE"
        ),
        "graph_edge_count": (graph or {}).get("admitted_edge_count"),
        "artifact_completeness": (artifact_manifest or {}).get("artifact_completeness"),
        "ticker_consistency": run_audit.get("ticker_consistency") if isinstance(run_audit, dict) else None,
        "semantic_execution_health": (
            semantic_health.get("semantic_execution_health_status") if semantic_health else None
        ),
        "semantic_execution_health_reason": (
            semantic_health.get("semantic_execution_health_status_reason") if semantic_health else None
        ),
        "conflict_counts": {
            "declared": (conflict_summary or {}).get("declared_pair_count"),
            "admitted": (conflict_summary or {}).get("admitted_count"),
            "candidate": (conflict_summary or {}).get("candidate_conflict_count"),
            "suppressed": (conflict_summary or {}).get("suppressed_count"),
            "rejected": (conflict_summary or {}).get("rejected_count"),
        },
    }


def build_regression_report_v3(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate already-built per-ticker entries (from
    ``build_regression_report_v3_entry``) into the full report, including
    the six top-level acceptance gates. Never itself decides which run_ids
    are "the" selected six-ticker set -- that is a Product/QA decision made
    by the caller before this function is ever invoked."""
    ticker_consistency_pass = sum(1 for e in entries if e.get("ticker_consistency") == "pass")
    artifact_completeness_pass = sum(1 for e in entries if e.get("artifact_completeness") == "pass")
    graph_edges_pass = sum(1 for e in entries if (e.get("graph_edge_count") or 0) >= 3)

    acceptance_evaluable_hit_rates = [
        e["actual_alpha_hit_rate"]
        for e in entries
        if e.get("alpha_hit_rate_evaluation_mode") == "acceptance" and e.get("actual_alpha_hit_rate") is not None
    ]
    expected_alpha_hit_rate = (
        sum(acceptance_evaluable_hit_rates) / len(acceptance_evaluable_hit_rates)
        if acceptance_evaluable_hit_rates
        else None
    )

    main_conflict_pass_count = sum(1 for e in entries if e.get("main_conflict_match_result") == "PASS")
    main_conflict_evaluable_count = sum(
        1 for e in entries if e.get("main_conflict_match_result") in ("PASS", "FAIL")
    )

    return {
        "schema_version": REGRESSION_REPORT_V3_SCHEMA_VERSION,
        "tickers": entries,
        "aggregate": {
            "ticker_count": len(entries),
            "ticker_consistency_pass_count": ticker_consistency_pass,
            "artifact_completeness_pass_count": artifact_completeness_pass,
            "graph_edges_gate_pass_count": graph_edges_pass,
            "expected_alpha_hit_rate": expected_alpha_hit_rate,
            "expected_alpha_hit_rate_evaluable_ticker_count": len(acceptance_evaluable_hit_rates),
            "main_conflict_match_pass_count": main_conflict_pass_count,
            "main_conflict_match_evaluable_count": main_conflict_evaluable_count,
        },
    }
