"""Provider Health Recheck + Degraded-Ticker Clean Rerun (Step 11).

Pure audit over the real, persisted repaired run artifacts and the static
Step 11 report artifacts. No Provider calls, no TradingAgents calls.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = REPO_ROOT / "docs" / "audit_artifacts"
OUTPUTS = REPO_ROOT / "outputs" / "runs"

FINAL_RUN_IDS = {
    "NVDA": "a8d47429-a47a-446b-93c4-dd718b8e2ff9",
    "QQQ": "defeb528-673e-44f7-8d94-c0abdfef03d4",
    "MSFT": "6cd2566d-e0f1-4306-995f-74f39efb21eb",
    "SNDK": "519c93f4-7fcd-4879-9ca9-dd65badc0fb8",
    "TSM": "0a44ec41-c181-488d-94b8-00a333e85ddb",
    "AMD": "4d8385ef-dff0-4574-b6e7-73fec1eaa5e1",
}
STEP10_DEGRADED_RUN_IDS = {
    "NVDA": "948be419-b542-4096-a536-ff567ef459c2",
    "MSFT": "c715460c-5fa3-43d8-9949-97fb6b33e8ec",
    "TSM": "5be841d5-0924-4943-8d37-ccd4168228cb",
}
REQUIRED_ARTIFACTS = [
    "metadata.json", "raw_agent_outputs.json", "structured_agent_outputs.json",
    "evidence_facts.json", "alpha_matches.json", "structure_graph.json",
    "alpha_activations.json", "conflicts.json", "run_audit.json",
]


@pytest.fixture(scope="module")
def step11() -> dict:
    return json.loads((ARTIFACTS / "step11_provider_health_and_rerun_v0.1.2.1.json").read_text())


@pytest.fixture(scope="module")
def e2e_r2() -> dict:
    return json.loads((ARTIFACTS / "final_six_ticker_production_e2e_v0.1.2.1_r2.json").read_text())


@pytest.fixture(scope="module")
def e2e_step10() -> dict:
    return json.loads((ARTIFACTS / "final_six_ticker_production_e2e_v0.1.2.1.json").read_text())


@pytest.fixture(scope="module")
def qa_r2() -> dict:
    return json.loads((ARTIFACTS / "final_regression_conflict_qa_v0.1.2.1_r2.json").read_text())


@pytest.fixture(scope="module")
def qa_index() -> dict:
    return json.loads((ARTIFACTS / "qa_closure_index.json").read_text())


# ---------------------------------------------------------------------------
# Health gate
# ---------------------------------------------------------------------------


def test_preflight_and_health_probe_passed(step11):
    assert step11["preflight"]["result"] == "PASS"
    probe = step11["live_health_probe"]
    assert probe["requests"] == 10
    assert probe["successes"] == 10
    assert probe["unavailable_or_errors"] == 0
    assert probe["payment_errors_detected"] == 0
    assert step11["health_gate_result"] == "PASS"


# ---------------------------------------------------------------------------
# Reruns produced genuinely new run_ids -- the dedup-hit regression guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ticker", ["NVDA", "MSFT", "TSM"])
def test_rerun_run_id_differs_from_step10_degraded_run_id(ticker):
    assert FINAL_RUN_IDS[ticker] != STEP10_DEGRADED_RUN_IDS[ticker]


def test_dedup_hit_was_detected_and_corrected_for_msft_and_tsm(step11):
    for ticker in ["MSFT", "TSM"]:
        detail = step11["reruns"][ticker]
        assert detail["dedup_hit_detected"] is True
        assert detail["force_refresh_needed"] is True
        assert len(detail["attempts"]) == 2


def test_nvda_did_not_need_force_refresh(step11):
    assert step11["reruns"]["NVDA"]["dedup_hit_detected"] is False


@pytest.mark.parametrize("ticker", ["NVDA", "MSFT", "TSM"])
def test_rerun_directory_exists_and_is_complete(ticker):
    run_dir = OUTPUTS / FINAL_RUN_IDS[ticker]
    assert run_dir.is_dir()
    for filename in REQUIRED_ARTIFACTS:
        assert (run_dir / filename).is_file(), f"{ticker} missing {filename}"


# ---------------------------------------------------------------------------
# Replacement rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ticker", ["NVDA", "MSFT", "TSM"])
def test_replacement_rule_all_four_conditions_met(step11, ticker):
    v = step11["replacement_rule_verification"][ticker]
    assert v["technical_completeness_9_of_9"] is True
    assert v["new_run_id_confirmed"] is True
    assert v["semantic_execution_health_materially_healthy"] is True
    assert v["no_configuration_invalid_condition"] is True
    assert v["replacement_decision"] == "YES"


def test_final_baseline_status_is_repaired(step11):
    assert step11["final_baseline_status"] == "REPAIRED"


# ---------------------------------------------------------------------------
# Retry policy -- only structural/provider reasons ever justified a retry
# ---------------------------------------------------------------------------


def test_no_retry_reason_cites_semantic_dissatisfaction(step11):
    forbidden_phrases = ("alpha is missing", "conflict is null", "activation is low", "diagnostic regression")
    blob = json.dumps(step11).lower()
    for phrase in forbidden_phrases:
        assert phrase not in blob


# ---------------------------------------------------------------------------
# QQQ/SNDK/AMD were NOT rerun
# ---------------------------------------------------------------------------


def test_qqq_sndk_amd_retained_unchanged_from_step10(e2e_r2, e2e_step10):
    for ticker in ["QQQ", "SNDK", "AMD"]:
        assert e2e_r2["run_ids"][ticker] == e2e_step10["run_ids"][ticker]


def test_step10_artifact_not_overwritten(e2e_step10):
    # Step 10's own report must still show its original (degraded) numbers --
    # proof this task did not silently rewrite history.
    assert e2e_step10["semantic_runtime_health"]["tickers_meeting_internal_benchmark"] == 3


# ---------------------------------------------------------------------------
# Composite semantic runtime health: now 6/6
# ---------------------------------------------------------------------------


def test_composite_semantic_runtime_health_is_6_of_6(e2e_r2):
    srh = e2e_r2["semantic_runtime_health"]
    assert srh["tickers_meeting_internal_benchmark"] == 6
    assert srh["tickers_total"] == 6
    for ticker, cov in srh["per_ticker_coverage"].items():
        assert cov >= 0.95, f"{ticker} below internal benchmark: {cov}"


def test_artifact_completeness_54_of_54(e2e_r2):
    ac = e2e_r2["artifact_completeness"]
    assert ac["total_present"] == 54
    assert ac["total_required"] == 54


# ---------------------------------------------------------------------------
# John callouts / main conflicts / negative constraints on composite
# ---------------------------------------------------------------------------


def test_john_callouts_12_of_12_on_composite(e2e_r2):
    assert e2e_r2["john_historical_alpha_callouts"]["detected_count"] == 12
    assert e2e_r2["john_historical_alpha_callouts"]["total_count"] == 12


def test_main_conflicts_non_null_on_composite(e2e_r2):
    main_conflicts = e2e_r2["conflict_b2_final_observation"]["main_conflicts"]
    assert all(v for v in main_conflicts.values())
    assert e2e_r2["conflict_b2_final_observation"]["non_null_count"] == 6


def test_negative_constraints_pass_on_composite(e2e_r2):
    assert e2e_r2["negative_constraints"]["status"] == "PASS"
    assert e2e_r2["negative_constraints"]["violation_count"] == 0


# ---------------------------------------------------------------------------
# Formal gates unchanged; Step 8/9 conclusions unchanged
# ---------------------------------------------------------------------------


def test_formal_gates_remain_pending_despite_strong_diagnostic(qa_r2):
    alpha_gate = qa_r2["expected_alpha_regression"]["formal_gate"]
    conflict_gate = qa_r2["main_conflict_regression"]["formal_gate"]
    assert alpha_gate["current_status"] == "PENDING_APPROVED_GOLD_OR_VALIDATED_CONTRACT"
    assert alpha_gate["gate_result"] is None
    assert conflict_gate["status"] == "PENDING_GOLD_CONTRACT"
    assert conflict_gate["gate_result"] is None


def test_step8_and_step9_conclusions_unchanged(qa_r2):
    s8 = qa_r2["step8_evidence_review_v2_unchanged"]
    assert s8["alpha_accuracy_percent"] == 83.0
    assert s8["polarity_accuracy_percent"] == 83.87
    assert s8["raw_critical_reversal"] == 1
    assert s8["status"] == "PENDING_CRITICAL_REVERSAL_ADJUDICATION"
    assert s8["john_approval_status"] == "PENDING_JOHN_APPROVAL"
    assert qa_r2["step9_high_value_recovery_unchanged"]["target_status"] == "TARGET_NOT_SUPPORTED_BY_HEALTHY_SEMANTIC_DATA"


# ---------------------------------------------------------------------------
# Run-id consistency across the aligned artifacts
# ---------------------------------------------------------------------------


def test_run_id_consistency_across_qa_index_a4_and_item6(qa_index):
    a4 = json.loads((ARTIFACTS / "a4_regression_runner_report.json").read_text())
    item6 = json.loads((ARTIFACTS / "item6_a2_artifact_completeness.json").read_text())
    qa_run_ids = qa_index["final_v0_1_2_1_production_e2e_r2"]["run_ids"]
    a4_run_ids = a4["final_v0_1_2_1_production_e2e_r2_step11"]["run_ids"]
    item6_run_ids = {t: v["run_id"] for t, v in item6["v0_1_2_1_step11_final_production_e2e_r2"]["tickers"].items()}
    assert qa_run_ids == FINAL_RUN_IDS
    assert a4_run_ids == FINAL_RUN_IDS
    assert item6_run_ids == FINAL_RUN_IDS


def test_history_preserved_not_deleted(qa_index):
    assert "final_v0_1_2_1_production_e2e" in qa_index  # Step 10 block still present
    assert "selected_runs" in qa_index  # original cautious gate still present
    assert qa_index["selected_runs"]["status"] == "NO_CURRENT_VALID_SEMANTIC_BASELINE"


# ---------------------------------------------------------------------------
# No production semantic changes
# ---------------------------------------------------------------------------


def test_production_semantic_files_unchanged_during_step11():
    # v0.1.3 QA Closure, Sections C/D: conflict_detector.py and
    # alpha_level_classifier.py were deliberately, authorizedly changed
    # after Step 11 shipped (John's A301 active-display gate and evidence-
    # polarity bull/bear display fixes -- see
    # tests/test_b4_activation_level_alignment.py's test_c2_* tests and
    # tests/test_conflict_detector.py's TestEvidencePolarityBullBearAssignment).
    # Both hashes updated deliberately for those authorized changes.
    # v0.1.3 P0/P1 Evidence Correctness Fix: activation_scorer_v2.py's hash
    # updated deliberately for that authorized change (foreign-issuer-only
    # evidence-ownership qualification veto + company_names propagation) --
    # see tests/test_p0_p1_evidence_correctness_fix.py.
    frozen_hashes = {
        "comqutor_alpha/structure_engine/alpha_mapper.py": "506a228eb10e0b77b2058c9eaa327ae0ec44ba36b1515e5e6400187ffe65a6fd",
        "comqutor_alpha/graph_engine/activation_scorer_v2.py": "c1b0a479a1d06c94811004c2ea62d95598427ea4541e0f770a5d4633e642911e",
        "comqutor_alpha/conflict_engine/conflict_detector.py": "f07604bc61a713f7ed3db4cb4db5b6ae9091487cf83c85e40b68696f9c3874da",
        "comqutor_alpha/graph_engine/alpha_level_classifier.py": "3cf25b42cbc91d8976978d89c45cbab45859accd37c6a8f8731ff42eabb1da85",
        "comqutor_alpha/graph_engine/evidence_source_role.py": "4835e4e2d83b8438bf23d1a9c35123072439d5f501146b77d8d038585d47ae99",
        "comqutor_alpha/graph_engine/alpha_display_normalizer.py": "f63cb9d63a157ab2d817d66d071b94f6b967809d871bc3bb067a2afa9d7ebeea",
        "comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml": "c031168c726cd424252cd9ee0491e55f335b5966694a326e0bcdfeeab1e7939c",
    }
    for path, expected in frozen_hashes.items():
        actual = hashlib.sha256((REPO_ROOT / path).read_bytes()).hexdigest()
        assert actual == expected, f"{path} hash changed during Step 11"


def test_r2_report_declares_no_production_semantic_changes(e2e_r2):
    assert e2e_r2["production_semantic_code_changed"] is False
    assert e2e_r2["alpha_mapper_changed"] is False
    assert e2e_r2["taxonomy_changed"] is False
    assert e2e_r2["commit"] is False
    assert e2e_r2["push"] is False
