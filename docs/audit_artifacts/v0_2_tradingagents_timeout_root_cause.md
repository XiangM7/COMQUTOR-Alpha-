# TradingAgents 903-Second Timeout Root Cause

**Companion artifact:** `docs/audit_artifacts/v0_2_tradingagents_timeout_root_cause.json` (SHA256 `aa1842ab9a733acb114023a066200cef1cb946250d393075ea5d3227767f1323`)
**Repository:** `comqutor-structure-layer`, HEAD `9f228723fad5406c72e62beca67ec70ea0fdb004` (unchanged). No commits, no pushes.
**Success decision: `ROOT_CAUSE_NARROWED`.**

## Executive Summary

Two prior independently-authorized live QQQ runs failed at an identical ~903-second mark before ever reaching the semantic pipeline. This task added observability-only instrumentation, ran one authorized diagnostic live run, and **narrowed** the failure to the pre-semantic setup phase of `run_streaming_tradingagents_research` — specifically, execution never reaches the LangGraph stream loop (no analyst node ever runs). The leading candidate is an **unbounded** `yf.Ticker(...).info` call (instrument-identity resolution) that has no timeout anywhere in this codebase, architecturally distinct from the OHLCV price-history path already proven healthy. The exact statement was not confirmed with 100% certainty (one caveat remains — see below), so this is reported as `ROOT_CAUSE_NARROWED`, not `ROOT_CAUSE_CONFIRMED`.

## Two Failed Live Attempts

