# v0.1.3 MSFT A304 Negation-Aware Structure Extraction

Design + bounded implementation. Offline-validated. **Provider calls: 0. TradingAgents calls: 0. Ticker runs: 0.** HEAD unchanged (`9f228723fad5406c72e62beca67ec70ea0fdb004`). No commit. No push.

## Executive Summary

```
Design gate:                       PASS
Implementation:                    YES

Canonical positive claim:          claim:82
First broken stage:                A. Missing factor alias (source side)

Source factor canonicalization:    Revenue Growth (existing factor, no new
                                    factor invented) + generic adverse-
                                    phrasing regex patterns
Negation handling:                 REUSED existing machinery (no new logic)

Positive claim extracts:           YES
"not a slowdown scenario" false edge: NO

MSFT A304 before:                  38.3642 / candidate
MSFT A304 offline after:           43.3642 / candidate (not detected)

Other Alpha level changes:         NONE (only A304 changed, across all 10
                                    MSFT alphas and all 5 other tickers)

False-positive edges:              0 / 89 scanned claims
New regressions:                   0
Gold unchanged:                    YES
Provider calls:                    0
Ticker runs:                       0
```

## John — MSFT A304 Extraction Fix

```
Item                          | Before              | After
--------------------------------|---------------------|---------------------
Growth slowdown recognized      | NO                  | YES
Multiple compression recognized | YES                 | YES (unchanged)
Causal edge                     | NOT EMITTED         | EMITTED (conditional)
Negation safety                 | N/A (never reached) | VERIFIED (7 categories)
A304 local structure            | raw=0.0, 0 edges    | raw=25.0, 1 edge
A304 score                      | 38.3642             | 43.3642
A304 level                      | candidate           | candidate (unchanged)

Positive: "slowdown ... could trigger multiple compression" -> expected causal edge   CONFIRMED
Negative: "not a slowdown scenario" -> no adverse edge                                CONFIRMED

Gold unchanged. No threshold changes. No Provider calls.
```

## 1. Canonical Claim Confirmed

`43472ace-454f-4c69-892c-adca91c25be7:fundamental_agent:fundamentals_report:claim:82` — exact persisted text: **"Any slowdown in Azure growth could trigger multiple compression."** Persisted `factors: ["Valuation Risk"]`, `assertion_status: "conditional"`, `analysis_eligible: true`.

## 2. Extraction Pipeline Traced

`claim text → _extract_factors() [factor_normalizer + literal record.factors] → _extract_edges()/_llm_edges() [len(factors)<2 early-return] → relation_grammar.extract_relation_candidates() [clause segmentation, mention-span finding, causal-verb matching, direction guard] → assertion_status_for() [negation/conditional] → _edge() → graph_builder.py (lineage/qualification) → activation_scorer_v2.py (local_structure_support, assertion_status != negated gate)`.

Key existing infrastructure confirmed already present and reused unmodified: clause segmentation (`_split_clauses`), causal rank/direction guard (`CAUSAL_RANK`, `plausible_causal_direction` — Revenue Growth rank 3, Valuation Risk rank 3, equal-rank pairs already admissible), the causal verb "trigger" (already in `FORWARD_CAUSAL_VERBS`), negation detection (`NEGATED_RELATION_PATTERN` scoped to the clause-local "bridge", `analyze_claim_semantics().negated`), and the downstream qualification gate (`assertion_status != negated` in `activation_scorer_v2.py:344`).

## 3. First Broken Stage — Proven

**A. Missing factor alias.** `_extract_factors()` on claim:82 produced exactly one factor, `Valuation Risk` (via the existing literal alias "multiple compression"). The source-side phrase "slowdown in Azure growth" matched **no** entry in `FACTOR_ALIASES`. Since both `_extract_edges()` and `_llm_edges()` return immediately when `len(factors) < 2`, no relation extraction was ever attempted — confirmed by direct reproduction before any code change.

