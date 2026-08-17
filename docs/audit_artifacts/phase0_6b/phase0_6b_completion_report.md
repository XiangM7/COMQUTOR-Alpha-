# Phase 0.6B Completion Report

Final gate: `PASS`

Phase 0.6B minimally integrates the Phase 0.6A semantic runtime into the existing, default-disabled Week2 LLM path. It adds run-local call recording, accepted-only validated cache wiring, optional live sidecars, and fail-closed manifest finalization without changing semantic authority or downstream business artifacts.

## Repository and scope

- Branch: `comqutor-structure-layer`
- HEAD: `b5837e80a4550fc35165d0013a8ef0f27ccb4c8f`
- Dirty worktree: preserved; 174/174 strictly protected preexisting files retain content and mtime.
- Commit/push/reset/restore/clean/stash: none.
- Production changes: `llm_runtime` session/recorder/manifest exports, Week2 Gateway, minimal Adapter/Mapper/Extractor finalization, and live route session lifecycle only.
- TradingAgents, Replay, Graph, Activation, Conflict, Exposure, canonical prompt injection, canonical relation prompt, frontend, migrations, schemas, and historical outputs: unchanged.

## Runtime and Gateway

One live run now uses one shared `SemanticRuntimeSession`, recorder, and injected cache. `Week2LLMGateway.invoke_json` remains backward compatible when no runtime is attached. The traced path records one logical call across retries, checks cache before Provider work, re-runs the existing task validator on a cache hit, and leaves final admission/fallback to the caller.

The three metadata prompt versions are `week2.claim_batch_enrichment.v1`, `week2.alpha_classifier.v1`, and `week2.structure_extractor.v1`. Their frozen hashes match the startup baseline. The Provider prompt and dynamic payload bytes are unchanged. Timeout 15 seconds, retry count 1, max calls 32, Provider selection, and model selection are unchanged.

The default cache is `NullLLMResponseCache`. Redis remains an injected-client adapter; Phase 0.6B creates no Redis client or connection. Unknown provider/model metadata uses `UNKNOWN_NOT_INSTRUMENTED`.

## Persistence and failure behavior

Explicitly enabled live runs may write optional `llm_semantic_calls.jsonl` and `llm_semantic_manifest.json`. Disabled runs create neither. Enabled zero-call runs create an empty JSONL and a complete manifest with zero records/calls and `exact_replay_ready=false`.

Raw Provider response fields are null. Structured input and saved candidates are sanitized; secret or hidden-reasoning redaction marks the artifact incomplete and blocks readiness/cache writes. Recorder, cache, error-log, and manifest failures are fail-soft and do not alter the business result or repeat a Provider call.

Readiness is fail-closed for zero calls, incomplete/unresolved calls, rejection, fallback, missing output, timeout, Provider error, or exhausted budget. Phase 0.6B does not execute Exact Replay and does not change Architecture Replay.

## Behavioral invariants

With identical offline raw input, run identity, fake Provider outputs, configuration, and cache miss, normalized hashes are identical for:

- `structured_agent_outputs.json`
- `alpha_matches.json`
- `extracted_structures.json`
- `structure_graph.json`
- `conflicts.json` (the current live canonical conflict artifact)

Claim count, evidence, matched Alpha, Alpha score, edges, Activation, Conflict, Exposure, and research response semantics are unchanged. Provider attempt count is also unchanged (3 before, 3 after); only the two semantic sidecars are added.

## Verification

- `tests/llm_runtime`: 83 passed.
- Existing Week2 Gateway tests: 12 passed, 1 explicit real-Provider smoke skipped.
- New Gateway integration tests: 9 passed.
- New live semantic artifact tests: 4 passed.
- Existing Adapter/Mapper/Extractor tests: 115 passed.
- Boundary audit: 4/4 passed.
- Ruff: passed.
- Guarded non-integration suite: 2690 passed, 1 skipped, 47 deselected, 69 subtests passed, 0 failures.
- Phase 0.6B verifier: 25/25 passed.
- Real Provider calls, completed external connections, Redis connections, and Phase 0.6B DB writes: 0.

The unchanged Phase 0.6A verifier reports six expected forward-scope failures because it freezes `NOT_INTEGRATED`, requires zero production importers, and requires the Gateway/callers to remain unchanged. Its Plan, ADR, Replay, canonical prompt, historical output, schema, and offline round-trip checks still pass. The old verifier was not modified.

## Integrity

- Development Plan SHA: `cabf3381aaa633b7b88035ab6df2d7dac0def3d5ddd337f6384f23f4c439a8d9`, unchanged.
- Protected files: 140/140 content and mtime unchanged.
- Historical `outputs/runs`: 133/133 unchanged.
- Historical `outputs/replays`: 108/108 unchanged.
- Disallowed Phase 0.6B diffs: none.

The next allowed phase is Phase 0.6C — Exact Semantic Replay Integration — only after independent review and explicit approval.