| Run | Elapsed | Exception | Semantic pipeline reached | Artifacts |
|---|---|---|---|---|
| `ac11831d-...` | 903s | ValueError | No | 0/9 |
| `9dc8f621-...` | 903s | ValueError | No | 0/9 |
| `78cdb570-...` (this task's diagnostic run) | 902s | ValueError | No | 0/9 |

Market-data readiness (`MARKET_DATA_NOT_YET_AVAILABLE`) was already disproven before the second attempt via a direct preflight of the OHLCV validator (1255 rows, PASS).

## Static Timeout Inventory

Repository-wide search for timeout/deadline patterns near 900s found **zero candidates in the 840–960s range**. Everything examined (job-manager timeout 7200s, Week2 LLM timeout 45s, vendor `REQUEST_TIMEOUT=30`, yfinance rate-limit backoff ~14s worst case, LangGraph's `recursion_limit=100` which is step-count only, not time-based) is either far larger, unrelated to this call path, or not time-bounded at all. **No local timeout constant explains the ~903s duration; no combination of local retries sums to it either.**

## Pre-Semantic Execution Tree

`POST /api/research` → `enqueue_research_request` (claim/gate, sync) → spawn worker process (`multiprocessing.spawn`) → `execute_claimed_research_run` → `run_research_request` → `run_streaming_tradingagents_research` →

1. **Build `TradingAgentsGraph`** — local, milliseconds, no network at construction.
2. **`_resolve_pending_entries(ticker)`** — resolves QQQ's one pending memory-log entry via `yf.Ticker(...).history()` + one LLM reflection call. **Evidence this completed successfully**: exactly one pending QQQ entry exists (`[2026-09-11 | QQQ | Underweight | pending]`), and the diagnostic run's log shows exactly one completed DeepSeek chat-completion at elapsed≈3.3s — consistent with this step finishing normally.
3. **`resolve_instrument_context` → `resolve_instrument_identity` → `yf.Ticker(...).info`** — **leading candidate**, see below. No timeout anywhere in this call chain.
4. **`get_past_context`** — pure local markdown read, explicitly "No LLM call" in source. Ruled out.
5. **`graph.graph.stream(...)`** (LangGraph, first analyst node) — **proven not reached**: this task's new `STREAM_LOOP_START` marker, placed immediately before this call, never fired in the diagnostic run.
6. `structured_adapter` — never reached in any attempt.

Full per-step file/function/timeout/retry table is in the JSON's `pre_semantic_execution_tree`.

## Failure Handler Analysis

The original exception is first caught at `comqutor_alpha/api/routes_research.py:2996` (`run_research_request`'s own `except Exception`). It is **not** wrapped, and `exc.__cause__`/`__context__` are never inspected there. The boundary log line (`logger.error(...)` at line ~3006) **deliberately never carries a traceback** — confirmed by a pre-existing, intentional test (`tests/test_research_input_validation.py::test_unexpected_internal_failure_is_logged_safely_at_error_level`, which pins `exc_info is None`). This task initially added `exc_info=True` there, which broke that test — a real regression, reverted. The persisted job/run state stores only `error_code=INTERNAL_ERROR` and a generic safe message; `exc_type=ValueError` was only ever visible in that one log line's `%s`-formatted type name, never a message or traceback, never in the database.

## Observability Gap

Before this task: no elapsed-time markers, no traceback, no indication of which pre-semantic step was executing at failure. After this task: a new passive `TradingAgentsDiagnosticCallback` (chain/tool/LLM/retry events with elapsed time and name only) plus `STREAM_LOOP_START`/`STREAM_CHUNK`/`STREAM_LOOP_ERROR` markers (with full traceback via `exc_info=True`, in a logger with no traceback-suppression policy). **Remaining gap, discovered by this task's own diagnostic run**: the new instrumentation starts at the stream-loop boundary, but the failure occurs *earlier* — extending instrumentation into `_resolve_pending_entries`/`resolve_instrument_context` is part of the recommended follow-up.

## Instrumentation Added

- **New file** `comqutor_alpha/runners/diagnostics.py`: `TradingAgentsDiagnosticCallback`, a passive LangChain `BaseCallbackHandler`. Logs only names/counts/elapsed time — never prompt/tool content, never credentials (tested).
- **Modified** `comqutor_alpha/runners/tradingagents_runner.py`: attaches the callback via the *existing* `callbacks` extension point already supported by `Propagator.get_graph_args()` (no signature change, so the existing `_FakePropagator` test double needed no update); wraps the stream loop with start/chunk/error logging; re-raises the exact same exception unchanged.
- **Modified** `comqutor_alpha/api/routes_research.py`: comment-only note explaining why `exc_info` was deliberately *not* added there (zero functional change).
- **Ephemeral tooling** `scripts/audit_tools/diagnostic_server_launcher.py`: configures INFO-level logging before starting the normal server — no change to `server.py` itself.

## Instrumentation Tests

`tests/test_tradingagents_diagnostic_instrumentation.py`, **12/12 pass**, covering all 10 required properties (stage start/end, exception stage, traceback retained, chained cause retained, elapsed-time metadata, no credential leakage ×2, unchanged success/failure semantics, no exception swallowing, unchanged return values), plus 2 extra (callback wiring, standalone event logging). Regression batch: **657/658 pass** across every touched/exercised test file — the 1 non-passing test is the already-established pre-existing baseline failure (`test_replay_conflict_does_not_get_run_id_mismatch`), unrelated to this task. One real regression was found and fixed during this task (the `exc_info=True` addition above) before it reached the final diff.

## Diagnostic Run

Static analysis alone could not identify the exact operation (no timeout constant found; distinguishing setup sub-steps required live timing evidence), so the one authorized diagnostic live run was performed: `run_id=78cdb570-1e35-4222-b5bf-5698a1740302`, `POST /api/research {"ticker":"QQQ","force_refresh":true}` against an isolated instrumented server (port 8002, PID 35297 — verified serving the current, instrumented worktree; original port-8000 process untouched; diagnostic server cleaned up after the task). **No second diagnostic run was launched.**

## Last Successful Stage

Pending-memory-log-entry resolution for QQQ's single pending entry — inferred from one completed DeepSeek chat-completion HTTP request at elapsed≈3.3s, before all further activity (including the new `STREAM_LOOP_START` marker) went silent for ~899 more seconds.

## Exact Failing Operation

**Not identified with full certainty.** Highest-confidence candidate: `tradingagents/agents/utils/agent_utils.py:resolve_instrument_identity`'s `yf.Ticker(normalize_symbol(ticker)).info` call — architecturally distinct from the already-proven-healthy OHLCV path, with no timeout anywhere in its call chain, and consistent with the reproducible network evidence (see below). **One caveat this candidate does not fully explain**: this function's own `except Exception: return {}` is explicitly written to fail open and never propagate an exception — so either the eventual `ValueError` surfaces from a different nearby statement, or the true stall is in a different, still-uninstrumented pre-stream-loop step (e.g., `TradingAgentsGraph.__init__`'s LLM client construction). Ruled out with confidence: the OHLCV fetch (already proven fast), `get_past_context` (no network call at all), and the LangGraph stream loop itself (proven not reached).

## Timeout Mechanism

Not a configured timeout in this codebase — no constant anywhere explains ~903s. Most likely mechanism: an **unbounded external call** eventually failing via whatever default the underlying HTTP client/OS imposes on a stalled connection, which this codebase never overrides for the suspected call. The near-identical duration across three independent attempts (902–903s, roughly 1–1.5 hours apart) indicates a deterministic mechanism, not random jitter — but the mechanism itself lives outside this codebase's own timeout configuration.

## Network Evidence

`lsof` on the actual TradingAgents worker subprocess (a `multiprocessing.spawn` child of the API server, confirmed via `ps -p <pid> -o ppid,command`) showed, during this task's diagnostic run: 2 `CLOSE_WAIT` sockets to `e1.ycpi.vip.sja.yahoo.com:443` and 1 `ESTABLISHED` connection consistent with a DeepSeek API endpoint IP. **Identical hostname pattern** was observed in the first prior failed attempt. Causality is not inferred from `CLOSE_WAIT` alone — it is offered as corroborating evidence for a Yahoo-backend-adjacent stall, consistent with (but not proof of) the `.info`/quoteSummary hypothesis.

## Root Cause Classification

**`MARKET_DATA_REQUEST_TIMEOUT`** — refined from the prior task's generic `UPSTREAM_TIMEOUT`: specifically the yfinance `.info` (instrument-identity) path, distinct from the OHLCV price-history path already proven healthy. Confidence: **HIGH** that the failure is pre-stream-loop and market-data-adjacent; **MEDIUM** on the exact statement, given the one caveat above.

## Recommended Minimal Fix

**Not implemented in this task** (per its own scope). File/function: `tradingagents/agents/utils/agent_utils.py:resolve_instrument_identity`. Wrap the `yf.Ticker(...).info` call with an explicit, bounded timeout using the same pattern already proven and tested elsewhere in this codebase (`comqutor_alpha/structure_engine/week2_llm.py:493`'s `future.result(timeout=...)` via a `ThreadPoolExecutor`) — e.g. 10–15s — and on timeout fall through to the **same** `{}` fallback this function already returns on any other exception. **Semantic risk: none** (the function's own documented contract is already "best-effort, fail-open"). **Implementation risk: low** (isolated, single-function change, reuses an existing pattern, touches nothing in Slice 1/2A/2B, Gold, taxonomy, activation, or conflict logic). **Another live run is required to validate the fix** — this task does not implement or validate it. This is explicitly **not** "increase the 900s timeout" — there is no existing timeout to increase; the fix adds a new, much shorter bound to a call that currently has none.

## John Requirement B Status

**Unchanged: `NOT_CLOSED_UPSTREAM_BLOCKED`.** Slice 1: PASS. Slice 2A: PASS. Slice 2B: PASS. No further optimization recommended. Next step: implement and validate the recommended minimal fix in a dedicated follow-up task, then retry the combined live timing validation.
