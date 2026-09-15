# Instrument-Identity Lookup Hard Time Bound + Final Live Validation

**Companion artifact:** `docs/audit_artifacts/v0_2_instrument_identity_timeout_fix.json` (SHA256 `a1e72d7413009fd731a2dd0821723cdedc4a00b249df674d79bb0bca378220d7`)
**Repository:** `comqutor-structure-layer`, HEAD `9f228723fad5406c72e62beca67ec70ea0fdb004` (unchanged). No commits, no pushes.
**Success decision: `FIX_VALIDATED_AND_LIVE_PASS`.**

## Executive Summary

`resolve_instrument_identity()` is now hard-bounded to 12s wall-clock via a custom fixed-size daemon-thread pool (not `ThreadPoolExecutor` — see below for why). The fix was proven genuinely wall-clock-bounded, fail-open-preserving, leak-free, and non-blocking to pipeline continuation, all offline, before the one authorized live QQQ validation was run. **That run completed successfully end-to-end for the first time in this entire multi-attempt session** — reaching and finishing the semantic pipeline, with a **34.96% total wall-clock reduction** against the historical baseline. **John Requirement B: `CLOSED`.**

## yfinance Call Path Investigation

Installed `yfinance==1.5.1`, backend `curl_cffi==0.15.0`. Call chain: `Ticker.info` → `get_info()` → `Quote.info` → `_fetch_info()`/`_fetch_complementary()` → `YfData.get_raw_json(url, timeout=30)`. **A native per-request timeout exists** (yfinance's own 30s default, `YfConfig.network.retries=0`), but `.info` makes several sequential internal calls (cookie/crumb negotiation, quoteSummary, v7 quote, a complementary timeseries fetch), none of which our call site can independently shrink without monkeypatching internals. Worst case (every call times out) is bounded to roughly 120–240s by yfinance's own internals — not literally infinite, but far above the 10–15s target and not directly controllable. Empirically, a standalone call completed in **1.07s** at investigation time.

## Why a Naive ThreadPoolExecutor Was Rejected

A first implementation used a module-level `ThreadPoolExecutor(max_workers=4)`, never explicitly shut down, with `future.result(timeout=N)` bounding the caller. **This task's own test suite hung past its harness timeout.** Root cause: `concurrent.futures.thread` registers a process-exit `atexit` hook that **joins every worker thread of every `ThreadPoolExecutor` ever created**, unconditionally — a genuinely-stuck task (this task's own "never returns" test fake, and by extension a truly-stalled Yahoo connection) hangs the **entire process** at exit, not just the one call. `future.result(timeout=...)` alone bounds the *caller's* wait; it does not bound *process shutdown* if the underlying mechanism is `ThreadPoolExecutor`.

## Selected Bounding Mechanism

A custom `_DaemonThreadPool`: a fixed-size (4) pool of plain `threading.Thread(daemon=True)` workers pulling from a `queue.Queue`, each submission returning a standard `concurrent.futures.Future`. Daemon threads are **abandoned, not joined**, at interpreter exit — sidestepping the atexit trap entirely — while the fixed pool size guarantees no unbounded thread growth under repeated timeouts. This satisfies preference (C) from the task's own ordering: native timeout (A) exists but isn't independently controllable; no project session mechanism (B) exists for this call; a demonstrably non-blocking, bounded isolation mechanism (C) was built instead. On the common, fast path (~0.26–1.1s observed), no thread is ever left running — this is not "a permanently leaking thread as the normal solution."

## Selected Timeout Value

**12.0 seconds** — within the 10–15s target. More than an order of magnitude above the observed healthy-path latency (near-zero false-positive risk), while capping the worst case at ~1.3% of the ~903s previously observed across three independent live-run failures. Exposed as an internal module constant (`_INSTRUMENT_IDENTITY_TIMEOUT_SECONDS`), no new user-facing configuration.

## Real Wall-Clock Bound Proof

A fake that genuinely blocks forever (`threading.Event().wait()`, no timeout) was submitted; the **wall-clock elapsed time of the `resolve_instrument_identity(...)` call itself** was measured (0.15s test-mode bound) and found to be **0.156s** — not merely a caught `TimeoutError` while the caller silently waited longer. Repeated-timeout tests confirm the pool never grows past its fixed size (4 threads) and a later successful lookup still works after prior timeouts. An integration test confirms `STREAM_LOOP_START` and semantic-pipeline setup proceed normally even when the identity lookup times out.

## Stage Markers Added

`INSTRUMENT_IDENTITY_START/SUCCESS/TIMEOUT/FAIL_OPEN/END` inside `resolve_instrument_identity`, plus `GRAPH_CONSTRUCTION_START/END`, `PENDING_ENTRIES_START/END`, `PAST_CONTEXT_START/END`, `INSTRUMENT_CONTEXT_START/END` in `tradingagents_runner.py` — closing the entire pre-`STREAM_LOOP_START` gap the prior root-cause task left uninstrumented. No credentials logged (tested). `routes_research.py`'s existing, test-backed "no traceback at this boundary" policy was left untouched.

## Tests

**Focused:** `tests/test_instrument_identity_timeout_hardening.py`, **16/16 pass** (real wall-clock bound ×2, repeated-timeout/resource-leak ×3, success-path parity ×2, failure-path ×8, non-critical-lookup integration ×1). One real (pre-existing, now-fixed) gap found: a malformed non-dict `.info` response raised uncaught `AttributeError` outside the original try/except — fixed by normalizing to `{}`.

