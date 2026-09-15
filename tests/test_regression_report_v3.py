"""v0.1.3 QA Closure, Item 1: regression_report_v3 schema/logic tests.

Per the task's explicit instruction, this is report/schema/testing only --
every fixture here is synthetic, never real six-ticker production data.
Proves the reporting path produces actual RESULTS (not just expected
labels), and never fabricates a gold PASS from a non-gold expectation.
Zero Provider calls, zero TradingAgents calls.
"""

from __future__ import annotations

from comqutor_alpha.regression.regression_report_v3 import (
    REGRESSION_REPORT_V3_SCHEMA_VERSION,
    build_regression_report_v3,
    build_regression_report_v3_entry,
)


def _run_audit(
    *,
    detected_alphas_and_levels,
    main_conflict_id=None,
    graph_edges=8,
    ticker_consistency="pass",
    declared=6,
    admitted=2,
    candidate=1,
    suppressed=1,
    rejected=3,
):
    return {
        "activation_summary": {
            "per_alpha": {
                alpha_id: {"level": level} for alpha_id, level in detected_alphas_and_levels.items()
            }
        },
        "conflict_summary": {
            "main_conflict_id": main_conflict_id,
            "declared_pair_count": declared,
            "admitted_count": admitted,
            "candidate_conflict_count": candidate,
            "suppressed_count": suppressed,
            "rejected_count": rejected,
        },
        "graph": {"admitted_edge_count": graph_edges},
        "ticker_consistency": ticker_consistency,
    }


def _artifact_manifest(completeness="pass"):
    """The run's separately-persisted artifact_manifest.json (Sprint 1
    Track A2) -- NOT the same shape as run_audit.json's own internal
    "artifact_manifest" per-file record list."""
    return {"artifact_completeness": completeness}


def _authority_audit(*, ticker, expected_alphas=(), expected_main_conflicts=()):
    return {
        "tickers": {
            ticker: {
                "expected_alphas": [
                    {
                        "alpha_id": alpha_id,
                        "authority_level": authority,
                        "valid_as_exact_regression_gold": authority == "APPROVED_GOLD",
                    }
                    for alpha_id, authority in expected_alphas
                ],
                "expected_main_conflicts": [
                    {
                        "expected_conflict": pair,
                        "authority_level": authority,
                        "valid_as_exact_regression_gold": authority == "APPROVED_GOLD",
                    }
                    for pair, authority in expected_main_conflicts
                ],
            }
        }
    }


def test_entry_reports_actual_results_not_just_expected_labels():
    """The core John complaint: the entry must carry ACTUAL detected data
    (alphas, main conflict) alongside expectations, not merely restate
    expected labels."""
    run_audit = _run_audit(
        detected_alphas_and_levels={"A101": "dominant", "A304": "active", "A003": "candidate"},
        main_conflict_id="A101__A304",
    )
    authority = _authority_audit(
        ticker="NVDA",
        expected_alphas=[("A101", "DOCUMENTED_EXPECTATION"), ("A103", "DOCUMENTED_EXPECTATION")],
        expected_main_conflicts=[("A101__A304", "DOCUMENTED_EXPECTATION")],
    )
    entry = build_regression_report_v3_entry(
        ticker="NVDA",
        selected_run_id="real-run-id-123",
        run_status="completed",
        run_audit=run_audit,
        authority_audit=authority,
    )
    # A003 is candidate -- never counted as detected.
    assert entry["actual_detected_alphas"] == ["A101", "A304"]
    assert entry["actual_admitted_main_conflict"] == "A101__A304"
    assert entry["selected_run_id"] == "real-run-id-123"
    assert entry["schema_version"] == REGRESSION_REPORT_V3_SCHEMA_VERSION


