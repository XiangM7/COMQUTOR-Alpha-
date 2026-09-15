"""COMQUTOR Alpha v0.1.2.1 Step 3 -- Regression QA Contract Cleanup.

Proves the authority-aware regression QA contract
(comqutor_alpha.regression.authority_contract) never lets a provisional or
rejected expectation masquerade as a production PASS/FAIL, never reports a
misleading 0% acceptance rate when no approved-gold denominator exists, and
still enforces already-approved negative constraints. No Provider call, no
TradingAgents call, no rerun of the six-ticker regression -- every case
below is a pure function of already-computed inputs.
"""

from __future__ import annotations

import pytest

from comqutor_alpha.regression import authority_contract as ac


# ---------------------------------------------------------------------------
# CASE 1: provisional expected conflict mismatch -> diagnostic mismatch,
# never a production FAIL.
# ---------------------------------------------------------------------------


def test_case1_provisional_mismatch_is_diagnostic_not_production_fail():
    expectations = [{"pair": "A301__A304", "authority": ac.PROVISIONAL_AI_PREDICTED, "exact_gold": False}]
    result = ac.apply_main_conflict_authority(
        ticker="SNDK", detected_main_conflict="A101__A304", expectations=expectations
    )
    exp = result["expectations"][0]
    assert exp["acceptance_status"] == ac.ACCEPTANCE_PROVISIONAL_DIAGNOSTIC
    assert exp["evaluation_mode"] == "diagnostic"
    assert exp["diagnostic_match"] is False
    # The ticker-level result must never read as a production FAIL for a
    # provisional-only mismatch.
    assert result["ticker_acceptance_status"] == ac.ACCEPTANCE_NOT_GOLD_EVALUABLE
    assert result["ticker_acceptance_result"] is None


def test_case1_documented_mismatch_is_also_diagnostic_not_production_fail():
    expectations = [{"pair": "A101__A304", "authority": ac.DOCUMENTED_EXPECTATION, "exact_gold": False}]
    result = ac.apply_main_conflict_authority(
        ticker="NVDA", detected_main_conflict="A301__A304", expectations=expectations
    )
    exp = result["expectations"][0]
    assert exp["acceptance_status"] == ac.ACCEPTANCE_DOCUMENTED_DIAGNOSTIC
    assert exp["evaluation_mode"] == "diagnostic"
    assert result["ticker_acceptance_result"] is None


# ---------------------------------------------------------------------------
# CASE 2: rejected/superseded conflict expectation -> excluded from the
# positive acceptance denominator.
# ---------------------------------------------------------------------------


def test_case2_rejected_expectation_excluded_from_acceptance_denominator():
    expectations = [{"pair": "A102__A304", "authority": ac.REJECTED_OR_SUPERSEDED, "exact_gold": False}]
    result = ac.apply_main_conflict_authority(ticker="MSFT", detected_main_conflict=None, expectations=expectations)
    assert result["excluded_from_acceptance_denominator"] == ["A102__A304"]
    assert result["ticker_acceptance_status"] == ac.ACCEPTANCE_NOT_GOLD_EVALUABLE
    # Never contributes a PASS or FAIL result.
    assert result["ticker_acceptance_result"] is None


def test_case2_rejected_alpha_expectation_excluded_from_positive_alpha_lists():
    expectations = [
        {"alpha_id": "A999", "authority": ac.REJECTED_OR_SUPERSEDED, "exact_gold": False},
        {"alpha_id": "A301", "authority": ac.PROVISIONAL_AI_PREDICTED, "exact_gold": False},
    ]
    result = ac.apply_alpha_authority(ticker="SNDK", detected_alphas=["A301"], expectations=expectations)
    assert "A999" not in result["diagnostic_expected_alphas"]
    assert "A999" not in result["approved_gold_expected_alphas"]
    assert result["rejected_expected_alphas"] == ["A999"]
    assert result["diagnostic_expected_alphas"] == ["A301"]


# ---------------------------------------------------------------------------
# CASE 3: zero approved gold cases -> acceptance rate is null /
# NOT_GOLD_EVALUABLE, never a misleading 0%.
# ---------------------------------------------------------------------------


def test_case3_zero_gold_alpha_expectations_yields_null_not_zero_percent():
    expectations = [{"alpha_id": "A301", "authority": ac.PROVISIONAL_AI_PREDICTED, "exact_gold": False}]
    result = ac.apply_alpha_authority(ticker="TSM", detected_alphas=[], expectations=expectations)
    assert result["approved_gold_expected_alphas"] == []
    # Must be Python None (JSON null), never the float 0.0.
    assert result["gold_acceptance_hit_rate"] is None
    assert result["gold_acceptance_status"] == ac.ACCEPTANCE_NOT_GOLD_EVALUABLE


