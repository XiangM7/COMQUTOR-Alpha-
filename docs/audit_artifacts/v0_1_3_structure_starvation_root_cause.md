# v0.1.3 Structure Starvation Root-Cause Audit

Offline / read-only diagnosis only. **No fix applied. No code/test/threshold/taxonomy/Gold changes. Provider calls: 0. TradingAgents calls: 0. No ticker run.**

## John — Why Structure Support Failed

| Ticker | Alpha | Root Cause | Defect/Design/Expected | Recoverable? |
|---|---|---|---|---|
| QQQ | A201 | S5 | DESIGN_GAP | HIGH CONFIDENCE RECOVERABLE |
| QQQ | A301 | S6 | DESIGN_GAP | LOW CONFIDENCE |
| MSFT | A304 | S2 | DESIGN_GAP | MEDIUM CONFIDENCE RECOVERABLE |
| MSFT | A601 | S2 | DESIGN_GAP | LOW CONFIDENCE |
| SNDK | A103 | S6 | DESIGN_GAP | MEDIUM CONFIDENCE RECOVERABLE |
| SNDK | A301 | S6 | DESIGN_GAP | LOW CONFIDENCE |
| TSM | A301 | S6 | DESIGN_GAP | HIGH CONFIDENCE RECOVERABLE |

**Most common failure:** Locality Qualification Failure (S6, 4 of 7 cases) — a correctly-extracted, correctly alpha-tagged graph edge exists, but the specific claim that produced it independently fails a *separate*, stricter evidence qualification check used only for scoring — so the edge and the qualifying evidence pool never actually overlap.

**Highest-priority case:** TSM A301 — the closest miss in the entire diagnosis (5.23pp gap) with the strongest evidence of any missed Alpha, precisely traced to this exact mismatch.

**Can fixing structure alone plausibly move Alpha Hit from 61.03% to >=75%: UNCERTAIN** — only 4 of the 7 cases are confidently legitimate recoveries (72.70%, still short); reaching 75% needs at least 1 of the 3 harder cases to also resolve.

## Executive Summary

Cases audited: **7**

Primary root causes:
```
S1 Input handoff:               0
S2 Extraction recall:           2   (MSFT A304, MSFT A601)
S3 Node normalization:          0
S4 Edge semantic:               0
S5 Alpha-edge alignment:        1   (QQQ A201)
S6 Locality qualification:      4   (QQQ A301, SNDK A103, SNDK A301, TSM A301)
S7 Evidence not structural:     0
S8 Traceability gap:            0
```

Judgment:
```
Implementation Defect:          0
Design Gap:                     7
Expected Conservative:          0
Insufficient Traceability:      0
```

High-confidence recoverable: **2** (QQQ A201, TSM A301)
Medium-confidence recoverable: **2** (MSFT A304, SNDK A103)
Low-confidence: **3** (QQQ A301, MSFT A601, SNDK A301)

**Can structure-layer improvements alone plausibly close the 13.97pp Alpha Hit gap? UNCERTAIN**
- High-confidence only (2 conversions): 66.59% -- still short of 75%
- High+Medium (4 conversions): 72.70% -- still short of 75%, and 4 conversions is also short of the minimum 5 needed
- All 7 structure cases (7 conversions): 81.59% -- exceeds 75%, and 7 conversions exceeds the minimum 5 needed

The confidently-legitimate subset (2 HIGH + 2 MEDIUM = 4 conversions) falls short both of the 75% target (72.70%) and of the minimum 5 hits required. Reaching >=75% via structure fixes alone requires at least 1 of the 3 LOW-confidence cases (QQQ A301, MSFT A601, SNDK A301) to also legitimately resolve -- each of which requires more than a single qualifying edge or a different edge type/extraction than currently exists. This is not guaranteed by current data, hence UNCERTAIN rather than YES or NO.

## Reconfirmation: Are These Really Structure Cases?