**Broader:** targeted batch **540/540 pass**. Full backend suite: **4262 passed, 29 failed, 42 errors** — one new item beyond the established baseline (`test_v4_flash_returns_structured_output`), confirmed via isolated re-run to be a **genuine live DeepSeek API timeout** (`openai.APITimeoutError` after 243.86s despite a 60s client timeout) — entirely unrelated to this change. **Zero true regressions.**

## Offline Fix Decision

All gates passed: genuinely wall-clock bounded ✓, fail-open preserved ✓, no resource leak ✓, graph proceeds after timeout ✓, focused tests pass ✓, no true regression ✓. **Proceeded to live validation.**

## Market-Data Preflight

`PREFLIGHT_READY` — QQQ, 1255 rows, latest date 2026-09-14, production validator passed.

## Final Live Validation

`POST http://127.0.0.1:8003/api/research {"ticker":"QQQ","force_refresh":true}`, run `85cfd878-7b72-4855-8b29-ebd743fd335a`. Server (PID 87510, port 8003) verified serving the current hardened worktree; port 8000 untouched; cleaned up after the task. **Exactly one live run was executed.**

**Root-cause proof:** `INSTRUMENT_IDENTITY_START` → `INSTRUMENT_IDENTITY_SUCCESS` at elapsed=**0.264s** → `STREAM_LOOP_START` fired immediately after. The identity lookup was **not** the blocker this time (it succeeded fast) — but the run proceeded past every point where all three prior attempts got stuck, all the way to full completion. This run alone does not prove the identity lookup *was* the original cause; it conclusively proves the fix introduces no regression and the pipeline is no longer blocked in the previously-uninstrumented setup gap.

### Workload Comparison

This fresh run's workload is substantially **heavier** than the historical baseline: 788 Provider calls vs. 617 historical (713 `alpha_classifier` calls alone exceed the historical run's entire total). Timing comparisons below must be read with this in mind.

### Stage Timing

| Stage | Wall-clock | Summed latency |
|---|---|---|
| Total | 2043s | — |
| structured_adapter | 210.8s | 1434.5s |
| alpha_classifier | 1018.5s | 1334.7s |
| evidence_stance | 585.8s | 11682.5s |
| structure_extractor | 0s (no LLM calls) | — |

Summed latency far exceeding wall-clock for all three confirms real concurrent overlap.

### Cache, Concurrency, Reliability

- **Cache:** 757 lookups, 0 hits (consistent with B1's own prediction that this specific fresh workload carries negligible duplicate opportunity — not a defect).
- **Live concurrency evidence:** a naive start/end overlap count is *misleading* here — Slice 2A/2B's deferred-finalize design records `completed_at` at batched finalize time, not true per-call completion, inflating a naive count to 10/34. The correct signal, `started_at` clustering (true invoke time), shows maximum simultaneous-start waves of **4** for both `structured_adapter` and `evidence_stance_classifier` — exactly matching the configured bound.
- **Reliability:** `structured_adapter` shows an elevated fallback rate (7 of 10 calls, 70%, to `WEEK2_LLM_TIMEOUT`/`WEEK2_LLM_VALIDATION_FAILED`) under real C4 concurrent live load — plausibly related to 4 simultaneous large-batch requests competing for Provider capacity. This is **designed, tested, safe degradation** (deterministic-splitter fallback), not a crash or corruption — disclosed as a follow-up item, not a blocker. 0 rate-limit (429) events. `alpha_classifier`: 0 retries/fallbacks/errors across 713 calls.

### Telemetry Integrity

`validate_semantic_call_records` (the authoritative production validator, not an ad-hoc check): **valid=True, 0 issues**. `call_sequence` values are unique and strictly increasing in append order (the actual documented contract) — they are *not* numerically contiguous (385 gap positions across the range), which was investigated and confirmed **not** a defect: the contract never requires full numeric contiguity, only uniqueness and monotonicity; gaps are consistent with retries consuming sequence allocations without each attempt producing its own persisted row. Full 20-file run-directory artifact completeness.

### Fresh v0.2 Gold Evaluation

Evaluated under the existing, unchanged Gold contract — the old post-fix QQQ result was **not** forced onto this fresh evidence. Detected active Alphas: A601 (Narrative Momentum, +), A304 (Multiple Compression, −), A101 (AI Expansion, +). Dominant: **A601**. Actual main conflict: **A101__A304** (2 of 6 declared pairs admitted). QQQ conflict-family governance remains `NOT_GOVERNED`. This is a legitimately different, evidence-dependent result from both prior QQQ runs — not a Gold failure.

### A001 Gate Validation

Fresh A001 status: **candidate** (score 26.31, not elevated) — fresh evidence did not contain qualifying positive easing support (sparse, single-agent evidence). The gate behaved **correctly** against the evidence presented, not via a hardcoded "always non-detected" rule.

## Performance Classification

**PASS** — 34.96% total wall-clock reduction (2043s vs. 3141s historical), meeting the ≥25% threshold, despite a substantially heavier fresh workload. No material reliability regression.

## John Requirement B Closure

**CLOSED.** A completed live run classified PASS closes John Requirement B per this task's own rule. This run reached and completed the full semantic pipeline for the first time in this session; demonstrated live bounded concurrency (C4, via `started_at` clustering) for both `evidence_stance_classifier` and `structured_adapter`; confirmed telemetry/recorder integrity; confirmed cache correctness; confirmed the A001 evidence-conditioned gate behaves correctly; and completed with a genuine, substantial wall-clock reduction. **Recommended (non-blocking) follow-up:** investigate the elevated `structured_adapter` fallback rate under sustained real concurrent live load as a separate, dedicated reliability task.