def test_no_gold_expected_alpha_never_fakes_a_gold_pass_falls_back_to_diagnostic():
    """Zero APPROVED_GOLD expected alphas exist system-wide today (see
    docs/audit_artifacts/regression_label_authority_audit_v0.1.2.1.json) --
    the entry must report this honestly as a diagnostic evaluation, never
    silently present a DOCUMENTED_EXPECTATION hit rate as if it were gold-
    accepted."""
    run_audit = _run_audit(detected_alphas_and_levels={"A101": "dominant"})
    authority = _authority_audit(
        ticker="NVDA", expected_alphas=[("A101", "DOCUMENTED_EXPECTATION"), ("A103", "DOCUMENTED_EXPECTATION")]
    )
    entry = build_regression_report_v3_entry(
        ticker="NVDA", selected_run_id="r1", run_status="completed", run_audit=run_audit, authority_audit=authority
    )
    assert entry["alpha_hit_rate_evaluation_mode"] == "diagnostic"
    assert entry["actual_alpha_hit_rate"] == 0.5
    assert entry["expected_alpha_hits"] == ["A101"]
    assert entry["expected_alpha_misses"] == ["A103"]


def test_approved_gold_expected_alpha_is_evaluated_as_acceptance():
    run_audit = _run_audit(detected_alphas_and_levels={"A101": "dominant", "A103": "candidate"})
    authority = _authority_audit(
        ticker="NVDA", expected_alphas=[("A101", "APPROVED_GOLD"), ("A103", "APPROVED_GOLD")]
    )
    entry = build_regression_report_v3_entry(
        ticker="NVDA", selected_run_id="r1", run_status="completed", run_audit=run_audit, authority_audit=authority
    )
    assert entry["alpha_hit_rate_evaluation_mode"] == "acceptance"
    assert entry["actual_alpha_hit_rate"] == 0.5
    assert entry["expected_alpha_hits"] == ["A101"]
    assert entry["expected_alpha_misses"] == ["A103"]


def test_main_conflict_with_no_authoritative_expectation_reports_none_never_a_guess():
    """'expected main conflict only where an authoritative expectation
    exists' -- a DOCUMENTED_EXPECTATION-only ticker (no APPROVED_GOLD) must
    report expected_main_conflict=None and NOT_GOLD_EVALUABLE, never
    present the diagnostic expectation as if it were an evaluable gold
    target."""
    run_audit = _run_audit(detected_alphas_and_levels={}, main_conflict_id="A101__A304")
    authority = _authority_audit(
        ticker="NVDA", expected_main_conflicts=[("A101__A304", "DOCUMENTED_EXPECTATION")]
    )
    entry = build_regression_report_v3_entry(
        ticker="NVDA", selected_run_id="r1", run_status="completed", run_audit=run_audit, authority_audit=authority
    )
    assert entry["expected_main_conflict"] is None
    assert entry["main_conflict_match_result"] == "NOT_GOLD_EVALUABLE"


def test_main_conflict_gold_match_and_mismatch():
    authority_match = _authority_audit(
        ticker="NVDA", expected_main_conflicts=[("A101__A304", "APPROVED_GOLD")]
    )
    matching_run_audit = _run_audit(detected_alphas_and_levels={}, main_conflict_id="A101__A304")
    entry_match = build_regression_report_v3_entry(
        ticker="NVDA",
        selected_run_id="r1",
        run_status="completed",
        run_audit=matching_run_audit,
        authority_audit=authority_match,
    )
    assert entry_match["expected_main_conflict"] == "A101__A304"
    assert entry_match["main_conflict_match_result"] == "PASS"

    mismatching_run_audit = _run_audit(detected_alphas_and_levels={}, main_conflict_id="A304__A601")
    entry_mismatch = build_regression_report_v3_entry(
        ticker="NVDA",
        selected_run_id="r1",
        run_status="completed",
        run_audit=mismatching_run_audit,
        authority_audit=authority_match,
    )
    assert entry_mismatch["main_conflict_match_result"] == "FAIL"


