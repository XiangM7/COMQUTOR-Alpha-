"""Tests for v0.1.3 Measurement Foundation, Part A: multi_run_reproducibility.

Pure, offline, deterministic -- no Provider call, no ticker run, no
filesystem mutation. Two categories: (1) synthetic-fixture unit tests
covering every rule in isolation (sections 27 A-R), and (2) a real-data
regression test reusing the persisted OLD/NEW TSM run artifacts to lock in
the exact fixture numbers from the task spec (section 17)."""

from __future__ import annotations

from pathlib import Path

import pytest

from comqutor_alpha.regression import multi_run_reproducibility as mrr

REPO_ROOT = Path(__file__).resolve().parents[1]
OLD_TSM_RUN_DIR = REPO_ROOT / "outputs" / "runs" / "dfc7ceb3-3584-4514-bd84-6c371aab3e95"
NEW_TSM_RUN_DIR = REPO_ROOT / "outputs" / "runs" / "0aeea938-97a8-49c8-97e1-409f6dadad30"
OLD_TSM_RUN_ID = "dfc7ceb3-3584-4514-bd84-6c371aab3e95"
NEW_TSM_RUN_ID = "0aeea938-97a8-49c8-97e1-409f6dadad30"


def _run_audit(per_alpha: dict) -> dict:
    return {"activation_summary": {"per_alpha": per_alpha}}


def _alpha_state(level: str, score: float | None = 0.0) -> dict:
    return {"level": level, "score": score}


# --- A. one-run evaluation ---------------------------------------------


def test_one_run_evaluation():
    run_audit = _run_audit({"A101": _alpha_state("active", 70.0), "A103": _alpha_state("candidate", 25.0)})
    result = mrr.evaluate_run(
        ticker="TSM", run_id="r1", run_audit=run_audit, gold_alpha_ids=["A101", "A103"]
    )
    assert result["gold_alpha_count"] == 2
    assert result["detected_gold_count"] == 1
    assert result["detected_gold_alpha_ids"] == ["A101"]
    assert result["missed_gold_alpha_ids"] == ["A103"]
    assert result["gold_hit_rate"] == pytest.approx(0.5)


# --- N. missing score handled as null -----------------------------------


def test_missing_score_handled_as_null():
    run_audit = _run_audit({"A101": {"level": "active"}})
    result = mrr.evaluate_run(ticker="TSM", run_id="r1", run_audit=run_audit, gold_alpha_ids=["A101"])
    assert result["per_alpha_gold_states"]["A101"]["level"] == "active"
    assert result["per_alpha_gold_states"]["A101"].get("score") is None


def test_alpha_missing_entirely_reports_null_state_and_not_detected():
    run_audit = _run_audit({})
    result = mrr.evaluate_run(ticker="TSM", run_id="r1", run_audit=run_audit, gold_alpha_ids=["A999"])
    assert result["per_alpha_gold_states"]["A999"] is None
    assert result["detected_gold_alpha_ids"] == []
    assert result["missed_gold_alpha_ids"] == ["A999"]


# --- N/O/P/Q. detection-level authority reuse ----------------------------


@pytest.mark.parametrize(
    "level,expected_detected",
    [
        ("candidate", False),
        ("capped_active", False),
        ("blocked", False),
        ("active", True),
        ("dominant", True),
        ("regime_level", True),
    ],
)
def test_detection_levels_match_canonical_authority(level, expected_detected):
    run_audit = _run_audit({"A101": _alpha_state(level)})
    detected = mrr.detected_alpha_ids_from_run_audit(run_audit)
    assert ("A101" in detected) is expected_detected


def test_reuses_canonical_detected_levels_constant_not_a_local_copy():
    from comqutor_alpha.regression.regression_report_v3 import _DETECTED_LEVELS

    assert mrr._DETECTED_LEVELS is _DETECTED_LEVELS


# --- C/D/E/F/G. flip classification (two-run) ----------------------------


def test_stable_hit_classification():
    e1 = {"run_id": "r1", "detected_gold_alpha_ids": ["A101"], "per_alpha_gold_states": {"A101": _alpha_state("active")}}
    e2 = {"run_id": "r2", "detected_gold_alpha_ids": ["A101"], "per_alpha_gold_states": {"A101": _alpha_state("active")}}
    agg = mrr.aggregate_alpha_across_runs("A101", [e1, e2])
    assert agg["two_run_flip_classification"] == mrr.STABLE_HIT
    assert agg["detection_frequency"] == 1.0


