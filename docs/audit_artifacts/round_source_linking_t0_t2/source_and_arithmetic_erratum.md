# NVDA run (034a0a60-430e-41f8-8321-03a11389707a): source and arithmetic erratum

Independent erratum, cross-referenced from the final delivery -- the original run's own files are unchanged. Supplementary frozen source snapshots (copied verbatim from this run's own `source_registry.json`, never re-fetched) are in `source_and_arithmetic_erratum_supplementary/cited_source_snapshots.json` (sha256 `dc694503023eca2758ad3a1c258186dd6847de3d8a06b819af69e36da96ae25c`).

## 1. Arithmetic errors in the research text itself

These confirm the *research agent's own text* is internally inconsistent with the dollar figures it cites in the same sentence -- they are not claims about whether the underlying financial data is true.

| Claim | Text's own figure | Recomputed from the text's own numbers | Correct figure |
|---|---|---|---|
| `fundamental_agent:fundamentals_report:claim:42` | "Revenue has compounded **4.4x** across five quarters ($46.7B -> $96.2B)" | 96,221,000,000 / 46,743,000,000 (exact figures elsewhere in the same report) | **2.0585x** (+105.85%). Consistent with the claim's own separately-stated "19.8% average sequential rate" compounded over 4 periods (1.198^4 = 2.058) -- the "4.4x" contradicts the claim's own other number, not just the raw dollar figures. |
| `fundamental_agent:fundamentals_report:claim:78`, `bull_researcher:...claim:18`, `bear_researcher:...claim:31` (same figures, repeated by 3 agents) | "Raw materials **more than doubled** sequentially ($6,647M -> $11,341M)" | 11,341 / 6,647 | **1.7062x** (+70.62%) -- not a doubling. The same arithmetic error appearing in three agents' text is one error restated, not three independent confirmations. |

## 2. News claim:77 -- figure misattributed to the wrong subject

Claim text: *"Accenture's record bookings (+23%) validate AI demand..."* -- presenting 23% as a **bookings/order-growth** figure.

The real, registered source for this story (`src_e9c1b0802ec94021`, `24/7 Wall St.`, retrieved this run, `metadata_status=TRACEABLE`) has the title: **"Accenture Soars 23% as Record Bookings Dispel AI Demand Fears"** -- the 23% is Accenture's **stock-price move**, with record bookings cited as the *catalyst*, not as a 23%-growth figure itself. This source has no captured excerpt/body text (see the broader 40-source gap already documented in `nvda_run_source_coverage_and_current_evidence_explanation.md`), so the real bookings growth rate, if reported in the article body, is not available in this run's own frozen materials. **The claim must not be displayed as "order growth +23%"; no figure for actual bookings growth exists in this run's frozen materials at all.**

## 3. The 24 `source_link_status=VALID` claims are not 24 "verified support" claims

Each of the 24 has a real, registered source and a real embedded `[fragmentid: ...]` marker that resolves correctly -- that is what `VALID` means, and it is true for all 24. It does **not** mean the full sentence is content-supported; per-claim boundaries (verified directly against each claim's own linked source snapshot, not merely restated from the review):

| boundary | count | representative, independently verified example |
|---|---:|---|
| Snapshot's stated value directly verifiable | 6 | `market_agent:claim:56/57/58` (Bollinger bands), `claim:67` (volume) -- the cited number matches the linked snapshot's own field exactly |
| Value matches, but the claim adds the analyst's own technical/strategic interpretation (e.g. labeling a moving average as "support"/"resistance") | 5 | `market_agent:claim:80/81/82/83/84` -- the numeric level matches the snapshot; "resistance"/"support"/"trend invalidation" is the analyst's own framing, not a sourced fact |
| Only part of the sentence is supported -- current value is real, but a trend/prior-period/historical-event component is not in the cited snapshot | 9 | `market_agent:claim:32`: current MACD/signal/histogram values (2.86/2.36/0.50) match the snapshot (`src_8e61838edf95c591`) exactly, but "**crossed back above**" asserts a prior-period comparison the snapshot (a single trading day, 2026-09-30) cannot support. `claim:50`'s "ATR declined from 7.57 on 2026-09-02" has the same gap (only 2026-09-30 is in the snapshot). `claim:20`/`claim:27`/`claim:80` similarly cite a historical date/trend outside the single-day snapshot. |
| Core derived value cited is **absent from the snapshot entirely** | 1 | `market_agent:claim:63`: cites "VWMA stands at 222.54" -- directly verified against `src_8e61838edf95c591`'s own field list (`ohlcv`, `indicators`: ema/sma/rsi/boll/macd/atr) -- **there is no VWMA field in this snapshot at all.** The fragmentid resolves to a real source; that source does not contain the figure the claim attributes to it. |
| Single-period financial value exists, but trend wording ("rose"/"fell") and disclosure time are both unsupported | 3 | `fundamental_agent:claim:40/69/98` -- each linked source (`src_bce051a83ee448c8`/`src_368d04e64ccecd8c`/`src_da65a19945a1ad41`) contains exactly **one** quarterly data point (verified directly: `data_snapshot` has no prior-period field), so "rose to"/"fell to" cannot be verified from the cited source alone; all three sources also have `published_at=null` -- a pending human review cannot supply a disclosure time that was never captured. |
| **Total** | **24** | None of the 24 automatically becomes `HUMAN_REVIEWED` by this AI review or by this erratum. |

The stockstats-derived technical snapshot (`src_8e61838edf95c591`) itself records its own computation window and a 1254-row input count, but this run's frozen materials do not include the full 1254-row historical OHLCV series -- so none of its derived indicators (EMA/MACD/ATR/Bollinger/RSI) can be independently recomputed from this run's own materials; only the single already-computed values can be cross-checked against the claim text, which is what this erratum does.

## 4. Searched for, not found, in this run's frozen materials (not newly fetched)

- Accenture article's full body text (bookings growth rate, if any, beyond the stock-price headline) -- not captured; see Section 2.
- The 1254-row historical OHLCV series underlying the technical snapshot -- not captured; only the single computed-indicator row is in `source_registry.json`.
- Any macro/prediction-market source record (the 97%/68%/8% figures cited in `01_AI_REVIEW_REPORT.md` Section 5) -- no corresponding source entries exist in this run's 45-source registry at all; these figures come from the research agents' own text with no registered external source to check against.

No new network request was made to look for any of the above; this section lists what is confirmed absent from already-frozen local materials, not what a new fetch might find.
