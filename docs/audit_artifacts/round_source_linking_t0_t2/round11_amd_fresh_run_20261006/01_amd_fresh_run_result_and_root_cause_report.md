# AMD Fresh Run (Round 11, 2026-10-06) — Result and Root-Cause Report

Single, authorized, real AMD Fresh Run against the current uncommitted
workspace code, through the real production entry point
(`POST /api/research` → background job → `run_research_request`), isolated
test database. Per this round's own stop boundary: **one run only, no
re-run, no prompt/threshold adjustment based on the result.** This report
covers that one run's real result, the real first blocking point found in
it, and the real fix applied and tested afterward (offline, zero additional
Provider cost) — not a second attempt.

## 0. Headline result

The run reached a **terminal `partial` status after 316 real seconds**,
having completed TradingAgents' full real research pipeline (market/news/
fundamentals analysts, bull/bear debate, trading plan, risk review — all
real, all real DeepSeek calls) but **crashing inside Week2's structured-
claim-extraction stage before a single structured claim record was
persisted**. Every downstream stage this run was meant to exercise —
content-support verification v2.1, Alpha classification, Evidence Fact,
Activation/Exposure, Conflict — **never ran at all**, not because of a
material or semantic-judgment gap, but because of a real, now-identified-
and-fixed **wiring/concurrency defect**: enabling this round's own new
request/response audit flag
(`COMQUTOR_WEEK2_LLM_ENABLE_REQUEST_AUDIT=1`) together with
`adapt_run_outputs`'s own pre-existing concurrent multi-agent dispatch
caused the shared `Week2LLMGateway` to raise
`WEEK2_LLM_AUDIT_CONCURRENT_ATTEMPT` the moment two agents' LLM calls
overlapped.

This is the **first actual blocking point**, and it is a **call-
incompletion / wiring cause**, not a material, semantic-judgment,
eligibility-rule, direction, structure, or Exposure cause — stated plainly
per this round's own requirement to never write "insufficient evidence" or
"by design" in its place.

The bug is fixed and regression-tested (see §8). The already-run instance
of this bug is **not** re-executed — per this round's explicit stop
boundary, no second Fresh Run was launched to confirm the fix against a
live AMD result.

## 1. Run identity, time, code/task identity, database target, effective config

| Field | Value |
|---|---|
| `run_id` | `91d7c420-6197-46c3-93f9-bd42792c1ff7` |
| Ticker | AMD |
| Analysis date | 2026-10-06 (resolved trading session: 2026-10-05, since 2026-10-06 has no session — `ANALYSIS_DATE_NON_TRADING_DAY`, info-level, not an error) |
| Selected analysts | market, news, fundamentals (sentiment intentionally excluded, per authorization) |
| Submitted | 2026-10-06T05:27:00.916318+00:00 (`created_at`) |
| Started | 2026-10-06T05:27:03.399789+00:00 |
| Completed (partial) | 2026-10-06T05:32:19.654315+00:00 (316s elapsed) |
| Research Profile | `comqutor_deepseek_default_v1` ("DeepSeek Default Research") |
| Code identity | HEAD `7a9aefa5c7b5c820515447c6289aeef80eac9bdc`, uncommitted working tree — full file-hash/version manifest in `00_code_snapshot_identity.md` (written before this run) |
| Database target | `comqutor_alpha_test` (isolated), confirmed both via env capture at launch and by direct query against the real database after the run (see §7) |
| `cache_disposition` on submit | `created` — confirmed genuinely new, not a reused historical result |

Effective config actually in force (confirmed by the real pre-launch
environment capture in `00_code_snapshot_identity.md`, not assumed):
Research Agent layer — `comqutor_deepseek_default_v1` profile (deepseek /
deepseek-v4-flash for both quick and deep think / 1 debate round / 1 risk
round / temperature 0.0), `COMQUTOR_RESEARCH_AGENT_MAX_ACTUAL_REQUESTS=150`,
`COMQUTOR_RESEARCH_AGENT_MAX_RETRIES=0`. Week2 layer —
`deepseek`/`deepseek-v4-flash`, `COMQUTOR_WEEK2_LLM_MAX_CALLS=1500`,
`COMQUTOR_WEEK2_LLM_MAX_RETRIES=0`,
`COMQUTOR_WEEK2_CONTENT_SUPPORT_BATCH_SIZE=1`,
`COMQUTOR_WEEK2_CONTENT_SUPPORT_MAX_TOKENS=16384`,
`COMQUTOR_WEEK2_LLM_ENABLE_REQUEST_AUDIT=1`, 45s per-call timeout (`.env`'s
own value, confirmed/frozen, not changed).

## 2. Both layers' real request counts, usage, timeouts, truncations, budget rejections

### Research Agent (TradingAgents) layer — completed its real work in full