def test_stable_miss_classification():
    e1 = {"run_id": "r1", "detected_gold_alpha_ids": [], "per_alpha_gold_states": {"A101": _alpha_state("candidate")}}
    e2 = {"run_id": "r2", "detected_gold_alpha_ids": [], "per_alpha_gold_states": {"A101": _alpha_state("candidate")}}
    agg = mrr.aggregate_alpha_across_runs("A101", [e1, e2])
    assert agg["two_run_flip_classification"] == mrr.STABLE_MISS
    assert agg["detection_frequency"] == 0.0


def test_hit_to_miss_classification():
    e1 = {"run_id": "r1", "detected_gold_alpha_ids": ["A101"], "per_alpha_gold_states": {"A101": _alpha_state("active")}}
    e2 = {"run_id": "r2", "detected_gold_alpha_ids": [], "per_alpha_gold_states": {"A101": _alpha_state("candidate")}}
    agg = mrr.aggregate_alpha_across_runs("A101", [e1, e2])
    assert agg["two_run_flip_classification"] == mrr.HIT_TO_MISS
    assert agg["transition_count"] == 1


def test_miss_to_hit_classification():
    e1 = {"run_id": "r1", "detected_gold_alpha_ids": [], "per_alpha_gold_states": {"A101": _alpha_state("candidate")}}
    e2 = {"run_id": "r2", "detected_gold_alpha_ids": ["A101"], "per_alpha_gold_states": {"A101": _alpha_state("active")}}
    agg = mrr.aggregate_alpha_across_runs("A101", [e1, e2])
    assert agg["two_run_flip_classification"] == mrr.MISS_TO_HIT
    assert agg["transition_count"] == 1


# --- J. 3-run detection sequence -----------------------------------------


def test_three_run_detection_sequence_and_transition_count():
    runs = [
        {"run_id": "r1", "detected_gold_alpha_ids": ["A101"], "per_alpha_gold_states": {"A101": _alpha_state("active")}},
        {"run_id": "r2", "detected_gold_alpha_ids": [], "per_alpha_gold_states": {"A101": _alpha_state("candidate")}},
        {"run_id": "r3", "detected_gold_alpha_ids": ["A101"], "per_alpha_gold_states": {"A101": _alpha_state("active")}},
    ]
    agg = mrr.aggregate_alpha_across_runs("A101", runs)
    assert agg["detection_sequence"] == [True, False, True]
    assert agg["transition_count"] == 2
    assert agg["detection_frequency"] == pytest.approx(2 / 3)
    # No binary stable/unstable threshold is invented for 3+ runs.
    assert agg["two_run_flip_classification"] is None


# --- H/I. pairwise Jaccard -------------------------------------------------


def test_pairwise_gold_jaccard_two_runs():
    result = mrr.pairwise_jaccards({"r1": {"A101", "A103"}, "r2": {"A101"}})
    assert result["mean_pairwise_jaccard"] == pytest.approx(0.5)
    assert result["min_pairwise_jaccard"] == pytest.approx(0.5)
    assert result["max_pairwise_jaccard"] == pytest.approx(0.5)
    assert len(result["pairwise_values"]) == 1


def test_pairwise_all_alpha_jaccard_three_runs_exposes_dispersion():
    result = mrr.pairwise_jaccards({"r1": {"A101"}, "r2": {"A101", "A103"}, "r3": set()})
    assert len(result["pairwise_values"]) == 3
    # dispersion must not be hidden -- min/max may legitimately differ from mean
    assert result["min_pairwise_jaccard"] <= result["mean_pairwise_jaccard"] <= result["max_pairwise_jaccard"]


def test_jaccard_both_empty_is_deterministic():
    assert mrr.jaccard(set(), set()) == 1.0


def test_jaccard_one_empty_one_nonempty():
    assert mrr.jaccard(set(), {"A101"}) == 0.0


# --- R. Provider-degraded run reported, not silently excluded -----------


def test_provider_degraded_run_is_reported_not_excluded():
    run_audit = _run_audit({"A101": _alpha_state("active")})
    result = mrr.evaluate_run(
        ticker="TSM",
        run_id="r1",
        run_audit=run_audit,
        gold_alpha_ids=["A101"],
        provider_health={"provider_health": "PROVIDER_DEGRADED", "benchmark_review_required": True, "impacted_alpha_ids": ["A101"]},
    )
    assert result["provider_health"] == "PROVIDER_DEGRADED"
    assert result["benchmark_review_required"] is True
    assert result["gold_hit_rate"] == 1.0  # not excluded from accuracy computation


