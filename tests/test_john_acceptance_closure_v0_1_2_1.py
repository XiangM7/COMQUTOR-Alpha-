"""John Item 10 -- Final v0.1.2.1 Acceptance Closure.

Pure audit-artifact consistency tests. Zero Provider calls, zero
TradingAgents calls; never touches production semantic code, Alpha
taxonomy, canonical conflict ontology, or B1/B2/B4 thresholds.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = REPO_ROOT / "docs" / "audit_artifacts"
CLOSURE_PATH = ARTIFACTS / "john_acceptance_closure_v0.1.2.1.json"

FINAL_SELECTED_RUN_IDS = {
    "NVDA": "a8d47429-a47a-446b-93c4-dd718b8e2ff9",
    "QQQ": "defeb528-673e-44f7-8d94-c0abdfef03d4",
    "MSFT": "6cd2566d-e0f1-4306-995f-74f39efb21eb",
    "SNDK": "519c93f4-7fcd-4879-9ca9-dd65badc0fb8",
    "TSM": "0a44ec41-c181-488d-94b8-00a333e85ddb",
    "AMD": "4d8385ef-dff0-4574-b6e7-73fec1eaa5e1",
}


@pytest.fixture(scope="module")
def closure() -> dict:
    return json.loads(CLOSURE_PATH.read_text())


# ---------------------------------------------------------------------------
# Section 1/3: final selected run set + ticker consistency
# ---------------------------------------------------------------------------


def test_final_selected_run_ids_match_johns_stated_set(closure):
    assert closure["final_selected_run_ids"] == FINAL_SELECTED_RUN_IDS


def test_ticker_consistency_is_6_of_6_across_four_authoritative_sources(closure):
    tc = closure["ticker_consistency"]
    assert tc["pass_count"] == 6
    assert tc["required"] == 6
    assert tc["status"] == "PASS"
    assert len(tc["sources_checked"]) == 4
    for ticker, detail in tc["detail"].items():
        assert detail["consistent_across_sources"] is True
        assert detail["expected_run_id"] == FINAL_SELECTED_RUN_IDS[ticker]


# ---------------------------------------------------------------------------
# Section 2: fresh E2E proof
# ---------------------------------------------------------------------------


def test_nvda_and_qqq_are_proven_fresh_production_e2e(closure):
    proof = closure["fresh_e2e_proof"]
    assert proof["NVDA"]["fresh_production_e2e"] is True
    assert proof["QQQ"]["fresh_production_e2e"] is True
    assert proof["NVDA"]["run_id"] == FINAL_SELECTED_RUN_IDS["NVDA"]
    assert proof["QQQ"]["run_id"] == FINAL_SELECTED_RUN_IDS["QQQ"]


def test_all_six_tickers_report_fresh_production_e2e(closure):
    for ticker in FINAL_SELECTED_RUN_IDS:
        assert closure["fresh_e2e_proof"][ticker]["fresh_production_e2e"] is True


# ---------------------------------------------------------------------------
# Section 4: artifact completeness
# ---------------------------------------------------------------------------


def test_artifact_completeness_is_54_of_54(closure):
    ac = closure["artifact_completeness"]
    assert ac["present"] == 54
    assert ac["required"] == 54
    assert ac["status"] == "PASS"
    assert ac["cross_check_consistent_with_item6_a2"] is True
    assert len(ac["required_artifacts_per_ticker"]) == 9


# ---------------------------------------------------------------------------
# Section 5: expected Alpha hit rate -- diagnostic, never approved gold
# ---------------------------------------------------------------------------


def test_alpha_hit_rate_is_12_of_12_but_diagnostic_not_approved_gold(closure):
    ahr = closure["expected_alpha_hit_rate"]
    assert ahr["numerator"] == 12
    assert ahr["denominator"] == 12
    assert ahr["percent"] == 100.0
    assert ahr["meets_threshold_numerically"] is True
    assert ahr["approved_gold_alpha_expectations"] == 0
    assert ahr["status"] == "DIAGNOSTIC"


# ---------------------------------------------------------------------------
# Section 6: Main Conflict match -- must never be manufactured as >=4/6
# ---------------------------------------------------------------------------


def test_main_conflict_match_is_not_gold_evaluable_never_manufactured_pass(closure):
    mc = closure["main_conflict_match"]
    assert mc["gold_evaluable_ticker_count"] == 0
    assert mc["status"] == "NOT_GOLD_EVALUABLE"
    assert mc["formal_gate_reference"]["gate_result"] is None
    assert len(mc["table"]) == 6
    for row in mc["table"]:
        assert row["any_candidate_is_gold_eligible"] is False
        for candidate in row["expected_candidates"]:
            assert candidate["valid_as_exact_regression_gold"] is False


def test_main_conflict_never_substitutes_non_null_for_gold_match(closure):
    # "6/6 non-null" is a real, separately-tracked diagnostic fact elsewhere
    # in the QA index -- it must never appear as this gate's own status.
    assert closure["gates_summary"]["main_conflict_match"] != "PASS"
    assert "NOT_GOLD_EVALUABLE" == closure["gates_summary"]["main_conflict_match"]


# ---------------------------------------------------------------------------
# Section 7/8: Evidence Review v2 (eligible-set acceptance, from Item 9)
# ---------------------------------------------------------------------------


def test_evidence_review_alpha_and_polarity_accuracy_recomputed_correctly(closure):
    er = closure["evidence_review"]
    assert er["source_of_truth_path"] == "docs/audit_artifacts/evidence_review_summary_v2.json"
    assert er["alpha_match_accuracy"]["value_percent"] == 83.0
    assert er["alpha_match_accuracy"]["status"] == "PASS"
    assert er["polarity_accuracy_eligible"]["value_percent"] == 85.25
    assert er["polarity_accuracy_eligible"]["eligible_denominator"] == 61
    assert er["polarity_accuracy_eligible"]["status"] == "PASS"
    assert er["critical_reversal_eligible"]["eligible_value"] == 0
    assert er["critical_reversal_eligible"]["raw_historical_value"] == 1
    assert er["john_approved"] is False


# ---------------------------------------------------------------------------
# Section 9: call accounting -- categories must not be silently merged
# ---------------------------------------------------------------------------


def test_call_accounting_separates_final_run_costs_from_qa_probe_costs(closure):
    ca = closure["call_accounting"]
    final_runs = ca["fresh_production_selected_runs"]
    extra = ca["additional_qa_retry_probe_calls"]
    assert final_runs["tradingagents_successful_executions_in_final_baseline"] == 6
    assert final_runs["provider_semantic_call_attempts"] == ca["headline_provider_calls"]["value"]
    # Health probes are reported separately, never folded into the
    # final-run provider_attempts headline.
    assert extra["health_probes"] == 11
    assert ca["headline_provider_calls"]["including_health_probes"] == (
        ca["headline_provider_calls"]["value"] + extra["health_probes"]
    )
    assert extra["request_dedup_non_executions"] == 2
    assert extra["payment_failed_attempts"] == 5


def test_dedup_non_executions_excluded_from_tradingagents_dispatch_count(closure):
    ca = closure["call_accounting"]
    final_runs = ca["fresh_production_selected_runs"]
    extra = ca["additional_qa_retry_probe_calls"]
    # 11 (Step 10) + 3 (Step 11 genuine) = 14, excluding the 2 dedup hits.
    assert final_runs["tradingagents_attempted_executions_across_establishing_lineage"] == 14
    assert extra["request_dedup_non_executions"] == 2


# ---------------------------------------------------------------------------
# Section 10: no internal QA contradictions
# ---------------------------------------------------------------------------


def test_current_acceptance_contradiction_count_is_zero(closure):
    assert closure["contradiction_audit"]["current_acceptance_contradiction_count"] == 0
    assert closure["contradiction_audit"]["contradictions"] == []


# ---------------------------------------------------------------------------
# Overall verdict + integrity constraints
# ---------------------------------------------------------------------------


def test_overall_acceptance_is_partial_authority_blocker_not_forced_pass(closure):
    assert closure["overall_engineering_acceptance"] == "PARTIAL — AUTHORITY BLOCKER ONLY"
    assert closure["overall_engineering_acceptance"] not in ("PASS", "FAIL — ENGINEERING / QA BLOCKER REMAINS")


def test_john_approved_is_false_and_never_self_satisfied(closure):
    assert closure["john_approved"] is False
    assert closure["john_approval_status"] == "PENDING_JOHN_APPROVAL"


def test_production_integrity_flags_are_all_false(closure):
    assert closure["production_semantic_code_changed"] is False
    assert closure["alpha_taxonomy_changed"] is False
    assert closure["canonical_conflict_ontology_changed"] is False
    assert closure["b1_b2_b4_thresholds_changed"] is False


def test_zero_provider_and_tradingagents_calls_performed_by_this_closure_task(closure):
    assert closure["provider_calls_this_closure_task"] == 0
    assert closure["tradingagents_calls_this_closure_task"] == 0


def test_no_commit_no_push(closure):
    assert closure["commit"] is False
    assert closure["push"] is False


def test_no_import_of_provider_or_tradingagents_client_modules_in_this_test_file():
    tree = ast.parse(Path(__file__).read_text())
    banned_substrings = ("llm_clients", "tradingagents", "week2_llm")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(b in node.module for b in banned_substrings)
