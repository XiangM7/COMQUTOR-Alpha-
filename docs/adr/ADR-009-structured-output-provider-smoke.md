# ADR-009: Structured Output Adapter Provider Smoke

Status:

- `ACCEPTED_FOR_CONTROLLED_SMOKE`
- `REAL_PROVIDER_OPT_IN_ONLY`
- `SHADOW_ONLY`
- `NO_PRODUCTION_AUTHORITY`
- `HUMAN_REVIEW_REQUIRED`

Date: 2026-08-06

## Context and provenance

`SOURCE_FROZEN` -- Development Plan v1.0 §5.1 requires Agent natural language to become the standard Claim schema; mandatory identity/Claim/Evidence fields; factors best effort; entities possibly empty; confidence in `[0,1]`; and safe handling that never propagates malformed LLM JSON or crashes the run. It requires the original fundamental/news/sentiment/technical Agent coverage. It does not require a real-model evaluation of any specific size, and does not mandate that Claim boundaries be LLM-generated.

`APPROVED_PROJECT_DECISION` -- ADR-008 accepted an offline-only Shadow contract and evaluation harness with no measured real-model semantic quality. Phase 1B requires independent approval and cannot be inferred from Phase 1A passing. This ADR accepts exactly one narrow, controlled first step: four real-Provider Shadow calls (one report per Agent family, one ticker), never more, never automatically followed by a larger Pilot or Evaluation.

`CURRENT_IMPLEMENTATION` -- Before this phase, the Shadow parser (`structured_output_shadow.py`) accepted only an injected `SemanticInvoker`; Phase 1A tests used `FakeSemanticInvoker` exclusively; there was no real-Provider code path anywhere in the Shadow evaluation stack. `Week2LLMGateway` already implemented retry/timeout/budget/semantic-runtime integration for the three live Week2 tasks (`claim_batch_enrichment`, `alpha_classifier`, `structure_extractor`), gated by `COMQUTOR_WEEK2_LLM_ENABLED`.

## Decision

1. `comqutor_alpha/structure_engine/structured_output_shadow_provider.py` adds `Week2GatewaySemanticInvoker`, a `SemanticInvoker` implementation that routes the frozen Phase 1A prompt (`structured_adapter.claim_extraction_shadow.v1`, SHA-256 `c60f1526fd927e4593ab5913bc3c653cd2a05f6d24dc5fdf3e258a3e62128d1e`) through `Week2LLMGateway.invoke_prebuilt_json_prompt` -- a new, additive Gateway method that reuses the existing retry/timeout/budget machinery without reading or altering `_TASK_INSTRUCTIONS`/`_TASK_RUNTIME_METADATA`, the fixed tables the three existing Week2 tasks use for their own prompt/version identity.
2. `structured_output_shadow_provider.build_real_provider_gateway` constructs the Gateway from an explicit `ResearchProfile` (`comqutor_alpha.research_profiles`), never from `COMQUTOR_WEEK2_LLM_ENABLED` or `build_server_week2_llm_gateway`. Provider/model authorization for this phase is deliberately independent of the unrelated live-route flag.
3. A new semantic task identity, `structured_claim_shadow`, is added to `comqutor_alpha.llm_runtime.contracts.SEMANTIC_TASKS`. This is additive: the three existing tasks' names, prompt versions, prompt hashes, cache identity, validators, and manifest semantics are unchanged, and the recorder/manifest machinery already generalizes over `SEMANTIC_TASKS` without further edits.
4. `scripts/run_phase1b1_provider_smoke.py` is the only real-Provider entrypoint. It requires `--research-profile`, `--max-provider-calls` (`<=4`), `--output-dir` (must resolve under `outputs/evaluations/`, non-existent or empty, no symlink/traversal), and `--execute-provider-smoke`, AND the environment variable `COMQUTOR_PHASE1B1_PROVIDER_SMOKE_APPROVED` set to exactly `"true"`. Absent any one of these, it performs zero Provider calls and reports a stable `BLOCKED_*` status. It never infers authorization from Provider-credential presence or from `COMQUTOR_WEEK2_LLM_ENABLED`.
5. Exactly four reports are selected: one per Agent family (fundamental, news, sentiment, technical), from the first ticker (in `NVDA, QQQ, MSFT, SNDK, TSM, AMD` order) with complete family coverage in Phase 1A's `evaluation_corpus_inventory.json`. Per-family report choice reuses Phase 1A's own already-deterministic `coverage[*].selected_agent_output_id` rather than re-deriving a second tie-break rule that could diverge from it.
6. `NullLLMResponseCache` is used for this smoke; no Redis client is constructed. Output is written to a new, atomically promoted directory under `outputs/evaluations/`; `outputs/runs/` and `outputs/replays/` are never written.
7. `structured_output_shadow_replay.py` adds an evaluation-only, Provider-zero exact-replay validator for one persisted Phase 1B.1 bundle. This is explicitly distinct from ADR-007's production Exact Semantic Replay (which consumes a live run's `structured_agent_outputs.json`/`alpha_matches.json`/`extracted_structures.json`): this module re-verifies only the four-report Shadow smoke bundle's own hashes, identity, and validator reproducibility, with zero Provider/Gateway/network/Redis/database calls.
8. Every accepted Shadow Claim in this smoke still passes the exact Phase 1A deterministic validator (`validate_shadow_bundle`): schema, identity, source-report hash, source-span exactness, evidence provenance, factor/source-ref vocabulary, and duplicate rejection. No output is admitted by inference or by human post-hoc repair.
9. Human review remains required and unautomated: `build_blank_review_rows`/`render_blank_review_csv` (unchanged, reused verbatim from Phase 1A) produce a blank CSV with `human_labels_created=false`. No Codex/LLM judgment is ever written into a human-label column.

