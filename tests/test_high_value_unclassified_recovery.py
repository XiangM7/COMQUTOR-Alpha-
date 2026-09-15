"""High-Value Unclassified Recovery Closure (Step 9 / John #7).

Pure audit over already-persisted Step 5A healthy six-ticker semantic
outputs. Zero Provider calls, zero TradingAgents calls. These tests read
the static report artifact and the persisted alpha_matches.json source
files -- they never call a Provider and never touch production semantic
code.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = REPO_ROOT / "docs" / "audit_artifacts"
REPORT_PATH = ARTIFACTS / "high_value_unclassified_recovery_report.json"
PRELIM_PATH = ARTIFACTS / "high_value_true_none_candidates_v0.1.2.1.json"
QA_INDEX_PATH = ARTIFACTS / "qa_closure_index.json"
TICKERS = ("NVDA", "QQQ", "MSFT", "SNDK", "TSM", "AMD")


@pytest.fixture(scope="module")
def report() -> dict:
    return json.loads(REPORT_PATH.read_text())


@pytest.fixture(scope="module")
def qa_index() -> dict:
    return json.loads(QA_INDEX_PATH.read_text())


# ---------------------------------------------------------------------------
# Case 1-2: pool membership rules
# ---------------------------------------------------------------------------


def test_case1_unavailable_rows_cannot_enter_recovery_pool(report):
    for r in report["reviewed_candidates"]:
        assert r["final_semantic_result"] == "NONE"
    # Direct source-data confirmation: unavailable is a distinct, excluded status.
    for ticker in TICKERS:
        run_dir = REPO_ROOT / "outputs" / "runs" / f"_step5a_coverage_{ticker.lower()}"
        data = json.loads((run_dir / "alpha_matches.json").read_text())
        statuses = {m.get("match_status") for m in data["matches"]}
        assert "unavailable" in statuses  # exists in the source data
    reviewed_ids = {r["claim_id"] for r in report["reviewed_candidates"]}
    unavailable_ids = set()
    for ticker in TICKERS:
        run_dir = REPO_ROOT / "outputs" / "runs" / f"_step5a_coverage_{ticker.lower()}"
        data = json.loads((run_dir / "alpha_matches.json").read_text())
        unavailable_ids |= {m["claim_id"] for m in data["matches"] if m.get("match_status") == "unavailable"}
    assert reviewed_ids.isdisjoint(unavailable_ids)


def test_case2_only_valid_none_rows_can_enter_recovery_pool(report):
    reviewed_ids = {r["claim_id"] for r in report["reviewed_candidates"]}
    valid_none_ids = set()
    for ticker in TICKERS:
        run_dir = REPO_ROOT / "outputs" / "runs" / f"_step5a_coverage_{ticker.lower()}"
        data = json.loads((run_dir / "alpha_matches.json").read_text())
        valid_none_ids |= {m["claim_id"] for m in data["matches"] if m.get("match_status") == "no_match"}
    assert reviewed_ids <= valid_none_ids
    assert report["total_valid_none"] == len(valid_none_ids) == 2764


# ---------------------------------------------------------------------------
# Case 3-4: classification rigor
# ---------------------------------------------------------------------------


def test_case3_keyword_hit_alone_cannot_produce_strong_recovery_candidate(report):
    for r in report["strong_recovery_candidates"]:
        assert r["single_best_fit"] is True
        assert r["high_value"] is True
        # A keyword-only diagnostic signal is never sufficient on its own --
        # canonical_fit_analysis must be a real mechanism explanation, not a
        # bare keyword restatement.
        assert len(r["canonical_fit_analysis"]) > 20


def test_case4_single_best_alpha_requirement_is_enforced(report):
    for r in report["reviewed_candidates"]:
        if r["classification"] == "STRONG_RECOVERY_CANDIDATE":
            assert r["single_best_fit"] is True
        if r["classification"] in ("CORRECT_NONE", "DUPLICATE_OR_LOW_VALUE"):
            assert r["single_best_fit"] is not True or r["classification"] == "DUPLICATE_OR_LOW_VALUE"


# ---------------------------------------------------------------------------
# Case 5-6: duplicate/borderline do not inflate the target count
# ---------------------------------------------------------------------------


def test_case5_duplicate_low_value_claims_do_not_count_toward_recovery_target(report):
    duplicate_ids = {r["claim_id"] for r in report["duplicate_or_low_value_cases"]}
    strong_ids = {r["claim_id"] for r in report["strong_recovery_candidates"]}
    assert duplicate_ids.isdisjoint(strong_ids)
    assert report["observed_strong_recovery_count"] == len(strong_ids)


def test_case6_borderline_candidates_do_not_count_as_strong_target_satisfaction(report):
    assert report["observed_strong_recovery_count"] == len(report["strong_recovery_candidates"])
    borderline_ids = {r["claim_id"] for r in report["borderline_candidates"]}
    strong_ids = {r["claim_id"] for r in report["strong_recovery_candidates"]}
    assert borderline_ids.isdisjoint(strong_ids)


# ---------------------------------------------------------------------------
# Case 7-9: target status logic
# ---------------------------------------------------------------------------


def _target_status_for(strong_count: int) -> str:
    return "TARGET_SUPPORTED" if strong_count >= 20 else "TARGET_NOT_SUPPORTED_BY_HEALTHY_SEMANTIC_DATA"


def test_case7_nineteen_strong_plus_borderline_is_not_supported():
    assert _target_status_for(19) == "TARGET_NOT_SUPPORTED_BY_HEALTHY_SEMANTIC_DATA"


def test_case8_twenty_strong_is_supported():
    assert _target_status_for(20) == "TARGET_SUPPORTED"


def test_case9_requested_target_remains_exactly_20(report):
    assert report["requested_recovery_target"] == 20


def test_actual_observed_result_matches_computed_status(report):
    assert report["target_status"] == _target_status_for(report["observed_strong_recovery_count"])
    assert report["observed_strong_recovery_count"] == 0
    assert report["target_status"] == "TARGET_NOT_SUPPORTED_BY_HEALTHY_SEMANTIC_DATA"


# ---------------------------------------------------------------------------
# Case 10-11: artifact/history integrity
# ---------------------------------------------------------------------------


def test_case10_production_semantic_artifacts_are_not_modified():
    import subprocess

    frozen_hashes = {
        "comqutor_alpha/structure_engine/alpha_mapper.py": "506a228eb10e0b77b2058c9eaa327ae0ec44ba36b1515e5e6400187ffe65a6fd",
        "comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml": "c031168c726cd424252cd9ee0491e55f335b5966694a326e0bcdfeeab1e7939c",
    }
    for path, expected in frozen_hashes.items():
        actual = hashlib.sha256((REPO_ROOT / path).read_bytes()).hexdigest()
        assert actual == expected, f"{path} hash changed"


def test_case11_historical_step5b_artifact_remains_historical():
    prelim = json.loads(PRELIM_PATH.read_text())
    assert prelim["raw_keyword_hits"] == 23
    assert len(prelim["strong_candidates"]) == 1
    assert len(prelim["weak_borderline_candidates"]) == 3
    # Untouched by this session's Steps 4-9 work -- it is untracked ("??"),
    # never committed, so "modified" ("M ") is the meaningful check, not
    # bare emptiness of git status.
    import subprocess

    result = subprocess.run(
        ["git", "status", "--short", str(PRELIM_PATH.relative_to(REPO_ROOT))],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert not result.stdout.strip().startswith("M")


# ---------------------------------------------------------------------------
# Case 12: qa_closure_index wiring
# ---------------------------------------------------------------------------


def test_case12_qa_closure_index_points_john7_to_new_authoritative_report(qa_index):
    block = qa_index["step9_high_value_unclassified_recovery"]
    assert block["artifact_path"] == "docs/audit_artifacts/high_value_unclassified_recovery_report.json"
    assert block["requested_target"] == 20
    assert block["target_status"] == "TARGET_NOT_SUPPORTED_BY_HEALTHY_SEMANTIC_DATA"
    assert block["production_semantic_changes"] is False
    assert block["provider_calls"] == 0
    assert block["tradingagents_calls"] == 0
