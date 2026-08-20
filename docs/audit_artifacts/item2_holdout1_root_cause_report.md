# QA Closure v0.1.2 — Blind Holdout #1 Root-Cause Analysis

Diagnosis only. `PROVIDER_CALLS = 0` — no B1, Alpha Mapper, or reviewer call was made in this task; every number below comes from joining the four already-frozen holdout artifacts by `sample_id` and this analysis's own explicit judgments (see `scripts/build_item2_holdout1_root_cause_analysis.py`'s `POLARITY_JUDGMENTS`/`ALPHA_JUDGMENTS`). The frozen result is unchanged and is **not** filtered or recalculated anywhere below: **polarity 79/100 = 79% FAIL, alpha match 73/100 = 73% FAIL, critical reversals = 0** (independently re-verified from row-level joins, not trusted from the summary JSON).

Holdout CSV SHA-256 re-verified: `835d7608b1aa61417ca3fa8eee955e964cdbb6aa5693484ec6cab311d873f592` — matches. Integrity re-confirmed: 100 holdout rows = 100 B1 predictions = 100 Alpha predictions = 100 reviewer rows, no duplicate/missing/extra IDs.

---

## POLARITY — 21 mismatches

Full row data: `docs/audit_artifacts/item2_holdout1_polarity_root_cause.csv`.

### Root cause

| Root cause | Count | Status |
|---|---|---|
| I. LOW_INFORMATION_OR_GENERIC | 5 | **SYSTEMATIC** |
| F. MIXED_OR_CONDITIONAL_LANGUAGE | 5 | **SYSTEMATIC** |
| M. OTHER (source-format artifact: header/fragment/score-label) | 4 | **SYSTEMATIC** |
| H. TARGET_ALPHA_AMBIGUITY | 2 | repeated but weak |
| J. TICKER_CONTEXT_MISSING | 2 | repeated but weak |
| E. COUNTER_ALPHA_BOUNDARY | 1 | isolated |
| K. REVIEWER_AMBIGUITY | 1 | isolated |
| L. B1_PROMPT_INTERPRETATION_ERROR | 1 | isolated |

**This is a materially different composition than the old 50-row development set's root-cause analysis**, which was dominated by MIXED_OR_CONDITIONAL_LANGUAGE alone (6/11, 55%). Here, F is tied with a **new** dominant pattern (I) and closely trailed by another new one (M):

- **I (LOW_INFORMATION_OR_GENERIC, 5 rows)** and **M (OTHER — structural artifacts, 4 rows: a bare section header `holdout-056`, a truncated mid-sentence fragment `holdout-068`, a rhetorical debate prompt `holdout-052`, a bare sentiment-score field `holdout-097`)** together account for 9/21 (43%) of mismatches. In every one of these, **B1 commits to a directional stance where the reviewer sees no assertable content at all** — the opposite failure direction from what the B1 v2 mixed-language fix targeted (which taught B1 to commit *more* readily rather than default to `mentions_alpha`/`neutral_background`). This is the strongest, most actionable finding in the polarity analysis: **the v2 prompt's general principle appears to also make B1 slightly more willing to find directional signal in genuinely thin/format-degenerate evidence** (trading-plan positioning notes, section headers, debate rhetoric, bare score fields) that a more conservative reading would correctly leave at `mentions_alpha`/`neutral_background`. This cannot be proven causally without a v1-vs-v2 comparison on this same holdout (out of scope — no B1 regeneration permitted in this task), but it is well-evidenced as an observed pattern.
- **F (MIXED_OR_CONDITIONAL_LANGUAGE, 5 rows)** is still present, confirming the underlying phenomenon the v2 fix targets remains genuinely hard — and notably `holdout-065` shows the **reverse** direction (B1 *under*-committing on "recession risk remains low (12%) but creeping higher", a quantified, resolvable claim), showing the fix has not fully generalized in either direction.

### Severity (re-verified, not assumed)

CRITICAL: **0** · HIGH: 1 (`holdout-012`) · MEDIUM: 15 · LOW: 5

### Downstream consequence

