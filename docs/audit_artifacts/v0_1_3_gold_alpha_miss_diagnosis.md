# v0.1.3 Gold Alpha Hit Miss Diagnosis

Offline / read-only diagnosis only. **No fix applied. Gold v1 unmodified. Provider calls: 0. TradingAgents calls: 0. No ticker run. No production code changed.**

## John — Why Alpha Hit Is 61.03%

```
61.03% vs 75.00% target
Gap: 13.97 percentage points

14 Gold misses (out of 37 expected)

A True Recall Defect:        0
B Evidence Starvation:       7
C Structure Starvation:      7
D Gating/Design Bottleneck:  0
E Gold Review flags:         2   (NOT a system failure)

Top 3 root causes:
1. Local structure support scores 0 on 7 of 14 misses -- real evidence exists,
   but zero qualifying graph edges were extracted for these Alpha/ticker pairs.
2. Evidence is genuinely thin (low unique/ticker-specific facts, few agents)
   on the other 7 misses -- conservative gating working as documented.
3. Two misses (NVDA A102, SNDK A102 -- both 'Inference Explosion') show a
   total evidence vacuum where the Gold expectation itself may be miscalibrated
   for these tickers -- flagged for future benchmark review, not a system bug.

Minimum legitimate additional hits to reach 75%: 5 (out of 14 possible)
```

## Executive Summary

- **Expected Alpha Hit: 61.03%** (independently reproduced exactly, macro-average across tickers)
- **Target: >=75%**
- **Gap: 13.97 percentage points**
- Gold expected: **37** · Detected: **23** · Missed: **14**

**System Primary Causes** (mutually exclusive, sum to 14):
- A Recall Defect: **0**
- B Evidence Starvation: **7**
- C Structure Starvation: **7**
- D Gating/Design Bottleneck: **0**

**Gold Review Candidates** (a flag, not a system-cause bucket):
- E: **2** (NVDA A102, SNDK A102)

## Why We Missed 75%

The shortfall is an even 50/50 split between two distinct pipeline stages, not one dominant failure. Seven misses fail purely on **evidence strength** -- the activation formula's evidence_quality/agent_independence/ticker_specificity components are genuinely low because the underlying run generated little on-thesis content for those Alpha/ticker pairs (conservative gating behaving exactly as documented). The other seven fail purely on **local structure support** -- a 20%-weighted scoring component that is zero in every one of those cases even though the same claims show healthy evidence volume (in several cases, 20+ raw supporting claims) -- the structure-extraction layer produced zero qualifying local graph edges for these specific Alpha/ticker pairs, worth investigating further (flagged DESIGN_REVIEW_NEEDED, not called a defect, since no evidence contradicts documented intended behavior). Two misses (both the same Alpha, 'Inference Explosion', on NVDA and SNDK) show essentially zero relevant evidence at all and are flagged as Gold Benchmark review candidates rather than system failures. **No qualification ceiling ever actually bound** (cap_was_binding=false in all 14 cases) and **zero misses are at capped_active** -- gating/design ceilings are not a contributing cause at all.

---

## Reconfirmation of the Hit Contract

Authority: `comqutor_alpha/regression/regression_report_v3.py::_detected_alphas()` — unchanged, reused exactly. A hit requires final level in `{active, dominant, regime_level}`; `candidate`, `capped_active` (status label), `blocked`, `ambiguous`, `unavailable` never count.

| Ticker | Hits/Expected | Hit Rate |
|---|---:|---:|
| NVDA | 5/7 = 71.43% | |
| QQQ | 3/6 = 50.00% | |
| MSFT | 3/6 = 50.00% | |
| SNDK | 2/5 = 40.00% | |
| TSM | 5/6 = 83.33% | |
| AMD | 5/7 = 71.43% | |

**Reproduced macro-average: 61.0317%** — matches the prior reported 61.03% exactly. **No discrepancy found.**

## Miss Diagnosis Table

