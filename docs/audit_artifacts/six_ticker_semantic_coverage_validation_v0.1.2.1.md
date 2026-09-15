# Six-Ticker Semantic Coverage Validation — v0.1.2.1

**Scope: semantic execution coverage only.** This validates that the repaired Week2 Alpha Mapper runtime can actually render a real classifier verdict on real production claim volume. The `>= 95%` threshold used here is an **internal engineering runtime-health benchmark for this repair — it is NOT a John-approved product/release acceptance metric** and must never be represented as one. Alpha recall (whether specific expected Alphas were detected) is explicitly **not evaluated** in this task.

Branch `comqutor-structure-layer`, HEAD `9f228723fad5406c72e62beca67ec70ea0fdb004` (unchanged — no commit, no push).

## Runtime Configuration (identical across all six tickers)

| | |
|---|---|
| Semantic unit | single claim (one claim + FULL canonical Alpha taxonomy → one LLM decision) |
| Claim concurrency | 4 |
| Ticker concurrency | 1 (strictly sequential) |
| Provider | deepseek |
| Model | deepseek-v4-flash |
| Call budget | workload-aware (Step 5A) — not the old fixed 32-call budget |
| Batching | DEFERRED_FOR_V0.1.2.1 — not used |
| TradingAgents calls | 0 |
| Deterministic semantic fallback | never used |
| Ticker-specific tuning | none — same configuration for all six |

## Per-Ticker Results

| Ticker | Eligible | MATCHED | NONE | UNAVAILABLE | Coverage | Status |
|---|---|---|---|---|---|---|
| NVDA | 768 | 377 | 388 | 3 | **99.61%** | PASS |
| QQQ | 874 | 305 | 564 | 5 | **99.43%** | PASS |
| MSFT | 721 | 342 | 370 | 9 | **98.75%** | PASS |
| SNDK | 736 | 332 | 401 | 3 | **99.59%** | PASS |
| TSM | 949 | 391 | 543 | 15 | **98.42%** | PASS |
| AMD | 846 | 344 | 498 | 4 | **99.53%** | PASS |
| **Total** | **4894** | **2091** | **2764** | **39** | **99.20%** | **6/6 PASS** |

All 39 UNAVAILABLE claims across all six tickers are tagged `invalid_output` (a genuine provider/schema failure after retry) or (SNDK's retry) one `validation_failed` — **never silently converted to NONE**. `disabled`/config-caused UNAVAILABLE = 0 on every ticker.

## SNDK: one retry, honestly reported

SNDK's *first* attempt (not counted above) hit a transient real-Provider failure storm: 1,416 `WEEK2_LLM_PROVIDER_ERROR` events, only 3.8% coverage, over ~44 minutes. Before retrying, a direct standalone health-check call to DeepSeek confirmed the Provider had recovered, and TSM's own partial log (captured before an unrelated session interruption) showed a return to normal timeout-only behavior immediately after SNDK's bad window — consistent with a transient Provider-side blip, not a code or configuration defect. SNDK was retried once with the **exact same, unmodified configuration** and passed at 99.59%.

## Aggregate Provider Accounting

| | |
|---|---|
| Total timeouts | 615 |
| Total transport/provider errors | 16 |
| Total rate-limit errors | 0 |
| Total validation failures | 1 |
| Total budget exhaustions | 0 |
| Total wall-clock | ~3.89 hours (NVDA/QQQ/MSFT timings approximated from output-directory timestamps after a session interruption lost the exact timer; SNDK/TSM/AMD measured exactly: 2176.3s / 2801.7s / 2262.4s) |
| TradingAgents calls | 0 |

Exact Provider *attempt* counts (including internal retries) are not separately recoverable from the persisted error log alone without double-counting first attempts — reported honestly as `EXACT_COUNT_UNAVAILABLE_FROM_PERSISTED_ARTIFACTS`, not invented.

## Session Interruption (transparency note)

A session/harness restart occurred mid-run, after NVDA/QQQ/MSFT had already completed and while TSM was in progress. The in-flight orchestration script (and its live timing log) lived only in the ephemeral scratchpad and was lost; the actual persisted artifacts under `outputs/runs/_step5a_coverage_*/` were **not** affected and were used to recompute every number in this report directly and independently via `comqutor_alpha.regression.semantic_execution_health.compute_semantic_execution_health`. TSM's incomplete first attempt (partial error log, no `alpha_matches.json` ever written) was discarded and redone cleanly; AMD had not yet started and was run fresh.

## Files

**Created:** `docs/audit_artifacts/six_ticker_semantic_coverage_validation_v0.1.2.1.json`, this file.
**Updated (additive):** `docs/audit_artifacts/qa_closure_index.json` (`semantic_runtime_validation` block).
**Isolated validation directories (not the original Step-4 runs):** `outputs/runs/_step5a_coverage_{nvda,qqq,msft,sndk,tsm,amd}/` — each contains a copy of the source run's `structured_agent_outputs.json`/`metadata.json` plus a freshly-computed `alpha_matches.json` from this validation. The original Step-4 fresh runs (`6f4e07f9…`, `57244747…`, `ce6b9628…`, `e4309acb…`, `43660d9d…`, `eb714c04…`) are untouched.
**Not touched:** Alpha taxonomy, Alpha Mapper semantic prompt, B1/B2/B4, conflict ontology, activation thresholds, regression labels, any ticker-specific configuration.
