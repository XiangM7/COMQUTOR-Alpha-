# v0.1.3 A102 + Cross-Company Evidence Integrity Audit

Offline only. **Provider calls: 0. TradingAgents calls: 0. Ticker runs: 0. No production code, test, threshold, taxonomy, or Gold file changed.**

## Executive Summary

```
A102 legitimate targets:              NVDA / MSFT / AMD
A102 Gold-review negative control:    SNDK (true evidence vacuum, not a system-fix target)

Cross-company contamination confirmed:  1 case  (AMD A201, Silicon Motion/SanDisk)
Company-name false-negative cases:      60 candidates -- 39 CLEAR_FALSE_NEGATIVE (in final evidence,
                                         zero ticker-specificity credit), 21 AMBIGUOUS (excluded for
                                         other reasons)
Shared entity root cause:               PARTIALLY (same weak-entity-model theme, two independent
                                         pipeline-stage mechanisms -- see below)

P0 integrity defects:      1  (AMD A201 evidence-ownership contamination)
P1 implementation defects: 1  (company_names=() -- no producer anywhere in the codebase)
P2 research coverage gaps: 2  (NVDA A102, AMD A102)
P3 semantic design gaps:   1  (AMD A102 predicate-vocabulary + clause co-location, secondary)
ETF product-model gaps:    1  (QQQ -- ETF_ENTITY_MODEL_GAP=YES)

Recommended first implementation target: P0 -- the AMD A201 evidence-ownership contamination.
Correctness before score recovery.
```

## John — A102 and Evidence Ownership Integrity

```
Issue                    Finding                                              Severity  Next Action
NVDA A102                8 'inference' claims, all competitive-threat framed  P2        research coverage
MSFT A102                company_names=() blocks a claim literally saying     P1        wire entity registry
                         "Microsoft" -- code-verified, 44.97 after fix (still short of 50)
AMD A102                 0/8 MI-series claims truly A102-eligible; closest    P2/P3     research + narrow
                         miss blocked by missing 'ramp' predicate + clause    (mixed)   predicate fix
                         boundary
AMD A201 contamination   Silicon Motion/SanDisk claim (zero AMD relationship) P0        ownership veto on
                         counted as AMD evidence via Alpha-Mapper LLM path              Alpha Mapper LLM path
company_names=()         Never populated at the ONLY production call site;   P1        static registry +
                         6/6 runs affected; 39 confirmed false-negative                 wire into pipeline.py
                         claims across 5/6 tickers
QQQ ETF ownership        No single company name can represent an index;      P4        separate design,
                         kept out of scope here                                        not unified with P1

Cross-company contamination confirmed:   1
Ticker-specific false negatives confirmed: 39 (of 60 candidates)
Does one shared fix solve everything:    NO
Highest-priority correctness issue:      AMD A201's Silicon Motion/SanDisk contamination (P0) --
                                          evidence assigned to companies with zero relationship to AMD
```

No code changed.

---

## A102 Semantic Contract

Reconstructed from `comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml` and the canonical AI hard gate in `comqutor_alpha/structure_engine/ai_alpha_discriminator.py`:

- **A101 AI Expansion**: broad AI training/adoption/capex/accelerator demand. Anchor groups: training, accelerator, investment, adoption.
- **A102 Inference Explosion**: enterprise AI application / inference-workload-specific demand. One flat anchor group: inference, inference workload/demand/request/traffic/capacity, model/serving workload, token generation/volume, AI agent(s), enterprise AI usage.
- **A103 AI Infrastructure**: physical buildout (datacenter, server, networking, power, cooling), locative-preposition-excluded.

Each of A101/A102/A103 requires an alpha-specific anchor phrase **co-located in the same clause** as a recognized change predicate (increase, rise, grow, expand, accelerate, double, ramp is **notably absent**, etc.) — generic AI/cloud/capex terms alone never grant admission.