| Ticker | Gold Alpha | Final Level | Score | Ticker-Specific Ev. | Unique Ev. | Distinct Agents | Local Edges | Qualifying Edges | Ceiling | Reason Codes | Primary | Secondary | Gold Flag | Diagnosis |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|---|
| NVDA | A102 | candidate | 0.00 | 0 | 0 | 0 | 1 | 0 | None | NO_QUALIFYING_EVIDENCE | B | — | E (review) | see below |
| NVDA | A201 | candidate | 18.58 | 0 | 2 | 1 | 0 | 0 | 60.0 | NO_TICKER_SPECIFIC_EVIDENCE, INSUFFICIENT_AGENT_INDEPENDENCE, NO_LOCAL_STRUCTURE_SUPPORT | B | C | — | see below |
| QQQ | A101 | candidate | 32.21 | 1 | 1 | 1 | 0 | 0 | 60.0 | INSUFFICIENT_UNIQUE_EVIDENCE, INSUFFICIENT_AGENT_INDEPENDENCE, NO_LOCAL_STRUCTURE_SUPPORT | B | C | — | see below |
| QQQ | A201 | candidate | 46.23 | 2 | 5 | 3 | 0 | 0 | 70.0 | NO_LOCAL_STRUCTURE_SUPPORT | C | — | — | see below |
| QQQ | A301 | candidate | 37.78 | 0 | 3 | 3 | 2 | 0 | 60.0 | NO_TICKER_SPECIFIC_EVIDENCE, NO_LOCAL_STRUCTURE_SUPPORT | C | B | — | see below |
| MSFT | A102 | candidate | 34.97 | 0 | 1 | 1 | 2 | 1 | 60.0 | INSUFFICIENT_UNIQUE_EVIDENCE, NO_TICKER_SPECIFIC_EVIDENCE, INSUFFICIENT_AGENT_INDEPENDENCE | B | — | — | see below |
| MSFT | A304 | candidate | 43.36 | 5 | 14 | 4 | 0 | 0 | 70.0 | NO_LOCAL_STRUCTURE_SUPPORT | C | — | — | see below |
| MSFT | A601 | candidate | 32.76 | 1 | 8 | 2 | 0 | 0 | 70.0 | NO_LOCAL_STRUCTURE_SUPPORT | C | — | — | see below |
| SNDK | A102 | candidate | 0.00 | 0 | 0 | 0 | 0 | 0 | None | NO_QUALIFYING_EVIDENCE | B | — | E (review) | see below |
| SNDK | A103 | candidate | 39.03 | 1 | 6 | 2 | 1 | 0 | 70.0 | NO_LOCAL_STRUCTURE_SUPPORT | C | — | — | see below |
| SNDK | A301 | candidate | 36.90 | 1 | 10 | 2 | 1 | 0 | 70.0 | NO_LOCAL_STRUCTURE_SUPPORT | C | — | — | see below |
| TSM | A301 | candidate | 44.77 | 1 | 13 | 2 | 1 | 0 | 70.0 | NO_LOCAL_STRUCTURE_SUPPORT | C | — | — | see below |
| AMD | A102 | candidate | 35.63 | 0 | 1 | 1 | 1 | 1 | 60.0 | INSUFFICIENT_UNIQUE_EVIDENCE, NO_TICKER_SPECIFIC_EVIDENCE, INSUFFICIENT_AGENT_INDEPENDENCE | B | — | — | see below |
| AMD | A201 | candidate | 25.73 | 0 | 5 | 2 | 1 | 0 | 60.0 | NO_TICKER_SPECIFIC_EVIDENCE, NO_LOCAL_STRUCTURE_SUPPORT | B | C | — | see below |

### Per-miss causal diagnosis (not reason-code dumping)

**NVDA A102 (Inference Explosion)** — primary=**B**, judgment=**GOLD_REVIEW_NEEDED**, priority=**P4**
> Total evidence vacuum: score=0 across every component. The only claims the deterministic mapper ever attached to A102 (6 claims) are bear/competitive-threat content about custom ASICs eroding NVDA's inference dominance -- not assertions that inference demand is exploding in NVDA's favor. Evidence-stance qualification correctly rejected all of them, yielding 0 supporting claims. Not a mapper recall failure (mapper did engage, 614 candidate-scoring attempts); the underlying content genuinely doesn't support this specific bullish thesis this period.
> Counterfactuals — evidence alone: **NO (all components are 0; even full local structure credit (+20) only reaches score=20, still far below 50)**; structure alone: **NO**; ceiling removed: N/A (no ceiling ever engaged, cap_was_binding=false); capped_active counted: N/A (status=candidate, not capped_active)

