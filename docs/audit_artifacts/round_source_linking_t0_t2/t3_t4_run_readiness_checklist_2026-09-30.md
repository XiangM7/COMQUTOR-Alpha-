# T3 / T4 run-readiness checklist (2026-09-30, third follow-up round — updated)

This document is preparation only. Neither T3's live evaluation nor T4's Fresh Run was executed this round — no paid Provider call was made to produce it. Script-writing, offline testing, and public pricing lookups were completed directly this round (no re-authorization needed for those); only the two real, paid runs below remain genuinely pending on a human decision.

## T3: evaluation — now directly executable, not just planned

### 1. Ready-to-use commands

**Offline preflight (zero external requests, safe to run anytime):**

```bash
cd /Users/xiangmao/COMQUTOR-Alpha-
.venv/bin/python3 docs/audit_artifacts/round_source_linking_t0_t2/t3_diagnostic_evaluation_driver.py preflight \
  --samples-file docs/audit_artifacts/round_source_linking_t0_t2/t3_targeted_diagnostic_sample_2026-09-30.json \
  --review-form-file docs/audit_artifacts/round_source_linking_t0_t2/t3_human_review_form_2026-09-30.json \
  --output-dir outputs/t3_evaluations
```

Run and confirmed working this round: all 40 samples report `sample_completeness_status=COMPLETE` and their real source material present on disk; the only current blocking reason is `WEEK2_LLM_CONFIG_INCOMPLETE_OR_DISABLED` (expected — `COMQUTOR_WEEK2_LLM_ENABLED` is correctly off by default) and human review being `BLOCKED_NO_HUMAN_LABELS` (expected — no reviewer has judged the 40 items yet).

**Live run — predict only, paid, PENDING AUTHORIZATION (do not run without explicit sign-off). `live` never reads or scores against human labels at all anymore — scoring is a fully separate, offline `score` mode below, run only after the fact:**

```bash
cd /Users/xiangmao/COMQUTOR-Alpha-
set -a; source .env; set +a   # picks up COMQUTOR_WEEK2_LLM_PROVIDER/MODEL from the confirmed config
export COMQUTOR_WEEK2_LLM_ENABLED=1
.venv/bin/python3 docs/audit_artifacts/round_source_linking_t0_t2/t3_diagnostic_evaluation_driver.py live \
  --i-acknowledge-this-makes-real-provider-calls \
  --samples-file docs/audit_artifacts/round_source_linking_t0_t2/t3_targeted_diagnostic_sample_2026-09-30.json \
  --review-form-file docs/audit_artifacts/round_source_linking_t0_t2/t3_human_review_form_2026-09-30.json \
  --output-dir outputs/t3_evaluations \
  --max-actual-requests 80 --max-retries-per-call 1 --max-output-tokens 200
```

**Budget parameters**: `--max-actual-requests 80` (40 samples × up to 2 attempts each in the worst case) and `--max-retries-per-call 1` are the recommended defaults — see `t3_t4_pricing_reference_2026-09-30.md` §2 for the real cost basis behind these numbers (≈$0.009–0.035 total, `deepseek-v4-flash`, off-peak-to-peak range). `--max-output-tokens 200` (new this round) is a real, explicit per-call output-token cap confirmed to reach the actual Provider client's own `max_tokens` field (tests/test_week2_llm.py) — generous headroom over the real, fixed output shape, never omitted on the assumption the output "happens to be small".

Each invocation of `live` mode creates its own new `execution_id` and writes a `freeze_identity.json` (git HEAD, dirty-diff hash, sample/review-form file hashes, taxonomy hash, live prompt-identity hash) into `outputs/t3_evaluations/<execution_id>/` before making any call — this is the freeze step, already implemented and tested, not a manual step someone has to remember. The command's own printed `t3_eval_summary.json` output names the exact `score` command to run next (with this run's own `<execution_id>` already filled in).

**After human review is complete — import the labels, then score entirely offline (zero Provider calls, zero cost, can be re-run as many times as needed):**