`B2_SUPPORT_COUNT`-affecting: `holdout-031, 032, 033, 042, 050` (5 rows genuinely change B2's `supporting_evidence_count` today). Of these, `holdout-042` and `holdout-050` are **also** `used_in_conflict=True` — the two highest-stakes rows in this mismatch set, both classified `MIXED_OR_CONDITIONAL_LANGUAGE`/`GENUINELY_AMBIGUOUS`. All other 16 rows: `NONE` (not currently consumed downstream regardless of which label wins).

### Plausibility

REVIEWER_MORE_PLAUSIBLE: **12** · SYSTEM_MORE_PLAUSIBLE: **0** · GENUINELY_AMBIGUOUS: **9**

Zero rows where independent re-reading favored B1's judgment over the reviewer's. This is a meaningfully different balance than the old development set (which had 2 system-favored rows) — consistent with the "over-commitment on thin evidence" hypothesis above.

### Quality-conditioned accuracy (diagnostics only — see section below)

Not-generic-AND-ticker-specific: **41/47 = 87.2%** (would clear target) · generic-OR-non-ticker-specific: **38/53 = 71.7%** (clearly the weak subset)

**Main systematic causes, ranked:**
1. B1 over-committing to a directional stance on low-substance/format-degenerate evidence (I + M, 9/21, 43%)
2. Mixed/conditional language, both directions of failure (F, 5/21, 24%) — the v2 fix's own target domain, not fully resolved
3. Target/ticker mismatch — evidence genuinely about a different Alpha or a different company (H + J, 4/21, 19%)

**Should B1 change again? SMALL_GENERAL_FIX_JUSTIFIED** — see recommendations below. Not `MAJOR_REDESIGN_REQUIRED` (0 critical reversals, only 2/21 mismatches carry real current B2/conflict consequence, and 9/21 ambiguous-or-close cases are not a sign of broad unreliability), but not `NO_CHANGE` either given the well-evidenced, repeated over-commitment pattern on thin evidence — a real, describable, low-taxonomy-risk gap distinct from "one row below threshold, don't touch it."

---

## ALPHA MATCH — 27 mismatches

Full row data: `docs/audit_artifacts/item2_holdout1_alpha_root_cause.csv`.

### Root cause

| Root cause | Count | Status |
|---|---|---|
| E. TAXONOMY_OVERLAP | 7 | **SYSTEMATIC** |
| C. AI_HARD_GATE_EXCLUSION | 6 | **SYSTEMATIC** |
| B. CANDIDATE_RECALL_ERROR | 5 | **SYSTEMATIC** |
| I. EXPECTED_NONE_GENERIC | 5 | **SYSTEMATIC** |
| D. THRESHOLD_EXCLUSION | 3 | **SYSTEMATIC** |
| A. TOP1_RANKING_ERROR | 1 | isolated |

expected-Alpha-rank-2 (present, not top-1): captured within A/E above · expected-Alpha-absent-from-top-5: **16** (subset of B/I) · Top-1 errors: **1** · candidate recall: **5** · AI hard-gate exclusions: **6** · taxonomy overlap: **7** · generic/unmappable: **5** · other: **3** (D, threshold-only)

### Plausibility

REVIEWER_MORE_PLAUSIBLE: **13** · SYSTEM_MORE_PLAUSIBLE: **0** · GENUINELY_AMBIGUOUS: **14**

Same pattern as polarity: zero rows favor the system on independent re-reading, though nearly half are genuinely ambiguous multi-topic evidence rather than clean reviewer wins.

**Should Alpha Mapper change? AI_GATE_REVIEW_REQUIRED** for the narrow gate question (see below); otherwise **NO_CHANGE** to scoring/threshold/candidate-generation. TAXONOMY_OVERLAP (7, the single largest bucket) reflects a structural property of the evidence corpus (analyst debate sentences routinely span multiple Alpha-relevant topics) that a single-Top-1 selection model cannot fully resolve without a design change — out of scope for a "fix" in the P0–P3 sense.

---

## AI HARD-GATE INVESTIGATION (mandatory section)

Full row data: `docs/audit_artifacts/item2_holdout1_ai_gate_analysis.csv`. The four groups the task warned are non-equivalent, computed precisely:

| Group | Count | sample_ids |
|---|---|---|
| 1. System final matched Alpha ∈ {A101,A102,A103} | 2 | `holdout-027, 063` |
| 2. Reviewer expected Alpha ∈ {A101,A102,A103} | 8 | `holdout-027, 042, 063, 069, 071, 077, 079, 084` |
| 3. An AI-Alpha candidate was generated at all (any score) | 27 (all mismatches) | — |
| 4. An AI-Alpha candidate is the **raw highest score** but marked ineligible | 10 | `holdout-002, 009, 027, 069, 071, 077, 079, 081, 084, 086` |

**A. How many of the 27 wrong-Alpha rows are *directly* caused by AI hard-gate exclusion** (meaning: gate removal would flip the system's answer to match the reviewer)**? 6** — `holdout-027, 069, 071, 077, 079, 084`. (Group 4's 10 is a superset that includes 4 rows — `002, 009, 081, 086` — where an AI candidate is gate-blocked but is *not* what the reviewer expected either; removing the gate would not fix these 4, so they are classified under `CANDIDATE_RECALL_ERROR`/`THRESHOLD_EXCLUSION` instead, not the gate.)

**B. In how many would the reviewer-expected Alpha have been Top-1 without the gate? 6** (identical to A, by construction of the above distinction).

**C. In how many is the reviewer-expected Alpha not actually strong even without the gate?** The 4 group-4-but-not-A/B rows (`002, 009, 081, 086`): in each, the reviewer's own pick is a *different* Alpha than the one the gate blocks, and that pick is itself weak-or-absent from the top-5 (`A304` absent for `002/009/086`; `A001` present only at 0.08 for `081`) — the gate is not what stands between the system and correctness for these 4.

**D. Concentration:** by ticker, the 6 true gate-caused rows: **SNDK 5** (`069, 071, 077, 079, 084`), MSFT 1 (`027`). By source run, verified directly: **all 5 SNDK rows come from the single secondary run `8d21c047-fc0a-4d94-957d-3787f353a544` (2026-07-17, the oldest run in this holdout)** — a striking concentration (5/6 = 83% of all gate-caused mismatches trace to one run). Only `holdout-027` (MSFT) falls outside it. Not one Alpha dominates within the six (A101 in 3, A103 in 3).

**E. Verdict: MIXED / INCONCLUSIVE**, leaning plausibly-protective. Of the 6 true gate-caused mismatches: 4 (`069, 071, 079, 084`) carry the reviewer's own `too_generic=True` and/or low confidence — squarely matching the gate's documented purpose (rejecting generic AI/cloud/capex mentions without specific engagement). 2 (`027, 077`) show **high reviewer confidence with genuinely specific content** (named dollar figures, named companies — "Nvidia's $500 billion AI financing plan", "IBM's warning... reduce forward memory demand forecasts") that the gate still rejects — a real, narrow over-strictness cost. Net: **2/100 rows (2%) show the gate plausibly being too strict**; the rest of its cost is defensible.

### False-positive safeguard research (repo-only, no web)

Found in `comqutor_alpha/structure_engine/ai_alpha_discriminator.py`'s own module docstring and `tests/test_ai_alpha_mapper_discrimination.py` (`TestGenericTermsNeverAdmitAlone`):

- **Original problem:** "closes over-triggering and shared generic-keyword collisions between A101/A102/A103" — generic terms like "AI", "cloud", "capex", "data center" alone were previously sufficient to formally match one of the three closely-related AI Alphas, and the taxonomy's factor-weight table deliberately gives *partial credit across all three* for shared factors (appropriate for scoring, not for a hard admission decision).
- **What the gate protects against:** documented, concrete false-positive examples in the test suite: `"AI is important."`, `"The company talked about artificial intelligence."`, `"Technology stocks were mixed today."`, `"The company discussed its cloud strategy."`, `"Capex guidance was reaffirmed for the fiscal year."` — all previously would have (or could have) triggered a formal AI-Alpha match on keyword presence alone.
- **Existing regression tests protecting it:** `tests/test_ai_alpha_mapper_discrimination.py` — 16 test classes covering the golden set (50 cases), per-Alpha hard-gate requirements, pairwise disambiguation, generic-term rejection, mutation-proves-load-bearing checks, and non-AI-Alpha regression protection.
- **Comparing against the new holdout failures:** 4 of the 6 gate-caused rows are textually close to the documented false-positive class (vague, hedge-framed, no specific data); 2 are not (specific figures/companies present) — a genuine but narrow gap between the gate's documented intent and its current precision.

**Would relaxing the gate to recover the missed rows likely reopen the historical false-positive problem? MEDIUM RISK.** Loosening broadly (e.g., relaxing the anchor-phrase requirement generally) would very plausibly reopen the exact, already-solved, well-tested false-positive class (4/6 of this holdout's own gate-caused rows would have been in that reopened set). A *narrow*, targeted refinement that specifically admits cases with named entities/concrete figures (the `027`/`077` pattern) without loosening the generic-term rejection is conceptually possible but unproven — evidence here (n=2) is too thin to justify a specific change, only a review.

---

## DUPLICATE / EFFECTIVE SAMPLE SIZE

LLM-judged duplicates: **37** · system structural-duplicate signal: **6** · overlap: **5** · exact-text duplicate groups within the 100-row holdout: **1** (`holdout-023`/`holdout-089`, both "Revenue growth is accelerating.", by-chance collision from the sampling pool, not an exclusion-logic failure — exclusion was scoped against the *old 50*, not new-vs-new).

The 37-vs-6 gap is genuine semantic (paraphrase-level) clustering by the LLM versus the system's much narrower structural evidence-fact-group signal — confirmed directly: `holdout-005`/`holdout-010` (near-identical "trader's plan to build a position... beat-and-hold... beat-and-raise... 50-day SMA" wording) are both correctly LLM-flagged as duplicates. **Effective semantic cluster count: not precisely reconstructable** — this evaluation's own artifacts persisted only the per-row boolean, not cluster membership, and re-deriving it would require a new Provider call (out of scope, `PROVIDER_CALLS=0`). A rough, disclosed estimate based on the visible 2-per-cluster pattern: likely in the 12–18 distinct-cluster range for the 37 flagged rows, not claimed as precise.

**Duplicate rows do not score worse** — polarity: duplicate=True 81.1% vs duplicate=False 77.8%; alpha: duplicate=True 83.8% vs duplicate=False 66.7%. **Duplication is not a driver of the metric shortfall**; if anything, unique (non-duplicate) rows are somewhat harder on the alpha-match dimension.

---

## TICKER-SPECIFIC DIAGNOSTIC

`not_ticker_specific = 51/100`. By ticker (ticker_specific=True / False):

AMD 12/4 · MSFT 11/6 · TSM 7/9 · SNDK 7/10 · NVDA 7/10 · QQQ 5/12

This tracks instrument type, not reviewer over-strictness: **QQQ is an ETF** — evidence about it is structurally more macro/sector-flavored and less often ties to a single named entity, which is a genuine, correct reason for lower ticker-specificity, not a reviewer artifact. AMD and MSFT (single companies, heavily covered by name in their own debate transcripts) skew ticker-specific as expected. No evidence of source-segmentation context loss driving this number generally — it matches instrument-type expectations.

By ticker, polarity / alpha accuracy: AMD 68.8%/50.0% (weakest on both) · MSFT 82.4%/82.4% · NVDA 88.2%/88.2% (strongest) · QQQ 76.5%/64.7% · SNDK 76.5%/58.8% · TSM 81.2%/93.8%.

---

## SOURCE-RUN EFFECTS

The 6 rows with pre-AI-gate-era `target_alpha_id` values come from `8d21c047-fc0a-4d94-957d-3787f353a544` (SNDK secondary run, **2026-07-17**, the oldest run in this holdout) — already disclosed in the frozen holdout report. Per-run accuracy (n≥3, all six):

| source_run_id | ticker | n | polarity | alpha |
|---|---|---|---|---|
| `b71765a0...` | AMD | 16 | 68.8% | 50.0% |
| `07ddc074...` | MSFT | 17 | 82.4% | 82.4% |
| `5ffe121a...` | NVDA | 17 | 88.2% | 88.2% |
| `a364e0ee...` | QQQ | 17 | 76.5% | 64.7% |
| `8d21c047...` | SNDK (secondary) | 16 | 81.2% | 62.5% |
| `1a338ced...` | TSM | 16 | 81.2% | 93.8% |

Since each ticker draws from exactly one dominant run, this table is equivalent to the by-ticker table above — **no additional, ticker-independent version-drift signal beyond the already-disclosed AI-gate/2026-07-17 interaction**. AMD's weakness is a ticker/content effect, not a source-run artifact (its run is the *most recent* of the six alongside MSFT's, not an old one).

---

## TOP RECOMMENDED FIXES (P0–P3, conceptual only — **DO NOT IMPLEMENT**)

| Priority | Component | Problem | Affected sample_ids | Conceptual fix | Expected benefit | Regression risk | Overfitting risk | PO approval required |
|---|---|---|---|---|---|---|---|---|
| P1 | B1 prompt | Over-commits to a directional stance on format-degenerate/low-substance evidence (trading-plan notes, section headers, debate rhetoric, bare score fields) | `005,010,032,052,056,058,068,093,097` (9 rows) | Add explicit guidance: before resolving a stance, first judge whether the Evidence contains an assertable claim at all (vs. a header/fragment/procedural prompt/bare metric label); if not, stance is `mentions_alpha`/`neutral_background` regardless of superficial keyword association | Could address the largest single polarity pattern (43% of mismatches) | Could make B1 marginally more conservative on borderline-but-real claims elsewhere — needs broader validation, not just these 9 | Moderate if phrased around these exact formats rather than a general "is there an assertable claim" test | YES |
| P2 | B1 prompt | Mixed/conditional resolution still imperfect in both directions (`holdout-065` under-commits on a quantified, resolvable claim) | `033,042,050,065,074` (5 rows) | Incremental refinement of the v2 guidance, not a new mechanism | Uncertain, smaller than P1 | Moderate — this is the same domain the v2 fix already touched once | Moderate-high | YES |
| P2 | Alpha Mapper keyword/factor recall (A304 specifically) | Evidence with explicit numeric valuation-multiple language ("162x earnings") not recognized as A304-relevant; A304 absent from top-5 in several cases | `001,002,006,009,012` (illustrative; A304-recall gaps concentrated in `TAXONOMY_OVERLAP`/`CANDIDATE_RECALL_ERROR` rows) | Review whether A304's keyword/factor coverage recognizes numeric multiple expressions ("Nx earnings", "Nx P/E"), not just the literal phrase "P/E multiple" | Could recover several CANDIDATE_RECALL_ERROR rows | Low if scoped to A304's own keyword coverage only | Low-moderate | YES |
| P2 | AI hard gate (`ai_alpha_discriminator.py`) | 2/100 rows show the gate rejecting specific, high-reviewer-confidence evidence (named entities/figures), not just generic chatter | `027, 077` | **Review** (not loosen) whether named-entity/figure-bearing AI-adjacent evidence should have a narrower admission path, without touching the generic-term rejection that protects the documented false-positive class | Uncertain — n=2, too thin to promise a specific fix | **Medium** if loosened broadly — would plausibly reopen the documented, already-solved false-positive problem (4/6 of this holdout's own gate-caused rows resemble it) | High if tuned to these 2 specific rows | YES |
| P3 | Evaluation protocol | `not_ticker_specific=51` driven substantially by instrument type (QQQ is an ETF), not a system defect | N/A | No production change; note in future benchmark documentation that ETF tickers should be expected to show structurally lower ticker-specificity | N/A | N/A | N/A | NO |

Not proposed, per this task's explicit constraints: no sample-specific keywords, no ticker hardcoding, no lowering the 0.35 threshold because 73% missed, no removing the AI hard gate because target is 75%, no reviewer-label changes.

---

## NEW HOLDOUT GOVERNANCE

Blind Holdout #1 is now **consumed**. Permitted future uses: root-cause analysis (this document), development regression after a future fix. **Not** permitted: reuse as final blind acceptance after any semantic change.

**NEW BLIND HOLDOUT #2 REQUIRED after any semantic change = YES.** Recommended size: **100 minimum**; given both metrics are close to threshold (79% vs 80%, 73% vs 75%) and this analysis found real variance by ticker (AMD 50–69%, NVDA/TSM 88–94%), **150–200 is worth considering** to reduce the chance that a future pass/fail hinges on a handful of borderline rows. Not generated in this task.

## FINAL CONCLUSION

Ranked from strongest to weakest contributor:

1. **(C) Conservative safeguard tradeoffs** — the AI hard gate, a deliberate, well-tested, well-documented anti-false-positive mechanism, directly explains 6/27 (22%) of alpha mismatches and is judged plausibly protective for 4 of those 6, genuinely over-strict for only 2/100 rows overall.
2. **(D) Taxonomy/evaluation ambiguity** — `TAXONOMY_OVERLAP` is the single largest alpha root cause (7/27), and `GENUINELY_AMBIGUOUS` is the plurality plausibility verdict on both metrics (9/21 polarity, 14/27 alpha) — a large share of the shortfall is genuine multi-topic evidence and defensible reviewer/system disagreement, not a clean defect.
3. **(B) One or two systematic production patterns** — B1's over-commitment on low-substance/format-degenerate evidence (9/21 polarity mismatches, 43%) is a real, well-evidenced, describable pattern with a plausible, narrow fix; Alpha Mapper's A304-recall gap on numeric-multiple language is a smaller, second concrete pattern.
4. **(E) Low-quality source evidence** — a meaningful contributor (headers, fragments, debate rhetoric, bare score labels feeding into the sample at all) but overlapping heavily with #3 above rather than a wholly separate cause.
5. **(A) Broad model unreliability** — **not** supported: 0 critical reversals across 100 rows, near-90% accuracy on both metrics within the not-generic-and-ticker-specific subset, and 0/48 mismatches judged system-more-plausible on careful re-reading. The failures are concentrated and describable, not scattered.

**(F) is the accurate summary: a mixture, weighted toward (C) and (D), with (B) as the most actionable component.**
