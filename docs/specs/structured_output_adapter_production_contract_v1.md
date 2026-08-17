# Structured Output Adapter Production Contract v1

Status: `PROPOSED_EXTENSION` -- describes the runtime contract Stage E/F/G of the Phase 1 Master Task (`docs/specs/phase1_master_execution_contract_v1.md`) must implement. Not yet built; not yet live. Building this contract's code is only in scope once `SMOKE`/`PILOT`/`CORE_EVALUATION`/`QUALITY_GATE` have actually passed.

## Purpose

Define exactly how `COMQUTOR_STRUCTURED_ADAPTER_MODE` changes runtime behavior, what must be persisted per run, and the fail-soft contract that keeps the Legacy Adapter as a permanent, config-only rollback path once the new Adapter becomes production authority.

## Mode variable

`COMQUTOR_STRUCTURED_ADAPTER_MODE`, values `legacy` | `shadow` | `primary`. Read once per run at the same integration point the Legacy Adapter is currently invoked from; never inferred from `COMQUTOR_WEEK2_LLM_ENABLED` or any other unrelated flag.

- **`legacy`** (pre-Stage-E default, and always available thereafter): only the deterministic Legacy Adapter executes. No new Adapter code path is entered. No sidecar artifacts are written. Behavior is byte-identical to today.
- **`shadow`** (Stage E default): Legacy Adapter executes and remains sole production authority -- its output is the only thing downstream (Alpha Mapper, Structure Extractor, Graph, Activation, Exposure, Conflict) ever consumes. The new Adapter also executes, in parallel, against the same raw Agent output, and writes sidecar artifacts only. A new-Adapter failure (Provider timeout, validation rejection, exception) never affects the run's production result or exit status -- it is caught, recorded in the sidecar validation artifact, and the run proceeds exactly as `legacy` mode would have.
- **`primary`** (Stage G only, requires the full cutover gate in the execution contract): the new Adapter's validated output becomes the production input to downstream stages. On Provider timeout/error or validation rejection, the run falls back to the Legacy Adapter's output for that run, records the fallback explicitly (never silently), and still completes -- fail-soft, not fail-crash, matching Development Plan §5.1's "never propagate malformed JSON, never crash the run".

## Sidecar artifacts (`shadow` mode)

Written alongside the existing run output, never overwriting it:

- `structured_agent_outputs_shadow.json` -- the new Adapter's validated Claims for this run, same schema shape as the production `structured_agent_outputs.json`, tagged `shadow_only: true, production_authority: false`.
- `structured_adapter_shadow_validation.json` -- per-report validation outcome (accepted/rejected/abstained/parser_error), reason codes, provenance/source-span/identity check results.
- `structured_adapter_shadow_comparison.json` -- Legacy-vs-Shadow comparison signals for this run's reports, reusing `compare_legacy_and_shadow` verbatim from Phase 1A/1B.1 (diagnostic only, never a production gate).

## Persisted fields (`primary` mode, every run)

Every run executed under `primary` mode persists, regardless of outcome:

- `selected_authority`: `"structured_output_adapter_llm"` or `"legacy_adapter_fallback"`.
- `prompt_version`, `prompt_sha256` (the Prompt actually used -- v1 or the approved v2).
- `provider`, `model` (the research profile actually used).
- `validation_outcome`: accepted/rejected/abstained/parser_error per report, with reason codes.
- `fallback_status`: `none` or the specific reason (`provider_timeout`, `provider_error`, `validation_rejected`, `budget_exhausted`, ...) -- never blank when a fallback occurred, never present when it did not.
- `llm_semantic_calls.jsonl` / `llm_semantic_manifest.json` for the run, using the existing Phase 0.6 semantic-call contract unmodified.

No run may claim `selected_authority: structured_output_adapter_llm` while `fallback_status` is non-`none` for that report, and no run may omit `fallback_status` when a fallback actually occurred. Silent fallback is a Stage G FAIL condition.

## Exact Replay interaction

A `primary`-mode run's persisted validated Claims are replay inputs under the existing ADR-007/Phase 0.6C `EXACT_SEMANTIC_REPLAY` contract, unmodified: replay reads persisted Claims, never re-calls a Provider, never re-derives a Claim, and re-runs only downstream deterministic stages. A run where any report used the Legacy fallback is replayed with that fact intact and explicit -- it is never presented as if every report were a pure new-Adapter decision. Fail-closed behavior (Phase 0.6C) is unchanged.

## What this contract does not authorize

- No change to Alpha Mapper, Structure Extractor, Graph, Activation, Exposure, or Conflict algorithms in any mode.
- No change to TradingAgents Agent prompts or canonical prompt injection in any mode.
- No Evidence Stance or ticker-specificity production authority in any mode.
- `primary` as a default value before Stage G's cutover gate has actually passed, verified by `scripts/verify_phase1_master.py`, not merely claimed.
