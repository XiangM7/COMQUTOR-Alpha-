# Phase 1 §5.1 — Live Shadow Canary Failure Diagnosis

## Status

The original `LIVE_SHADOW_CANARY=FAIL` remains unchanged. This diagnosis used only persisted artifacts and made zero Provider calls.

The failure decomposes into two independent findings: a confirmed Shadow isolation implementation defect, and one correctly fail-closed ambiguous technical quote.

## Failure A — Shadow isolation

Root cause: `_DefaultV4ShadowExecutor` correctly placed its semantic recorder in `structured_adapter_shadow_runtime`, but `build_phase1_master_provider_gateway` constructed `Week2LLMGateway` with the Gateway's canonical default error path. When the technical proposal failed validation, `Week2LLMGateway._log` appended `WEEK2_LLM_VALIDATION_FAILED` to run-root `error_logs/week2_llm_errors.jsonl`.

`build_research_response` reports the existence of that canonical file as `artifacts.week2_llm_error_logs`. Thus the Shadow rejection changed the API response from `false` to `true` even though Legacy semantic and deterministic downstream artifacts were unchanged.

The minimal repair preserves the Gateway's canonical default for authoritative Week2 callers and adds an explicit validated path override. Phase 1 Shadow builders now use:

`structured_adapter_shadow_runtime/error_logs/week2_llm_errors.jsonl`

Offline regression cases cover validation rejection, Provider exception, and malformed output. In every case:

- Legacy-only response equals Legacy-plus-Shadow response;
- canonical `artifacts.week2_llm_error_logs` remains `false`;
- the rejection/error remains visible in Shadow-only diagnostics.

`FAILURE_A_OFFLINE_VERIFICATION=PASS`

## Failure B — Technical ambiguous exact match

Classification: `B1_EXPECTED_SAFE_AMBIGUOUS_REJECTION`.

Persisted facts establish that technical claim index 0, supporting quote index 0 had exactly two byte-exact matches. The resolver processed the proposal with the available deterministic hint machinery but could not reduce those matches to one location. It therefore returned `AMBIGUOUS_MULTIPLE_MATCH`; normalization emitted no admissible source span, and the validator rejected the entire proposal with `SHADOW_SOURCE_SPAN_INVALID`.

This is correct fail-closed behavior. No first-match default, fuzzy matching, normalization, semantic guess, or Provider repair was used. No Evidence from the rejected bundle was admitted.

### Forensic limitation

The immutable rejected semantic-call record contains:

- `raw_output_text=null`
- `raw_output_sha256=null`
- `validated_output=null`

The validation sidecar preserves only `claim_index=0`, `quote_index=0`, `status=AMBIGUOUS_MULTIPLE_MATCH`, and `match_count=2`. It does not preserve the rejected proposal's claim text, quote text, or claim-level `candidate_ids`.

Therefore the exact quote, exact two offsets, and surrounding contexts cannot be recovered from the persisted Canary artifacts. The request contained 26 location hints, but whether the rejected claim emitted a specific candidate reference is likewise not recoverable. Because the quote text is absent, attempting to infer it from repeated substrings in the report would fabricate forensic evidence.

No resolver change was made. The recorded response cannot be replayed because it was not persisted.

`RESOLVER_BEHAVIOR=CORRECT_FAIL_CLOSED`

`TECHNICAL_RECORDED_RESPONSE_OFFLINE_REVALIDATION=NOT_APPLICABLE_RESPONSE_NOT_PERSISTED`

## Decision

Failure A is repaired and verified. Failure B remains an expected safe rejection, and rerunning the same protocol may encounter the same ambiguity. A Product Owner decision is required on duplicate-quote protocol/location binding and rejected-response forensic persistence before a new Canary.

`CANARY_FAILURE_REPAIR=PARTIAL`

`READY_FOR_RECANARY=NO`

`PRODUCTION_AUTHORITY=LEGACY_ADAPTER`

`PRODUCTION_CUTOVER=NOT_RUN`
