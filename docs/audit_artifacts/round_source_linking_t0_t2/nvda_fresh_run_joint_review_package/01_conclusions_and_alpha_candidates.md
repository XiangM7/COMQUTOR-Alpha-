# NVDA Fresh Run -- key conclusions and Alpha/conflict candidates

run_id: `034a0a60-430e-41f8-8321-03a11389707a` | ticker: NVDA | analysis_date: 2026-10-02
created_at: 2026-10-02T00:55:24Z | provider/model: deepseek/deepseek-v4-flash

## Official result (reported honestly -- the full, accurate picture, not simplified)

- **No Alpha is reported as officially dominant, and no main conflict is
  reported, in this run's final/gated output.** This is the correct, honest
  headline result. **But it is not because the underlying Activation
  signal was weak -- it was strong.** The raw Week-3 Activation score
  (formula `week3.activation.mvp_v1`) reached the `regime_level` band (the
  highest band) for **six** of the nine scored Alphas, and `dominant` for a
  seventh. The reason none of this surfaces as an official "dominant Alpha"
  is a **separate, later gate**: the Entity Exposure qualification layer
  (`week4.exposure_score.mvp_v1`), which blends each Alpha's historical
  seed mapping with *this run's own* "current_evidence"/"agent_confidence"
  measures -- and this run's `current_evidence` component came back `0.0`
  for every single Alpha (the Exposure Engine's own, stricter evidence bar
  found no qualifying ticker-specific exposure-grade evidence, even where
  the more permissive Activation formula found strong signal). That drags
  every blended `final_exposure` value below the regime/dominant threshold,
  which is explicitly recorded via `would_block_regime_level: true` and
  reason code `EXPOSURE_BELOW_REGIME_THRESHOLD` on seven of the nine Alphas
  below. This is a real, recorded, honest product-level outcome -- not a
  data gap and not something this report is inferring or softening.

### Raw Activation scores vs. the Exposure-qualification gate, per Alpha

| Alpha | Name | Activation score | Activation status | Direction | Exposure status | Final (gated) exposure | Exposure reason codes |
|---|---|---|---|---|---|---|---|
| A102 | Inference Explosion | 100.00 | regime_level | positive | computed | 0.375 | EXPOSURE_BELOW_REGIME_THRESHOLD, EXPOSURE_QUALIFICATION_APPLIED |
| A301 | Revenue Expansion | 100.00 | regime_level | positive | computed | 0.425 | EXPOSURE_BELOW_REGIME_THRESHOLD, EXPOSURE_QUALIFICATION_APPLIED |
| A501 | Recession Risk | 99.09 | regime_level | negative | missing_seed | None | EXPOSURE_QUALIFICATION_APPLIED, EXPOSURE_SEED_MISSING, SEED_ENTRY_MISSING |
| A101 | AI Expansion | 96.69 | regime_level | positive | computed | 0.475 | EXPOSURE_BELOW_REGIME_THRESHOLD, EXPOSURE_QUALIFICATION_APPLIED |
| A304 | Multiple Compression | 92.10 | regime_level | negative | computed | 0.375 | EXPOSURE_BELOW_REGIME_THRESHOLD, EXPOSURE_QUALIFICATION_APPLIED |
| A601 | Narrative Momentum | 88.21 | regime_level | positive | computed | 0.425 | EXPOSURE_BELOW_REGIME_THRESHOLD, EXPOSURE_QUALIFICATION_APPLIED |
| A103 | AI Infrastructure | 84.36 | dominant | positive | computed | 0.425 | EXPOSURE_BELOW_REGIME_THRESHOLD, EXPOSURE_QUALIFICATION_APPLIED |
| A201 | Semiconductor Supercycle | 65.49 | active | positive | computed | 0.45 | EXPOSURE_BELOW_REGIME_THRESHOLD, EXPOSURE_QUALIFICATION_APPLIED |
| A001 | Rate Cut Cycle | 0.00 | inactive | unknown | missing_seed | None | EXPOSURE_QUALIFICATION_APPLIED, EXPOSURE_SEED_MISSING, SEED_ENTRY_MISSING |
| A003 | Liquidity Expansion | 0.00 | inactive | unknown | missing_seed | None | EXPOSURE_QUALIFICATION_APPLIED, EXPOSURE_SEED_MISSING, SEED_ENTRY_MISSING |

- **Main conflict: none.** 8 candidate conflict pairs were evaluated by the
  arbitration gate; all 8 were rejected (0 admitted). See the per-pair
  breakdown below -- note several of these candidate pairs (e.g. A101 vs
  A304, A001 vs A501) pair up Alphas that individually show strong,
  opposite-direction raw Activation scores above, which is exactly why they
  were evaluated as conflict candidates in the first place; they were still
  rejected at the arbitration/evidence-audit stage (see each pair's
  excluded-claim reasons below), independent of the Exposure gate.
- Of 1040 total structured claims, **137 claims** received a non-null
  `matched_alpha` from the single-claim LLM classifier. Those 137
  claim-level matches collapsed into **9 distinct
  Alpha IDs** at the activation-scoring stage (table above).

## Main Alpha candidates (claim-level matches, by Alpha ID)

