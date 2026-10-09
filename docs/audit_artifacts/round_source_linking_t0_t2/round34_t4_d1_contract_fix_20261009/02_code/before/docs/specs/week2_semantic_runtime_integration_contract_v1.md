# Week2 Semantic Runtime Integration Contract v1

Status: `APPROVED_PROJECT_DECISION`; `DEFAULT_DISABLED`; `NO_SEMANTIC_AUTHORITY_CHANGE`.

This contract defines the Phase 0.6B integration between the existing COMQUTOR Week2 semantic callers, `Week2LLMGateway`, and the Phase 0.6A `llm_runtime` primitives. The underlying record, cache-entry, canonical JSON, and manifest schemas remain those defined by `llm_semantic_call_contract_v1.md`.

## Session lifecycle

A live `run_research_request` creates at most one run-local `SemanticRuntimeSession`, and only after all of the following are true:

1. the existing `COMQUTOR_WEEK2_LLM_ENABLED` opt-in resolves true;
2. a current run directory exists;
3. a real `Week2LLMGateway` was created or explicitly injected;
4. that Gateway does not already own an explicitly injected session.

The session uses `execution_mode=live`, the current `run_id` and run directory, explicit Gateway provider/model metadata, one recorder, and one cache. The default cache is `NullLLMResponseCache`; an alternative is used only when explicitly injected by the caller. The same Gateway and session flow through Adapter, Mapper, and Extractor.

On normal research completion, the route asks the session to produce a complete manifest. On an exception, it asks for an incomplete manifest. Finalization is best-effort and cannot change the research response. Replay does not create or finalize a session.

## Gateway backward compatibility

`Week2LLMGateway.invoke_json(task, payload, validator)` remains the public compatibility API. With `semantic_runtime=None`, it uses the legacy path and preserves:

- the exact fixed prompt wrapper and task instruction text;
- `json.dumps(dict(payload), ensure_ascii=False, default=str)` payload serialization;
- strict JSON object parsing;
- retry count, timeout, and Provider-call budget defaults;
- Provider client construction arguments;
- stable error-code and fallback behavior;
- the prior return value (`validator(parsed)` or `None`).

`invoke_json_with_trace` is an additive API. It returns the parsed candidate, task-validated caller value, trace handle, cache/Provider status, retry/attempt counts, and stable error metadata. The prompt version and prompt hash are metadata and are never appended to the Provider message.

## Logical-call lifecycle

One caller request to one task is one logical semantic call, regardless of retry count:

1. Allocate a unique call ID and strictly increasing run-local `call_sequence`.
2. Sanitize the approved task input and calculate its canonical `input_sha256`.
3. Calculate prompt metadata and the cross-run cache key.
4. Attempt a cache read.
5. On a usable hit, run the current task validator. No Provider call or budget reservation occurs.
6. On miss or rejected cache candidate, execute the existing bounded Provider loop.
7. Strictly parse each response and run the same task validator. Existing retry/error behavior applies.
8. Return the candidate/validated caller value to the existing semantic caller.
9. The caller decides whether the result is actually admitted or whether its existing deterministic fallback is used.
10. Finalize exactly one record. Only an admitted Provider-success candidate is cache-write eligible.

Outstanding/unfinalized trace handles make finalization incomplete and prevent exact readiness.

## Prompt and request identity

The metadata-only versions are:

| Gateway task | Semantic task | Prompt version |
|---|---|---|
| `claim_batch_enrichment` | `structured_adapter` | `week2.claim_batch_enrichment.v1` |
| `alpha_classifier` | `alpha_classifier` | `week2.alpha_classifier.v1` |
| `structure_extractor` | `structure_extractor` | `week2.structure_extractor.v1` |

`prompt_sha256` hashes only the exact fixed shared JSON-only wrapper, exact fixed task instruction, and the source-template identity separator `\\nINPUT_JSON:\\n`. The Provider still receives the unchanged rendered newline separator `\nINPUT_JSON:\n`; the identity form is metadata only. Dynamic payload is excluded. `input_sha256` hashes the sanitized structured payload separately. Neither `input_sha256` nor the cache key includes `run_id`; the call record still contains `run_id` for provenance.

Provider/model fields use the already-resolved configuration. Unknown metadata is the literal `UNKNOWN_NOT_INSTRUMENTED`; no client reflection, environment dump, API key, authorization header, or client representation is allowed.

## Validation authority

Gateway parsing is not semantic admission. Final authority remains:

| Caller | Final task validator | Preserved fallback |
|---|---|---|
| Structured Output Adapter | `_validate_llm_batch_enrichment` | deterministic segmented enrichment |
| Alpha Mapper | existing inline candidate/admissibility validator | precomputed deterministic mapping |
| Structure Extractor | `_validated_llm_edges` plus the existing nonempty-use condition | deterministic relation rules |

