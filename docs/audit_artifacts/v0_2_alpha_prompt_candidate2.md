# v0.2 Day 4C — Alpha Prompt Candidate 2

Full detail in `v0_2_alpha_prompt_candidate2.json`. Gold taxonomy unchanged. No new Alpha IDs. No ticker-specific or sample-ID content.

## Hashes

| Prompt | Baseline (v3) | Candidate 1 (v4, **REJECTED**) | Candidate 2 (v5) |
|---|---|---|---|
| `alpha_classifier` | `a2ca2a32...` | `36bf5a63...` | `70303c5f...` |
| `alpha_classifier_batch` | `0caa5b77...` | `291f69db...` | `a4f4b174...` |

## Candidate 1's Failure Mechanism

An **unconditional** rule — "a bare, standalone financial figure or ratio is never sufficient by itself" — gave the model no way to recognize that some KINDS of figures (capex/PP&E, revenue/FCF/EPS/margin growth, valuation multiples) are themselves the conventional evidence for a specific Alpha. 21 of 25 regressions were previously-correct classifications suppressed to `none` for exactly this reason. 3 traced to the new `trigger_signals` data creating fresh A101/A103 surface overlap. 1 was a new false positive from a figure inside a negated clause.

## Candidate 2's Changes

1. **Conditional, not absolute, "bare figure" rule** — sufficient when the figure is itself standard, domain-conventional evidence for an Alpha's mechanism (capex→infrastructure, revenue/FCF/EPS/margin growth→fundamental growth, valuation multiple→valuation risk/relief); insufficient only for figures with no standard Alpha-relevant interpretation (bare stock price, date, administrative number).
2. **Trigger-signal-overlap disambiguation** — when two Alphas' signals share surface wording, resolve by mechanism, not by which signal list contains the matching word.
3. **Negation-scoping** — a figure inside a negated/rebutted clause doesn't satisfy the positive-connection bar for the side it negates.
4. **Retained unchanged**: the `trigger_signals`/`confirmation_signals` taxonomy-data enrichment and paraphrase-tolerance guidance (not the source of Candidate 1's regressions).

All four changes are general (defined by figure-kind, mechanism, and sentence-polarity — never by ticker, ID, or holdout wording).

## Local Non-Provider Tests

**384 passed, 1 skipped, 0 failed.** Engineering checks only (construction/schema/parser/taxonomy-injection) — not semantic validation.

## Development Diagnostic (Holdout #4 — `DEVELOPMENT_METRIC_ONLY`)

One authorized development run (Holdout #4 is `DEVELOPMENT_AFTER_FIRST_INSPECTION`, never independent):

| | Correct/200 | Accuracy |
|---|---:|---:|
| Pre-remediation baseline | 148 | 74.00% |
| Candidate 1 (rejected) | 139 | 69.50% |
| **Candidate 2 (development)** | **145** | **72.50%** |

Fixes 16 of Candidate 1's own 25 regressions; introduces 18 of its own (mostly new false positives on generic content) relative to the pre-remediation baseline. **Improvement over Candidate 1, but does not recover the original baseline on this development set.** Per explicit instruction, this single run is not used for further tuning in this task.

## Final Independent Validation

**Not performed** — no untouched independent Alpha holdout exists (see `v0_2_alpha_holdout_provenance.md`).
