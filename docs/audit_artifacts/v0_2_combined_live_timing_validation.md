# Combined Live Timing Validation

**Companion artifact:** `docs/audit_artifacts/v0_2_combined_live_timing_validation.json` (SHA256 `b8dc8860401083db6c204eaa8f7c892b5cfb094778736f43d1085afc443e461c`)
**Repository:** `comqutor-structure-layer`, HEAD `9f228723fad5406c72e62beca67ec70ea0fdb004` (unchanged before/after). No commits, no pushes, 0 production/test files changed this task.

## Executive Result

**FAIL — inconclusive.** The single authorized live QQQ run failed after 903 seconds, before ever reaching the semantic pipeline (cache, `alpha_classifier`, `evidence_stance_classifier`, `structured_adapter`). The failure occurred entirely inside TradingAgents' own pre-semantic "initializing" stage (market-data acquisition / analyst debate), which none of Slice 1, 2A, or 2B touch. **This is not a regression caused by the three optimization slices** — none of their code was ever executed in this run. **John Requirement B is NOT CLOSED**, pending a successful live run.

## Exact Live Request

```
POST http://127.0.0.1:8001/api/research
Content-Type: application/json

{"ticker": "QQQ", "force_refresh": true}
```

- Request sent: `2026-09-14T18:31:52Z`. Response: `2026-09-14T18:31:53Z`, HTTP 202.
- Response body: `{"run_id":"ac11831d-7a31-4e6f-9ae8-a37bffddd4c0","ticker":"QQQ","status":"queued","run_status":"queued","stage":"accepted","cache_disposition":"force_refreshed"}`
- Exactly 1 fresh ticker run was made. No second benchmark run was attempted.

## Environment / Effective Concurrency

| Setting | Value |
|---|---|
| Cache enabled | yes, run-local |
| `alpha_classifier` concurrency | 4 |
| `evidence_stance_classifier` concurrency | 4 |
| `structured_adapter` concurrency | 4 |
| `structure_extractor` concurrency | unchanged (no concurrency mechanism exists) |
| Alpha Memory | SHADOW |
| Activation modulation | OFF |
| Env var overrides | none — all three concurrency env vars unset, defaults (4) used |

**Server restart required:** the only running `comqutor-api` process (PID 27595, port 8000) had been running since 2026-09-10, before any of Slice 1/2A/2B's code existed — serving the validation from it would have measured zero optimization effect. Killing it was denied by the environment's own safety classifier (interfering with a running workload). A **separate, freshly-started instance** (PID 99906, port 8001) was launched instead, using the exact same readiness preflight `scripts/start_live_comqutor.sh` itself uses — the pre-existing port-8000 process was never touched. Preflight passed: `REAL=1, WEEK2=1, PROVIDER=1`.

## Historical QQQ Baseline

Run `f239a53f-4ebe-455c-bb76-5f5485903901`: total ≈3141s, structured_adapter ≈595.3s, evidence_stance ≈1604.2s, semantic wall-clock ≈2937.6s, 617 Provider calls, 595 semantic records.

## Fresh QQQ Workload

- Run `ac11831d-7a31-4e6f-9ae8-a37bffddd4c0`, `analysis_date=2026-09-14` (a Monday, normal trading day).
- **Result: `failed`, `error_code=INTERNAL_ERROR`, exception type `ValueError`, after 903s**, stuck the entire time at `progress_percent=8, current_stage=initializing, completed_units=0/15`.
- No run directory was ever created (`GET /api/research/{run_id}` returns `RUN_NOT_FOUND`).

## Stage Timing Comparison

Not meaningfully computable — the run never advanced past the pre-semantic "initializing" stage, so no `structured_adapter`/`evidence_stance`/`alpha_classifier`/`structure_extractor` timing exists to compare.

## Normalized Timing Comparison

Not applicable for the same reason — zero claims, zero semantic calls, zero adapter/stance/classifier invocations occurred.

## Cache Behavior

Not observable. `InMemoryLLMResponseCache` is instantiated inside the semantic pipeline stage, which was never reached.

## Live Concurrency Evidence

Not observable — no `llm_semantic_calls.jsonl` was ever created (no run directory exists), so no in-flight/overlap measurement is possible for `evidence_stance_classifier` or `structured_adapter`.

## Retry / Timeout / Rate-Limit Behavior

