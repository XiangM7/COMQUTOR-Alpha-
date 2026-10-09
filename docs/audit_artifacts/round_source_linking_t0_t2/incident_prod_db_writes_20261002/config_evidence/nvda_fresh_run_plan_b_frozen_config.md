# Plan B: NVDA Fresh Run -- frozen configuration (captured before launch)

Captured 2026-10-01, immediately before starting the real server process and
submitting the one authorized real research request. This document is the
pre-run freeze required by this round's authorization; the post-run report
will reference it rather than re-deriving these facts from memory.

## Code state

- HEAD: `7a9aefa5c7b5c820515447c6289aeef80eac9bdc`
- Dirty-diff sha256 (uncommitted working-tree changes, `git diff` at freeze
  time, includes this round's `task_model_overrides` addition to
  `week2_llm.py` and its two new offline wiring tests):
  `a52d508fb23934f514a44d9f46028beccc496914e3705242ae7975207cc102aa`
- No commit is made for this run; the working tree as it stands at this hash
  is what the server process will import and execute.

## Database target (verified, credential-redacted)

- `COMQUTOR_DATABASE_URL` is force-overridden, for the launched server
  process only, to `COMQUTOR_TEST_DATABASE_URL`'s value (never written to
  `.env`), by `run_nvda_fresh_run_isolated_db.sh`, which fails closed if the
  resolved database name does not end in `_test`.
- Resolved target: host `127.0.0.1`, port `5433`, database
  `comqutor_alpha_test`.
- The real production `COMQUTOR_DATABASE_URL` (main database) resolves to
  the SAME host:port (`127.0.0.1:5433`) and differs only in database name
  (`comqutor_alpha`) -- there is no host/port-level separation, so the
  launcher's own "must end in `_test`" fail-closed check is the only real
  safety boundary, and is the reason this run must only ever be started
  through that launcher script, never by hand-constructing an equivalent
  command.

## Week2 semantic-extraction layer (`Week2LLMGateway`, one instance per run)

- Provider: `deepseek` (`COMQUTOR_WEEK2_LLM_PROVIDER`, from `.env`)
- Model: `deepseek-v4-flash` (`COMQUTOR_WEEK2_LLM_MODEL`, from `.env`)
- Timeout: 45s (`COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS`, from `.env`)
- Max retries per logical call: 1 (`COMQUTOR_WEEK2_LLM_MAX_RETRIES=1`,
  already set in `.env`, unchanged by this run)