From this run's own `tradingagents_llm_usage_summary.json` /
`tradingagents_llm_calls.jsonl` (17 real call records, read directly, not
estimated):

| Metric | Value |
|---|---|
| Actual real requests | **17** (budget cap was 150 — 11% utilized, no rejection) |
| Successes | 17 / Failures | 0 / Retries | 0 |
| Total cost | **$0.054276** (real, non-null — the pricing-table fix noted in this session's own memory, disambiguating DeepSeek models by model name rather than LangChain's own misreported `provider=openai` field, is confirmed active: `cost_basis_notes` shows `deepseek:deepseek-v4-flash:...` pricing was actually applied) |
| Tokens | 217,446 input / 36,101 output / 253,547 total, all known (0 missing-usage) |
| Stages observed (from live progress polling) | market_analysis → news_analysis → fundamentals_analysis → research_debate → trading_plan → risk_review, each completing in turn |

This layer is a complete, clean, real success — 17 well under the 150 cap,
zero retries, zero failures, real cost and token accounting all present.
**This is the "engineering mechanism works" proof for the Research Agent
layer specifically** — it is not, by itself, proof that AMD now has any new
active Alpha (see §4).

### Week2 semantic layer — only 3 real attempts were ever made, all before the crash

| Metric | Value |
|---|---|
| Real provider request-audit records written | 3 (`attempt_id` `:1`, `:4`, `:5`, task `claim_batch_enrichment`) |
| Real provider response-audit records written | 1 (only `:5` got a response; `:1` and `:4` timed out before any response arrived) |
| `llm_semantic_calls.jsonl` (successful, validated calls) | **0** — not one Week2 call this run ever produced a validated, usable result |
| `week2_llm_errors.jsonl` | 3 entries: `WEEK2_LLM_TIMEOUT` (×2, each at the configured 45s), `WEEK2_LLM_VALIDATION_FAILED` (×1, the one attempt that did get a response) |
| `COMQUTOR_WEEK2_LLM_MAX_CALLS` budget (1500) | Never approached — the run stopped at 3 attempts, not because of budget exhaustion |
| Content-support verification | **Never reached** — it runs only after claim extraction/batch-enrichment completes, which this run's crash prevented |

Per this round's own recording rule, these 3 outcomes are recorded exactly
as what they are — two timeouts ("no valid judgment this time", never
converted to NONE or SUPPORTS) and one validation failure — never folded
into a content-support or eligibility statistic, since content-support
verification never ran.

### The actual blocking event

```
week3 pipeline stage failed (run_id=91d7c420-6197-46c3-93f9-bd42792c1ff7, stage=structure_graph_inputs)
semantic runtime degraded (run_id=91d7c420-6197-46c3-93f9-bd42792c1ff7, reason_code=SEMANTIC_RUNTIME_UNRESOLVED_CALLS, exc_type=None)
```

and, in this run's own `error_logs/week2_pipeline_errors.jsonl`:

```json
{"run_id": "91d7c420-6197-46c3-93f9-bd42792c1ff7", "stage": "structured_agent_outputs", "error_code": "WEEK2_ARTIFACT_GENERATION_FAILED", "created_at": "2026-10-06T05:32:19Z"}
```

`routes_research.py`'s own `_run_week1_week2_artifact_pipeline` never logs
the real exception type/message/traceback at this catch site (by design,
to avoid leaking a raw exception that could echo an env value) — so the
real root cause was **not visible from the run's own logs alone** and had
to be reproduced offline (see §8).

## 3. New material capture and citation stats

Real materials genuinely captured by this run's own tools (not reused from
any prior run):

- **11 real agent outputs** (`raw_agent_outputs.json`): market_agent
  (20,093 chars), news_agent (15,813 chars), fundamental_agent (15,554
  chars), bull_researcher (9,466 chars), bear_researcher (12,098 chars),
  plus trading-plan/risk-review/debate-summary outputs.
- **35 real sources** persisted to `source_registry.json` for this run.
- **0 structured claim records** (`structured_output_count: 0`, confirmed
  via the real API) — the crash in §2/§8 happened during the very first
  pass over these 11 raw outputs, before any could be converted into a
  structured, citable claim record.

Because structured-claim extraction never completed, **source-linkage
success and content-support establishment cannot be reported separately
for this run** — both are zero, for the same single upstream reason, not
two independent findings. This is stated explicitly so it is never
misread as "materials were insufficient" (a different, false conclusion):
the 11 raw outputs and 35 sources are real and present on disk; they were
simply never processed past the first stage.

## 4. Per-Alpha funnel