## Current implementation boundaries

`CURRENT_IMPLEMENTATION`:

- The current Adapter, Alpha Mapper, Structure Extractor, live routes, production Replay, Graph/Activation/Exposure/Conflict, TradingAgents, and canonical prompt injection are unchanged by this phase.
- `COMQUTOR_WEEK2_LLM_ENABLED` remains default-disabled and is not read by this phase's authorization path.
- The Shadow Engine has zero production importers; this phase adds zero new importers of it outside `scripts/run_phase1b1_provider_smoke.py`.
- No 12-report Pilot or 24-report Evaluation is started by this ADR; both require separate, explicit approval (Phase 1B.2/1B.3).
- Semantic quality remains unproven: this phase measures whether the pipeline mechanically works end-to-end against a real Provider, not whether its output is semantically correct.

## Consequences

The repository gains one, tightly bounded, auditable real-Provider data point per Agent family, persisted with full identity/provenance/hash traceability and a Provider-zero exact-replay proof, without granting the Shadow Engine any production authority or committing to a larger evaluation. The next decision point (Phase 1B.2) requires independent review of this smoke's artifacts and the completed human review CSV.

## Source classification summary

`SOURCE_FROZEN`:

- Development Plan §5.1 NL-to-Claim-schema purpose, malformed-JSON fail-soft requirement, required fundamental/news/sentiment/technical Agent coverage, structured downstream-consumption contract.

`APPROVED_PROJECT_DECISION`:

- Exactly four reports, one per Agent family, in this first real-Provider evaluation.
- Prompt v1 (`structured_adapter.claim_extraction_shadow.v1`) is immutable for this phase; a content change would require a new version and blocks this phase instead.
- `NullLLMResponseCache` for this smoke, never Redis.
- Output written to an independent `outputs/evaluations/` directory, never `outputs/runs/` or `outputs/replays/`.
- Real Provider output is a Shadow sidecar only; it never gains production authority.
- Human review, not an automated signal, determines semantic quality.
- A Provider-zero Shadow exact replay verifies the persisted result before any review begins.

`CURRENT_IMPLEMENTATION`:

- Production Adapter/Mapper/Extractor/Graph/Activation/Exposure/Conflict are unchanged.
- The Shadow Engine is not wired into any live route.
- This phase is exercised only through the evaluation CLI.
- Semantic quality remains `UNPROVEN` regardless of this phase's PASS/BLOCKED outcome.

`JOHN_LATER_REQUIREMENT`:

- Evidence Stance and B2 Conflict Evidence Admissibility remain untouched and are not implemented, extended, or referenced by this phase.
