# v0.1.3 QQQ/SNDK Clean-Gold Recovery + Phase-2 Discrepancy Audit

Offline / read-only. **Provider calls: 0. TradingAgents calls: 0. Ticker runs: 0. HEAD unchanged (`9f228723fad5406c72e62beca67ec70ea0fdb004`). No commit. No push.**

## John — Clean-Gold Recovery Decision

```
Ticker  Alpha  Gold Quality      Real Root Cause                          Recoverability      Action
QQQ     A101   SUPPORTED_GOLD    R1 Research coverage gap (0 Primary      LOW_CONFIDENCE      defer
                                  QQQ-aggregate claims exist)
SNDK    A103   STRONG_GOLD       R13 Expected conservative -- no real     EXPECTED_CONSERV.   do not target
                                  omitted edge/fact found
SNDK    A301   STRONG_GOLD       R13 Expected conservative -- edge is     EXPECTED_CONSERV.   do not target
                                  correctly-excluded CONFLICTING type
TSM     A301   (structure track) Provider-timeout artifact (NOT the      FRESH_RUN_          no code change;
                                  locality-qualification issue assumed)   VALIDATION_REQUIRED  await healthy rerun
MSFT    A304   (structure track) Regex-capable + negation-aware          DESIGN_NOT_READY    scope a design
                                  extraction required; simple phrase                          task (NEXT_D)
                                  matching demonstrably unsafe

Current:                          61.03%
Phase-2 theoretical (verified):   74.13%
With clean QQQ/SNDK candidates:   70.48% (added to CURRENT baseline, not Phase-2)
Extended (Phase-2 + clean, all):  83.57%  PROJECTION_ONLY -- not a result
Credible >=75% path:              NO (NO_CREDIBLE_PATH_TO_75_YET)
Next step:                        NEXT_D -- MSFT negation-aware structure extraction design
```

## Executive Summary

```
QQQ clean Gold misses:            1  (A101)
SNDK clean Gold misses:           2  (A103, A301)

Clean misses HIGH recoverability:      0
MEDIUM:                                0
LOW:                                   1  (QQQ A101)
Expected conservative:                 2  (SNDK A103, SNDK A301)
Product-model gaps:                    0

TSM A301 reconciled root cause: LLM provider-timeout artifact orphaned a
  deterministically-strong A301 claim -- NOT the S6 locality-qualification
  issue the prior audit assumed for its "high-confidence" rating.

MSFT A304 reconciled root cause: extraction blind spot confirmed, but a
  safe generalizable fix requires regex-capable + negation-aware matching
  that does not exist today -- not a simple phrase alias.

Current official Alpha Hit:        61.0317%
Prior Phase-2 projected max:       74.1270%  (re-verified exact)
Extended projected max:            83.5714%  (Phase-2 + all 3 clean, PROJECTION_ONLY)
Credible path to >=75%:            NO

Recommended next engineering direction: NEXT_D (MSFT negation-aware
  structure extraction design)

Gold unchanged: YES.  Code changes: 0.  Provider calls: 0.  Ticker runs: 0.
```

## Verified Clean-Gold Target Set

| Ticker | Alpha | Gold Validity Class | Detected Level | Hit/Miss | System-Fix Eligible |
|---|---|---|---|---|---|
| QQQ | A101 | SUPPORTED_GOLD | candidate | MISS | YES |
| QQQ | A103 | SUPPORTED_GOLD | active | HIT | n/a |
| QQQ | A201 | REVIEW_CANDIDATE | candidate | MISS | NO (excluded) |
| QQQ | A301 | REVIEW_CANDIDATE | candidate | MISS | NO (excluded) |
| QQQ | A304 | SUPPORTED_GOLD | active | HIT | n/a |
| QQQ | A601 | SUPPORTED_GOLD | active | HIT | n/a |
| SNDK | A102 | REVIEW_CANDIDATE | candidate | MISS | NO (excluded) |
| SNDK | A103 | STRONG_GOLD | candidate | MISS | YES |
| SNDK | A201 | SUPPORTED_GOLD | dominant | HIT | n/a |
| SNDK | A301 | STRONG_GOLD | candidate | MISS | YES |
| SNDK | A601 | STRONG_GOLD | active | HIT | n/a |

**QQQ_CLEAN_MISSES = [A101]. SNDK_CLEAN_MISSES = [A103, A301].** Exactly matches the prior audits' implied target set — no discrepancy in target-set membership (the discrepancies found are in TSM A301's and MSFT A304's *root causes*, not in which Alphas qualify as clean misses).

## QQQ A101

Current: score 32.2068, candidate, 1 unique qualifying fact, 1 distinct agent (bull_researcher), 1/1 ticker-specific. Full funnel traced: 4 raw claims discuss QQQ/AI exposure, **zero from any Primary Research agent** — all 4 are Secondary (bull_researcher ×2, conservative_risk_analyst, portfolio_manager). Only 1 of 4 (the one literally saying **"QQQ's core holdings"**) is ticker-specific; the other 3 name individual constituents (Intel/AMD/Marvell) without naming QQQ, correctly excluded as `SECONDARY_NOT_TICKER_SPECIFIC`.

