# NVDA Fresh Run -- key conclusions and Alpha/conflict candidates (v2, corrected)

run_id: `034a0a60-430e-41f8-8321-03a11389707a` | ticker: NVDA | analysis_date: 2026-10-02

**This v2 corrects a real error in the v1 package's own narrative** (not a change to any underlying research result): v1 reported Activation scores of 96.69/100/84.36/etc. as if they were this run's headline Activation picture. Those were the `activation_versions.v1` score set -- the oldest, most permissive diagnostic formula (`week3.activation.mvp_v1`). **This run's actual primary/official Activation result (`v2_verified`, `activation.v2.evidence_local_structure.verified_gate.v1`) is 0.0 for every single Alpha.** See `08_source_coverage_root_cause_analysis.md` in this package for the full, code-traced explanation of why, and for the precise request-accounting/audit-trail fix, see `09_concurrent_audit_fix_and_request_reconciliation.md`. Nothing about the underlying research run changed between v1 and v2 of this package -- only this package's own description of which number is official.

## Official result (the full, accurate picture)

- **No Alpha is officially dominant, and no main conflict is reported.** The reason is specific and traceable, not "weak signal": **zero of this run's 1040 claims have ever been through human review** (`content_support_review.method` is `UNREVIEWED` for all 1040, with no exception). The verified-evidence eligibility gate (`comqutor_alpha.source_provenance.compute_verified_support_eligibility`) requires a genuine `HUMAN_REVIEWED` review as one of its conditions -- unsatisfiable for any claim in a run this fresh, by design, not by defect. This is the single, sufficient, confirmed reason `v2_verified` (and this run's own reported `dominant_alphas`/`current_evidence`) are empty/zero everywhere.
- Two **diagnostic-only** score sets (`v1`, the oldest MVP formula; `v2`, a newer "evidence_local_structure" formula) do **not** require human review and found real, structured signal -- most strongly for A101/A102/A103 (AI-expansion/inference/infrastructure) on the positive side and A304/A501 (valuation compression/recession risk) on the negative side. **These are candidates for review, never official results.**

### Activation across all three score sets, per Alpha (diagnostic v1/v2 vs. official v2_verified)

| Alpha | Name | v1 (diagnostic) | v2 (diagnostic) | **v2_verified (official)** | current_evidence |
|---|---|---|---|---|---|
| A101 | AI Expansion | 96.69, regime_level | 53.43, active | **0.0, candidate** | 0.0 |
| A102 | Inference Explosion | 100.0, regime_level | 66.0, active | **0.0, candidate** | 0.0 |
| A103 | AI Infrastructure | 84.36, dominant | 45.35, watch | **0.0, candidate** | 0.0 |
| A201 | Semiconductor Supercycle | 65.49, active | 18.37, inactive | **0.0, candidate** | 0.0 |
| A301 | Revenue Expansion | 100.0, regime_level | 32.87, watch | **0.0, candidate** | 0.0 |
| A304 | Multiple Compression | 92.10, regime_level | 19.67, inactive | **0.0, candidate** | 0.0 |
| A501 | Recession Risk | 99.09, regime_level | 51.03, active | **0.0, candidate** | 0.0 |
| A601 | Narrative Momentum | 88.21, regime_level | 36.54, watch | **0.0, candidate** | 0.0 |
| A001, A003 | Rate Cut Cycle, Liquidity Expansion | 0.0, inactive | 0.0, inactive | 0.0, candidate | 0.0 |

- **Main conflict: none** at the official (`v2_verified`) level, for the same reason -- no claim is verified. 8 candidate conflict pairs were separately evaluated by the diagnostic-level arbitration gate (independent of the human-review question); all 8 were rejected (0 admitted). See the per-pair breakdown below.
- Of 1040 total structured claims, **137 claims** received a non-null `matched_alpha` from the single-claim LLM classifier (diagnostic layer). Those collapsed into **9 distinct Alpha IDs** at the Activation-scoring stage.

## Main Alpha candidates (diagnostic claim-level matches, by Alpha ID -- never official)

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

Full claim-by-claim detail (which specific claims matched each Alpha and why) is in `02_claim_index_full.json`.

## Conflict candidates -- both sides, as actually evaluated

**Correction**: this arbitration is **not independent of the human-review gate**. Each pair's own real, top-level verdict code is `DIRECTION_ROLE_UNRESOLVED` (2 pairs also `MISSING_LEFT_EVIDENCE`) -- a direct consequence of zero claims being `HUMAN_REVIEWED` (see `08_source_coverage_root_cause_analysis.md`): with no verified evidence on either side, no pair's bull/bear role can be resolved. The per-claim `evidence_audit` exclusion reasons below are real, separate, lower-level detail about each side's raw candidate pool -- not the pair's own verdict, and the two must not be read as "two independent gates agreeing."