All 7 confirmed as genuine Structure Starvation cases. **Misclassified: 0.** For each case verified: cap_was_binding=false (from alpha_activations.json); Gold expected=yes; Alpha Mapper produced candidate_scores for the alpha (25-819 attempts); local_structure_support component raw=0/contribution=0 in every case; final level=candidate, never active/dominant/regime_level.

*Note on QQQ A301:* QQQ A301 carries a secondary NO_TICKER_SPECIFIC_EVIDENCE code alongside NO_LOCAL_STRUCTURE_SUPPORT. Verified via component math that ticker-specificity alone (max +10) cannot cross the 12.22pp gap while structure alone (a single causal/asserted edge, +10 realistic) also falls short by 2.22pp -- structure remains the larger, still-necessary lever, so this case legitimately remains classified as Structure Starvation, not reclassified to Evidence Starvation, but the secondary factor is disclosed.

## Shared Root Cause

**SHARED_ROOT_CAUSE = YES**

The Structure Extractor / graph-builder's edge-to-alpha_ids attribution and the Alpha Mapper / Evidence-Source-Role qualification pipeline that feeds activation scoring are two INDEPENDENT classification passes over the same underlying claims, and they frequently disagree. comqutor_alpha/graph_engine/activation_scorer_v2.py::_local_structure_component() only credits an edge if its own source_claim_ids intersect the SAME claim_ids that independently survived the stricter, later evidence_source_role_v1 Primary/Secondary qualification (comqutor_alpha/graph_engine/evidence_source_role.py) used for evidence_quality/ticker_specificity scoring. An edge can be correctly alpha_ids-tagged, lineage-resolved, and asserted in structure_graph.json while the ONE claim that produced it is independently rejected as SECONDARY_NOT_TICKER_SPECIFIC (risk-debate/investment-debate rounds are classified SECONDARY_DECISION_OR_DEBATE and require their own ticker-specificity bar) or was never independently matched to that alpha by the Alpha Mapper's own claim-level candidate scoring at all (the graph builder's alpha_ids tagging appears to use a more liberal, node/relation-level semantic association than the Alpha Mapper's per-claim scoring). Only claims that satisfy BOTH systems simultaneously ever produce a qualifying local structure edge -- a double-gate that is rarely satisfied even when substantial, correctly-labeled evidence and edges exist.

**Affected cases:** QQQ A301, SNDK A103, SNDK A301, TSM A301

**Supporting evidence:** Directly traced 4 of 7 cases' sole/best candidate edge to a specific claim_id and confirmed via alpha_activations.json's evidence_fact_groups: TSM A301's and QQQ A301's edge-claims are tagged source_role=SECONDARY_DECISION_OR_DEBATE / activation_qualification_reason=SECONDARY_NOT_TICKER_SPECIFIC; SNDK A103's and SNDK A301's edge-claims are entirely ABSENT from evidence_fact_groups for those alphas (never independently Alpha-Mapper-attributed), despite the graph tagging the resulting edge with that exact alpha_id.

**Not covered by the shared cause:** QQQ A201 (S5, wrong-alpha attribution, not a qualification mismatch); MSFT A304 (S2, no edge extracted at all); MSFT A601 (S2, no edge extracted at all)

---

## Case-by-Case Diagnosis

| Ticker | Alpha | Final Level | Score | Evidence Strength | Local Edges | Qualifying Edges | First Broken Stage | Root Cause | Judgment | Recoverability |
|---|---|---|---:|---|---:|---:|---|---|---|---|
| QQQ | A201 | candidate | 46.23 | see diagnosis | 1-2 | 0 | S5 stage | S5 | DESIGN_GAP | HIGH CONFIDENCE RECOVERABLE |
| QQQ | A301 | candidate | 37.78 | see diagnosis | 1-2 | 0 | S6 stage | S6 | DESIGN_GAP | LOW CONFIDENCE |
| MSFT | A304 | candidate | 43.36 | see diagnosis | 0 | 0 | S2 stage | S2 | DESIGN_GAP | MEDIUM CONFIDENCE RECOVERABLE |
| MSFT | A601 | candidate | 32.76 | see diagnosis | 0 | 0 | S2 stage | S2 | DESIGN_GAP | LOW CONFIDENCE |
| SNDK | A103 | candidate | 39.03 | see diagnosis | 1-2 | 0 | S6 stage | S6 | DESIGN_GAP | MEDIUM CONFIDENCE RECOVERABLE |
| SNDK | A301 | candidate | 36.90 | see diagnosis | 1-2 | 0 | S6 stage | S6 | DESIGN_GAP | LOW CONFIDENCE |
| TSM | A301 | candidate | 44.77 | see diagnosis | 1-2 | 0 | S6 stage | S6 | DESIGN_GAP | HIGH CONFIDENCE RECOVERABLE |

