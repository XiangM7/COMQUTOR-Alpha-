# Alpha Memory — Step 2: Atomic Edge φ Adopted

SHADOW ONLY. **Provider calls: 0. TradingAgents calls: 0. No fresh research. No commit, no push.**

## Final identity formula

```
phi_id = sha256(json_canonical({
  identity_version: "alpha_memory.phi_edge.v1",
  ticker, alpha_id, taxonomy_version, taxonomy_sha256,
  source, edge_type, target
}))
```

`alpha_id` and `edge_type` are **both retained** — the ablation audit showed dropping either would silently merge structures with real, non-noise semantic content.

## Hierarchy

- **Level 1 (primary)**: atomic edge φ — one per qualifying edge per Alpha.
- **Level 2 (secondary)**: whole-Alpha aggregate fingerprint — Step 1's original computation, arithmetic **unchanged**, renamed `aggregate_fingerprint_id` / `alpha_memory.aggregate_fingerprint.v1`, reported separately, never the primary identity.
- **Motif level**: deferred, unchanged.

## One Alpha → many φ tokens

Confirmed: an Alpha with N qualifying edges produces N atomic φ records. Real NVDA data: A101 alone produced 5 atomic tokens from its 5 linked edges. The same literal edge linked to two Alphas produces two separate records — never collapsed.

## Aggregate fingerprint behavior

Explicitly reported under `aggregate_fingerprints` with its own id field and version string — no consumer can mistake it for the primary φ. Real NVDA pair: 0 of 6/5 aggregate fingerprints matched, while **2** atomic edges did — direct proof the old whole-set approach materially understated real recurrence.

## Cross-run reader changes

Primary matching is now atomic-φ-based (`find_prior_phi_edge_observations`) — no longer requires an entire Alpha edge-set to agree. New: `build_phi_structures` (combines identity + history), `summarize_alpha_memory` (descriptive per-Alpha rollup, never a score), `detect_alpha_attribution_variance`, `detect_edge_type_variance`.

## Real NVDA result

`2f8ee897` vs `c9abf687`: **atomic exact matches = 2** (A101, A102) vs **aggregate exact matches = 0**. Atomic matching > whole-Alpha matching, confirmed on real data — actual values, not manufactured.

Bonus: scanning the *complete* persisted NVDA history (not just this one pair) from `2f8ee897`: 15 current atomic tokens, per-Alpha historical matches A001 1/2, A101 1/5, A102 1/2, A103 2/4, A301 1/1, A501 0/1; **12** alpha-attribution-variance signals and **7** edge-type-variance signals detected.

## Real MSFT result

`07ddc074` vs `6cd2566d`: **atomic exact matches = 0**, **aggregate exact matches = 0** — both zero, reported honestly. Root cause (from Step 1.6): `07ddc074` has only 1 edge with any `alpha_ids` attached at all, an independent data-quality limitation of that specific run, not a defect of the atomic model. This pair does not demonstrate the improvement; NVDA does.

## Alpha-attribution instability diagnostic

Audit-only. No merging, no scoring, no penalty. `test_alpha_attribution_variance_is_detected_and_does_not_merge_phi_ids` proves both variants remain listed with distinct φ ids, no field labels either "correct." Real data: 12 signals across NVDA's full history.

## Edge-type instability diagnostic

Same guarantees. Real data: 7 signals across NVDA's full history.

## Files changed

**Rewritten**: `comqutor_alpha/memory/phi_identity.py`, `history_reader.py`. **Modified**: `comqutor_alpha/api/routes_research.py` (`_alpha_memory_section` restructured). **Rewritten tests**: `test_alpha_memory_phi_identity.py` (16), `test_alpha_memory_history_reader.py` (13). **Modified tests**: `test_run_audit_v2.py` (+1, 26 total). **Regenerated (offline, zero cost)**: both real NVDA runs' `run_audit.json`.

## DB migration: NO.

## Proof B1/B2/B4/Conflict unchanged

`comqutor_alpha/memory/*` still never imported by `activation_scorer_v2.py`/`alpha_level_classifier.py`/`conflict_detector.py`/`conflict_admissibility.py` (AST-verified). A dedicated integration test constructs a real attribution-variance case and proves `activation_summary`/`conflict_summary`/`audit_validation` stay byte-identical. Full 14-file regression sweep: 431 passed, only the same 13 pre-existing, unrelated `evidence_review_v2.json` failures remain.

## Tests

33 new/revised tests, all passing, covering all 17 required proof points.

**Provider calls: 0. TradingAgents calls: 0.**