All 8 real candidate pairs, verified directly against `conflicts.json`'s own `arbitration.candidate_evaluations` (not reconstructed from memory):

| pair | outcome | top-level reason_codes | side A excluded | side A reasons | side B excluded | side B reasons |
|---|---|---|---|---|---|---|
| A001 vs A501 | rejected | MISSING_LEFT_EVIDENCE, DIRECTION_ROLE_UNRESOLVED | 1036 | NON_ANALYTICAL_QUALITY, NON_COMMITTED_MATCH, WRONG_ALPHA | 61 | NON_ANALYTICAL_QUALITY, NON_COMMITTED_MATCH, UNSUPPORTED_RELATION, WRONG_ALPHA |
| A003 vs A501 | rejected | MISSING_LEFT_EVIDENCE, DIRECTION_ROLE_UNRESOLVED | 1019 | NON_COMMITTED_MATCH, WRONG_ALPHA | 61 | NON_ANALYTICAL_QUALITY, NON_COMMITTED_MATCH, UNSUPPORTED_RELATION, WRONG_ALPHA |
| A101 vs A304 | rejected | DIRECTION_ROLE_UNRESOLVED | 1025 | NON_ANALYTICAL_QUALITY, NON_COMMITTED_MATCH, WRONG_ALPHA | 92 | NON_ANALYTICAL_QUALITY, NON_COMMITTED_MATCH, UNSUPPORTED_RELATION, WRONG_ALPHA |
| A102 vs A304 | rejected | DIRECTION_ROLE_UNRESOLVED | 940 | NON_ANALYTICAL_QUALITY, NON_COMMITTED_MATCH, WRONG_ALPHA | 92 | NON_ANALYTICAL_QUALITY, NON_COMMITTED_MATCH, UNSUPPORTED_RELATION, WRONG_ALPHA |
| A201 vs A304 | rejected | DIRECTION_ROLE_UNRESOLVED | 27 | NON_ANALYTICAL_QUALITY, NON_COMMITTED_MATCH, UNSUPPORTED_RELATION, WRONG_ALPHA | 92 | NON_ANALYTICAL_QUALITY, NON_COMMITTED_MATCH, UNSUPPORTED_RELATION, WRONG_ALPHA |
| A301 vs A304 | rejected | DIRECTION_ROLE_UNRESOLVED | 78 | NON_ANALYTICAL_QUALITY, NON_COMMITTED_MATCH, UNSUPPORTED_RELATION, WRONG_ALPHA | 92 | NON_ANALYTICAL_QUALITY, NON_COMMITTED_MATCH, UNSUPPORTED_RELATION, WRONG_ALPHA |
| A304 vs A601 | rejected | DIRECTION_ROLE_UNRESOLVED | 92 | NON_ANALYTICAL_QUALITY, NON_COMMITTED_MATCH, UNSUPPORTED_RELATION, WRONG_ALPHA | 74 | NON_ANALYTICAL_QUALITY, NON_COMMITTED_MATCH, UNSUPPORTED_RELATION, WRONG_ALPHA |
| A501 vs A601 | rejected | DIRECTION_ROLE_UNRESOLVED | 61 | NON_ANALYTICAL_QUALITY, NON_COMMITTED_MATCH, UNSUPPORTED_RELATION, WRONG_ALPHA | 74 | NON_ANALYTICAL_QUALITY, NON_COMMITTED_MATCH, UNSUPPORTED_RELATION, WRONG_ALPHA |

All 8 rejected (0 admitted). Full per-pair evidence audit (every excluded claim's own id and reason code) is in `04_derived_metrics/conflicts.json`.

## Source coverage, honestly disclosed (see `08_source_coverage_root_cause_analysis.md` for the full root-cause breakdown)

- 1040 structured claims total. 24 have `source_link_status=VALID`; 1016 have `NOT_PROVIDED`.
- Re-running the real, unmodified source-linking functions offline against every claim found: 1001/1016 show no plausible external source at all (genuinely internal analysis/debate text); 15/1016 show a plausible (not confirmed) textual connection to one of 40 real, registered-but-content-less news sources; **0** cases where the production pipeline missed a candidate the real matching logic would have found (no implementation defect in the linking logic itself this run).
- All 40 "news"-type sources (100%, `provider=yfinance`) lack `excerpt`/`fragment_id`, making `SOURCE_LINK_VALID` structurally impossible for them regardless of claim wording. Root cause (external API limitation vs. an extraction defect) could not be determined from this run's frozen artifacts and is marked **UNKNOWN**, not guessed.
- All 24 VALID-linked claims are `content_support_status=PENDING_REVIEW` (never reviewed) and none carry `ticker_specific=true` in their own record (a separate, deliberate design property of `_is_ticker_specific`, not a defect -- see `08_source_coverage_root_cause_analysis.md`).
- "CANNOT_JUDGE" remains an explicitly valid answer throughout the review form for exactly this reason.
