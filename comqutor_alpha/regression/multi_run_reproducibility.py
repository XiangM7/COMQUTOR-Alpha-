"""v0.1.3 Measurement Foundation, Part A: Multi-Run Reproducibility Evaluator.

Purely observational, read-only, deterministic measurement over
ALREADY-persisted per-run artifacts (``run_audit.json``'s own
``activation_summary``) and the already-frozen Gold expectation list
(``docs/audit_artifacts/alpha_conflict_gold_benchmark_v1.json``). This
module never calls a Provider, never reruns TradingAgents, never mutates a
historical run artifact, and never re-evaluates B1/B2/B4/Conflict Detector
production semantics -- it only reads already-computed per-alpha
``score``/``level`` values and aggregates them across runs.

Core design requirement (task section 5): ACCURACY ("did the run detect the
expected Gold Alpha?") and REPRODUCIBILITY ("how consistently did repeated
runs detect that Alpha?") are kept as two separate, explicit, never-combined
concepts throughout this module. Nothing here produces a single opaque
"score" that blends the two.

Official detection authority (task section 6) is REUSED, not
reimplemented, from ``comqutor_alpha.regression.regression_report_v3``:
only ``active``/``dominant``/``regime_level`` count as "detected" -- a
``candidate`` (including ``capped_active``, which is a distinct, non-active
level in ``alpha_level_classifier.py``'s own vocabulary) never counts,
matching the same rule every other v0.1.3 diagnostic module already uses.

This module does not implement or gate on any Alpha-Hit acceptance
threshold. ``planned_acceptance_diagnostic`` (section 16) is an isolated,
non-gating reporting helper only -- it has no effect on any production
PASS/FAIL result and is never called from the main evaluation path.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from statistics import mean
from typing import Any

from comqutor_alpha.regression.regression_report_v3 import _DETECTED_LEVELS, _detected_alphas

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _PACKAGE_ROOT.parent

DEFAULT_GOLD_BENCHMARK_PATH = (
    _REPO_ROOT / "docs" / "audit_artifacts" / "alpha_conflict_gold_benchmark_v1.json"
)

# Task section 16/40: documented, non-enforced future target. Never used as
# an automatic gate anywhere in this module.
PLANNED_ACCEPTANCE_TARGET = 0.75
PLANNED_ACCEPTANCE_TARGET_LABEL = "PLANNED_ACCEPTANCE_TARGET"
NOT_ACTIVE_GATE = "NOT_ACTIVE_GATE"


# ---------------------------------------------------------------------------
# Gold expectation loading (reuses the existing frozen benchmark file --
# never a second, independently-maintained Gold list).
# ---------------------------------------------------------------------------


def load_gold_benchmark(path: Path | str | None = None) -> dict[str, Any]:
    resolved = Path(path) if path is not None else DEFAULT_GOLD_BENCHMARK_PATH
    return json.loads(resolved.read_text(encoding="utf-8"))


def gold_alpha_ids_for_ticker(ticker: str, gold_benchmark: dict[str, Any] | None = None) -> list[str]:
    benchmark = gold_benchmark if gold_benchmark is not None else load_gold_benchmark()
    entries = (benchmark.get("expected_alphas") or {}).get(ticker) or []
    return sorted(e["alpha_id"] for e in entries if isinstance(e, dict) and "alpha_id" in e)


# ---------------------------------------------------------------------------
# Per-run loading / pure evaluation (section 4, 6, 7).
# ---------------------------------------------------------------------------


def load_run_audit(run_dir: str | Path) -> dict[str, Any]:
    path = Path(run_dir) / "run_audit.json"
    return json.loads(path.read_text(encoding="utf-8"))


def detected_alpha_ids_from_run_audit(run_audit: dict[str, Any] | None) -> list[str]:
    """Reuses the canonical detection rule verbatim (never reimplemented)."""
    activation_summary = (run_audit or {}).get("activation_summary")
    return _detected_alphas(activation_summary)


def per_alpha_states_from_run_audit(run_audit: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    activation_summary = (run_audit or {}).get("activation_summary") or {}
    per_alpha = activation_summary.get("per_alpha")
    return per_alpha if isinstance(per_alpha, dict) else {}


def evaluate_run(
    *,
    ticker: str,
    run_id: str | None,
    run_audit: dict[str, Any] | None,
    gold_alpha_ids: list[str],
    provider_health: dict[str, Any] | None = None,
    recorder_health: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Task section 7: the full per-run metric record. Pure function of an
    already-loaded ``run_audit`` dict plus optional already-computed Provider
    Health / Recorder Health dicts for the SAME run (never computed here --
    this module has no opinion on Provider or recorder internals)."""
    detected_all = detected_alpha_ids_from_run_audit(run_audit)
    per_alpha_states = per_alpha_states_from_run_audit(run_audit)

    gold_set = sorted(set(gold_alpha_ids))
    detected_set = set(detected_all)
    detected_gold = sorted(a for a in gold_set if a in detected_set)
    missed_gold = sorted(a for a in gold_set if a not in detected_set)

    gold_alpha_count = len(gold_set)
    detected_gold_count = len(detected_gold)
    gold_hit_rate = (detected_gold_count / gold_alpha_count) if gold_alpha_count else None

    return {
        "ticker": ticker,
        "run_id": run_id,
        "gold_alpha_count": gold_alpha_count,
        "detected_gold_count": detected_gold_count,
        "missed_gold_count": gold_alpha_count - detected_gold_count if gold_alpha_count else 0,
        "gold_hit_rate": gold_hit_rate,
        "detected_gold_alpha_ids": detected_gold,
        "missed_gold_alpha_ids": missed_gold,
        "detected_all_alpha_ids": detected_all,
        "provider_health": provider_health.get("provider_health") if provider_health else None,
        "benchmark_review_required": provider_health.get("benchmark_review_required") if provider_health else None,
        "impacted_alpha_ids": provider_health.get("impacted_alpha_ids") if provider_health else None,
        "recorder_health": recorder_health.get("recorder_health") if recorder_health else None,
        "recorder_failure_events": recorder_health.get("recorder_failure_events") if recorder_health else None,
        "per_alpha_gold_states": {
            alpha_id: per_alpha_states.get(alpha_id) for alpha_id in gold_set
        },
    }


