# Week 0 Adversarial Audit — TradingAgents Core Baseline

Repo: `/Users/xiangmao/COMQUTOR-Alpha-`, branch `comqutor-structure-layer`, HEAD `64e657958aa1db32528d55e8b9c5520b387f86fc`.
Scope: `tradingagents/graph/{trading_graph,setup,propagation,conditional_logic}.py`, `tradingagents/agents/utils/agent_states.py`, `comqutor_alpha/runners/tradingagents_runner.py` (consumption only).

---

## 1. Contract/spec claims found in docs

| Claim | Source |
|---|---|
| "Week 0 baseline: PASS" | `docs/current_system_state.md:16` |
| "Week 0 baseline: Verified — Baseline reports and setup records" | `docs/mvp_evaluation_report.md:24` |
| "Week 0 baseline: PASS — baseline setup/report documents" | `docs/week6_final_gap_audit.md:31` |
| "Streaming execution preserves memory, context, checkpoint and post-run semantics of `propagate`" | `docs/current_system_state.md:37` |
| "Ticker and asset-type handling follows TradingAgents CLI rules" | `docs/current_system_state.md:36` |
| Report tree: `1_analysts/`, `2_research/`, `3_trading/trader.md`, `4_risk/`, `5_portfolio/decision.md` | `docs/setup_baseline.md:83-93,126-130` |
| `checkpoint_enabled` config exists to let a "crashed run... resume from the last successful node on a subsequent invocation with the same ticker+date" | `tradingagents/graph/trading_graph.py:327-329` (docstring, itself a claim to verify against code) |
| CLI exposes `--checkpoint/--no-checkpoint` "Enable/disable checkpoint-resume (save state after each node so a crashed run can resume)" | `cli/main.py:1293-1296` |

None of these docs cite a test suite as evidence for Week 0 specifically — the evidence column for "Week 0 baseline" in both `mvp_evaluation_report.md:24` and `week6_final_gap_audit.md:31` is "baseline setup/report documents," i.e. `docs/setup_baseline.md`'s manual CLI walkthrough, not automated tests.

---

## 2. Actual code behavior (file:line evidence)

### Q1 — Real fields of `final_state`

`AgentState(MessagesState)` (`tradingagents/agents/utils/agent_states.py:47-77`) declares: `messages` (inherited), `company_of_interest`, `asset_type`, `instrument_context`, `trade_date`, `sender`, `market_report`, `sentiment_report`, `news_report`, `fundamentals_report`, `investment_debate_state` (`InvestDebateState`: `bull_history`, `bear_history`, `history`, `current_response`, `judge_decision`, `count`), `investment_plan`, `trader_investment_plan`, `risk_debate_state` (`RiskDebateState`: `aggressive_history`, `conservative_history`, `neutral_history`, `history`, `latest_speaker`, `current_*_response` x3, `judge_decision`, `count`), `final_trade_decision`, `past_context`.

Initial population: `Propagator.create_initial_state` (`tradingagents/graph/propagation.py:34-69`) sets `messages`, `company_of_interest`, `asset_type`, `instrument_context`, `trade_date`, `past_context`, empty `investment_debate_state`/`risk_debate_state`, and empty `market_report`/`fundamentals_report`/`sentiment_report`/`news_report`. Note: `sender` and `investment_plan`/`trader_investment_plan`/`final_trade_decision` are **not** seeded in the initial state at all — they exist only once an agent node writes them (out of Week-0 scope files; agent implementations live in `tradingagents/agents/*`).

Proof the "real" shape of a completed `final_state` is exactly the above: `TradingAgentsGraph._log_state` (`tradingagents/graph/trading_graph.py:440-470`) dereferences every one of these keys with bracket access (`final_state["company_of_interest"]`, `["market_report"]`, `["investment_debate_state"]["bull_history"]`, `["risk_debate_state"]["judge_decision"]`, `["final_trade_decision"]`, etc.) — if any is absent this raises `KeyError`, which is itself evidence of what the real, load-bearing field set is (not the docstring, the crash surface).

### Q2 — Execution order (setup.py / conditional_logic.py)

