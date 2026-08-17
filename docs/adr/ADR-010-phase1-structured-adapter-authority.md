# ADR-010: Phase 1 Master — Structured Output Adapter Production Authority

Status:

- `ACCEPTED_FOR_STAGED_EXECUTION`
- `RESUMABLE_STATE_MACHINE`
- `HUMAN_REVIEW_REQUIRED_BEFORE_CUTOVER`
- `LEGACY_ROLLBACK_MANDATORY`
- `NO_AUTOMATIC_PHASE_2`

Date: 2026-08-06

## Accepted provider-routing amendment

This remains the same Phase 1 Master and the same architecture. Following the
recorded DeepSeek diagnostics, the product owner approved exactly one
task-specific routing change:

- `structured_claim_shadow` -> `comqutor_anthropic_medium_sonnet46_v1`
  (`claude-sonnet-4-6`), with 180-second timeout and at most one
  transient-only retry.
- `structured_adapter`, `alpha_classifier`, and `structure_extractor` remain
  on their existing DeepSeek configuration. The global/default research
  profile is unchanged.
- No Provider fallback is allowed for the Shadow evaluation; DeepSeek and
  Anthropic results are never mixed into one Prompt-version quality score.
- The prior root blocker is
  `BLOCKED_PROVIDER_MODEL_UNSUITABLE_FOR_LONG_STRUCTURED_TASK`; Exact Replay
  is not classified as its cause.
- All known real Phase 1 calls, including the three ad-hoc diagnostic calls
  and interrupted executions with minimum-only logical-call accounting, are
  preserved in the append-only global Provider ledger.
- Provider-error/timeout reports are auditable non-accepted states. Exact
  Replay is mandatory per accepted/valid-empty/abstained report and does not
  require a partial-failure stage manifest to claim stage-wide readiness.

This amendment grants no production authority. `SEMANTIC_QUALITY=UNPROVEN`,
`HUMAN_REVIEW=PENDING`, and `PRODUCTION_AUTHORITY=LEGACY_ADAPTER` remain in
force.

## Context and provenance

`SOURCE_FROZEN` -- Development Plan v1.0 §5.1 requires each Agent's natural-language output to become the standard Claim schema, with mandatory identity/Claim/Evidence fields and safe handling that never propagates malformed JSON or crashes the run (`docs/specs/development_plan_v1.0_reference_index.md`). `docs/specs/semantic_authority_matrix.csv` (row "claim extraction") names the Phase 1 target production authority as "LLM primary open-language Claim proposer" behind a "Deterministic provenance/source-span/schema validator", with cutover gate "Semantic quality evaluation approved" and Phase label `Phase 1`.

`APPROVED_PROJECT_DECISION` -- `docs/specs/future_semantic_phase_contract.md`'s Phase 1 section states the explicit non-goals ("No immediate production authority; no Graph/Activation/Conflict formula change; no TradingAgents prompt change") and cutover blocker ("Semantic quality, malformed-output, provenance, cost, and fallback thresholds must be explicitly approved"). ADR-008 accepted the offline-only Shadow contract; ADR-009 accepted exactly one controlled four-report real-Provider smoke, explicitly not followed automatically by a larger Pilot or Evaluation. Both are prerequisites this ADR builds on, not supersedes.

`CURRENT_IMPLEMENTATION` -- Before this phase: the real-Provider Shadow smoke path exists (`structured_output_shadow_provider.py`, `structured_output_shadow_replay.py`) and was exercised exactly once with explicit product-owner authorization (`docs/audit_artifacts/phase1b1/phase1b1_completion_report.md`); all 4 logical calls (8/8 attempts) timed out with zero Provider responses -- a real infrastructure finding, not a semantic-quality finding. The Legacy (deterministic) Adapter remains the sole production authority. No 12-report Pilot, 24-report Core Evaluation, human review, quality gate, live shadow wiring, canary run, or production cutover has occurred.

## Decision