A cache hit must pass the same validator. Cache schema/hash validation checks storage integrity only and cannot substitute for task validation. Empty accepted edge arrays remain behaviorally equivalent to the prior path: the caller uses its existing deterministic relation fallback and records the logical call as fallback/rejected for readiness purposes.

## Cache order and eligibility

Read order is identity → cache read → cache contract/hash verification → task validation → Provider miss/fallback when unusable. A corrupt entry is fail-soft, receives a stable reason code, never enters downstream code, and may be followed by the normal Provider path.

Write happens only after the caller finalizes all of these as true:

- Provider status is `success`;
- strict JSON parsing succeeded;
- the current task validator accepted the candidate;
- caller admission did not select fallback;
- validated output is canonical, hashable, and secret-free;
- recorder append succeeded and the session is not incomplete;
- this was not already a cache hit.

No raw response, rejected candidate, malformed JSON, timeout, Provider error, exhausted budget, deterministic fallback, partial result, Evidence Stance output, Graph/Activation/Conflict output, or cache-hit record may be inserted.

A cache-write failure marks the session degraded but preserves the accepted semantic result and saved call. It does not invoke the Provider again or trigger fallback. Redis is supported only through an injected client; constructor/import paths do not connect, and the default remains the null cache.

## Provider budget and retries

`Week2LLMGateway.call_count` and `max_calls` continue to count actual Provider attempts, not semantic requests. Cache hits reserve zero calls. Under the null cache, call count and retry behavior match the legacy path. `retry_count` is the number of additional attempts beyond the first. A fresh request blocked before any attempt uses `provider_status=budget_exhausted`; if budget is reached after a real attempt, the record retains the last actual Provider status so `provider_call_count` remains derivable.

## Artifacts

When explicitly enabled and a Gateway/session exists, the live run may add:

- `llm_semantic_calls.jsonl`: append-only, one record per finalized logical call;
- `llm_semantic_manifest.json`: atomic, derived counts/hash/completion/readiness.

They are optional sidecars and are not added to the existing required artifact list or public response artifact map. Disabled runs create no session and neither file. Enabled zero-call runs create an empty calls file and a complete, verified manifest with zero records/calls and readiness false. Tests write only below pytest temporary directories; Phase 0.6B does not modify historical run or replay artifacts.

## Sensitive-data policy

Default records always set `raw_output_text=null` and `raw_output_sha256=null`; SDK token usage remains null when unavailable. Persisted input is limited to the structured payload already sent to the task. Sanitization removes credential and hidden-reasoning keys and redacts bearer values, credential-like assignments, secret-token forms, and complete local home paths. The same policy is applied defensively to an accepted candidate before persistence.

Any redaction marks the session incomplete, blocks cache writes, and makes exact readiness false. Raw exception bodies, tracebacks, Provider client representations, full environment mappings, cookies, authorization values, and chain-of-thought are never persisted.

## Failure and degraded behavior

- Cache read corruption or task-invalid cached content becomes a safe miss and stable diagnostic; it never bypasses the Provider/fallback path.
- Cache write failure leaves the accepted caller result and saved record unchanged.
- Recorder initialization/append/integrity failure marks the session incomplete and cannot cause a second Provider call.
- Manifest failure does not truncate or replace the calls file and does not fabricate a complete manifest.
- Session construction/finalization errors are caught at the live route boundary and cannot alter the business response.
- Deterministic fallback, task validator behavior, and downstream stage ordering remain unchanged.

## Manifest semantics

`complete=true` means the semantic session finalized normally and the calls file is readable, contract-valid, and self-consistent. It does not claim that every Provider call succeeded or that semantic quality is correct.

`exact_replay_ready=true` requires a complete, nonempty record set in which every record is accepted, has a hash-valid saved candidate, uses no fallback, and has no timeout, Provider error, or budget exhaustion. It is false for zero calls, an unresolved logical call, missing output, rejected/not-run validation, fallback, recorder corruption, or incomplete finalization.

Phase 0.6B produces readiness evidence but does not execute Exact Semantic Replay.

## Default-disabled and boundary guarantees

This phase does not change the default LLM setting, any prompt, Provider/model selection, Claim/Evidence rules, Alpha taxonomy/eligibility/threshold/score/selection, Structure relation grammar/admission, Graph, Activation, Exposure, Conflict, Evidence Stance, TradingAgents, canonical prompt injection, or Architecture Replay. It creates no database schema or migration and performs no default Redis/network action.

## Non-goals and Phase 0.6C prerequisites

Non-goals include new semantic algorithms, semantic-quality acceptance, raw response retention, Redis deployment activation, a required-sidecar migration, exact replay execution, replay fixture synthesis, and John's later B1/B2/B3/B4/B5/J1/J2/J3 features.

Phase 0.6C requires independent review and explicit approval. At minimum it must define verified artifact selection, exact task/input/prompt/model identity checks, fail-closed behavior for missing/rejected/fallback records, a hard no-Provider/no-network/no-database replay boundary, and compatibility with the current Architecture Replay contract.
