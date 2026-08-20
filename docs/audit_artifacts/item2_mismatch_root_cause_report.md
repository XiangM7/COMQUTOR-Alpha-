# QA Closure v0.1.2 — Item 2 Mismatch Root-Cause Analysis

Diagnosis only. No production code, threshold, weight, or prompt was changed to produce this report. `PROVIDER_CALLS = 0` — every judgment below comes from directly reading the same 25 evidence texts and the same frozen source artifacts already on disk; nothing was re-adjudicated by a new LLM call.

## Inputs

- Polarity comparison: `docs/audit_artifacts/b1_llm_stance_50_validation_after_parser_fix.csv` (current, final B1 authoritative stance — 50/50 real LLM, 0 fallback) vs `comqutor_alpha/config/j3_provisional_semantic_benchmark_v0.1.json` (frozen independent J3 reviewer).
- Alpha comparison: system `matched_alpha_id` (`docs/evidence_review_sample_records.json`) vs `llm_expected_alpha_id` (`docs/audit_artifacts/evidence_review_llm_provisional.csv`).
- Candidate-rank diagnostics: each mismatched row's own source `outputs/runs/<source_run_id>/alpha_matches.json`, re-sorted by raw score for this diagnostic only (labeled explicitly below — **not** the production selection order, which is eligible-first-then-score; see `alpha_mapper._sort_candidates`). `candidate_scores` is capped at 5 entries per claim in the exported artifact, so "absent" below means "does not appear in the exported top-5," not necessarily "scored zero."

## Current metrics (unchanged, restated)

B1 polarity: 39/50 = 78% (target ≥80%) · Alpha match: 36/50 = 72% (target ≥75%) · Critical support↔oppose reversals: **re-verified = 0** (recomputed independently in `build_item2_mismatch_root_cause_analysis.py`, not assumed)

---

## Part 1 — Polarity mismatches (11 rows)

Full row data: `docs/audit_artifacts/item2_polarity_mismatch_analysis.csv`. Two fields are honestly reported as unavailable rather than fabricated: **current B1 confidence/reason is not captured** by the post-parser-fix CSV (no such column exists), and **the independent reviewer's reason text is not captured** by the frozen J3 benchmark's `rows` (only `review_confidence` survived the join into that file, even though the original blind-packet schema requested a `review_reason` field).

### Severity (recomputed, not assumed)

| Severity | Count | Sample IDs |
|---|---|---|
| CRITICAL | **0** | — |
| HIGH | 3 | evrs-008, 042, 045 |
| MEDIUM | 7 | evrs-007, 013, 020, 026, 034, 036, 040 |
| LOW | 1 | evrs-006 |

### Root cause

| Root cause | Count | Status | Sample IDs |
|---|---|---|---|
| F. MIXED_OR_CONDITIONAL_LANGUAGE | 6 | **SYSTEMATIC** | evrs-007, 020, 026, 034, 036, 040 |
| E. COUNTER_ALPHA_BOUNDARY | 3 | **SYSTEMATIC** | evrs-008, 042, 045 |
| C. OPPOSE_VS_MENTION_BOUNDARY | 1 | isolated | evrs-013 |
| G. TARGET_ALPHA_AMBIGUITY | 1 | isolated | evrs-006 |

**Systematic finding 1 — F (6/11, 55%):** every one of these six rows contains an explicit contrastive or hedging connective ("but", "though...", "yet", "the dominant tension is", "constructive tension"). Current B1 systematically resolves these to the conservative `mentions_alpha` rather than judging which clause the sentence itself treats as dominant. This is the single largest pattern in the polarity mismatches, and it is also the one with the clearest downstream consequence: 4 of these 6 (evrs-020, 026, 034, 040) directly flip B2's `supporting_evidence_count` for their target Alpha, because the independent reviewer's stance is `supports_alpha` while B1's is not.

**Systematic finding 2 — E (3/11, 27%):** whenever evidence plausibly engages both a direct stance *and* a counter-Alpha-flavored contrast, B1 and the independent reviewer disagree on whether to route it through `supports_counter_alpha` or resolve it as a plain `opposes_alpha`. Not one-directional — B1 under-uses the counter-Alpha mechanism on evrs-008/045 (recession-risk and multiple-compression language, both textually close to a named counter-Alpha's own `core_thesis`) but over-uses it on evrs-042 (where B1's `supports_counter_alpha(A304)` is arguably the *more* precise reading). All three are HIGH severity by the task's own rubric, though **current B2 impact on the row's own target-Alpha supporting count is `none` for all three** (neither candidate stance in any of the three is `supports_alpha`); a possible secondary effect on the counter-Alpha's *own* supporting count was not confirmed by this diagnostic and is flagged as an open question, not asserted.

### B2 downstream impact (recomputed from `conflict_admissibility.py`'s actual logic, not assumed)

`stance_for_alpha` / `conflict_admissibility.py` counts **only** the literal string `"supports_alpha"` toward a side's `supporting_evidence_count` — every other stance value is B2-neutral for that Alpha's own count. Applying this precisely:

