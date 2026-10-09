# What-if: pairs declared as REQUIRED (NOT approved; a controlled label edit)

The label copy `whatif_required.yaml` moves NVDA A101__A304 and A301__A304, SNDK A201__A304 and MSFT A102__A304 from conditional_conflicts to required_conflicts. Nothing is approved; it only shows what the engine does with a required pair on the real saved runs (the six pinned runs, read-only, zero network attempts).

| Ticker | Pair | Round 23 | Round 24 | Round 24 state | Reasons the run recorded |
|---|---|---|---|---|---|
| NVDA | A101__A304 | fail | not_applicable | b2_rejected | BULL_SCORE_BELOW_THRESHOLD |
| NVDA | A301__A304 | fail | not_applicable | b2_rejected | NO_BULL_TICKER_SPECIFIC_SUPPORT |
| SNDK | A201__A304 | not_applicable | not_evaluable | no_arbitration_record | no record |
| MSFT | A102__A304 | not_applicable | not_evaluable | no_arbitration_record | no record |

| Ticker | Round 23 formal_status | Round 24 formal_status |
|---|---|---|
| NVDA | fail | needs_review |
| SNDK | needs_review | needs_review |
| MSFT | needs_review | needs_review |

Reading: NVDA's two pairs were B2's correct rejections (A101 scored 48.55, below 50; A301 had no ticker-specific support), and Round 23 turned NVDA into a `fail` for them. SNDK's and MSFT's pairs have no record in the saved conflicts.json (the runs predate the taxonomy declaration): Round 23 read that as `not_applicable`; it is now `not_evaluable`, and the required pair keeps the status at needs_review.
