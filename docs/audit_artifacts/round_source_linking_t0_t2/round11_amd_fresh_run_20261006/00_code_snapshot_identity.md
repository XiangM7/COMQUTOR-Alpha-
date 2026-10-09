# AMD Fresh Run (Round 11) — Code Snapshot Identity

Captured 2026-10-06, before any real Provider call for this run. This file
is the pre-launch identity record required by Part 三/点 1 of this round's
authorization. It is a record only — no code changes are made here.

## Git identity

- HEAD: `7a9aefa5c7b5c820515447c6289aeef80eac9bdc` (unchanged since this
  session started; `git log` shows no new commits).
- Working tree: 307 modified/untracked paths (`git status --porcelain | wc -l`),
  all pre-existing from this session's earlier, uncommitted rounds plus this
  round's own two edits (`scripts/start_live_comqutor.sh`,
  `tests/test_live_launcher_database_isolation.py`).
- No commit is made as part of this run, per this round's own stop boundary.

## Key file SHA-256 (working-tree content, not git blob hashes)

| File | SHA-256 |
|---|---|
| `comqutor_alpha/structure_engine/content_support_llm.py` | `5ce3a9f74c0fb2daf4d3a6e769d147ac8ab469ded0495fa8c798a202865dba33` |
| `comqutor_alpha/structure_engine/week2_llm.py` | `508d5bbe478da98edd409a5fed4d7163c6b3d5d940c97588863262df739e9844` |
| `comqutor_alpha/structure_engine/structured_output_adapter.py` | `d451532abfdfecd2606b1bc0abf5f970df1831fdc20bc6012a8e56310d8defa9` |
| `comqutor_alpha/research_profiles.py` | `8b595f7d75636968fe78aae25b9a1bb03ec87e445ddd5284f628c0d43400abfc` |
| `comqutor_alpha/runners/tradingagents_runner.py` | `075b78cca276242297ccb24916e854eadeab9f58b5e48994e4b4bdecd215ca70` |
| `comqutor_alpha/runners/request_budget.py` | `230c395ccf1475d744cd701b07b4bc1ff288d358ca2f84f9a68ac5fc682962f4` |
| `comqutor_alpha/research_lifecycle.py` | `d4b3855b9a90618d8279d1c1be06380caab9a8a91bbd6f7da690a1716ef93bff` |
| `comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml` | `18a0dc6b5de7bbae3541272fbd66fa1172e62eed172fd86e97a72e1a40d90972` |
| `scripts/start_live_comqutor.sh` | `f0b209c816daf03ce9d6f2e920ffc145ec641cef76ca4c57e74961411380feca` |

## Prompt / schema / taxonomy / method versions

- Content-support verification contract: `LLM_METHOD_VERSION =
  "content_support.llm.v2.1"` (`content_support_llm.py:89`).
- Structured-output schema: `SCHEMA_VERSION =
  "week1a.structured_agent_outputs.v2"` (`structured_output_adapter.py:70`).
- Alpha taxonomy: `schema_version: alpha_taxonomy_v1`
  (`alpha_taxonomy_v1.yaml:1`).

## Research Profile identity (the Research Agent layer's actual config source)

**Correction to this round's own earlier working assumption**: a real,
web-submitted run's TradingAgents provider/model/debate-depth/temperature
are **not** controlled by `TRADINGAGENTS_*` environment variables at all.
`comqutor_alpha/server_execution.build_server_tradingagents_config()` calls
`comqutor_alpha.research_profiles.get_active_research_profile()`, which
returns a fixed, hardcoded `ResearchProfile` dataclass instance; its fields
unconditionally overwrite the matching `DEFAULT_CONFIG` keys
(`PROFILE_CONFIG_KEYS`), so any `TRADINGAGENTS_LLM_PROVIDER`/
`TRADINGAGENTS_DEEP_THINK_LLM`/`TRADINGAGENTS_QUICK_THINK_LLM`/
`TRADINGAGENTS_MAX_DEBATE_ROUNDS`/`TRADINGAGENTS_MAX_RISK_ROUNDS` env var set
before this run would be silently ignored on this exact path. This round
does **not** set any of those env vars — doing so would have had no effect
and would have been a misleading thing to report as "the config used."