| Affects B2 supporting_evidence_count | Count | Sample IDs |
|---|---|---|
| YES | 4 | evrs-020, 026, 034, 040 (all root cause F) |
| NO (neither candidate stance is `supports_alpha`) | 6 | evrs-006, 007, 008, 013, 036, 042 |
| NO (row not currently `used_in_activation`/`used_in_conflict` at all) | 1 | evrs-045 |

### Plausibility (analytical adjudication, not automatic trust of either side)

| | Count |
|---|---|
| SYSTEM_MORE_PLAUSIBLE | 2 (evrs-013, 042) |
| REVIEWER_MORE_PLAUSIBLE | 4 (evrs-006, 007, 008, 045) |
| GENUINELY_AMBIGUOUS | 5 (evrs-020, 026, 034, 036, 040) |

The majority of the F-bucket rows (5 of 6) are judged genuinely ambiguous on a close reading, not a clean reviewer win — the sentences really are close to 50/50 in their own rhetorical weighting.

---

## Part 2 — Alpha mismatches (14 rows)

Full row data: `docs/audit_artifacts/item2_alpha_mismatch_analysis.csv`.

### Candidate-rank diagnostics

| Category | Count |
|---|---|
| Expected Alpha absent from exported top-5 | 5 (evrs-007, 041, 043, 045, 049) |
| Expected Alpha present, rank 2 | 4 (evrs-011, 017, 031, 042) |
| Expected Alpha present, rank 3+ | 3 (evrs-002 rank3, evrs-023/030 rank5) |
| Expected Alpha excluded by the AI_ALPHA_IDS hard eligibility gate despite highest raw score | **3 (evrs-011, 016, 044)** |

The last row is its own distinct, precisely-confirmed finding, not a generic ranking loss — see below.

### Root cause

| Root cause | Count | Status | Sample IDs |
|---|---|---|---|
| C. TAXONOMY_OVERLAP | 6 | **SYSTEMATIC** | evrs-002, 023, 030, 031, 045, 049 |
| A. TOP1_RANKING_ERROR | 5 | **SYSTEMATIC** | evrs-011, 016, 017, 042, 044 |
| B. CANDIDATE_RECALL_ERROR | 1 | isolated | evrs-043 |
| D. ALPHA_DEFINITION_AMBIGUITY | 1 | isolated | evrs-007 |
| J. OTHER | 1 | isolated | evrs-041 |

**Systematic finding 3 — the AI_ALPHA_IDS hard gate (3 of the 5 TOP1_RANKING_ERROR rows: evrs-011, 016, 044).** Confirmed directly from each row's own `candidate_scores[].rejection_reason` field (not inferred): in all three, the LLM's independently-expected Alpha (A103 in two cases, A101/A103 both in the third) carries the literal rejection reason `"AI alpha hard gate not satisfied: missing an alpha-specific anchor phrase with a locally co-occurring change predicate"` — despite having the **highest raw semantic/keyword score** of any candidate on the claim. `matched_alpha` falls through to the highest-scoring *eligible* candidate instead. This is **not a ranking bug**. Per `alpha_mapper.py`'s own comment (line ~515), this hard gate was deliberately built to close "the weak-recall gap" of an *earlier* problem — generic AI/cloud/capex keyword presence over-triggering A101/A102/A103 matches. The current disagreements are cases where that deliberate anti-false-positive gate's precision/recall tradeoff conflicts with the independent reviewer's judgment on these 3 specific claims — genuinely uncertain which side is right without a broader sample, and explicitly **not** evidence the gate itself is broken.

