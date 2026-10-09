# T3 offline prep, item 4 (2026-09-30 corrected): per-step model config comparison

**Correction of the 2026-09-29 version of this document**: that version correctly identified the Alpha-classification provider/model mismatch, but then also compared the Research Agent's own model (gpt-5.5/gpt-5.4-mini) as if it were additional evidence for "Alpha verification is inconsistent." That comparison is irrelevant on its own terms: the Research Agent never performed Alpha classification in either the historical evaluation or production, so its model identity proves nothing about Alpha-classification consistency. This document instead maps each of the five real, distinct production steps separately, states each step's own precise historical-vs-current facts, and marks anything not independently confirmed as unknown rather than assumed.

No paid Provider calls were made to produce this document — every fact below is read from already-committed config files or already-persisted historical audit artifacts.

## Step 1: Research Agent (market/news/fundamentals/sentiment analysts, bull/bear researchers, trader, risk analysts)

| Field | Value |
|---|---|
| Real production call site | `tradingagents/agents/analysts/*.py`, `tradingagents/agents/researchers/*.py`, etc. (the original TradingAgents multi-agent graph) |
| Provider / model | `openai` / `deep_think_llm=gpt-5.5`, `quick_think_llm=gpt-5.4-mini` (`tradingagents/default_config.py`) |
| Prompt / code version | N/A — a full, multi-turn, tool-calling conversational agent, not a single versioned Week2 semantic-task prompt |
| Batch / single | N/A — not a batch-classification call at all |
| Historical validation config | **NONE FOUND** |
| Evidence location | N/A — no independent accuracy validation of this step exists anywhere in `docs/audit_artifacts/` (confirmed by directory search, not assumed) |
| Verdict | **Needs first validation, not re-validation** — there is nothing to compare against, historical or otherwise |

## Step 2: Extraction (`structured_adapter`, task `claim_batch_enrichment`)