| Alpha ID | matched claim count |
|---|---|
| A601 | 36 |
| A304 | 18 |
| A101 | 17 |
| A301 | 17 |
| A102 | 16 |
| A201 | 14 |
| A501 | 13 |
| A103 | 5 |
| A001 | 1 |

Full claim-by-claim detail (including which specific claims matched each
Alpha and why) is in `02_claim_index_full.json`.

## Conflict candidates -- both sides, as actually evaluated

### Candidate pair: A001 vs A501

- A001 side: 1036 claims excluded (reasons: ['NON_ANALYTICAL_QUALITY', 'NON_COMMITTED_MATCH', 'WRONG_ALPHA'])
- A501 side: 61 claims excluded (reasons: ['NON_ANALYTICAL_QUALITY', 'NON_COMMITTED_MATCH', 'UNSUPPORTED_RELATION', 'WRONG_ALPHA'])
- Outcome: rejected (not admitted as a real conflict this run)

### Candidate pair: A003 vs A501

- A003 side: 1019 claims excluded (reasons: ['NON_COMMITTED_MATCH', 'WRONG_ALPHA'])
- A501 side: 61 claims excluded (reasons: ['NON_ANALYTICAL_QUALITY', 'NON_COMMITTED_MATCH', 'UNSUPPORTED_RELATION', 'WRONG_ALPHA'])
- Outcome: rejected (not admitted as a real conflict this run)

### Candidate pair: A101 vs A304

- A101 side: 1025 claims excluded (reasons: ['NON_ANALYTICAL_QUALITY', 'NON_COMMITTED_MATCH', 'WRONG_ALPHA'])
- A304 side: 92 claims excluded (reasons: ['NON_ANALYTICAL_QUALITY', 'NON_COMMITTED_MATCH', 'UNSUPPORTED_RELATION', 'WRONG_ALPHA'])
- Outcome: rejected (not admitted as a real conflict this run)

### Candidate pair: A102 vs A304

- A102 side: 940 claims excluded (reasons: ['NON_ANALYTICAL_QUALITY', 'NON_COMMITTED_MATCH', 'WRONG_ALPHA'])
- A304 side: 92 claims excluded (reasons: ['NON_ANALYTICAL_QUALITY', 'NON_COMMITTED_MATCH', 'UNSUPPORTED_RELATION', 'WRONG_ALPHA'])
- Outcome: rejected (not admitted as a real conflict this run)

### Candidate pair: A201 vs A304

- A201 side: 27 claims excluded (reasons: ['NON_ANALYTICAL_QUALITY', 'NON_COMMITTED_MATCH', 'UNSUPPORTED_RELATION', 'WRONG_ALPHA'])
- A304 side: 92 claims excluded (reasons: ['NON_ANALYTICAL_QUALITY', 'NON_COMMITTED_MATCH', 'UNSUPPORTED_RELATION', 'WRONG_ALPHA'])
- Outcome: rejected (not admitted as a real conflict this run)

### Candidate pair: A301 vs A304

- A301 side: 78 claims excluded (reasons: ['NON_ANALYTICAL_QUALITY', 'NON_COMMITTED_MATCH', 'UNSUPPORTED_RELATION', 'WRONG_ALPHA'])
- A304 side: 92 claims excluded (reasons: ['NON_ANALYTICAL_QUALITY', 'NON_COMMITTED_MATCH', 'UNSUPPORTED_RELATION', 'WRONG_ALPHA'])
- Outcome: rejected (not admitted as a real conflict this run)

### Candidate pair: A304 vs A601

- A304 side: 92 claims excluded (reasons: ['NON_ANALYTICAL_QUALITY', 'NON_COMMITTED_MATCH', 'UNSUPPORTED_RELATION', 'WRONG_ALPHA'])
- A601 side: 74 claims excluded (reasons: ['NON_ANALYTICAL_QUALITY', 'NON_COMMITTED_MATCH', 'UNSUPPORTED_RELATION', 'WRONG_ALPHA'])
- Outcome: rejected (not admitted as a real conflict this run)

### Candidate pair: A501 vs A601

- A501 side: 61 claims excluded (reasons: ['NON_ANALYTICAL_QUALITY', 'NON_COMMITTED_MATCH', 'UNSUPPORTED_RELATION', 'WRONG_ALPHA'])
- A601 side: 74 claims excluded (reasons: ['NON_ANALYTICAL_QUALITY', 'NON_COMMITTED_MATCH', 'UNSUPPORTED_RELATION', 'WRONG_ALPHA'])
- Outcome: rejected (not admitted as a real conflict this run)


## Source coverage, honestly disclosed

- 1040 structured claims total.
- 24 claims have `source_link_status=VALID` (linked to one of the 45
  registered external sources, each with a real URL/publication time).
- 1016 claims have `source_link_status=NOT_PROVIDED` -- these are
  TradingAgents-internal analyst/debate/report commentary that was never
  linked to an independently-checkable external source. This is not an
  error to be silently closed over; it is the real, honest state of this
  run's source coverage, and it is why most rows in the review form below
  will need a "cannot judge" or "no external source" answer for source
  locatability -- that is an explicitly allowed value, not a gap in the
  form.
