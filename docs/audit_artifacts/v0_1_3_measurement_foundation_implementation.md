# v0.1.3 Measurement Foundation

Implementation authorized, measurement/observability only. **Provider calls: 0. TradingAgents calls: 0. Ticker runs: 0.** HEAD unchanged (`9f228723fad5406c72e62beca67ec70ea0fdb004`). No commit. No push. No Alpha semantic change. Official six-ticker Alpha Hit remains **61.0317%**, unchanged. New TSM run not promoted.

## Executive Summary

```
Multi-run evaluator:                 IMPLEMENTED
Recorder Health:                     IMPLEMENTED

TSM runs evaluated:                  2
TSM old Gold Hit:                    83.33%
TSM new Gold Hit:                    66.67%
TSM two-run mean:                    75.00%
Variable Gold Alphas:                A103, A201, A301
Gold-set Jaccard:                    0.50

Recorder failures in new TSM:        247
Canonical semantic losses:           0
Recorder Health:                     DEGRADED

Provider metrics polluted by
  recorder events:                   NO
Alpha semantics changed:             NO
New regressions:                     0
Gold unchanged:                      YES
```

## John — Accuracy vs Reproducibility

```
Metric                       Result
Old TSM Gold Hit             5/6
New TSM Gold Hit             4/6
2-Run Mean                   75.0%
Stable Gold Hits             A101, A304, A601
Variable Gold                A103, A201, A301
Gold Jaccard                 0.50
Recorder Health              DEGRADED
Recorder Failures            247
Canonical Semantic Loss      0

Official six-ticker result remains:   61.0317%
Multi-run metric is diagnostic only.
No Alpha semantics changed.
```

## What Was Built

Two new, purely observational modules under the existing regression namespace:

- `comqutor_alpha/regression/multi_run_reproducibility.py` — Part A, the multi-run reproducibility evaluator (28 tests in `tests/test_multi_run_reproducibility.py`).
- `comqutor_alpha/regression/recorder_health_diagnostics.py` — Part B, recorder health diagnostics, kept entirely separate from Provider Health (18 tests in `tests/test_recorder_health_diagnostics.py`).

Zero existing production files modified. Six artifact files created (this pair plus `v0_1_3_multi_run_reproducibility.{json,md}` and `v0_1_3_recorder_health_diagnostics.{json,md}`). Full details of each module's design are in those two artifact pairs — this document is the closure summary, not a duplicate of their content.

## Design Requirements Honored

- **Accuracy and reproducibility kept separate** (task section 5): `gold_hit_rate`/`mean_gold_hit_rate` never combine with `detection_frequency`/Jaccard/flip metrics into one score.
- **Official detection authority reused** (task section 6): `_DETECTED_LEVELS`/`_detected_alphas()` imported directly from `regression_report_v3.py`, verified by object-identity test.
- **Generic over run count** (task section 4): 1/2/3+ runs all supported and tested; no code assumes exactly 3 runs.
- **Run quality never silently filtered** (task section 15): Provider-degraded/benchmark-review-required runs are reported, never excluded (`REPORT_ALL_RUNS`).
- **Equal per-ticker weighting** (task section 14): a 3-run ticker never outweighs a 1-run ticker in the global macro average — proven by test.
- **No new acceptance gate** (task section 16): `planned_acceptance_diagnostic()` is isolated, non-gating, and never called from the main evaluation path.
- **Recorder architecture untouched** (task section 24): `recorder.py` and `session.py` were read for the architectural proof only — zero lines changed.
- **Recorder source durability reported honestly** (task section 23): `EPHEMERAL_LOG_ONLY` when a log is supplied, `UNAVAILABLE` when not — no canonical run-scoped artifact for this data was found to exist, and none is fabricated.

## Tests

- **New targeted tests**: `tests/test_multi_run_reproducibility.py` + `tests/test_recorder_health_diagnostics.py` — **46 passed, 0 failed**.
- **P0/P1**: `tests/test_p0_p1_evidence_correctness_fix.py` — **26 passed, 0 failed**.
- **Provider Health**: `tests/test_provider_health_diagnostics.py` — **32 passed, 0 failed**.
- **Frozen SHA guards**: `tests/test_step11_provider_health_rerun.py` + `tests/test_step10_final_e2e_qa.py` — **73 passed, 0 failed**. (`tests/test_evidence_review_v2.py`'s 13 failures are pre-existing baseline failures unrelated to this task or to any SHA guard on `activation_scorer_v2.py` — see full-suite comparison below.)
- **Full backend suite**: **4121 passed, 21 failed, 3 errors, 47 skipped** (baseline: 4075 passed, 21 failed, 3 errors, 47 skipped). Delta = **+46 passed**, exactly the new test count. Every failed/error test name matches the accepted pre-existing baseline verbatim — none touch `multi_run_reproducibility` or `recorder_health_diagnostics`. **New regressions: 0.**

## Three-Run Benchmark Evaluator Readiness

**`THREE_RUN_BENCHMARK_EVALUATOR_READY: YES`.** All aggregation functions are generic over run count and tested for N=1, 2, 3. No code change is required to later evaluate 6 tickers × 3 runs once the persisted inputs exist. **This does not authorize any future run.**

## Future Acceptance Formula (Documented, Not Enforced)

```
ticker_mean_gold_hit = mean(run-level Gold hit rates for that ticker)
multi_run_macro_gold_hit = mean(ticker_mean_gold_hit across tickers)

Planned target: >= 75%
PLANNED_ACCEPTANCE_TARGET
NOT_ACTIVE_GATE
```

## Explicitly Not Modified

`v0_1_3_gold_validation.json`, `regression_report_v3.json`, `v0_1_3_final_fresh_six_ticker_ledger.json`, the official Alpha Hit figure, any B1/B2/B4 rule, any taxonomy definition, `recorder.py`, `session.py`, and any Provider Health field or threshold.

---

## Final Validation

Gold v1 SHA256 `99b1cd0247637054de360c3b5c0c00c7d8052152f3db1d29045eae1850bd8e9a` unchanged. Gold Validity SHA256 `3643ea45168c029d7c2a2ceb6d1d61cac3d5de80770d3dccb1f57d005c0c1cdf` unchanged. Frozen six-ticker ledger unchanged. Old TSM still authoritative; new TSM still not promoted. Official Alpha Hit still 61.0317%. P0/P1 still CLOSED. Provider Health unchanged. Recorder failures kept separate from Provider failures (test-proven). No thresholds, taxonomy, B1/B2/B4, or Alpha-Hit detection semantics changed. No production Alpha semantic files changed. **New regressions: 0. Provider calls: 0. TradingAgents calls: 0. Ticker runs: 0. Commits: 0. Pushes: 0. Destructive git operations: 0.**