**NVDA A201 (Semiconductor Supercycle)** — primary=**B**, secondary=C, judgment=**EXPECTED_CONSERVATIVE_BEHAVIOR**, priority=**P3**
> Score 18.58, gap 31.42pp to threshold -- evidence is thin on every axis (2 raw claims, 1 distinct agent, 0 ticker-specific), driving evidence_quality raw to just 1.18/100 (contribution 0.41 of a possible 35). Local structure is also 0 (contribution 0 of possible 20). Evidence weakness dominates: even full local-structure credit (+20) only reaches 38.58, still short of 50 -- evidence_quality is the larger, binding lever.
> Counterfactuals — evidence alone: **YES (raising evidence_quality to a realistic mid-range, e.g. raw>=55, adds ~19pts, crossing 50 even without structure)**; structure alone: **NO (+20 max only reaches 38.58)**; ceiling removed: N/A (cap not binding); capped_active counted: N/A

**QQQ A101 (AI Expansion)** — primary=**B**, secondary=C, judgment=**EXPECTED_CONSERVATIVE_BEHAVIOR**, priority=**P3**
> Score 32.21, gap 17.79pp. Reason codes flag both INSUFFICIENT_UNIQUE_EVIDENCE and INSUFFICIENT_AGENT_INDEPENDENCE (unique_evidence=1, distinct_agents=1) plus NO_LOCAL_STRUCTURE_SUPPORT. Evidence-side qualification codes (2) outnumber the structure code (1) and evidence_quality raw is very low (7.26/100). Structure alone (+20) would reach 52.21 and cross, but evidence thinness is the more comprehensively documented root condition.
> Counterfactuals — evidence alone: **YES (raising evidence_quality materially would cross 50 without touching structure)**; structure alone: **YES (+20 -> 52.21, crosses by a narrow 2.21pp margin)**; ceiling removed: N/A; capped_active counted: N/A