Wired order in `GraphSetup.setup_graph` (`tradingagents/graph/setup.py:97-165`):
`START` → first selected analyst (`setup.py:99`) → per-analyst tool loop (`should_continue_<key>` conditional edge to `tools_<key>` or `Msg Clear <Name>`, `setup.py:108-113`) → next analyst in selection order, or `Bull Researcher` if last (`setup.py:116-119`) → `Bull Researcher` ⇄ `Bear Researcher` debate loop gated by `ConditionalLogic.should_continue_debate` (`setup.py:122-137`, logic in `conditional_logic.py:52-61`) → `Research Manager` (`setup.py:138`) → `Trader` (`setup.py:139`) → `Aggressive Analyst` ⇄ `Conservative Analyst` ⇄ `Neutral Analyst` risk loop gated by `should_continue_risk_analysis` (`setup.py:140-163`, logic in `conditional_logic.py:63-73`) → `Portfolio Manager` → `END` (`setup.py:165`).

Debate loop termination: `count >= 2 * max_debate_rounds` (`conditional_logic.py:55-58`); risk loop termination: `count >= 3 * max_risk_discuss_rounds` (`conditional_logic.py:65-68`). This matches `docs/setup_baseline.md`'s implied report order (`1_analysts` → `2_research` → `3_trading` → `4_risk` → `5_portfolio`, lines 83-93) — **no doc/code conflict found on ordering**. However, **this wiring and both termination predicates have zero test coverage anywhere in the repo** (see §4/§5).

### Q3 — `propagate()` vs `invoke()` vs `stream()` consistency, and which path is tested

Three independent implementations of "merge streamed chunks into a final state" exist and must stay consistent by hand:
1. `TradingAgentsGraph._run_graph` debug branch (`trading_graph.py:397-417`): `graph.stream(..., stream_mode="values")`, `final_state.update(chunk)` per chunk (`trading_graph.py:413-415`); non-debug branch calls `graph.invoke(...)` directly (`trading_graph.py:417`).
2. `cli/main.py:1101-1219`: builds `init_agent_state` manually via `graph.propagator.create_initial_state(...)` (never calls `graph.propagate()`), streams `graph.graph.stream(...)` (`cli/main.py:1120`), and merges chunks itself (`cli/main.py:1217-1219`) — a **third, independent reimplementation** of the same merge logic used nowhere near `TradingAgentsGraph`.
3. `run_streaming_tradingagents_research` (`comqutor_alpha/runners/tradingagents_runner.py:334-346`): same `dict.update(chunk)` merge pattern, again independently implemented.

Given `stream_mode="values"` (`propagation.py:82`), LangGraph emits the *full cumulative state* after every super-step, not a delta — the code comments at `trading_graph.py:411-412` and `cli/main.py:1217` calling these "per-node deltas" are inaccurate, but functionally harmless (`dict.update` over cumulative snapshots converges to the same result as taking the last chunk, which is what `invoke()` also returns for `stream_mode="values"`). No functional divergence found between the three paths in the current code, but three hand-synced copies of the same merge logic is a live drift risk.

**Which path is actually tested?** `graph.propagate()` — nominally the primary public API (`trading_graph.py:321-360`) — is called by exactly: `main.py:15` (a one-off demo script, not test-covered), `comqutor_alpha/runners/tradingagents_runner.py:132` (only when `payload.get("final_state")` is `None`, i.e. the real-execution branch, itself gated behind `allow_real_tradingagents_run=True` and untested — see §4), and `tests/test_memory_log.py:867` (`TradingAgentsGraph.propagate(mock_graph, ...)` against a `MagicMock`, not a real graph — see §4 rating). **`cli/main.py`, the actual interactive entrypoint documented in `docs/setup_baseline.md`, never calls `propagate()` at all** — it duplicates `_run_graph`'s logic by hand and skips the checkpoint/memory-log side effects `propagate()` performs (see Q4/Q5 below). So the one path with a real end-to-end test-shaped exercise (streaming + merge + progress) is the W7 runner's fake-graph tests, not `propagate()` itself, not the CLI, and not a real `TradingAgentsGraph`.

### Q4 — Checkpoint/memory semantics