## 4. Structural Semantics — Existing Ontology Reused

No new factor was created. The nearest existing canonical factor for "slowdown in Azure growth" / "revenue deceleration" / "growth deterioration" is **`Revenue Growth`** (already a canonical factor with growth-supportive aliases like "revenue acceleration", "beat and raise") — the adverse-direction phrasing is the same underlying concept, not a distinct one. Target side (`Valuation Risk`, via "multiple compression") was already correctly recognized and was **not modified**.

## 5. Implementation

Added `FACTOR_ALIAS_PATTERNS` — a small, generic, ticker-independent dict of regex patterns — to `comqutor_alpha/structure_engine/factor_normalizer.py`, the single central authority both `extract_known_factors_from_text()`/`factor_mention_span()`/`factor_mention_start()` (factor_normalizer.py) and `_factor_spans()` (relation_grammar.py, imported from factor_normalizer.py) now consult, additively, alongside the existing literal `FACTOR_ALIASES`:

```
slowdown in <0-3 words> growth
growth slowdown
decelerating <0-3 words> growth
growth deceleration
growth deterioration
slower <0-3 words> growth
weaker <0-3 words> growth
```

**No new negation logic was added.** No ticker, alpha, or claim-ID check exists anywhere in the change (verified: "Azure" appears only as claim *content*, never as code; the same fix behaves identically for MSFT, NVDA, GOOGL, and a made-up ticker "ZZZZ" in testing).

## 6. Design Gate — PASS (All 9 Criteria)

| Criterion | Result |
|---|---|
| claim:82 first break proven | YES |
| Existing ontology represents both source and target | YES |
| Existing relation represents the causal relation | YES ("trigger" already supported; rank-equal direction already admissible) |
| Proposed rule is general, not MSFT-specific | YES |
| Negative-control scope handled deterministically | YES |
| Corpus blast radius bounded | YES (89 scanned, 1 new edge) |
| No Gold-specific condition required | YES |
| No threshold change required | YES |
| No Provider call required | YES |
| Regression risk | LOW |

## 7. Corpus Blast-Radius Scan (Before Implementation)

Scanned all persisted claims across all six authoritative runs for `slowdown/slowing/slower/deceleration/decelerating/compression/compress/contraction/valuation multiple`: **89 claims matched.** Of those, exactly **2** gained a new factor recognition, and exactly **1** produced a new causal edge:

| Claim | Classification |
|---|---|
| MSFT claim:82 | `TRUE_POSITIVE_EXPECTED_EDGE` |
| NVDA bear_researcher claim:77 ("...a simple growth deceleration far outweighs...") | `RISK_ONLY_NO_ASSERTED_EDGE` — gains a harmless factor tag only; no target factor present, no edge |

**Unexpected false positives: 0.**

## 8. Positive Causal Semantics — Honest Boundaries

| Example | Result |
|---|---|
| "Any slowdown in Azure growth could trigger multiple compression." | **EDGE** (Revenue Growth → Valuation Risk, causal, conditional) |
| "Decelerating revenue growth may pressure valuation multiples." | No edge — target phrase "valuation multiples" is not an existing `Valuation Risk` alias (target side intentionally untouched) |
| "Weaker revenue growth could lead to multiple contraction." | No edge — target phrase "multiple contraction" is not an existing alias |
| "Growth deterioration may cause multiple contraction." | No edge — same target-side gap |

Per instruction, these are reported honestly as **not** producing an edge rather than loosened to force a pass — the fix is scoped to the source side only.

## 9. Negation Audit — All 7 Categories