**QQQ A201 (Semiconductor Supercycle)** — primary=**C**, judgment=**DESIGN_REVIEW_NEEDED**, priority=**P2**
> Score 46.23, gap only 3.77pp -- the closest near-miss besides TSM A301. Every evidence-side qualification code is ABSENT (no NO_TICKER_SPECIFIC_EVIDENCE, no INSUFFICIENT_UNIQUE_EVIDENCE, no INSUFFICIENT_AGENT_INDEPENDENCE) -- evidence_quality(40.27), agent_independence(70.0), and ticker_specificity(40.0) all pass their own checks. The SOLE cap_reason_code is NO_LOCAL_STRUCTURE_SUPPORT (local_structure raw=0, contribution 0 of a possible 20) -- a lever more than 5x larger than the remaining gap. This is the cleanest structure-only miss in the set: qualification passed everywhere except structure, and structure alone would clear the threshold with room to spare.
> Counterfactuals — evidence alone: **NO (evidence already passes its own checks; improving it further isn't the binding lever)**; structure alone: **YES (+20 -> 66.23, crosses easily)**; ceiling removed: N/A (cap not binding, eligible_cap=70 was never reached); capped_active counted: N/A

**QQQ A301 (Revenue Expansion)** — primary=**C**, secondary=B, judgment=**DESIGN_REVIEW_NEEDED**, priority=**P2**
> Score 37.78, gap 12.22pp. Two reason codes: NO_TICKER_SPECIFIC_EVIDENCE (ticker_specific=0, contribution 0 of possible 10) and NO_LOCAL_STRUCTURE_SUPPORT (contribution 0 of possible 20). Ticker-specificity alone (+10 max) reaches only 47.78, still short; local-structure alone (+20 max) reaches 57.78, crossing comfortably -- structure is the larger, sufficient-alone lever, so it is primary; ticker-specificity gap is real but insufficient by itself.
> Counterfactuals — evidence alone: **NO (ticker-specificity alone maxes at +10, insufficient)**; structure alone: **YES (+20 -> 57.78, crosses)**; ceiling removed: N/A; capped_active counted: N/A

**MSFT A102 (Inference Explosion)** — primary=**B**, judgment=**EXPECTED_CONSERVATIVE_BEHAVIOR**, priority=**P3**
> Score 34.97, gap 15.03pp. THREE evidence-side codes fire (INSUFFICIENT_UNIQUE_EVIDENCE, NO_TICKER_SPECIFIC_EVIDENCE, INSUFFICIENT_AGENT_INDEPENDENCE) -- unique_evidence=1, ticker_specific=0, distinct_agents=1. Notably, local_structure_support is NOT flagged as failing here (raw=50.0, contributing 10 of possible 20) -- structure is half-present. Evidence thinness across three independent axes is unambiguously the binding cause.
> Counterfactuals — evidence alone: **YES (evidence_quality raw is only 15.15/100; a realistic improvement crosses 50 without touching structure, which is already half-credited)**; structure alone: **NO (already at half credit; the remaining +10 max alone reaches only 44.97, short)**; ceiling removed: N/A; capped_active counted: N/A

**MSFT A304 (Multiple Compression)** — primary=**C**, judgment=**DESIGN_REVIEW_NEEDED**, priority=**P2**
> Score 43.36, gap 6.64pp. Sole cap_reason_code is NO_LOCAL_STRUCTURE_SUPPORT. Evidence is genuinely healthy: 39 raw supporting claims, 14 unique facts, 5 ticker-specific, 4 distinct agents -- none of the evidence-side qualification codes fire. Local structure contributes 0 of a possible 20, more than 3x the remaining gap. A ticker with this much real evidence volume failing purely on the structure-extraction step is a clean design-attention case.
> Counterfactuals — evidence alone: **NO (evidence already qualifies; more of it isn't the lever)**; structure alone: **YES (+20 -> 63.36, crosses)**; ceiling removed: N/A; capped_active counted: N/A

**MSFT A601 (Narrative Momentum)** — primary=**C**, judgment=**DESIGN_REVIEW_NEEDED**, priority=**P2**
> Score 32.76, gap 17.24pp -- close to the full +20 structure ceiling, a tighter margin than MSFT A304. Sole cap_reason_code is NO_LOCAL_STRUCTURE_SUPPORT; no evidence-side code fires despite ticker_specific being only 1 (evidently above whatever minimum the NO_TICKER_SPECIFIC_EVIDENCE check requires). 21 raw claims / 8 unique facts / 2 distinct agents is moderate but adequate by the system's own qualification logic. Structure is still the documented sole blocker, though the margin is tighter than other structure-only cases.
> Counterfactuals — evidence alone: **UNKNOWN (evidence already passes its own checks, but the gap (17.24) is close to structure's max (20) -- a partial evidence improvement combined with structure could also close it; pure structure alone is the only single-lever fix confirmed sufficient)**; structure alone: **YES (+20 -> 52.76, crosses narrowly)**; ceiling removed: N/A; capped_active counted: N/A

**SNDK A102 (Inference Explosion)** — primary=**B**, judgment=**GOLD_REVIEW_NEEDED**, priority=**P4**
> Total evidence vacuum, identical pattern to NVDA A102: score=0 across every component, 0 matched claims, 0 of 819 candidate-scoring attempts ever eligible. SNDK is a NAND/storage manufacturer, not a compute/inference chip vendor -- 'Inference Explosion' is a conceptually more indirect thesis for this ticker than for NVDA/AMD. No mapper recall failure; there is essentially no generated content this period asserting SNDK-specific inference-demand exposure.
> Counterfactuals — evidence alone: **NO (all components 0; structure alone would only reach 20)**; structure alone: **NO**; ceiling removed: N/A; capped_active counted: N/A

**SNDK A103 (AI Infrastructure)** — primary=**C**, judgment=**DESIGN_REVIEW_NEEDED**, priority=**P2**
> Score 39.03, gap 10.97pp. Sole cap_reason_code is NO_LOCAL_STRUCTURE_SUPPORT; evidence is moderate (13 raw claims, 6 unique, 2 agents, evidence_quality raw=37.23) and passes its own checks. Independently cross-checked against the high-value unclassified recovery audit (v0_1_3): its ONE borderline candidate across the entire fresh six-run set is this exact ticker/alpha (SNDK A103) -- a bear rebuttal comparing SNDK to NVDA's AI moat, judged comparative/meta-argumentative rather than a first-person ticker-specific claim, and explicitly NOT actioned as a recovery. This independently confirms the miss is not a hidden mapper recall defect.
> Counterfactuals — evidence alone: **NO (evidence already qualifies)**; structure alone: **YES (+20 -> 59.03, crosses)**; ceiling removed: N/A; capped_active counted: N/A

**SNDK A301 (Revenue Expansion)** — primary=**C**, judgment=**DESIGN_REVIEW_NEEDED**, priority=**P2**
> Score 36.90, gap 13.10pp. Sole cap_reason_code is NO_LOCAL_STRUCTURE_SUPPORT; evidence is the strongest-volume case among SNDK's misses (23 raw claims, 10 unique, evidence_quality raw=34.26) yet still structure-blocked. Local structure contributes 0 of a possible 20, comfortably larger than the gap.
> Counterfactuals — evidence alone: **NO**; structure alone: **YES (+20 -> 56.90, crosses)**; ceiling removed: N/A; capped_active counted: N/A

**TSM A301 (Revenue Expansion)** — primary=**C**, judgment=**DESIGN_REVIEW_NEEDED**, priority=**P1**
> Score 44.77, gap only 5.23pp -- the single closest miss in the entire set. Evidence is the strongest of any missed Alpha (evidence_quality raw=56.56, the highest among all 14 misses; 23 raw claims, 13 unique facts). Sole cap_reason_code is NO_LOCAL_STRUCTURE_SUPPORT, contributing 0 of a possible 20 -- nearly 4x the remaining gap. This is the highest-payoff case to investigate further: strong, qualifying evidence exists, yet the structure-extraction layer produced zero qualifying local edges (exclusion reasons: LINEAGE_UNRESOLVED, NO_COMMITTED_ALPHA_MATCH, RELATION_OR_ASSERTION_NOT_QUALIFYING).
> Counterfactuals — evidence alone: **NO (evidence already strong and passing; not the lever)**; structure alone: **YES (+20 -> 64.77, crosses with room to spare)**; ceiling removed: N/A; capped_active counted: N/A

**AMD A102 (Inference Explosion)** — primary=**B**, judgment=**EXPECTED_CONSERVATIVE_BEHAVIOR**, priority=**P3**
> Score 35.63, gap 14.37pp. Three evidence-side codes fire (INSUFFICIENT_UNIQUE_EVIDENCE, NO_TICKER_SPECIFIC_EVIDENCE, INSUFFICIENT_AGENT_INDEPENDENCE) -- unique_evidence=1, ticker_specific=0, distinct_agents=1, despite local_structure already contributing 8 of a possible 20 (not flagged as failing). Evidence thinness is the clear, multiply-documented binding cause.
> Counterfactuals — evidence alone: **YES (evidence_quality raw is only 22.76/100; realistic improvement crosses 50)**; structure alone: **NO (remaining +12 max reaches only 47.63, short)**; ceiling removed: N/A; capped_active counted: N/A

**AMD A201 (Semiconductor Supercycle)** — primary=**B**, secondary=C, judgment=**EXPECTED_CONSERVATIVE_BEHAVIOR**, priority=**P3**
> Score 25.73, gap 24.27pp -- the second-largest gap among all misses. evidence_quality raw is catastrophically low (4.0/100, contribution 1.4 of a possible 35) despite 5 raw claims; ticker_specific=0. Local structure is also 0. Evidence weakness dominates by a wide margin: even full structure credit (+20) only reaches 45.73, still short of 50.
> Counterfactuals — evidence alone: **YES (evidence_quality raw at even a moderate 50 would add ~16pts, crossing 50 without structure)**; structure alone: **NO (+20 max only reaches 45.73)**; ceiling removed: N/A; capped_active counted: N/A

---

## Aggregate Causes

| Cause | Count | % of 14 misses |
|---|---:|---:|
| A — True Recall Defect | 0 | 0.0% |
| B — Evidence Starvation | 7 | 50.0% |
| C — Structure Starvation | 7 | 50.0% |
| D — Gating/Design Bottleneck | 0 | 0.0% |

**Gold Review Flags (separate from the above, not mutually exclusive with B/C):** E = 2 (14.29% of misses) — NVDA A102, SNDK A102.

**Why D = 0:** cap_was_binding=false for all 14 misses (verified directly from each run's alpha_activations.json) -- the qualification_ceiling never actually clipped a higher raw score down in any case. Every miss fails purely because its own uncapped score never reached the 50-point ACTIVE_THRESHOLD; the ceiling mechanism was never the operative constraint. No miss has status=capped_active. Gating/ceiling design is therefore not implicated in any of the 14 misses.

**Why A = 0:** Every missed Gold Alpha shows alpha_recognized_by_mapper_at_all=true (the Alpha Mapper generated deterministic candidate_scores entries for each, ranging from 25 to 819 scoring attempts per case). None show the mapper failing to engage with the Alpha at all. Where mapper engagement produced zero qualifying evidence (NVDA A102, SNDK A102), direct inspection of the underlying claims showed they were genuinely off-thesis (competitive-risk commentary, not the Alpha's actual bullish mechanism) or simply absent -- not a case of relevant on-thesis evidence existing but being missed.

## Behavior Judgment Counts

| Judgment | Count |
|---|---:|
| DEFECT | 0 |
| EXPECTED_CONSERVATIVE_BEHAVIOR | 5 |
| DESIGN_REVIEW_NEEDED | 7 |
| GOLD_REVIEW_NEEDED | 2 |
| INSUFFICIENT_DATA | 0 |

## Per-Ticker Breakdown

**NVDA** — Gold expected: 7, hits: 5, misses: 2, missed: A102, A201, primary-cause distribution: {'B': 2}
**QQQ** — Gold expected: 6, hits: 3, misses: 3, missed: A101, A201, A301, primary-cause distribution: {'B': 1, 'C': 2}
**MSFT** — Gold expected: 6, hits: 3, misses: 3, missed: A102, A304, A601, primary-cause distribution: {'B': 1, 'C': 2}
**SNDK** — Gold expected: 5, hits: 2, misses: 3, missed: A102, A103, A301, primary-cause distribution: {'B': 1, 'C': 2}
**TSM** — Gold expected: 6, hits: 5, misses: 1, missed: A301, primary-cause distribution: {'C': 1}
**AMD** — Gold expected: 7, hits: 5, misses: 2, missed: A102, A201, primary-cause distribution: {'B': 2}

### Which ticker(s) contribute most, and why

SNDK contributes most in relative terms (40.00% hit rate, lowest of the six) because its 5-Alpha Gold set has the smallest denominator, so each of its 3 misses (60% of its own expected set) carries the largest single-ticker weight in the macro-average (each SNDK conversion is worth 1/5 = 3.33pp of the aggregate, the largest of any ticker). Structurally, SNDK's misses are dominated by NO_LOCAL_STRUCTURE_SUPPORT (2 of 3) plus one genuine evidence vacuum (A102) that also carries a Gold-review flag, since 'Inference Explosion' is a conceptually less direct thesis for a NAND/storage manufacturer than for a compute/inference chip vendor. QQQ and MSFT tie for the next-largest contribution (50.00% each) -- QQQ's misses split between evidence thinness (A101) and structure-only gaps (A201, A301); MSFT's split between evidence thinness (A102, three codes) and structure-only gaps (A304, A601), both A304 and A601 backed by substantial evidence volume that nonetheless produced zero qualifying local edges. TSM contributes least (83.33%, only 1 miss) and that single miss (A301) is the closest near-hit in the entire set (score 44.77, only 5.23pp from threshold, with the strongest evidence_quality of any missed Alpha) -- purely structure-blocked.

## Quantifying Why 61.03% Misses 75%

Current macro-average = **61.03%**, target = **75.0%**, gap = **13.97pp**.

Marginal macro-average impact of converting ONE miss to a hit, per ticker (denominators differ):

| Ticker | Fraction | Contribution to macro-average |
|---|---|---:|
| NVDA | 1/7 | 2.381pp |
| QQQ | 1/6 | 2.778pp |
| MSFT | 1/6 | 2.778pp |
| SNDK | 1/5 | 3.333pp |
| TSM | 1/6 | 2.778pp |
| AMD | 1/7 | 2.381pp |

**Minimum additional legitimate hits required to reach >=75%: 5** (out of 14 possible). 4 conversions maximum possible improvement = 3xSNDK(3.333) + 1x(2.778) = 12.778pp < 13.97pp gap (insufficient). 5 conversions can reach >=75% via multiple combinations.

**61 distinct ticker-distribution combinations** of exactly 5 conversions reach >=75%. Examples:
- {'SNDK': 2, 'TSM': 1, 'AMD': 2} -> 75.24%
- {'SNDK': 3, 'AMD': 2} -> 75.79%
- {'QQQ': 1, 'MSFT': 1, 'SNDK': 3} -> 76.59%

*Diagnostic mathematics only — no recommendation is made to convert any specific miss merely to reach the threshold.*

## Counterfactual Aggregate Impact (no double counting)

- All B (Evidence Starvation) recovered: **7 misses** -> hypothetical macro-average **79.44%**
- All C (Structure Starvation) recovered: **7 misses** -> hypothetical macro-average **81.59%**

Full recovery of either the B (evidence starvation) or C (structure starvation) bucket alone would independently exceed the 75% target -- the failure is not concentrated in one single mechanism; both evidence acquisition and local-structure extraction contribute roughly equally (7 misses each) to the shortfall. No double counting: A/B/C/D partitions are mutually exclusive by construction (each miss has exactly one primary cause).

## Capped_active Check

Gold misses currently at `capped_active`: **0**. Hypothetical macro-average if `capped_active` counted as a hit: **61.03%** (unchanged — no miss is in that state). No miss has status=capped_active (verified directly from alpha_activations.json for all 14). Counting capped_active as a hit would therefore make NO difference to the current result -- this is a non-factor in the current 61.03% shortfall, though the diagnostic question was verified rather than assumed.

## High-Value Unclassified Recovery Cross-Check

Cross-referenced the existing recovery audit (200 candidates, individually reviewed, 0 strong + 1 borderline) against all 14 missed Gold Alphas. **3 matches found; 0 credible true recall defects.**

| Ticker | Alpha | Recovery Audit Verdict | Implication |
|---|---|---|---|
| SNDK | A103 | BORDERLINE_RECOVERY_CANDIDATE | Confirms SNDK A103's miss is not a hidden true-recall defect; independently supports its C (structure starvation) classification. |
| QQQ | A101 | CORRECT_NONE | Confirms no additional qualifying evidence was missed by the mapper for QQQ A101; supports its B classification. |
| MSFT | A102 | CORRECT_NONE | Confirms no additional qualifying evidence was missed for MSFT A102; supports its B classification. |

No hidden recoverable evidence was found for any missed Gold Alpha. This is consistent with A=0 across the diagnosis and with the recovery audit's own prior conclusion (0 strong recoveries across the entire fresh six-run set).

## Entity Exposure Note

Entity Exposure reason codes present on the missed Alphas (EXPOSURE_BELOW_REGIME_THRESHOLD, EXPOSURE_BELOW_DOMINANT_THRESHOLD, EXPOSURE_SEED_MISSING) all govern eligibility for the DOMINANT/REGIME_LEVEL tiers specifically -- none of them affect the basic ACTIVE_THRESHOLD (50) gate that every one of these 14 misses actually fails at. Entity Exposure is therefore not a contributing cause to any of the 14 misses.

## Priority Table

| Priority | Ticker | Alpha | Cause | Judgment | Potential Legitimate Hit Improvement | Recommended Next Investigation |
|---|---|---|---|---|---|---|
| P1 | TSM | A301 | C | DESIGN_REVIEW_NEEDED | Closest miss (5.23pp gap) with the strongest evidence_quality of any missed Alpha (raw=56.56) -- highest payoff-per-effort to investigate. | Inspect why the structure-extraction step produced zero qualifying local edges (LINEAGE_UNRESOLVED, NO_COMMITTED_ALPHA_MATCH, RELATION_OR_ASSERTION_NOT_QUALIFYING) despite 23 raw / 13 unique supporting claims. |
| P2 | QQQ | A201 | C | DESIGN_REVIEW_NEEDED | Cleanest structure-only miss -- every evidence-side qualification code passes; only structure fails, gap is small (3.77pp) relative to structure's 20pt weight. | Same structure-extraction review as above, applied to this ticker/Alpha pair. |
| P2 | MSFT | A304 | C | DESIGN_REVIEW_NEEDED | 39 raw supporting claims yet 0 qualifying local edges -- high evidence volume, zero structural credit. | Same structure-extraction review. |
| P2 | SNDK | A103 | C | DESIGN_REVIEW_NEEDED | Independently cross-checked against the recovery audit (borderline, not actioned) -- confirms structure, not recall, is binding. | Same structure-extraction review. |
| P2 | SNDK | A301 | C | DESIGN_REVIEW_NEEDED | Highest evidence volume among SNDK's misses (23 raw claims) yet zero qualifying edges. | Same structure-extraction review. |
| P2 | MSFT | A601 | C | DESIGN_REVIEW_NEEDED | Structure-only miss with a tighter margin (17.24pp vs 20pt max) than other C cases. | Same structure-extraction review; verify margin is genuinely achievable via structure alone. |
| P2 | QQQ | A301 | C | DESIGN_REVIEW_NEEDED | Structure is the larger, sufficient-alone lever versus the smaller ticker-specificity gap also present. | Same structure-extraction review. |
| P3 | NVDA | A201 | B | EXPECTED_CONSERVATIVE_BEHAVIOR | Evidence-quality is the dominant lever (raw 1.18/100); large gap (31.42pp), not a near-miss. | None recommended -- conservative gating behaving as documented on thin evidence. |
| P3 | QQQ | A101 | B | EXPECTED_CONSERVATIVE_BEHAVIOR | Both evidence and structure absent; evidence more comprehensively flagged. | None recommended. |
| P3 | MSFT | A102 | B | EXPECTED_CONSERVATIVE_BEHAVIOR | Three independent evidence-side codes fire; structure already half-credited. | None recommended. |
| P3 | AMD | A102 | B | EXPECTED_CONSERVATIVE_BEHAVIOR | Three independent evidence-side codes fire; structure already partially credited. | None recommended. |
| P3 | AMD | A201 | B | EXPECTED_CONSERVATIVE_BEHAVIOR | Second-largest gap in the set (24.27pp); evidence_quality raw catastrophically low (4.0/100). | None recommended. |
| P4 | NVDA | A102 | B | GOLD_REVIEW_NEEDED | Total evidence vacuum; only related content is bear/competitive-threat commentary, not the Alpha's actual bullish mechanism. | Future independent review of whether 'Inference Explosion' materiality was correctly assumed for NVDA this period -- NOT a system fix. |
| P4 | SNDK | A102 | B | GOLD_REVIEW_NEEDED | Total evidence vacuum; SNDK is a storage/NAND maker, a conceptually less direct fit for an inference-compute thesis than NVDA/AMD. | Future independent review of whether this Gold expectation is well-calibrated for SNDK's business model -- NOT a system fix, and would require alpha_conflict_gold.v2 if ever revised. |

*No threshold relaxation is recommended anywhere in this table merely to raise the hit rate.*

---

**Gold benchmark SHA-256 unchanged throughout this analysis:** `99b1cd0247637054de360c3b5c0c00c7d8052152f3db1d29045eae1850bd8e9a`

**Provider calls: 0. TradingAgents calls: 0. No ticker run. No production code changed. Gold v1 not modified.**