- 0 HTTP 429s observed (this task's own request layer; the failure was internal to the TradingAgents worker, not an HTTP-level rate limit against COMQUTOR's own API).
- The TradingAgents worker subprocess (a `multiprocessing.spawn` child, PID 110, of the server process) showed 2 sockets in `CLOSE_WAIT` to Yahoo Finance hosts (`e1`/`e2.ycpi.vip.sja.yahoo.com`) and 1 `ESTABLISHED` HTTPS connection at the time of inspection — confirming genuine network activity (not a frozen thread), consistent with a market-data fetch that was retried/delayed before ultimately failing.
- No retry storm or fallback-increase signal is separately measurable since no semantic stage was reached.

## Recorder / Telemetry Integrity

Not applicable — `llm_semantic_calls.jsonl` and the semantic manifest were never created for this run. Artifact completeness: **0/9** (no run directory exists at all, versus the historical run's full bundle).

## Fresh v0.2 Gold Evaluation

Not applicable — no raw agent outputs, no claims, no Alpha mapping, no conflict detection occurred.

## A001 Gate Validation

Not applicable — no fresh evidence was produced to evaluate the gate against.

## Conflict Diagnostic

Not applicable — no structure/conflict detection occurred. Fresh actual main conflict: none (run failed before this stage).

## Artifact Completeness

Expected 9/9 (or current equivalent); observed **0/9** — no run directory was ever created for this run.

## Root Cause Analysis

**Method:** server log inspection (only the exception *type* was logged — `comqutor_alpha/api/routes_research.py`'s failure handler does not call with `exc_info=True`), progress-stage source tracing (`comqutor_alpha/research_lifecycle.py:853` calls `progress_reporter.record_stage("initializing")` exactly once, immediately before invoking the full pipeline — progress never advanced past this single marker for the full 903s), and live network inspection of the actual TradingAgents worker subprocess.

**Conclusion:** the failure occurred entirely within the pre-semantic "initializing" stage — inside TradingAgents' own market-data acquisition / analyst-debate layer — **before** `structured_adapter`, `alpha_classifier`, or `evidence_stance_classifier` (the three components Slice 1/2A/2B modified) ever executed. Zero semantic Provider calls, zero cache lookups, and zero concurrency-managed work of any kind occurred.

**Most likely specific cause (stated as probable, not confirmed — the exact `ValueError` message was not captured, and a second live call to confirm it is explicitly forbidden in this task):** `tradingagents/dataflows/market_data_validator.py` raises exactly this failure shape for a same-day request — `No OHLCV data available for {symbol}.` / `No OHLCV rows on or before {curr_date} for {symbol}.` Combined with the observed Yahoo Finance `CLOSE_WAIT` connections and the ~900s delay (consistent with retry/backoff before giving up), the most probable explanation is that same-day OHLCV data for QQQ was not yet available from the market-data provider at the time of this mid-session request.

**Attributable to Slice 1, 2A, or 2B:** **No.** This is a pre-existing, upstream TradingAgents/market-data condition, structurally incapable of being caused by any of the three optimization slices — none of their modified files (`comqutor_alpha/llm_runtime/cache.py`, `comqutor_alpha/structure_engine/evidence_stance_llm.py`, `comqutor_alpha/structure_engine/structured_output_adapter.py`, `comqutor_alpha/structure_engine/week2_llm.py`) were ever reached in this run's call stack. **Classification: `PRE_EXISTING_UNRELATED_INFRASTRUCTURE_FAILURE`.**

## Performance Decision

**FAIL** — per Section 18's literal thresholds, a run producing no comparable timing measurement cannot be scored STRONG_PASS/PASS/MARGINAL_PASS. This FAIL reflects an **inconclusive measurement**, not a reliability regression, concurrency defect, or telemetry corruption introduced by the three slices — none of their code was exercised.

## John Requirement B Closure Decision

**NOT CLOSED.** Per Section 19, closure requires that Slice 2A's and Slice 2B's live concurrency be observed and that live runtime materially improves — neither could be evaluated because the run failed before reaching the semantic pipeline. This is not a rejection of the three slices' offline evidence (their own artifacts remain PASS, unaffected) — it is a statement that live confirmation has not yet been obtained.

**Recommended next step:** retry ONE live QQQ combined-timing validation (same single-run authorization and scope) at a time when same-day OHLCV data is confirmed available (e.g. after US market close, or on a subsequent trading day), or first investigate/resolve the TradingAgents market-data-availability condition as a separate, unrelated task. **Do not begin another optimization slice** — Slice 1/2A/2B's offline evidence remains valid.