```bash
cd /Users/xiangmao/COMQUTOR-Alpha-
# 1. import the filled-in worksheet into the review form
.venv/bin/python3 docs/audit_artifacts/round_source_linking_t0_t2/t3_diagnostic_evaluation_driver.py import-worksheet \
  --review-form-file docs/audit_artifacts/round_source_linking_t0_t2/t3_human_review_form_2026-09-30.json \
  --worksheet-file docs/audit_artifacts/round_source_linking_t0_t2/t3_human_review_worksheet_2026-09-30.csv

# 2. score the ALREADY-SAVED prediction execution from step 1's live run
#    against the now-completed review form -- replace <execution_id> with
#    the real one the live run printed/wrote to outputs/t3_evaluations/.
.venv/bin/python3 docs/audit_artifacts/round_source_linking_t0_t2/t3_diagnostic_evaluation_driver.py score \
  --prediction-execution-dir outputs/t3_evaluations/<execution_id> \
  --review-form-file docs/audit_artifacts/round_source_linking_t0_t2/t3_human_review_form_2026-09-30.json
```

`score` reads the prediction's own already-saved `t3_eval_records.jsonl` and the review form, aligns by `sample_id`, checks that each judged sample's `claim_text` still matches what was actually sent to the Provider (flagging `sample_version_mismatches` rather than silently scoring against a drifted pool), and writes a NEW `<score_execution_id>_score_result.json` into the SAME prediction directory — it never re-calls `map_claim_to_alpha`, never constructs a gateway, and never overwrites the original prediction's own files (confirmed by an AST-level test that the function cannot even reference those symbols, plus a behavioral test with a gateway-construction sentinel that would raise if ever reached).

### 2. Scope actually covered by this driver

Only **Alpha Classification** (see `t3_diagnostic_evaluation_driver.py`'s own `STEPS_COVERED` dict, and its module docstring's outcome taxonomy). Source-support verification, claim-fidelity, Evidence-Stance/Polarity, and downstream-eligibility are separate real steps this driver does not call — any report this driver produces says so explicitly rather than implying a broader evaluation.

### 3. Sample set and human-review status

- `t3_targeted_diagnostic_sample_2026-09-30.json`: 40/40, `status=COMPLETE`.
- `t3_human_review_form_2026-09-30.json`: 40 blind `review_items`, `human_review_performed=false`. Each item now also carries `source_material_completeness_status` (see `t3_sample_material_completeness_2026-09-30.json` for the full audit and `t3_reviewer_package_readme_2026-09-30.md` for the ready-to-hand-off package and instructions — not sent to anyone yet).
- 25/40 items already scored into the frozen historical 82.67%/87.23% results; 13/40 (`prod-run-*`) verified `NOT_PREVIOUSLY_USED`; 2/40 `PARTIALLY_EXPOSED` (a formal-acceptance trigger-matrix artifact, not a labeled set). See each item's own field — never summarized as one blanket status.

### 4. Freezing mechanism

Implemented in the driver itself (`build_freeze_identity`), not a manual step: every `live` invocation hashes the samples file, review-form file, and taxonomy file, records the live `alpha_classifier` prompt-identity hash, the current git HEAD, and a hash of any uncommitted (`git diff`) changes — all written to `freeze_identity.json` before the first real call.

## T4: one NVDA Fresh Run — PENDING AUTHORIZATION

### 1. Startup command (isolated PostgreSQL enforced by real code, not a manual reminder)

```bash
cd /Users/xiangmao/COMQUTOR-Alpha-

# Week2 layer: real, already-enforced per-run call/retry caps (pre-existing).
export COMQUTOR_WEEK2_LLM_MAX_CALLS=700
export COMQUTOR_WEEK2_LLM_MAX_RETRIES=1

# Research Agent layer: per-call output-token cap and LangGraph recursion
# (super-step) limit -- real, tested, previously absent entirely
# (tests/test_env_overrides.py, tests/test_temperature_config.py).
export TRADINGAGENTS_MAX_TOKENS=4000
export TRADINGAGENTS_MAX_RECUR_LIMIT=100
# NOTE: do NOT also set TRADINGAGENTS_MAX_RETRIES here. Whenever
# COMQUTOR_RESEARCH_AGENT_MAX_ACTUAL_REQUESTS (below) is set, the real
# production code forces the underlying client's own max_retries to 0
# regardless of this variable -- confirmed this round, at the real
# transport boundary, that mutating an already-constructed client's
# max_retries does NOT change its real retry behavior, so this must happen
# at construction time, overriding whatever this env var says. Setting it
# here would be silently ignored; COMQUTOR_RESEARCH_AGENT_MAX_RETRIES below
# is the one real, fully-counted retry control while the guard is active.

# Research Agent layer: the REAL, hard TOTAL actual-request cap (distinct
# from the recursion limit above -- this counts real LLM requests,
# including retries, and raises before the (N+1)th one; the recursion
# limit above only bounds LangGraph super-steps, never call count directly
# -- verified this round at the real httpx transport boundary, not just via
# an invoke()-level mock or an env-var pass-through check:
# tests/test_request_budget.py's transport-boundary suite,
# tests/test_live_research_final_closure.py).
export COMQUTOR_RESEARCH_AGENT_MAX_ACTUAL_REQUESTS=150
export COMQUTOR_RESEARCH_AGENT_MAX_RETRIES=1

bash docs/audit_artifacts/round_source_linking_t0_t2/run_nvda_fresh_run_isolated_db.sh
```
```bash
# in a second terminal, once the preflight above prints all ✅ READY:
curl -X POST http://127.0.0.1:8000/api/research \
  -H "Content-Type: application/json" \
  -d '{"ticker": "NVDA", "asset_type": "stock", "selected_analysts": ["market","sentiment","news","fundamentals"]}'
```