def test_aggregate_ticker_reports_all_runs_never_filters():
    e1 = {
        "run_id": "r1", "gold_hit_rate": 1.0, "detected_gold_count": 1,
        "detected_gold_alpha_ids": ["A101"], "detected_all_alpha_ids": ["A101"],
        "per_alpha_gold_states": {"A101": _alpha_state("active")},
        "provider_health": "PROVIDER_DEGRADED", "benchmark_review_required": True,
    }
    e2 = {
        "run_id": "r2", "gold_hit_rate": 1.0, "detected_gold_count": 1,
        "detected_gold_alpha_ids": ["A101"], "detected_all_alpha_ids": ["A101"],
        "per_alpha_gold_states": {"A101": _alpha_state("active")},
        "provider_health": "PROVIDER_HEALTHY", "benchmark_review_required": False,
    }
    agg = mrr.aggregate_ticker_across_runs(ticker="TSM", run_evaluations=[e1, e2], gold_alpha_ids=["A101"])
    assert agg["runs_total"] == 2
    assert agg["runs_provider_degraded"] == 1
    assert agg["run_filtering_policy"] == "REPORT_ALL_RUNS"
    assert set(agg["quality_flags_by_run"]) == {"r1", "r2"}


# --- K. variable run counts across tickers do not change ticker weighting -


def test_variable_run_counts_do_not_change_ticker_weighting():
    nvda_runs = [
        {"run_id": f"nvda{i}", "gold_hit_rate": rate, "detected_gold_count": 0,
         "detected_gold_alpha_ids": [], "detected_all_alpha_ids": [], "per_alpha_gold_states": {}}
        for i, rate in enumerate([1.0, 0.5, 0.5])
    ]
    qqq_runs = [
        {"run_id": f"qqq{i}", "gold_hit_rate": rate, "detected_gold_count": 0,
         "detected_gold_alpha_ids": [], "detected_all_alpha_ids": [], "per_alpha_gold_states": {}}
        for i, rate in enumerate([0.0, 0.0])
    ]
    nvda_agg = mrr.aggregate_ticker_across_runs(ticker="NVDA", run_evaluations=nvda_runs, gold_alpha_ids=[])
    qqq_agg = mrr.aggregate_ticker_across_runs(ticker="QQQ", run_evaluations=qqq_runs, gold_alpha_ids=[])

    macro = mrr.aggregate_global_macro({"NVDA": nvda_agg, "QQQ": qqq_agg})
    # NVDA mean = 2/3, QQQ mean = 0.0 -> macro = mean(2/3, 0.0) = 1/3,
    # NOT mean of all 5 individual run rates pooled together (which would be 0.4).
    assert macro["multi_run_macro_gold_hit_rate"] == pytest.approx((2 / 3 + 0.0) / 2)
    assert macro["multi_run_macro_gold_hit_rate"] != pytest.approx(0.4)


# --- L. macro-average, not micro-average ----------------------------------


def test_macro_average_matches_ticker_means_not_pooled_runs():
    a_runs = [{"run_id": "a1", "gold_hit_rate": 1.0, "detected_gold_count": 0, "detected_gold_alpha_ids": [], "detected_all_alpha_ids": [], "per_alpha_gold_states": {}}]
    b_runs = [
        {"run_id": "b1", "gold_hit_rate": 0.0, "detected_gold_count": 0, "detected_gold_alpha_ids": [], "detected_all_alpha_ids": [], "per_alpha_gold_states": {}},
        {"run_id": "b2", "gold_hit_rate": 0.0, "detected_gold_count": 0, "detected_gold_alpha_ids": [], "detected_all_alpha_ids": [], "per_alpha_gold_states": {}},
        {"run_id": "b3", "gold_hit_rate": 0.0, "detected_gold_count": 0, "detected_gold_alpha_ids": [], "detected_all_alpha_ids": [], "per_alpha_gold_states": {}},
    ]
    a_agg = mrr.aggregate_ticker_across_runs(ticker="A", run_evaluations=a_runs, gold_alpha_ids=[])
    b_agg = mrr.aggregate_ticker_across_runs(ticker="B", run_evaluations=b_runs, gold_alpha_ids=[])
    macro = mrr.aggregate_global_macro({"A": a_agg, "B": b_agg})
    assert macro["multi_run_macro_gold_hit_rate"] == pytest.approx(0.5)  # mean(1.0, 0.0)


