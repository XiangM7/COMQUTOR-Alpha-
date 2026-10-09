# Day 4C — Candidate 1's 25 New Regressions: Root-Cause Analysis

Source: `item2_blind_holdout4` (now `DEVELOPMENT_AFTER_FIRST_INSPECTION` data — used here purely for root-cause analysis, not validation). Full per-sample detail in `v0_2_day4c_candidate1_regression_analysis.json`.

## Categories

| Category | Count | Root Cause |
|---|---:|---|
| `NUMERIC_FUNDAMENTAL_OR_VALUATION_METRIC_SUPPRESSED_TO_NONE` | 21 | Candidate 1's unconditional "bare figure never sufficient" clause suppressed previously-correct classifications built on a domain-standard metric (capex/PP&E, revenue/FCF/EPS/margin growth, valuation multiples) with no exception for figures that ARE themselves conventional Alpha evidence. |
| `CAPEX_LANGUAGE_MISASSIGNED_TO_A101_VIA_TRIGGER_SIGNAL_OVERLAP` | 3 | The newly-added `trigger_signals` data gave A101 the literal phrase "cloud providers raise AI capex", creating new surface overlap with A103-targeted hyperscaler-capex claims. |
| `NEW_FALSE_POSITIVE_FROM_NEGATION_MISHANDLING` | 1 | A figure inside a negated/rebuttal clause ("the balance sheet does NOT prevent...") was read as affirmative mechanism evidence. |

## Generalized Lessons (feeding Candidate 2)

1. **The "bare figure" guardrail must be conditional, not absolute.** Apply it only to figures with no standard, recognized Alpha-relevant interpretation (a raw stock price, a date, an administrative number) — never to figures that are themselves conventional evidence for a specific Alpha's mechanism.
2. **Trigger-signal overlap between neighboring Alphas needs explicit resolution guidance** — by mechanism, not by shared surface vocabulary.
3. **New positive-evidence guidance must not override existing negation-handling** — a figure inside a negated clause should not automatically satisfy a "connects to a mechanism" bar.

No sample-specific exceptions were added; all three lessons are stated as general, taxonomy-wide rules in Candidate 2 (see `v0_2_alpha_prompt_candidate2.md`).
