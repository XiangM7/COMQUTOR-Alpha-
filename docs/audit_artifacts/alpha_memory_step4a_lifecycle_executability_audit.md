# Alpha Memory — Step 4A: Lifecycle / Invalidation Executability Audit

Read-only product + code audit. **No production code, tests, phi identity, or recurrence semantics modified. Provider calls: 0. TradingAgents calls: 0.**

## Headline finding

**30 invalidation conditions enumerated across all 10 canonical Alphas (4 formally Product-Owner-approved for A101; 26 non-authoritative taxonomy phrases for all 10 Alphas). Zero are executable now — deterministically or otherwise — from currently persisted data.** Every one requires external market/macro data this pipeline doesn't ingest, a new LLM semantic judgment not currently performed for this purpose, an undefined threshold, or lacks formal approval provenance entirely.

| Classification | Count |
|---|---|
| EXECUTABLE_NOW_DETERMINISTIC | 0 |
| EXECUTABLE_FROM_EXISTING_STRUCTURED_OUTPUT | 0 |
| REQUIRES_NEW_SEMANTIC_JUDGMENT | 3 |
| REQUIRES_EXTERNAL_DATA | 9 |
| REQUIRES_PRODUCT_THRESHOLD | 0 |
| AMBIGUOUS | 4 |
| DISPLAY_ONLY | 10 |

## Invalidation authority

**No.** The only formal authority (A101's 4 approved conditions) defines invalidation in terms this pipeline cannot evaluate. Of 8 candidate signals tested (taxonomy conditions, B1 opposing evidence, counter-Alpha dominance, evidence disappearance, loss of local structure support, aggregate fingerprint change, phi absence, historical Alpha-level decline): **1 is AUTHORIZED as content but not as an executable rule; 4 are POSSIBLE_INPUT_BUT_RULE_UNDEFINED; 3 are NOT_VALID_FOR_INVALIDATION** (evidence disappearance, aggregate fingerprint change, and phi absence — all explicitly ruled out, consistent with Step 3's own boundary).

## Expired / Failed / Non-execution

All three: **PRODUCT_DECISION_REQUIRED.** No time-to-live/run-count/inactivity-window rule exists anywhere for EXPIRED. FAILED conflates at least 8 genuinely distinct interpretations (failed prediction, contradicted-by-evidence, never-confirmed, lost activation, lost arbitration, non-execution, data-quality failure, runtime/provider failure) that the Plan never operationally separates. NON_EXECUTION has no existing production object authoritatively mapped to the patent's concept — COMQUTOR has no execution layer at all (explicit MVP scope guard), and reinterpreting candidate/suppressed/blocked states as "non-execution" would be an unauthorized new analogy.

## Absence semantics

**`ABSENCE_ONLY = NO_LIFECYCLE_EVENT`** — confirmed with three real, concrete cases from actual persisted NVDA structure graphs. The same real causal claim (`ai_capex → gpu_demand`) disappears from Alpha Memory's view in several real runs purely because its Alpha-linkage metadata was empty in those runs — not because the underlying claim changed. Edge-type flips (causal↔supportive) and alpha-attribution churn on identical node pairs are both fully explained by already-documented pipeline extraction variance, never by evidenced thesis change. In every case inspected, what might superficially look like invalidation is satisfactorily explained by known noise, not genuine signal.

## Reason-code catalog (highlights)

14 code families cataloged across B4, B2, exposure, semantic health, LLM transport, and regression-authority domains. Two are **SAFE_REUSE** (semantic execution health status reasons; artifact-completeness family — both already reused by Step 3's own eligibility filter). Several are **REUSE_WITH_NAMESPACE_ONLY** (the pattern is good, the literal code must not be reused verbatim). Others are **SEMANTIC_MISMATCH** or **NOT_MEMORY_RELATED** — infrastructure/transport failures and within-run scoring gates must never be conflated with a thesis-level memory concept.

## Recommended minimum model: **MODEL 0**

No lifecycle events can be operationalized yet. Model 1 needs at least one deterministically-evaluable condition — zero exist. Model 2 needs an executable invalidation rule — none exists either. This is the audit's honest conclusion, not a failure: Steps 1–3's purely observational recurrence/history layer remains fully valid and useful on its own; it simply isn't "lifecycle" in the invalidation/expiry/failure sense the Plan names, not yet.

## Event model (spec only, not implemented)

Fields specified for future use: `event_type, phi_id, ticker, alpha_id, current_run_id, prior_run_id_or_reference, reason_code, reason_detail, evidence_refs, detected_at, authority_source, event_schema_version`. **Not implemented, not persisted.** Critical separation maintained: a fact (e.g. "ticker-specific evidence count = 0") never automatically becomes an interpretation (e.g. "phi invalidated") without an explicit, Product-approved rule connecting them.

## Persistence recommendation

**Recompute-from-source by default**, matching Steps 1–3's own established pattern — better for auditability, deterministic replay, taxonomy/version changes, and reclassification. Durable persistence considered later, narrowly, only if a genuine measured performance problem justifies it. **No DB table recommended now.**

## Modulation boundary

Four future candidates identified (an eventual invalidation rule's output; historical Alpha-level decline, pending a not-yet-built prior-activation reader; recurrence/recurrence_ratio itself) — **none specified with any weight, formula, threshold, or direction.** `activation_modulation_applied` remains hardcoded `false`.

## Files/artifacts inspected

Taxonomy and invalidation registry YAMLs; B4/B2/exposure/conflict production modules; `authority_contract.py`, `semantic_execution_health.py`; LLM transport error codes; `comqutor_alpha/memory/*` (Steps 1–3, read-only); real NVDA `structure_graph.json` across ~10 persisted runs; the Development Plan docx (re-confirmed, no new extraction needed); prior Steps 1.5/1.6/3 audit artifacts.

**Provider calls: 0. TradingAgents calls: 0.**