Real persistence: `langgraph.checkpoint.sqlite.SqliteSaver` over a per-ticker SQLite DB at `<data_cache_dir>/checkpoints/<TICKER>.db` (`tradingagents/graph/checkpointer.py:19-25,34-43`). `thread_id(ticker, date) = sha256(f"{ticker.upper()}:{date}")[:16]` (`checkpointer.py:28-30`) — date is part of the hash input, so two dates for the same ticker get different threads and cannot collide (verified empirically, §5 Mutation B).

Wiring into `propagate()`: only active when `config.get("checkpoint_enabled")` is true (`trading_graph.py:337`, default `False` at `tradingagents/default_config.py:100`); when active, `propagate()` recompiles `self.graph` with the SqliteSaver (`trading_graph.py:341-342`), injects `thread_id` into the LangGraph `config.configurable` (`_run_graph`, `trading_graph.py:393-395`), and clears the checkpoint on success (`trading_graph.py:433-436`) so a stale checkpoint cannot leak into the *next* run of the same ticker+date.

**Defect: the interactive CLI's checkpoint flag is inert.** `cli/main.py` exposes `--checkpoint/--no-checkpoint` (`cli/main.py:1293-1296`) and writes it into `config["checkpoint_enabled"]` (`cli/main.py:987-988`), but `run_analysis` (`cli/main.py:992-1219`) never calls `get_checkpointer`, never recompiles `graph.workflow` with a checkpointer, and never injects a `thread_id` into the stream config — confirmed by exhaustive grep: `grep -n "_resolve_pending_entries\|memory_log\|checkpoint_enabled\|get_checkpointer\|store_decision\|clear_checkpoint\|thread_id" cli/main.py` returns only the two config-plumbing lines above and the `--clear-checkpoints` admin command (`cli/main.py:1297-1306`), which just deletes DB files — it never participates in an actual run. Passing `--checkpoint` on the CLI therefore does nothing: `graph.graph` stays the plain `self.workflow.compile()` built in `TradingAgentsGraph.__init__` (`trading_graph.py:129`), with no checkpointer attached, so a crash mid-run loses all progress regardless of the flag.

**Secondary consequence, same root cause:** the CLI also never calls `graph._resolve_pending_entries(ticker)` (pending same-ticker memory-log reflections from prior runs never resolve when the CLI is used) and never calls `graph.memory_log.store_decision(...)` (the CLI's own runs are never recorded to the memory log at all, so the PM's `past_context` injection on a *future* CLI run of the same ticker will never see decisions made by earlier CLI runs). Both of these ARE correctly wired in `TradingAgentsGraph.propagate()` (`trading_graph.py:334,426-430`) and in the COMQUTOR streaming runner (`tradingagents_runner.py:290-292,356-362`) — i.e. the COMQUTOR-side runner is *more* faithful to `propagate()`'s documented contract than TradingAgents' own CLI is.

### Q5 — Does the COMQUTOR runner preserve TradingAgents' behavior?

`run_original_tradingagents_research` (`tradingagents_runner.py:80-145`) is a thin, unmodified pass-through to `graph.propagate(str(ticker), str(analysis_date), asset_type=asset_type)` (`tradingagents_runner.py:131-136`) when no `final_state` is injected — no config defaults are silently changed, `selected_analysts` mapping is explicit and tested (`map_public_analysts_to_internal`, `tradingagents_runner.py:53-70`, covered by `tests/test_tradingagents_progress_runner.py:32-57`). This branch is **safe by construction** but requires `allow_real_tradingagents_run=True` and is not exercised by any test with a real graph (only via the CLI-bypassing `final_state` injection seam, `tradingagents_runner.py:89-101`).

That injection seam has a real gap: it validates only `ticker`/`analysis_date`/`config` presence (`_require_payload_value`, `tradingagents_runner.py:73-77`) and never validates that the injected `final_state` itself is *complete*. Confirmed by mutation (§5, Mutation C): a `final_state` missing `final_trade_decision` (and several report fields) is accepted, written to disk as a normal-looking run with no `status`/`error` field anywhere in `metadata.json`, and the Portfolio Manager's `raw_agent_outputs.json` entry is silently `[]` instead of surfacing an error. `save_comqutor_run_outputs` does reject a **fully empty** `{}` with `ValueError: final_state is empty` unless `allow_empty_final_state=True` (`tests/test_tradingagents_output_writer.py:213-231`), but that guard only fires on total emptiness, not on a partially-populated state missing the one field (`final_trade_decision`) every downstream consumer (`process_signal`, `_log_state`, memory log, this very writer's `portfolio_manager` field) treats as mandatory.

