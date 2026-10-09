# T3 / T4 pricing reference and recomputed call-volume estimates (2026-09-30, third follow-up round)

Public official pricing pages were consulted to produce this document (`WebSearch`/`WebFetch`, both read-only, zero model calls, zero research-data fetch of any kind related to the trading pipeline itself). No model was called to produce this document.

## 1. Every billed provider/model in the actual frozen config

Per `t3_model_config_comparison_2026-09-30.md`, the current production config uses exactly three distinct (provider, model) pairs across all five real steps:

| Step(s) | Provider | Model |
|---|---|---|
| Research Agent (deep-think) | `openai` | `gpt-5.5` |
| Research Agent (quick-think) | `openai` | `gpt-5.4-mini` |
| Extraction, Alpha Classification, Polarity, Structure (all four Week2 tasks) | `deepseek` | `deepseek-v4-flash` |

All three were successfully priced from an official source — there is no unconfirmed gap for the current production config.

### gpt-5.5

| Field | Value |
|---|---|
| Official URL | https://developers.openai.com/api/docs/pricing (reached via the official redirect from `https://platform.openai.com/docs/pricing`) |
| Query date | 2026-09-30 |
| Currency / unit | USD per 1,000,000 tokens |
| Input | $5.00 |
| Cached input | $0.50 |
| Output | $30.00 |
| Time-of-day variation | None found |

### gpt-5.4-mini

| Field | Value |
|---|---|
| Official URL | https://developers.openai.com/api/docs/pricing |
| Query date | 2026-09-30 |
| Currency / unit | USD per 1,000,000 tokens |
| Input | $0.75 |
| Cached input | $0.075 |
| Output | $4.50 |
| Time-of-day variation | None found |

### deepseek-v4-flash

| Field | Value |
|---|---|
| Official URL | https://api-docs.deepseek.com/quick_start/pricing |
| Query date | 2026-09-30 |
| Currency / unit | USD per 1,000,000 tokens |
| Model-name note | The official page's pricing TABLE lists the model as **`deepseek-flash`**, with an explicit statement that the legacy name **`deepseek-v4-flash`** (the exact string this codebase's own `COMQUTOR_WEEK2_LLM_MODEL` uses) is still accepted as an alias for the same, current pricing. This is the vendor's own documented rename, not this document substituting a similar-but-different model's price. |
| Input (cache miss), off-peak | $0.15 |
| Input (cache miss), peak | $0.30 |
| Input (cache hit), off-peak | $0.003 |
| Input (cache hit), peak | $0.006 |
| Output, off-peak | $0.60 |
| Output, peak | $1.20 |
| Peak window | 01:00–04:00 and 06:00–10:00 UTC, Monday–Friday, excluding Chinese public holidays. All other hours (including weekends and those holidays) are off-peak. |

These three entries are now encoded in `comqutor_alpha/llm/cost_basis.py`'s `_PRICING_USD_PER_MILLION_TOKENS` (off-peak/standard rate as the point estimate) and `_PEAK_PRICING_USD_PER_MILLION_TOKENS` (the peak-rate ceiling), each with the same source/date cited directly in that file's own comments — not duplicated data that could silently drift from this document.

### Models NOT priced here, and why

No other provider/model appears in the current frozen production config, so no other entry was needed this round. The **historical** evaluation models (`anthropic`/`claude-sonnet-4-6`, behind the frozen 82.67%/87.23% scores) are deliberately NOT priced here — they are not part of the current production config this task asked to price, and pricing them would imply a relevance to a future run that would use `deepseek-v4-flash`/`gpt-5.5`/`gpt-5.4-mini` instead.

## 2. T3: recomputed call volume (supersedes the prior ~44-call estimate)

The prior estimate (`~44 logical Provider calls`) assumed both Alpha Classification AND a batched Polarity re-score. The actual driver built this round (`t3_diagnostic_evaluation_driver.py`) implements **only** the Alpha Classification step (see its own `STEPS_COVERED` disclosure) — Polarity is not part of what this specific script would run. The real, current call volume for a full 40-sample T3 run through this driver is:

- **40 logical calls** (one per sample; `alpha_classifier` is confirmed single-claim, never batched, at the real production call site).
- **Actual requests**: 40 at minimum (every call succeeds first try) up to 80 at the configured `--max-retries-per-call 1` default if every single call needed its one allowed retry. Realistically closer to 40–50 based on how rarely a single well-formed call fails outright.

### Cost estimate (assumption-based — no real historical token measurement exists for this exact call yet)

The real, measured PROMPT CHARACTER length for each of the 40 samples' actual `alpha_classifier` request text was computed directly from the real production prompt-construction code this round (`Week2LLMGateway._provider_prompt_prefix` + `alpha_mapper._alpha_taxonomy_request_block`, which embeds the full 10-Alpha taxonomy block into every request): **average 5,501 characters, range 5,284–5,920** across the 40 samples. Converting to a token estimate requires a heuristic (this document uses the common, widely-cited ~4 characters/token approximation for English text — an ASSUMPTION, not a measurement of DeepSeek's specific tokenizer) — **≈1,375 input tokens** per call. Output is a fixed, tiny JSON shape (`{"decision": ..., "selected_alpha_id": ...}`) — assumed **≈20 output tokens**.

