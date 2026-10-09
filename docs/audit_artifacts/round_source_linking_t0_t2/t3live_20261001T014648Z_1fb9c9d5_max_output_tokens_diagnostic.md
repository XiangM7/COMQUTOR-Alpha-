# Diagnostic: `--max-output-tokens 200` real behavior during `t3live_20261001T014648Z_1fb9c9d5`

Scope: this document only investigates why real `output_tokens` averaged ~881/call (far above the configured 200) during the already-completed, already-authorized execution `t3live_20261001T014648Z_1fb9c9d5`. **No prediction was re-run, no new paid call was made, no original prediction/call-log file was modified** (`t3_eval_records.jsonl`, `t3_eval_semantic_call_records.jsonl`, `llm_semantic_calls.jsonl`, `t3_eval_summary.json` are all byte-for-byte as the real run left them). Every claim below is labeled as either a fact confirmed from this execution's own saved records, a fact confirmed by local offline reproduction, a fact confirmed from DeepSeek's own public documentation, or an inference that remains unconfirmed.

## 1. Actual endpoint and the real serialized request field

**What the saved records can and cannot show**: `comqutor_alpha.llm_runtime.recorder.SemanticCallRecorder` persists `input_payload` (COMQUTOR's own request to the LLM gateway — the claim/evidence/taxonomy JSON), not the raw HTTP request LangChain/the `openai`-compatible SDK sent to DeepSeek's server. **The actual historical HTTP request body for this run's 40 real calls was never logged and cannot be retrieved.** The following is offline reproduction using the IDENTICAL frozen construction path and parameters this run actually used, not a record of the actual historical requests.

**Offline reproduction** (`tradingagents.llm_clients.factory.create_llm_client(provider="deepseek", model="deepseek-v4-flash", max_tokens=200, timeout=45, max_retries=0)` — the exact call `comqutor_alpha.structure_engine.week2_llm.build_server_week2_llm_gateway` makes, with only the `httpx` transport replaced by a request-capturing `httpx.MockTransport`):

- **Endpoint actually targeted**: `https://api.deepseek.com/chat/completions` (confirmed: `DeepSeekChatOpenAI`'s `ProviderSpec` sets no `use_responses_api`, so this goes through the standard OpenAI-compatible Chat Completions path, not the Responses API).
- **The real serialized request body's token-cap field**:
  ```json
  { "...": "...", "max_completion_tokens": 200, "stream": false }
  ```
  **Not `max_tokens`, and not `max_output_tokens`.** Confirmed reproducible across repeated calls (not a one-off artifact).

**Why**: traced to `langchain_openai`'s own installed library code (`.venv/lib/python3.13/site-packages/langchain_openai/chat_models/base.py`, both `_default_params` and `_get_request_payload`):
```python
# max_tokens was deprecated in favor of max_completion_tokens
# in September 2024 release
if "max_tokens" in payload:
    payload["max_completion_tokens"] = payload.pop("max_tokens")
```
This rename is **unconditional** — applied to every model, not gated on recognizing an OpenAI "reasoning model" name. `comqutor_alpha`'s own `DeepSeekChatOpenAI`/`NormalizedChatOpenAI` classes (`tradingagents/llm_clients/openai_client.py`) do not override this method, so the rename is never corrected for the DeepSeek target.

**DeepSeek's own documented parameter name** (official API reference, `https://api-docs.deepseek.com/api/create-chat-completion`, fetched this round): the complete request-body parameter list is `messages, model, thinking, max_tokens, response_format, stop, stream, stream_options, temperature, top_p, tools, tool_choice, logprobs, top_logprobs, user_id, frequency_penalty, presence_penalty`. **`max_completion_tokens` does not appear anywhere in DeepSeek's own documented parameter list.**

## 2. Raw usage vs. aggregation logic — checked for double-counting

**Arithmetic check against the actual saved records** (both `t3_eval_semantic_call_records.jsonl` and `llm_semantic_calls.jsonl` are byte-identical, confirmed):
- `sum(record["token_usage"]["output_tokens"] for the 40 real records) == 35,260`, verified directly against the file — this number **is** exactly the sum of the 40 individually-recorded `output_tokens` values. No duplication in the summation itself.
- For every one of the 40 records, `input_tokens + output_tokens == total_tokens` exactly — internally consistent.

**Checked for double-counting in extraction** (`comqutor_alpha.structure_engine.week2_llm._response_token_usage`): reads exactly ONE value for `output_tokens`, from the first match among `("output_tokens", "completion_tokens", "output_token_count")` — it never adds two fields together. No bug found here.

**Checked for double-counting in LangChain's own `usage_metadata` construction** (offline reproduction, a fixed response shaped like a real reasoning-model completion with `usage.completion_tokens=1049` AND a separate `usage.completion_tokens_details.reasoning_tokens=1000` sub-field, mirroring OpenAI's own documented convention that `completion_tokens` is already inclusive of reasoning tokens): the resulting `AIMessage.usage_metadata` was `{"output_tokens": 1049, ..., "output_token_details": {"reasoning": 1000}}` — **`output_tokens` equals the raw `completion_tokens` value exactly; `reasoning` under `output_token_details` is a diagnostic sub-breakdown, never an additional summand.** No double-counting found at this layer either.

**What remains unconfirmed**: whether each of the 40 real historical responses' own raw `completion_tokens` field (never logged, cannot be recovered) itself correctly reflected DeepSeek's real token accounting. This document can confirm the extraction and aggregation code is faithful to whatever that raw field said; it cannot independently re-verify DeepSeek's own accounting for calls that already completed and were never logged at the raw-response level.

## 3. Evidence boundary, stated explicitly

- **Confirmed, directly, from this execution's own real saved records**: 40/40 calls succeeded on the first attempt, zero retries, `provider_status=success` for all, real token usage 100% present (never estimated), arithmetic in §2 above.
- **Confirmed, by offline reproduction using the identical frozen config** (not a record of the actual historical requests, since those were never logged): the real serialized request sends `max_completion_tokens`, not `max_tokens`; the real endpoint is DeepSeek's standard chat-completions path; LangChain's usage parsing does not double-count reasoning tokens.
- **Confirmed, from DeepSeek's own public API documentation** (fetched this round, not assumed from memory): their documented parameter name is `max_tokens`; `max_completion_tokens` appears nowhere in their documented parameter list.
- **Not confirmed**: how DeepSeek's real server actually handled the unrecognized `max_completion_tokens` field during the 40 real historical calls (silently ignored vs. partially honored vs. something else) — this would require either a real DeepSeek server response/error detail this round never captured (the real run's own responses were accepted/parsed successfully, which only shows the request was not rejected outright) or an explicit DeepSeek statement on unknown-field handling, neither of which this investigation has.

