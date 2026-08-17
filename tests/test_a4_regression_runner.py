"""A4 Regression Runner + J2 Provisional Labels -- dedicated tests (task
A4_REGRESSION_RUNNER / J2_PROVISIONAL_LABELS).

Every comparison/evaluation function is tested as a pure function against
hand-built synthetic payloads (fast, no replay) -- the small number of
tests that genuinely need a real Architecture Replay call (Provider-call
counting, source-artifact hash-identity, determinism, the real CLI
command) share one module-scoped real replay via a fixture, rather than
each re-running the ~10s replay independently.

Section map:
    A - Labels (schema/vocabulary/overlap/undeclared-pair validation)
    B - Run selection (deterministic selection, file/DB status split)
    C - Alpha comparison (expected/detected/missing/unexpected)
    D - Conflict comparison (admitted/candidate/main_conflict)
    E - Evidence polarity (contract-integrity only, never semantic accuracy)
    F - Safety (Provider=0, TradingAgents=0, hash-identical, determinism, CLI)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from comqutor_alpha.conflict_engine.conflict_admissibility import CANDIDATE
from comqutor_alpha.regression.evaluator import (
    STANCE_SOURCE_DETERMINISTIC_BASELINE,
    STANCE_SOURCE_LLM_SEMANTIC,
    STANCE_SOURCE_MIXED,
    STANCE_SOURCE_UNAVAILABLE,
    alpha_comparison,
    conflict_comparison,
    detected_alpha_sets,
    dominance_guard_flags,
    evaluate_ticker,
    evidence_polarity_errors,
    stance_source,
)
from comqutor_alpha.regression.labels import (
    LabelValidationError,
    load_j2_labels,
    ticker_label,
)
from comqutor_alpha.regression.report import build_regression_report
from comqutor_alpha.regression.run_selection import (
    STATUS_RUN_ARTIFACT_NOT_AVAILABLE,
    STATUS_SELECTED,
    select_run_for_ticker,
)
from comqutor_alpha.replay.pipeline import run_structure_replay

REPO_ROOT = Path(__file__).resolve().parents[1]
SIX_TICKERS = ("NVDA", "QQQ", "MSFT", "SNDK", "TSM", "AMD")


# ---------------------------------------------------------------------------
# Section A -- Labels
# ---------------------------------------------------------------------------


class TestSectionALabels:
    def test_a1_all_six_tickers_present(self):
        labels = load_j2_labels()
        assert set(SIX_TICKERS) <= set(labels["tickers"].keys())

    def test_a2_every_alpha_id_belongs_to_canonical_taxonomy(self):
        from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy

        known = frozenset(load_alpha_taxonomy().keys())
        labels = load_j2_labels()
        for ticker, block in labels["tickers"].items():
            for group in ("expected_positive_alphas", "expected_negative_alphas", "conditional_alphas"):
                for alpha_id in block[group]:
                    assert alpha_id in known, f"{ticker}.{group} has unknown alpha {alpha_id}"
            for alpha_id in (block.get("should_not_be_dominant_without_strong_evidence") or {}):
                assert alpha_id in known

    def test_a3_positive_negative_conditional_never_overlap(self):
        labels = load_j2_labels()
        for ticker, block in labels["tickers"].items():
            positive = set(block["expected_positive_alphas"])
            negative = set(block["expected_negative_alphas"])
            conditional = set(block["conditional_alphas"])
            assert not (positive & negative), ticker
            assert not (positive & conditional), ticker
            assert not (negative & conditional), ticker

    def test_a4_provisional_label_is_never_john_approved(self):
        labels = load_j2_labels()
        assert labels["status"] == "provisional_ai_predicted"
        assert labels["approved_by"] is None
        assert labels["formal_product_owner_approval"] == "pending"
        assert labels["evaluation_mode"] == "shadow"

    def test_a5_env_var_cannot_upgrade_provisional_to_authoritative(self, monkeypatch):
        for var in ("J2_FORCE_AUTHORITATIVE", "COMQUTOR_LABEL_AUTHORITY", "REGRESSION_AUTHORITATIVE"):
            monkeypatch.setenv(var, "1")
        labels = load_j2_labels()
        assert labels["evaluation_mode"] == "shadow"
        assert labels["formal_product_owner_approval"] == "pending"

    def test_a6_conflict_pair_format_is_validated(self, tmp_path):
        raw = _minimal_label_yaml(allowed_main_conflicts=["not-a-valid-pair"])
        path = tmp_path / "bad_labels.yaml"
        path.write_text(raw, encoding="utf-8")
        with pytest.raises(LabelValidationError):
            load_j2_labels(path)

    def test_a7_undeclared_conflict_pair_is_reported_never_silently_dropped(self):
        labels = load_j2_labels()
        # MSFT's A102__A304 is not in the canonical 6-pair taxonomy.
        assert "MSFT" in labels["undeclared_conflict_pairs"]
        assert "A102__A304" in labels["undeclared_conflict_pairs"]["MSFT"]
        # Still present, verbatim, in the loaded ticker block -- never
        # silently deleted because it is undeclared.
        assert "A102__A304" in ticker_label(labels, "MSFT")["allowed_main_conflicts"]


def _minimal_label_yaml(**ticker_overrides) -> str:
    block = {
        "expected_positive_alphas": ["A101"],
        "expected_negative_alphas": ["A304"],
        "conditional_alphas": ["A601"],
        "allowed_main_conflicts": ["A101__A304"],
        "should_not_be_dominant_without_strong_evidence": {},
        "source_basis": [],
    }
    block.update(ticker_overrides)
    payload = {
        "schema_version": "regression_labels.v1",
        "label_version": "test.v0",
        "taxonomy_version": "alpha_taxonomy_v1",
        "label_scope": "ticker_general",
        "status": "provisional_ai_predicted",
        "evaluation_mode": "shadow",
        "evaluation_authority": "provisional",
        "prepared_for": "test",
        "approved_by": None,
        "approved_at": None,
        "formal_product_owner_approval": "pending",
        "tickers": {"NVDA": block},
    }
    return yaml.safe_dump(payload)


# ---------------------------------------------------------------------------
# Section B -- Run selection
# ---------------------------------------------------------------------------


def _write_run(output_root: Path, run_id: str, ticker: str, analysis_date: str, created_at: str, *, complete: bool = True):
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True)
    metadata = {"run_id": run_id, "ticker": ticker, "analysis_date": analysis_date, "created_at": created_at}
    (run_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (run_dir / "raw_agent_outputs.json").write_text(json.dumps({"agent_outputs": []}), encoding="utf-8")
    if complete:
        for name in (
            "structured_agent_outputs.json",
            "evidence_facts.json",
            "alpha_matches.json",
            "structure_graph.json",
            "alpha_activations.json",
            "conflicts.json",
            "run_audit.json",
        ):
            (run_dir / name).write_text("{}", encoding="utf-8")
    return run_dir


class TestSectionBRunSelection:
    def test_b8_deterministic_latest_complete_run_selected(self, tmp_path):
        _write_run(tmp_path, "run-old", "NVDA", "2026-01-01", "2026-01-01T00:00:00Z")
        _write_run(tmp_path, "run-new", "NVDA", "2026-02-01", "2026-02-01T00:00:00Z")
        result = select_run_for_ticker("NVDA", tmp_path)
        assert result["run_selection_status"] == STATUS_SELECTED
        assert result["run_id"] == "run-new"

    def test_b9_incomplete_artifact_run_not_preferred_over_a_complete_one(self, tmp_path):
        _write_run(tmp_path, "run-incomplete-newer", "NVDA", "2026-03-01", "2026-03-01T00:00:00Z", complete=False)
        _write_run(tmp_path, "run-complete-older", "NVDA", "2026-01-01", "2026-01-01T00:00:00Z", complete=True)
        result = select_run_for_ticker("NVDA", tmp_path)
        assert result["run_id"] == "run-complete-older"
        assert result["file_artifact_completeness"] == "pass"

    def test_b9b_incomplete_run_still_selected_when_it_is_the_only_replay_eligible_candidate(self, tmp_path):
        _write_run(tmp_path, "run-incomplete", "NVDA", "2026-01-01", "2026-01-01T00:00:00Z", complete=False)
        result = select_run_for_ticker("NVDA", tmp_path)
        assert result["run_selection_status"] == STATUS_SELECTED
        assert result["file_artifact_completeness"] == "fail"

    def test_b10_ticker_mismatch_excludes_the_run(self, tmp_path):
        _write_run(tmp_path, "run-msft", "MSFT", "2026-01-01", "2026-01-01T00:00:00Z")
        result = select_run_for_ticker("NVDA", tmp_path)
        assert result["run_selection_status"] == STATUS_RUN_ARTIFACT_NOT_AVAILABLE

    def test_b11_no_saved_run_reports_explicit_status(self, tmp_path):
        result = select_run_for_ticker("NVDA", tmp_path)
        assert result["run_selection_status"] == STATUS_RUN_ARTIFACT_NOT_AVAILABLE
        assert result["run_id"] is None

    def test_b12_file_and_database_status_reported_independently(self, tmp_path):
        _write_run(tmp_path, "run-a", "NVDA", "2026-01-01", "2026-01-01T00:00:00Z")

        class _FakeRepo:
            def get_research_run_record(self, run_id):
                return None  # DB has no row -- legitimately absent, not an error

        result = select_run_for_ticker("NVDA", tmp_path, repository=_FakeRepo())
        assert result["file_artifact_completeness"] == "pass"
        assert result["database_record_status"] == "not_found"


# ---------------------------------------------------------------------------
# Section C -- Alpha comparison
# ---------------------------------------------------------------------------


def _alpha_entry(alpha_id: str) -> dict:
    return {"alpha_id": alpha_id}


class TestSectionCAlphaComparison:
    def test_c13_expected_union_is_positive_plus_negative(self):
        label = {"expected_positive_alphas": ["A101"], "expected_negative_alphas": ["A304"], "conditional_alphas": []}
        detected = detected_alpha_sets({"active_alphas": [], "dominant_alphas": [], "regime_level_alphas": [], "candidate_alphas": [], "blocked_alphas": []})
        cmp = alpha_comparison(label, detected)
        assert cmp["expected_alphas"] == ["A101", "A304"]

    def test_c14_conditional_present_is_never_unexpected(self):
        label = {"expected_positive_alphas": [], "expected_negative_alphas": [], "conditional_alphas": ["A601"]}
        graph = {"active_alphas": [_alpha_entry("A601")], "dominant_alphas": [], "regime_level_alphas": [], "candidate_alphas": [], "blocked_alphas": []}
        cmp = alpha_comparison(label, detected_alpha_sets(graph))
        assert cmp["unexpected_alphas"] == []

    def test_c15_conditional_absent_is_never_missing(self):
        label = {"expected_positive_alphas": [], "expected_negative_alphas": [], "conditional_alphas": ["A601"]}
        graph = {"active_alphas": [], "dominant_alphas": [], "regime_level_alphas": [], "candidate_alphas": [], "blocked_alphas": []}
        cmp = alpha_comparison(label, detected_alpha_sets(graph))
        assert cmp["missing_expected"] == []

    def test_c16_blocked_and_candidate_never_count_as_detected(self):
        graph = {
            "active_alphas": [],
            "dominant_alphas": [],
            "regime_level_alphas": [],
            "candidate_alphas": [_alpha_entry("A101")],
            "blocked_alphas": [_alpha_entry("A304")],
        }
        detected = detected_alpha_sets(graph)
        assert detected["detected_alphas"] == []
        assert detected["candidate_alphas"] == ["A101"]
        assert detected["blocked_alphas"] == ["A304"]

    def test_c17_active_dominant_regime_level_all_count_as_detected(self):
        graph = {
            "active_alphas": [_alpha_entry("A001")],
            "dominant_alphas": [_alpha_entry("A101"), _alpha_entry("A201")],
            "regime_level_alphas": [_alpha_entry("A201")],
            "candidate_alphas": [],
            "blocked_alphas": [],
        }
        detected = detected_alpha_sets(graph)
        assert detected["detected_alphas"] == ["A001", "A101", "A201"]
        # dominant_alphas (legacy, blended) minus regime_level_alphas ->
        # pure dominant-only, never double counted with regime_level.
        assert detected["dominant_alphas"] == ["A101"]
        assert detected["regime_level_alphas"] == ["A201"]

    def test_c18_dominance_guard_only_produces_a_review_flag_never_a_reclassification(self):
        label = {"should_not_be_dominant_without_strong_evidence": {"A102": "some evidence condition"}}
        graph = {
            "activation_versions": {
                "v2": {
                    "alphas": [
                        {
                            "alpha_id": "A102",
                            "status": "dominant",
                            "unique_evidence_count": 2,
                            "ticker_specific_evidence_count": 0,
                            "local_edge_count": 0,
                        }
                    ]
                }
            }
        }
        flags = dominance_guard_flags(label, graph, None)
        assert len(flags) == 1
        assert flags[0]["alpha_id"] == "A102"
        assert flags[0]["review_status"] == "dominance_guard_review_required"
        # Never claims a semantic verdict -- no pass/fail field, no auto
        # regex judgment of the free-text condition.
        assert "condition_met" not in flags[0]

    def test_c19_provisional_mismatch_is_reported_never_disguised_as_a_formal_regression_failure(self):
        label = {"expected_positive_alphas": ["A999_NEVER_DETECTED"], "expected_negative_alphas": [], "conditional_alphas": []}
        graph = {"active_alphas": [], "dominant_alphas": [], "regime_level_alphas": [], "candidate_alphas": [], "blocked_alphas": []}
        cmp = alpha_comparison(label, detected_alpha_sets(graph))
        assert cmp["missing_expected"] == ["A999_NEVER_DETECTED"]
        # A pure data field -- no exception raised, no crash; the CLI
        # layer is what decides this never flips the exit code.


# ---------------------------------------------------------------------------
# Section D -- Conflict comparison
# ---------------------------------------------------------------------------


class TestSectionDConflictComparison:
    def test_d20_main_conflict_must_come_from_admitted(self):
        conflict_payload = {
            "conflicts": [{"conflict_id": "A101__A304"}],
            "main_conflict": {"conflict_id": "A101__A304"},
            "arbitration": {"candidate_evaluations": []},
        }
        cmp = conflict_comparison({"allowed_main_conflicts": ["A101__A304"]}, conflict_payload)
        assert cmp["main_conflict_in_admitted"] is True
        assert cmp["main_conflict_match"] is True

    def test_d21_candidate_can_never_become_main(self):
        conflict_payload = {
            "conflicts": [],
            "main_conflict": None,
            "arbitration": {
                "candidate_evaluations": [
                    {"alpha_a": "A101", "alpha_b": "A304", "admissibility": {"status": CANDIDATE, "reason_codes": ["X"]}}
                ]
            },
        }
        cmp = conflict_comparison({"allowed_main_conflicts": ["A101__A304"]}, conflict_payload)
        assert cmp["main_conflict"] is None
        assert "A101__A304" in cmp["candidate_conflicts"]
        assert cmp["main_conflict_match"] is False

    def test_d22_expected_pair_at_candidate_preserves_b2_failure_reasons(self):
        conflict_payload = {
            "conflicts": [],
            "main_conflict": None,
            "arbitration": {
                "candidate_evaluations": [
                    {
                        "alpha_a": "A101",
                        "alpha_b": "A304",
                        "admissibility": {"status": CANDIDATE, "reason_codes": ["BULL_SCORE_BELOW_THRESHOLD"]},
                    }
                ]
            },
        }
        cmp = conflict_comparison({"allowed_main_conflicts": ["A101__A304"]}, conflict_payload)
        assert cmp["expected_pair_status"]["A101__A304"] == CANDIDATE
        assert cmp["candidate_failure_reasons"]["A101__A304"] == ["BULL_SCORE_BELOW_THRESHOLD"]

    def test_d23_comparison_never_touches_conflictscore_or_admissibility_inputs(self):
        # Purely a read: passing extra/unrelated keys through untouched
        # proves this function only extracts, never recomputes.
        conflict_payload = {
            "conflicts": [{"conflict_id": "A101__A304", "conflict_score": 42.5}],
            "main_conflict": {"conflict_id": "A101__A304", "conflict_score": 42.5},
            "arbitration": {"candidate_evaluations": []},
        }
        before = json.dumps(conflict_payload, sort_keys=True)
        conflict_comparison({"allowed_main_conflicts": []}, conflict_payload)
        assert json.dumps(conflict_payload, sort_keys=True) == before


# ---------------------------------------------------------------------------
# Section E -- Evidence polarity (contract-integrity only)
# ---------------------------------------------------------------------------


class TestSectionEEvidencePolarity:
    def test_e24_invalid_stance_vocabulary_is_counted(self):
        alpha_matches = {
            "matches": [
                {"claim_id": "c1", "candidate_scores": [{"alpha_id": "A101", "evidence_stance": "not_a_real_stance"}]}
            ]
        }
        result = evidence_polarity_errors(alpha_matches, {"conflicts": []})
        assert result["evidence_polarity_errors"] == 1
        assert result["evidence_polarity_error_details"][0]["code"] == "INVALID_STANCE_VOCABULARY"

    def test_e25_non_supports_alpha_fact_in_supporting_pool_is_counted(self):
        conflict_payload = {
            "conflicts": [
                {
                    "conflict_id": "A101__A304",
                    "evidence_ui": {
                        "bull_evidence": [{"claim_id": "c1", "evidence_stance": "opposes_alpha"}],
                        "bear_evidence": [],
                    },
                }
            ]
        }
        result = evidence_polarity_errors({"matches": []}, conflict_payload)
        assert result["evidence_polarity_errors"] == 1
        assert result["evidence_polarity_error_details"][0]["code"] == "SUPPORTING_POOL_NON_SUPPORTS_ALPHA_FACT"

    def test_e26_semantic_polarity_accuracy_stays_null(self):
        result = evidence_polarity_errors({"matches": []}, {"conflicts": []})
        assert result["semantic_polarity_accuracy"] is None
        assert result["semantic_polarity_review_status"] == "PENDING_J3_HUMAN_REVIEW"

    def test_e27_zero_errors_means_contract_integrity_clean_only(self):
        alpha_matches = {
            "matches": [{"claim_id": "c1", "candidate_scores": [{"alpha_id": "A101", "evidence_stance": "supports_alpha"}]}]
        }
        result = evidence_polarity_errors(alpha_matches, {"conflicts": []})
        assert result["evidence_polarity_errors"] == 0
        assert result["evidence_polarity_error_scope"] == "contract_integrity_only"
        # Never claims semantic accuracy from a zero count.
        assert result["semantic_polarity_accuracy"] is None


# ---------------------------------------------------------------------------
# Section F -- Safety (shares one real, module-scoped replay)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_saved_run_id() -> str | None:
    candidates = sorted((REPO_ROOT / "outputs" / "runs").glob("*/metadata.json")) if (REPO_ROOT / "outputs" / "runs").exists() else []
    for path in candidates:
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if metadata.get("ticker") == "QQQ" and (path.parent / "raw_agent_outputs.json").exists():
            return path.parent.name
    return None


@pytest.fixture(scope="module")
def shared_replay(real_saved_run_id, tmp_path_factory):
    if real_saved_run_id is None:
        pytest.skip("LIVE_SAVED_RUN_NOT_AVAILABLE: no real QQQ saved run found for safety tests")
    replay_root = tmp_path_factory.mktemp("a4_safety_replay")
    source_raw_path = REPO_ROOT / "outputs" / "runs" / real_saved_run_id / "raw_agent_outputs.json"
    before_bytes = source_raw_path.read_bytes()
    result = run_structure_replay(
        real_saved_run_id,
        replay_output_root=str(replay_root),
        comparison=False,
    )
    after_bytes = source_raw_path.read_bytes()
    return {"result": result, "before_bytes": before_bytes, "after_bytes": after_bytes, "replay_root": replay_root}


class TestSectionFSafety:
    def test_f28_provider_call_count_is_zero(self, shared_replay):
        assert shared_replay["result"].llm_provider_calls == 0
        assert shared_replay["result"].provider_zero is True

    def test_f29_tradingagents_call_count_is_zero(self, shared_replay):
        assert shared_replay["result"].tradingagents_calls == 0

    def test_f30_saved_artifact_is_byte_identical_before_and_after_reprocess(self, shared_replay):
        assert shared_replay["before_bytes"] == shared_replay["after_bytes"]
        assert shared_replay["result"].source_raw_sha256_before == shared_replay["result"].source_raw_sha256_after

    def test_f31_runner_never_overwrites_the_original_run_directory(self, shared_replay, real_saved_run_id):
        # The replay's own output_dir is a brand-new directory, never the
        # source run's own path under outputs/runs.
        assert shared_replay["result"].output_dir is not None
        assert real_saved_run_id not in Path(shared_replay["result"].output_dir).parts[-2:-1]
        assert str(shared_replay["replay_root"]) in shared_replay["result"].output_dir

    def test_f32_repeated_run_is_deterministic(self, real_saved_run_id, tmp_path_factory):
        if real_saved_run_id is None:
            pytest.skip("LIVE_SAVED_RUN_NOT_AVAILABLE")
        root_a = tmp_path_factory.mktemp("a4_det_a")
        root_b = tmp_path_factory.mktemp("a4_det_b")
        result_a = run_structure_replay(real_saved_run_id, replay_output_root=str(root_a), comparison=False)
        result_b = run_structure_replay(real_saved_run_id, replay_output_root=str(root_b), comparison=False)
        graph_a = json.loads((Path(result_a.output_dir) / "structure_graph.json").read_text())
        graph_b = json.loads((Path(result_b.output_dir) / "structure_graph.json").read_text())

        # evidence_fact_group_id is intentionally scoped to (run_id,
        # ticker, claim_ids) -- see evidence_fact_index.evidence_fact_
        # group_id -- so it (and the sort order derived from it) legitimately
        # differs between two separate replay_run_ids by design, same as
        # claim_id/run_id themselves. The classification/scoring outputs
        # A4 actually compares against J2 labels must still be identical.
        def _stable_alpha_view(alphas):
            return {
                a["alpha_id"]: {
                    key: a.get(key)
                    for key in (
                        "activation_score",
                        "status",
                        "qualified_level",
                        "is_blocked",
                        "evidence_count",
                        "unique_evidence_count",
                        "ticker_specific_evidence_count",
                        "distinct_supporting_agents",
                        "local_edge_count",
                    )
                }
                for a in alphas
            }

        alphas_a = _stable_alpha_view(graph_a["activation"]["alphas"])
        alphas_b = _stable_alpha_view(graph_b["activation"]["alphas"])
        assert alphas_a == alphas_b
        assert {a["alpha_id"] for a in graph_a["dominant_alphas"]} == {a["alpha_id"] for a in graph_b["dominant_alphas"]}

    def test_f33_cli_runs_the_exact_fixed_six_ticker_command(self, tmp_path):
        outputs_runs = REPO_ROOT / "outputs" / "runs"
        if not outputs_runs.exists():
            pytest.skip("LIVE_SAVED_RUN_NOT_AVAILABLE: no outputs/runs directory")
        report_path = tmp_path / "regression_report.json"
        replay_root = tmp_path / "replays"
        proc = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "run_regression.py"),
                "--tickers",
                *SIX_TICKERS,
                "--report-path",
                str(report_path),
                "--replay-output-root",
                str(replay_root),
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert report_path.exists(), proc.stderr
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["provider_calls"] == 0
        assert report["tradingagents_calls"] == 0
        assert [r["ticker"] for r in report["results"]] == list(SIX_TICKERS)


# ---------------------------------------------------------------------------
# Report assembly (stance_source classification + top-level assembly)
# ---------------------------------------------------------------------------


class TestReportAssemblyAndStanceSource:
    def test_stance_source_unavailable_when_no_stance_data(self):
        assert stance_source({"matches": []}) == STANCE_SOURCE_UNAVAILABLE

    def test_stance_source_deterministic_when_no_llm_ever_attempted(self):
        alpha_matches = {
            "matches": [{"candidate_scores": [{"alpha_id": "A101", "evidence_stance": "supports_alpha", "stance_method": None}]}]
        }
        assert stance_source(alpha_matches) == STANCE_SOURCE_DETERMINISTIC_BASELINE

    def test_stance_source_llm_semantic_when_every_candidate_used_llm(self):
        alpha_matches = {
            "matches": [{"candidate_scores": [{"alpha_id": "A101", "evidence_stance": "supports_alpha", "stance_method": "llm"}]}]
        }
        assert stance_source(alpha_matches) == STANCE_SOURCE_LLM_SEMANTIC

    def test_stance_source_mixed_when_llm_and_deterministic_both_present(self):
        alpha_matches = {
            "matches": [
                {"candidate_scores": [{"alpha_id": "A101", "evidence_stance": "supports_alpha", "stance_method": "llm"}]},
                {"candidate_scores": [{"alpha_id": "A304", "evidence_stance": "opposes_alpha", "stance_method": None}]},
            ]
        }
        assert stance_source(alpha_matches) == STANCE_SOURCE_MIXED

    def test_report_marks_coverage_partial_when_a_ticker_has_no_saved_run(self):
        results = [
            {"ticker": "NVDA", "run_selection_status": "selected", "offline_reprocess_status": "completed", "provider_calls": 0, "tradingagents_calls": 0},
            {"ticker": "ZZZZ", "run_selection_status": STATUS_RUN_ARTIFACT_NOT_AVAILABLE, "offline_reprocess_status": "not_attempted", "provider_calls": 0, "tradingagents_calls": 0},
        ]
        report = build_regression_report(
            tickers_requested=["NVDA", "ZZZZ"],
            label_version="j2.provisional.v0.1",
            label_status="provisional_ai_predicted",
            evaluation_mode="shadow",
            results=results,
        )
        assert report["overall_execution_status"] == "coverage_partial"
        assert report["six_ticker_live_coverage"] == "SIX_TICKER_LIVE_COVERAGE_PARTIAL"

    def test_report_status_complete_when_every_ticker_replays_cleanly(self):
        results = [
            {"ticker": "NVDA", "run_selection_status": "selected", "offline_reprocess_status": "completed", "provider_calls": 0, "tradingagents_calls": 0},
        ]
        report = build_regression_report(
            tickers_requested=["NVDA"],
            label_version="j2.provisional.v0.1",
            label_status="provisional_ai_predicted",
            evaluation_mode="shadow",
            results=results,
        )
        assert report["overall_execution_status"] == "complete"

    def test_evaluate_ticker_reports_run_artifact_not_available_without_crashing(self):
        selection = {"run_selection_status": STATUS_RUN_ARTIFACT_NOT_AVAILABLE, "run_id": None, "analysis_date": None, "file_artifact_completeness": None, "database_record_status": "not_applicable"}
        result = evaluate_ticker("ZZZZ", selection, None, replay_output_root="/tmp/should-not-be-used")
        assert result["offline_reprocess_status"] == "not_attempted"
        assert result["detected_alphas"] == []
        assert result["stance_source"] == STANCE_SOURCE_UNAVAILABLE