def evaluate_run_from_disk(
    *,
    ticker: str,
    run_id: str,
    run_dir: str | Path,
    gold_alpha_ids: list[str] | None = None,
    provider_health: dict[str, Any] | None = None,
    recorder_health: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Thin I/O convenience wrapper around :func:`evaluate_run` -- loads
    ``run_audit.json`` from disk and, if ``gold_alpha_ids`` is not supplied,
    the ticker's frozen Gold expectation list. ``provider_health`` /
    ``recorder_health`` are still the CALLER's responsibility to compute
    (via ``provider_health_diagnostics`` / ``recorder_health_diagnostics``)
    and pass in -- this function does no Provider or recorder I/O itself."""
    run_audit = load_run_audit(run_dir)
    resolved_gold = gold_alpha_ids if gold_alpha_ids is not None else gold_alpha_ids_for_ticker(ticker)
    return evaluate_run(
        ticker=ticker,
        run_id=run_id,
        run_audit=run_audit,
        gold_alpha_ids=resolved_gold,
        provider_health=provider_health,
        recorder_health=recorder_health,
    )


# ---------------------------------------------------------------------------
# Detected-set stability / Jaccard (section 10).
# ---------------------------------------------------------------------------


def jaccard(set_a: set[str], set_b: set[str]) -> float:
    """J(A,B) = |A intersect B| / |A union B|. Documented both-empty
    behavior (section 10): two empty sets are treated as identical
    (maximally similar), returning 1.0, never a division by zero."""
    union = set_a | set_b
    if not union:
        return 1.0
    return len(set_a & set_b) / len(union)


def pairwise_jaccards(sets_by_run: dict[str, set[str]]) -> dict[str, Any]:
    """Section 10: for N>2 runs, expose every pairwise value plus
    mean/min/max -- dispersion is never hidden behind only the mean. For
    exactly 2 runs there is exactly one pair, so mean==min==max."""
    run_ids = sorted(sets_by_run)
    pairs = list(itertools.combinations(run_ids, 2))
    detail = []
    values: list[float] = []
    for run_a, run_b in pairs:
        value = jaccard(sets_by_run[run_a], sets_by_run[run_b])
        values.append(value)
        detail.append({"run_a": run_a, "run_b": run_b, "jaccard": value})
    return {
        "pairwise_values": detail,
        "mean_pairwise_jaccard": mean(values) if values else None,
        "min_pairwise_jaccard": min(values) if values else None,
        "max_pairwise_jaccard": max(values) if values else None,
    }


# ---------------------------------------------------------------------------
# Per-alpha multi-run aggregation / flip metrics (section 8, 11).
# ---------------------------------------------------------------------------

STABLE_HIT = "STABLE_HIT"
STABLE_MISS = "STABLE_MISS"
HIT_TO_MISS = "HIT_TO_MISS"
MISS_TO_HIT = "MISS_TO_HIT"


def aggregate_alpha_across_runs(alpha_id: str, run_evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    """Task section 8/11: one Gold Alpha's detection record across N runs of
    the SAME ticker, ordered exactly as ``run_evaluations`` was passed in
    (callers must pass runs in a stable, meaningful order -- typically
    execution order -- since ``detection_sequence``/``transition_count``
    are order-dependent by design)."""
    per_run = []
    for run_eval in run_evaluations:
        states = run_eval.get("per_alpha_gold_states") or {}
        state = states.get(alpha_id)
        per_run.append(
            {
                "run_id": run_eval.get("run_id"),
                "level": state.get("level") if isinstance(state, dict) else None,
                "score": state.get("score") if isinstance(state, dict) else None,
                "detected": alpha_id in (run_eval.get("detected_gold_alpha_ids") or []),
            }
        )

    detection_sequence = [entry["detected"] for entry in per_run]
    runs_evaluated = len(per_run)
    detected_count = sum(1 for value in detection_sequence if value)
    miss_count = runs_evaluated - detected_count
    detection_frequency = (detected_count / runs_evaluated) if runs_evaluated else None
    transition_count = sum(
        1 for i in range(1, len(detection_sequence)) if detection_sequence[i] != detection_sequence[i - 1]
    )

    two_run_flip_classification = None
    if runs_evaluated == 2:
        first, second = detection_sequence
        if first and second:
            two_run_flip_classification = STABLE_HIT
        elif not first and not second:
            two_run_flip_classification = STABLE_MISS
        elif first and not second:
            two_run_flip_classification = HIT_TO_MISS
        else:
            two_run_flip_classification = MISS_TO_HIT

    return {
        "alpha_id": alpha_id,
        "runs_evaluated": runs_evaluated,
        "detected_count": detected_count,
        "miss_count": miss_count,
        "detection_frequency": detection_frequency,
        "detection_sequence": detection_sequence,
        "transition_count": transition_count,
        "two_run_flip_classification": two_run_flip_classification,
        "per_run": per_run,
    }


# ---------------------------------------------------------------------------
# Per-ticker multi-run aggregation (section 9, 12, 15).
# ---------------------------------------------------------------------------


def aggregate_ticker_across_runs(
    *, ticker: str, run_evaluations: list[dict[str, Any]], gold_alpha_ids: list[str]
) -> dict[str, Any]:
    """Task section 9/12/15: the full per-ticker multi-run reproducibility
    record. ``mean_gold_hit_rate`` (an ACCURACY-family average) is never
    conflated with the REPRODUCIBILITY-family Jaccard/flip metrics computed
    alongside it -- both are reported, neither is derived from the other."""
    runs_evaluated = len(run_evaluations)
    per_run_gold_hit_rates = [run_eval.get("gold_hit_rate") for run_eval in run_evaluations]
    valid_rates = [rate for rate in per_run_gold_hit_rates if rate is not None]
    mean_gold_hit_rate = mean(valid_rates) if valid_rates else None
    min_gold_hit_rate = min(valid_rates) if valid_rates else None
    max_gold_hit_rate = max(valid_rates) if valid_rates else None

    gold_hit_counts = [run_eval.get("detected_gold_count") for run_eval in run_evaluations]
    valid_counts = [count for count in gold_hit_counts if count is not None]
    gold_hit_count_mean = mean(valid_counts) if valid_counts else None

    sorted_gold_alpha_ids = sorted(set(gold_alpha_ids))
    per_alpha = {
        alpha_id: aggregate_alpha_across_runs(alpha_id, run_evaluations) for alpha_id in sorted_gold_alpha_ids
    }
    per_alpha_detection_frequency = {alpha_id: agg["detection_frequency"] for alpha_id, agg in per_alpha.items()}

    stable_hit_alpha_ids = sorted(
        alpha_id for alpha_id, agg in per_alpha.items() if agg["detection_frequency"] == 1.0
    )
    stable_miss_alpha_ids = sorted(
        alpha_id for alpha_id, agg in per_alpha.items() if agg["detection_frequency"] == 0.0
    )
    variable_alpha_ids = sorted(
        alpha_id
        for alpha_id, agg in per_alpha.items()
        if agg["detection_frequency"] is not None and agg["transition_count"] > 0
    )
    gold_alpha_flip_count = len(variable_alpha_ids)

    gold_sets = {
        run_eval.get("run_id"): set(run_eval.get("detected_gold_alpha_ids") or []) for run_eval in run_evaluations
    }
    all_alpha_sets = {
        run_eval.get("run_id"): set(run_eval.get("detected_all_alpha_ids") or []) for run_eval in run_evaluations
    }
    gold_jaccard = pairwise_jaccards(gold_sets)
    all_alpha_jaccard = pairwise_jaccards(all_alpha_sets)

    runs_provider_degraded = sum(
        1 for run_eval in run_evaluations if run_eval.get("provider_health") == "PROVIDER_DEGRADED"
    )
    runs_benchmark_review_required = sum(
        1 for run_eval in run_evaluations if run_eval.get("benchmark_review_required")
    )
    quality_flags_by_run = {
        run_eval.get("run_id"): {
            "provider_health": run_eval.get("provider_health"),
            "benchmark_review_required": run_eval.get("benchmark_review_required"),
            "impacted_alpha_ids": run_eval.get("impacted_alpha_ids"),
            "recorder_health": run_eval.get("recorder_health"),
            "recorder_failure_events": run_eval.get("recorder_failure_events"),
        }
        for run_eval in run_evaluations
    }

    return {
        "ticker": ticker,
        "runs_evaluated": runs_evaluated,
        "run_ids": [run_eval.get("run_id") for run_eval in run_evaluations],
        "per_run_gold_hit_rates": per_run_gold_hit_rates,
        "mean_gold_hit_rate": mean_gold_hit_rate,
        "min_gold_hit_rate": min_gold_hit_rate,
        "max_gold_hit_rate": max_gold_hit_rate,
        "gold_hit_count_mean": gold_hit_count_mean,
        "gold_alpha_flip_count": gold_alpha_flip_count,
        "stable_hit_alpha_ids": stable_hit_alpha_ids,
        "stable_miss_alpha_ids": stable_miss_alpha_ids,
        "variable_alpha_ids": variable_alpha_ids,
        "per_alpha_detection_frequency": per_alpha_detection_frequency,
        "per_alpha": per_alpha,
        "gold_detected_set_jaccard": gold_jaccard,
        "all_alpha_detected_set_jaccard": all_alpha_jaccard,
        # Section 12 reproducibility-summary field names, reported alongside
        # (never instead of) the above -- descriptive only, no PASS/FAIL.
        "gold_alpha_detection_frequency_mean": (
            mean(v for v in per_alpha_detection_frequency.values() if v is not None)
            if any(v is not None for v in per_alpha_detection_frequency.values())
            else None
        ),
        "gold_alpha_detection_frequency_min": (
            min(v for v in per_alpha_detection_frequency.values() if v is not None)
            if any(v is not None for v in per_alpha_detection_frequency.values())
            else None
        ),
        "gold_alpha_detection_frequency_max": (
            max(v for v in per_alpha_detection_frequency.values() if v is not None)
            if any(v is not None for v in per_alpha_detection_frequency.values())
            else None
        ),
        "variable_gold_alpha_count": len(variable_alpha_ids),
        "stable_gold_hit_count": len(stable_hit_alpha_ids),
        "stable_gold_miss_count": len(stable_miss_alpha_ids),
        "mean_pairwise_gold_jaccard": gold_jaccard["mean_pairwise_jaccard"],
        "mean_pairwise_all_alpha_jaccard": all_alpha_jaccard["mean_pairwise_jaccard"],
        # Section 15: run quality visibility -- REPORT_ALL_RUNS, never a
        # silent exclusion of a degraded run.
        "runs_total": runs_evaluated,
        "runs_provider_degraded": runs_provider_degraded,
        "runs_benchmark_review_required": runs_benchmark_review_required,
        "quality_flags_by_run": quality_flags_by_run,
        "run_filtering_policy": "REPORT_ALL_RUNS",
    }


# ---------------------------------------------------------------------------
# Multi-ticker / global macro aggregation (section 13, 14).
# ---------------------------------------------------------------------------


def aggregate_global_macro(ticker_aggregates: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Task section 13/14: equal ticker-level weighting regardless of how
    many runs each ticker happened to accumulate -- a ticker with 3 runs
    never outweighs a ticker with 1 run in the global macro average. This
    is a straight mean of each ticker's OWN mean_gold_hit_rate, never a
    micro-average that pools every run-row from every ticker together."""
    ticker_ids = sorted(ticker_aggregates)
    ticker_mean_gold_hit_rate = {
        ticker: ticker_aggregates[ticker].get("mean_gold_hit_rate") for ticker in ticker_ids
    }
    valid_means = [value for value in ticker_mean_gold_hit_rate.values() if value is not None]
    multi_run_macro_gold_hit_rate = mean(valid_means) if valid_means else None

    return {
        "tickers_evaluated": ticker_ids,
        "runs_per_ticker": {ticker: ticker_aggregates[ticker].get("runs_evaluated") for ticker in ticker_ids},
        "ticker_mean_gold_hit_rate": ticker_mean_gold_hit_rate,
        "multi_run_macro_gold_hit_rate": multi_run_macro_gold_hit_rate,
        "weighting_policy": "EQUAL_PER_TICKER_REGARDLESS_OF_RUN_COUNT",
    }


def planned_acceptance_diagnostic(
    multi_run_macro_gold_hit_rate: float | None, target: float = PLANNED_ACCEPTANCE_TARGET
) -> dict[str, Any]:
    """Task section 16/40: an ISOLATED, non-gating reporting helper. Never
    called by any other function in this module and never used to gate a
    PASS/FAIL result anywhere -- it exists only so a future task can report
    "would this currently meet the planned target" as a labeled diagnostic,
    not an active acceptance rule."""
    meets_target = (
        multi_run_macro_gold_hit_rate is not None and multi_run_macro_gold_hit_rate >= target
    )
    return {
        "multi_run_macro_gold_hit_rate": multi_run_macro_gold_hit_rate,
        PLANNED_ACCEPTANCE_TARGET_LABEL: target,
        "meets_planned_target": meets_target if multi_run_macro_gold_hit_rate is not None else None,
        "gate_status": NOT_ACTIVE_GATE,
    }


__all__ = [
    "DEFAULT_GOLD_BENCHMARK_PATH",
    "PLANNED_ACCEPTANCE_TARGET",
    "PLANNED_ACCEPTANCE_TARGET_LABEL",
    "NOT_ACTIVE_GATE",
    "STABLE_HIT",
    "STABLE_MISS",
    "HIT_TO_MISS",
    "MISS_TO_HIT",
    "load_gold_benchmark",
    "gold_alpha_ids_for_ticker",
    "load_run_audit",
    "detected_alpha_ids_from_run_audit",
    "per_alpha_states_from_run_audit",
    "evaluate_run",
    "evaluate_run_from_disk",
    "jaccard",
    "pairwise_jaccards",
    "aggregate_alpha_across_runs",
    "aggregate_ticker_across_runs",
    "aggregate_global_macro",
    "planned_acceptance_diagnostic",
]