## 4. Classification, per the available evidence

This is, on the evidence gathered, an **API field mapping issue**: a library-level, unconditional `max_tokens`→`max_completion_tokens` rename (`langchain_openai`'s own code, following OpenAI's own September 2024 deprecation) that this codebase's DeepSeek-specific client subclass does not correct for, sent against a provider whose own documented API uses the older `max_tokens` name and does not list `max_completion_tokens` at all. This is **not** classified as "parameter omission" (a value was supplied and did reach request-serialization, just under an unexpected key) and **not** classified as "statistics/aggregation problem" (§2 found no double-counting at any layer this round could inspect). It is **not yet classified as confirmed, unexplainable Provider behavior** either — the field-mapping mismatch is a sufficient, well-evidenced candidate explanation for why the sent cap was not observed in the real output-token counts, but this document does not claim it as a proven root cause, since DeepSeek's actual server-side handling of the unrecognized field was never directly observed. **"Reasoning tokens are exempt from the output cap" is explicitly NOT asserted as a confirmed root cause anywhere in this document** — the more concrete, evidenced finding is the field-name mismatch itself; whether DeepSeek would have honored the cap even under the correct field name for its reasoning output specifically remains a separate, open question this round's evidence does not settle.

## 5. Real usage vs. the original (public-pricing-based) cost estimate — historical estimate preserved, not overwritten

The original estimate, from `t3_t4_pricing_reference_2026-09-30.md` §2, is kept as the historical record it was: **~1,375 input / ~20 output tokens per call (assumption)**, ≈$0.009–$0.035 total for 40–80 calls (**an estimate, computed from public pricing, never a confirmed actual charge**).

Real measured usage from this execution (addendum, not a replacement of the above):