| Category | Example | Result |
|---|---|---|
| A. Positive causal | "Slowdown in Azure growth could trigger multiple compression." | EDGE (causal, conditional) |
| B. Negated premise | "This is not a slowdown scenario." / "Azure growth is not slowing." | NO EDGE (zero factors recognized) |
| C. Negated consequence | "Slower growth would not cause multiple compression." | Edge created, `assertion_status=negated` — excluded from qualifying structure by the existing, unmodified gate |
| D. Negated causality | "There is no reason to expect slower Azure growth to compress valuation." | Any edge is `negated`, never asserted |
| E. Risk-only | "There is a risk of slower Azure growth." | NO EDGE (1 factor only) |
| F. Descriptive-only | "Investors discussed a possible slowdown." | NO EDGE (zero factors) |
| G. Counterfactual/denial | "Growth is strong, not slowing." | NO EDGE (zero factors) |

**No new negation model was built** — every case above is handled by the pre-existing `assertion_status_for()`/`analyze_claim_semantics()`/`activation_scorer_v2.py` qualification chain, exercised for the first time against this new factor-recognition pathway.

## 10. Clause Boundary Safety — Mixed Clause Test

`"Azure is not slowing, but valuation could compress if demand weakens."` → **zero factors, zero edges.** Neither clause contains a phrase matching any recognized factor pattern under the existing, unmodified ontology (bare "demand" without an AI/GPU/Inference qualifier is not a factor) — no fabricated edge in either direction. Reuses the pre-existing `_split_clauses()` clause segmentation.

*Note (out of scope, reported for completeness)*: `assertion_status_for()`'s fallback to whole-claim `analyze_claim_semantics().negated` is not itself clause-scoped, unlike its bridge-based `NEGATED_RELATION_PATTERN` check — a pre-existing characteristic that could, in principle, over-suppress (never over-create) a relation in an unrelated clause of some other mixed sentence. Not exercised by any required test here; not modified, per this task's scope.

## 11. Edge Direction — Verified Correct

Required: `growth slowdown → multiple compression`. Actual: `MSFT Revenue Growth → Valuation Risk`. Explicit regression test confirms the source is never `Valuation Risk` for this claim (no reversal).

## 12. No Stance/Evidence Rule Change; No Alpha-ID Hardcode

B1 stance, ticker specificity, Primary/Secondary, fact dedupe, and evidence scores are all untouched — claim:82 independently passed canonical evidence qualification before and after this change. No edge dict emitted by this code ever contains an `alpha_ids` key (verified by test) — Alpha association remains the existing, unmodified lineage authority's responsibility.

## 13. MSFT A304 Offline Replay

Pure-function replay: `extract_structures_from_records()` on MSFT's persisted records (deterministic-only, no `llm_gateway`), then `build_and_score_structure_graph()` against the persisted, unmodified `alpha_matches.json`. "Before" = patterns disabled (simulating pre-fix code); "after" = current fixed code. No Provider calls; no run artifact mutated.

| | Before | After |
|---|---:|---:|
| Score | 38.3642 | 43.3642 |
| Level | candidate | candidate |
| `local_structure_support.raw` | 0.0 | 25.0 |
| `qualifying_local_edge_count` | 0 | 1 |
| `cap_reason_codes` | `[NO_LOCAL_STRUCTURE_SUPPORT]` | `[]` |

The +5.0 score delta is **entirely** attributable to `local_structure_support`'s contribution rising from 0.0 to 5.0 (raw 25.0 × weight 0.2) — every other component (evidence_quality, agent_independence, ticker_specificity, recency, direction_consistency) is byte-identical. **A304 remains `candidate`** — not forced across any threshold, per explicit instruction not to require a Gold hit.

## 14. All-Alpha and All-Ticker Blast Radius

**MSFT, all 10 alphas**: only A304 changed (38.3642→43.3642, candidate→candidate); A001, A003, A101, A102, A103, A201, A301, A501, A601 are byte-identical before/after.

**Other five tickers** (full before/after pipeline replay, not just the extraction layer): NVDA, QQQ, SNDK, TSM, AMD each show **zero** edge-count change and **zero** alpha score/status change. SNDK A103, SNDK A301, and TSM A301 — the explicit negative controls — are confirmed unchanged.