| Stage | Result |
|---|---|
| Structured claims extracted | 0 |
| Source-linked | 0 (N/A — no claims to link) |
| Content-support verified | 0 (never reached) |
| Claim-quality eligible | 0 (never reached) |
| Independent Evidence Facts | 0 (`alpha_matches: false` in the real API response) |
| Stance/direction assigned | 0 |
| Exposure before/after score | N/A — `entity_alpha_exposure_status: "unavailable"` |
| Activation level | N/A — `structure_graph_status: "not_ready"` |
| Active / dominant Alpha | **None** — `dominant_alphas: []`, confirmed via the real API, not inferred |

Every row above is zero for the **same single reason** (the §8 crash
during claim extraction), not five independent negative findings — stated
once here rather than repeated five times with different-sounding
rationales.

## 5. Per-Conflict funnel

| Stage | Result |
|---|---|
| Both-side direction present | N/A — no claims exist |
| Independent qualified evidence | N/A |
| Score/structure conditions | N/A |
| Admissibility evaluation ran | **No** — `conflict_status: "not_ready"`, `main_conflict: null`, confirmed via the real API |
| Admitted / rejection reason | N/A — never reached the admissibility gate at all |

## 6. Real snippets / data locations / computation inputs behind key conclusions

Since no claim reached content-support verification or Alpha matching,
there are no "key conclusions" this run itself produced to trace. The only
real, concrete artifacts this run produced are the raw material captures
themselves:

- `outputs/runs/91d7c420-6197-46c3-93f9-bd42792c1ff7/raw_agent_outputs.json`
  — 11 real agent outputs, real text, real lengths (see §3).
- `outputs/runs/91d7c420-6197-46c3-93f9-bd42792c1ff7/source_registry.json`
  — 35 real sources.
- `outputs/runs/91d7c420-6197-46c3-93f9-bd42792c1ff7/market_data_snapshot.json`
  and `data_sanity.json` — real market-data capture, passed data-sanity
  (`data_sanity_status: "ok"`, 0 warnings beyond the expected non-trading-
  day info note, 0 critical).
- `tradingagents_llm_calls.jsonl` — 17 real, itemized Research Agent calls
  with real latency/token/cost per call.

## 7. API / Export consistency and historical-file-hash confirmation

- **Real API** (`GET /api/research/{run_id}`): `status: "partial"`,
  `structured_output_count: 0`, `artifacts.alpha_matches: false`,
  `dominant_alphas: []`, `main_conflict: null`, `conflict_status:
  "not_ready"` — read live, through the real route, not from a JSON-read
  shortcut.
- **Real Export** (`GET /api/research/{run_id}/export`, the real
  `get_run_export_bundle` route): **HTTP 409, `error_code:
  "EXPORT_NOT_READY"`** — the export path correctly refuses to produce a
  bundle for a partial run rather than silently emitting an incomplete or
  misleading ZIP. This is consistent, correct behavior, not a bug.
- **Real database** (`comqutor_alpha_test`, queried directly, not inferred
  from files): `research_runs` and `research_run_progress` each hold
  exactly 1 row for this `run_id`, with `status='partial'` — matching the
  file-based and API-based status exactly. `agent_outputs`,
  `alpha_matches`, `alpha_activations`, `alpha_conflicts`,
  `entity_alpha_exposures`, and `structure_graphs` all hold **zero** rows
  for this `run_id` — directly confirming, at the database level, that
  nothing downstream of basic run tracking was ever persisted.
