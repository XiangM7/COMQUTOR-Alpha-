# ADR-005: LLM Execution Substrate

Status:

- `ACCEPTED_FOR_OFFLINE_FOUNDATION`
- `NOT_INTEGRATED`
- `NO_PRODUCTION_AUTHORITY`

Date: 2026-08-05

## Context and provenance

The project needs an auditable substrate before any future migration of semantic LLM execution. Specification statements retain their provenance and priority; this ADR does not rewrite later requirements into the frozen Development Plan.

`SOURCE_FROZEN` — Development Plan v1.0 requires LLM JSON retry, validation, safe fallback, error logs, and an LLM response cache.

`CURRENT_IMPLEMENTATION` — Week2LLMGateway currently has retry, timeout, and error logging behavior. A response cache is absent. Prompt/model/input/output observability is incomplete. Live semantic decisions do not share a unified persistence contract. Architecture Replay forces deterministic rebuild and does not yet provide exact saved-semantic replay.

Phase 0.6A must not modify any of those current behaviors. In particular, it does not enable the default-disabled Week2 LLM path, remove canonical prompt injection, alter Adapter/Mapper/Extractor authority, change replay, or promote Evidence Stance.

## Decision

`APPROVED_PROJECT_DECISION`:

1. Every future COMQUTOR semantic LLM call must produce a valid `SemanticCallRecord v1`.
2. Cache entries may contain only validation-accepted structured results produced by a successful Provider call without fallback. Rejected values, Provider errors, fallback values, and raw text are not cache entries.
3. Redis access is behind an injected Redis-like client. Import and adapter construction do not create a client or connection.
4. Future live runs must persist semantic-call JSONL and its derived manifest as run artifacts.
5. Future Exact Semantic Replay must use verified saved accepted semantic results and make no Provider, TradingAgents, market-data, or database calls.
6. Raw Rebuild Diagnostic is a separate, explicitly labeled mode and cannot claim historical semantic equivalence.
7. Schema identifiers and canonicalization behavior are versioned and fail closed; breaking change requires a new version.

The offline implementation lives only in `comqutor_alpha.llm_runtime`. Tests and read-only verification may import it. Current production modules may not import it during Phase 0.6A.

## Consequences

The project gains deterministic canonical JSON/hash primitives, strict semantic-call and cache-entry validation, a versioned cross-run cache key, null and injected-Redis cache adapters, an append-only recorder, an atomic derived manifest, and explicit corruption diagnostics. Exact replay now has a frozen artifact interface without changing replay execution.

The Redis adapter deliberately reports corrupt entries as explicit errors rather than silently treating them as misses. Recorder concurrency is serialized within one process; cross-process writers are unsupported in v1. No minimum number of calls for a real run is decided here.

Integration, feature flags, production paths, Provider budgets, retry/timeout defaults, deployment configuration, Redis provisioning, database persistence, and semantic quality acceptance remain future work requiring independent review and explicit approval.

## Rejected alternatives

- Caching raw Provider text or errors: rejected because values are unvalidated and may contain secrets.
- Including `run_id` in the semantic cache key: rejected because identical fully versioned requests should be reusable across runs.
- Constructing Redis clients from environment variables in the adapter: rejected because it creates hidden I/O and configuration authority.
- Silently skipping corrupt JSONL or treating corrupt cache content as an ordinary miss: rejected because it destroys auditability.
- Integrating the foundation during Phase 0.6A: rejected by the phase boundary.
