# ADR-007: Exact Semantic Replay Integration

Status:

- `ACCEPTED_FOR_IMPLEMENTATION`
- `PROVIDER_ZERO`
- `FAIL_CLOSED`
- `NO_LIVE_SEMANTIC_CHANGE`

Date: 2026-08-06

## Context and provenance

`SOURCE_FROZEN` — Development Plan v1.0 requires replay to use saved outputs and rerun deterministic downstream analysis without invoking a Provider. A replay result must retain source provenance and must not overwrite historical artifacts.

`APPROVED_PROJECT_DECISION` — Exact Semantic Replay and Raw Rebuild Diagnostic are distinct products. Exact Replay consumes saved, validated semantic authority; Raw Rebuild reinterprets raw text with the current parser/fallback implementation for architecture diagnosis. A failed Exact Replay never silently becomes Raw Rebuild.

`CURRENT_IMPLEMENTATION BEFORE 0.6C` — `run_structure_replay` read `raw_agent_outputs.json`, reran Adapter, Alpha Mapper, and Structure Extractor with `llm_gateway=None`, then reran Graph, Activation, Exposure, and Conflict. It was Provider-zero but could reproduce only current fallback semantics, not the source live run's saved LLM decisions.

Phase 0.6B added optional `llm_semantic_calls.jsonl` and `llm_semantic_manifest.json` sidecars for explicitly enabled live runs. A verified manifest can prove that all saved calls were accepted and admitted without fallback, but Phase 0.6B did not implement replay.

## Decision

1. The only replay mode identities are `EXACT_SEMANTIC_REPLAY` and `RAW_REBUILD_DIAGNOSTIC`.
2. `run_structure_replay` remains the backward-compatible Raw Rebuild entrypoint. Its raw input, parser/fallback path, Provider-zero behavior, database-zero behavior, and artifact semantics are preserved. Additive metadata identifies `semantic_source=raw_rebuild`.
3. `run_exact_semantic_replay` accepts a source run directory and a separate replay output root. It reads source files only and never updates their content or metadata.
4. Exact eligibility requires a supported, complete, exact-ready semantic manifest; a complete hash-valid JSONL stream; supported call/prompt/input/output/taxonomy versions; accepted outputs with no fallback or Provider failure; consistent run/ticker/artifact identities; and complete source artifacts.
5. Each semantic call must bind uniquely to the saved structured decision it produced:
   - Adapter calls bind by exact agent, ticker, segment IDs, claim/evidence/section, factors, direction, and confidence.
   - Alpha calls bind by exact saved claim identity, factors/direction, complete admissible candidates and scores, allowed IDs, and selected/defer result.
   - Extractor calls bind by exact claim ID, claim/evidence, allowed factors, and saved edge identities.
6. Task name, array position, call order, or text similarity alone is never sufficient. Missing, orphan, duplicate, one-to-many, many-to-one, hash-invalid, version-invalid, or decision-mismatched bindings fail closed.
7. The saved `structured_agent_outputs.json`, `alpha_matches.json`, and `extracted_structures.json`, together with calls and manifest, are `SAVED_SEMANTIC_AUTHORITY`. They are copied byte-for-byte to the replay bundle. Their embedded `run_id` remains the source run ID.
8. A private in-memory computation view may carry the replay execution identity required by existing deterministic downstream functions. It does not rewrite the persisted semantic copies or change any Claim, Alpha, factor, edge, evidence, score, or semantic decision.
9. Exact Replay reruns only Graph assembly/admission, Activation, Exposure, Conflict, and downstream serialization. It does not call Adapter, Alpha Mapper, Structure Extractor, Week2 Gateway, TradingAgents, a Provider factory, market data, Redis, a network socket, or a database.
10. Exact output is written to a uniquely named staging directory, validated, source-integrity-checked again, and promoted using one atomic directory rename. Failure removes or isolates staging and never creates a successful final bundle.
11. Comparison maps only explicit execution-owner identity, generated timestamps, and deterministic evidence-fact-group IDs derived from identical member Claim IDs. Graph, Activation, Exposure, and Conflict changes are reported as `DETERMINISTIC_ENGINE_DELTA`, not as a semantic mismatch.
12. Historical runs without Phase 0.6B sidecars return `EXACT_REPLAY_SEMANTIC_ARTIFACT_MISSING`. A non-ready manifest returns `EXACT_REPLAY_SEMANTIC_NOT_READY`. Neither case synthesizes sidecars, reconstructs semantic calls, or falls back to Raw Rebuild.

## Current implementation after 0.6C

`CURRENT_IMPLEMENTATION` — `comqutor_alpha.replay` now exposes both strict mode identities and separate entrypoints. Exact Replay validates the source bundle and unique semantic bindings before any deterministic downstream work. It produces byte-identical semantic copies, replay-owned downstream artifacts, a source snapshot, binding audit, behavioral comparison, run audit, and artifact manifest through staging and atomic promotion. Offline tests use the existing Phase 0.6B live path with a fake Provider to create an eligible source and then prove zero external calls during replay.

The live Week2 path, default-disabled setting, prompts, cache, validators, semantic authority, Adapter/Mapper/Extractor logic, TradingAgents, canonical prompt injection, Graph/Activation/Exposure/Conflict algorithms, and historical output trees are unchanged.

## Consequences

Exact Replay now means reuse of historical semantic decisions, not re-execution of an Agent or a current parser. Semantic ownership remains visibly attached to `source_run_id`; deterministic replay artifacts belong to `replay_id`. A future deterministic engine upgrade may produce a declared engine delta while retaining exact semantic input reuse.

Runs without sufficient saved evidence remain ineligible. This is intentional fail-closed behavior, not a migration failure. Raw Rebuild remains available only through its separately named mode.

## Rejected alternatives

- Rebuilding semantic artifacts from raw text and calling it exact: rejected because it substitutes current interpretation for historical authority.
- Rewriting copied semantic JSON to the replay ID: rejected because it destroys byte identity and source ownership.
- Binding by call order or fuzzy claim text: rejected because duplicates cannot be proven unique.
- Automatically invoking Raw Rebuild after an Exact error: rejected because it mislabels semantic provenance.
- Reusing source downstream artifacts without recomputation: rejected because Exact Replay must expose deterministic engine deltas independently from saved semantics.
- Adding stable binding metadata by modifying Phase 0.6B live code in this phase: rejected because the observed saved identities are sufficient for the supported fixture and live contract; ambiguous composites still fail closed.

## Non-goals

This ADR does not modify live LLM behavior, prompts, caches, semantic validators, Provider/model selection, TradingAgents, Evidence Stance, ticker specificity, B2, canonical prompt injection, or any Graph, Activation, Exposure, or Conflict formula. It does not begin Development Plan §5.1 Phase 1 or John's B1/B2/B3/B4/B5/J1/J2/J3 work.