| Field | Value |
|---|---|
| Real production call site | `comqutor_alpha/structure_engine/structured_output_adapter.py::_llm_batch_enrichment`, invoked from `save_structured_agent_outputs` |
| Provider / model | `deepseek` / `deepseek-v4-flash` (`.env` `COMQUTOR_WEEK2_LLM_PROVIDER`/`COMQUTOR_WEEK2_LLM_MODEL`; cross-confirmed against a real historical run's own persisted `llm_semantic_manifest.json`) |
| Prompt / code version | `week2.claim_batch_enrichment.v1` — verified UNCHANGED (live-computed `Week2LLMGateway.prompt_identity_sha256("claim_batch_enrichment")` matches the already-pinned Exact-Replay identity hash exactly, confirmed directly this round) |
| Batch / single | **BATCH** — one call covers multiple segments (`batch_segments`) per invocation |
| Historical validation config | **NONE FOUND** |
| Evidence location | N/A — `docs/audit_artifacts/structured_adapter_gap_matrix.csv` is mechanism/contract documentation (Q&A format), not an accuracy score |
| Verdict | **Needs first validation, not re-validation** |

## Step 3: Alpha Classification (task `alpha_classifier`)

| Field | Value |
|---|---|
| Real production call site | `comqutor_alpha/structure_engine/alpha_mapper.py::map_structured_records`, invoked via `save_alpha_matches(run_id, output_root=..., llm_gateway=...)` — this REAL call site never passes `use_batched_classifier`, so it uses that parameter's own default |
| Provider / model | `deepseek` / `deepseek-v4-flash` |
| Prompt / code version | `week2.alpha_classifier.v6` (current, live) |
| Batch / single | **SINGLE** — `use_batched_classifier` defaults to `False` and is never overridden at the real production call site; independently confirmed by a real historical run's own manifest (`"alpha_classifier": 754` calls, never `"alpha_classifier_batch"`) |
| Historical validation config | provider=`anthropic`, model=`claude-sonnet-4-6`; **SINGLE** (confirmed: `logical_provider_calls=150` for `rows_total=150`, a 1:1 per-row call ratio); prompt/code version **UNKNOWN** — only a classifier hash (`candidate3_classifier_hash_sha256 = d53b2d75...`) was recorded, not a human-readable version string, and it cannot be reverse-mapped to a version label from what is on file |
| Evidence location | `docs/audit_artifacts/v0_2_candidate3_final_validation_result.json`, `docs/audit_artifacts/v0_2_candidate3_final_provider_audit.json` |
| Verdict | **Needs re-validation.** The calling CONVENTION matches (single-claim, both historical and current) — only the underlying model differs (Anthropic Claude Sonnet 4.6 historically vs. DeepSeek v4 Flash today). This is the precise, narrow reason the frozen 82.67% score cannot be inherited: not because "the whole pipeline changed," but because this ONE step's actual predictive model changed while its calling shape stayed the same. |

## Step 4: Polarity (Evidence Stance, task `evidence_stance_classifier`)

| Field | Value |
|---|---|
| Real production call site | `comqutor_alpha/structure_engine/evidence_stance_llm.py::apply_llm_stance_upgrade` |
| Provider / model | `deepseek` / `deepseek-v4-flash` |
| Prompt / code version | `evidence_stance.llm_classifier.v3` (current, live) |
| Batch / single | **BATCH** (`BATCH_SIZE = 10`) |
| Historical validation config | provider=`anthropic`, model=`claude-sonnet-4-6`; prompt_version=`evidence_stance.llm_classifier.v3` — **the exact same version string as current production**; **BATCH** (`batch_count=15` for 141 samples, ≈9–10 per batch, consistent with `BATCH_SIZE=10`) |
| Evidence location | `docs/audit_artifacts/item2_blind_holdout2_provider_call_log.json` (`phase3_b1_evaluation`), `docs/audit_artifacts/item2_blind_holdout2_summary.json` (the 87.23% score) |
| Verdict | **Needs re-validation**, for an even narrower reason than Alpha Classification: the prompt version AND the batching convention are both independently confirmed identical to production today. The ONLY difference is the model itself (Anthropic Claude Sonnet 4.6 historically vs. DeepSeek v4 Flash today). This is the cleanest possible case for "the harness and the prompt are proven; only the model swapped" — still enough, on its own, to require a fresh measurement before the 87.23% figure could ever be claimed for the current model. |

## Step 5: Structure (task `structure_extractor`)

| Field | Value |
|---|---|
| Real production call site | `comqutor_alpha/structure_engine/structure_extractor.py::_llm_edges`, called per-claim when `llm_gateway` is set and the claim has ≥2 factors |
| Provider / model | `deepseek` / `deepseek-v4-flash` |
| Prompt / code version | `week2.structure_extractor.v1` (current, live; verified unchanged via the same live-hash method as Step 2) |
| Batch / single | **SINGLE** — confirmed per-claim (`structure_extractor_gap_matrix.csv`: "Real LLM call: Yes, per-claim, only when llm_gateway is not None and len(factors)>=2") |
| Historical validation config | **NONE FOUND** |
| Evidence location | N/A — no independent accuracy validation of this step exists |
| Verdict | **Needs first validation, not re-validation** |

## Summary table

| Step | Config identical to historical validation? | Historical score exists? | Can the historical score be inherited? |
|---|---|---|---|
| Research Agent | N/A (no historical validation) | No | N/A |
| Extraction | N/A (no historical validation) | No | N/A |
| Alpha Classification | Calling convention (single) matches; model differs | Yes, 82.67% | **No** — model differs |
| Polarity | Prompt version AND batching convention match; model differs | Yes, 87.23% | **No** — model differs |
| Structure | N/A (no historical validation) | No | N/A |

**Explicit statement per the task's own requirement**: the historical 82.67% (Alpha Classification) and 87.23% (Polarity) scores are NOT the current production pipeline's existing scores, for the specific, narrow, verified reason above (provider/model swap on an otherwise-matching harness) — not a general, unverified assumption that "everything changed." Research Agent, Extraction, and Structure have never been independently validated at all; this is reported as a genuine, pre-existing gap, not newly introduced by this round's own work. This round completes offline preparation only; no paid-model prediction was run to produce a new score for any step.