The W7 streaming path (`run_streaming_tradingagents_research`, `tradingagents_runner.py:239-396`) was checked line-by-line against `propagate()`/`_run_graph()`'s side effects (ticker assignment, `_resolve_pending_entries`, past-context/instrument-context resolution, checkpoint compile+thread_id+clear, `_log_state`, `store_decision`, `process_signal`) and matches on every point — this substantiates `docs/current_system_state.md:37`'s claim that streaming execution preserves `propagate()`'s semantics, for this runner specifically (not for the CLI, which does not preserve them — see Q4).

---

## 3. Doc-vs-code conflicts (explicit)

1. **"Week 0 baseline: PASS/Verified"** (`docs/current_system_state.md:16`, `docs/mvp_evaluation_report.md:24`, `docs/week6_final_gap_audit.md:31`) cites only manual CLI report artifacts as evidence, not automated tests. Code audit shows `tradingagents/graph/setup.py` and `tradingagents/graph/conditional_logic.py` — the two modules that decide graph topology and debate/risk-loop termination — have **zero references in the entire `tests/` tree** (confirmed by `grep -rln "GraphSetup\|setup_graph(\|ConditionalLogic(\|conditional_logic\|should_continue" tests/` → no hits) and by mutation testing (§5, Mutation A: breaking loop termination entirely does not fail a single existing test).
2. **"Ticker and asset-type handling follows TradingAgents CLI rules"** and the CLI's own `--checkpoint` flag (`cli/main.py:1293-1296`) imply the CLI participates in the checkpoint/resume contract described in `trading_graph.py:327-329`'s docstring ("a crashed run can resume from the last successful node"). It does not — see Q4. This is a doc/flag-vs-behavior conflict, not merely a missing feature: the flag exists and is documented as functional but has no effect on the interactive run path.
3. **`trading_graph.py:411-412` / `cli/main.py:1217` code comments** claim streamed chunks are "per-node deltas, not full state." With `stream_mode="values"` (`propagation.py:82`) they are full cumulative snapshots. Not a functional bug (merge still converges correctly) but a factually wrong comment in code that is otherwise treated as documentation of intent.

---

## 4. Test effectiveness table

