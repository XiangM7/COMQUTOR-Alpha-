# v0.2 Evidence Failure Analysis

**Row-level root-cause analysis of all 34 Alpha Match failures and 9 Polarity failures behind the John-approved Evidence Review metrics.**

## Executive Summary

**Alpha Match:** 166/200 correct, 34/200 incorrect — **83.00%**
**Polarity:** 52/61 correct, 9/61 incorrect — **85.25%**
**Critical support/opposition reversal (accepted gate):** **0**

All three counts were reproduced exactly, row-by-row, from the frozen row-level authority (`item2_blind_holdout5_{frozen,review_frozen,comparison}.csv`, cross-verified against `evidence_review_summary_v2.json`'s `row_level_audit.detailed_rows` and `item2_blind_holdout5_metrics.json`'s independently pre-computed diagnostic buckets and confusion matrices) — not re-derived from summary percentages.

**Top 4 actual root-cause patterns found in the 43 failure rows:**

1. **TAXONOMY_OVERLAP between a growth/cyclical Alpha and a risk-family Alpha** (A201↔A304 ×3, A103↔A304 ×1, A501↔A301 ×1, plus A201↔A301 ×3, A101↔A103 ×2, A101↔A102 ×2) — 12 Alpha Match failures, the largest single category, and the highest-severity one where it crosses into the risk family.
2. **GENERIC_BACKGROUND_EVIDENCE false-positive attribution** on non-substantive technical/trivia/balance-sheet statements the reviewer found immaterial — 11 Alpha Match failures, the second-largest category, all LOW severity.
3. **MENTION_VS_OPPOSITION_OVERCALL**: the shadow `evidence_stance.py` classifier calls `opposes_alpha` on hedged/cautious/uncertain-direction language that reviewers read as a neutral mention — 5 of 9 Polarity failures. This is an independent polarity-calibration issue in `evidence_stance.py`, unrelated to Alpha-mapping.
4. **MENTION_VS_SUPPORT under-calling**: the same classifier under-reads declarative supportive claims as mere mentions — 4 of 9 Polarity failures.

No finding here is exaggerated: 15/34 (44%) Alpha Match failures and 4/9 (44%) Polarity failures occur on **HIGH-reviewer-confidence** rows, indicating a genuine, systematic semantic-mapping/stance-calibration signal rather than pure annotation-boundary noise — but the majority of Alpha Match failures (18/34) remain LOW severity, low-impact diagnostic noise on content the reviewer judged immaterial.

---

## Authority and Reconciliation

**Row-level authority located** (not a later summary substituted for it):

| Metric | Authority path | Row count |
|---|---|---|
| Alpha Match | `item2_blind_holdout5_comparison.csv` (system output) joined with `item2_blind_holdout5_frozen.csv` (claim/evidence text) and `item2_blind_holdout5_review_frozen.csv` (reviewer labels) | 200 |
| Polarity | Same three CSVs, restricted to the 61-row `polarity_eligible=true` subset | 61 |

Both are reconciled through `evidence_review_summary_v2.json`'s `row_level_audit.detailed_rows` (200 entries, added by a prior independent audit task, itself derived directly from the same frozen CSVs).

| File | SHA256 |
|---|---|
| `item2_blind_holdout5_frozen.csv` | `a2f8e0bd6fa1229f3e5876673be751e54155c750e524899cde9dd523142e17b7` |
| `item2_blind_holdout5_review_frozen.csv` | `900ee50b9cfb8f5b3653ebcd30e41403d2af6665fc72cc7f4af49493d9d92ed1` |
| `item2_blind_holdout5_comparison.csv` | `ebbcc96a4af6c6fedf282aaa67bc5bc117127d8673b3353009c35e511adedd6e` |
| `item2_blind_holdout5_metrics.json` | `baba9395efc9886dad6bea9adeee8cc806a0f8c568c7e90fe5c32cb1df254112` |
| `evidence_review_summary_v2.json` | `2f01795c41aa17c61a52bd03abd2224e51390e83a7b5ee0c2f981640212b8519` |

**Hard reconciliation:**