def test_no_selected_run_degrades_every_field_to_none_never_a_fabricated_pass():
    entry = build_regression_report_v3_entry(
        ticker="AMD",
        selected_run_id=None,
        run_status="NOT_YET_RUN",
        run_audit={},
        authority_audit=_authority_audit(ticker="AMD"),
    )
    assert entry["actual_detected_alphas"] == []
    assert entry["actual_admitted_main_conflict"] is None
    assert entry["graph_edge_count"] is None
    assert entry["artifact_completeness"] is None
    assert entry["ticker_consistency"] is None
    assert entry["main_conflict_match_result"] == "NOT_GOLD_EVALUABLE"


def test_semantic_execution_health_is_passed_through_verbatim_never_recomputed():
    run_audit = _run_audit(detected_alphas_and_levels={})
    entry = build_regression_report_v3_entry(
        ticker="NVDA",
        selected_run_id="r1",
        run_status="completed",
        run_audit=run_audit,
        authority_audit=_authority_audit(ticker="NVDA"),
        semantic_health={
            "semantic_execution_health_status": "PASS",
            "semantic_execution_health_status_reason": "COVERAGE_AT_OR_ABOVE_TARGET",
        },
    )
    assert entry["semantic_execution_health"] == "PASS"
    assert entry["semantic_execution_health_reason"] == "COVERAGE_AT_OR_ABOVE_TARGET"


def test_conflict_counts_are_reused_verbatim_from_run_audit_never_recomputed():
    run_audit = _run_audit(detected_alphas_and_levels={}, declared=6, admitted=3, candidate=2, suppressed=2, rejected=1)
    entry = build_regression_report_v3_entry(
        ticker="NVDA",
        selected_run_id="r1",
        run_status="completed",
        run_audit=run_audit,
        authority_audit=_authority_audit(ticker="NVDA"),
    )
    assert entry["conflict_counts"] == {
        "declared": 6,
        "admitted": 3,
        "candidate": 2,
        "suppressed": 2,
        "rejected": 1,
    }


def test_aggregate_gates_computed_across_a_synthetic_six_ticker_set():
    entries = []
    for ticker, graph_edges, consistency, completeness in (
        ("NVDA", 8, "pass", "pass"),
        ("QQQ", 5, "pass", "pass"),
        ("MSFT", 2, "fail", "pass"),  # below graph_edges gate
        ("SNDK", 4, "pass", "fail"),  # artifact completeness fails
        ("TSM", 6, "pass", "pass"),
        ("AMD", 3, "pass", "pass"),
    ):
        run_audit = _run_audit(
            detected_alphas_and_levels={"A101": "active"},
            main_conflict_id="A101__A304",
            graph_edges=graph_edges,
            ticker_consistency=consistency,
        )
        authority = _authority_audit(
            ticker=ticker,
            expected_alphas=[("A101", "APPROVED_GOLD")],
            expected_main_conflicts=[("A101__A304", "APPROVED_GOLD")],
        )
        entries.append(
            build_regression_report_v3_entry(
                ticker=ticker,
                selected_run_id=f"run-{ticker.lower()}",
                run_status="completed",
                run_audit=run_audit,
                authority_audit=authority,
                artifact_manifest=_artifact_manifest(completeness),
            )
        )

    report = build_regression_report_v3(entries)
    aggregate = report["aggregate"]
    assert aggregate["ticker_count"] == 6
    assert aggregate["ticker_consistency_pass_count"] == 5
    assert aggregate["artifact_completeness_pass_count"] == 5
    assert aggregate["graph_edges_gate_pass_count"] == 5  # only MSFT=2 fails the >=3 gate
    assert aggregate["expected_alpha_hit_rate"] == 1.0
    assert aggregate["main_conflict_match_pass_count"] == 6
    assert aggregate["main_conflict_match_evaluable_count"] == 6


def test_never_calls_a_provider_or_tradingagents_client():
    import ast
    from pathlib import Path

    tree = ast.parse(
        (Path(__file__).resolve().parents[1] / "comqutor_alpha" / "regression" / "regression_report_v3.py").read_text()
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(b in node.module for b in ("llm_clients", "tradingagents", "week2_llm"))