| Test file::function | What it calls | Mock level | Assertion specificity | Rating | Justification |
|---|---|---|---|---|---|
| `tests/test_checkpoint_resume.py::TestCheckpointResume::test_crash_and_resume` | Real `checkpointer.get_checkpointer/thread_id` + a hand-built toy `StateGraph` (`_node_a`/`_node_b`), not `TradingAgentsGraph`/`setup.py` | None on the primitive; the "domain" graph is a 2-node fake | Business-specific: exact resumed value (`count == 11`), exact step number | **PARTIAL** | Strong proof the LangGraph+SqliteSaver primitive works; proves nothing about `TradingAgentsGraph.propagate()`'s own checkpoint-recompile wiring (`trading_graph.py:337-360`), which no test touches with a real graph. |
| `tests/test_checkpoint_resume.py::test_different_date_starts_fresh` | Same real primitives | None | Specific: `has_checkpoint(date2) is False`, `tid1 != tid2` | **STRONG** | Directly verifies the exact date-isolation property in question; empirically confirmed to catch a date-dropping mutation (§5 Mutation B). |
| `tests/test_memory_log.py::TestLegacyRemoval::test_full_pipeline_no_regression` | `TradingAgentsGraph.propagate` (unbound) + real `_run_graph` bound onto a `MagicMock`; `graph.invoke` is mocked to return a fixed `fake_state` | Mock sits **directly below** `_run_graph`'s call to `self.graph.invoke(...)` — i.e. it swallows all of `setup.py`'s graph construction, all of `conditional_logic.py`'s branching, and every real agent node | Specific: memory-log entry count/ticker/pending flag | **PARTIAL** | Strong for orchestration (call order: resolve-pending → invoke → log → store_decision), but the mock is below the exact modules this audit targets (`setup.py`, `conditional_logic.py`), so it cannot catch a wiring/termination bug in either. `checkpoint_enabled` is absent from the fake config, so the checkpoint branch of `propagate()` (`trading_graph.py:337-360`) is not exercised at all by this test. |
| `tests/test_analyst_execution.py::AnalystExecutionPlanTests::*` | Real `build_analyst_execution_plan`, `get_initial_analyst_node` | None | Specific: exact node/tool/clear names and order | **STRONG** (narrow scope) | Correctly verifies the data structure `setup.py` consumes, but never calls `GraphSetup.setup_graph` itself, so it cannot catch a bug in how `setup.py` *uses* the plan to wire edges. |
| `tests/test_tradingagents_progress_runner.py::test_checkpoint_setup_thread_clear_and_context_cleanup` | `run_streaming_tradingagents_research` with a fully fake `_ParityGraph`/`_FakeWorkflow`/`_FakeCompiledGraph`, and `checkpointer.get_checkpointer/thread_id/clear_checkpoint` monkeypatched to no-op stubs | Mock sits **above** the real `checkpointer.py` (SqliteSaver never touched) and **above** `TradingAgentsGraph`/`setup.py` entirely | Specific: call-order list (`["enter","clear","exit"]`), exact `thread_id` string, exact `compile()` kwargs | **STRONG for orchestration, but structurally cannot see the modules in Week-0 scope** | Excellent proof the *runner's* call sequence is correct; zero evidence about `setup.py`, `conditional_logic.py`, or the real SQLite checkpoint behavior since both are faked out. |
| `tests/test_market_toolnode.py::test_market_toolnode_can_execute_verified_snapshot` | `TradingAgentsGraph._create_tool_nodes(None)` (unbound, no LLM built) | None (real tool registration) | Specific: exact tool name present in `tools_by_name` | **STRONG** (narrow) | Good regression guard for one wiring fact; unrelated to graph topology/ordering. |
| `tests/test_symbol_normalization_paths.py::test_fetch_returns_normalizes_symbol` | `TradingAgentsGraph._fetch_returns` (unbound) with `yf.Ticker` monkeypatched | Real method, mocked yfinance | Specific: exact symbol queried | **STRONG** (narrow) | Good but orthogonal to Week-0 scope questions. |
| *(none)* `setup.py` / `conditional_logic.py` direct coverage | — | — | — | **VACUOUS (absent)** | Confirmed by `grep -rln "GraphSetup\|setup_graph(\|ConditionalLogic(\|conditional_logic\|should_continue" tests/` → zero matches anywhere in the test tree. |

---

## 5. Mutation results table

| # | Fault injected | Test expected to catch it | Actually failed? | Verdict |
|---|---|---|---|---|
| A | Monkeypatched `ConditionalLogic.should_continue_debate` → always `"Bull Researcher"` and `should_continue_risk_analysis` → always `"Aggressive Analyst"` (debate/risk loops never terminate, ignoring `max_debate_rounds`/`max_risk_discuss_rounds` entirely — a real production run would blow the recursion limit or loop indefinitely) | None specifically; ran the full requested suite (`test_checkpoint_resume.py`, `test_memory_log.py`, `test_analyst_execution.py`, `test_structured_agents.py`) | **NO** — 103/103 passed, exit code 0 | **TEST GAP** — confirmed empirically, script at `/private/tmp/.../scratchpad/mutate_conditional_logic.py` |
| B (positive control) | Monkeypatched `checkpointer.thread_id` to ignore the `date` argument (same ticker → same thread id regardless of date, simulating stale-checkpoint reuse across dates) | `tests/test_checkpoint_resume.py::test_different_date_starts_fresh` | **YES** — `AssertionError: True is not false` on `has_checkpoint(tmpdir, ticker, date2)` | **CAUGHT** — proves the mutation harness works and this specific class of bug (date-checkpoint isolation) is genuinely guarded, in contrast to A |
| C | `run_original_tradingagents_research({"final_state": {...missing final_trade_decision, missing 3 of 4 report fields...}, "ticker": "NVDA", ...})` — simulates a caller injecting a partial/crashed `final_state` via the documented test seam | None (no test in the repo calls `run_original_tradingagents_research` by name at all) | Ran to completion with **no exception**; `metadata.json` has no `status`/`error` field; `raw_agent_outputs.json`'s `portfolio_manager` record is silently `[]` | **TEST GAP** — a partially-complete `final_state` is written to disk indistinguishable from a genuinely completed run, verified live with `.venv/bin/python` script (see transcript) |