def test_case3_expected_alpha_gate_pending_when_no_ticker_has_gold():
    gate = ac.expected_alpha_gate([None, None, None, None, None, None])
    assert gate["current_status"] == "PENDING_APPROVED_GOLD_OR_VALIDATED_CONTRACT"
    assert gate["current_gold_hit_rate"] is None
    assert gate["gate_result"] is None
    assert gate["target"] == 0.75  # target preserved, never deleted


def test_case3_main_conflict_gate_pending_when_zero_evaluable_gold_cases():
    gate = ac.main_conflict_gate({"NVDA": None, "QQQ": None, "MSFT": None, "SNDK": None, "TSM": None, "AMD": None})
    assert gate["current_evaluable_gold_cases"] == 0
    assert gate["status"] == "PENDING_GOLD_CONTRACT"
    assert gate["use_for_current_production_acceptance"] is False
    assert gate["gate_result"] is None
    assert gate["requested_target"] == ">=4/6"  # target preserved, never deleted


def test_case3_gate_activates_once_a_real_gold_case_exists():
    # Once at least one ticker has a real gold hit-rate, the gate must
    # switch to ACTIVE and actually compute a result -- this is not a
    # permanently-disabled gate, only a currently-pending one.
    gate = ac.expected_alpha_gate([0.8, None, None, None, None, None])
    assert gate["current_status"] == "ACTIVE"
    assert gate["current_gold_hit_rate"] == 0.8
    assert gate["gate_result"] == "PASS"

    mc_gate = ac.main_conflict_gate({"NVDA": "PASS", "QQQ": None, "MSFT": None, "SNDK": None, "TSM": None, "AMD": None})
    assert mc_gate["status"] == "ACTIVE"
    assert mc_gate["current_evaluable_gold_cases"] == 1
    assert mc_gate["gate_result"] == "1/1"


# ---------------------------------------------------------------------------
# CASE 4: approved negative Product Decision violated -> valid QA failure.
# ---------------------------------------------------------------------------


def test_case4_negative_constraint_violation_is_a_valid_failure():
    result = ac.check_negative_constraints(
        ticker="MSFT",
        admitted_conflicts=["A102__A304"],
        candidate_conflicts=[],
        rejected_pairs=["A102__A304"],
    )
    assert result["negative_constraint_status"] == "FAIL"
    assert result["violations"] == ["A102__A304"]


def test_case4_negative_constraint_violation_detected_even_as_candidate_only():
    result = ac.check_negative_constraints(
        ticker="SNDK",
        admitted_conflicts=[],
        candidate_conflicts=["A201__A304"],
        rejected_pairs=["A201__A304"],
    )
    assert result["negative_constraint_status"] == "FAIL"
    assert result["violations"] == ["A201__A304"]


def test_case4_no_violation_when_rejected_pair_never_produced():
    result = ac.check_negative_constraints(
        ticker="MSFT",
        admitted_conflicts=["A301__A304"],
        candidate_conflicts=["A304__A601"],
        rejected_pairs=["A102__A304"],
    )
    assert result["negative_constraint_status"] == "PASS"
    assert result["violations"] == []


def test_case4_absence_of_positive_gold_does_not_disable_negative_check():
    # Even with zero approved-gold positive expectations for this ticker,
    # a negative-constraint violation must still be reported as FAIL.
    mc_result = ac.apply_main_conflict_authority(ticker="MSFT", detected_main_conflict=None, expectations=[])
    assert mc_result["ticker_acceptance_status"] == ac.ACCEPTANCE_NOT_GOLD_EVALUABLE
    neg_result = ac.check_negative_constraints(
        ticker="MSFT", admitted_conflicts=["A102__A304"], candidate_conflicts=[], rejected_pairs=["A102__A304"]
    )
    assert neg_result["negative_constraint_status"] == "FAIL"


# ---------------------------------------------------------------------------
# CASE 5: all three current QA artifacts reference identical selected run
# IDs (Step 2/Step 3 alignment, checked against the real repository files).
# ---------------------------------------------------------------------------