- **Historical AMD 34-item artifacts** (`docs/audit_artifacts/
  round_source_linking_t0_t2/round4_amd_34_item_reverification_20261004/`):
  confirmed untouched (no file in that directory has a newer mtime than
  round 10's own report) — this run is supplementary, current-process
  testing only, and does not alter or replace the original 34-item
  historical acceptance record, per this round's own boundary.
- No commit was made. No existing historical run directory was modified.

## 8. Root cause and fix (offline, zero additional real cost, not a re-run)

### Reproduction

The real exception was invisible in production logs by design (§2), so it
was reproduced offline against this exact run's own real
`raw_agent_outputs.json` (11 outputs) and `source_registry.json` (35
sources), with a fake, always-slow model standing in for the Provider
boundary (zero real network calls) and a real `Week2LLMGateway` +
`SemanticRuntimeSession` configured identically to production
(`enable_request_response_audit=True`, `max_retries=0`):

```
RuntimeError: WEEK2_LLM_AUDIT_CONCURRENT_ATTEMPT: a previous audit-enabled
attempt is still pending on this Gateway instance -- enable_request_
response_audit=True requires strictly sequential calls through this
Gateway, never concurrent ones
```

### Real root cause

`comqutor_alpha/structure_engine/structured_output_adapter.py`'s
`adapt_run_outputs` dispatches multiple raw agent outputs onto a
`ThreadPoolExecutor` (`_adapt_run_outputs_concurrently`) whenever
`concurrency > 1` and more than one agent output exists — the real
production default for this run (11 agent outputs). Every concurrent
worker shares the **same** `Week2LLMGateway` instance. That gateway's own
request/response audit mode (`enable_request_response_audit=True`, this
round's own new wiring, see `00_code_snapshot_identity.md`) tracks at most
one pending attempt at a time by design — a precondition the gateway's own
code already documented, but which nothing in `adapt_run_outputs` enforced
before calling into it. The moment two agents' `claim_batch_enrichment`
calls overlapped (expected under real network latency — the real run's
news_agent and fundamentals_agent calls were only ~1 second apart per the
progress log), the second one found a pending attempt already in flight and
raised, which propagated up through `_adapt_run_outputs_concurrently`'s
`future.result()`, through `save_structured_agent_outputs`, and was caught
only by `_run_week1_week2_artifact_pipeline`'s outer
`except Exception: _log_pipeline_error(...); return` — stopping the entire
Week1/Week2 pipeline for this run.

This is a genuine, real, reproduced **wiring defect**: two independently
reasonable pieces of code (per-agent concurrency for throughput; strictly-
sequential audit tracking for correct request/response pairing) had never
previously been exercised together in a real run, because the audit flag
had never been turned on for a real run with real multi-agent concurrency
before this round.

### Fix (minimal, targeted, no semantic/scoring change)

`adapt_run_outputs` now forces `concurrency = 1` whenever the gateway's own
`_audit_enabled` flag is true — making this call site honor a precondition
the gateway already declared, rather than changing the audit mechanism's
own pending-attempt tracking or its correctness guarantees. No prompt,
schema, eligibility rule, scoring threshold, or taxonomy was touched.

```python
if getattr(llm_gateway, "_audit_enabled", False):
    concurrency = 1
```

### Verification (offline, zero real cost)

1. **New regression test** (`tests/test_structured_output_adapter.py::
   test_audit_enabled_gateway_forces_sequential_processing_no_crash`): a
   real `Week2LLMGateway` + `SemanticRuntimeSession` with audit enabled, 3
   synthetic agent outputs, `concurrency=4` explicitly requested — confirms
   the fix overrides it to sequential and all 3 agents' calls still happen
   (no silent drop), with zero crash. **Passing.**
2. **Direct re-reproduction against this exact run's own real captured
   materials** (same fake always-times-out model, same `raw_agent_outputs.
   json`/`source_registry.json` from `91d7c420-...`): before the fix, this
   raised `WEEK2_LLM_AUDIT_CONCURRENT_ATTEMPT` as shown above; after the
   fix, it completes successfully and returns all 877 structured records
   (the same count the Legacy deterministic path alone already produced
   with `llm_gateway=None` in an earlier, separate zero-cost check this
   round) — confirming the fix doesn't just avoid the crash but lets
   processing actually complete end to end for this run's real data.
3. **Full regression run**: `tests/test_structured_output_adapter.py` — 50
   passed, 0 failed, 0 regressions on any pre-existing test.

### A separate, non-blocking, pre-existing observation (not fixed this round)

During both the real run and the offline reproduction, a second, distinct
log line appeared: `semantic runtime degraded (reason_code=
SEMANTIC_RUNTIME_UNRESOLVED_CALLS` in the real run;
`SEMANTIC_RUNTIME_CALL_START_FAILED` in the offline reproduction, both
`exc_type` either `None` or `ValueError`). `SemanticRuntimeSession`'s own
docstring states this class of failure is "contained" and "never changes
or replaces the caller's business result" — consistent with what was
observed: the offline reproduction's business result (877 records) was
correct despite these warnings. This appears related to how the semantic-
call recorder's own start/finish bookkeeping behaves when many calls fail
or time out in sequence. It was not investigated further or fixed this
round — doing so was out of this round's scope (observability-only,
non-blocking, pre-existing, unrelated to this round's own new wiring) and
risked exactly the kind of scope creep this round's authorization excluded.
It is named here so it is not silently lost, and so a future round can
decide whether it is worth a dedicated investigation.

## 9. What this run does and does not prove

- **Proves**: the Research Agent layer's real budget guard, profile
  system, cost-basis fix, and database isolation all work correctly under
  a real, full 3-analyst AMD run (17 real calls, $0.054, 0 retries, 0
  failures, correct isolated-DB writes). Proves the export endpoint
  correctly refuses a partial run rather than fabricating a bundle. Proves
  a real, previously-latent concurrency defect in this round's own new
  audit wiring, now fixed and regression-tested.
- **Does not prove**: anything about AMD's own Alpha/Conflict/Exposure
  state under the v2.1 content-support contract — no claim from this run
  ever reached that stage. The original AMD 34-item historical record
  remains the only acceptance-relevant AMD evidence; this run is
  supplementary infrastructure testing only, exactly as scoped.
- **Per this round's stop boundary**: this fix is not re-validated against
  a second live AMD run. No new Fresh Run follows this report. T1 /
  John's overall acceptance status is unchanged and is not addressed by
  this report.
