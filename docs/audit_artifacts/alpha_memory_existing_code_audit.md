# Alpha Memory / Feedback Loop — Existing-Code Audit

Read-only. Local worktree (including uncommitted changes) inspected directly. **Provider calls: 0. TradingAgents calls: 0.** No production code, tests, or artifacts modified except this audit's own output.

## Overall verdict: **MIXED**

The Development Plan's "MVP Lite memory" half (static Alpha taxonomy + static entity-exposure seed) is genuinely **ACTIVE_PRODUCTION** — real, live, exactly as scoped for MVP. The Phase-2 "adaptive memory" half (phi-ID, cross-run causal-chain matching, invalidation-event persistence, reason-code lifecycle, memory-based activation modulation, human-review feedback) is essentially **NOT_IMPLEMENTED**, with exactly one incidental, unintentional reusable primitive found. Neither "PARTIAL_FOUNDATION_ONLY" nor "NOT_IMPLEMENTED" alone is true of both halves — hence MIXED.

## What already exists and is ACTIVE

- **Static Alpha taxonomy** (`alpha_taxonomy_v1.yaml` + `alpha_loader.py`) — versioned, hash-guarded, loaded every run.
- **Static entity-exposure seed** (`entity_alpha_exposure_seed_v0.1.yaml` + `seed_loader.py`) — versioned, hash-guarded, loaded every run; its `historical_mapping` field IS read every run and DOES gate B4 activation (50% weight in `exposure_engine.py`) — but it is a fixed, human-authored prior, never something the system measured from actual past runs.
- Per-run persistence of everything (exposure, activations, conflicts, graphs) — genuinely written every time.

## What exists but is disconnected / partial

- **`structure_extractor.py`'s node id** (`_slug(_display_label(canonical_factor, ticker))`) is *already* deterministic and stable across runs of the same ticker — the closest thing to a phi-ID anywhere in the codebase. It is written into every run's `structure_graph.json` and **never read back cross-run** by any code. Built for intra-run graph deduplication, not memory. Best reuse candidate for a future v1 identity system (no change to the Structure Extractor itself needed).
- Only the factor "Revenue Growth" gets a ticker-scoped id; every other factor's id is ticker-independent — a real design detail a future phi-ID would need a Product decision on.
- All persistence (exposure/activation/conflict/graph tables) is **write-only across runs** — nothing anywhere queries a *different* run's row.

## What does not exist at all

phi_id / phi_token (zero code hits anywhere), cross-run causal-chain matching, invalidation-event detection (conditions are static display text, never evaluated), invalidation/non-execution event persistence (no such event type exists), reason-code lifecycle tracking, historical-memory lookup functions, feedback-loop sections in `run_audit.json`, feedback-loop UI. No dead/orphaned code was found that was clearly *intended* for Alpha Memory and abandoned — the gap is that it was never started, not that it broke.

## Does any current historical data affect Activation?

**No.** `activation_scorer_v2.py` and `exposure_engine.py` have zero repository/DB imports — confirmed by reading every import statement in both files. Architecturally incapable of reading history. The only "historical" input is the static seed's fixed prior number.

## Does current Evidence Review data feed future runs?

**No.** `evidence_review_summary_v2.json` and all review artifacts are referenced only by test files — zero production code path reads them.

## Exact reusable components

1. `structure_extractor.py`'s factor(+ticker) node id — seed of a v1 stable identity.
2. `entity_alpha_exposures`/`alpha_conflicts`/`alpha_activations` DB tables — query target for a new cross-run reader; no migration needed.
3. `authority_contract.py`'s GOLD/DOCUMENTED/PROVISIONAL/REJECTED vocabulary — reusable pattern for any future confidence/authority tiering.
4. `run_audit.json`'s additive-section convention — where a future `memory_summary` belongs.

## Product decisions required (not invented here)

- Ticker-scoping consistency for structure ids across all factors.
- Phi-similarity thresholds, memory weights, decay/expiry formulas — none exist in any authority; explicitly not invented.
- Reason-code semantics for any new cross-run event type.
- Whether/how Evidence Review data should ever influence future runs.
- Which reading of John's original "feedback loop" complaint is meant (see `section_f_feedback_loop_spec_search_v0.1.3.json`) — this audit maps what exists, it does not resolve that ambiguity.

## Files inspected (representative, not exhaustive)

`alpha_library/`, `exposure/seed_loader.py`, `exposure_engine.py`, `storage/db/schema.py`, `storage/db/repository.py`, `storage/db/exposure_persistence.py`, `storage/db/week4_persistence.py`, `graph_engine/activation_scorer_v2.py`, `graph_engine/alpha_level_classifier.py`, `conflict_engine/conflict_detector.py`, `conflict_engine/invalidation_registry.py`, `conflict_engine/conflict_evidence_ui.py`, `structure_engine/structure_extractor.py`, `research_lifecycle.py`, `evaluation/cross_run.py` + `metrics.py`, `api/routes_research.py`, `frontend/src/components/AlphaCard.tsx`/`ConflictCard.tsx`, `docs/audit_artifacts/evidence_review_summary_v2.json`, plus ~30 targeted grep sweeps across the full worktree for every concept in the task's keyword list.

## Provider calls: 0. TradingAgents calls: 0.
