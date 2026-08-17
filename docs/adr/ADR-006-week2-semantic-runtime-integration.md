# ADR-006: Week2 Semantic Runtime Integration

Status:

- `ACCEPTED_FOR_INTEGRATION`
- `DEFAULT_DISABLED`
- `NO_SEMANTIC_AUTHORITY_CHANGE`

Date: 2026-08-05

## Context and provenance

`SOURCE_FROZEN` — Development Plan v1.0 requires LLM JSON retry, task validation, safe deterministic fallback, stable error logs, and an LLM response cache. Those requirements do not transfer semantic authority away from COMQUTOR's existing task validators.

`CURRENT_IMPLEMENTATION` — Before Phase 0.6B, `Week2LLMGateway` already implemented the explicitly enabled Provider path, fixed prompt wrapper and task instructions, strict JSON parsing, bounded retry, caller-side timeout, Provider-call budget, and safe error codes. Adapter, Alpha Mapper, and Structure Extractor already owned their validation and deterministic fallback rules. Phase 0.6A supplied versioned runtime primitives but intentionally left them unintegrated.

`APPROVED_PROJECT_DECISION` — Phase 0.6B minimally connects those primitives to the existing Week2 path. It does not introduce a language-understanding algorithm, change a task prompt, or move semantic authority.

## Decision

1. One live research run may own one `SemanticRuntimeSession`, one append-only recorder, and one injected `LLMResponseCache`. All three Week2 semantic tasks share that session through the existing `Week2LLMGateway`.
2. A session is created only when `COMQUTOR_WEEK2_LLM_ENABLED` is explicitly true and Gateway construction succeeds. The default remains disabled. An explicitly supplied, already-attached session remains an intentional caller-controlled test/integration seam.
3. Gateway request identity and cache lookup happen before Provider work. A cache hit consumes no Provider-call budget and is sent through the same existing task validator used for a Provider candidate.
4. The existing task-specific validators remain final authority:
   - `_validate_llm_batch_enrichment`
   - the Alpha classifier's existing inline admissibility validator
   - `_validated_llm_edges`
5. Only a Provider-success candidate accepted by the task validator, with no fallback or runtime-integrity failure, may create a validated cache entry. Rejected, malformed, timed-out, errored, budget-exhausted, fallback, and cache-hit records are not written to cache.
6. Each logical semantic request creates at most one `SemanticCallRecord`; `retry_count` represents additional Provider attempts. Cache hits use `provider_status=not_called` and do not increment the Gateway's Provider budget.
7. Prompt versions are metadata only:
   - `week2.claim_batch_enrichment.v1`
   - `week2.alpha_classifier.v1`
   - `week2.structure_extractor.v1`

   `prompt_sha256` covers the existing fixed JSON-only wrapper and fixed task instruction, excluding dynamic payload. Neither version nor hash is inserted into the Provider prompt.
8. Provider and model metadata come from the already-selected Gateway configuration. Unavailable identities are recorded as `UNKNOWN_NOT_INSTRUMENTED`; the runtime never introspects or serializes a Provider client.
9. `NullLLMResponseCache` is the default. `RedisLLMResponseCache` remains usable only with an injected client and does not create a Redis or network connection.
10. Explicitly enabled live runs write optional `llm_semantic_calls.jsonl` and `llm_semantic_manifest.json` sidecars. They do not alter the required artifact list or research response. Disabled runs create neither file. An enabled zero-call run writes an empty JSONL and a complete manifest with `record_count=0`, `provider_call_count=0`, and `exact_replay_ready=false`.
11. Raw Provider text is not persisted by this integration: `raw_output_text` and `raw_output_sha256` are null. Approved structured inputs are redacted before persistence. Secret-bearing fields, hidden-reasoning fields, credential-like text, and full local home paths are removed or redacted; any such redaction makes the semantic artifact incomplete and blocks cache writes/readiness.
12. Recorder, cache, and manifest failures are fail-soft with respect to the research result. Recorder failure marks the session degraded/incomplete; cache failure never changes an accepted business result; manifest failure never overwrites the JSONL or fabricates completion.
13. Replay readiness fails closed. A complete nonempty record set is ready only when every call has an accepted saved output and none uses fallback or ends in timeout, Provider error, or exhausted budget. An unresolved call, missing output, failed recorder, incomplete manifest, rejection, or fallback forces readiness false.

## Current implementation boundaries

`CURRENT_IMPLEMENTATION`:

- Week2 LLM execution remains default-disabled.
- The default cache is network-free `NullLLMResponseCache`.
- Redis support remains injected only; no Redis URL is read and no client is constructed.
- Architecture Replay still forces `llm_gateway=None` and imports no Phase 0.6B session integration.
- TradingAgents is unchanged except for its pre-existing Provider factory use by the explicit live Gateway builder.
- Canonical prompt injection and canonical relation prompt behavior are unchanged.
- Claim segmentation and Claim/Evidence pairing are unchanged.
- Alpha eligibility, candidates, threshold, top-three presentation, hard gate, score, and selected status are unchanged.
- Structure edge vocabulary, allowed factors, grammar, merge, dedupe, and graph admission are unchanged.
- Graph, Activation, Exposure, Conflict, and Evidence Stance are unchanged.

## Consequences

An explicitly enabled live run now has an auditable, hash-verified semantic-call stream and derived manifest without making observability a business-path dependency. Cross-run cache identity excludes `run_id`, while saved call identity remains run-local. The Provider budget remains an attempt budget; cache hits are free. Existing callers that do not supply a semantic runtime continue through the legacy `invoke_json` path with the same prompt, payload serialization, retry, timeout, budget, parser, error codes, and return semantics.

Phase 0.6B does not implement Exact Semantic Replay. It only produces the optional inputs that a separately approved replay integration could later consume. It does not implement or modify John's B1/B2/B3/B4/B5/J1/J2/J3 product-semantic work.

## Rejected alternatives

- Letting cache contract validation replace task validation: rejected because the task validator owns semantic admission.
- Caching deterministic fallback or rejected output: rejected because it would turn fallback into semantic authority.
- Automatically constructing Redis from environment configuration: rejected because it introduces hidden network I/O and deployment authority.
- Persisting raw Provider response text: rejected because it expands sensitive-data and hidden-reasoning exposure.
- Making semantic sidecars required run artifacts: rejected because Phase 0.6B must preserve the existing live response and artifact-completion contract.
- Adding session creation to Replay: rejected because Exact Replay is Phase 0.6C work requiring separate approval.

## Next review boundary

Phase 0.6C may be considered only after independent review and explicit approval. Its prerequisites are a verified complete manifest, accepted saved task candidates, fail-closed identity/version checks, a no-Provider/no-network replay guard, and an explicit decision about how replay consumes saved candidates without changing current Architecture Replay semantics.