| Example | Classification |
|---|---|
| "AI demand is growing" | A101 only |
| "Microsoft is increasing AI capex" | A101/A103, NOT automatically A102 |
| "inference token volume doubled" | Strongly A102 |
| "MI-series demand is increasing" | Ambiguous — accelerator anchor (A101), no inference workload named |
| "AI accelerator demand increased because inference workloads expanded" | Both A101 and A102 can independently pass (no exclusion rule between them except one narrow A101-adoption-suppression case) |

---

## NVDA A102 Trace

8 "inference"-mentioning claims exist in NVDA's raw corpus — **zero** are bullish/supportive. All are competitive-threat framed (custom ASICs from Google/Amazon/Microsoft eroding NVDA's inference dominance). 6 are classified `relation=mention` (correctly rejected — no NVDA-specific asserted change); 2 reach `relation=activation` but fail the AI hard gate outright. **First broken stage: B1 stance/relation classification — correctly rejecting genuinely non-supportive content.** Root cause: **A102-N1 QUERY_COVERAGE_GAP** — the real, externally-confirmed bullish "tokens=inference explosion" narrative (Jensen Huang) was never surfaced by NVDA's research agents in this run. **Recoverability: MEDIUM** (research-coverage improvement only).

## MSFT A102 Trace

**company_names Production Audit**: The only production call site (`comqutor_alpha/graph_engine/pipeline.py:183`) never passes `company_names` to `score_alpha_activations_v2` — confirmed by direct grep showing zero occurrences in the file. It silently defaults to `()`. An exhaustive search found **no ticker-to-company-name registry anywhere in the codebase** — this is not merely an unwired argument; no producer of this data exists at all. Classification: **MISSING_METADATA_PROPAGATION**. **6/6 runs** use this same call site with the same missing parameter.

