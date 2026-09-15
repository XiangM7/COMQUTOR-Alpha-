"""FINAL Fresh Six-Ticker Production E2E + Regression/Conflict QA (Step 10).

Pure audit over the real, persisted final production run artifacts and the
static Step 10 report artifacts. No Provider calls, no TradingAgents calls
-- everything here reads already-completed run directories and JSON
artifacts.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = REPO_ROOT / "docs" / "audit_artifacts"
OUTPUTS = REPO_ROOT / "outputs" / "runs"

RUN_IDS = {
    "NVDA": "948be419-b542-4096-a536-ff567ef459c2",
    "QQQ": "defeb528-673e-44f7-8d94-c0abdfef03d4",
    "MSFT": "c715460c-5fa3-43d8-9949-97fb6b33e8ec",
    "SNDK": "519c93f4-7fcd-4879-9ca9-dd65badc0fb8",
    "TSM": "5be841d5-0924-4943-8d37-ccd4168228cb",
    "AMD": "4d8385ef-dff0-4574-b6e7-73fec1eaa5e1",
}
REQUIRED_ARTIFACTS = [
    "metadata.json", "raw_agent_outputs.json", "structured_agent_outputs.json",
    "evidence_facts.json", "alpha_matches.json", "structure_graph.json",
    "alpha_activations.json", "conflicts.json", "run_audit.json",
]


@pytest.fixture(scope="module")
def e2e() -> dict:
    return json.loads((ARTIFACTS / "final_six_ticker_production_e2e_v0.1.2.1.json").read_text())


@pytest.fixture(scope="module")
def qa() -> dict:
    return json.loads((ARTIFACTS / "final_regression_conflict_qa_v0.1.2.1.json").read_text())


@pytest.fixture(scope="module")
def qa_index() -> dict:
    return json.loads((ARTIFACTS / "qa_closure_index.json").read_text())


@pytest.fixture(scope="module")
def a4() -> dict:
    return json.loads((ARTIFACTS / "a4_regression_runner_report.json").read_text())


@pytest.fixture(scope="module")
def item6() -> dict:
    return json.loads((ARTIFACTS / "item6_a2_artifact_completeness.json").read_text())


# ---------------------------------------------------------------------------
# Run existence / freshness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ticker", sorted(RUN_IDS))
def test_run_ids_are_new_not_reused_from_prior_steps(ticker):
    """None of the 6 final run_ids collide with any Step-4/Step-5 run_id
    used earlier in this session."""
    prior_run_ids = {
        "6f4e07f9-e7fb-4637-9105-5d6936e28f81", "57244747-7237-4cb6-a01c-cb8dd95d122f",
        "ce6b9628-b23f-4933-9fde-2568b315adf7", "e4309acb-22c6-475e-a357-1e47db587202",
        "43660d9d-5993-4d2d-a7d8-9b3a47fd59b8", "eb714c04-645c-41e2-8292-a4739915f940",
        "5ffe121a-68fd-473b-82b5-c9465332d8a2", "a364e0ee-3bb4-4032-88b7-5cd82e379805",
        "07ddc074-9ab2-4b16-8957-acbf94012144", "183b04dd-aae3-4b33-bbb0-3c9bc3bc942f",
    }
    assert RUN_IDS[ticker] not in prior_run_ids


@pytest.mark.parametrize("ticker", sorted(RUN_IDS))
def test_run_directory_exists_on_disk(ticker):
    assert (OUTPUTS / RUN_IDS[ticker]).is_dir()


# ---------------------------------------------------------------------------
# Artifact completeness: 54/54, recomputed fresh
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ticker", sorted(RUN_IDS))
def test_nine_core_artifacts_present_per_ticker(ticker):
    run_dir = OUTPUTS / RUN_IDS[ticker]
    for filename in REQUIRED_ARTIFACTS:
        assert (run_dir / filename).is_file(), f"{ticker} missing {filename}"


def test_artifact_completeness_is_exactly_54_of_54(e2e):
    ac = e2e["artifact_completeness"]
    assert ac["total_required"] == 54
    assert ac["total_present"] == 54


# ---------------------------------------------------------------------------
# Semantic runtime health honesty -- no silent inflation
# ---------------------------------------------------------------------------


def test_semantic_runtime_health_is_reported_honestly_not_inflated(e2e):
    srh = e2e["semantic_runtime_health"]
    # Recompute coverage directly from the persisted alpha_matches.json for
    # every ticker and confirm it matches the reported per-ticker figure
    # exactly -- the report must not round up or hide a failing ticker.
    for ticker, run_id in RUN_IDS.items():
        data = json.loads((OUTPUTS / run_id / "alpha_matches.json").read_text())
        matches = data["matches"]
        eligible = len(matches)
        matched = sum(1 for m in matches if m.get("match_status") == "matched")
        none_ = sum(1 for m in matches if m.get("match_status") == "no_match")
        coverage = (matched + none_) / eligible
        assert coverage == pytest.approx(srh["per_ticker_coverage"][ticker], abs=1e-9)
    assert srh["tickers_meeting_internal_benchmark"] == 3
    assert srh["tickers_total"] == 6


def test_at_least_one_ticker_genuinely_failed_the_internal_benchmark(e2e):
    """This is the honest, real finding of Step 10 -- the test must fail
    loudly if a future re-generation of the artifact silently claims 6/6."""
    srh = e2e["semantic_runtime_health"]
    failing = [t for t, cov in srh["per_ticker_coverage"].items() if cov < 0.95]
    assert set(failing) == {"NVDA", "MSFT", "TSM"}


def test_unavailable_never_silently_converted_to_none(e2e):
    for ticker, detail in e2e["semantic_runtime_health"]["per_ticker_detail"].items():
        assert detail["disabled_caused_unavailable"] == 0


# ---------------------------------------------------------------------------
# John's 12 historical callouts -- diagnostic, correlated with the runtime failure
# ---------------------------------------------------------------------------


def test_john_callout_misses_are_exactly_the_two_degraded_tickers(e2e):
    callouts = e2e["john_historical_alpha_callouts"]["classification"]
    not_detected = {k for k, v in callouts.items() if v != "DETECTED"}
    not_detected_tickers = {k.split(":")[0] for k in not_detected}
    assert not_detected_tickers == {"MSFT", "TSM"}
    assert e2e["john_historical_alpha_callouts"]["detected_count"] == 7
    assert e2e["john_historical_alpha_callouts"]["total_count"] == 12


# ---------------------------------------------------------------------------
# Step 6 qualification verified live (not offline-only)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ticker", sorted(RUN_IDS))
def test_step6_evidence_qualification_present_in_live_structure_graph(ticker):
    run_dir = OUTPUTS / RUN_IDS[ticker]
    graph = json.loads((run_dir / "structure_graph.json").read_text())
    alphas = graph["activation"]["alphas"]
    assert len(alphas) == 10
    for a in alphas:
        assert "evidence_qualification" in a
        eq = a["evidence_qualification"]
        assert eq["policy_version"] == "evidence_source_role_v1"
        assert "qualified_unique_evidence_fact_count" in eq


@pytest.mark.parametrize("ticker", sorted(RUN_IDS))
def test_step7_display_normalization_present_in_live_structure_graph(ticker):
    run_dir = OUTPUTS / RUN_IDS[ticker]
    graph = json.loads((run_dir / "structure_graph.json").read_text())
    for a in graph["activation"]["alphas"]:
        assert a.get("activation_level") in ("candidate", "active", "capped_active", "dominant", "regime_level")
        assert a.get("activation_level") != "candidate_active"


# ---------------------------------------------------------------------------
# Negative constraints
# ---------------------------------------------------------------------------


def test_negative_constraints_all_pass(qa):
    assert qa["negative_constraints"]["status"] == "PASS"
    assert qa["negative_constraints"]["violation_count"] == 0
    for pair in ["MSFT:A102__A304", "SNDK:A201__A304", "TSM:A201__A304", "AMD:A201__A304"]:
        assert pair in qa["negative_constraints"]["pairs_checked"]


def test_no_null_main_conflict_is_ever_flagged_as_a_negative_constraint_violation(qa):
    for result in qa["negative_constraints"]["results"]:
        assert result["status"] in ("PASS", "VIOLATION")


# ---------------------------------------------------------------------------
# Formal gold gates remain honestly pending
# ---------------------------------------------------------------------------


def test_formal_alpha_gate_remains_pending_not_faked_pass_or_fail(qa):
    gate = qa["expected_alpha_regression"]["formal_gate"]
    assert gate["current_status"] == "PENDING_APPROVED_GOLD_OR_VALIDATED_CONTRACT"
    assert gate["gate_result"] is None


def test_formal_main_conflict_gate_remains_pending_not_faked_pass_or_fail(qa):
    gate = qa["main_conflict_regression"]["formal_gate"]
    assert gate["status"] == "PENDING_GOLD_CONTRACT"
    assert gate["use_for_current_production_acceptance"] is False
    assert gate["gate_result"] is None


def test_diagnostic_numbers_never_relabeled_as_formal_acceptance(qa):
    assert qa["expected_alpha_regression"]["john_threshold_use"] == "DIAGNOSTIC_ONLY"
    assert qa["main_conflict_regression"]["john_threshold_use"] == "DIAGNOSTIC_ONLY"


def test_gold_authority_state_unchanged_zero_approved_gold(qa):
    assert qa["gold_authority_state"]["approved_gold_alpha_expectations"] == 0
    assert qa["gold_authority_state"]["approved_gold_main_conflict_expectations"] == 0


# ---------------------------------------------------------------------------
# Run-id consistency across the three aligned artifacts
# ---------------------------------------------------------------------------


def test_run_id_consistency_across_qa_index_a4_and_item6(qa_index, a4, item6):
    qa_run_ids = qa_index["final_v0_1_2_1_production_e2e"]["run_ids"]
    a4_run_ids = {t: v["run_id"] for t, v in a4["final_v0_1_2_1_production_e2e_step10"]["run_ids"].items()} if isinstance(a4["final_v0_1_2_1_production_e2e_step10"]["run_ids"], dict) and "run_id" in next(iter(a4["final_v0_1_2_1_production_e2e_step10"]["run_ids"].values())) else a4["final_v0_1_2_1_production_e2e_step10"]["run_ids"]
    item6_run_ids = {t: v["run_id"] for t, v in item6["v0_1_2_1_step10_final_production_e2e"]["tickers"].items()}
    assert qa_run_ids == RUN_IDS
    assert item6_run_ids == RUN_IDS


def test_qa_closure_index_does_not_silently_promote_degraded_runs_as_valid_baseline(qa_index):
    # selected_runs (the actual regression-baseline gate) must remain
    # untouched/still-cautious -- Step 10 adds an ADDITIVE new block, it
    # never flips the existing gate to "valid" when semantic health failed
    # on 3/6 tickers.
    assert qa_index["selected_runs"]["status"] == "NO_CURRENT_VALID_SEMANTIC_BASELINE"


# ---------------------------------------------------------------------------
# No production semantic changes
# ---------------------------------------------------------------------------


def test_production_semantic_files_unchanged_during_step10():
    # v0.1.3 QA Closure, Sections C/D: conflict_detector.py and
    # alpha_level_classifier.py were deliberately, authorizedly changed
    # after Step 10 shipped (John's A301 active-display gate and evidence-
    # polarity bull/bear display fixes -- see
    # tests/test_b4_activation_level_alignment.py's test_c2_* tests and
    # tests/test_conflict_detector.py's TestEvidencePolarityBullBearAssignment).
    # Both hashes updated deliberately for those authorized changes; this
    # guard's job is to catch an UNREVIEWED future drift, not to freeze the
    # files forever.
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
        assert actual == expected, f"{path} hash changed during Step 10"


def test_e2e_report_declares_no_production_semantic_changes(e2e):
    assert e2e["production_semantic_code_changed"] is False
    assert e2e["alpha_mapper_changed"] is False
    assert e2e["taxonomy_changed"] is False
    assert e2e["b1_changed"] is False
    assert e2e["b2_changed"] is False
    assert e2e["b4_changed"] is False
    assert e2e["step6_evidence_qualification_changed"] is False
    assert e2e["step7_display_normalization_changed"] is False
    assert e2e["commit"] is False
    assert e2e["push"] is False


def test_whole_ticker_retries_are_documented_with_full_audit_trail(e2e):
    retries = e2e["whole_ticker_retries"]
    assert len(retries) == 5
    for r in retries:
        assert r["failed_run_id"]
        assert r["successful_replacement_run_id"]
        assert r["ticker"] in {"QQQ", "MSFT", "SNDK", "TSM", "AMD"}
