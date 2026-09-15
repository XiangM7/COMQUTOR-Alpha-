# v0.1.3 Multi-Run Reproducibility

Measurement/observability implementation. **Provider calls: 0. TradingAgents calls: 0. Ticker runs: 0.** HEAD unchanged (`9f228723fad5406c72e62beca67ec70ea0fdb004`). No commit. No push. Official six-ticker Alpha Hit remains **61.0317%**, unchanged. New TSM run not promoted.

## Executive Summary

```
Multi-run evaluator implemented:   YES
TSM runs evaluated:                2
TSM old Gold Hit:                  83.33% (5/6)
TSM new Gold Hit:                  66.67% (4/6)
TSM two-run mean:                  75.00%
Variable Gold Alphas:              A103, A201, A301
Gold-set Jaccard:                  0.50
Three-run evaluator ready:         YES (not authorizing any run)
Alpha semantics changed:           NO
Official six-ticker Alpha Hit:     61.0317% (unchanged)
```

## What Was Built

A single new, purely observational module: `comqutor_alpha/regression/multi_run_reproducibility.py`, plus `tests/test_multi_run_reproducibility.py` (28 tests). Zero existing production files modified.

**Design (task section 5)**: ACCURACY ("did the run detect the expected Gold Alpha?") and REPRODUCIBILITY ("how consistently did repeated runs detect that Alpha?") are computed and reported as two permanently separate families of numbers — `gold_hit_rate`/`mean_gold_hit_rate` (accuracy) are never combined with `detection_frequency`/Jaccard/flip metrics (reproducibility) into one opaque score.

**Official detection authority reused, not reimplemented (task section 6)**: `_DETECTED_LEVELS` and `_detected_alphas()` are imported directly from `comqutor_alpha.regression.regression_report_v3` — only `active`/`dominant`/`regime_level` count as detected; `candidate` (including the distinct `capped_active` level) never does. A test (`test_reuses_canonical_detected_levels_constant_not_a_local_copy`) asserts object identity with the source module's constant, not a local copy.

**Gold expectation reused, not reinvented**: `gold_alpha_ids_for_ticker()` reads the frozen `docs/audit_artifacts/alpha_conflict_gold_benchmark_v1.json` directly — the same six-ticker Gold list already governing the official 61.0317% result.

## Architecture

- `evaluate_run()` — pure function over an already-loaded `run_audit.json` dict plus optional already-computed Provider Health / Recorder Health dicts for the same run. Computes per-run accuracy metrics (section 7).
- `evaluate_run_from_disk()` — thin I/O wrapper that loads `run_audit.json` and, if not supplied, the ticker's Gold list. Provider/recorder health are still the caller's responsibility to compute.
- `aggregate_alpha_across_runs()` — per-alpha detection sequence, frequency, transition count, and (for exactly 2 runs) `STABLE_HIT`/`STABLE_MISS`/`HIT_TO_MISS`/`MISS_TO_HIT` classification (section 8/11). No binary stable/unstable threshold is invented for 3+ runs — only `transition_count`/`detection_frequency` are reported.
- `aggregate_ticker_across_runs()` — full per-ticker record: accuracy family (`mean`/`min`/`max_gold_hit_rate`), reproducibility family (Jaccard, flip counts, per-alpha frequency), and quality visibility (`runs_provider_degraded`, `runs_benchmark_review_required`, `quality_flags_by_run` — **no run is ever silently excluded**, `run_filtering_policy = "REPORT_ALL_RUNS"`).
- `pairwise_jaccards()` — generic over N runs; for N>2 it exposes every pair (`pairwise_values`) plus `mean`/`min`/`max`, never hiding dispersion behind only the mean. Both-empty sets are defined to return `1.0` (documented, not a division-by-zero guess).
- `aggregate_global_macro()` — macro-averages ticker-level means, giving every ticker equal weight regardless of how many runs it has accumulated (section 14) — never a micro-average pooling every run-row together.
- `planned_acceptance_diagnostic()` — an isolated, non-gating helper reporting whether a given macro rate would meet the documented 0.75 `PLANNED_ACCEPTANCE_TARGET`. It is never called by any other function in this module and never gates a PASS/FAIL result (`gate_status = "NOT_ACTIVE_GATE"`).

