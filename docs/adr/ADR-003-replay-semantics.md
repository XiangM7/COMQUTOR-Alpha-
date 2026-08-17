# ADR-003 — Replay Semantics

- **Status:** `ACCEPTED_FOR_FUTURE_IMPLEMENTATION`
- **Current replay:** `CURRENT_REPLAY_PARTIAL`
- **Decision classification:** `APPROVED_PROJECT_DECISION`
- **Implementation in Phase 0.5:** None

## Context

Current Architecture Replay reads the saved per-run raw_agent_outputs.json artifact, reruns current parsers/fallbacks, and forces `llm_gateway=None`. TradingAgents calls, LLM Provider calls, market-data calls, and database writes are structurally zero. This behavior is useful and safe, but it cannot reproduce LLM-tier semantic decisions made during a live run unless those decisions are replayed as persisted artifacts.

Calling both behaviors “replay” without a mode contract would conceal a material semantic difference.

## Decision

Two explicitly different Provider-zero modes are required.

### A. `EXACT_SEMANTIC_REPLAY`

Purpose: reuse the live run's already-saved and validated semantic decisions, then recompute the deterministic Graph, Activation, Exposure, and Conflict layers.

It must not:

- invoke an LLM or TradingAgents;
- request market data;
- write to the database;
- regenerate semantic decisions from raw prose.

The future artifact contract must include:

- validated structured semantic claims and Claim/Evidence boundaries;
- accepted Alpha classifier decisions, eligible candidates, defer/fallback state, and validation result;
- accepted structure-relation decisions and admission inputs;
- prompt version/hash, schema version/hash, model/provider identity, and input/output hashes;
- retry, validation, fallback, and degradation metadata;
- source run identity and immutable source-artifact hashes.

The result must explain deterministic differences between the saved live result and replay recomputation.

If required semantic artifacts are missing, exact mode must either fail explicitly or emit an explicit, separately named degradation. It must never silently rebuild and claim exact equivalence.

### B. `RAW_REBUILD_DIAGNOSTIC`

Purpose: start from the saved per-run raw_agent_outputs.json artifact and rerun a named parser version, deterministic fallback, or comparison candidate for architecture diagnosis.

It must:

- record parser/schema versions and `replay_mode=RAW_REBUILD_DIAGNOSTIC`;
- retain Provider, TradingAgents, market-data, and DB calls at zero;
- report semantic deltas without claiming equivalence to historical live decisions.

## Current Classification

The present implementation is `RAW_REBUILD_DIAGNOSTIC`-like because it rebuilds from raw outputs and forces `llm_gateway=None`. Its Provider-zero property is compliant; its exact semantic reproducibility is partial.

## Shared Invariants

| Invariant | Exact semantic replay | Raw rebuild diagnostic |
| --- | --- | --- |
| Explicit `replay_mode` | Required | Required |
| Provider calls | 0 | 0 |
| TradingAgents calls | 0 | 0 |
| Market-data calls | 0 | 0 |
| DB writes | 0 | 0 |
| Source mutation | Forbidden | Forbidden |
| Semantic source | Persisted validated decisions | Saved raw output plus named parser/fallback |
| Claim of live semantic equivalence | Allowed only when artifact contract is complete | Forbidden |

## Consequences

- Phase 0.6 must define semantic-call persistence and the exact replay artifact contract before production LLM is enabled by default.
- Future modes must have different names and cannot silently substitute for one another.
- Phase 0.5 does not change replay execution or metadata.