---

## 6. Confirmed defects

### Defect 1 — CLI `--checkpoint` flag is a no-op (interactive run path never wires the checkpointer)
- **Severity:** P1
- **Location:** `cli/main.py:992-1219` (`run_analysis`), contrast with `tradingagents/graph/trading_graph.py:337-360` (`propagate()`'s correct implementation)
- **Corresponding test:** none — `tests/test_checkpoint_resume.py` only tests the underlying primitive on a toy graph; no test drives `cli/main.py`'s `run_analysis` or asserts a checkpoint DB is created/used by the CLI.
- **Actual problem:** `run_analysis` builds `graph = TradingAgentsGraph(...)` then streams `graph.graph.stream(...)` directly, using the plain `self.workflow.compile()` built in `__init__` (`trading_graph.py:129`). It never calls `get_checkpointer`, never recompiles with a `SqliteSaver`, never injects `thread_id`. The `--checkpoint`/`--no-checkpoint` CLI flag and `TRADINGAGENTS_CHECKPOINT_ENABLED` env var only affect `config["checkpoint_enabled"]`, a dict key nothing in the CLI's run path ever reads again.
- **Why existing tests missed it:** no test exercises `cli/main.py::run_analysis` at all (it's an interactive Typer command); the checkpoint tests target either the raw primitive (toy graph) or the COMQUTOR runner (fake graph) — neither touches the CLI.
- **Minimal repro:** `grep -n "get_checkpointer\|thread_id\|checkpoint_enabled" cli/main.py` shows only the two config-assignment lines (987-988) and the standalone `--clear-checkpoints` admin path (1297-1306); no occurrence inside `run_analysis`'s body.
- **Blast radius:** every interactive CLI user who passes `--checkpoint` expecting crash-resume gets silent data loss on crash — the documented safety feature (`trading_graph.py:327-329`'s own docstring) simply does not apply to the tool's primary entrypoint.
- **Recommended fix direction:** either route `run_analysis` through `TradingAgentsGraph.propagate()`/`_run_graph()` (eliminating the triplicated stream/merge logic at the same time), or duplicate the checkpoint-compile/thread_id/clear steps into the CLI's manual stream block, with a regression test that asserts a checkpoint DB file is created under `--checkpoint`.

### Defect 2 — Partial `final_state` silently accepted as a completed run through the injection seam
- **Severity:** P2
- **Location:** `comqutor_alpha/runners/tradingagents_runner.py:89-101` (`run_original_tradingagents_research`'s `final_state` branch) and `comqutor_alpha/adapters/tradingagents_output_writer.py` (writer has no per-field completeness check, only a whole-dict-emptiness check)
- **Corresponding test:** none (`run_original_tradingagents_research` has zero references anywhere in `tests/`); `tests/test_tradingagents_output_writer.py:213-231` only tests fully-empty `{}` rejection.
- **Actual problem:** `_require_payload_value` validates `ticker`/`config`, never `final_state`'s internal shape. A `final_state` missing `final_trade_decision` (e.g. a crashed/partial run someone injects) is written to `outputs/runs/<id>/` with no `status: failed`/`error` field anywhere, `metadata.json["artifacts"]["final_report"]: false` as the only hint, and `portfolio_manager` silently empty in `raw_agent_outputs.json`.
- **Why existing tests missed it:** the only place this seam is exercised is via hand-constructed *complete* `fake_state` fixtures in other test files (e.g. `tests/test_memory_log.py:829-849`); no negative/boundary-case test ever calls it with a deliberately incomplete state.
- **Minimal repro:** see §5 Mutation C script (executed live, output captured above: `portfolio_manager record: []`, no error, no status field).
- **Blast radius:** currently low — the production HTTP path (`comqutor_alpha/api/routes_research.py:687`) only calls this function when `final_state is None`, so the vulnerable branch is reachable only by direct Python callers (documented as a "test seam," but the function itself enforces no such restriction at runtime). Risk grows if any future integration reuses a cached/partial `final_state`.
- **Recommended fix direction:** extend the writer's (or the runner's) validation to require `final_trade_decision` (and ideally all four report fields) to be non-empty before treating a run as complete, or add an explicit `status` field to `metadata.json` that downstream consumers can check instead of inferring completeness from artifact presence.

### Defect 3 (minor/observational, not independently blocking) — `setup.py` and `conditional_logic.py` have no direct or indirect test coverage
- **Severity:** P2
- **Location:** `tradingagents/graph/setup.py`, `tradingagents/graph/conditional_logic.py`
- **Corresponding test:** none, confirmed by grep and by Mutation A (§5).
- **Actual problem:** the graph topology (node registration, edge wiring, which conditional function gates which transition) and the debate/risk round-termination arithmetic are exercised by no test at any level — not unit, not integration, not through a mock that at least calls the real function once.
- **Why existing tests missed it:** the two "closest" tests (`test_analyst_execution.py`, `test_memory_log.py::test_full_pipeline_no_regression`) each mock at a layer that excludes these modules — one never calls `setup_graph`, the other mocks `graph.invoke` itself, bypassing the compiled graph entirely.
- **Minimal repro:** Mutation A (§5) — breaking both termination predicates to loop forever passes the entire targeted test suite unchanged.
- **Blast radius:** any regression in loop-termination or edge wiring (e.g. an off-by-one in the round cap, a copy-paste edge pointing at the wrong node) would only be caught by a real (expensive, LLM-calling) end-to-end run or in production.
- **Recommended fix direction:** a unit test file for `conditional_logic.py` that drives `should_continue_debate`/`should_continue_risk_analysis` directly with boundary-value `AgentState` fixtures (count at, just below, just above the cap), and a `setup.py` test that builds a real `StateGraph` with stub node callables (no LLM) and asserts the compiled graph's edge map / node set.

---

## 7. Week 0 verdict

**PARTIALLY_VERIFIED**

Justification against the acceptance criteria:
- *Code matches spec*: mostly yes — the graph topology, checkpoint isolation semantics, and the W7 streaming runner's fidelity to `propagate()` all check out against their docstrings/docs with one exception (below).
- *Call chain actually connects*: **no**, in one concrete, user-facing way — the documented/flagged checkpoint-resume feature does not connect end-to-end on the CLI, the tool's own primary entrypoint (Defect 1).
- *Independent manual oracle exists*: yes for the checkpoint primitive (`test_different_date_starts_fresh`, confirmed to catch injected faults) and for the runner's chunk-merge/progress logic; **no** independent oracle exists for `setup.py`'s graph wiring or `conditional_logic.py`'s termination logic — nothing in the repo would notice if either were wrong.
- *Positive/negative/boundary tests exist*: strong for memory-log/checkpoint-primitive/analyst-plan modules; **absent** for `setup.py`/`conditional_logic.py`; **absent negative-path test** for the `final_state` injection seam (Defect 2).
- *Mutation faults get caught*: mixed by design of this audit — one mutation (date-checkpoint isolation) was caught cleanly; two mutations (debate/risk-loop non-termination, incomplete-final_state acceptance) were not caught by anything in the suite.
- *No bypassed production path*: the CLI silently bypasses `propagate()`'s checkpoint/memory-log side effects while still presenting a working `--checkpoint` flag — this is exactly a "bypassed production path presented as working."
- *Error states aren't reported as completed*: violated by Defect 2 — a `final_state` missing its terminal field is written with no error/status marker.
- *Tests aren't tautological/vacuous*: the tests that exist are largely non-vacuous (specific business-outcome assertions), but two of the five Week-0-scope files (`setup.py`, `conditional_logic.py`) have **no tests at all**, which is a stronger gap than a weak/tautological test.

Given the docs' own "PASS/Verified" claims for Week 0 rest on manual CLI report artifacts rather than code-level verification, and this audit found a real, user-visible feature (checkpoint-resume via the CLI) that does not work despite being flagged as available, plus two core modules with zero test coverage, "PASS" is not supportable as-is. Nothing found is catastrophic (no wrong trading decisions, no data corruption, no security issue) — hence not INCORRECT — but the verification claim needs qualification, hence PARTIALLY_VERIFIED.
