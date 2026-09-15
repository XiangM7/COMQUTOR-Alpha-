"""V0.1.3 Provider Health + Benchmark Eligibility Diagnostics tests.

Covers synthetic-fixture unit tests (A-D, G-K) for the counting/classification
rules in isolation, plus real-persisted-run integration tests (E, F, L) using
the six FINAL_FRESH_SELECTED run directories already used throughout this
session's diagnostic tasks. All tests are read-only against persisted
artifacts or synthetic tmp_path fixtures -- zero Provider calls, zero ticker
runs, zero mutation of any historical artifact.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from comqutor_alpha.regression.provider_health_diagnostics import (
    PROVIDER_DEGRADED,
    PROVIDER_HEALTHY,
    compute_final_orphans,
    compute_impacted_alphas,
    compute_provider_failure_events,
    compute_provider_health_diagnostics,
)

REAL_RUNS_BASE = Path("outputs/runs")
REAL_RUNS = {
    "NVDA": "57d7b4c4-dbb9-4134-b962-ee2a873941cc",
    "QQQ": "f88c8956-cb62-48aa-9951-89f8e8a95f83",
    "MSFT": "43472ace-454f-4c69-892c-adca91c25be7",
    "SNDK": "e8e0f398-7b26-4462-8135-a1410ea5b335",
    "TSM": "dfc7ceb3-3584-4514-bd84-6c371aab3e95",
    "AMD": "949f685a-3945-4fd0-b7b9-362b37c90721",
}


def _real_run_dir(ticker: str) -> Path:
    path = REAL_RUNS_BASE / REAL_RUNS[ticker]
    if not path.is_dir():
        pytest.skip(f"real run artifact for {ticker} not present in this environment")
    return path


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + ("\n" if records else ""))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def _synthetic_run(
    tmp_path: Path,
    *,
    alpha_matches: list[dict] | None = None,
    error_log: list[dict] | None = None,
    semantic_calls: list[dict] | None = None,
    manifest: dict | None = None,
) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "alpha_matches.json", {"matches": alpha_matches or []})
    _write_jsonl(run_dir / "error_logs" / "week2_llm_errors.jsonl", error_log or [])
    _write_jsonl(run_dir / "llm_semantic_calls.jsonl", semantic_calls or [])
    if manifest is not None:
        _write_json(run_dir / "llm_semantic_manifest.json", manifest)
    return run_dir


def _claim(
    claim_id: str,
    *,
    agent: str = "fundamental_agent",
    match_status: str = "matched",
    matched_alpha: str | None = "A301",
    deterministic_match_status: str | None = "matched",
    deterministic_top_alpha: str | None = "A301",
    alpha_match_fallback_reason: str | None = None,
) -> dict:
    return {
        "claim_id": claim_id,
        "agent": agent,
        "match_status": match_status,
        "matched_alpha": matched_alpha,
        "deterministic_match_status": deterministic_match_status,
        "deterministic_top_alpha": deterministic_top_alpha,
        "alpha_match_fallback_reason": alpha_match_fallback_reason,
    }


# ---------------------------------------------------------------------------
# A. Failure event counting
# ---------------------------------------------------------------------------


def test_a_failure_event_counting_by_task(tmp_path):
    run_dir = _synthetic_run(
        tmp_path,
        error_log=[
            {"task": "alpha_classifier", "error_code": "WEEK2_LLM_TIMEOUT", "attempt": 1, "created_at": "2026-01-01T00:00:00Z"},
            {"task": "alpha_classifier", "error_code": "WEEK2_LLM_TIMEOUT", "attempt": 2, "created_at": "2026-01-01T00:01:00Z"},
            {"task": "evidence_stance_classifier", "error_code": "WEEK2_LLM_TIMEOUT", "attempt": 1, "created_at": "2026-01-01T00:02:00Z"},
            {"task": "claim_batch_enrichment", "error_code": "WEEK2_LLM_TIMEOUT", "attempt": 1, "created_at": "2026-01-01T00:03:00Z"},
        ],
    )
    result = compute_provider_failure_events(run_dir)
    assert result["provider_failure_events"] == 4
    assert result["semantic_critical_failure_events"] == 3  # excludes claim_batch_enrichment
    assert result["alpha_classifier_failure_events"] == 2


# ---------------------------------------------------------------------------
# B. Retry: failure then success -> event counted, no final orphan
# ---------------------------------------------------------------------------


def test_b_retry_failure_then_success_no_final_orphan(tmp_path):
    run_dir = _synthetic_run(
        tmp_path,
        alpha_matches=[_claim("c1", match_status="matched")],  # eventually succeeded
        error_log=[
            {"task": "alpha_classifier", "error_code": "WEEK2_LLM_TIMEOUT", "attempt": 1, "created_at": "2026-01-01T00:00:00Z"},
        ],
    )
    events = compute_provider_failure_events(run_dir)
    orphans = compute_final_orphans(run_dir)
    assert events["alpha_classifier_failure_events"] == 1
    assert orphans["alpha_classifier_final_orphans"] == 0
    impacted = compute_impacted_alphas(run_dir)
    assert impacted["alphas_impacted_by_provider_failure"] == 0


# ---------------------------------------------------------------------------
# C. Repeated retries on the SAME claim collapse to one final orphan
# ---------------------------------------------------------------------------


def test_c_repeated_retries_collapse_to_one_final_orphan(tmp_path):
    run_dir = _synthetic_run(
        tmp_path,
        alpha_matches=[_claim("c1", match_status="unavailable", matched_alpha=None,
                               alpha_match_fallback_reason="provider_timeout")],
        error_log=[
            {"task": "alpha_classifier", "error_code": "WEEK2_LLM_TIMEOUT", "attempt": 1, "created_at": "2026-01-01T00:00:00Z"},
            {"task": "alpha_classifier", "error_code": "WEEK2_LLM_TIMEOUT", "attempt": 2, "created_at": "2026-01-01T00:01:00Z"},
            {"task": "alpha_classifier", "error_code": "WEEK2_LLM_TIMEOUT", "attempt": 3, "created_at": "2026-01-01T00:02:00Z"},
        ],
    )
    events = compute_provider_failure_events(run_dir)
    orphans = compute_final_orphans(run_dir)
    assert events["alpha_classifier_failure_events"] == 3
    assert orphans["alpha_classifier_final_orphans"] == 1


# ---------------------------------------------------------------------------
# D. Semantic-critical vs presentation-only
# ---------------------------------------------------------------------------


def test_d_presentation_only_task_excluded_from_semantic_critical(tmp_path):
    run_dir = _synthetic_run(
        tmp_path,
        error_log=[
            {"task": "claim_batch_enrichment", "error_code": "WEEK2_LLM_TIMEOUT", "attempt": 1, "created_at": "2026-01-01T00:00:00Z"},
            {"task": "structured_adapter", "error_code": "WEEK2_LLM_TIMEOUT", "attempt": 1, "created_at": "2026-01-01T00:01:00Z"},
        ],
    )
    result = compute_provider_failure_events(run_dir)
    assert result["provider_failure_events"] == 2
    assert result["semantic_critical_failure_events"] == 0


# ---------------------------------------------------------------------------
# E. TSM A301 positive fixture (real persisted run)
# ---------------------------------------------------------------------------


def test_e_tsm_a301_positive_fixture_real_run():
    run_dir = _real_run_dir("TSM")
    result = compute_provider_health_diagnostics(run_dir=run_dir, ticker="TSM", run_id=REAL_RUNS["TSM"])
    assert result["provider_health"] == PROVIDER_DEGRADED
    assert "A301" in result["impacted_alpha_ids"]
    assert result["alphas_impacted_by_provider_failure"] >= 1
    assert result["benchmark_review_required"] is True
    assert any("A301" in reason for reason in result["benchmark_review_reasons"])
    assert result["alpha_classifier_final_orphans"] == 9
    assert result["alpha_classifier_failure_events"] == 47


# ---------------------------------------------------------------------------
# F. Unrelated Gold miss NOT impacted (real persisted runs, all 6 tickers)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ticker,unrelated_alphas",
    [
        ("NVDA", ["A102"]),
        ("MSFT", ["A102", "A304"]),
        ("AMD", ["A102"]),
        ("QQQ", ["A101"]),
        ("SNDK", ["A103", "A301"]),
    ],
)
def test_f_unrelated_gold_miss_not_impacted_real_runs(ticker, unrelated_alphas):
    run_dir = _real_run_dir(ticker)
    result = compute_provider_health_diagnostics(run_dir=run_dir, ticker=ticker, run_id=REAL_RUNS[ticker])
    for alpha_id in unrelated_alphas:
        assert alpha_id not in result["impacted_alpha_ids"], (
            f"{ticker} {alpha_id} must not be marked provider-impacted merely for being a miss"
        )


# ---------------------------------------------------------------------------
# G. benchmark_review_required trigger
# ---------------------------------------------------------------------------


def test_g_benchmark_review_required_triggers_on_impacted_alpha(tmp_path):
    run_dir = _synthetic_run(
        tmp_path,
        alpha_matches=[
            _claim("c1", match_status="unavailable", matched_alpha=None,
                   deterministic_match_status="matched", deterministic_top_alpha="A301",
                   alpha_match_fallback_reason="provider_timeout"),
        ],
    )
    result = compute_provider_health_diagnostics(run_dir=run_dir)
    assert result["benchmark_review_required"] is True
    assert result["benchmark_review_reasons"] == ["PROVIDER_FAILURE_IMPACTED_ALPHA:A301"]


def test_g_benchmark_review_not_required_when_no_impacted_alpha(tmp_path):
    run_dir = _synthetic_run(
        tmp_path,
        alpha_matches=[_claim("c1", match_status="matched")],
    )
    result = compute_provider_health_diagnostics(run_dir=run_dir)
    assert result["benchmark_review_required"] is False
    assert result["benchmark_review_reasons"] == []


# ---------------------------------------------------------------------------
# H. No auto benchmark rejection
# ---------------------------------------------------------------------------


def test_h_no_automatic_benchmark_rejection_field(tmp_path):
    run_dir = _synthetic_run(
        tmp_path,
        alpha_matches=[
            _claim("c1", match_status="unavailable", matched_alpha=None,
                   deterministic_match_status="matched", deterministic_top_alpha="A301"),
        ],
    )
    result = compute_provider_health_diagnostics(run_dir=run_dir)
    assert result["benchmark_auto_rejected"] is False
    assert "BENCHMARK_FAIL" not in json.dumps(result)
    assert "INVALID" not in json.dumps(result)


# ---------------------------------------------------------------------------
# I. Null denominator handling
# ---------------------------------------------------------------------------


def test_i_null_denominator_returns_none_not_guessed(tmp_path):
    run_dir = _synthetic_run(tmp_path)  # no manifest at all
    result = compute_provider_health_diagnostics(run_dir=run_dir)
    assert result["provider_call_attempts_total"] is None
    assert result["provider_failure_rate"] is None
    assert result["alpha_classifier_call_attempts"] is None
    assert result["alpha_classifier_failure_rate"] is None


def test_i_rate_computed_when_manifest_present(tmp_path):
    run_dir = _synthetic_run(
        tmp_path,
        error_log=[
            {"task": "alpha_classifier", "error_code": "WEEK2_LLM_TIMEOUT", "attempt": 1, "created_at": "2026-01-01T00:00:00Z"},
        ],
        manifest={"provider_call_count": 100, "tasks": {"alpha_classifier": 50}},
    )
    result = compute_provider_health_diagnostics(run_dir=run_dir)
    assert result["provider_failure_rate"] == pytest.approx(1 / 100)
    assert result["alpha_classifier_failure_rate"] == pytest.approx(1 / 50)


# ---------------------------------------------------------------------------
# J. Error-type aggregation
# ---------------------------------------------------------------------------


def test_j_error_type_aggregation_buckets(tmp_path):
    run_dir = _synthetic_run(
        tmp_path,
        error_log=[
            {"task": "alpha_classifier", "error_code": "WEEK2_LLM_TIMEOUT", "attempt": 1, "created_at": "2026-01-01T00:00:00Z"},
            {"task": "evidence_stance_classifier", "error_code": "WEEK2_LLM_TRANSPORT_ERROR", "attempt": 1, "created_at": "2026-01-01T00:01:00Z"},
            {"task": "structure_extractor", "error_code": "WEEK2_LLM_VALIDATION_FAILED", "attempt": 1, "created_at": "2026-01-01T00:02:00Z"},
        ],
    )
    result = compute_provider_failure_events(run_dir)
    assert result["error_type_counts"] == {"TIMEOUT": 1, "TRANSPORT_ERROR": 1, "SCHEMA_ERROR": 1}
    assert result["error_type_counts"].get("TIMEOUT") != result["provider_failure_events"]  # not collapsed to one bucket


def test_j_amd_transport_error_heavy_profile_real_run():
    """AMD previously showed a distinct TRANSPORT_ERROR-heavy profile --
    confirm the bucket breakdown preserves this distinction rather than
    collapsing everything to TIMEOUT."""
    run_dir = _real_run_dir("AMD")
    result = compute_provider_failure_events(run_dir)
    assert result["error_type_counts"].get("TRANSPORT_ERROR", 0) > 0
    assert result["error_type_counts"].get("TIMEOUT", 0) > 0


# ---------------------------------------------------------------------------
# K. Traceability unknown
# ---------------------------------------------------------------------------


def test_k_traceability_unknown_when_no_deterministic_lineage(tmp_path):
    run_dir = _synthetic_run(
        tmp_path,
        alpha_matches=[
            _claim("c1", match_status="unavailable", matched_alpha=None,
                   deterministic_match_status="no_match", deterministic_top_alpha=None),
            _claim("c2", match_status="unavailable", matched_alpha=None,
                   deterministic_match_status="ambiguous", deterministic_top_alpha=None),
        ],
    )
    impacted = compute_impacted_alphas(run_dir)
    assert impacted["alphas_impacted_by_provider_failure"] == 0
    assert impacted["impacted_alpha_ids"] == []
    assert impacted["traceability_unknown_count"] == 2


# ---------------------------------------------------------------------------
# L. Diagnostics do not mutate Alpha result (real runs, byte-identical reread)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ticker", list(REAL_RUNS))
def test_l_diagnostics_do_not_mutate_alpha_matches_artifact(ticker):
    run_dir = _real_run_dir(ticker)
    path = run_dir / "alpha_matches.json"
    before = path.read_bytes()
    compute_provider_health_diagnostics(run_dir=run_dir, ticker=ticker, run_id=REAL_RUNS[ticker])
    after = path.read_bytes()
    assert before == after, f"{ticker}'s alpha_matches.json must remain byte-identical"


@pytest.mark.parametrize("ticker", list(REAL_RUNS))
def test_l_diagnostics_do_not_mutate_structure_graph_artifact(ticker):
    run_dir = _real_run_dir(ticker)
    path = run_dir / "structure_graph.json"
    before = path.read_bytes()
    compute_provider_health_diagnostics(run_dir=run_dir, ticker=ticker, run_id=REAL_RUNS[ticker])
    after = path.read_bytes()
    assert before == after, f"{ticker}'s structure_graph.json must remain byte-identical"


def test_l_diagnostics_module_never_imports_scoring_or_mapping_modules():
    """Diagnostics must be purely observational -- it must not import (and
    therefore cannot invoke) any Alpha-mapping, activation-scoring, or
    structure-extraction production module."""
    import comqutor_alpha.regression.provider_health_diagnostics as diag_module

    banned_substrings = ("alpha_mapper", "activation_scorer", "structure_extractor", "graph_builder")
    with open(diag_module.__file__) as f:
        source = f.read()
    for banned in banned_substrings:
        assert f"import {banned}" not in source and f"from comqutor_alpha.structure_engine.{banned}" not in source and f"from comqutor_alpha.graph_engine.{banned}" not in source


# ---------------------------------------------------------------------------
# M. P0/P1 remains unchanged (import-level smoke check; full suite run separately)
# ---------------------------------------------------------------------------


def test_m_p0_p1_module_untouched_by_this_feature():
    """Import-level check that this new diagnostics module has no coupling
    to the P0/P1 evidence-ownership module at all."""
    import comqutor_alpha.regression.provider_health_diagnostics as diag_module

    with open(diag_module.__file__) as f:
        source = f.read()
    assert "issuer_aliases" not in source
    assert "_foreign_issuer_only_reason" not in source
