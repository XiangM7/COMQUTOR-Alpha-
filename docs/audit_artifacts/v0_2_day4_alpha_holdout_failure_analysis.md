# v0.2 Day 4 — Independent Alpha Holdout (#4) Failure Analysis

Source: `item2_blind_holdout4` (independent of Day 2/3's H5 sample; 200 samples, denominator and exclusions unchanged: 148/200 = 74.00%). Full per-error detail (input text, candidate scores, reviewer reasoning) is in the companion `v0_2_day4_alpha_holdout_failure_analysis.json`.

## Category Breakdown (52 errors)

| Category | Count | Description |
|---|---:|---|
| `SYSTEM_FALSE_NEGATIVE_LLM_NONE` | 26 | LLM said `decision=none`; reviewer expected a specific Alpha |
| `SYSTEM_FALSE_POSITIVE_OVERMATCH` | 10 | LLM attributed an Alpha to content the reviewer judged generic/non-substantive |
| `OTHER_WRONG_ALPHA_SUBSTITUTION` | 10 | LLM chose a different Alpha than expected, not fitting the two patterns below |
| `CROSS_FAMILY_GROWTH_VS_RISK_CONFUSION` | 4 | LLM crossed the growth/cycle-vs-risk family boundary (e.g. A301↔A304) |
| `A101_A102_A103_BOUNDARY_CONFUSION` | 2 | LLM selected A101 where A103 (or vice versa) was expected |
| **Total** | **52** | |

## Central Finding: 100% LLM-Method-Driven, 0% Deterministic-Addressable

Every one of the 52 error records carries `alpha_match_method: "llm"` — none involved the deterministic keyword/factor scoring path at all. This corpus's production architecture is **Pure-LLM Alpha semantic authority**: deterministic scoring is retained only as a diagnostic/counterfactual signal and is never consulted as a semantic fallback or used to override the LLM's answer (confirmed directly from `item2_blind_holdout4_report.md`'s own architecture disclosure). Checking `deterministic_top_alpha` against the reviewer's expected label for all 52 errors: **0 of 52** show the deterministic path arriving at the correct answer where the LLM did not.

**Conclusion: no local/deterministic code path is responsible for any of these 52 errors, so none can be addressed by a deterministic/local code change.** This is not a failure to look hard enough — every error was individually inspected and categorized (see JSON) — it is a structural property of this architecture: the LLM is the sole decision-maker, and its specific semantic judgment calls (a low PEG ratio read as valuation risk vs. revenue growth; hyperscaler capex commentary read as general AI expansion vs. infrastructure buildout; a bare EPS/balance-sheet figure read as materially engaging a thesis or not) cannot be reproduced, tested, or corrected without invoking the Provider — which this task does not authorize today.

**One category is worth flagging for future work, not fixed today:** the 2 `A101_A102_A103_BOUNDARY_CONFUSION` errors fall in exactly the boundary family Day 3 found the `alpha_classifier` v3 prompt (commit `c454245`, 2026-08-21) already targets with its own worked A101/A103 example. These specific H4 samples predate that prompt version (H4's own recorded HEAD still carries `alpha_classifier` v1) — the same "fix provenance identified, not independently re-verified" situation Day 3 documented for the H5 samples. No new evidence changes that conclusion here.

## Production Fix

**Not applied.** Zero of the 52 errors are addressable by deterministic/local code (see above); implementing a change here would necessarily mean either a ticker-specific/sample-ID special case (explicitly forbidden) or a Provider-facing prompt change that cannot be locally tested without a Provider call (out of today's scope, and — per the c454245 finding — arguably already attempted once, pending confirmation).

## Re-Run Result

Since no code change was made, **no re-run was performed** — there is nothing for a re-run to measure that differs from the existing, already-computed result. The independent Alpha score remains **148/200 = 74.00%**, unchanged, honestly reported below target.