1. Phase 1's remaining work (Provider connectivity recovery, controlled evaluation up to 24 core historical reports, exactly one optional Prompt v2 revision, a single human quality-gate review, live Shadow integration, four canary runs, and conditional production cutover) is executed as **one resumable Master Task**, not as separately-instructed sub-phases. Internal Gates and checkpoints are preserved as state-machine transitions, not as new user-facing phase instructions. The sole external pause point is `WAITING_FOR_HUMAN_REVIEW` -- a genuine human semantic-quality judgment step that cannot be synthesized, approximated, or skipped by any automated agent, including this one.
2. `scripts/run_phase1_master.py --resume` is the single, idempotent entrypoint. State is persisted atomically to `docs/audit_artifacts/phase1_master/phase1_master_state.json` after every transition: current state, cumulative logical-call and Provider-attempt counts (never reset, including calls made during interrupted/voided attempts), Prompt version/hash in use, selected report IDs already called (never re-called), and the next allowed action.
3. Total logical-call and Provider-attempt budgets are hard caps enforced by the state machine itself, independent of and in addition to `Week2LLMGateway`'s own existing per-call retry policy (unchanged, not widened): 53 logical calls, 105 Provider attempts, computed as 1 connectivity probe (retry=0) + up to 29 expected evaluation calls (1 probe... actually 24 historical + 4 canary = 28, plus 1 auth probe = 29) each with the existing 1-retry policy, plus one full optional v2 re-run of the same 24 reports. Reaching either cap halts all further Provider calls with `FAIL_PHASE1_PROVIDER_CALL_LIMIT_EXCEEDED`; the count is never reset by deleting an evaluation directory.
4. Historical report selection reuses Phase 1A's frozen `evaluation_corpus_inventory.json` `coverage[*].selected_agent_output_id` exclusively -- the same 24 core slots (6 tickers x 4 Agent families) already used for Phase 1B.1's Smoke selection, expanded stage by stage (Smoke: NVDA x4; Pilot: NVDA+QQQ+MSFT x4=12; Core Evaluation: all 6 tickers x4=24). A report already successfully attempted is never re-called within the same Prompt version; Smoke's 4 results carry forward into Pilot and Core Evaluation rather than being re-fetched.
5. The Phase 1 Quality Gate (safety gates, human semantic gates, operational gates -- full thresholds in `docs/specs/phase1_master_execution_contract_v1.md`) requires a real human reviewer's completed CSV. This agent never fabricates, infers, or substitutes an automated judgment for any `review_label`/`severity`/`reviewer` field. `human_labels_created` starts and remains `false` until a human-completed CSV is supplied back to `--resume --human-review-csv`.
6. At most one Prompt revision (`structured_adapter.claim_extraction_shadow.v2`) is permitted, only if v1 fails the Quality Gate, only derived from named systematic errors in the completed human review, preserving v1's results and directory untouched. v1 and v2 results are never mixed when computing final quality. A v2 failure produces `BLOCKED_PHASE1_SEMANTIC_QUALITY` and does not auto-create v3.
7. Live Shadow integration introduces `COMQUTOR_STRUCTURED_ADAPTER_MODE` (`legacy` / `shadow` / `primary`), defaulting to `shadow` once wired. In `shadow` mode the Legacy Adapter remains sole production authority; the new Adapter runs in parallel and writes sidecar artifacts only (`structured_agent_outputs_shadow.json`, `structured_adapter_shadow_validation.json`, `structured_adapter_shadow_comparison.json`) that never feed downstream computation. This ADR does not, by itself, authorize `primary` mode -- that requires passing every condition in `docs/specs/phase1_master_execution_contract_v1.md` §Stage G, confirmed by `scripts/verify_phase1_master.py`.
8. Production Cutover (`primary` mode) preserves the Legacy Adapter as an explicit, always-available fail-soft path: any Provider timeout/error or validation rejection at run time falls back to the Legacy Adapter with an explicitly recorded, never-silent fallback reason. Cutover changes no Alpha Mapper, Structure Extractor, Graph, Activation, Exposure, or Conflict logic, and no TradingAgents Agent prompt or canonical prompt injection behavior.
9. Exact Semantic Replay for `primary`-mode runs reuses the existing Phase 0.6/ADR-007 contract unmodified: replay never re-calls a Provider, never re-interprets an Agent report, never re-generates a Claim; it reads persisted validated Claims and re-runs only the deterministic downstream stages. A run that used the Legacy fallback records that decision explicitly and is never presented as a pure-LLM Exact Replay.

## Current implementation boundaries

`CURRENT_IMPLEMENTATION` at the start of this Master Task:

- Production authority for §5.1 claim extraction remains the deterministic Legacy Adapter. `COMQUTOR_STRUCTURED_ADAPTER_MODE` does not yet exist in code.
- `COMQUTOR_WEEK2_LLM_ENABLED` remains default-disabled and is not read by any Phase 1 Master authorization path.
- Alpha Mapper, Structure Extractor, Graph/Activation/Exposure/Conflict algorithms, TradingAgents Agent prompts, and canonical prompt injection are unchanged by this ADR and must remain unchanged through every stage of this Master Task except the explicitly-scoped Stage E live-orchestration wiring.
- Evidence Stance and ticker specificity (Addendum A, `JOHN_LATER_REQUIREMENT` / `PROPOSED_EXTENSION`, not approved) are out of scope for this Master Task and must not be implemented, expanded, or given production authority here.
- No commit, push, reset, restore, clean, or stash occurs as part of this Master Task's execution.

## Consequences

- A single resumable state file replaces per-sub-phase instruction documents; every future `--resume` invocation (in this or a later session) must re-derive its next action from `phase1_master_state.json` plus the immutable audit ledger, not from conversational memory.
- Real Provider spend is bounded by an explicit, non-resettable hard cap independent of and in addition to the existing Gateway retry policy.
- Production authority cannot change without a real human completing real semantic review of real Provider output across all 24 core historical slots -- this ADR does not, and no automated agent may, shortcut that requirement.