### Full pipeline trace and diagnosis per case

#### QQQ A201 (Semiconductor Supercycle) — score 46.23, gap 3.77pp

| Stage | Status |
|---|---|
| Evidence Facts | PRESENT -- 5 raw supporting claims, evidence_quality raw=40.27 (moderate) |
| Alpha Mapping | PRESENT -- Alpha Mapper produced candidate_scores for A201 across 30 claims, 26 eligible |
| Structure Extraction Input | PRESENT -- extracted_structures.json contains 'ai_capex --causal--> semiconductor_cycle' (lineage=resolved) |
| Structure Nodes | PRESENT -- 'semiconductor_cycle' node exists |
| Structure Edges | PRESENT -- the edge survives into structure_graph.json unchanged |
| Alpha Edge Association | PRESENT BUT WRONG ALPHA -- edge is tagged alpha_ids=['A301'] only, never 'A201', despite the target node being literally named 'semiconductor_cycle' |
| Ticker Local Qualification | NOT_REACHED -- never evaluated for A201 since the edge isn't associated with A201 at all |
| Qualifying Activation Support Edge | ABSENT for A201 (qualifying_local_edge_count=0) |

**Root cause: S5**
**Judgment: DESIGN_GAP**

> The exact relation Gold's A201 thesis requires ('AI CapEx causally drives the Semiconductor Cycle') IS extracted, lineage-resolved, and asserted -- but the graph's alpha-linking step attributed it ONLY to A301 (Revenue Expansion), never to A201 (Semiconductor Supercycle), despite the target node being literally named 'semiconductor_cycle'. This is a clean alpha-edge misalignment, not missing evidence or extraction failure.

**Counterfactual (one qualifying edge, all else unchanged):** would cross 50 → **YES**. If this same existing edge (causal/asserted, contribution 1.00) were additionally attributed to A201, raw local-structure=50, +10.0 to score: 46.23+10.0=56.23, crossing 50 with 6.23pp to spare.
**Is missing structure currently a necessary blocker to promotion?** YES

**Recoverability: HIGH CONFIDENCE RECOVERABLE**

Citations: `outputs/runs/f88c8956-cb62-48aa-9951-89f8e8a95f83/extracted_structures.json`; `outputs/runs/f88c8956-cb62-48aa-9951-89f8e8a95f83/structure_graph.json (edge: ai_capex->semiconductor_cycle)`

---

#### QQQ A301 (Revenue Expansion) — score 37.78, gap 12.22pp

| Stage | Status |
|---|---|
| Evidence Facts | PRESENT -- 6 raw supporting claims, evidence_quality raw=25.07 (weak-moderate) |
| Alpha Mapping | PRESENT -- 36 candidate-scoring attempts, 26 eligible |
| Structure Extraction Input | PRESENT -- 'ai_capex --causal--> semiconductor_cycle' and 'valuation_risk --conflicting--> qqq_revenue_growth' both extracted |
| Structure Nodes | PRESENT |
| Structure Edges | PRESENT -- both edges survive into structure_graph.json, both alpha_ids-tagged including A301 |
| Alpha Edge Association | PRESENT -- correctly tagged alpha_ids includes 'A301' on both edges |
| Ticker Local Qualification | FAILED -- edge1's sole source_claim (risk_debate_state.aggressive_history:claim:13) is source_role=SECONDARY_DECISION_OR_DEBATE, activation_qualification_reason=SECONDARY_NOT_TICKER_SPECIFIC; edge2's 4 source_claims are ALL absent from A301's evidence_fact_groups entirely (never independently Alpha-Mapper-matched to A301) |
| Qualifying Activation Support Edge | ABSENT (qualifying_local_edge_count=0, exclusion reason RELATION_OR_ASSERTION_NOT_QUALIFYING) |

