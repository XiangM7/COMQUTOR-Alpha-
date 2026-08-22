"""J3 Provisional Semantic Benchmark + J2 v0.2 Evaluation Contract --
dedicated tests (task J3_PROVISIONAL_SEMANTIC_BENCHMARK_INTEGRATION /
J2_V0.2_EVALUATION_CONTRACT_ALIGNMENT).

Section map (matches the task's own 43-item checklist):
    A - J3 benchmark construction (1-10)
    B - Semantic comparison (11-18)
    C - J2 v0.2 schema (19-28)
    D - A4 integration (29-35)
    E - Invariants (36-43)

Sections A/B run against the real embedded 50-row data and the real,
already-exported blind packet / B1 comparison CSV -- these are this
task's own formal, frozen inputs, never synthetic stand-ins. Section C
uses small hand-built label fixtures for the validator-rejection cases
(mirrors tests/test_a4_regression_runner.py's own style) plus the real
v0.2 file for the ticker-specific decisions. Section D/E's replay-backed
cases share one real, module-scoped NVDA replay (the only artifact-
complete saved run) rather than each re-running it independently.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.conflict_engine.conflict_admissibility import ADMITTED, CANDIDATE
from comqutor_alpha.evaluation.j3_semantic_benchmark import (
    BENCHMARK_SCHEMA_VERSION,
    DEFAULT_BLIND_PACKET_PATH,
    EMBEDDED_REVIEWED_ROWS,
    J3BenchmarkValidationError,
    build_j3_semantic_benchmark,
    load_j3_semantic_benchmark,
)
from comqutor_alpha.regression.evaluation_contract import apply_v2_contract
from comqutor_alpha.regression.evaluator import evaluate_ticker
from comqutor_alpha.regression.labels import (
    DEFAULT_LABEL_PATH,
    _canonical_conflict_pairs,
    load_j2_labels,
    ticker_label,
)
from comqutor_alpha.regression.labels_v2 import (
    LabelV2ValidationError,
    load_j2_labels_v2,
    ticker_label_v2,
)
from comqutor_alpha.regression.report import build_regression_report
from comqutor_alpha.regression.run_selection import select_run_for_ticker
from comqutor_alpha.regression.semantic_benchmark import (
    EXPECTED_DISAGREEMENT_ROW_IDS,
    EXPECTED_FALSE_SUPPORT_NEGATIVE_IDS,
    J3SemanticComparisonMismatchError,
    compare_j3_benchmark,
    load_stance_comparison_rows,
    verify_reversal_rows_support_b1_llm,
)
from comqutor_alpha.structure_engine.evidence_stance import VALID_EVIDENCE_STANCES

REPO_ROOT = Path(__file__).resolve().parents[1]
SIX_TICKERS = ("NVDA", "QQQ", "MSFT", "SNDK", "TSM", "AMD")
FROZEN_SESSION_HEAD = "b5837e80a4550fc35165d0013a8ef0f27ccb4c8f"


# ---------------------------------------------------------------------------
# Section A -- J3 benchmark construction (checks 1-10)
# ---------------------------------------------------------------------------


class TestSectionAJ3BenchmarkConstruction:
    def test_a1_exactly_fifty_rows(self):
        benchmark = build_j3_semantic_benchmark()
        assert benchmark["row_count"] == 50
        assert len(benchmark["rows"]) == 50

    def test_a2_sample_ids_unique(self):
        benchmark = build_j3_semantic_benchmark()
        ids = [row["sample_id"] for row in benchmark["rows"]]
        assert len(ids) == len(set(ids)) == 50

    def test_a3_row_order_matches_blind_packet_never_resorted(self):
        blind_packet = json.loads(DEFAULT_BLIND_PACKET_PATH.read_text(encoding="utf-8"))
        blind_order = [row["sample_id"] for row in blind_packet["rows"]]
        benchmark = build_j3_semantic_benchmark()
        benchmark_order = [row["sample_id"] for row in benchmark["rows"]]
        assert benchmark_order == blind_order

    def test_a4_identity_fields_copied_verbatim_never_regenerated(self):
        blind_packet = json.loads(DEFAULT_BLIND_PACKET_PATH.read_text(encoding="utf-8"))
        blind_by_id = {row["sample_id"]: row for row in blind_packet["rows"]}
        benchmark = build_j3_semantic_benchmark()
        for row in benchmark["rows"]:
            blind_row = blind_by_id[row["sample_id"]]
            assert row["run_id"] == blind_row["run_id"]
            assert row["claim_id"] == blind_row["claim_id"]
            assert row["target_alpha_id"] == blind_row["target_alpha_id"]

    def test_a5_claim_text_byte_for_byte_from_blind_packet(self):
        blind_packet = json.loads(DEFAULT_BLIND_PACKET_PATH.read_text(encoding="utf-8"))
        blind_by_id = {row["sample_id"]: row for row in blind_packet["rows"]}
        benchmark = build_j3_semantic_benchmark()
        for row in benchmark["rows"]:
            assert row["claim_text"] == blind_by_id[row["sample_id"]]["claim"]

    def test_a6_every_reviewed_stance_is_valid_vocabulary(self):
        benchmark = build_j3_semantic_benchmark()
        for row in benchmark["rows"]:
            assert row["reviewed_stance"] in VALID_EVIDENCE_STANCES

    def test_a6b_invalid_stance_vocabulary_fails_closed(self):
        bad_rows = tuple(
            {**row, "reviewed_stance": "not_a_real_stance"} if row["sample_id"] == "evrs-001" else row
            for row in EMBEDDED_REVIEWED_ROWS
        )
        with pytest.raises(J3BenchmarkValidationError) as exc_info:
            build_j3_semantic_benchmark(reviewed_rows=bad_rows)
        assert exc_info.value.reason_code == "J3_BENCHMARK_INVALID_STANCE_VOCABULARY"

    def test_a7_counter_alpha_rules_hold_on_real_data(self):
        blind_packet = json.loads(DEFAULT_BLIND_PACKET_PATH.read_text(encoding="utf-8"))
        blind_by_id = {row["sample_id"]: row for row in blind_packet["rows"]}
        benchmark = build_j3_semantic_benchmark()
        for row in benchmark["rows"]:
            if row["reviewed_stance"] == "supports_counter_alpha":
                legal = blind_by_id[row["sample_id"]].get("legal_counter_alphas") or ()
                assert row["reviewed_counter_alpha_id"] in legal
            else:
                assert row["reviewed_counter_alpha_id"] is None

    def test_a7b_illegal_counter_alpha_fails_closed(self):
        # evrs-008's legal_counter_alphas is ["A304", "A501"] -- A101 is a
        # real, known Alpha (so this exercises the *illegal-for-this-row*
        # branch specifically, distinct from an unknown-Alpha-ID branch).
        bad_rows = tuple(
            {**row, "reviewed_counter_alpha_id": "A101"} if row["sample_id"] == "evrs-008" else row
            for row in EMBEDDED_REVIEWED_ROWS
        )
        with pytest.raises(J3BenchmarkValidationError) as exc_info:
            build_j3_semantic_benchmark(reviewed_rows=bad_rows)
        assert exc_info.value.reason_code == "J3_BENCHMARK_ILLEGAL_COUNTER_ALPHA"

    def test_a7e_unknown_counter_alpha_id_fails_closed(self):
        bad_rows = tuple(
            {**row, "reviewed_counter_alpha_id": "A999_NOT_A_REAL_ALPHA"} if row["sample_id"] == "evrs-008" else row
            for row in EMBEDDED_REVIEWED_ROWS
        )
        with pytest.raises(J3BenchmarkValidationError) as exc_info:
            build_j3_semantic_benchmark(reviewed_rows=bad_rows)
        assert exc_info.value.reason_code == "J3_BENCHMARK_UNKNOWN_COUNTER_ALPHA"

    def test_a7c_missing_counter_alpha_when_stance_requires_it_fails_closed(self):
        bad_rows = tuple(
            {**row, "reviewed_counter_alpha_id": None} if row["sample_id"] == "evrs-008" else row
            for row in EMBEDDED_REVIEWED_ROWS
        )
        with pytest.raises(J3BenchmarkValidationError) as exc_info:
            build_j3_semantic_benchmark(reviewed_rows=bad_rows)
        assert exc_info.value.reason_code == "J3_BENCHMARK_MISSING_COUNTER_ALPHA_ID"

    def test_a7d_unexpected_counter_alpha_when_stance_does_not_allow_it_fails_closed(self):
        bad_rows = tuple(
            {**row, "reviewed_counter_alpha_id": "A304"} if row["sample_id"] == "evrs-001" else row
            for row in EMBEDDED_REVIEWED_ROWS
        )
        with pytest.raises(J3BenchmarkValidationError) as exc_info:
            build_j3_semantic_benchmark(reviewed_rows=bad_rows)
        assert exc_info.value.reason_code == "J3_BENCHMARK_UNEXPECTED_COUNTER_ALPHA_ID"

    def test_a8_stance_distribution_matches_task_exactly(self):
        benchmark = build_j3_semantic_benchmark()
        distribution: dict[str, int] = {}
        for row in benchmark["rows"]:
            distribution[row["reviewed_stance"]] = distribution.get(row["reviewed_stance"], 0) + 1
        assert distribution == {
            "supports_alpha": 26,
            "opposes_alpha": 16,
            "mentions_alpha": 5,
            "supports_counter_alpha": 2,
            "neutral_background": 1,
        }

    def test_a9_confidence_distribution_matches_task_exactly(self):
        benchmark = build_j3_semantic_benchmark()
        distribution: dict[str, int] = {}
        for row in benchmark["rows"]:
            distribution[row["review_confidence"]] = distribution.get(row["review_confidence"], 0) + 1
        assert distribution == {"high": 38, "medium": 12}

    def test_a10_wrong_row_count_fails_closed(self):
        with pytest.raises(J3BenchmarkValidationError) as exc_info:
            build_j3_semantic_benchmark(reviewed_rows=EMBEDDED_REVIEWED_ROWS[:49])
        assert exc_info.value.reason_code == "J3_BENCHMARK_ROW_COUNT_MISMATCH"

    def test_a10b_duplicate_sample_id_fails_closed(self):
        bad_rows = EMBEDDED_REVIEWED_ROWS[:49] + (EMBEDDED_REVIEWED_ROWS[0],)
        with pytest.raises(J3BenchmarkValidationError) as exc_info:
            build_j3_semantic_benchmark(reviewed_rows=bad_rows)
        assert exc_info.value.reason_code == "J3_BENCHMARK_DUPLICATE_SAMPLE_ID"

    def test_a10c_identity_mismatch_vs_blind_packet_fails_closed(self):
        bad_rows = EMBEDDED_REVIEWED_ROWS[:49] + ({**EMBEDDED_REVIEWED_ROWS[49], "sample_id": "evrs-999"},)
        with pytest.raises(J3BenchmarkValidationError) as exc_info:
            build_j3_semantic_benchmark(reviewed_rows=bad_rows)
        assert exc_info.value.reason_code == "J3_BENCHMARK_IDENTITY_MISMATCH"

    def test_a10d_load_rejects_a_tampered_row_count_file(self, tmp_path):
        path = tmp_path / "tampered_benchmark.json"
        path.write_text(json.dumps({"schema_version": BENCHMARK_SCHEMA_VERSION, "rows": []}), encoding="utf-8")
        with pytest.raises(J3BenchmarkValidationError) as exc_info:
            load_j3_semantic_benchmark(path)
        assert exc_info.value.reason_code == "J3_BENCHMARK_ROW_COUNT_MISMATCH"

    def test_a10e_load_rejects_wrong_schema_version(self, tmp_path):
        benchmark = build_j3_semantic_benchmark()
        benchmark["schema_version"] = "some.other.version"
        path = tmp_path / "wrong_schema.json"
        path.write_text(json.dumps(benchmark), encoding="utf-8")
        with pytest.raises(J3BenchmarkValidationError) as exc_info:
            load_j3_semantic_benchmark(path)
        assert exc_info.value.reason_code == "J3_BENCHMARK_SCHEMA_VERSION_MISMATCH"


# ---------------------------------------------------------------------------
# Section B -- Semantic comparison (checks 11-18)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_benchmark():
    return build_j3_semantic_benchmark()


@pytest.fixture(scope="module")
def real_stance_rows():
    return load_stance_comparison_rows()


@pytest.fixture(scope="module")
def real_comparison(real_benchmark, real_stance_rows):
    return compare_j3_benchmark(real_benchmark, real_stance_rows)


class TestSectionBSemanticComparison:
    def test_b11_exact_agreement_counts(self, real_comparison):
        assert real_comparison["independent_vs_b1_llm_agreement_count"] == 39
        assert real_comparison["independent_vs_b1_llm_agreement_rate"] == pytest.approx(0.78)
        assert real_comparison["independent_vs_deterministic_agreement_count"] == 22
        assert real_comparison["independent_vs_deterministic_agreement_rate"] == pytest.approx(0.44)

    def test_b12_exact_partition_breakdown(self, real_comparison):
        assert real_comparison["both_agree_count"] == 18
        assert real_comparison["b1_llm_only_count"] == 21
        assert real_comparison["deterministic_only_count"] == 4
        assert real_comparison["neither_count"] == 7

    def test_b13_all_seven_reversal_rows_support_b1_llm(self, real_benchmark, real_stance_rows):
        assert verify_reversal_rows_support_b1_llm(real_benchmark, real_stance_rows) is True

    def test_b14_exact_disagreement_ids(self, real_comparison):
        assert tuple(real_comparison["disagreement_rows"]) == tuple(sorted(EXPECTED_DISAGREEMENT_ROW_IDS))
        assert len(real_comparison["disagreement_rows"]) == 11

    def test_b15_false_support_positive_is_zero(self, real_comparison):
        changes = real_comparison["support_pool_changes"]
        assert changes["false_support_positive_count"] == 0
        assert changes["false_support_positive_rows"] == []

    def test_b16_false_support_negative_exact_ids(self, real_comparison):
        changes = real_comparison["support_pool_changes"]
        assert changes["false_support_negative_count"] == 4
        assert tuple(changes["false_support_negative_rows"]) == tuple(sorted(EXPECTED_FALSE_SUPPORT_NEGATIVE_IDS))

    def test_b17_comparison_never_mutates_its_inputs(self, real_benchmark, real_stance_rows):
        benchmark_before = json.dumps(real_benchmark, sort_keys=True)
        stance_before = json.dumps(real_stance_rows, sort_keys=True)
        compare_j3_benchmark(real_benchmark, real_stance_rows)
        assert json.dumps(real_benchmark, sort_keys=True) == benchmark_before
        assert json.dumps(real_stance_rows, sort_keys=True) == stance_before

    def test_b18_tampered_row_is_caught_fail_closed_never_silently_reported(self, real_benchmark, real_stance_rows):
        # evrs-001 is not in the disagreement list, so its reviewed_stance
        # originally agrees with llm_v1_stance ("supports_alpha"); flipping
        # it must break the historically-recorded 39/50 agreement count.
        tampered = json.loads(json.dumps(real_benchmark))
        for row in tampered["rows"]:
            if row["sample_id"] == "evrs-001":
                row["reviewed_stance"] = "opposes_alpha"
        with pytest.raises(J3SemanticComparisonMismatchError):
            compare_j3_benchmark(tampered, real_stance_rows)

    def test_b18b_wrong_row_count_is_caught_fail_closed(self, real_benchmark, real_stance_rows):
        truncated = {**real_benchmark, "rows": real_benchmark["rows"][:10]}
        with pytest.raises(J3SemanticComparisonMismatchError):
            compare_j3_benchmark(truncated, real_stance_rows)


# ---------------------------------------------------------------------------
# Section C -- J2 v0.2 schema (checks 19-28)
# ---------------------------------------------------------------------------


def _empty_v2_ticker_block(**overrides) -> dict:
    block = {
        "structural_expectations": {"positive_alphas": [], "negative_alphas": [], "conditional_alphas": []},
        "run_bound_expectations": None,
        "required_conflicts": [],
        "conditional_conflicts": [],
        "product_decision_pending": [],
        "remove_while_undeclared": [],
        "allowed_conflicts": [],
    }
    block.update(overrides)
    return block


def _minimal_v2_yaml(**ticker_overrides) -> str:
    payload = {
        "schema_version": "regression_labels.v2",
        "label_version": "test.v2",
        "taxonomy_version": "alpha_taxonomy_v1",
        "evaluation_mode": "shadow",
        "evaluation_authority": "provisional",
        "approved_by": None,
        "approved_at": None,
        "formal_product_owner_approval": "pending",
        "tickers": {"NVDA": _empty_v2_ticker_block(**ticker_overrides)},
    }
    return yaml.safe_dump(payload)


def _evaluable_result(*, admitted_conflicts=None, candidate_conflicts=None, detected_alphas=None) -> dict:
    return {
        "run_selection_status": "selected",
        "offline_reprocess_status": "completed",
        "artifact_completeness": "pass",
        "ticker_consistency": "pass",
        "admitted_conflicts": admitted_conflicts or [],
        "candidate_conflicts": candidate_conflicts or [],
        "detected_alphas": detected_alphas or [],
    }


def _not_evaluable_result() -> dict:
    return {
        "run_selection_status": "selected",
        "offline_reprocess_status": "completed",
        "artifact_completeness": "fail",
        "ticker_consistency": "pass",
        "admitted_conflicts": [],
        "candidate_conflicts": [],
        "detected_alphas": [],
    }


class TestSectionCJ2V2Schema:
    def test_c19_v01_still_loads_and_is_unaffected_by_v02(self):
        v1 = load_j2_labels()
        assert v1["schema_version"] == "regression_labels.v1"
        assert set(SIX_TICKERS) <= set(v1["tickers"].keys())

    def test_c19b_v01_file_byte_identical_to_recorded_hash(self):
        content = DEFAULT_LABEL_PATH.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        assert digest == "3eec746e1f0fed0f568d77cb5a4368b5fa6d19421b305c54c6d24132cacbe9f1"

    def test_c20_pair_in_multiple_categories_is_rejected(self, tmp_path):
        raw = _minimal_v2_yaml(required_conflicts=["A101__A304"], conditional_conflicts=["A101__A304"])
        path = tmp_path / "bad_v2.yaml"
        path.write_text(raw, encoding="utf-8")
        with pytest.raises(LabelV2ValidationError) as exc_info:
            load_j2_labels_v2(path)
        assert exc_info.value.reason_code == "LABEL_V2_PAIR_IN_MULTIPLE_CATEGORIES"

    def test_c21_conditional_conflict_miss_is_informational_never_fails_ticker(self):
        label = _empty_v2_ticker_block(conditional_conflicts=["A101__A304"])
        result = apply_v2_contract(
            ticker="NVDA", ticker_v2_label=label, evaluate_ticker_result=_evaluable_result()
        )
        assert result["conditional_conflict_results"][0]["result"] == "informational_mismatch"
        assert result["ticker_status"] == "pass"

    def test_c22_required_conflict_miss_fails_the_ticker(self):
        label = _empty_v2_ticker_block(required_conflicts=["A101__A304"])
        result = apply_v2_contract(
            ticker="NVDA", ticker_v2_label=label, evaluate_ticker_result=_evaluable_result()
        )
        assert result["required_conflict_results"][0]["result"] == "fail"
        assert result["ticker_status"] == "fail"

    def test_c22b_required_conflict_present_passes_the_ticker(self):
        label = _empty_v2_ticker_block(required_conflicts=["A101__A304"])
        result = apply_v2_contract(
            ticker="NVDA",
            ticker_v2_label=label,
            evaluate_ticker_result=_evaluable_result(admitted_conflicts=["A101__A304"]),
        )
        assert result["required_conflict_results"][0]["result"] == "pass"
        assert result["ticker_status"] == "pass"

    def test_c23_product_decision_pending_is_always_unresolved_never_pass_fail(self):
        label = _empty_v2_ticker_block(product_decision_pending=[{"pair_id": "A102__A304", "reason": "x"}])
        for evaluate_result in (_evaluable_result(), _not_evaluable_result()):
            result = apply_v2_contract(ticker="MSFT", ticker_v2_label=label, evaluate_ticker_result=evaluate_result)
            pending = result["product_decision_pending_results"][0]
            assert pending["result"] == "unresolved"
            assert pending["pair_id"] == "A102__A304"

    def test_c24_incomplete_artifact_marks_whole_ticker_not_evaluable(self):
        result = apply_v2_contract(
            ticker="QQQ", ticker_v2_label=_empty_v2_ticker_block(), evaluate_ticker_result=_not_evaluable_result()
        )
        assert result["evaluation_status"] == "not_evaluable"
        assert result["ticker_status"] == "not_evaluable"

    def test_c24b_incomplete_artifact_never_evaluates_conditional_pairs_as_if_reliable(self):
        label = _empty_v2_ticker_block(conditional_conflicts=["A101__A304"])
        result = apply_v2_contract(ticker="QQQ", ticker_v2_label=label, evaluate_ticker_result=_not_evaluable_result())
        assert result["conditional_conflict_results"] == []

    def test_c25_undeclared_executable_conflict_pair_rejected(self, tmp_path):
        raw = _minimal_v2_yaml(conditional_conflicts=["A999__A998"])
        path = tmp_path / "bad_v2.yaml"
        path.write_text(raw, encoding="utf-8")
        with pytest.raises(LabelV2ValidationError) as exc_info:
            load_j2_labels_v2(path)
        assert exc_info.value.reason_code == "LABEL_V2_UNDECLARED_EXECUTABLE_CONFLICT_PAIR"

    def test_c25b_remove_while_undeclared_rejects_an_actually_canonical_pair(self, tmp_path):
        raw = _minimal_v2_yaml(remove_while_undeclared=["A101__A304"])
        path = tmp_path / "bad_v2.yaml"
        path.write_text(raw, encoding="utf-8")
        with pytest.raises(LabelV2ValidationError) as exc_info:
            load_j2_labels_v2(path)
        assert exc_info.value.reason_code == "LABEL_V2_REMOVE_WHILE_UNDECLARED_IS_ACTUALLY_CANONICAL"

    def test_c26_msft_a102_a304_was_adjudicated_and_rejected_not_pending(self):
        # Was product_decision_pending at the time this test was first
        # written; formally adjudicated to REJECT_PAIR by PD-017
        # (docs/specs/product_decisions_and_unknowns.md) -- see
        # tests/test_msft_a102_a304_taxonomy_adjudication.py for the
        # dedicated regression coverage of that decision.
        v2 = load_j2_labels_v2()
        msft = ticker_label_v2(v2, "MSFT")
        pending_ids = {entry["pair_id"] for entry in msft["product_decision_pending"]}
        assert "A102__A304" not in pending_ids
        assert "A102__A304" in msft["remove_while_undeclared"]
        assert "A102__A304" not in msft["required_conflicts"]
        assert "A102__A304" not in msft["conditional_conflicts"]
        assert "A102__A304" not in msft["allowed_conflicts"]

    def test_c27_amd_a301_a304_is_allowed_not_auto_required(self):
        v2 = load_j2_labels_v2()
        amd = ticker_label_v2(v2, "AMD")
        assert "A301__A304" in amd["allowed_conflicts"]
        assert "A301__A304" not in amd["required_conflicts"]
        assert "A301__A304" not in amd["conditional_conflicts"]

    def test_c28_a201_a304_no_longer_executable_for_sndk_tsm_amd(self):
        v2 = load_j2_labels_v2()
        for ticker in ("SNDK", "TSM", "AMD"):
            block = ticker_label_v2(v2, ticker)
            assert "A201__A304" in block["remove_while_undeclared"], ticker
            for category in ("required_conflicts", "conditional_conflicts", "allowed_conflicts"):
                assert "A201__A304" not in block[category], f"{ticker}.{category}"

    def test_c28b_no_ticker_currently_has_a_required_conflict(self):
        # No formally John-approved, artifact-complete, version-locked
        # reference run exists yet for any of the six tickers -- promoting
        # anything into required_conflicts is a future, explicit action,
        # never inferred from a provisional shadow-evaluation run.
        v2 = load_j2_labels_v2()
        for ticker in SIX_TICKERS:
            assert ticker_label_v2(v2, ticker)["required_conflicts"] == []


# ---------------------------------------------------------------------------
# Section D -- A4 integration (checks 29-35)
# ---------------------------------------------------------------------------


def _minimal_ticker_result(ticker: str) -> dict:
    return {
        "ticker": ticker,
        "run_selection_status": "selected",
        "offline_reprocess_status": "completed",
        "provider_calls": 0,
        "tradingagents_calls": 0,
    }


class TestSectionDA4Integration:
    def test_d29_report_shows_actual_label_and_benchmark_versions(self, real_comparison):
        report = build_regression_report(
            tickers_requested=["NVDA"],
            label_version="j2.provisional.v0.1",
            label_status="provisional_ai_predicted",
            evaluation_mode="shadow",
            results=[_minimal_ticker_result("NVDA")],
            semantic_benchmark={"benchmark_version": "v0.1", "row_count": 50, "comparison": real_comparison},
            evaluation_contract={"j2_label_version": "j2.provisional.v0.2"},
        )
        assert report["semantic_benchmark"]["benchmark_version"] == "v0.1"
        assert report["evaluation_contract"]["j2_label_version"] == "j2.provisional.v0.2"

    def test_d30_semantic_benchmark_block_has_all_required_fields(self, real_benchmark, real_comparison):
        block = {
            "benchmark_version": "v0.1",
            "authority": real_benchmark["authority"],
            "human_review_performed": real_benchmark["human_review_performed"],
            "john_approved": real_benchmark["john_approved"],
            "row_count": real_benchmark["row_count"],
            "comparison": real_comparison,
        }
        for key in ("benchmark_version", "authority", "human_review_performed", "john_approved", "row_count", "comparison"):
            assert key in block
        assert block["human_review_performed"] is False
        assert block["john_approved"] is False
        assert block["row_count"] == 50

    def test_d31_report_omits_new_keys_entirely_when_not_given(self):
        report = build_regression_report(
            tickers_requested=["NVDA"],
            label_version="j2.provisional.v0.1",
            label_status="provisional_ai_predicted",
            evaluation_mode="shadow",
            results=[_minimal_ticker_result("NVDA")],
        )
        assert "semantic_benchmark" not in report
        assert "evaluation_contract" not in report

    def test_d32a_cli_without_new_flags_produces_no_new_keys(self, tmp_path):
        if not (REPO_ROOT / "outputs" / "runs").exists():
            pytest.skip("LIVE_SAVED_RUN_NOT_AVAILABLE: no outputs/runs directory")
        report_path = tmp_path / "regression_report.json"
        proc = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "run_regression.py"),
                "--tickers",
                "NVDA",
                "--report-path",
                str(report_path),
                "--replay-output-root",
                str(tmp_path / "replays"),
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert report_path.exists(), proc.stderr
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert "semantic_benchmark" not in report
        assert "evaluation_contract" not in report
        assert report["label_version"] == "j2.provisional.v0.1"

    def test_d32b_cli_bad_labels_v2_path_exits_with_dedicated_code(self, tmp_path):
        proc = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "run_regression.py"),
                "--tickers",
                "NVDA",
                "--labels-v2",
                str(tmp_path / "does_not_exist.yaml"),
                "--report-path",
                str(tmp_path / "regression_report.json"),
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 5, proc.stderr

    def test_d32c_cli_bad_semantic_benchmark_path_exits_with_dedicated_code(self, tmp_path):
        proc = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "run_regression.py"),
                "--tickers",
                "NVDA",
                "--semantic-benchmark",
                str(tmp_path / "does_not_exist.json"),
                "--report-path",
                str(tmp_path / "regression_report.json"),
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 6, proc.stderr

    def test_d33_repeated_comparison_is_deterministic(self, real_benchmark, real_stance_rows):
        first = compare_j3_benchmark(real_benchmark, real_stance_rows)
        second = compare_j3_benchmark(real_benchmark, real_stance_rows)
        assert first == second

    def test_d33b_repeated_contract_application_is_deterministic(self):
        label = _empty_v2_ticker_block(conditional_conflicts=["A101__A304"])
        evaluate_result = _evaluable_result(admitted_conflicts=["A101__A304"])
        first = apply_v2_contract(ticker="NVDA", ticker_v2_label=label, evaluate_ticker_result=evaluate_result)
        second = apply_v2_contract(ticker="NVDA", ticker_v2_label=label, evaluate_ticker_result=evaluate_result)
        assert first == second

    def test_d34_generated_at_is_the_only_field_allowed_to_vary(self):
        kwargs = {
            "tickers_requested": ["NVDA"],
            "label_version": "v",
            "label_status": "s",
            "evaluation_mode": "shadow",
            "results": [_minimal_ticker_result("NVDA")],
        }
        report_a = dict(build_regression_report(**kwargs))
        report_b = dict(build_regression_report(**kwargs))
        report_a.pop("generated_at")
        report_b.pop("generated_at")
        assert report_a == report_b

    def test_d35_source_run_directory_hash_unchanged_after_v02_contract_application(self, real_evaluated_nvda):
        assert real_evaluated_nvda["artifact_hashes"]["source_raw_artifact_unchanged"] is True
        before = real_evaluated_nvda["artifact_hashes"]["source_raw_agent_outputs_sha256_before"]
        v2 = load_j2_labels_v2()
        label = ticker_label_v2(v2, "NVDA")
        apply_v2_contract(ticker="NVDA", ticker_v2_label=label, evaluate_ticker_result=real_evaluated_nvda)
        assert real_evaluated_nvda["artifact_hashes"]["source_raw_agent_outputs_sha256_before"] == before


# ---------------------------------------------------------------------------
# Section E -- Invariants (checks 36-43)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_saved_nvda_run_id() -> str | None:
    runs_dir = REPO_ROOT / "outputs" / "runs"
    if not runs_dir.exists():
        return None
    for path in sorted(runs_dir.glob("*/metadata.json")):
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if metadata.get("ticker") == "NVDA" and (path.parent / "raw_agent_outputs.json").exists():
            return path.parent.name
    return None


@pytest.fixture(scope="module")
def real_evaluated_nvda(real_saved_nvda_run_id, tmp_path_factory):
    if real_saved_nvda_run_id is None:
        pytest.skip("LIVE_SAVED_RUN_NOT_AVAILABLE: no real NVDA saved run found")
    v1_labels = load_j2_labels()
    label_block = ticker_label(v1_labels, "NVDA")
    selection = select_run_for_ticker("NVDA", REPO_ROOT / "outputs" / "runs")
    replay_root = tmp_path_factory.mktemp("j3_j2_v02_replay")
    return evaluate_ticker("NVDA", selection, label_block, replay_output_root=str(replay_root))


class TestSectionEInvariants:
    def test_e36_five_value_stance_vocabulary_unchanged(self):
        assert frozenset(
            {"supports_alpha", "opposes_alpha", "mentions_alpha", "neutral_background", "supports_counter_alpha"}
        ) == VALID_EVIDENCE_STANCES

    def test_e37_b2_admissibility_status_constants_unchanged(self):
        assert ADMITTED == "admitted"
        assert CANDIDATE == "candidate"

    def test_e38_canonical_conflict_pairs_are_exactly_the_frozen_six(self):
        # MVP-10 taxonomy's 6 frozen conflict pairs (canonical_pair_key's
        # own alpha-sorted __-joined form, e.g. A601__A304 sorts as
        # "A304__A601").
        taxonomy = load_alpha_taxonomy()
        pairs = _canonical_conflict_pairs(taxonomy)
        assert pairs == frozenset(
            {"A101__A304", "A301__A304", "A001__A501", "A003__A501", "A304__A601", "A501__A601"}
        )

    def test_e39_msft_pending_pair_was_never_added_to_canonical_taxonomy(self):
        taxonomy = load_alpha_taxonomy()
        pairs = _canonical_conflict_pairs(taxonomy)
        assert "A102__A304" not in pairs

    def test_e40_provider_calls_zero_on_real_replay(self, real_evaluated_nvda):
        assert real_evaluated_nvda.get("provider_calls") == 0

    def test_e41_tradingagents_calls_zero_on_real_replay(self, real_evaluated_nvda):
        assert real_evaluated_nvda.get("tradingagents_calls") == 0

    def test_e42_head_unchanged_from_session_frozen_starting_commit(self):
        # Proxy for "commit=none": HEAD must still equal the commit
        # recorded at the very start of this multi-segment session.
        # "push=none" and "SUBAGENTS=0" are process-level facts about this
        # session's own operator actions, not code behavior -- verified
        # and stated directly in the final report, not asserted here.
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), capture_output=True, text=True, check=True
        )
        assert proc.stdout.strip() == FROZEN_SESSION_HEAD

    def test_e43_frozen_files_this_segment_must_never_touch_are_clean(self):
        # B1 prompt/stance-derivation, B2 admissibility, ConflictScore, and
        # the canonical taxonomy may already carry *staged* changes from
        # this session's earlier B1-B5 segments (legitimate, pre-existing
        # before this J3/J2 segment began) -- what this segment must never
        # do is layer any further *unstaged* edit on top of them.
        #
        # week2_llm.py and alpha_mapper.py removed from this list (Post-
        # Alpha-Authority-Migration Cleanup task): this guard was always
        # scoped to the J3/J2 segment's own historical execution window
        # ("this segment must never touch") -- a segment-local, task-
        # completion assertion, not a permanent product invariant (see
        # this file's own module docstring: sections map to that task's
        # own 43-item checklist). The later, separately Product-Owner-
        # authorized Alpha Mapper Authority Migration explicitly modified
        # both files (LLM semantic primary over the full canonical
        # taxonomy; see comqutor_alpha/structure_engine/alpha_mapper.py
        # and week2_llm.py's alpha_classifier v2 prompt) -- an intentional,
        # in-scope, unrelated-to-J3/J2 change. The remaining three paths
        # are untouched by that migration and stay covered here unchanged.
        frozen_paths = [
            "comqutor_alpha/conflict_engine/conflict_schema.py",
            "comqutor_alpha/conflict_engine/conflict_admissibility.py",
            "comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml",
        ]
        proc = subprocess.run(
            ["git", "status", "--porcelain", "--", *frozen_paths],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        for line in (line for line in proc.stdout.splitlines() if line.strip()):
            worktree_status = line[1]
            assert worktree_status == " ", f"unstaged change found on top of already-staged content: {line!r}"