## 15. Provider Reliability Baseline — Unchanged

`week2_llm.py` retry policy, Provider Health, Recorder Health, and the Multi-Run Evaluator are untouched. Evidence-stance retry remains 2 retries / 3 max attempts. No new test requires a real Provider call.

## 16. Tests

**New**: `tests/test_msft_a304_negation_aware_extraction.py` — **21 passed, 0 failed**, covering the canonical positive claim, factor normalization (generic segment phrasing), anti-overreach (bare slow/weak), correct edge direction, negated premise/relation/consequence, risk-only and descriptive language, the mixed-clause case, an unrelated valuation mention, two honest target-side boundary cases, existing-edge regressions, ticker-independence, and no-Alpha-ID-hardcoding.

**Existing structure suites**: `test_structure_correctness_sprint.py`, `test_relation_grammar.py`, `test_structure_extractor.py`, `test_factor_normalizer.py` — **115 passed, 0 failed**.

**Regression suites**: P0/P1 **26/26**, Provider Health **32/32**, Multi-Run Reproducibility **28/28**, Recorder Health **16 passed / 2 skipped** (environment-dependent, unrelated), Evidence-Stance Retry Fix **18/18**.

**Frozen SHA guards**: neither `factor_normalizer.py` nor `relation_grammar.py` is protected by any of the four known guard files (`test_step10_final_e2e_qa.py`, `test_step11_provider_health_rerun.py`, `test_evidence_review_v2.py`, `test_source_integrity.py`) — no hash update required.

**Full backend suite**: **21 failed, 4158 passed, 3 errors, 49 skipped** (baseline: 21 failed, 4139 passed, 3 errors, 47 skipped). Delta = +21 new tests, −2 passed/+2 skipped from an unrelated, already-observed environment condition (an ephemeral launcher log no longer present in this shell). Every failed/error test name matches the baseline verbatim. **New regressions: 0.**

## 17. Implementation Verdict

**`A304_FIX_IMPLEMENTED_AND_VALIDATED_OFFLINE`.** Complete implementation, all tests green, precisely bounded blast radius (1 new edge across the entire six-run corpus, 0 false positives across 89 scanned claims), and a fully-explained offline replay result. This verdict is **not** based on A304 crossing the Gold Hit threshold — it remains `candidate`.

## 18. Live Validation Readiness

**`MSFT_FRESH_VALIDATION_READY = YES`** — not executed in this task. A future, separately-authorized fresh MSFT run could validate this fix against live Provider output.

## 19. Deferred Work

NVDA A102, MSFT A102 research coverage, AMD A102, NVDA A201, AMD A201, QQQ A101, SNDK A103, SNDK A301, TSM structure changes, Provider retry beyond the current evidence-stance change, Gold ≥75% itself, multi-run live benchmark, and `Valuation Risk` target-side alias extension (e.g. "valuation multiples", "multiple contraction").

---

## Final Validation

Gold v1 SHA256 `99b1cd0247637054de360c3b5c0c00c7d8052152f3db1d29045eae1850bd8e9a` unchanged. Gold Validity SHA256 `3643ea45168c029d7c2a2ceb6d1d61cac3d5de80770d3dccb1f57d005c0c1cdf` unchanged. Official Alpha Hit unchanged at 61.0317%. Frozen ledger unchanged. P0/P1, Provider Health, Measurement Foundation, Recorder Health, and Evidence-Stance Retry Fix all intact. No threshold, taxonomy, B1/B2/B4, or Provider changes. No Alpha-specific hardcode anywhere. **Production files changed: 2** (`comqutor_alpha/structure_engine/factor_normalizer.py`, `comqutor_alpha/structure_engine/relation_grammar.py`). **Test files changed: 1** (new). **Provider calls: 0. TradingAgents calls: 0. Ticker runs: 0. Commits: 0. Pushes: 0. Destructive git operations: 0.**