| | Off-peak (floor) | Peak (ceiling) |
|---|---|---|
| Per call | (1375/1e6 × $0.15) + (20/1e6 × $0.60) ≈ **$0.00022** | ≈ **$0.00043** |
| 40 calls, no retries | ≈ **$0.0087** | ≈ **$0.0175** |
| 80 actual requests (worst-case, every call retries once) | ≈ **$0.0175** | ≈ **$0.0349** |

**This is an estimate, explicitly distinguished from actual**: it will be superseded by the real, measured `token_usage` this round's own fix to `invoke_json_with_trace` now records for every real call (see `t4_request_level_statistics_offline_prep_2026-09-30b` in `release_manifest.json`) — the very first live T3 run will produce real numbers to replace this assumption, not just confirm it.

## 3. T4: one NVDA Fresh Run — recomputed call-volume estimate

Unlike T3, no new driver script defines T4's exact call pattern — a Fresh Run goes through the full, real `run_streaming_tradingagents_research` entry point end to end (Research Agent multi-agent conversation, then all four Week2 semantic tasks). The closest real reference point is the existing frozen NVDA run (`57d7b4c4-dbb9-4134-b962-ee2a873941cc`), whose own real, persisted `llm_semantic_manifest.json` shows:

| Task | Real logical calls (this reference run) |
|---|---|
| `alpha_classifier` | 499 |
| `evidence_stance_classifier` | 32 (batched, `BATCH_SIZE=10`) |
| `structure_extractor` | 11 |
| `structured_adapter` | 7 (batched) |
| **Total Week2 logical calls** | **549** |
| Total Week2 provider_call_count (includes retries) | 591 |

**This is a reference point from a past run, not a guarantee** — a new NVDA Fresh Run's actual claim count depends on that day's real market/news content, which does not exist yet.

### Research Agent (gpt-5.5 / gpt-5.4-mini) call volume and cost: genuinely UNKNOWN, not estimated

A repo-wide check this round (see `t4_request_level_statistics_offline_prep_2026-09-30b`) confirmed the TradingAgents research-agent layer has **zero historical request-level logging of any kind** — there is no real historical call count or token-usage figure anywhere in this repository for this layer, unlike the Week2 layer above. Per this round's own explicit instruction never to estimate from a proxy, this document reports the Research Agent's own call volume and cost as **UNKNOWN — no real measurement exists yet**, not a guessed number. The `TradingAgentsUsageStatsCallback` added this round (wired at the real entry point, verified in `tests/test_tradingagents_usage_stats_callback.py`) will produce the *first* real measurement the moment an actual Fresh Run executes — that first run's own `tradingagents_llm_usage_summary.json` is the number to read, not anything asserted here in advance.

### Week2 semantic-layer cost estimate (using the reference run's real call counts + the same token-length methodology as T3 above)

Applying the same ~1,375-input/~20-output-token assumption used for `alpha_classifier` above (the only task whose real prompt length was actually measured this round) to all 549 reference-run calls as a rough proxy (each task's real prompt is a different length; this is a single, disclosed approximation, not a per-task measurement):

- 549 calls × ≈$0.00022 (off-peak) ≈ **$0.12**; at peak rate ≈ **$0.24**.
- This almost certainly UNDER-counts `structured_adapter`/`structure_extractor` (which embed full claim batches or structure graphs, likely far longer prompts than a single Alpha-classification request) — reported as a floor, not a realistic total.

### Combined statement

**Total T4 cost is TO BE DETERMINED**: the Week2 portion has a rough, disclosed floor estimate (~$0.12–0.24, likely an undercount); the Research Agent portion is genuinely unknown pending the first real measurement from this round's own new instrumentation. Whoever authorizes a Fresh Run should budget for an unknown Research Agent cost on top of the Week2 floor above, not treat the Week2 figure as the whole cost.

## 4. Assumptions summary (estimate vs. actual, stated once for both sections above)

| Quantity | Status |
|---|---|
| Pricing rates for all 3 models | **Actual** — official, sourced, dated |
| T3's 40-call logical-call count | **Actual** — fixed by the real 40-sample set and the real driver's own single-call-per-sample design |
| T3's per-call token count (~1,375 in / ~20 out) | **Estimate** — real prompt CHARACTER length measured; token conversion uses a disclosed generic heuristic, not DeepSeek's real tokenizer |
| T4's Week2 call-count reference (549) | **Actual, but historical** — a real past run's real number, not a guarantee for a new run |
| T4's Research Agent call count / cost | **Unknown** — no historical measurement exists at all |