def test_case5_qa_closure_index_and_item6_agree_on_all_six_run_ids():
    import json
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    index = json.loads((repo_root / "docs" / "audit_artifacts" / "qa_closure_index.json").read_text())
    item6 = json.loads((repo_root / "docs" / "audit_artifacts" / "item6_a2_artifact_completeness.json").read_text())

    # As of Step 5A (Week2 runtime-capacity repair), Step 4's fresh
    # promotion was ITSELF corrected: those six v0.1.2.1 runs have
    # semantic_execution_health=FAIL (technical completeness alone was
    # insufficient -- see week2_runtime_capacity_root_cause_v0.1.2.1.json),
    # so they were relabeled runtime_failure_baseline and qa_closure_index's
    # top-level selected_runs is now an explicit pending status, never a
    # per-ticker run_id mapping. runtime_failure_baseline still agrees with
    # item6's v0_1_2_1_fresh_baseline block on every run_id -- correcting
    # QA status never silently changed which run_id is on record.
    assert index["selected_runs"]["status"] == "NO_CURRENT_VALID_SEMANTIC_BASELINE"
    fresh_item6 = item6["v0_1_2_1_fresh_baseline"]["tickers"]
    for ticker in ["NVDA", "QQQ", "MSFT", "SNDK", "TSM", "AMD"]:
        index_run_id = index["runtime_failure_baseline"][ticker]["run_id"]
        item6_run_id = fresh_item6[ticker]["run_id"]
        assert index_run_id == item6_run_id, f"{ticker}: qa_closure_index={index_run_id} item6={item6_run_id}"
        assert index["runtime_failure_baseline"][ticker]["semantic_execution_health"] == "FAIL"
        assert index["runtime_failure_baseline"][ticker]["technical_completeness"] == "PASS"

    # The pre-Step-4 (v0.1.2) historical selection is still preserved, byte-
    # identical, under item6's original "tickers" block and qa_closure_index's
    # historical_selected_runs -- never overwritten in place.
    for ticker in ["NVDA", "QQQ", "MSFT", "SNDK", "TSM", "AMD"]:
        historical_index_run_id = index["historical_selected_runs"][ticker]["selected_run_id"]
        historical_item6_run_id = item6["tickers"][ticker]["run_id"]
        assert historical_index_run_id == historical_item6_run_id, (
            f"{ticker}: historical qa_closure_index={historical_index_run_id} "
            f"historical item6={historical_item6_run_id}"
        )


def test_case5_a4_report_current_selection_matches_qa_closure_index():
    import json
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    index = json.loads((repo_root / "docs" / "audit_artifacts" / "qa_closure_index.json").read_text())
    a4 = json.loads((repo_root / "docs" / "audit_artifacts" / "a4_regression_runner_report.json").read_text())

    # As of Step 5A, a4's v0_1_2_1_fresh_baseline_selection block still
    # matches qa_closure_index's per-run_id record for those six runs, now
    # under runtime_failure_baseline (semantic_execution_health=FAIL) rather
    # than selected_runs (which is a pending status, not a per-ticker map,
    # until a repaired six-ticker rerun passes semantic health).
    fresh_selection = a4["v0_1_2_1_fresh_baseline_selection"]["selected_runs"]
    for ticker in ["NVDA", "QQQ", "MSFT", "SNDK", "TSM", "AMD"]:
        assert fresh_selection[ticker]["run_id"] == index["runtime_failure_baseline"][ticker]["run_id"]

    historical_selection = a4["current_selection"]["selected_runs"]
    for ticker in ["NVDA", "QQQ", "MSFT", "SNDK", "TSM", "AMD"]:
        assert historical_selection[ticker]["run_id"] == index["historical_selected_runs"][ticker]["selected_run_id"]


# ---------------------------------------------------------------------------
# CASE 6: historical run provenance may remain while CURRENT selection is
# different.
# ---------------------------------------------------------------------------


def test_case6_a4_report_preserves_historical_snapshot_alongside_current_selection():
    import json
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    a4 = json.loads((repo_root / "docs" / "audit_artifacts" / "a4_regression_runner_report.json").read_text())

    # Historical snapshot (original A4 implementation run) is preserved
    # byte-for-byte in its original field, including its own then-current
    # NVDA/MSFT run_ids -- never rewritten.
    historical = {row["ticker"]: row["run_id"] for row in a4["six_ticker_coverage"]}
    assert historical["NVDA"] == "e3eb3909-3744-4a02-9b32-b225cf6ef665"
    assert historical["MSFT"] == "0cb43bae-1a4d-4003-bb29-55d420498842"

    # The new, clearly-named current section uses the aligned run_ids,
    # genuinely different from the preserved historical ones for these two
    # tickers.
    current = {t: v["run_id"] for t, v in a4["current_selection"]["selected_runs"].items()}
    assert current["NVDA"] == "5ffe121a-68fd-473b-82b5-c9465332d8a2"
    assert current["MSFT"] == "07ddc074-9ab2-4b16-8957-acbf94012144"
    assert current["NVDA"] != historical["NVDA"]
    assert current["MSFT"] != historical["MSFT"]


# ---------------------------------------------------------------------------
# Invariant: an unrecognized authority level is a hard error, never a
# silent default that could let a rejected pair read as gold.
# ---------------------------------------------------------------------------


def test_unknown_authority_level_raises_rather_than_silently_defaulting():
    with pytest.raises(ac.AuthorityContractError):
        ac.acceptance_status_for_authority("NOT_A_REAL_LEVEL")


def test_all_five_step1_authority_levels_map_to_a_defined_acceptance_status():
    for level in ac.VALID_AUTHORITY_LEVELS:
        status = ac.acceptance_status_for_authority(level)
        assert status in {
            ac.ACCEPTANCE_GOLD,
            ac.ACCEPTANCE_DOCUMENTED_DIAGNOSTIC,
            ac.ACCEPTANCE_PROVISIONAL_DIAGNOSTIC,
            ac.ACCEPTANCE_REJECTED,
            ac.ACCEPTANCE_NOT_GOLD_EVALUABLE,
        }
