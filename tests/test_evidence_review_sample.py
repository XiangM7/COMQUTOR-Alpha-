"""Sprint 2, Track J3: evidence_review_sample.csv exporter tests (task
spec section 28, items 46-60).

Uses real local outputs/runs/ source data via Architecture Replay --
offline, deterministic, zero Provider/LLM/DB calls. The module-scoped
fixture builds the real 6-ticker/50-row sample once; per-test assertions
read from that single build to keep the suite fast.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from comqutor_alpha.evaluation.evidence_review_sample import (
    CSV_FIELDNAMES,
    DEFAULT_TICKERS,
    MAX_PER_TICKER,
    MIN_PER_TICKER,
    REQUESTED_STANCE_QUOTAS,
    REVIEWER_BLANK_FIELDNAMES,
    build_evidence_review_sample,
    write_evidence_review_sample_csv,
    write_evidence_review_sample_manifest,
    write_evidence_review_sample_records_json,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_OUTPUT_ROOT = REPO_ROOT / "outputs" / "runs"


@pytest.fixture(scope="module")
def sample_result(tmp_path_factory):
    replay_root = tmp_path_factory.mktemp("evidence_review_sample_replays")
    return build_evidence_review_sample(
        tickers=DEFAULT_TICKERS,
        count=50,
        source_output_root=str(SOURCE_OUTPUT_ROOT),
        replay_output_root=str(replay_root),
    )


@pytest.fixture(scope="module")
def sample_outputs(tmp_path_factory, sample_result):
    out_dir = tmp_path_factory.mktemp("evidence_review_sample_outputs")
    csv_path = out_dir / "evidence_review_sample.csv"
    csv_sha = write_evidence_review_sample_csv(sample_result, csv_path)
    records_path = out_dir / "evidence_review_sample_records.json"
    write_evidence_review_sample_records_json(sample_result, records_path)
    manifest_path = out_dir / "evidence_review_sample_manifest.json"
    write_evidence_review_sample_manifest(
        sample_result, manifest_path, csv_sha256=csv_sha, generated_at="2026-08-04T00:00:00+00:00"
    )
    return {"csv_path": csv_path, "records_path": records_path, "manifest_path": manifest_path, "csv_sha256": csv_sha}


# ---------------------------------------------------------------------------
# 46-50: sample composition
# ---------------------------------------------------------------------------


def test_46_exactly_50_unique_rows_when_enough_candidates_exist(sample_result):
    assert sample_result.verdict == "PASS"
    assert sample_result.actual_count == 50
    assert len(sample_result.rows) == 50


def test_47_no_duplicate_candidate_key(sample_result):
    keys = [
        (r["ticker"], r["run_id"], r["claim_id"], r["target_alpha_id"]) for r in sample_result.rows
    ]
    assert len(keys) == len(set(keys))


def test_48_deterministic_byte_identical_output(tmp_path_factory, sample_result):
    out_dir = tmp_path_factory.mktemp("determinism_check")
    path_a = out_dir / "a.csv"
    path_b = out_dir / "b.csv"
    sha_a = write_evidence_review_sample_csv(sample_result, path_a)
    sha_b = write_evidence_review_sample_csv(sample_result, path_b)
    assert sha_a == sha_b
    assert path_a.read_bytes() == path_b.read_bytes()


def test_49_six_ticker_coverage(sample_result):
    selected_tickers = {r["ticker"] for r in sample_result.rows}
    assert selected_tickers.issubset(set(DEFAULT_TICKERS))
    for ticker in DEFAULT_TICKERS:
        count = sample_result.ticker_distribution.get(ticker, 0)
        selection = next(s for s in sample_result.ticker_selections if s.ticker == ticker)
        if selection.status == "selected":
            assert MIN_PER_TICKER <= count <= MAX_PER_TICKER, (ticker, count)
        else:
            assert count == 0


def test_50_quota_calculations_correct(sample_result):
    for stance, target in REQUESTED_STANCE_QUOTAS.items():
        actual = sample_result.actual_quotas[stance]
        shortfall = sample_result.quota_shortfalls[stance]
        assert actual + shortfall >= target or actual == target
        assert shortfall == max(0, target - actual)
        assert sample_result.stance_distribution[stance] == actual
    assert sum(sample_result.actual_quotas.values()) == sample_result.actual_count


def test_51_quota_shortfall_honestly_reported(sample_result):
    # Every requested quota was satisfiable from real 6-ticker data in this
    # environment (verdict PASS, all shortfalls 0) -- this asserts the
    # reporting mechanism itself is wired, not that a shortfall exists.
    assert isinstance(sample_result.quota_shortfalls, dict)
    assert set(sample_result.quota_shortfalls) == set(REQUESTED_STANCE_QUOTAS)
    if sample_result.verdict == "PARTIAL":
        assert sample_result.actual_count < sample_result.requested_count


# ---------------------------------------------------------------------------
# 52-53: reviewer fields
# ---------------------------------------------------------------------------


def test_52_reviewer_fields_blank(sample_result):
    for row in sample_result.rows:
        for field_name in REVIEWER_BLANK_FIELDNAMES:
            assert row[field_name] == ""


def test_53_review_status_pending(sample_result):
    for row in sample_result.rows:
        assert row["review_status"] == "pending"


# ---------------------------------------------------------------------------
# 54-57: CSV safety and integrity
# ---------------------------------------------------------------------------


def test_54_multiline_evidence_safely_quoted(sample_outputs):
    with sample_outputs["csv_path"].open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    assert len(rows) == 50
    for row in rows:
        assert set(row.keys()) == set(CSV_FIELDNAMES)


def test_55_csv_formula_injection_protected(sample_result, tmp_path):
    injected = dict(sample_result.rows[0])
    injected["claim"] = "=cmd|' /C calc'!A0"
    injected["evidence"] = "+1+1"
    fabricated_rows = [injected]

    class _Fake:
        rows = fabricated_rows

    csv_path = tmp_path / "injection_check.csv"
    write_evidence_review_sample_csv(_Fake(), csv_path)
    content = csv_path.read_text(encoding="utf-8")
    assert "\n=cmd" not in content and ",=cmd" not in content
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        row = next(reader)
    assert row["claim"].startswith("'=")
    assert row["evidence"].startswith("'+")


def test_56_json_companion_preserves_exact_original_text(sample_outputs, sample_result):
    payload = json.loads(sample_outputs["records_path"].read_text(encoding="utf-8"))
    assert payload["count"] == 50
    by_sample_id = {r["sample_id"]: r for r in payload["records"]}
    for row in sample_result.rows:
        original = by_sample_id[row["sample_id"]]
        assert original["claim"] == row["claim"]
        assert original["evidence"] == row["evidence"]


def test_57_csv_sha_matches_manifest(sample_outputs):
    manifest = json.loads(sample_outputs["manifest_path"].read_text(encoding="utf-8"))
    assert manifest["csv_sha256"] == sample_outputs["csv_sha256"]


# ---------------------------------------------------------------------------
# 58-60: traceability and coverage
# ---------------------------------------------------------------------------


def test_58_sample_rows_trace_back_to_real_artifacts(sample_result):
    for selection in sample_result.ticker_selections:
        if selection.status != "selected":
            continue
        source_dir = SOURCE_OUTPUT_ROOT / selection.source_run_id
        assert source_dir.exists()
        assert (source_dir / "raw_agent_outputs.json").exists()
    for row in sample_result.rows:
        assert row["claim_id"].startswith(row["source_run_id"])


def test_59_sample_contains_manual_review_cases(sample_result):
    assert sample_result.manual_review_count > 0
    assert any(r["requires_manual_review"] for r in sample_result.rows)


def test_60_sample_includes_conflict_and_activation_evidence(sample_result):
    assert sample_result.activation_evidence_count > 0
    assert sample_result.conflict_evidence_count > 0
    assert any(r["used_in_activation"] for r in sample_result.rows)
    assert any(r["used_in_conflict"] for r in sample_result.rows)


def test_source_hashes_recorded_and_match_disk(sample_result):
    import hashlib

    for selection in sample_result.ticker_selections:
        if selection.status != "selected":
            continue
        digest = selection.source_artifact_hashes.get("raw_agent_outputs.json")
        assert digest
        raw_path = SOURCE_OUTPUT_ROOT / selection.source_run_id / "raw_agent_outputs.json"
        assert digest == hashlib.sha256(raw_path.read_bytes()).hexdigest()
