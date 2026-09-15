# FINAL Regression / Conflict QA — v0.1.2.1 (Step 10)

Authority-aware regression and conflict QA over the same 6 fresh final production runs (see `final_six_ticker_production_e2e_v0.1.2.1.json/.md` for execution/runtime detail). Branch `comqutor-structure-layer`, HEAD `9f228723fad5406c72e62beca67ec70ea0fdb004` (unchanged). No taxonomy, conflict ontology, regression label, B1, B2, or B4 changes.

## Gold authority state (unchanged from Steps 1–3)

- **Approved-gold Alpha expectations: 0.** Documented expectations: 15. Provisional AI-predicted: 22.
- **Approved-gold Main Conflict expectations: 0.** Documented: 2. Provisional: 5. Rejected/superseded: 4.

Source: `regression_label_authority_audit_v0.1.2.1.json` (unchanged, not touched in Step 10).

## Expected-Alpha regression

**Diagnostic hit rate: 7 / 12 = 58.33%** (comparison against John's 12 historical callouts — `DOCUMENTED_EXPECTATION`/`PROVISIONAL_AI_PREDICTED` authority, never approved gold). John's requested ≥75% threshold is **DIAGNOSTIC ONLY** against this number — never a formal PASS/FAIL claim, since the denominator is not gold-evaluable.

**Formal gate**: `expected_alpha_gate([None]*6)` → `current_status = PENDING_APPROVED_GOLD_OR_VALIDATED_CONTRACT`, `gate_result = null`. Not "0% gold," not "failed because 0/6" — a genuinely undefined (not-yet-evaluable) denominator, reported as such.

The 5 misses (MSFT ×3, TSM ×2) are fully attributable to this run's semantic-runtime-health failure on those two tickers (see the E2E report) — not a semantic recall regression.

## Main-Conflict regression

**Diagnostic comparison: 4 / 6 tickers produced a non-null admitted main conflict** (NVDA, QQQ, SNDK, AMD). This is a coarse "did any conflict admit at all" diagnostic, **not** a match against a specific approved-gold expected pair (none exists) — John's requested ≥4/6 threshold is **DIAGNOSTIC ONLY** here too.

**Formal gate**: `main_conflict_gate({ticker: None for all 6})` → `status = PENDING_GOLD_CONTRACT`, `use_for_current_production_acceptance = False`, `gate_result = null`.

| Ticker | Main conflict | Null reason (where applicable) |
|---|---|---|
| NVDA | A101__A304 | — |
| QQQ | A101__A304 | — |
| MSFT | null | Semantic runtime health failure (3.92% coverage) left insufficient qualifying evidence for any pair to clear B2's unchanged thresholds |
| SNDK | A304__A601 | — |
| TSM | null | Semantic runtime health failure (0.00% coverage) — no qualifying evidence existed at all |
| AMD | A101__A304 | — |

Both nulls are legitimate, expected B2 outcomes given the documented runtime failures — never treated as a bug in themselves.

## Negative constraints: PASS (0 violations)

| Ticker | Pair | Result |
|---|---|---|
| MSFT | A102__A304 | PASS |
| SNDK | A201__A304 | PASS |
| TSM | A201__A304 | PASS |
| AMD | A201__A304 | PASS |

None of these four ontology-forbidden pairs appeared as an admitted main conflict or in the admitted-conflicts list on any ticker. No ontology/implementation defect found.

## Conflict/B2 candidate-evaluation detail

Full per-pair `bull_score`/`bear_score`/`bull_supporting_evidence_count`/`bear_supporting_evidence_count`/ticker-specific-support-counts/admissibility status/rejection reason codes for every canonical pair evaluated on every ticker are in the JSON artifact's `conflict_b2_detail`. B2's own thresholds (score ≥50, ≥2 unique supports_alpha facts per side, ≥1 ticker-specific fact per side) are unchanged in value throughout.

## Summary

| Gate | Result |
|---|---|
| Expected-Alpha diagnostic | 7/12 = 58.33% |
| Expected-Alpha formal | PENDING_APPROVED_GOLD_OR_VALIDATED_CONTRACT |
| Main-Conflict diagnostic | 4/6 non-null |
| Main-Conflict formal | PENDING_GOLD_CONTRACT |
| Negative constraints | PASS (0 violations) |

Neither formal gate can be closed until real, approved gold expectations exist for at least one ticker — this is an authority/product state, not a technical defect discovered by Step 10.