The active profile for this run (read directly from the current code,
2026-10-06):

```
profile_id: comqutor_deepseek_default_v1
llm_provider: deepseek
quick_think_llm: deepseek-v4-flash
deep_think_llm: deepseek-v4-flash
backend_url: None
output_language: English
max_debate_rounds: 1
max_risk_discuss_rounds: 1
temperature: 0.0
deepseek_thinking: disabled
profile_identity_sha256: 4a55ec098d1510dce3ee49905f6f29bdc40f3e53e182779c755c4e74da3ad863
```

This is the exact profile the real NVDA reference run
(`034a0a60-430e-41f8-8321-03a11389707a`, `metadata.json`:
`llm_provider=deepseek`, `quick_model=deepseek-v4-flash`,
`deep_model=deepseek-v4-flash`) also used — confirming "reuse the
already-verified DeepSeek config, no model auto-switching" is satisfied by
simply not touching the profile system, not by setting matching env vars.

`max_tokens`/`max_retries` are **not** `PROFILE_CONFIG_KEYS` members, so
they still flow from `DEFAULT_CONFIG` (itself env-var-overridable via
`TRADINGAGENTS_MAX_TOKENS`/`TRADINGAGENTS_MAX_RETRIES`). This run does not
set `TRADINGAGENTS_MAX_TOKENS` (freezing it at its current default, `None` —
provider default applies, confirmed from `tradingagents/default_config.py`).
`TRADINGAGENTS_MAX_RETRIES` is moot for this run regardless of its value:
`tradingagents_runner.py` (lines 402-405) unconditionally forces
`max_retries=0` on the graph-construction config the moment
`research_agent_max_actual_requests` is set (see below), which this run
always does.

## Research Agent layer hard-budget mechanism (real, already implemented)

`comqutor_alpha/runners/request_budget.py`'s `RequestBudgetGuard` +
`wrap_chat_model_with_budget_guard` is a real, already-tested
(`tests/test_request_budget.py`), in-place `__class__`-swap guard around
TradingAgents' own `deep_thinking_llm`/`quick_thinking_llm` instances. It is
wired end-to-end through
`comqutor_alpha.research_lifecycle`'s real request-preparation path (not a
bespoke mechanism for this run): setting the server-process env vars
`COMQUTOR_RESEARCH_AGENT_MAX_ACTUAL_REQUESTS` /
`COMQUTOR_RESEARCH_AGENT_MAX_RETRIES` causes
`execution_payload["research_agent_max_actual_requests"]` /
`["research_agent_max_retries"]` to be set (`research_lifecycle.py:798-803`),
which `tradingagents_runner.py` reads to construct a `RequestBudgetGuard` and
wrap both LLM instances before the graph ever runs a real node. A
`ResearchAgentBudgetExceeded` raised from inside the wrapped model is never
caught by any TradingAgents node (confirmed in `request_budget.py`'s own
docstring, itself based on an earlier empirical check), so it propagates
uncaught — a real, hard stop, not a soft/advisory counter.

This run sets `COMQUTOR_RESEARCH_AGENT_MAX_ACTUAL_REQUESTS=150` and
`COMQUTOR_RESEARCH_AGENT_MAX_RETRIES=0`, satisfying the "Research Agent
layer ≤150 real requests, zero retries at both layers" requirement through
this real, pre-existing mechanism — no new code was needed for this part.

## Week2 layer config (effective for this run)

