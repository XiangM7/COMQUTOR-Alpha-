# Adaptive Alpha Memory / Feedback Loop — Phase 2 Spec Freeze

Specification only. No production code, tests, Provider calls, or TradingAgents calls. **Provider calls: 0. TradingAgents calls: 0.**

Phase 1 implementation (once authorized) MUST be **SHADOW ONLY**: `activation_modulation_applied = false`, hardcoded, throughout.

## Authoritative source (Development Plan, verbatim)

- **Phase 2 roadmap**: "persist structure identities across runs; match recurring causal chains to stable ϕ-IDs; store invalidation/non-execution events with reason codes and use them to modulate future activation."
- **Structure Memory row**: "Alpha Structure Library (taxonomy YAML) + entity_alpha_exposure history" — MVP status "**MVP static seed; adaptive Phase 2**" — this is the Plan's own confirmation that today's static seed is correctly MVP-scope, and adaptivity is Phase 2.
- **Worked φ example**: "ϕ-001 = AI demand → GPU shortage → NVDA benefits" — a causal *chain*, not a single node; its premise steps are ticker-general, its conclusion is ticker-specific.
- The words **"observed", "repeated", "absent" do not appear anywhere in the Plan** — they are this spec's own organizing vocabulary, not authoritative terms.
- `invalidation_conditions` appears in the Plan's own worked Alpha JSON schema as a **static per-Alpha field**, confirming Step 0's audit: it is taxonomy metadata, not a runtime event log, by the Plan's own design.
- **Phase 3** ("Stabilization & readout windows... update window") is a separate, later roadmap phase — explicitly out of scope here.

## A. Minimum feedback loop

```
previous persisted runs (existing DB tables + JSON artifacts)
  → stable structure identity (phi) — node-level: reuse existing; chain-level: new
  → cross-run matching — new, read-only
  → historical observation ledger — new aggregation, existing source tables
  → lifecycle/event detection — new, only for AUTHORIZED event types
  → shadow memory assessment — new, additive
  → run_audit.json alpha_memory section — new, existing convention
```

Every step is a **read** of already-persisted data, or a new read-only computation over it. Nothing writes into or is consulted by `activation_scorer_v2.py`, `alpha_level_classifier.py`, `conflict_detector.py`, or `conflict_admissibility.py`.

## B. φ / stable identity model

**Scope verdict: SCOPE-DEPENDENT**, not resolvable to one blanket rule. The Plan's own worked example (a chain whose premise is ticker-general, whose conclusion is ticker-specific) plausibly *explains* the current code's inconsistency (only "Revenue Growth" is ticker-scoped) rather than making it a bug — but the Plan never states this as a governing rule, and which of the 110 canonical factors are "premise" vs "conclusion" is undocumented.

- **Reusable as-is**: `structure_extractor.py::_make_node`'s deterministic node id — already cross-run-stable, already persisted, zero extractor change needed.
- **Cannot be reused unchanged**: the current ticker-scoping rule itself — built for intra-run dedup, not cross-run/cross-ticker phi disambiguation.
- **Missing entirely**: chain-level (multi-hop path) identity — the Plan's *actual* φ-token unit. Node identity is necessary but not sufficient.
- **Versioning**: a `phi_identity_version` string is required from day one, following this codebase's existing frozen-hash-guard convention — no silent reinterpretation of persisted phi ids.
- **Collision risks**: cross-ticker collision for ticker-independent factors (may be intended); taxonomy-drift collision; chain-boundary ambiguity from independent LLM extraction runs.

## C. Historical observation model

Every fact needed already exists in already-persisted, already-queryable form (`structure_graphs`, `alpha_activations`, `entity_alpha_exposures`, `alpha_conflicts` tables and their JSON mirrors) **except `phi_id` itself**, which is new derived data — not a new raw fact. **No new table is required to store raw observations.**

## D. Lifecycle events — authority status

| Event | Authority | Operational definition |
|---|---|---|
| Recurrence | **AUTHORIZED** (concept) | PRODUCT_DECISION_REQUIRED (matching rule) |
| Invalidated | **AUTHORIZED** (concept) | PRODUCT_DECISION_REQUIRED (detection mechanism) |
| Expired | **AUTHORIZED** (concept) | PRODUCT_DECISION_REQUIRED (window — must not be invented) |
| Failed | **AUTHORIZED** (concept) | PRODUCT_DECISION_REQUIRED (what counts as failure) |
| Non-execution | **AUTHORIZED** (concept, patent-derived analogy) | PRODUCT_DECISION_REQUIRED (COMQUTOR has no execution concept at all) |
| Reason codes | **AUTHORIZED** (must exist) | PRODUCT_DECISION_REQUIRED (actual vocabulary — never repurpose the 4 existing B4 codes) |
| Observed / repeated / absent | **NOT FOUND IN THE PLAN** | PRODUCT_DECISION_REQUIRED in full |

## E. Shadow memory output (proposed, not final)

Additive `alpha_memory` section on `run_audit.json` (same convention as `activation_summary`/`conflict_summary`): `mode: "shadow"`, `phi_matches`, `historical_observations`, `lifecycle_events` (only populated for authorized types), `shadow_memory_signal` (descriptive text, never a score/weight), `activation_modulation_applied: false` (hardcoded constant).

## F. Evidence Review boundary

**PRODUCT_DECISION_REQUIRED.** No connection made this phase. `evidence_review_summary_v2.json` stays QA-only, exactly as today — the Plan never requires connecting them.

## G. Reuse plan

Structure Extractor's node id; the four existing per-run DB tables (no migration); `authority_contract.py`'s vocabulary *pattern* (a new, separate vocabulary file, not literal reuse); `run_audit.json`'s additive-section convention; this codebase's frozen-hash-guard pattern.

## H. Implementation phases

| Phase | Name | DB migration | Provider calls | TradingAgents calls | Semantics changed |
|---|---|---|---|---|---|
| 1 | Stable identity | No | No | No | No |
| 2 | Cross-run history reader | No | No | No | No |
| 3 | Historical observation ledger | No | No | No | No |
| 4 | Lifecycle events | Maybe (only if persisted) | No | No | No |
| 5 | Shadow memory engine | No | No | No | No |
| 6 | Artifact/API/UI | No | No | No | No |
| 7 | Offline replay QA | No | No | No | No |

**Target Provider calls = 0, TradingAgents calls = 0 through all 7 phases**, until an explicitly separate, future, authorized fresh regression.

## I. Non-negotiable constraints — confirmed untouched by this spec

B1 stance, B2 admissibility thresholds, B4 thresholds/formula, Alpha taxonomy, canonical conflict pairs, existing human-reviewed labels. No memory-modulation weights introduced. Static `historical_mapping` is explicitly **not** claimed to be adaptive memory.

## Files created

`docs/audit_artifacts/alpha_memory_phase2_spec.json`, this file.

**Provider calls: 0. TradingAgents calls: 0.**