**Root cause: R1 RESEARCH_COVERAGE_GAP** (dominant), with R6 as a downstream consequence, not an independent defect. **Answer to the A–G question: G, dominated by A** — zero Primary-sourced, QQQ-aggregate-level AI-exposure content exists; the ETF-ownership boundary (B) is confirmed correct, unmodified, intended behavior (individual constituent mentions correctly do not become direct QQQ evidence) — not a gap. The one claim that DOES qualify proves the existing, unmodified ticker-specificity mechanism already works correctly for genuine aggregate-index framing; **no new ETF entity model is required** to recover via more such evidence.

**Counterfactual** (exact formula, no invented weights): +1 new legitimate Primary QQQ-aggregate fact → **39.41** (still short). +2 → **46.62** (still short — local_structure_support stays at 0 throughout). **Recoverability: LOW_CONFIDENCE_RECOVERABLE.**

## SNDK A103

**Re-verified from scratch against the current P0/P1 baseline** — the persisted `structure_graph.json` (39.0305) is the *stale, pre-P0/P1* value; the true current score (offline replay with the patched scorer) is **42.3638** (ticker-specific evidence 1→3, P1's effect). The prior audit's "~49.03" figure was **always a hypothetical** under a separate, never-implemented "Option B" design — not a historical score, and not something P0/P1 (which never touches `local_structure_support`) was ever meant to deliver. No contradiction, but an important clarification.

Traced the one incident structure edge (`ai_demand→sndk_revenue_growth`, alpha_ids include A103): its two underlying claims are **correctly** excluded — one has `relation="mention"` (not `activation`, fails canonical eligibility regardless of matched_alpha), the other is matched to A201, not A103 at all. **No real omitted qualifying fact/edge exists.**

**Section 12 answer: NO.** → **Classification: R13 EXPECTED_CONSERVATIVE_BEHAVIOR.** No threshold, rounding, epsilon, or arbitrary-credit remedy is proposed. **Recoverability: EXPECTED_CONSERVATIVE** (evidence-side counterfactual with a hypothetical new fact comes close to 50 but is unconfirmed and FRESH_RUN_DEPENDENT — not implementable now).

## SNDK A301

Current: score 36.9042, candidate. Traced all A301-tagged edges: the ONE incident edge is `valuation_risk→sndk_revenue_growth`, **`edge_type="conflicting"`** — an opposing/risk-vs-growth relationship, not supportive. `EDGE_CONTRIBUTIONS` has no entry for `"conflicting"` at any assertion status (contributes exactly 0.0 by design), and its 4 underlying claims are all valuation-risk-framed debate commentary, not genuine revenue-growth support. **The existing code already correctly excludes this edge** — exactly per Section 13's own instruction not to count an opposing edge as positive support. **No legitimate omitted structure edge exists.**

**Classification: R13 EXPECTED_CONSERVATIVE_BEHAVIOR.** Counterfactual: +1/+2 new independent Primary facts → 43.59 / 45.47 (both still short of 50). **Recoverability: EXPECTED_CONSERVATIVE.**

## Discrepancy A — TSM A301

**Old diagnosis**: structure/locality starvation (S6), high-confidence recovery candidate. **New verified diagnosis**: traced the full artifact lineage (research → claims → Mapper output → structure extraction → Provider execution metadata → persisted fallback → activation score). **Confirmed: YES, there was an actual provider timeout.** Exact component: Alpha Mapper's Pure-LLM Semantic Authority (`alpha_classifier` task, Week2 LLM Gateway). Exact status: `match_status='unavailable'`, `alpha_match_fallback_reason='provider_timeout'` for claim `fundamental_agent:claim:42` ("TSM has delivered two consecutive years of >30% revenue growth... driven by the AI infrastructure buildout") — despite the **deterministic** layer independently, correctly scoring it a clean, eligible A301 match (`deterministic_top_alpha='A301'`, score 0.7596). Corroborated by `error_logs/week2_llm_errors.jsonl`: **128 total LLM errors in this run, 47 specifically `alpha_classifier` failures**, with real timestamps — this run experienced substantial Week2 Gateway instability.

The old S6 diagnosis is not *wrong* — it correctly describes a real, different, genuinely non-ticker-specific edge (`neutral_risk_analyst:claim:28`) — but it never surfaced claim:42's provider-timeout, the actual higher-value, more decisive blocker. **Classification: OLD_DIAGNOSIS_PARTIAL_DOWNSTREAM_SYMPTOM.**

**Future validation status: FRESH_RUN_VALIDATION_REQUIRED.** A healthy future run may naturally recover A301 with **zero code change** — the deterministic layer already sees this correctly; only the original run's infrastructure hiccup blocked it. No production structure change is proposed. Offline counterfactual if claim:42 had committed: local structure raw 0→~50 (contribution +10.0), projected score **≈54.77** — but this is contingent on a future LLM call succeeding, not achievable today.

## Discrepancy B — MSFT A304

Old audit: claim:82 is `PRIMARY_QUALIFIED`/eligible/`factor_score=1.0`, an explicit causal statement, absent from `extracted_structures.json`; recommended recognizing causal-language patterns. **Extraction language audit**: "trigger"/"triggers"/"triggering" are **already** recognized `FORWARD_CAUSAL_VERB`s — the causal-verb layer is not the gap. **"slowdown" has no `FACTOR_ALIASES` entry anywhere.** `structure_extractor.py::_extract_edges()` requires ≥2 factors to form any edge; claim:82 produces only one (Valuation Risk). **Classification: CONCEPT_NORMALIZATION_GAP compounded by TOKENIZATION_GAP** (the relevant words appear in non-adjacent order — "slowdown in Azure growth" — which literal-phrase matching cannot represent).

**Negation-aware requirement**: positive fixture ("Any slowdown in Azure growth could trigger multiple compression") vs. negative fixture ("This is not a slowdown scenario") — both real, both must be handled. Minimum safe design: a clause-scoped negation detector + a non-adjacent-phrase-aware source-concept matcher (regex/token-window) + the already-sufficient causal-verb detector, all three together. **Design only, no implementation.**

**Fix readiness: DESIGN_NOT_READY.** A narrow deterministic grammar cannot yet distinguish positive causal / negative causal / negated premise / negated consequence / risk-only-descriptive — this is explicitly not a simple phrase alias.

## Mathematical Path to 75%

Current macro-average (verified): **61.0317%**. Prior Phase-2 projection (re-verified exact): **74.1270%**.

| Scenario (added to CURRENT baseline) | New macro % |
|---|---:|
| + QQQ A101 only | 63.8095 |
| + SNDK A103 only | 64.3651 |
| + SNDK A301 only | 64.3651 |
| + SNDK A103 and A301 | 67.6984 |
| + all three (QQQ A101, SNDK A103, SNDK A301) | 70.4762 |
| Extended: Phase-2 (5 targets) + all 3 clean (8 total conversions) | **83.5714** (PROJECTION_ONLY) |

### Three numbers, kept separate
- **A. CURRENT_OFFICIAL**: 61.0317%
- **B. PRIOR_PHASE2_PROJECTION**: 74.1270%
- **C. EXTENDED_PROJECTION** (Phase-2 + clean QQQ/SNDK): 83.5714% — **projection only, not a result**

### Minimum legitimate path
Proved 4 conversions cannot reach 75% (max achievable ≈73.25% using the two heaviest available plus two medium ones). **Minimum is 5 conversions**: SNDK A103 + SNDK A301 + QQQ A101 + MSFT A304 + TSM A301 → **76.0318%**. But every single one of these 5 is `FRESH_RUN_DEPENDENT` or `DESIGN_DEPENDENT` — **zero `OFFLINE_PROVEN` conversions exist**. Per the task's own explicit rule: **NO_CREDIBLE_PATH_TO_75_YET**, even though a mathematically sufficient combination exists.

## Clean-Gold Diagnostic Recheck

Frozen STRONG+SUPPORTED hit rate: **66.35%** (re-derived exactly: macro-average of NVDA 5/7, QQQ 3/4, MSFT 3/5, SNDK 2/4, TSM 3/4, AMD 4/6 = 66.3492%). Impact of recoveries (diagnostic only, does not replace the official v1 gate): QQQ A101 alone → 70.52%; either SNDK recovery alone → 70.52%; both SNDK → 74.68%; all three → **78.85%**.

## Priority Recommendation

**NEXT_D — MSFT negation-aware structure extraction design.** Weighed against correctness, recoverability, blast radius, Gold strength, and ability to prove improvement (not score gain alone): NEXT_A (Provider research) is Provider-facing and uncertain; NEXT_B (QQQ ETF model) has low leverage per the counterfactual; **NEXT_C (SNDK structure recovery) is a dead end** — no legitimate omission was found for either SNDK target; NEXT_E (TSM fresh run) is a single non-deterministic retry with no generalizable value. NEXT_D is the only track addressing a demonstrated, **code-side**, **offline-replayable** correctness gap whose underlying pattern recurs across 4 of 6 tickers — real value beyond the single MSFT A304 hit, and testable without any Provider dependency.

---

## Final Validation

Gold v1 / Gold Validity SHA-256: unchanged. No Gold v2. No code or test files changed. P0/P1 untouched (CLOSED PASS intact). No thresholds/taxonomy/B1/B2/B4/Alpha-Hit-semantics changes.

**Provider calls: 0. TradingAgents calls: 0. Ticker runs: 0. No commit. No push. No destructive git operations.**