`run_nvda_fresh_run_isolated_db.sh` (new this round) forces `COMQUTOR_DATABASE_URL` to `COMQUTOR_TEST_DATABASE_URL`'s own value for this process only and **refuses to hand off to `start_live_comqutor.sh` unless the resulting database name ends in `_test`** — a real, executed check, not a manual reminder (dry-run-verified both the pass and refusal cases this round; see the round report). `start_live_comqutor.sh` itself still forces `COMQUTOR_REAL_TRADINGAGENTS_ENABLED=true` / `COMQUTOR_WEEK2_LLM_ENABLED=true` in-process and refuses to start unless its own same-process preflight (`comqutor_alpha.server_execution.build_live_semantic_readiness()`) passes.

### 2. What happens when a limit is reached

- **Week2 layer** (`COMQUTOR_WEEK2_LLM_MAX_CALLS`): enforced inside `Week2LLMGateway._reserve_call()` — once reached, that task returns `provider_status="budget_exhausted"` for the remaining claims; already-processed claims are unaffected; this has been real, tested production behavior since before this round.
- **Research Agent recursion** (`TRADINGAGENTS_MAX_RECUR_LIMIT`): LangGraph's own `GraphRecursionError` if the graph takes more super-steps than this — an existing, pre-this-round mechanism, now made env-configurable instead of hardcoded to 100.
- **Research Agent actual-request cap** (`COMQUTOR_RESEARCH_AGENT_MAX_ACTUAL_REQUESTS`, new this round): a real `ResearchAgentBudgetExceeded` is raised from inside the wrapped chat model's own `invoke()` — BEFORE the real Provider request is made — the moment the (N+1)th real attempt (including a retry) would be needed. Confirmed empirically this round, at the REAL httpx transport boundary (`tests/test_request_budget.py`'s transport-boundary suite — a real `create_llm_client`→`ChatOpenAI`→real `openai` SDK→real `httpx` client chain, with only the transport itself replaced by a fixed `httpx.MockTransport` response; never a mock of `.invoke()`/`._generate()`, never just an env-var check): a blocked request's transport handler is never called at all, proving it genuinely never leaves the process. Also confirmed empirically that a LangChain *callback*-based approach (e.g. raising from `on_chat_model_start`) does **not** actually stop the call — LangChain swallows the exception and proceeds anyway — which is why this is implemented as a real call-interception wrapper instead (`comqutor_alpha/runners/request_budget.py`). This exception propagates all the way out of `run_streaming_tradingagents_research` uncaught (confirmed: no analyst/researcher/trader/risk node anywhere in `tradingagents/` wraps its own `.invoke()` in a `try`/`except`) — it is never silently swallowed into a "graceful" continuation that keeps spending. The runner catches this ONE specific exception type just long enough to save whatever real chunks already arrived (tagging `metadata.json` with `stopped_reason=RESEARCH_AGENT_REQUEST_BUDGET_EXCEEDED`, relocated to the claimed run_id exactly like a normal completion) before re-raising, so a stopped run's real partial output is not discarded.
- **Retries, honestly scoped, final effective values**: `COMQUTOR_RESEARCH_AGENT_MAX_RETRIES` retries are implemented at this same wrapper's own level — every retry attempt consumes one unit of the SAME actual-request budget above, confirmed via a real retry-then-success scenario showing exactly 2 real transport calls (never more, never silently fewer). **A real, previously-undiscovered gap was found and fixed this round**: simply retrying at the wrapper's own level is not enough on its own — if the underlying client's own `max_retries` were left at the SDK's default, a *single* wrapper-level attempt could silently cause 3 real transport-level requests underneath (confirmed directly: the `openai` SDK's own default retry setting made 3 real calls for what `.invoke()` itself saw as one), invisible to this guard's own counter. Closed, not merely disclosed: whenever `COMQUTOR_RESEARCH_AGENT_MAX_ACTUAL_REQUESTS` is set, `run_streaming_tradingagents_research` now forces the config handed to graph construction to carry `max_retries=0` before the real client is ever built — **`TRADINGAGENTS_MAX_RETRIES` is silently overridden to 0 whenever the guard is engaged, regardless of what the operator set it to** — making `COMQUTOR_RESEARCH_AGENT_MAX_RETRIES` the ONE AND ONLY place a retry happens, with full visibility. What remains genuinely unobservable at this boundary (a real, disclosed limitation, not claimed to be covered) is anything below `httpx` entirely — e.g. a raw OS/TCP-level retry a network stack might perform beneath the HTTP client, which this round's testing cannot reach or rule out.

### 3. Budget parameters still requiring a human decision

- **Ticker**: NVDA only, one run. **`force_refresh`**: left at its safe default (`false`) unless explicitly requested otherwise.
- **The two new numeric caps above** (`COMQUTOR_WEEK2_LLM_MAX_CALLS=700`, `COMQUTOR_RESEARCH_AGENT_MAX_ACTUAL_REQUESTS=150`) are this document's own suggested starting points (700 gives headroom over the existing historical NVDA reference run's real 591 total Week2 calls; 150 is a round, conservative guess for the Research Agent layer, which has no historical measurement at all to size against) — not validated against a real run of this exact scope. A human should confirm or adjust both before authorizing.
- **Cost**: see `t3_t4_pricing_reference_2026-09-30.md` §3 — Week2 semantic layer floor estimate ≈$0.12–0.24 (likely an undercount for `structured_adapter`/`structure_extractor`'s longer prompts, and now bounded above by `COMQUTOR_WEEK2_LLM_MAX_CALLS`, not just historically typical). Research Agent (`gpt-5.5`/`gpt-5.4-mini`) cost is genuinely **UNKNOWN in dollars** — the request-count/token/retry caps above bound how many requests of what maximum size can happen, but **do not by themselves guarantee a dollar ceiling** (price-per-token still applies per real request made, and this round found no confirmed pricing basis beyond what §3 already sourced for the two Research Agent models). Real cost is only knowable after the fact from this round's own new `tradingagents_llm_usage_summary.json`. **Budget authorization should treat the request-count caps as a request-volume ceiling, and the Week2 floor plus an unknown, possibly larger, Research Agent dollar cost as the actual financial exposure.**

### 4. What to record and verify after the run

- A new, real `execution_id`/`run_id` (never reusing `57d7b4c4-...`, the existing frozen NVDA reference run).
- The run's own actual config from `metadata.json` / `llm_semantic_manifest.json`, compared against `t3_model_config_comparison_2026-09-30.md` to catch drift.
- Both request-statistics artifacts: `outputs/runs/<run_id>/llm_semantic_calls.jsonl` + `llm_semantic_manifest.json` (Week2, pre-existing) and the new `outputs/runs/<run_id>/tradingagents_llm_calls.jsonl` + `tradingagents_llm_usage_summary.json` (TradingAgents layer, new this round) — read back and spot-check `missing_usage_ratio`/`retry_count_total`/`actual_request_count`, not just confirm the files exist.
- Full artifact completeness: `raw_agent_outputs.json`, `structured_agent_outputs.json`, `alpha_matches.json`, `alpha_activations.json`, `conflicts.json`, `entity_alpha_exposures.json`, `evidence_facts.json`, `run_audit.json`, `artifact_manifest.json`.
- Functional verification against the real API: source viewing, the formal-acceptance conclusion path (`run_formal_acceptance` with this run's real `alpha_matches_payload`), historical-read consistency, export, and the insufficient-material/failure path (provoked deliberately if feasible, or at minimum the code path cited).

## What this round changed relative to the prior version of this document

The prior version said "no driver script exists" and "no pricing table exists" as open gaps. Both are now closed: `t3_diagnostic_evaluation_driver.py` exists, is tested (33 tests across this round's three new/updated test files), and was run against the real 40-sample files this round (preflight mode only — zero paid calls). The ~44-call T3 estimate is superseded by a real 40-call count tied to the driver's actual single-step scope. Pricing for all three currently-billed models is sourced and dated in `t3_t4_pricing_reference_2026-09-30.md`. The only genuinely open items are the two paid executions themselves (T3 live run, T4 Fresh Run) and the human review of the 40 samples — all three require an explicit human decision, not further script-writing.