- Max actual-request budget (global across the whole run, counts every real
  attempt including retries -- confirmed by direct code reading of
  `Week2LLMGateway._reserve_call`/`invoke_json_with_trace`, NOT "logical
  calls"): **700**, via `COMQUTOR_WEEK2_LLM_MAX_CALLS=700` exported for this
  run only (the unset default would have been the workload-aware formula's
  own total, confirmed much larger than 700 -- this run explicitly lowers it
  to the authorized ceiling).
- Alpha-classifier concurrency: 4 (`DEFAULT_ALPHA_CLASSIFIER_CONCURRENCY`,
  `COMQUTOR_WEEK2_LLM_CONCURRENCY` left unset/default -- not a value this
  round's authorization specified, recorded for completeness only).
- Alpha classification call shape: **single-claim**, not batch -- confirmed
  by direct code reading: `map_structured_records`/`build_alpha_matches_
  payload`/`save_alpha_matches` all default `use_batched_classifier=False`;
  the real call site (`routes_research.py`'s `save_alpha_matches` dispatch)
  passes no override; `map_claim_to_alpha` calls
  `llm_gateway.invoke_json_with_trace("alpha_classifier", ...)` directly.
  `alpha_classifier_batch` (prompt version `week2.alpha_classifier_batch.v4`,
  sha256 `f217bdbeb5a68f80f1447a1178f97b2a4c314d90f445cf92b356b164c33ebc2e`)
  is **not reachable by this real run** and **not covered by this round's
  single-claim v7 verification** -- left completely untouched.
- Alpha-classifier single-call output cap: **4096**, reusing the frozen v7
  prompt -- via a new, additive, opt-in-only mechanism built this round
  (`Week2LLMGateway.task_model_overrides` / `COMQUTOR_WEEK2_ALPHA_CLASSIFIER_
  MAX_TOKENS=4096`, exported for this run only). A dedicated second LLM
  client instance is built and used ONLY for the `alpha_classifier` task;
  every other task keeps the shared gateway model with no output cap
  (unchanged). Verified offline (no real Provider call) via two new tests in
  `tests/test_week2_llm.py`:
  `test_task_model_overrides_routes_exactly_the_named_task_to_its_own_model`
  and `test_alpha_classifier_max_tokens_env_var_reaches_only_the_alpha_
  classifier_real_request` (the latter inspects the real serialized
  outgoing HTTP body through a MockTransport, confirming `max_tokens: 4096`
  reaches alpha_classifier's own request and is absent from
  claim_batch_enrichment's).

### Prompt versions and identity hashes (all 5 Week2 tasks)

| task | prompt_version | prompt_identity_sha256 |
|---|---|---|
| claim_batch_enrichment | week2.claim_batch_enrichment.v1 | c6822099e2171c6fbad72c36bf2881bcd59bd4d4ad2fc20e10ab62af50b5bfd9 |
| alpha_classifier | week2.alpha_classifier.v7 | ac48723f15cf347590ad2cb175f76cd438dbc4181c7b781aa0cfffaafe589b95 |
| alpha_classifier_batch (unused, untouched) | week2.alpha_classifier_batch.v4 | f217bdbeb5a68f80f1447a1178f97b2a4c314d90f445cf92b356b164c33ebc2e |
| structure_extractor | week2.structure_extractor.v1 | 326622a1786be03909e3d6dbcfca5069fe3cd4b31f0aab2da36bf8be324edbbc |
| evidence_stance_classifier | evidence_stance.llm_classifier.v3 | d9455fd5ff337c670ed7d146da3362ae656fd542f456690859fcb15564d0b6f2 |

## Research Agent (TradingAgents) layer

Fixed server research profile `comqutor_deepseek_default_v1`
(`get_active_research_profile()`), applied on top of `DEFAULT_CONFIG`:

- Provider: `deepseek`; quick_think_llm = deep_think_llm = `deepseek-v4-flash`
- temperature: 0.0; max_debate_rounds: 1; max_risk_discuss_rounds: 1
- output_language: English; backend_url: None (SDK default);
  deepseek_thinking: disabled
- Max actual-request budget: **150**, via
  `COMQUTOR_RESEARCH_AGENT_MAX_ACTUAL_REQUESTS=150` exported for this run
  (opt-in mechanism, unset by default -- confirmed via
  `comqutor_alpha/research_lifecycle.py` reading this exact env var and
  `comqutor_alpha/runners/tradingagents_runner.py`'s
  `RequestBudgetGuard`/`wrap_chat_model_with_budget_guard` wiring).
- Max visible retries: **1**, via `COMQUTOR_RESEARCH_AGENT_MAX_RETRIES=1`.
- SDK-hidden retries: disabled automatically as a direct consequence of
  setting `research_agent_max_actual_requests` -- `tradingagents_runner.py`
  forces `graph_construction_config["max_retries"] = 0` on the underlying
  chat client BEFORE `TradingAgentsGraph` ever constructs it (confirmed by
  direct code reading and an existing transport-boundary test suite in
  `tests/test_request_budget.py`), so `TRADINGAGENTS_MAX_RETRIES` is
  irrelevant here and is left unset.
- Research Agent single-call output cap: **4000**, via
  `TRADINGAGENTS_MAX_TOKENS=4000` (env-var-driven `DEFAULT_CONFIG["max_
  tokens"]`, forwarded to the real `ChatOpenAI`-compatible client
  constructor in `tradingagents/graph/trading_graph.py`). Unset default is
  `None` (unbounded) -- this run explicitly sets it.
- LangGraph recursion-step (super-step) cap: **100** -- this is already
  `DEFAULT_CONFIG`'s own default (`max_recur_limit=100`); exported explicitly
  as `TRADINGAGENTS_MAX_RECUR_LIMIT=100` anyway for this run, for an
  unambiguous audit trail rather than relying on an unstated default.

## Request submitted

`POST /api/research` body: `{"ticker": "NVDA", "selected_analysts":
["market", "sentiment", "news", "fundamentals"]}`. `asset_type` is not a
client-settable field on `ResearchRequest` -- it is resolved server-side via
`server_execution.resolve_asset_type("NVDA")`, confirmed to return `"stock"`
directly against the real classifier (`cli.utils.detect_asset_type`). All
four requested analysts are confirmed members of
`server_execution.REAL_RUN_ALLOWED_ANALYSTS = {"market", "news",
"fundamentals", "sentiment"}`.

## Taxonomy / rules

- `comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml`:
  `schema_version: alpha_taxonomy_v1`, sha256
  `18a0dc6b5de7bbae3541272fbd66fa1172e62eed172fd86e97a72e1a40d90972`
  (current working-tree content, which is what the server process reads;
  this file shows as modified relative to HEAD in this branch).
- Step 7A (`alpha_specific_invalidation_matched`) / Step 7A.2 (`alpha_
  positive_requirement_satisfied`) post-hoc semantic gates: unchanged this
  round except for the A001 negation-scope regex fix (grammatically-scoped
  patterns replacing the earlier, now-retired character-window check).

## Evidence cutoff

Resolved by the server at submission time via
`server_execution.resolve_real_analysis_date(None)` (no explicit
`analysis_date` supplied in the request): **2026-10-02**.

## Run submitted

- `run_id`: `034a0a60-430e-41f8-8321-03a11389707a`
- Submitted via `POST /api/research` at the real running server
  (`127.0.0.1:8000`), HTTP 202, `cache_disposition: created`.
- Observed: the real TradingAgents research pipeline begins executing
  immediately (confirmed via the server's own stdout: real Reddit RSS and
  macro-indicator data-gathering calls for NVDA), but `GET /api/research/
  {run_id}` reports `RUN_NOT_FOUND` until the run's file directory
  (`outputs/runs/{run_id}/`) is first created by the pipeline's own
  persistence step -- confirmed by direct code reading
  (`get_research_run`/`run_dir_for`/`resolve_output_root`: the real server
  process has `app.state.output_root = None`, which resolves to
  `COMQUTOR_OUTPUT_DIR` if set (it is not) else `<cwd>/outputs/runs`) to be
  expected behavior, not a defect: status polling is directory-existence-
  gated, not based on an early in-memory/DB "queued" claim row. This will be
  reported as an observed characteristic, not silently smoothed over.