**Systematic finding 4 — TAXONOMY_OVERLAP (6/14, 43%).** The dominant pattern in the Alpha mismatches: evidence sentences pulled from analyst-debate summaries frequently name **multiple** alpha-relevant topics in one sentence (e.g. evrs-023/030's single sentence naming AI CapEx, semiconductor cycle, rate cuts, *and* liquidity together). The Alpha Mapper's single-Top-1-Alpha contract inherently has to pick one; which one a reader judges "primary" is often a genuinely defensible, close call. In 3 of these 6 (evrs-002, 023, 030), the system's own pick tracks the sentence's most literal/explicit clause more closely than the independent reviewer's pick, which leans toward `SYSTEM_MORE_PLAUSIBLE`; the other 3 are genuinely close.

Note: **evrs-023 and evrs-030 are byte-identical evidence text** (both QQQ, same sentence sampled twice) — this is one underlying disagreement counted twice by the sampling, not two independent data points. Any future fix-effectiveness estimate should treat this pair as n=1, not n=2.

### Plausibility (analytical adjudication)

| | Count |
|---|---|
| SYSTEM_MORE_PLAUSIBLE | 3 (evrs-002, 023, 030) |
| REVIEWER_MORE_PLAUSIBLE | 2 (evrs-042, 043) |
| GENUINELY_AMBIGUOUS | 9 |

Nearly two-thirds of the Alpha mismatches are genuinely ambiguous on direct reading — a materially higher ambiguity rate than the polarity side.

---

## Top systematic issues (ranked by evidence strength)

1. **Mixed/contrastive-language stance resolution (polarity, F, 6/11, the only pattern with direct B2 count impact on 4 rows).**
2. **Multi-topic ("kitchen sink") sentences overwhelming single-Top-1 Alpha selection (alpha, C, 6/14, the largest alpha-side pattern).**
3. **AI_ALPHA_IDS hard-gate precision/recall tradeoff (alpha, 3/14, exact mechanism confirmed via `rejection_reason`) — flagged as "review," not "fix," given it is a deliberate, already-shipped anti-overfit safeguard.**
4. Counter-Alpha routing inconsistency (polarity, E, 3/11, all HIGH severity, but currently zero confirmed B2 impact on the row's own target-Alpha count).

---

## Recommended fixes (conceptual only — **DO NOT IMPLEMENT**)

| Rank | Component | Exact problem | Affected sample_ids | Proposed conceptual fix | Expected benefit | Regression risk | Overfitting risk |
|---|---|---|---|---|---|---|---|
| P1 | B1 LLM prompt (`week2_llm.py` `_TASK_INSTRUCTIONS["evidence_stance_classifier"]`) | Systematically defaults to `mentions_alpha` on sentences with explicit contrastive connectives, even when the sentence has a clear net-dominant clause | evrs-007, 020, 026, 034, 036, 040 | Add general guidance on identifying a sentence's own dominant/concluding clause in "but/though/yet"-structured evidence, rather than defaulting to the most conservative label whenever two clauses are present | Could recover up to 4–6 of 11 polarity mismatches; the only pattern found with direct B2 supporting-count impact | Could shift genuinely-neutral claims elsewhere in the corpus toward more committal stances — needs validation on a broader set, not just these 6 rows | Moderate–high if phrased around these specific sentences rather than as a general principle |
| P1 | B1 LLM prompt (counter-Alpha decision criteria) | Inconsistent resolution between plain `opposes_alpha` and `supports_counter_alpha` when evidence engages both readings | evrs-008, 042, 045 | Clearer decision criteria for when text should route through the counter-Alpha mechanism (e.g. an explicit match test against the counter-Alpha's own `core_thesis` vocabulary) | 3 rows, all HIGH severity | Could over-trigger counter-Alpha attribution elsewhere if not carefully scoped | Moderate |
| P2 | Alpha taxonomy definitions (`alpha_taxonomy_v1.yaml`, A304 boundary) | Unclear whether "spending not yet proven to convert to revenue" execution-risk claims belong under A304 (valuation/multiples) or elsewhere | evrs-007, 041 | Document the intended boundary of A304 relative to adjacent execution/payoff-risk claims — a definitional clarification, not a scoring change | 2 rows directly; likely reduces ambiguity for similar future claims | Low (documentation only) | Low if phrased as a general boundary principle |
| P2 | `ai_alpha_discriminator.py` AI_ALPHA_IDS hard gate | Gate's current anchor-phrase/change-predicate criteria excludes some evidence an independent reviewer considers on-thesis | evrs-011, 016, 044 | **Review** (not loosen) the gate's precision/recall tradeoff against a broader sample than these 3 rows | Uncertain until reviewed — could be zero if the gate is correctly rejecting borderline cases | **High if loosened carelessly** — this gate was built specifically to close a prior, real false-positive problem | **High** — this is the clearest case in the whole analysis where tuning to these exact 3 rows would risk reopening a previously-fixed problem |
| P3 | Alpha Mapper single-Top-1 selection contract | Multi-topic "kitchen sink" sentences (common in analyst-debate summaries) inherently strain a single-primary-Alpha model | evrs-002, 011(partial), 023, 030, 031, 045, 049 | Not a scoring tweak — worth a broader design conversation about whether single-Top-1 is the right consumption contract for this text shape | Potentially large architecturally; out of scope for a scoring fix | N/A (design question, not a code change) | N/A |

No P0 was identified: zero critical (support↔oppose) reversals, and the only rows with confirmed direct B2 count impact are MEDIUM severity, not CRITICAL.

**Explicitly not proposed, per this task's own constraints:** no threshold changes (the `ALPHA_SCORE_THRESHOLD=50.0`/B2's `0.35`-family constants), no sample-specific keywords, no ticker/sample hard-coding, no tuning aimed at these 25 specific sample_ids.

---

## Overfitting risk

Every "systematic" label above is based on **11 and 14 rows respectively**, drawn from **6 tickers and a narrow slice of agent roles**. Any fix built directly against this set's specific phrasing risks overfitting badly: `evrs-023`/`evrs-030` alone show the sample already contains duplicate content, meaning the *effective* independent sample size is smaller than the nominal row count. The AI-gate finding (P2, 3 rows) is the highest-risk case for overfitting specifically because the gate exists *because of* a prior overfitting-adjacent problem (generic-keyword false positives) — loosening it based on 3 rows from one 50-row benchmark would repeat the same mistake in reverse.

## New holdout required after fix = YES

This 50-row set should become the **development/error-analysis set**. Recommend a new, untouched **50–100 row blind holdout**, stratified across NVDA/QQQ/MSFT/SNDK/TSM/AMD and across all 5 stance classes and the 10 canonical Alpha families, generated fresh (not reusing any of these 50 claims) after any future prompt/definition changes are made — not generated in this task.