| Env var | Value | Purpose |
|---|---|---|
| `COMQUTOR_WEEK2_LLM_ENABLED` | `true` (forced by `start_live_comqutor.sh`) | gate |
| `COMQUTOR_WEEK2_LLM_PROVIDER` | `deepseek` (from `.env`, unchanged) | provider |
| `COMQUTOR_WEEK2_LLM_MODEL` | `deepseek-v4-flash` (from `.env`, unchanged) | model |
| `COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS` | `45` (from `.env`, unchanged — confirmed/frozen, not changed) | per-call timeout |
| `COMQUTOR_WEEK2_LLM_MAX_RETRIES` | `0` (this run's own override; `.env`'s own `1` would otherwise apply) | zero retries, Week2 layer |
| `COMQUTOR_WEEK2_LLM_MAX_CALLS` | `1500` (this run's own override; unset default is ~2478, see `week2_llm.py:150`) | shared hard call budget |
| `COMQUTOR_WEEK2_CONTENT_SUPPORT_BATCH_SIZE` | `1` (new override added this round) | one claim per content-support request |
| `COMQUTOR_WEEK2_CONTENT_SUPPORT_MAX_TOKENS` | `16384` (new override added this round) | content-support single-call output cap |
| `COMQUTOR_WEEK2_LLM_ENABLE_REQUEST_AUDIT` | `1` (new override added this round) | mounts the real request/response audit sink |

## Database target

- `.env`'s `COMQUTOR_DATABASE_URL` points at `comqutor_alpha` (production);
  `COMQUTOR_TEST_DATABASE_URL` points at `comqutor_alpha_test` — same
  Postgres instance (`127.0.0.1:5433`), different database name.
- This run forces `COMQUTOR_DATABASE_URL` to `COMQUTOR_TEST_DATABASE_URL`'s
  value and sets `COMQUTOR_REQUIRE_DATABASE_NAME=comqutor_alpha_test` in the
  launching shell, before `scripts/start_live_comqutor.sh` ever sources
  `.env` — verified end to end (not just read from code) by
  `tests/test_live_launcher_database_isolation.py`
  (`TestLiveLauncherDatabaseIsolationEndToEnd`, 2/2 passing against the real,
  unmodified script content as a real subprocess).

## Reproduced-and-fixed wiring defect (this round, before any spend)

`scripts/start_live_comqutor.sh` re-sources `.env` after inheriting the
launching shell's exports (needed so credentials/other config load), which
silently overwrote a caller's `COMQUTOR_WEEK2_LLM_MAX_RETRIES=0` back to
`.env`'s own `1` — the same bug class as the already-fixed 2026-10-02
`COMQUTOR_DATABASE_URL` incident, just for a different variable, newly
reproduced while preparing this run. Fixed by generalizing the existing
capture-before/restore-after pattern to a short list of caller-override
variables (`COMQUTOR_DATABASE_URL`, `COMQUTOR_WEEK2_LLM_MAX_RETRIES`),
written in a form compatible with this machine's actual `/bin/bash` (3.2.57,
no `declare -A` support — the first attempt at this fix used an associative
array and would have crashed the launcher; caught and corrected before this
file was written). Verified via
`tests/test_live_launcher_database_isolation.py`'s new
`TestLiveLauncherWeek2MaxRetriesIsolationEndToEnd` class (2/2 passing) and
the full file's regression run (6/6 passing, zero regressions on the
pre-existing database-isolation tests).

## Real end-to-end launcher dry run (zero cost, real production entry point)

Ran the REAL, unmodified `run_amd_fresh_run_isolated_db.sh` →
`scripts/start_live_comqutor.sh` chain as a real subprocess, with only the
final `exec comqutor-api` line swapped for an environment capture (same
sibling-file-patch technique `tests/test_live_launcher_database_isolation.py`
already uses) — so the real `.env` load, the real caller-override
preservation, and the real Python preflight (`server_execution.
is_real_tradingagents_enabled()` / `is_week2_llm_enabled()` /
`build_live_semantic_readiness()` — the exact same functions `/ready` and
`POST /api/research` use) all ran for real, with zero server start and zero
network call. Output:

```
AMD Fresh Run isolated-DB check passed: COMQUTOR_DATABASE_URL -> database 'comqutor_alpha_test'.
Research Agent budget: <=150 requests, 0 retries.
Week2 budget: <=1500 requests, 0 retries; content-support batch_size=1, max_tokens=16384.
========================================
COMQUTOR LIVE PREFLIGHT
Real TradingAgents : ✅ ON
Week2 Semantic LLM : ✅ ON
Semantic Provider  : ✅ READY
API                : 127.0.0.1:8000
========================================
```

