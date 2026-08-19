"""QA Closure v0.1.2 Item 6 (Complete Nine-Artifact Bundle Per Regression
Ticker) -- dedicated tests.

``check_artifact_bundle`` is exercised against synthetic temp-directory
fixtures (never a real saved run, so a bad-data test case can never touch
real data). ``reconstruct_missing_artifacts`` is exercised against a real,
already-saved run's own untouched source artifacts (structure_graph.json/
alpha_matches.json), written into an ISOLATED temp copy -- never the real
``outputs/runs/`` tree -- so reconstruction can be tested repeatedly
without risk to the actual regression fixtures this session already
completed.

Section map:
    A - check_artifact_bundle: presence/validity/identity
    B - reconstruct_missing_artifacts: real-data reconstruction, never
        overwrites, provenance, zero Provider calls
    C - classify_bundle_status / build_bundle_manifest
    D - determinism
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from comqutor_alpha.api.artifact_export import REQUIRED_ARTIFACT_FILENAMES
from comqutor_alpha.evaluation.artifact_bundle_audit import (
    BUNDLE_STATUS_COMPLETE_ORIGINAL,
    BUNDLE_STATUS_COMPLETE_RECONSTRUCTED,
    BUNDLE_STATUS_INCOMPLETE_HISTORICAL,
    build_bundle_manifest,
    check_artifact_bundle,
    classify_bundle_status,
    reconstruct_missing_artifacts,
)

REAL_SOURCE_RUNS = {
    "QQQ": "a364e0ee-3bb4-4032-88b7-5cd82e379805",
    "AMD": "b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6",
}
REAL_SOURCE_OUTPUT_ROOT = "outputs/runs"
# The exact set this session's QA Item 6 found genuinely missing for these
# two real tickers before reconstruction -- reused here as the realistic
# "what's absent" starting point for the isolated-copy tests below.
ORIGINALLY_MISSING = ("evidence_facts.json", "alpha_activations.json", "conflicts.json")


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _minimal_bundle(tmp_path: Path, run_id: str, ticker: str, *, omit: tuple[str, ...] = ()) -> Path:
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    for name in REQUIRED_ARTIFACT_FILENAMES:
        if name in omit:
            continue
        _write(run_dir / name, {"run_id": run_id, "ticker": ticker, "schema_version": "test.v1"})
    return tmp_path


# ---------------------------------------------------------------------------
# Section A -- check_artifact_bundle
# ---------------------------------------------------------------------------


class TestSectionACheckArtifactBundle:
    def test_a1_complete_nine_of_nine_bundle_is_reported_complete(self, tmp_path):
        _minimal_bundle(tmp_path, "run1", "NVDA")
        result = check_artifact_bundle("run1", "NVDA", str(tmp_path))
        assert result["present_artifact_count"] == 9
        assert result["missing_artifacts"] == []

    def test_a2_missing_one_required_artifact_is_incomplete(self, tmp_path):
        _minimal_bundle(tmp_path, "run1", "NVDA", omit=("conflicts.json",))
        result = check_artifact_bundle("run1", "NVDA", str(tmp_path))
        assert result["present_artifact_count"] == 8
        assert result["missing_artifacts"] == ["conflicts.json"]
        assert result["per_artifact_status"]["conflicts.json"] == "MISSING"

    def test_a3_invalid_json_artifact_fails_closed_as_missing(self, tmp_path):
        run_dir = _minimal_bundle(tmp_path, "run1", "NVDA") / "run1"
        (run_dir / "conflicts.json").write_text("{not valid json", encoding="utf-8")
        result = check_artifact_bundle("run1", "NVDA", str(tmp_path))
        assert "conflicts.json" in result["missing_artifacts"]
        assert result["per_artifact_status"]["conflicts.json"] == "INVALID_JSON"

    def test_a4_zero_byte_artifact_fails_closed_as_missing(self, tmp_path):
        run_dir = _minimal_bundle(tmp_path, "run1", "NVDA") / "run1"
        (run_dir / "conflicts.json").write_text("", encoding="utf-8")
        result = check_artifact_bundle("run1", "NVDA", str(tmp_path))
        assert "conflicts.json" in result["missing_artifacts"]
        assert result["per_artifact_status"]["conflicts.json"] == "ZERO_BYTE"

    def test_a5_wrong_run_id_in_artifact_fails_closed(self, tmp_path):
        run_dir = _minimal_bundle(tmp_path, "run1", "NVDA") / "run1"
        _write(run_dir / "conflicts.json", {"run_id": "some_other_run", "ticker": "NVDA"})
        result = check_artifact_bundle("run1", "NVDA", str(tmp_path))
        assert "conflicts.json" in result["missing_artifacts"]
        assert result["per_artifact_status"]["conflicts.json"] == "RUN_ID_MISMATCH"

    def test_a6_wrong_ticker_in_artifact_fails_closed(self, tmp_path):
        run_dir = _minimal_bundle(tmp_path, "run1", "NVDA") / "run1"
        _write(run_dir / "conflicts.json", {"run_id": "run1", "ticker": "MSFT"})
        result = check_artifact_bundle("run1", "NVDA", str(tmp_path))
        assert "conflicts.json" in result["missing_artifacts"]
        assert result["per_artifact_status"]["conflicts.json"] == "TICKER_MISMATCH"


# ---------------------------------------------------------------------------
# Section B -- reconstruct_missing_artifacts (real source data, isolated copy)
# ---------------------------------------------------------------------------


def _isolated_copy_missing_the_reconstructable_artifacts(tmp_path, ticker, run_id):
    """Copies a real run's own untouched source artifacts (metadata/raw/
    structured/alpha_matches/structure_graph -- never the reconstructable
    ones) into an isolated temp run directory, exactly reproducing the
    real pre-reconstruction gap this session actually found for this
    ticker -- without ever writing into the real outputs/runs/ tree."""
    real_dir = Path(REAL_SOURCE_OUTPUT_ROOT) / run_id
    if not real_dir.is_dir():
        pytest.skip(f"LIVE_SAVED_RUN_NOT_AVAILABLE: {run_id} not found locally")
    dest_dir = tmp_path / run_id
    dest_dir.mkdir(parents=True)
    for name in REQUIRED_ARTIFACT_FILENAMES:
        if name in ORIGINALLY_MISSING:
            continue
        src = real_dir / name
        if src.is_file():
            shutil.copy2(src, dest_dir / name)
    return tmp_path


class TestSectionBReconstructMissingArtifacts:
    @pytest.mark.parametrize("ticker", sorted(REAL_SOURCE_RUNS))
    def test_b7_reconstruction_fills_exactly_the_missing_artifacts_from_real_source_data(self, tmp_path, ticker):
        run_id = REAL_SOURCE_RUNS[ticker]
        root = _isolated_copy_missing_the_reconstructable_artifacts(tmp_path, ticker, run_id)
        before = check_artifact_bundle(run_id, ticker, str(root))
        assert set(before["missing_artifacts"]) == set(ORIGINALLY_MISSING)

        result = reconstruct_missing_artifacts(run_id, ticker, str(root))
        assert set(result["reconstructed_artifacts"]) == set(ORIGINALLY_MISSING)
        assert result["provider_calls"] == 0
        assert result["tradingagents_calls"] == 0

        after = check_artifact_bundle(run_id, ticker, str(root))
        assert after["missing_artifacts"] == []

    def test_b8_reconstruction_never_overwrites_an_already_present_artifact(self, tmp_path):
        ticker, run_id = "QQQ", REAL_SOURCE_RUNS["QQQ"]
        root = _isolated_copy_missing_the_reconstructable_artifacts(tmp_path, ticker, run_id)
        run_dir = root / run_id
        # Plant an obviously-fake conflicts.json in the "missing" slot --
        # reconstruction must never touch it if the file already exists,
        # regardless of what check_artifact_bundle would say about its
        # own validity (a stricter guard than presence-checking alone).
        sentinel = {"run_id": run_id, "ticker": ticker, "sentinel": "must-not-be-overwritten"}
        _write(run_dir / "conflicts.json", sentinel)

        reconstruct_missing_artifacts(run_id, ticker, str(root))
        assert json.loads((run_dir / "conflicts.json").read_text(encoding="utf-8")) == sentinel

    def test_b9_reconstructed_conflicts_preserves_b2_output_exactly(self, tmp_path):
        # The reconstructed conflicts.json must be byte-identical to
        # calling the same official B2 entry point directly against the
        # same real, untouched source artifacts -- never a second/
        # different admissibility judgment.
        from comqutor_alpha.api.artifact_export import extract_conflicts_export
        from comqutor_alpha.conflict_engine.conflict_detector import detect_alpha_conflicts

        ticker, run_id = "QQQ", REAL_SOURCE_RUNS["QQQ"]
        root = _isolated_copy_missing_the_reconstructable_artifacts(tmp_path, ticker, run_id)
        reconstruct_missing_artifacts(run_id, ticker, str(root))
        reconstructed = json.loads((root / run_id / "conflicts.json").read_text(encoding="utf-8"))

        graph = json.loads((root / run_id / "structure_graph.json").read_text(encoding="utf-8"))
        matches = json.loads((root / run_id / "alpha_matches.json").read_text(encoding="utf-8"))
        directly_computed = extract_conflicts_export(
            detect_alpha_conflicts(
                run_id=run_id, ticker=ticker, activation_payload=graph["activation"], alpha_matches=matches["matches"]
            ),
            run_id=run_id,
            ticker=ticker,
        )
        assert reconstructed == directly_computed

    def test_b10_reconstructed_alpha_activations_preserves_b4_output_exactly(self, tmp_path):
        from comqutor_alpha.api.artifact_export import extract_alpha_activations_export

        ticker, run_id = "AMD", REAL_SOURCE_RUNS["AMD"]
        root = _isolated_copy_missing_the_reconstructable_artifacts(tmp_path, ticker, run_id)
        reconstruct_missing_artifacts(run_id, ticker, str(root))
        reconstructed = json.loads((root / run_id / "alpha_activations.json").read_text(encoding="utf-8"))

        graph = json.loads((root / run_id / "structure_graph.json").read_text(encoding="utf-8"))
        directly_extracted = extract_alpha_activations_export(graph, run_id=run_id, ticker=ticker)
        assert reconstructed == directly_extracted

    def test_b11_missing_structure_graph_source_cannot_be_fabricated(self, tmp_path):
        # No structure_graph.json/alpha_matches.json at all -- the "raw"
        # historical-source case task section 11 requires blocking rather
        # than fabricating.
        _minimal_bundle(
            tmp_path, "run1", "NVDA", omit=(*ORIGINALLY_MISSING, "structure_graph.json", "alpha_matches.json")
        )
        result = reconstruct_missing_artifacts("run1", "NVDA", str(tmp_path))
        assert result["reconstructed_artifacts"] == []
        assert "evidence_facts.json" in result["blocked_artifacts"]
        assert "conflicts.json" in result["blocked_artifacts"]
        assert result["provider_calls"] == 0


# ---------------------------------------------------------------------------
# Section C -- classify_bundle_status / build_bundle_manifest
# ---------------------------------------------------------------------------


class TestSectionCManifest:
    def test_c12_complete_original_never_claimed_when_anything_was_reconstructed(self):
        before = {"missing_artifacts": ["conflicts.json"]}
        reconstruction = {"reconstructed_artifacts": ["conflicts.json"], "post_missing_artifacts": [], "blocked_artifacts": {}}
        assert classify_bundle_status(before, reconstruction) == BUNDLE_STATUS_COMPLETE_RECONSTRUCTED

    def test_c13_already_complete_bundle_is_complete_original(self):
        before = {"missing_artifacts": []}
        assert classify_bundle_status(before, None) == BUNDLE_STATUS_COMPLETE_ORIGINAL

    def test_c14_nothing_reconstructable_and_still_missing_is_incomplete_historical(self):
        before = {"missing_artifacts": ["metadata.json"]}
        assert classify_bundle_status(before, None) == BUNDLE_STATUS_INCOMPLETE_HISTORICAL

    def test_c15_manifest_distinguishes_original_from_reconstructed_lists(self, tmp_path):
        ticker, run_id = "QQQ", REAL_SOURCE_RUNS["QQQ"]
        root = _isolated_copy_missing_the_reconstructable_artifacts(tmp_path, ticker, run_id)
        before = check_artifact_bundle(run_id, ticker, str(root))
        reconstruction = reconstruct_missing_artifacts(run_id, ticker, str(root))
        manifest = build_bundle_manifest(
            run_id, ticker, str(root), pre_existing=before["present_artifacts"], reconstruction=reconstruction
        )
        assert manifest["bundle_status"] == BUNDLE_STATUS_COMPLETE_RECONSTRUCTED
        assert set(manifest["reconstructed_artifacts"]) == set(ORIGINALLY_MISSING)
        assert set(manifest["original_artifacts"]) & set(manifest["reconstructed_artifacts"]) == set()
        assert manifest["present_count"] == 9
        assert manifest["provider_calls"] == 0


# ---------------------------------------------------------------------------
# Section D -- Determinism
# ---------------------------------------------------------------------------


class TestSectionDDeterminism:
    def test_d16_reconstruction_is_deterministic_across_two_independent_isolated_copies(self, tmp_path):
        ticker, run_id = "AMD", REAL_SOURCE_RUNS["AMD"]
        root_a = _isolated_copy_missing_the_reconstructable_artifacts(tmp_path / "a", ticker, run_id)
        root_b = _isolated_copy_missing_the_reconstructable_artifacts(tmp_path / "b", ticker, run_id)
        reconstruct_missing_artifacts(run_id, ticker, str(root_a))
        reconstruct_missing_artifacts(run_id, ticker, str(root_b))
        for name in ORIGINALLY_MISSING:
            content_a = (root_a / run_id / name).read_text(encoding="utf-8")
            content_b = (root_b / run_id / name).read_text(encoding="utf-8")
            assert content_a == content_b, f"{name} not deterministic"
