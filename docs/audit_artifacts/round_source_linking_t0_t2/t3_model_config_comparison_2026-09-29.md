# T3 offline prep, item 5(a): actual product vs. historical evaluation model configuration

This is a factual comparison only — no new Provider calls, no Fresh Run. Every value below is read directly from already-committed config files or already-persisted historical artifacts; none is invented.

## Step 1: identify the historical evaluation's own model

Source: `docs/audit_artifacts/v0_2_candidate3_final_validation_result.json` (the artifact behind the frozen "Alpha 82.67%" score) and `docs/audit_artifacts/v0_2_final_delivery_package.md` ("Candidate 3 classifier `d53b2d75...`, batch `a03c8f67...`, permanently frozen for this validation cycle").

| Field | Value |
|---|---|
| `provider` | `anthropic` |
| `model_name` | `claude-sonnet-4-6` |
| `candidate3_classifier_hash_sha256` | `d53b2d7511f4c4a8089db746d09e4c79cb38f22597dac6459920ca3deac1171d` |
| `candidate3_batch_hash_sha256` | `a03c8f673ffd387a866bc8dd585c4c96cf5464b80a50cb6e4c3fc5f894f68379` |
| Task evaluated | Alpha classification only (given a frozen claim/evidence pair, select the matching Alpha or NONE) |
| Sample count | 150 (Final Gold v1), independent of whatever model originally wrote the underlying claim/evidence text |

The companion "Polarity 87.23%" score (`item2_blind_holdout2_summary.json`) evaluates a *different* task (evidence stance / polarity), not re-checked here since item 5 is scoped to the Alpha-classification errors (A304/A101/A103).

## Step 2: identify the ACTUAL production model(s) — there are two, not one

Production has two independently-configured model layers, and neither matches the historical evaluation's model:

### 2a. Week2 semantic layer (alpha_classifier / structured_adapter / structure_extractor / evidence_stance_classifier) — the layer the historical evaluation actually tested

Source: `.env` (this machine's real, currently-active configuration) and confirmed against a real historical production run's own persisted manifest (`outputs/runs/ded99ecd-a186-4a90-859e-0f1a0efa43db/llm_semantic_manifest.json`, the canonical NVDA run — `"models": ["deepseek-v4-flash"]`, matching `.env` exactly).

| Field | Value |
|---|---|
| `COMQUTOR_WEEK2_LLM_PROVIDER` | `deepseek` |
| `COMQUTOR_WEEK2_LLM_MODEL` | `deepseek-v4-flash` |
| Gate | `COMQUTOR_WEEK2_LLM_ENABLED` (must be explicitly set `true` in the operator's own shell; see this session's own memory note on this gate never living in `.env`) |
| Prompt version actually used today | `week2.alpha_classifier.v6` (current, live — see `week2_llm.py`'s own `_TASK_RUNTIME_METADATA`) |

### 2b. Original TradingAgents research-agent layer (market/news/fundamentals analysts, bull/bear researchers, trader, risk analysts — the agents that WRITE the raw claim/evidence text the Week2 layer later classifies)

Source: `tradingagents/default_config.py`.

| Field | Value |
|---|---|
| `llm_provider` | `openai` |
| `deep_think_llm` | `gpt-5.5` |
| `quick_think_llm` | `gpt-5.4-mini` |

## Step 3: the direct comparison

| Layer | Historical Alpha-classification evaluation | Actual product today |
|---|---|---|
| Provider | Anthropic | DeepSeek |
| Model | `claude-sonnet-4-6` | `deepseek-v4-flash` |
| Prompt version | Whatever "Candidate 3" used at the time (not independently re-derivable from the frozen hash alone without the original prompt text on file at that commit; not re-verified here) | `week2.alpha_classifier.v6` (current) |
| Task | Alpha classification on a FROZEN, already-written claim/evidence pair | Alpha classification on a live claim/evidence pair, freshly written by the `gpt-5.5`/`gpt-5.4-mini` research-agent layer |

**Conclusion, stated plainly:** the historical 82.67%/87.23% scores measure a *different provider and a different model* than what actually runs in production today. This is exactly why Section 六 of this round's own task sheet requires these scores to remain historical, never inherited by the current version — not a new conclusion, but now backed by the specific, concrete model-identity evidence above rather than asserted as a general principle only.

## Honest scope note

This comparison identifies *which models differ*; it does not re-run the historical evaluation against `deepseek-v4-flash` (that would be a live, paid Provider evaluation — explicitly T3 work this round does not execute, per the task sheet's own "本轮不执行 T3 的付费模型验证"). The root-cause analysis in the companion document instead uses the historical evaluation's own already-paid-for, already-frozen error data to build reusable diagnostic material for whenever that live T3 evaluation is authorized.