Captured environment at the real pre-`exec comqutor-api` point confirmed
every required variable simultaneously, including that
`COMQUTOR_WEEK2_LLM_MAX_RETRIES=0` (this run's override) survived the real
`.env` re-source rather than being clobbered back to `.env`'s own `1` —
direct proof the fix above works in the real script, not only in the
isolated test:

```
COMQUTOR_DATABASE_URL=...comqutor_alpha_test
COMQUTOR_REQUIRE_DATABASE_NAME=comqutor_alpha_test
COMQUTOR_RESEARCH_AGENT_MAX_ACTUAL_REQUESTS=150
COMQUTOR_RESEARCH_AGENT_MAX_RETRIES=0
COMQUTOR_WEEK2_CONTENT_SUPPORT_BATCH_SIZE=1
COMQUTOR_WEEK2_CONTENT_SUPPORT_MAX_TOKENS=16384
COMQUTOR_WEEK2_LLM_ENABLE_REQUEST_AUDIT=1
COMQUTOR_WEEK2_LLM_MAX_CALLS=1500
COMQUTOR_WEEK2_LLM_MAX_RETRIES=0
COMQUTOR_WEEK2_LLM_MODEL=deepseek-v4-flash
COMQUTOR_WEEK2_LLM_PROVIDER=deepseek
```

Also observed: `COMQUTOR_JOB_TIMEOUT_SECONDS=7200` (the background job
manager's own 2-hour per-run timeout, from `.env`, unchanged) — noted here
since it bounds how long the real run below may run before the job manager
itself kills it, independent of either call-count budget.

## Preflight items closed by direct evidence (Part 三 checklist)

1. Code snapshot identity — this file.
2. Real API/worker code path loads current workspace code — confirmed:
   `comqutor_alpha.__file__` resolves to this working tree (not a
   site-packages copy); `comqutor-api`'s `main()` calls
   `uvicorn.run(app, host=host, port=port, reload=False)` — no reload
   watcher, no multi-worker process split; no module in
   `comqutor_alpha/` calls `load_dotenv()` at runtime (`.env` loading is
   the launcher script's job only, once, before the server process starts).
3. Isolated test database — confirmed end-to-end, see above.
4/5. `batch_size=1` + `max_tokens=16384` + zero retries reaching the real
   request before send — confirmed by composing three independently-passing
   real tests, each proving one real link in the same production call
   chain (not a single combined test): `tests/test_week2_llm.py::
   test_content_support_max_tokens_env_var_reaches_only_the_content_
   support_real_request` (env var → real serialized HTTP body, via
   `httpx.MockTransport`); `tests/test_structured_output_adapter.py::
   test_content_support_batch_size_env_var_reaches_the_real_call` (env var →
   `adapt_run_outputs` → `batch_size` kwarg on the real
   `apply_llm_content_support_verification` reference); and the pre-existing
   `tests/test_content_support_llm_phase_c_batch_size_fix.py` (real
   `Week2LLMGateway`, real 21-claim AMD fixture, `batch_size=1` → 21
   single-claim requests, `max_retries=0` → exactly one real attempt per
   claim, global `max_calls` budget genuinely stops sending). These three
   tests share the same production functions end to end (not
   reimplementations), so composing them is direct evidence for the full
   chain, not an assumption that the pieces compose.
6. Automated verification reaches scoring without human review — already
   established in this round's own prior investigation (see
   `16_fact_to_alpha_chain_investigation_and_erratum_20261006.md`):
   `comqutor_alpha.structure_engine.claim_quality.is_claim_eligible`
   returns `True` unconditionally for `quality=ANALYTICAL`, independent of
   `content_support_status` or any `HUMAN_REVIEWED` flag.
7. Request/response audit mounted, persists, blocks on failure — confirmed:
   `tests/test_week2_llm.py::test_request_audit_enabled_via_env_var_
   reaches_the_real_gateway` (env var → `gateway._audit_enabled is True`,
   via the exact `build_server_week2_llm_gateway(run_id, output_root)` call
   shape `run_research_request` actually uses — no extra keyword);
   `tests/test_phase_c_script_transport_level_fixed_response.py` (7/7
   passing) proves the real `audit_write_failed` gate blocks all further
   sends on this Gateway instance once a request/response audit record
   fails to persist. Concurrency-safety for the underlying append-only log
   was not independently stress-tested this round; it reuses the same lock
   pattern already proven for `_reserve_call()`'s own error log elsewhere in
   `week2_llm.py`, and this run's own `batch_size=1` config processes
   content-support sequentially, minimizing concurrent-write exposure for
   this specific stage.