# --- Planned acceptance target is isolated / non-gating -------------------


def test_planned_acceptance_diagnostic_is_isolated_and_non_gating():
    result = mrr.planned_acceptance_diagnostic(0.8)
    assert result["gate_status"] == mrr.NOT_ACTIVE_GATE
    assert result["meets_planned_target"] is True
    result_low = mrr.planned_acceptance_diagnostic(0.5)
    assert result_low["meets_planned_target"] is False
    assert result_low["gate_status"] == mrr.NOT_ACTIVE_GATE


def test_gold_alpha_ids_for_ticker_reuses_frozen_benchmark():
    gold = mrr.gold_alpha_ids_for_ticker("TSM")
    assert gold == ["A101", "A103", "A201", "A301", "A304", "A601"]


# --- B. two-run TSM evaluation (real persisted artifacts) -----------------


@pytest.mark.skipif(not OLD_TSM_RUN_DIR.is_dir() or not NEW_TSM_RUN_DIR.is_dir(), reason="TSM run artifacts not present in this environment")
class TestTSMTwoRunRegressionFixture:
    @pytest.fixture(scope="class")
    def gold(self):
        return mrr.gold_alpha_ids_for_ticker("TSM")

    @pytest.fixture(scope="class")
    def old_eval(self, gold):
        return mrr.evaluate_run_from_disk(
            ticker="TSM", run_id=OLD_TSM_RUN_ID, run_dir=OLD_TSM_RUN_DIR, gold_alpha_ids=gold
        )

    @pytest.fixture(scope="class")
    def new_eval(self, gold):
        return mrr.evaluate_run_from_disk(
            ticker="TSM", run_id=NEW_TSM_RUN_ID, run_dir=NEW_TSM_RUN_DIR, gold_alpha_ids=gold
        )

    def test_old_run_hit_rate(self, old_eval):
        assert old_eval["gold_hit_rate"] == pytest.approx(5 / 6)
        assert old_eval["detected_gold_alpha_ids"] == ["A101", "A103", "A201", "A304", "A601"]

    def test_new_run_hit_rate(self, new_eval):
        assert new_eval["gold_hit_rate"] == pytest.approx(4 / 6)
        assert new_eval["detected_gold_alpha_ids"] == ["A101", "A301", "A304", "A601"]

    def test_two_run_mean_is_75_percent(self, old_eval, new_eval, gold):
        agg = mrr.aggregate_ticker_across_runs(ticker="TSM", run_evaluations=[old_eval, new_eval], gold_alpha_ids=gold)
        assert agg["mean_gold_hit_rate"] == pytest.approx(0.75)
        assert agg["runs_evaluated"] == 2

    def test_per_alpha_detection_frequencies(self, old_eval, new_eval, gold):
        agg = mrr.aggregate_ticker_across_runs(ticker="TSM", run_evaluations=[old_eval, new_eval], gold_alpha_ids=gold)
        expected = {"A101": 1.0, "A103": 0.5, "A201": 0.5, "A301": 0.5, "A304": 1.0, "A601": 1.0}
        assert agg["per_alpha_detection_frequency"] == expected

    def test_variable_gold_alphas(self, old_eval, new_eval, gold):
        agg = mrr.aggregate_ticker_across_runs(ticker="TSM", run_evaluations=[old_eval, new_eval], gold_alpha_ids=gold)
        assert agg["variable_alpha_ids"] == ["A103", "A201", "A301"]
        assert agg["gold_alpha_flip_count"] == 3

    def test_gold_detected_set_jaccard(self, old_eval, new_eval, gold):
        agg = mrr.aggregate_ticker_across_runs(ticker="TSM", run_evaluations=[old_eval, new_eval], gold_alpha_ids=gold)
        assert agg["gold_detected_set_jaccard"]["mean_pairwise_jaccard"] == pytest.approx(0.5)

    def test_evaluation_does_not_mutate_run_artifacts(self, old_eval, new_eval):
        import hashlib

        for run_dir in (OLD_TSM_RUN_DIR, NEW_TSM_RUN_DIR):
            path = run_dir / "run_audit.json"
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            mrr.load_run_audit(run_dir)
            after = hashlib.sha256(path.read_bytes()).hexdigest()
            assert before == after