- 166 + 34 = **200** ✓
- 52 + 9 = **61** ✓
- Alpha incorrect rows discovered: **exactly 34** ✓
- Polarity incorrect rows discovered: **exactly 9** ✓
- Critical reversals discovered (accepted gate): **exactly 0** ✓ — raw pre-exclusion count is **1** (`holdout5-005`), formally adjudicated `BOTH_REASONABLE_AMBIGUOUS` → `AMBIGUOUS_DIRECTION` by the existing, general (non-ticker-specific) `directional_eligibility_contract` already present in `evidence_review_summary_v2.json` — this is the frozen source authority's own pre-existing exclusion, reproduced here unmodified, not a new decision made in this task.

**Independent cross-check**: `item2_blind_holdout5_metrics.json`'s own pre-computed `diagnostic_error_buckets` (`system_alpha_a_reviewed_alpha_b=16`, `system_alpha_reviewed_none=16`, `system_none_reviewed_alpha=2`, sum=34) and `polarity.confusion_matrix` exactly match this task's independently-built row-level tally. **All counts reproduced exactly — no `EVIDENCE_FAILURE_AUTHORITY_RECONCILIATION_FAILURE`.**

---

## Alpha Match — 34 Failures

Every one of the 34 failure rows breaks into exactly one of three empirically pre-computed buckets (matching `item2_blind_holdout5_metrics.json`'s own `diagnostic_error_buckets`):

| Bucket | Count | Meaning |
|---|---:|---|
| `SYSTEM_ALPHA_REVIEWED_NONE` | 16 | System attributed a materially-fit Alpha to content the reviewer judged immaterial (false positive) |
| `SYSTEM_ALPHA_A_REVIEWED_ALPHA_B` | 16 | Both system and reviewer found material content, but disagreed on which Alpha |
| `SYSTEM_NONE_REVIEWED_ALPHA` | 2 | System found no material fit where the reviewer expected one (false negative) |

## Alpha Match Failure Categories

| Category | Count |
|---|---:|
| `TAXONOMY_OVERLAP` | 12 |
| `GENERIC_BACKGROUND_EVIDENCE` | 11 |
| `AI_THEME_OVERGENERALIZATION` | 3 |
| `TARGET_ALPHA_AMBIGUITY` | 2 |
| `NEGATION_OR_MODALITY_ERROR` | 2 |
| `REVIEWER_AMBIGUITY` | 1 |
| `NARRATIVE_VS_FUNDAMENTAL_CONFUSION` | 1 |
| `MACRO_VS_COMPANY_CONFUSION` | 1 |
| `MULTI_ALPHA_CLAIM` | 1 |
| **Total** | **34** |

## Largest Alpha Confusion Pairs

`system_alpha → reviewer_expected_alpha`:

| Pair | Count |
|---|---:|
| `A601 → NONE` | 6 |
| `A201 → A304` | 3 |
| `A301 → NONE` | 3 |
| `A201 → NONE` | 3 |
| `A201 → A301` | 3 |
| `A101 → A103` | 2 |
| `A101 → NONE` | 2 |
| `A102 → A101` | 2 |
| (11 further pairs, each count 1) | 10 |
| **Total** | **34** |

The largest *substantive* (non-`NONE`) confusion clusters are:

- **`A201 ↔ A304`/`A301` (6 rows total)** — semiconductor/industry-cycle language (write-downs, pricing deterioration, cycle-peak margins, inventory-to-revenue conversion) is repeatedly read literally as the *industry cycle itself* (A201) by the system, where the reviewer reads the same language as its *downstream consequence* — either valuation-risk (A304: 3 rows — `004`,`151`,`174`) or revenue/margin expansion (A301: 3 rows — `086`,`102`,`167`). This is the single largest, most consequential confusion pattern in the dataset.
- **`A101 ↔ A103` / `A101 ↔ A102` (4 rows: `001`,`003`,`057`,`164`)** — the AI-theme family's internal boundaries (training/theme demand vs. infrastructure buildout vs. inference-specific demand) are a recurring, genuine source of confusion — notably the *same* A101/A102 boundary Gold v0.2 itself found ambiguous enough to require a rule split (`MSFT-A102-DIRECT`/`INDIRECT`).

## Failure Breakdown by Ticker

| Ticker | Failures |
|---|---:|
| SNDK | 9 |
| AMD | 7 |
| MSFT | 5 |
| GOOGL | 3 |
| MU | 3 |
| NVDA | 3 |
| QQQ | 2 |
| TSM | 2 |
| **Total** | **34** |

No zero-count ticker exists in this 8-ticker holdout set (all eight — AMD, GOOGL, MSFT, MU, NVDA, QQQ, SNDK, TSM — appear at least twice).

## Failure Breakdown by Agent

| Agent | Alpha Match failures | % of 34 |
|---|---:|---:|
| bear_researcher | 9 | 26.5% |
| conservative_risk_analyst | 4 | 11.8% |
| bull_researcher | 4 | 11.8% |
| fundamental_agent | 3 | 8.8% |
| neutral_risk_analyst | 3 | 8.8% |
| news_agent | 3 | 8.8% |
| aggressive_risk_analyst | 2 | 5.9% |
| sentiment_agent | 1 | 2.9% |
| portfolio_manager | 1 | 2.9% |
| **Total** | **34** | **100%** |

No per-agent row-count denominator is available in the frozen row-level authority (the 200-row sample is not stratified by agent in a documented way), so a per-agent *failure rate* is not reported — only the raw count/percentage, per the instruction not to manufacture a denominator that doesn't exist.

## Alpha Match — Severity and Confidence

| Severity | Count | Criterion |
|---|---:|---|
| HIGH | 7 | Cross-family confusion (growth/cyclical Alpha ↔ risk-family Alpha: A304/A501) or a genuinely multi-mechanism sentence where the wrong side was picked — could plausibly feed the wrong side of a growth-vs-valuation or macro conflict evaluation |
| MEDIUM | 9 | Confusion within the same broad family (AI-theme siblings A101/A102/A103; industry-vs-company siblings A201/A301) |
| LOW | 18 | False-positive attribution on non-substantive/generic/technical content, or a false-negative already flagged low-confidence/ambiguous by the reviewer |

**High-confidence-wrong count: 15/34 (44%)** — a meaningful share of failures are not simply low-confidence borderline calls; they represent systematic semantic patterns (taxonomy-boundary confusion in particular).

---

## Row-Level Table — Alpha Failures (34 rows)

| # | Sample | Ticker | Agent | System Alpha | Reviewer Alpha | Category | Root Cause | Severity | Actionable |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 001 | AMD | aggressive_risk_analyst | A101 | A103 | TAXONOMY_OVERLAP | TAXONOMY_BOUNDARY | MEDIUM | True |
| 2 | 003 | AMD | bear_researcher | A101 | A103 | TAXONOMY_OVERLAP | TAXONOMY_BOUNDARY | MEDIUM | True |
| 3 | 004 | AMD | conservative_risk_analyst | A201 | A304 | TAXONOMY_OVERLAP | SEMANTIC_CLASSIFICATION | HIGH | True |
| 4 | 005 | AMD | conservative_risk_analyst | NONE | A601 | REVIEWER_AMBIGUITY | INPUT_AMBIGUITY | LOW | False |
| 5 | 008 | AMD | news_agent | A101 | NONE | AI_THEME_OVERGENERALIZATION | SEMANTIC_CLASSIFICATION | LOW | True |
| 6 | 016 | AMD | bull_researcher | A601 | A301 | NARRATIVE_VS_FUNDAMENTAL_CONFUSION | SEMANTIC_CLASSIFICATION | MEDIUM | True |
| 7 | 017 | AMD | bull_researcher | NONE | A304 | TARGET_ALPHA_AMBIGUITY | INPUT_AMBIGUITY | LOW | uncertain |
| 8 | 033 | GOOGL | conservative_risk_analyst | A601 | NONE | NEGATION_OR_MODALITY_ERROR | SEMANTIC_CLASSIFICATION | LOW | True |
| 9 | 035 | GOOGL | fundamental_agent | A301 | NONE | GENERIC_BACKGROUND_EVIDENCE | SEMANTIC_CLASSIFICATION | LOW | True |
| 10 | 043 | GOOGL | bull_researcher | A601 | NONE | AI_THEME_OVERGENERALIZATION | SEMANTIC_CLASSIFICATION | LOW | True |
| 11 | 056 | MSFT | aggressive_risk_analyst | A301 | A501 | MACRO_VS_COMPANY_CONFUSION | SEMANTIC_CLASSIFICATION | HIGH | True |
| 12 | 057 | MSFT | bear_researcher | A102 | A101 | TAXONOMY_OVERLAP | TAXONOMY_BOUNDARY | MEDIUM | True |
| 13 | 059 | MSFT | bull_researcher | A301 | NONE | GENERIC_BACKGROUND_EVIDENCE | SEMANTIC_CLASSIFICATION | LOW | True |
| 14 | 063 | MSFT | neutral_risk_analyst | A304 | NONE | GENERIC_BACKGROUND_EVIDENCE | SEMANTIC_CLASSIFICATION | LOW | True |
| 15 | 071 | MSFT | bear_researcher | A304 | A103 | TAXONOMY_OVERLAP | TAXONOMY_BOUNDARY | HIGH | True |
| 16 | 081 | MU | bear_researcher | A201 | NONE | GENERIC_BACKGROUND_EVIDENCE | SEMANTIC_CLASSIFICATION | LOW | True |
| 17 | 083 | MU | bull_researcher | A301 | NONE | GENERIC_BACKGROUND_EVIDENCE | SEMANTIC_CLASSIFICATION | LOW | True |
| 18 | 086 | MU | fundamental_agent | A201 | A301 | TAXONOMY_OVERLAP | TAXONOMY_BOUNDARY | MEDIUM | True |
| 19 | 102 | NVDA | bear_researcher | A201 | A301 | TAXONOMY_OVERLAP | TAXONOMY_BOUNDARY | MEDIUM | True |
| 20 | 103 | NVDA | bear_researcher | A101 | NONE | AI_THEME_OVERGENERALIZATION | SEMANTIC_CLASSIFICATION | LOW | True |
| 21 | 104 | NVDA | bull_researcher | A201 | NONE | GENERIC_BACKGROUND_EVIDENCE | SEMANTIC_CLASSIFICATION | LOW | True |
| 22 | 143 | QQQ | news_agent | A601 | NONE | GENERIC_BACKGROUND_EVIDENCE | SEMANTIC_CLASSIFICATION | LOW | True |
| 23 | 146 | QQQ | news_agent | A304 | A101 | MULTI_ALPHA_CLAIM | INPUT_AMBIGUITY | HIGH | True |
| 24 | 151 | SNDK | bear_researcher | A201 | A304 | TAXONOMY_OVERLAP | SEMANTIC_CLASSIFICATION | HIGH | True |
| 25 | 154 | SNDK | fundamental_agent | A301 | A304 | TARGET_ALPHA_AMBIGUITY | INPUT_AMBIGUITY | HIGH | uncertain |
| 26 | 158 | SNDK | neutral_risk_analyst | A601 | A304 | TAXONOMY_OVERLAP | SEMANTIC_CLASSIFICATION | MEDIUM | True |
| 27 | 162 | SNDK | sentiment_agent | A601 | NONE | GENERIC_BACKGROUND_EVIDENCE | SEMANTIC_CLASSIFICATION | LOW | True |
| 28 | 163 | SNDK | aggressive_risk_analyst | A601 | NONE | GENERIC_BACKGROUND_EVIDENCE | SEMANTIC_CLASSIFICATION | LOW | True |
| 29 | 164 | SNDK | bear_researcher | A102 | A101 | TAXONOMY_OVERLAP | TAXONOMY_BOUNDARY | MEDIUM | True |
| 30 | 167 | SNDK | fundamental_agent | A201 | A301 | TAXONOMY_OVERLAP | TAXONOMY_BOUNDARY | MEDIUM | True |
| 31 | 171 | SNDK | neutral_risk_analyst | A601 | NONE | GENERIC_BACKGROUND_EVIDENCE | SEMANTIC_CLASSIFICATION | LOW | True |
| 32 | 174 | SNDK | portfolio_manager | A201 | A304 | TAXONOMY_OVERLAP | SEMANTIC_CLASSIFICATION | HIGH | True |
| 33 | 177 | TSM | bear_researcher | A201 | NONE | GENERIC_BACKGROUND_EVIDENCE | SEMANTIC_CLASSIFICATION | LOW | True |
| 34 | 185 | TSM | conservative_risk_analyst | A304 | NONE | NEGATION_OR_MODALITY_ERROR | SEMANTIC_CLASSIFICATION | LOW | True |

(Full claim text, evidence, reviewer notes, and per-row `recommended_future_action` are in the JSON companion file.)

---

## Polarity — 9 Failures

All 9 sit at the `mentions_alpha` boundary, approached from two directions:

| Direction | Count | Pattern |
|---|---:|---|
| System under-calls: `mentions_alpha` (system) vs. `supports_alpha` (reviewer) | 4 | Declarative supportive claims embedded in longer/complex sentences read as mere mentions |
| System over-calls: `opposes_alpha` (system) vs. `mentions_alpha` (reviewer) | 5 | Hedged, cautious, or uncertain-direction language read as an active opposing stance |

## Polarity Confusion Analysis

`system_polarity → reviewer_polarity` (9 accepted failures; the 10th raw off-diagonal cell, `opposes_alpha → supports_alpha` ×1, is `holdout5-005`, excluded as the formally-adjudicated ambiguous/critical-reversal row, reported separately below):

| Transition | Count |
|---|---:|
| `opposes_alpha → mentions_alpha` | 5 |
| `mentions_alpha → supports_alpha` | 4 |
| **Total** | **9** |

## Failure Breakdown by Ticker (Polarity)

| Ticker | Failures |
|---|---:|
| AMD | 3 |
| MSFT | 2 |
| TSM | 2 |
| GOOGL | 1 |
| SNDK | 1 |
| NVDA | 0 |
| QQQ | 0 |
| MU | 0 |
| **Total** | **9** |

## Failure Breakdown by Agent (Polarity)

| Agent | Failures | % of 9 |
|---|---:|---:|
| bull_researcher | 2 | 22.2% |
| aggressive_risk_analyst | 2 | 22.2% |
| bear_researcher | 2 | 22.2% |
| sentiment_agent | 2 | 22.2% |
| fundamental_agent | 1 | 11.1% |
| **Total** | **9** | **100%** |

## Polarity — Severity

| Severity | Count | Criterion |
|---|---:|---|
| HIGH | 5 | `MENTION_VS_OPPOSITION_OVERCALL` — an independent polarity-calibration issue in the shadow `evidence_stance.py` classifier; not the same stage or root-cause mechanism as the QQQ-A001 Alpha Mapper `MAPPING` defect |
| MEDIUM | 4 | `MENTION_VS_SUPPORT` under-call, no cross-family risk implication |

**High-confidence-wrong count: 4/9 (44%).**

---

## Row-Level Table — Polarity Failures (9 rows)

| # | Sample | Ticker | Agent | System Polarity | Reviewer Polarity | Category | Critical Reversal | Severity |
|---|---|---|---|---|---|---|---|---|
| 1 | 003 | AMD | bear_researcher | mentions_alpha | supports_alpha | MENTION_VS_SUPPORT | False | MEDIUM |
| 2 | 016 | AMD | bull_researcher | mentions_alpha | supports_alpha | MENTION_VS_SUPPORT | False | MEDIUM |
| 3 | 017 | AMD | bull_researcher | opposes_alpha | mentions_alpha | MENTION_VS_OPPOSITION_OVERCALL | False | HIGH |
| 4 | 040 | GOOGL | aggressive_risk_analyst | opposes_alpha | mentions_alpha | MENTION_VS_OPPOSITION_OVERCALL | False | HIGH |
| 5 | 057 | MSFT | bear_researcher | mentions_alpha | supports_alpha | MENTION_VS_SUPPORT | False | MEDIUM |
| 6 | 070 | MSFT | aggressive_risk_analyst | mentions_alpha | supports_alpha | MENTION_VS_SUPPORT | False | MEDIUM |
| 7 | 154 | SNDK | fundamental_agent | opposes_alpha | mentions_alpha | MENTION_VS_OPPOSITION_OVERCALL | False | HIGH |
| 8 | 196 | TSM | sentiment_agent | opposes_alpha | mentions_alpha | MENTION_VS_OPPOSITION_OVERCALL | False | HIGH |
| 9 | 198 | TSM | sentiment_agent | opposes_alpha | mentions_alpha | MENTION_VS_OPPOSITION_OVERCALL | False | HIGH |

---

## Critical Reversal Verification

**Accepted-gate critical reversal count: 0.** Verified directly from row-level records: all 9 accepted Polarity failures carry `critical_reversal: false`.

**Raw (pre-exclusion) critical reversal count: 1** — `holdout5-005` (AMD): system=`opposes_alpha`, reviewer=`supports_alpha`, a genuine direct support/opposition flip on the same target Alpha (A601). This row is formally adjudicated `BOTH_REASONABLE_AMBIGUOUS` in `item2_blind_holdout5_internal_report.md` (Section 11) and mapped to `AMBIGUOUS_DIRECTION` by the existing, general `directional_eligibility_contract` — excluding it from the polarity/critical-reversal acceptance gate. This is the frozen source authority's own pre-existing rule, reproduced here unmodified; the 9 failures analyzed above do **not** include this row's transition, per the definition already established by the original review authority.

No other row was reclassified toward or away from "critical reversal" in this task. Per Section 13's guidance, mention-vs-support and mention-vs-opposition confusions (all 9 accepted failures) are **not** counted as critical reversals, matching the original review authority's own definition.

---

## Recommended Future Remediation

No implementation performed. Priorities derived from the actual 43 failures (not pre-assigned):

| Priority | Pattern | Rows | Rationale |
|---|---|---:|---|
| **P1** | `TAXONOMY_OVERLAP` cross-family confusion (A201↔A304, A201↔A301, A103↔A304) + `MACRO_VS_COMPANY_CONFUSION` (A501↔A301) | 9 | Highest-severity Alpha Match pattern — a cyclical/company-growth signal and a valuation/macro-risk signal interchanged, which could feed the wrong side of a growth-vs-valuation or macro conflict evaluation. |
| **P1** | `MENTION_VS_OPPOSITION_OVERCALL` — `evidence_stance.py` calling `opposes_alpha` on hedged/cautious language reviewers read as neutral | 5 | An independent polarity-calibration issue in `evidence_stance.py`, unrelated to Alpha-mapping. |
| **P2** | A101↔A103 and A101↔A102 taxonomy-boundary confusion | 4 | Same-family AI-theme confusion; recurring enough, and overlapping the exact boundary Gold v0.2 itself found ambiguous enough to warrant a rule split. |
| **P2** | `MENTION_VS_SUPPORT` under-calling | 4 | Stance classifier appears conservative on declarative supportive claims embedded in longer sentences. |
| **P3** | `GENERIC_BACKGROUND_EVIDENCE` / `AI_THEME_OVERGENERALIZATION` false-positive attribution | 15 | Largest-volume but lowest-severity pattern — diagnostic-only impact expected (low-scoring, loosely-matched claims). |
| **P3** | `NEGATION_OR_MODALITY_ERROR` | 2 | Small, clean pattern — epistemological/hedging framing mistaken for a substantive claim. |

No Gold version change is required for any of the above (`requires_new_gold_version: NO` throughout); a new fresh acceptance run set would be required after any future code fix, per standard practice.

---

## Cross-Framework Disclosure

Gold v0.2 acceptance evaluates **ticker-level, evidence-conditional product behavior** against six specific authoritative fresh runs. This Evidence Review evaluates **row-level semantic Alpha-mapping and polarity correctness** against a separate, older 200-row blind holdout sample spanning 8 tickers (including GOOGL and MU, outside Gold v0.2's 6-ticker scope) with entirely different `run_id`s.

**These are not combined.** 83% Alpha Match accuracy does not equal, prove, or disprove Gold v0.2 acceptance.

---

## Final Closure

Requirement 5 asked for complete root-cause analysis of the 34 Alpha Match failures and 9 Polarity failures. That analysis is complete; the remediation priorities documented above are follow-up engineering recommendations, not unresolved acceptance requirements.

```
JOHN_REQUIREMENT_5_EVIDENCE_FAILURE_ANALYSIS = CLOSED
ALPHA_MATCH_FAILURES_ANALYZED = 34/34
POLARITY_FAILURES_ANALYZED = 9/9
CRITICAL_ACCEPTED_SUPPORT_OPPOSITION_REVERSALS = 0
IMPLEMENTATION_REMEDIATION_REQUIRED_BY_THIS_REQUIREMENT = NO
```
