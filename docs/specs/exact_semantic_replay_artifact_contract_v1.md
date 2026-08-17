# Exact Semantic Replay Artifact Contract v1

Status: `APPROVED_PROJECT_DECISION` for a future interface; `NOT_IMPLEMENTED`; `NOT_INTEGRATED`.

Phase 0.6A freezes artifact inputs, integrity rules, and failure semantics. It does not change the current Architecture Replay pipeline.

## A. EXACT_SEMANTIC_REPLAY

Required saved inputs are:

- raw agent outputs associated with the historical run;
- `llm_semantic_calls.jsonl` containing `comqutor.semantic_call.v1` records;
- `llm_semantic_manifest.json` containing `comqutor.semantic_manifest.v1`;
- the saved validated structured semantic artifacts used by the historical run; and
- prompt, input/output schema, taxonomy, model, task, sequence, and run identity metadata needed for an unambiguous match.

An Exact Semantic Replay must perform zero Provider calls, TradingAgents calls, market-data calls, and database writes. It must not reinterpret natural-language agent text, regenerate an LLM decision, or substitute a current parser/fallback for a saved LLM decision. After strict artifact verification and unique call matching, it reads the saved accepted semantic result and may rerun only deterministic downstream stages.

The manifest and complete JSONL byte stream are verified before any semantic result is consumed. The calls-file SHA-256, record count, task/status/fallback/cache/Provider counts, prompt/model sets, completion flags, and replay-ready derivation must all match. Each call's input, raw-output, and validated-output hashes and every schema/version identity must verify. Run IDs must agree across request, manifest, call, and associated structured artifacts.

The reader fails closed with stable reason codes:

| Reason code | Condition |
|---|---|
| `EXACT_REPLAY_SEMANTIC_ARTIFACT_MISSING` | A required calls, manifest, structured, raw-agent, or metadata artifact is absent. |
| `EXACT_REPLAY_SEMANTIC_MANIFEST_INVALID` | Manifest JSON/schema/derived counts/hash/completion/readiness is invalid. |
| `EXACT_REPLAY_SEMANTIC_CALL_CORRUPTED` | JSONL is partial, malformed, non-UTF-8, internally invalid, hash-invalid, or missing an accepted output. |
| `EXACT_REPLAY_SEMANTIC_INPUT_MISMATCH` | Requested replay input canonical hash differs from the saved call. |
| `EXACT_REPLAY_SEMANTIC_VERSION_MISMATCH` | Prompt, semantic-call, input, output, taxonomy, task, Provider, or model identity required for matching differs. |
| `EXACT_REPLAY_SEMANTIC_CALL_AMBIGUOUS` | No unique call can be selected, including duplicate IDs or multiple matches. |
| `EXACT_REPLAY_SEMANTIC_RUN_ID_MISMATCH` | Run identity differs among request and artifacts. |

No fallback-to-rebuild is allowed after one of these failures. A caller may explicitly start the separate diagnostic mode, but it cannot relabel that result as exact replay.

## B. RAW_REBUILD_DIAGNOSTIC

Raw Rebuild Diagnostic starts from saved raw agent outputs and reruns explicitly selected current or version-pinned parsers/fallbacks. It is intended for investigation, comparison, and migration analysis. Its result may differ from historical live semantics and must never claim exact semantic equivalence.

Implementations must expose the mode name and artifact/version provenance in results so Exact Semantic Replay and Raw Rebuild Diagnostic cannot be confused.

## Non-goals and current boundary

This document implements neither mode. It does not add replay dispatch, match calls, write replay artifacts, call deterministic downstream code, or alter current Provider-zero replay behavior. It does not decide how many semantic calls a real run must contain. Phase 0.6A verifies only artifact self-consistency and leaves all current semantic authority unchanged.