**Blast Radius (all six runs)**: Scanning every matched claim for "ticker symbol absent, company name present" found **60 candidates**, of which **39 are CLEAR_FALSE_NEGATIVE** (already part of an alpha's final qualifying evidence, contributing zero ticker-specificity credit) across MSFT(14), SNDK(9), TSM(7), NVDA(8), AMD(1). MSFT A102 is **not an isolated incident** — it is one instance of a systemic 5-of-6-ticker defect.

**Full Counterfactual**: Ticker-specificity-only fix: 34.9674 → 44.9674 (still short by 5.03). Remaining blocker: `INSUFFICIENT_UNIQUE_EVIDENCE` + `INSUFFICIENT_AGENT_INDEPENDENCE` — only ONE independent qualifying Primary fact exists (the one Secondary duplicate is correctly deduped). Using the exact documented formula constants (`EVIDENCE_QUALITY_SATURATION=4.0`, `AGENT_COVERAGE_DENOMINATOR=3`, shares 0.70/0.30): **with company_names fixed PLUS one comparable-quality new independent Primary A102 fact, the score reaches ≈54.93 — crossing 50.** Two conditions, not one; the second fact does not currently exist in this run's corpus. **Recoverability: MEDIUM.**

## AMD A102 Trace

Directly re-ran the deterministic AI hard gate (`evaluate_ai_alpha_gates`) against all 8 real MI-series claims. **0 of 8 are genuinely A102-gate-eligible.** Closest near-miss: `fundamental_agent:claim:82` ("...AMD's Instinct MI300/MI400 series AI accelerators are ramping rapidly, competing with NVIDIA in the AI training/inference market"). Code-verified: the claim splits into 3 clauses; "inference" appears in clause 3 (predicate: "competing" — not in the vocabulary); "ramping" appears in clause 2 (no inference anchor there). **"ramp"/"ramping" is itself absent from `POSITIVE_PREDICATES`** — verified directly (an equivalent sentence using "accelerating" instead passes). Even fixing that vocabulary gap would not flip this specific claim, since the anchor and predicate sit in different clauses. **Correction to the prior audit**: this is not a deliberate "reject bundled claims" rule — the gate would admit a claim asserting both A101 and A102 in the same sentence. The real mechanism is a predicate-vocabulary gap plus clause-boundary separation. **Root cause: MIXED** (primary: research gap — no claim ever isolates inference from the bundled training/inference framing; secondary: semantic gate gap). **Recoverability: MEDIUM.**

## SNDK Negative Control

Score 0.0, 0 raw supporting claims out of 819 candidate-scoring attempts — a **true evidence vacuum**, not a qualification/entity problem. No design option in this audit (Entity A/B/C, A102 Option A/B) can activate SNDK A102, because no claim content exists to newly qualify. **SNDK_A102_FALSE_POSITIVE_RISK = LOW for every option proposed.** SNDK A102 remains a v1 Gold miss and stays out of scope as a system-recovery target.

## company_names Production Audit

See MSFT A102 Trace above. Summary: **6/6 runs affected**; classification **MISSING_METADATA_PROPAGATION** (no upstream producer exists, not merely an unwired argument).

## Cross-Company Contamination Scan

Scanned every claim contributing to any alpha's final activation score across all six runs (750+ total matches) for mentions of ~19 known peer/competitor/supplier companies.

| Class | Count | Description |
|---|---:|---|
| C1 CLEAR_CROSS_COMPANY_CONTAMINATION | 1 | AMD A201 Silicon Motion/SanDisk — see case study below |
| C2 POSSIBLE_RELATIONAL_EVIDENCE | 39 | Competitor/peer references explicitly tied back to the run ticker |
| C3 SECTOR_CONTEXT_CORRECTLY_NON_TICKER_SPECIFIC | 8 | Legitimate sector background, correctly excluded from ticker-specific credit |
| C4 MULTI_COMPANY_CLAIM_AMBIGUOUS | 0 | None found — all multi-company claims resolved into C2 or C5 |
| C5 ETF_CONSTITUENT_CASE | 7 | QQQ's named constituents (Intel, AMD, Marvell) — legitimate, not contamination |

**Only 1 of 750+ evidence-contributing claims across the entire six-run corpus is genuine contamination.**

## Entity Ownership Matrix

| Class | Count |
|---|---:|
| A. False positive (foreign evidence counted for ticker) | 1 |
| B. False negative (company name present, empty company_names blocks credit) | 39 |
| C. Legitimate relational evidence | 39 |
| D. Generic sector evidence, correctly non-ticker-specific | 8 |

**Bias conclusion: the entity/ticker-specificity layer is biased toward false negatives (39) far more than false positives (1) — the two are not symmetric and do not share one mechanical cause.**

## AMD A201 Case Study

Claim `news_agent:news_report:claim:43`: *"Memory/storage: Silicon Motion up 186% in a year on NAND strength; SanDisk soaring on S&P 100 inclusion."* Zero AMD relationship, unrelated sub-sector (NAND memory vs. AMD's CPU/GPU business). **First incorrect decision: Alpha Mapping's Pure-LLM Semantic Authority classifier** (`alpha_mapper.py::_classify_alpha_with_llm`) independently selected `matched_alpha='A201'`, **overriding** the deterministic layer's correct rejection (`eligible_candidates=[]`, `deterministic_match_status='no_match'`). The LLM's classification prompt has no requirement that a claim be substantively about the run's own ticker — only that the selected Alpha ID be a member of the canonical taxonomy. The claim IS correctly marked non-ticker-specific downstream, but still counts toward `evidence_count`, `agent_independence`, and `direction_consistency` since none of those components check entity ownership.

## ETF Special Case

QQQ's real economic exposure is inherently expressed via named constituents (Intel, AMD, Marvell), not the ticker "QQQ" itself. No single company-name string can represent an index. **ETF_ENTITY_MODEL_GAP = YES.** Kept as a separate P4 product-model gap, not unified with the single-company entity fix.

## Design Options

**Entity/ticker-specificity** (3 options; full comparison in JSON): **Option A** (static ticker→company-name registry, wired into `pipeline.py`) is preferred — lowest risk, zero Primary/Secondary/B1 impact, LOW SNDK false-positive risk. It does **not** fix AMD's contamination; a separate, narrowly-scoped ownership veto (a minimal slice of Option C) is recommended as an independent second fix.

**A102 semantic coverage** (3 options): Option A (research/query coverage) is the primary lever for NVDA and AMD. A narrowly-scoped Option B (add "ramp"/"ramping" to the predicate vocabulary, no co-location relaxation) is a secondary, SNDK-regression-tested improvement for AMD. **Option C (relaxed co-location) is NOT recommended** — HIGH SNDK false-positive risk, violates the task's own stop conditions.

**Can one safe fix solve NVDA + MSFT + AMD A102? NO** — three independently-verified, non-overlapping mechanisms (research/stance gap; entity-ownership + evidence-thinness; predicate-vocabulary + clause-boundary gap).

## Counterfactual Impact

- **MSFT A102**: company_names fix + one new comparable-quality Primary fact → **≈54.93, crosses 50** (formula-exact, two conditions required, second does not yet exist).
- **AMD A201 contamination removed**: score **25.7333 → 21.0667** (a genuine 4.67-point **decrease**; agent_independence loses its only news_agent corroboration). No Alpha Hit or level change (miss before and after). Correctness prioritized over score, reported honestly.
- **NVDA/AMD A102**: minimum-facts-needed is UNKNOWN precise (no invented weights) — both require net-new research content that doesn't currently exist.
- **Diagnostic path-to-75%**: this audit adds at most one additional plausible (not yet real) conversion beyond prior audits' findings. Does not change the standing conclusion that 75% is not yet reachable with fixes identified so far.

## Regression Risks (top 5)

1. An ownership veto scoped too broadly could suppress legitimate C2 relational evidence.
2. Predicate-vocabulary expansion is global (all six tickers' A101/A102/A103 gates) — requires full six-run regression, especially SNDK.
3. Company-name alias curation must stay to genuine legal/common names and clear product brands — never generic sector words.
4. Any Alpha-Mapping LLM-path change risks altering `matched_alpha` for many of the 750+ per-run claims beyond the ones examined here — requires rerunning the full existing regression suite (`item2_blind_holdout5`, `evidence_review_summary_v2`'s 200 rows).
5. QQQ's ETF-constituent handling (P4) must not be conflated with the single-company entity fix (P1) — forced unification risk.

## Recommended Implementation Order

**Phase 1** — Fix the P0 AMD A201 ownership contamination first (narrow veto on Alpha-Mapper `matched_alpha`). **Phase 2** — Wire `company_names` from a canonical static registry into `pipeline.py`. **Phase 3** — Offline blast-radius replay against all six runs' frozen artifacts (no ticker runs) to confirm predicted changes and zero SNDK A102 side-effect. **Phase 4** — Address A102 research/semantic gaps separately (Provider-facing changes need separate authorization). **Phase 5** — Run the full existing test suite plus historical regression artifacts. **Phase 6** — Only after explicit authorization, a fresh six-ticker production run.

---

## Final Validation

- Gold Benchmark v1 SHA-256: unchanged (`99b1cd0247637054de360c3b5c0c00c7d8052152f3db1d29045eae1850bd8e9a`)
- Gold Validity Judgment SHA-256: unchanged (`3643ea45168c029d7c2a2ceb6d1d61cac3d5de80770d3dccb1f57d005c0c1cdf`)
- No production code, test, threshold, taxonomy, B1/B2/B4, or Alpha Hit semantic changes
- SNDK A102 retained strictly as a negative control, never a recovery target
- Zero Provider calls, zero TradingAgents calls, zero ticker runs

**Provider calls: 0. TradingAgents calls: 0. No ticker run. No production code changed. No commit. No push.**