| | Estimated (pre-run) | Actual (`t3live_20261001T014648Z_1fb9c9d5`, real Provider-reported usage) |
|---|---|---|
| Calls | 40–80 | 40 (exactly 1 attempt each, 0 retries) |
| Avg input tokens/call | ~1,375 | 1,197.5 |
| Avg output tokens/call | ~20 | 881.5 |
| Total tokens | ~56,000–112,000 (40–80 calls × ~1,395) | 83,160 (47,900 in + 35,260 out) |
| Cost, off-peak public rate | ~$0.0087 (40 calls) | **$0.028 (estimate, see caveat below)** |
| Cost, peak public rate | ~$0.0175 (40 calls) | **$0.057 (estimate, see caveat below)** |

**Caveat, stated once here rather than implied**: both "actual" cost figures above are computed from the officially published DeepSeek per-token price (`t3_t4_pricing_reference_2026-09-30.md`) applied to the real, Provider-reported token counts — they are **cost estimates based on public pricing, not a confirmed actual deduction**. No DeepSeek billing statement or account-balance change was checked against this execution. Which of the two bounds (off-peak vs. peak) actually applied depends on whether the real call timestamps (~01:46–01:50 UTC on 2026-10-01) fall inside DeepSeek's own peak window, which also excludes Chinese public holidays — not independently resolved here.

## What this document does not do

It does not modify `t3_eval_records.jsonl`, `t3_eval_semantic_call_records.jsonl`, `llm_semantic_calls.jsonl`, or `t3_eval_summary.json` for execution `t3live_20261001T014648Z_1fb9c9d5` — all four remain exactly as the real run produced them. It does not re-run any prediction, make any new paid Provider call, or start Plan B / a Fresh Run. It does not change `comqutor_alpha/structure_engine/week2_llm.py`, `tradingagents/llm_clients/openai_client.py`, or any other production code — the field-mapping finding above is reported, not fixed, since fixing it was not requested this round and doing so would itself require either a real verifying call (not authorized) or further, out-of-scope design work (e.g., whether to override `_get_request_payload` for `DeepSeekChatOpenAI` to preserve `max_tokens`, and whether that is even desirable given the uncertainty in §3).

## Addendum (2026-10-01, scope-limited DeepSeek parameter compatibility fix round)

**The field-mapping issue identified in §1/§4 above is now fixed in subsequent code.** `DeepSeekChatOpenAI._get_request_payload` (`tradingagents/llm_clients/openai_client.py`) now renames `max_completion_tokens` back to `max_tokens` in the final serialized payload, scoped only to the DeepSeek-specific client subclass (`NormalizedChatOpenAI`, used by every other OpenAI-compatible provider, and the native OpenAI/Anthropic/Google/Bedrock clients, are all unaffected — confirmed by targeted regression, not merely by class-hierarchy inspection). Verified, through the real `build_server_week2_llm_gateway` → `Week2LLMGateway.invoke_json` → real `DeepSeekChatOpenAI` → `httpx.MockTransport` path (`tests/test_week2_llm.py::test_server_gateway_deepseek_max_tokens_reaches_real_serialized_request`), that configuring `max_tokens=200` now produces a real serialized request body containing `"max_tokens": 200`, with `max_completion_tokens` absent.

**This fix does NOT retroactively apply to or explain what actually happened during the already-completed `t3live_20261001T014648Z_1fb9c9d5` run.** That run's own real output-cap enforcement status **remains UNCONFIRMED** — specifically:

- The fix changes code that did not exist at the time `t3live_20261001T014648Z_1fb9c9d5` ran. The 40 real historical calls in that execution were made against the pre-fix code path, which sent `max_completion_tokens` (per §1's offline reproduction using that run's identical frozen config) — the post-fix `max_tokens` field was never sent during the actual historical run.
- §3's open question — how DeepSeek's real server actually handled the unrecognized `max_completion_tokens` field during those 40 real historical calls — is **still not resolved** by this fix. Fixing the field name forward does not retroactively reveal what the server did with the wrong field name in the past.
- The corrected/fixed configuration (`max_tokens` field, verified via the test above) is **not** to be written into this document, or anywhere else, as if it were `t3live_20261001T014648Z_1fb9c9d5`'s own actual historical request configuration. That run's actual, as-sent configuration is, and remains, exactly what §1 above already states: `max_completion_tokens: 200` (offline-reproduced from the pre-fix code), not `max_tokens: 200`.
- No new real Provider call was made as part of this fix-and-verify round (zero real Provider calls; the verification above uses `httpx.MockTransport`, not a live DeepSeek call), and the 40 frozen samples were not re-run. Whether a *future* real run with the fixed code achieves the intended output-length cap is a separate, not-yet-tested question that any future real run must state explicitly (its own configuration and budget), rather than assume from this fix.
