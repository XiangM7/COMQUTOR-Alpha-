# NVDA run (034a0a60-430e-41f8-8321-03a11389707a): key-conclusion acceptance traceability

Reuses the existing 79-claim AI_REVIEW (`reviewer_id=ChatGPT`, `human_review_performed=false`, `john_approval=false`, `review_mode=NONBLIND_ARTIFACT_AUDIT`) and the 24 VALID-linked claims' own content-support judgments already produced this round -- **no re-review of the other 1040-79 claims was performed**. "All official scores are 0" is not used anywhere below as the sole proof of T1; each row traces a real conclusion through its own real claim, source, and current product display.

## A. Positive cases -- source and content support genuinely hold

| conclusion | claim_id (short) | source fragment | support judgment | current product display |
|---|---|---|---|---|
| NVDA close (228.38, 2026-09-30) sits above all 3 key moving averages | `market_agent:claim:3` | `src_8e61838edf95c591` (real OHLCV/indicator snapshot) | `SNAPSHOT_FACT_SUPPORTED` -- all 4 cited numbers verified against the snapshot | `source_link_status=VALID`, `content_support_status=PENDING_REVIEW` (correctly not yet counted as HUMAN_REVIEWED support anywhere) |
| Bollinger upper/middle/lower bands = 234.69 / 223.13 / 211.56 | `market_agent:claim:56/57/58` | same snapshot | `SNAPSHOT_FACT_SUPPORTED` | same -- `VALID` link, `PENDING_REVIEW` |
| NVDA market cap $5.57T; trailing P/E 29.22 | `fundamental_agent:claim:4/5` | `src_8355190cdfcda8ae` (real fundamentals snapshot) | `SNAPSHOT_FACT_SUPPORTED` | same -- `VALID` link, `PENDING_REVIEW` |

These 6 are genuinely sound at the snapshot-fact level. None is `HUMAN_REVIEWED`; the product correctly withholds official support status from all of them pending that review -- a real positive case is still, correctly, not yet "accepted."

## B. Cases correctly downgraded -- insufficient material, rebuttal, or unreviewed status

| conclusion | claim_id (short) | issue | how the product currently handles it |
|---|---|---|---|
| "MACD crossed back above the signal line" | `market_agent:claim:32` | Current MACD/signal/histogram values match the snapshot; the crossover claim needs the PRIOR period's values, which the single-day snapshot does not contain | `source_link_status=VALID` but `content_support_judgment=PARTIAL_SUPPORT` (missing: prior-period MACD/signal) -- `content_support_status=PENDING_REVIEW`, never auto-promoted |
| "VWMA stands at 222.54, confirming volume-backed gains" | `market_agent:claim:63` | VWMA is not a field in the cited snapshot at all | `PARTIAL_SUPPORT_MATERIAL_VALUE_MISSING` -- the core derived number is absent from its own citation; `PENDING_REVIEW`, not silently accepted |
| "Total Revenue/Assets rose..." / "FCF fell..." | `fundamental_agent:claim:40/69/98` | Each source has exactly one quarterly data point (no prior-period comparison) and `published_at=null` | `PARTIAL_SUPPORT_DISCLOSURE_UNKNOWN` -- trend wording and disclosure time both unverifiable from the cited source; `PENDING_REVIEW` |
| Support/resistance labels on real moving-average levels | `market_agent:claim:43/81/82/83/84` | The numeric level is real; "support"/"resistance"/"trend invalidation" is the analyst's own strategic framing, not a sourced fact | `VALUE_SUPPORTED_ANALYST_INTERPRETATION` -- value and interpretation are not conflated; `PENDING_REVIEW` |
| Recession-risk-easing and valuation-not-expensive claims (`news:65/82/102`, `fundamental:28`, `bull:73/101/118`) | see `a304_a501_reverse_evidence_fix.md` | Real reverse evidence vs. A501/A304's own risk thesis; was previously misclassified as supporting the risk alpha | **Fixed this round** at the diagnostic-v2 layer (`relation` corrected to `risk_relief`, excluded from qualifying evidence, verified via real recomputation: A304 19.6667->0.0, A501 51.0271->34.6677). The **official** `v2_verified` result was, and remains, 0 regardless (zero human review) -- the fix corrects the diagnostic layer's own internal consistency, not the official product output, which was never showing these claims as "official support" to begin with. |
| 55 of 79 reviewed claims (and the broader ~1001/1040 with no source match at all) | various | No locatable external source in this run's own frozen materials | `content_support_judgment=CANNOT_JUDGE_EXTERNAL_SUPPORT` -- recorded as an explicit, allowed "cannot judge," never defaulted to either "true" or "false"; product shows `source_link_status=NOT_PROVIDED`, `content_support_status=NOT_APPLICABLE` |

## Summary, not proven by score-emptiness alone

The official `v2_verified` result being 0 for every Alpha is a real, correct consequence of zero human review (see `nvda_run_source_coverage_and_current_evidence_explanation.md`) -- it is **not**, by itself, evidence that T1's source-linking and content-support machinery works correctly. That claim is instead supported by the item-by-item table above: 6 real positive matches verified correctly as `SNAPSHOT_FACT_SUPPORTED`, 13 real partial-support boundaries correctly held at `PARTIAL_SUPPORT*` rather than being rounded up to full support, 5 value/interpretation splits correctly kept separate, 7 real reverse-evidence claims found and fixed this round (verified by real recomputation, not asserted), and 55(+~946 more, same category) correctly left at `CANNOT_JUDGE`/`NOT_PROVIDED` rather than defaulted to a guess in either direction. No claim anywhere in this table was promoted to `HUMAN_REVIEWED`, `Gold`, or John's approval by this review.