**Root cause: S6** (secondary: B (secondary evidence gap: ticker_specific_evidence_count=0))
**Judgment: DESIGN_GAP**

> Two edges ARE correctly alpha_ids-tagged to A301 and lineage-resolved, but their underlying claims independently fail the stricter Evidence-Source-Role qualification used for scoring (one is a SECONDARY debate-round claim judged not ticker-specific enough; the other three claims were never even matched to A301 by the Alpha Mapper's own per-claim scoring, despite the graph attributing the resulting edge to A301). This is the cross-system qualification mismatch shared with 3 other cases.

**Counterfactual (one qualifying edge, all else unchanged):** would cross 50 → **NO**. Requalifying the single causal/asserted edge alone (contribution 1.00, +10.0) reaches only 47.78, short by 2.22pp. Ticker-specificity alone (max +10) is also insufficient (47.78). Both together, or two qualifying edges, would be needed.
**Is missing structure currently a necessary blocker to promotion?** YES

**Recoverability: LOW CONFIDENCE**

Citations: `outputs/runs/f88c8956-cb62-48aa-9951-89f8e8a95f83/structure_graph.json`; `outputs/runs/f88c8956-cb62-48aa-9951-89f8e8a95f83/alpha_activations.json (evidence_fact_groups for A301)`

---

#### MSFT A304 (Multiple Compression) — score 43.36, gap 6.64pp

| Stage | Status |
|---|---|
| Evidence Facts | PRESENT -- 39 raw supporting claims, 14 unique, 5 ticker-specific, evidence_quality raw=32.17 |
| Alpha Mapping | PRESENT -- 141 candidate-scoring attempts, 22 eligible |
| Structure Extraction Input | ABSENT for this relation -- extracted_structures.json's only valuation-related node ('valuation_risk') appears solely in edges to 'rate_cut_cycle' (tagged A001), never to 'msft_revenue_growth' or any MSFT-outcome node |
| Structure Nodes | PARTIAL -- 'valuation_risk' node exists but is never connected to an MSFT outcome node |
| Structure Edges | ABSENT -- no edge connecting valuation/multiple-compression content to an MSFT outcome node exists anywhere in extracted_structures.json or structure_graph.json |
| Alpha Edge Association | NOT_APPLICABLE -- no candidate edge exists to associate |
| Ticker Local Qualification | NOT_REACHED |
| Qualifying Activation Support Edge | ABSENT (qualifying_local_edge_count=0, incident_graph_edge_count=0) |

**Root cause: S2**
**Judgment: DESIGN_GAP**

> Despite 39 raw supporting claims and 5 ticker-specific facts -- substantial real evidence about MSFT's valuation/multiple-compression risk -- the Structure Extractor never produced ANY edge connecting valuation-risk concepts to an MSFT outcome node. The only valuation-related node ('valuation_risk') is extracted solely in the context of macro rate-cut-cycle relations (tagged A001), not as a company-specific multiple-compression relation. This is a genuine extraction-recall gap, not a qualification or attribution failure -- the relation never reached the graph at all.

**Counterfactual (one qualifying edge, all else unchanged):** would cross 50 → **YES (hypothetical)**. If a single causal/asserted valuation_risk->msft_revenue_growth-type edge were extracted AND its claim passed qualification, raw=50, +10.0: 43.36+10.0=53.36, crossing with 3.36pp to spare. This is a larger hypothetical than the other cases since it requires new extraction, not just requalification of an existing edge.
**Is missing structure currently a necessary blocker to promotion?** YES

**Recoverability: MEDIUM CONFIDENCE RECOVERABLE**

Citations: `outputs/runs/43472ace-454f-4c69-892c-adca91c25be7/extracted_structures.json (12 raw edges, none MSFT-valuation-outcome)`; `outputs/runs/43472ace-454f-4c69-892c-adca91c25be7/structure_graph.json`

---

#### MSFT A601 (Narrative Momentum) — score 32.76, gap 17.24pp

| Stage | Status |
|---|---|
| Evidence Facts | PRESENT -- 21 raw supporting claims, 8 unique, evidence_quality raw=21.02 |
| Alpha Mapping | PRESENT -- 98 candidate-scoring attempts, 54 eligible |
| Structure Extraction Input | ABSENT -- extracted_structures.json contains no node or edge with any narrative/momentum/sentiment semantics for MSFT at all |
| Structure Nodes | ABSENT -- no narrative/momentum-type node exists |
| Structure Edges | ABSENT |
| Alpha Edge Association | NOT_APPLICABLE |
| Ticker Local Qualification | NOT_REACHED |
| Qualifying Activation Support Edge | ABSENT (qualifying_local_edge_count=0, incident_graph_edge_count=0) |

**Root cause: S2**
**Judgment: DESIGN_GAP**

> 21 raw claims exist discussing MSFT sentiment/momentum dynamics, but none were ever extracted into a structural node or edge at all -- narrative/momentum content appears to fall entirely outside what the Structure Extractor's relation-extraction rules currently represent as graph structure, as opposed to a qualification or attribution problem downstream. The gap (17.24pp) is also the largest among the structure-only cases relative to a single edge's maximum realistic contribution.

**Counterfactual (one qualifying edge, all else unchanged):** would cross 50 → **NO**. Even a hypothetical single causal/asserted edge (+10.0) only reaches 42.76, short by 7.24pp -- would need roughly two such edges' worth of structural credit, a larger and less certain recovery than the other cases.
**Is missing structure currently a necessary blocker to promotion?** YES

**Recoverability: LOW CONFIDENCE**

Citations: `outputs/runs/43472ace-454f-4c69-892c-adca91c25be7/extracted_structures.json (12 raw edges, none narrative/momentum-related)`

---

#### SNDK A103 (AI Infrastructure) — score 39.03, gap 10.97pp

| Stage | Status |
|---|---|
| Evidence Facts | PRESENT -- 13 raw supporting claims, 6 unique, evidence_quality raw=37.23 (moderate) |
| Alpha Mapping | PRESENT -- 698 candidate-scoring attempts, 5 eligible |
| Structure Extraction Input | PRESENT -- 'ai_demand --causal--> sndk_revenue_growth' extracted |
| Structure Nodes | PRESENT |
| Structure Edges | PRESENT -- survives into structure_graph.json, alpha_ids=['A103','A201'] |
| Alpha Edge Association | PRESENT -- correctly tagged A103 |
| Ticker Local Qualification | FAILED -- both of the edge's source_claim_ids (aggressive_risk_analyst and neutral_risk_analyst risk-debate claims) are entirely ABSENT from A103's evidence_fact_groups -- never independently matched to A103 by the Alpha Mapper's own claim scoring |
| Qualifying Activation Support Edge | ABSENT (RELATION_OR_ASSERTION_NOT_QUALIFYING). Independently cross-checked against docs/audit_artifacts/high_value_unclassified_recovery_report_v0.1.3_final.json -- its ONE borderline candidate across the entire fresh six-run set is this exact ticker/alpha (SNDK A103), judged comparative/meta-argumentative and NOT actioned, confirming no hidden recall defect. |

**Root cause: S6**
**Judgment: DESIGN_GAP**

> Same cross-system qualification mismatch as TSM A301/QQQ A301: a correctly alpha_ids-tagged, lineage-resolved edge exists, but neither of its two source claims (both risk-debate-round commentary) was ever independently matched to A103 by the Alpha Mapper's own scoring, so neither enters the qualifying claim pool the local-structure component requires.

**Counterfactual (one qualifying edge, all else unchanged):** would cross 50 → **NO (essentially a rounding-distance miss)**. The existing causal/asserted edge, if requalified, contributes +10.0: 39.03+10.0=49.03 -- short of 50 by only 0.97pp, the closest near-miss of any structure counterfactual in this set.
**Is missing structure currently a necessary blocker to promotion?** YES

**Recoverability: MEDIUM CONFIDENCE RECOVERABLE**

Citations: `outputs/runs/e8e0f398-7b26-4462-8135-a1410ea5b335/structure_graph.json`; `outputs/runs/e8e0f398-7b26-4462-8135-a1410ea5b335/alpha_activations.json (evidence_fact_groups for A103)`; `docs/audit_artifacts/high_value_unclassified_recovery_report_v0.1.3_final.json`

---

#### SNDK A301 (Revenue Expansion) — score 36.90, gap 13.10pp

| Stage | Status |
|---|---|
| Evidence Facts | PRESENT -- 23 raw supporting claims, 10 unique, evidence_quality raw=34.26 |
| Alpha Mapping | PRESENT -- 88 candidate-scoring attempts, 61 eligible |
| Structure Extraction Input | PRESENT -- 'valuation_risk --conflicting--> sndk_revenue_growth' extracted |
| Structure Nodes | PRESENT |
| Structure Edges | PRESENT -- survives into structure_graph.json, alpha_ids=['A201','A301'] |
| Alpha Edge Association | PRESENT BUT LOW-VALUE -- edge_type is 'conflicting' (an opposing/risk relation), and comqutor_alpha/graph_engine/activation_scorer_v2.py's EDGE_CONTRIBUTIONS table has NO entry for 'conflicting' edges at all (only causal/supportive score), so this edge contributes ZERO to local_structure_support regardless of claim qualification |
| Ticker Local Qualification | FAILED (moot) -- its 4 source claims are also all absent from A301's evidence_fact_groups, but even if they were present, the edge_type itself is excluded from scoring by design |
| Qualifying Activation Support Edge | ABSENT |

**Root cause: S6**
**Judgment: DESIGN_GAP**

> The only candidate edge is a 'conflicting'-type relation (valuation risk opposing revenue growth) -- a real, correctly-extracted relation, but one the local-structure-support formula never scores regardless of claim qualification, since only causal/supportive edge types carry a nonzero contribution weight. Its claims also independently fail the same cross-system qualification pattern as the other S6 cases. A genuinely different (causal or supportive) A301-linked edge would be needed, not merely requalification of this one.

**Counterfactual (one qualifying edge, all else unchanged):** would cross 50 → **NO**. Requalifying THIS specific edge changes nothing (contribution=0 by edge-type design). A hypothetical NEW causal/asserted A301 edge (+10.0) would reach 46.90, still short by 3.10pp -- would need more than one new qualifying edge of the right type.
**Is missing structure currently a necessary blocker to promotion?** YES

**Recoverability: LOW CONFIDENCE**

Citations: `outputs/runs/e8e0f398-7b26-4462-8135-a1410ea5b335/structure_graph.json`; `comqutor_alpha/graph_engine/activation_scorer_v2.py EDGE_CONTRIBUTIONS table`

---

#### TSM A301 (Revenue Expansion) — score 44.77, gap 5.23pp

| Stage | Status |
|---|---|
| Evidence Facts | PRESENT -- 23 raw supporting claims, 13 unique, evidence_quality raw=56.56 (the strongest of any missed Alpha in the full 14-miss diagnosis) |
| Alpha Mapping | PRESENT -- 70 candidate-scoring attempts, 45 eligible; 13 of 23 unique facts PRIMARY_QUALIFIED |
| Structure Extraction Input | PRESENT -- 'ai_demand --supportive--> tsm_revenue_growth' extracted (canonical relation, TradingAgents own output) |
| Structure Nodes | PRESENT |
| Structure Edges | PRESENT -- survives into structure_graph.json, lineage=resolved, alpha_ids=['A301'] |
| Alpha Edge Association | PRESENT -- correctly tagged A301, no alpha_link_reason_codes |
| Ticker Local Qualification | FAILED -- the edge's sole source claim (neutral_risk_analyst:risk_debate_state.neutral_history:claim:28, 'The fundamentals are genuinely exceptional...') is source_role=SECONDARY_DECISION_OR_DEBATE, activation_qualification_reason=SECONDARY_NOT_TICKER_SPECIFIC, per evidence_qualification.qualification_reason_counts (13 PRIMARY_QUALIFIED, 10 SECONDARY_NOT_TICKER_SPECIFIC) |
| Qualifying Activation Support Edge | ABSENT (RELATION_OR_ASSERTION_NOT_QUALIFYING) -- none of the 13 PRIMARY_QUALIFIED claims independently produced their own graph edge linked to A301 |

**Root cause: S6**
**Judgment: DESIGN_GAP**

> This is the closest miss in the entire 14-case diagnosis (5.23pp gap) with the strongest evidence_quality of any missed Alpha. The pipeline trace shows exactly why: TSM's 23 raw claims split into 13 PRIMARY_QUALIFIED (feeding evidence_quality/ticker_specificity scoring) and 10 SECONDARY_NOT_TICKER_SPECIFIC (excluded from scoring) -- but the ONE claim that happened to independently produce a structural edge was drawn from the REJECTED 10, not the qualified 13. This is not extraction recall failure (the relation was cleanly extracted, lineage-resolved, and correctly alpha-tagged) and not evidence starvation (evidence_quality is strong) -- it is specifically that the claim generating the edge and the claims passing evidence qualification are disjoint sets for this Alpha.

**Counterfactual (one qualifying edge, all else unchanged):** would cross 50 → **YES**. Requalifying this exact supportive/asserted edge (contribution 0.80, +8.0): 44.77+8.0=52.77, crossing 50 with 2.77pp to spare.
**Is missing structure currently a necessary blocker to promotion?** YES

**Recoverability: HIGH CONFIDENCE RECOVERABLE**

Citations: `outputs/runs/dfc7ceb3-3584-4514-bd84-6c371aab3e95/structure_graph.json`; `outputs/runs/dfc7ceb3-3584-4514-bd84-6c371aab3e95/alpha_activations.json (evidence_qualification, evidence_fact_groups for A301)`

---

## Next-Step Categories (no patches written)

- investigate why the graph-builder's alpha_ids attribution for a node literally named 'semiconductor_cycle' excludes A201 (Semiconductor Supercycle) -- QQQ A201 case
- investigate whether risk-debate-round (SECONDARY_DECISION_OR_DEBATE) claims that produce a canonical-relation edge should be eligible to feed local-structure-support even when they fail the SECONDARY_NOT_TICKER_SPECIFIC bar used for evidence_quality -- affects QQQ A301, SNDK A103, TSM A301
- investigate why the graph builder attributes alpha_ids to an edge using claims the Alpha Mapper's own per-claim scoring never independently matched to that alpha -- affects SNDK A103, SNDK A301, and partially QQQ A301
- investigate extractor coverage for valuation/multiple-compression-type causal chains for MSFT (A304)
- investigate extractor coverage for narrative/momentum-type structural content generally (A601, MSFT case)
- investigate whether 'conflicting'-type edges should ever be alpha_ids-tagged to a bullish revenue Alpha at all, given they never score in local_structure_support by design -- SNDK A301 case
- no change recommended to Gold v1, thresholds, taxonomy, B1/B2/B4, or qualification ceilings

**Gold benchmark SHA-256 unchanged throughout this audit:** `99b1cd0247637054de360c3b5c0c00c7d8052152f3db1d29045eae1850bd8e9a`

**Provider calls: 0. TradingAgents calls: 0. No ticker run. No production code, test, threshold, taxonomy, or Gold changes.**