## TSM Two-Run Regression Fixture

| | Old (`dfc7ceb3`) | New (`0aeea938`) |
|---|---:|---:|
| Gold Hit | 5/6 = 83.3333% | 4/6 = 66.6667% |
| Detected Gold | A101, A103, A201, A304, A601 | A101, A301, A304, A601 |

**Two-run mean Gold Hit: 75.00%.** Per-alpha detection frequency: A101=1.0, A103=0.5, A201=0.5, A301=0.5, A304=1.0, A601=1.0. Variable Gold Alphas: **A103, A201, A301** (flip count = 3). Gold-set Jaccard (and, coincidentally, all-Alpha-set Jaccard, since no non-Gold alpha changed detected status): **0.50**.

All values above were independently recomputed by the evaluator from the persisted `run_audit.json` files for both runs and match the task spec's expected fixture exactly (see `tests/test_multi_run_reproducibility.py::TestTSMTwoRunRegressionFixture`).

**Interpretation — do not misread this**: this is labeled `TSM_TWO_RUN_REPRODUCIBILITY_DIAGNOSTIC`, not a new official benchmark result. It does not mean "TSM performance = 75%." The official six-ticker Alpha Hit remains **61.0317%**, and the frozen ledger is untouched.

## Multi-Ticker / Global Macro

Currently only TSM has 2 runs; no other ticker has more than 1 persisted run, so `aggregate_global_macro({"TSM": ...})` trivially reduces to TSM's own mean (75.0%) — **not fabricated as a six-ticker result**. The equal-per-ticker weighting policy (`EQUAL_PER_TICKER_REGARDLESS_OF_RUN_COUNT`) is verified by a dedicated test proving that a 3-run ticker and a 2-run ticker each contribute one, equally-weighted mean to the macro average, never 3 and 2 individually-weighted rows.

## Run Quality Visibility (Section 15)

Both TSM runs are `PROVIDER_DEGRADED` and `benchmark_review_required=True` — **neither is silently excluded**. `quality_flags_by_run` carries both runs' Provider Health, benchmark-review, impacted-alpha, and Recorder Health flags side by side, exactly as computed by the independent Provider Health and Recorder Health modules.

## Three-Run Benchmark Evaluator Readiness

**`THREE_RUN_BENCHMARK_EVALUATOR_READY: YES`.** Every aggregation function (`aggregate_alpha_across_runs`, `pairwise_jaccards`, `aggregate_ticker_across_runs`) is generic over run count and is tested for N=1, 2, and 3. No code change is required to evaluate 6 tickers × 3 runs once the persisted `run_audit.json` inputs exist. **This does not authorize any future run** — it is a technical-readiness statement only.

## Future Acceptance Formula (Documented, Not Enforced)

```
ticker_mean_gold_hit = mean(run-level Gold hit rates for that ticker)
multi_run_macro_gold_hit = mean(ticker_mean_gold_hit across tickers)

PLANNED_ACCEPTANCE_TARGET: 0.75
NOT_ACTIVE_GATE
```

No automatic PASS/FAIL threshold is implemented or wired into any production path in this task.

## Tests

`tests/test_multi_run_reproducibility.py`: **28 passed** — covering one-run evaluation (A), the real TSM two-run fixture (B), detection frequency (C), all four flip classifications (D-G), pairwise Gold/all-Alpha Jaccard including 3-run dispersion (H/I/J), variable-run-count ticker weighting (K), macro- vs micro-averaging (L), null-score handling (M), the full canonical-level authority reuse matrix including `capped_active` (N/O/P/Q), and Provider-degraded-run visibility (R).

---

## Final Validation

Gold v1 SHA256 `99b1cd0247637054de360c3b5c0c00c7d8052152f3db1d29045eae1850bd8e9a` unchanged. Gold Validity SHA256 `3643ea45168c029d7c2a2ceb6d1d61cac3d5de80770d3dccb1f57d005c0c1cdf` unchanged. Old TSM authoritative run/ledger unchanged. Official six-ticker Alpha Hit (61.0317%) unchanged. No production Alpha semantic file modified. No B1/B2/B4 change. No detection-authority reimplementation. **Provider calls: 0. TradingAgents calls: 0. Ticker runs: 0. Commits: 0. Pushes: 0. Destructive git operations: 0.**
