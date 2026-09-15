# v0.1.3 S5/S2 Targeted Recovery Design Audit

Offline / read-only diagnosis and design only. **No code, test, threshold, taxonomy, or Gold changes. Provider calls: 0. TradingAgents calls: 0. No ticker run.**

## John — Targeted Path From 61.03% Toward 75%

| Case | Failure Type | Preferred Fix | Recoverable? | Risk |
|---|---|---|---|---|
| QQQ A201 | S5 + hidden S2 (dual gap) | Attribution fix + evidence fallback, or new extraction | UNCERTAIN | MEDIUM |
| MSFT A304 | S2 (clean extraction-recall gap) | Recognize existing causal pattern (Option A) | YES/UNCERTAIN (needs 1-2 edges) | MEDIUM |
| MSFT A601 | S2 (weak underlying content) | None safely recommended | NO/UNCERTAIN | — |
| TSM A301 | S6 (prior audit) | Already-designed Option B fallback | YES | LOW |
| SNDK A103 | S6 (prior audit) | Same Option B fallback | NO (falls 0.97pt short) | LOW |
| QQQ A301 | S6 (prior audit) | Same Option B fallback | NO (falls 2.22pt short) | LOW-MEDIUM |

```
Minimum additional hits needed:            5
Recoverable from S5 (QQQ A201):            UNCERTAIN
Recoverable from S2 (MSFT A304/A601):      1 UNCERTAIN, 1 unlikely
Recoverable from known near-miss (TSM):    1 confirmed (from prior audit)

Best credible realistic total:             3 conversions -> 69.37% (still short)
Additional B-side recovery likely needed:  YES (at least 2, more likely 3-4)
```

No code changed.

## Executive Summary

Current Alpha Hit: **61.0317%** · Target: **>=75%**

S5 cases: **1** (QQQ A201) · S2 cases: **2** (MSFT A304, MSFT A601)

Preferred S5 design: **Option B — additive secondary-alpha marking** (safest; does NOT by itself recover QQQ A201 — see dual-gap finding)

Preferred S2 design: **Option A — recognize existing causal-language patterns from PRIMARY_RESEARCH claims**

QQQ A201 recoverable: **UNCERTAIN** · MSFT A304 recoverable: **UNCERTAIN (medium confidence, needs 1-2 qualifying edges)** · MSFT A601 recoverable: **UNCERTAIN, leaning NO**

Can S5+S2 alone recover enough hits: **NO** (best credible scenario: 3 conversions, 69.37%, still short of both the 75% target and the minimum-5 conversion count)

Would additional B-side (Evidence Starvation) work still be required: **YES**

---

## S5 End-to-End Trace — QQQ A201

- Alpha IDs the Mapper considered for the lineage-anchor claim (claim:13): ['A001', 'A003', 'A101', 'A102', 'A103', 'A301']
- Was A201 present anywhere before graph attribution? NOT for the lineage-anchor claim (claim:13, 'Dell is up 300%...') -- A201 never appears in that claim's own candidate_scores at all. BUT A201 IS genuinely present elsewhere in the SAME evidentiary context: claim:10 ('you are ignoring the semiconductor resilience') and claim:62 ('...semiconductor complex...') from the SAME agent output (aggressive_risk_analyst risk-debate) both have matched_alpha=A201, and claim:62 is independently PRIMARY/SECONDARY-qualified (SECONDARY_QUALIFIED_CAUSAL_EVIDENCE, activation_eligible=True) for A201.
- Field with the full Alpha mapping: `candidate_scores (list, per-claim, each entry has alpha_id/eligible/evidence_stance) -- alpha_matches.json`
- Field with only the singular committed match: `matched_alpha (string, mutually exclusive across alphas) -- alpha_matches.json, requires match_status=='matched'`
- Why `_committed_alpha_ids_for_claim` chose A301 only: graph_builder.py::_committed_alpha_ids_for_claim() reads ONLY claim_info['matched_alpha'] for the ONE claim (claim:13) that lineage resolution happened to anchor the canonical relation to. That claim's own matched_alpha is A301 -- even though A301's own candidate_scores entry for THAT claim shows eligible=False, score=0.08, evidence_stance=neutral_background (i.e. even A301 is a weak/arbitrary pick for this specific claim, not a confident match).
- Lost to data-shape narrowing? **True** · Lost because only one committed Alpha retained? **True** · Lost to relation-compatibility rejection? **False**

**Proof:** Verified directly: (1) claim:13's candidate_scores contains 6 alphas, none is A201, confirming A201 was never even considered a candidate for THIS specific claim; (2) claim:10 and claim:62 in the SAME agent-output ARE matched_alpha=A201 and claim:62 is activation_eligible=True for A201; (3) NEITHER claim:10 nor claim:62 is the source_claim_id of any edge in structure_graph.json at all -- A201's own genuinely-qualifying evidence never produced its own structural edge either. This is a DUAL gap: (a) an S5 misattribution on the semiconductor_cycle edge (wrong lineage anchor claim), AND (b) a separate S2-like extraction-recall gap where A201's OWN best evidence (claim:62) never became any node/edge at all.

**Conclusion:** QQQ A201 is NOT a pure, single-mechanism S5 case as originally framed -- it requires BOTH a relation-compatible re-attribution fix (or better lineage resolution) AND separately extracting a new edge from claim:62 (or equivalent) to be fully recovered. A single-mechanism fix addresses only part of the gap.

## S5 Attribution Contract Evaluation

**A_singular_matched_alpha_only**: current behavior — INSUFFICIENT -- proven to lose real, independently-qualified Alpha associations (QQQ A201)

**B_all_mapper_candidate_alpha_ids**: attribute edge to every alpha with eligible=True on the lineage claim — UNSAFE -- blast radius audit (Section 5) found candidate_scores frequently marks multiple alphas eligible+supports_alpha on the SAME claim (24 such claims across six runs) where the underlying content only substantively supports ONE of them; blind adoption would create real false multi-Alpha attribution

**C_all_canonically_qualified_alpha_ids**: attribute edge to every alpha for which this claim is in qualified_claim_ids — SAFER than B (already passed Primary/Secondary+ticker-specific screening) but still risks attributing a structurally-generic edge to multiple alphas whose RELATION content the edge doesn't actually represent (e.g. a claim eligible for both A301 and A304 doesn't mean an edge built from it represents BOTH a revenue-expansion AND a multiple-compression relation)

**D_relation_compatible_subset_of_canonical_mapped_alpha_ids**: intersect the claim's canonically-qualified alpha set with an explicit, auditable relation-compatibility table keyed on the edge's source/target node semantics (e.g. a 'semiconductor_cycle' target node is compatible with A201; an edge whose target is a generic 'X_revenue_growth' node is compatible with A301 but not automatically A201) — SAFEST -- preserves relation compatibility explicitly, never blindly unions, bounded and auditable

**E_another_existing_authority**: e.g. re-run lineage resolution to prefer the claim with the HIGHEST matched_alpha confidence among all claims in the same canonical relation's supporting quote, rather than the first/only text-match found — COMPLEMENTARY, not a replacement -- improves WHICH claim anchors an edge, addressing the QQQ A201 dual-gap's first half (S5) but not attribution logic itself

**Recommended contract:** Combine D (relation-compatible subset, for attribution safety) with a bounded form of E (lineage resolution should prefer a canonically-qualified, higher-confidence claim over a weak/arbitrary one when multiple candidate claims exist in the same supporting quote) -- see Section 12 Option recommendation.

**Safety requirement confirmed:** A structure edge MUST NOT automatically inherit every Alpha candidate -- confirmed necessary by the Section 5 blast-radius data (0 of 7 audited multi-eligible-claim edges would be 'obviously correct' under a blind full-union rule).

## S5 Counterfactual — QQQ A201

- Local structural edges: 1 (the ai_capex->semiconductor_cycle edge, IF correctly re-attributed)
- Qualifying activation-support edges: UNKNOWN -- depends on whether the edge's OWN claim (claim:13, weak/arbitrary for any alpha) would also need to pass A201's qualified_claim_ids intersection (current rule) or benefit from the Section-prior 'Option B' alpha-level fallback (A201 DOES have a non-empty qualified pool: 5 members including claim:62). Under the prior audit's recommended Option B fallback, this edge (causal/asserted, contribution 1.00) WOULD qualify.
- Activation score: 46.2329 (current) + 10.0 (causal/asserted, raw=50, contribution 1.00) = 56.23 IF the Option B fallback also applies
- Qualification ceiling changes: No -- eligible_cap remains 70.0, not binding either before or after (uncapped_score never approaches it)
- Final level: candidate -> active, IF both the S5 re-attribution AND the Option B evidence-fallback are applied together
- Official Alpha Hit: YES, but ONLY under a COMBINED fix (S5 attribution repair + the previously-designed Option B fallback) -- attribution repair ALONE, without also addressing whether claim:13 itself ever qualifies, leaves the eligibility question open, since claim:13 is NOT independently qualified for A201 (it isn't even a candidate).

**Would a single repair be sufficient? UNCERTAIN -- explicitly NOT a confident YES. S5 attribution repair alone re-labels the edge as 'for A201' but does not by itself make claim:13 canonically qualifying evidence for A201 (it never was). Recovery requires EITHER (a) pairing the S5 fix with the already-designed Option B alpha-level fallback (since A201 independently has a non-empty qualified pool via claim:62), OR (b) separately extracting a new edge from claim:62 itself (a distinct S2-like fix). Neither is 'the single repair' the task's Section 4 asks about in isolation.**

## S5 Blast Radius Audit

Total claims with >=2 eligible+supports_alpha candidates across all six runs: **24**
Total structure_graph edges tracing to such claims: **7**
Currently-correct full-union cases: **0** · Ambiguous cases: **4** · Safe multi-attribution candidates: **0**

Affected tickers: QQQ, MSFT, AMD · Affected Alphas: A102, A103, A201, A301, A304, A501, A601

**Conclusion:** A blind union or blanket 'all-eligible-alphas' attribution rule (Options B/C as literally stated) would touch AT LEAST 7 edges across 3 tickers beyond QQQ A201, with ZERO currently-observed cases where full union would be obviously correct -- confirming the Section 3 finding that only a relation-compatible SUBSET rule (Option D) is safe. A naive fix scoped only to 'QQQ A201' would, if implemented as a general rule change, silently also alter these other 7 edges' attribution -- this must be explicitly bounded/tested before any implementation.

---

## S2 Trace — MSFT A304

| Family | Count | Strongest Claim | Mapped Alpha | Source Role | Qualification | To Extractor? | Node? | Edge? | Classification |
|---|---:|---|---|---|---|---|---|---|---|
| capex_burden_and_growth_vs_valuation | 1 | Any slowdown in Azure growth could trigger multiple compression. (fundamental_ag | A304 | PRIMARY_RESEARCH | PRIMARY_QUALIFIED, activation_eligible=True, factor_score=1.0, evidence_stance=supports_alpha, relation=conditional | False | False | False | STRUCTURALLY_EXPLICIT |
| high_rates_discount_rate_pressure | 3 | For a stock trading at 27.8x trailing earnings and 21.2x forward earnings, with  | A304 | SECONDARY_DECISION_OR_DEBATE (bear_researcher) | Likely SECONDARY_NOT_TICKER_SPECIFIC or SECONDARY_CAUSALITY_UNPROVEN (not independently verified per-claim in this audit) | False | Partial ('valuation_risk' node exists from OTHER claims/relations) | False | STRUCTURALLY_IMPLICIT |
| priced_for_perfection_valuation_pressure | 6 | Valuation (PEG 1.66) leaves limited margin of safety if growth disappoints. (fun | A304 | PRIMARY_RESEARCH | Likely qualified (not individually re-verified beyond claim:82 in this audit) | False | False | False | STRUCTURALLY_IMPLICIT |
| descriptive_multiple_statistics | 8 | Metric: P/E (TTM); Value: 27.8x; Assessment: Moderately rich (fundamental_agent) | A304 | PRIMARY_RESEARCH | Qualified in several cases | False | False | False | DESCRIPTIVE_ONLY -- correctly not extraction-worthy (states a value, no relation) |
| macro_fed_hike_multiple_compression_debate | 20 | The re-rating risk is asymmetric: if the Fed hikes and growth slows (even modest | A304 | SECONDARY_DECISION_OR_DEBATE (bear/bull/research_manager/risk analysts/portfolio_manager debate) | Mostly Secondary, largely NOT ticker-specific per this audit's spot checks | Partially -- some rate_cut_cycle/valuation_risk canonical relations DID extract from this family (existing edges tagged A001) | True | Yes, but tagged A001 (Rate Cut Cycle), not A304 | STRUCTURALLY_EXPLICIT in places (e.g. 'the Fed hikes... the multiple compresses') but attributed to the macro alpha (A001), not A304 |

**First break:** The first, and cleanest, break is at the STRUCTURE EXTRACTOR INPUT stage for the single strongest claim (claim:82, PRIMARY_QUALIFIED, STRUCTURALLY_EXPLICIT, factor_score=1.0) -- it never appears anywhere in extracted_structures.json. This is upstream of any alpha-attribution or evidence-qualification question; the claim simply never reached extraction at all.

## S2 Trace — MSFT A601

| Family | Count | Strongest Examples | To Extractor? | Nodes? | Edges? | Why not structural |
|---|---:|---|---|---|---|---|
| retail_sentiment_scorecards | 15 | Overall Sentiment: Mildly Bearish (Score: 3.8/10); The StockTwits sample... heavily weighted toward  | False | False | False | Pure numeric/scorecard reporting -- no asserted mechanism connecting sentiment to price/momentum outcome |
| price_target_and_analyst_narrative | 8 | Stifel lifted its MSFT price target to $530 -- described as a 'jaw-dropping' hike | False | False | False | Reports an event/fact, does not assert a momentum-driving mechanism |
| retail_vs_institutional_divergence | 10 | retail leaning bearish while institutions stay constructive; The $500 psychological battleground --  | False | False | False | Descriptive characterization of a divergence, not a causal narrative-momentum chain |
| ai_narrative_conditional_collapse | 1 | If OpenAI loses its edge, Azure's AI-driven demand narrative collapses. (bear_researcher) | False | False | False | The ONE claim with explicit causal language in the entire 46-claim A601 pool -- but it asserts narrative COLLAPSE (a negative/conditional risk), not the positive momentum-building mechanism Gold's A601 thesis requires, and is Secondary-sourced (bear_researcher) |

**First break:** Different in character from A304: this audit found NO clean, PRIMARY-qualified, structurally-explicit claim asserting a positive narrative-momentum mechanism anywhere in the 46-claim pool. The single causal-language claim found argues the OPPOSITE (narrative risk/collapse) and is Secondary-sourced. The 'break' here is less a pure extraction-recall failure and more that the underlying generated content for this run genuinely leans descriptive/scorecard rather than mechanistic for this specific Alpha.

## Description vs. Structure Classification

**A304:**
- STRUCTURALLY_EXPLICIT: Any slowdown in Azure growth could trigger multiple compression. (claim:82)
- STRUCTURALLY_IMPLICIT: Valuation (PEG 1.66) leaves limited margin of safety if growth disappoints.; rising discount rates are a direct [pressure] on a rich multiple
- DESCRIPTIVE_ONLY: Metric: P/E (TTM); Value: 27.8x; Assessment: Moderately rich; The PEG ratio of 1.66 suggests the stock is priced at a premium

**A601:**
- STRUCTURALLY_IMPLICIT: If OpenAI loses its edge, Azure's AI-driven demand narrative collapses.
- DESCRIPTIVE_ONLY: Overall Sentiment: Mildly Bearish (Score: 3.8/10); Stifel lifted its MSFT price target to $530
- NON_STRUCTURAL: RSI peaked above 79 in early August; generic retail chatter/positioning commentary

A304 has at least ONE clean STRUCTURALLY_EXPLICIT, PRIMARY-qualified claim that should have produced an edge -- a genuine extraction-recall defect on the evidence. A601's content is overwhelmingly DESCRIPTIVE_ONLY/NON_STRUCTURAL with only one STRUCTURALLY_IMPLICIT claim (itself negatively-framed and Secondary-sourced) -- extraction recall is NOT clearly defective here; the underlying generated content may simply not contain a qualifying structural relation this period. Do not call A601 an extraction defect on the same footing as A304.

## Extractor Blind Spots

| Mechanism | Observed Evidence | Affected | Confidence |
|---|---|---|---|
| relation vocabulary not recognized for conditional/hedged phrasing ('could trigger', 'may cause') | claim:82 uses hedged conditional language ('could trigger') and never entered extracted_structures.json, despite being P | MSFT A304 | MEDIUM -- plausible given the specific phrasing, but not proven against the extractor's actual pattern rules (not inspected in this audit, would require reading the Structure Extractor's own relation-recognition code, out of scope for this pass) |
| claim selection before extractor (fundamentals_report claims systematically under-sampled) | fundamental_agent DOES appear as a source for SOME extracted edges elsewhere in the same run (disproving a blanket exclu | MSFT A304 | LOW (disproven as a categorical explanation, though a per-claim selection heuristic gap remains possible) |
| valuation/narrative concepts absent from node ontology | A 'valuation_risk' node ALREADY EXISTS in the same run's extracted_structures.json (from other claims/relations) -- the  | MSFT A304 | LOW (ontology gap ruled out -- the concept-node already exists) |
| underlying content genuinely lacks a positive-momentum causal assertion | Only 1 of 46 A601 claims contains any causal language at all, and it argues narrative COLLAPSE, not construction -- a co | MSFT A601 | HIGH |
| source-role/ticker-specificity screening happening BEFORE (not after) extraction, silently dropping Secondary-sourced macro-debate claims | Many A304-relevant claims (the 20-claim 'macro Fed hike' family) are Secondary-sourced and largely not independently tic | MSFT A304 (partially) | MEDIUM |

## Node/Edge Type Expressiveness

**A304_earnings_expectations_to_multiple_compression**: YES -- edge_type='causal' + a target node conceptually equivalent to 'valuation_risk' or 'multiple_compression' already exist in this exact run's node set → EXTRACTION_RECALL_GAP, not REPRESENTATIONAL_GAP

**A304_higher_yields_to_discount_rate_pressure**: YES -- 'rate_cut_cycle --causal--> valuation_risk' already exists as a real edge in this exact run, proving the type system already expresses this exact relation shape → EXTRACTION_RECALL_GAP, not REPRESENTATIONAL_GAP (the relation type clearly works; A304 specifically wasn't the attributed alpha on it)

**A601_ai_narrative_to_investor_attention_to_momentum**: UNKNOWN/UNTESTED -- no node resembling 'investor_attention' or 'narrative_momentum' exists in ANY of the six runs inspected across this audit series; the edge_type vocabulary (causal/supportive/conflicting) could in principle represent it, but no node ontology precedent exists to confirm fit → AMBIGUOUS between EXTRACTION_RECALL_GAP and REPRESENTATIONAL_GAP -- leans REPRESENTATIONAL_GAP given zero precedent anywhere in the corpus, but not proven since the underlying content itself was also found to be weak (Section 8)

**A601_market_leadership_to_narrative_momentum**: Same as above -- UNTESTED, no precedent found → AMBIGUOUS, leans REPRESENTATIONAL_GAP

## S2 Counterfactual Recoverability

### MSFT A304 (current score 43.3642)
- one_edge_causal_conditional_contribution_0_50: new_score=48.36, crosses_50=False
- one_edge_supportive_asserted_contribution_0_80: new_score=51.36, crosses_50=True
- two_edges_causal_conditional: new_score=53.36, crosses_50=True
> Whether ONE edge suffices depends on how strongly the extractor would classify claim:82's assertion_status -- 'conditional' framing ('could trigger') is more conservative (insufficient alone), while a claim like the ALSO-EXPLICIT PEG/margin-of-safety family could plausibly support a second, independent edge. Two qualifying edges of at least conditional strength WOULD cross. Reported honestly as a range, not a single invented number.

### MSFT A601 (current score 32.7558)
- one_edge_causal_asserted_contribution_1_00: new_score=42.76, crosses_50=False
- two_edges_causal_asserted: new_score=52.76, crosses_50=True
> Even the strongest possible single edge does not cross (42.76). Two strong edges would (52.76) -- but Section 8 found only ONE weak, negatively-framed, Secondary-sourced causal claim exists in the entire pool, well short of what two genuinely qualifying edges would require. LOW confidence this is achievable without inventing content the underlying evidence doesn't support.

---

## S5 Design Options

**S5 Option A -- Use relation-compatible canonical Mapper Alpha IDs instead of singular matched_alpha**
- Files: `comqutor_alpha/graph_engine/graph_builder.py::_committed_alpha_ids_for_claim()`
- QQQ A201 recovery: PARTIAL -- would still require claim:13 to be a genuine A201 candidate, which it is not (Section 2); this option alone does not fix QQQ A201 without ALSO improving lineage resolution
- False positive risk: LOW if the compatibility table is narrow and explicit (not fuzzy) · Multi-alpha contamination risk: LOW-MEDIUM, bounded by the compatibility table · Blast radius: Bounded to the 24 multi-eligible claims found in Section 5, but requires building and maintaining a new compatibility table -- non-trivial ongoing maintenance surface

**S5 Option B -- Keep matched_alpha as primary, allow secondary canonical Alpha IDs when edge target/source semantics match taxonomy relation**
- Files: `comqutor_alpha/graph_engine/graph_builder.py`
- QQQ A201 recovery: SAME LIMITATION as Option A -- does not fix the underlying fact that claim:13 isn't a genuine A201 match
- False positive risk: LOW (secondary alphas are distinguishable from primary, can be excluded from scoring-eligibility by default) · Multi-alpha contamination risk: LOW (opt-in secondary marking, not automatic scoring inclusion) · Blast radius: Smaller than A (additive field, not a behavior change to existing alpha_ids) -- SAFEST of the three from a backward-compatibility standpoint

**S5 Option C -- At graph attribution time, query canonical Mapper result object and intersect with a structure relation compatibility table**
- Files: `comqutor_alpha/graph_engine/graph_builder.py`
- QQQ A201 recovery: SAME LIMITATION
- False positive risk: LOW, same as A · Multi-alpha contamination risk: LOW-MEDIUM, same as A · Blast radius: Same as A

**S5 Option D (this audit's addition) -- Improve LINEAGE RESOLUTION to prefer a canonically-qualified, higher-confidence claim among all candidate claims in the same canonical-relation supporting quote, rather than accepting the first/weakest text match**
- Files: `Structure Extractor's lineage resolution module (not yet located precisely in this audit -- likely comqutor_alpha/structure_engine/ or a graph_engine lineage-resolution helper)`
- QQQ A201 recovery: YES, this DIRECTLY addresses the actual identified root cause (Section 2) -- but requires locating and modifying code NOT precisely traced in this audit pass
- False positive risk: MEDIUM -- requires care that 'higher confidence' doesn't mean 'any claim mentioning similar keywords', must stay within the SAME agent-output's supporting-quote context, not search globally · Multi-alpha contamination risk: LOW if scoped to the same agent-output/quote context · Blast radius: UNKNOWN -- would require the same file/function investigation as Options A-C before scoping could be bounded; NOT recommended for immediate implementation without that follow-up trace

**Preferred: Option B (additive secondary-alpha marking)**
> Safest backward-compatibility profile (does not alter existing alpha_ids semantics), lowest contamination risk (opt-in, clearly separated field), and highest auditability. HOWEVER, explicitly acknowledged: Option B (and A/C) do NOT by themselves recover QQQ A201, because the actual root cause (Section 2) is a WEAK LINEAGE ANCHOR CLAIM, not merely restrictive attribution logic. Option D more directly addresses QQQ A201's real mechanism but requires further code-location work this audit did not complete. RECOMMENDATION: implement Option B first (safe, general-purpose improvement, addresses the OTHER 7 blast-radius cases found in Section 5 more cleanly than QQQ A201 itself), and treat QQQ A201 as requiring separate Option D follow-up investigation before any recovery claim is made for it specifically.

## S2 Design Options

**S2 Option A -- Improve extraction coverage using existing ontology/schema only (recognize additional deterministic causal patterns like 'X could trigger Y', 'X compresses Y' from PRIMARY_RESEARCH claims already flowing through the pipeline)**
- Problem addressed: MSFT A304's claim:82-type extraction-recall gap
- Taxonomy changes required: False · Ontology changes required: False
- Regression risk: LOW-MEDIUM -- adding a new deterministic pattern could also newly extract edges from OTHER runs' similarly-phrased claims, requiring the same kind of blast-radius check as Section 5
- A304 recovery likelihood: MEDIUM-HIGH (directly targets the proven gap) · A601 recovery likelihood: LOW (the underlying A601 content doesn't contain a comparable clean pattern to recognize -- Section 8)

**S2 Option B -- Expand relation compatibility/edge vocabulary for valuation and narrative relations (e.g. explicit 'multiple_compression', 'narrative_momentum' node/edge archetypes)**
- Problem addressed: Would help IF a REPRESENTATIONAL_GAP existed -- Section 10 found this is NOT the case for A304 (existing types already sufficient, proven by the pre-existing valuation_risk node and rate_cut_cycle->valuation_risk edge)
- Taxonomy changes required: Possibly for A601 only (unproven, Section 10 marks it AMBIGUOUS/leans REPRESENTATIONAL_GAP), NOT for A304 · Ontology changes required: Same caveat
- Regression risk: MEDIUM-HIGH -- broadening the ontology is a wider, harder-to-bound change than pattern recognition alone
- A304 recovery likelihood: LOW marginal benefit over Option A (A304 doesn't need new ontology) · A601 recovery likelihood: UNCERTAIN -- might help IF a genuine narrative-momentum relation existed in the content to represent, but Section 8 found the content itself is weak, so ontology expansion alone would extract nothing new

**S2 Option C -- Pre-normalize structurally implicit claims into extractor-compatible relation candidates using deterministic logic (e.g. a rule that rewrites 'X leaves limited margin of safety if Y' into a conditional causal candidate before extraction)**
- Problem addressed: The STRUCTURALLY_IMPLICIT family (3-6 claims) that Section 6 found for A304, beyond just the one STRUCTURALLY_EXPLICIT claim
- Taxonomy changes required: False · Ontology changes required: False
- Regression risk: MEDIUM-HIGH -- a general-purpose implicit-to-explicit rewriter is the most complex, highest-effort, and highest-risk of the three options; a poorly-scoped rewrite rule could manufacture false causal claims from genuinely non-causal text elsewhere in the six-ticker corpus
- A304 recovery likelihood: HIGH in principle (would catch more of A304's implicit family) but HIGHEST implementation/regression risk of the three · A601 recovery likelihood: LOW (the one A601 implicit claim is negatively-framed and Secondary -- normalizing it would still fail Primary/Secondary+ticker-specific screening)

**Preferred: Option A (recognize existing causal-language patterns from PRIMARY_RESEARCH claims already in the pipeline)**
> Directly, narrowly targets the ONE proven, clean extraction-recall gap (claim:82) without requiring ontology changes (Section 10 confirmed the existing types already suffice) or the higher-risk implicit-claim rewriting of Option C. Explicitly does NOT promise A601 recovery -- Section 8's finding that A601's content is overwhelmingly descriptive/non-structural means no extraction-pattern improvement can manufacture a relation the underlying evidence doesn't assert.

## Can One Fix Solve Both S5 and S2?

**NO** — S5 (QQQ A201) is an attribution-and-lineage-resolution problem in comqutor_alpha/graph_engine/graph_builder.py, operating on an EDGE THAT ALREADY EXISTS. S2 (MSFT A304/A601) is a claim-to-structure EXTRACTION problem, operating BEFORE any edge exists at all, in the Structure Extractor's own pattern-recognition layer. They touch different files, different pipeline stages, and different failure modes (misattribution of an existing relation vs. non-existence of a relation). Keeping them as separate remediation tracks, per the task's own Section 14 instruction.

## Prioritization

| Priority | Case | Rationale |
|---|---|---|
| P0 | TSM A301 | Highest legitimacy (Gold-expected, strong evidence, evidence_quality raw=56.56 the highest of any miss), closest to threshold (5.23pp), HIGHEST diagnostic certainty (fully traced t |
| P1 | MSFT A304 | Strong legitimacy (39 raw claims, one PRIMARY_QUALIFIED structurally-explicit claim proven never extracted), meaningful evidence strength, HIGH diagnostic certainty on the root cau |
| P2 | QQQ A201 | Legitimate Gold expectation, genuine underlying evidence exists (Section 2's dual-gap finding), but LOWER diagnostic certainty on the SINGLE fix needed (requires combining an attri |
| P2 | SNDK A103 | Legitimate, close near-miss (0.97pt short even under the already-designed Option B fix per the prior audit), independently corroborated by the recovery audit (no hidden recall defe |
| P3 | QQQ A301 | Legitimate expectation, but the prior audit's Option B fix leaves it 2.22pt short, AND this audit's blast-radius check flags it as touching a multi-eligible-claim pattern requiring |
| P3 | MSFT A601 | Legitimate Gold expectation in principle, but this audit's Section 8 finding (content overwhelmingly descriptive, only one weak/negative causal claim) suggests EXPECTED_CONSERVATIV |

---

## Path to 75% — Combinatorial Recovery

| Scenario | Conversions | Macro-Average | Confidence |
|---|---:|---:|---|
| Scenario 1 (HIGH_CONFIDENCE): TSM A301 only | 1 | 63.8095% | HIGH_CONFIDENCE |
| Scenario 2 (MEDIUM_CONFIDENCE): TSM A301 + MSFT A304 | 2 | 66.5873% | MEDIUM_CONFIDENCE |
| Scenario 3 (SPECULATIVE): TSM A301 + MSFT A304 + QQQ A201 (combined attribution+evidence fix) | 3 | 69.3651% | SPECULATIVE |
| Scenario 4 (SPECULATIVE, upper theoretical bound): all 7 structure-starvation cases recover (requires SNDK A103/A301 and MSFT A601 to ALSO recover, none of which current evidence supports with confidence) | 7 | 81.5873% | SPECULATIVE -- NOT credible given Sections 8/11/13's findings on A601 and the prior audit's finding that SNDK falls short even under its best-designed fix |

No credible (HIGH or MEDIUM confidence) scenario reaches the minimum 5 additional hits or the 75% target using structure-side work alone. The most defensible realistic ceiling is Scenario 3 (3 conversions, 69.37%, itself SPECULATIVE) -- still 2 conversions and 5.63 percentage points short.

## Is B-Side Work Necessary?

**Can structure-side work alone plausibly reach >=75%? NO**

At least 2, more likely 3-4, additional legitimate recoveries from the 7 Evidence Starvation cases (NVDA A102, NVDA A201, QQQ A101, MSFT A102, SNDK A102, AMD A102, AMD A201) would be needed even under the most optimistic credible structure-side scenario (Scenario 3, 3 conversions) to reach the minimum 5 total and approach 75%. This audit does NOT investigate B-side cases further, per the task's own Section 17 instruction.

## Regression Safety Plan

Required negative controls:
- All 23 currently-hit Gold Alphas across the six runs -- must remain at their current level under any S5 or S2 change
- Non-Gold candidate Alphas in each run's activation_summary -- must not newly cross to active/dominant/regime_level as a side effect
- Admitted main conflicts (NVDA/QQQ/TSM/AMD A101__A304 or A304__A601 pairs) -- conflict admissibility must remain byte-identical; no evidence found in this audit that local_structure_support feeds conflict_detector.py directly, but this must be explicitly re-verified before implementation
- QQQ A301 -- must not silently 'fix itself' via an S5 change not intended for it (the blast-radius audit shows it IS one of the 7 multi-eligible-claim-affected edges)
- SNDK A301 -- must remain unaffected by S5 changes (its issue is edge-type exclusion, unrelated to attribution)
- Currently-correct single-Alpha edges (the vast majority of edges in all six runs) -- must retain identical alpha_ids under any S5 attribution change
- Neutral/opposing evidence (evidence_stance != supports_alpha) -- must never newly qualify for structural support under any S2 extraction change
- Secondary evidence -- SECONDARY_NOT_TICKER_SPECIFIC/SECONDARY_CAUSALITY_UNPROVEN claims must remain ineligible; only PRIMARY_RESEARCH-sourced or already-qualified-Secondary claims may ever produce a NEW extracted edge under S2 Option A
- Multi-Alpha claims (the 24 identified in Section 5) -- each must be individually reviewed post-change, not assumed safe by the aggregate count alone

Must remain byte/semantically unchanged:
- B1 stance labels and thresholds
- B4 activation thresholds (50.0/70.0/86.0)
- Primary/Secondary qualification logic (evidence_source_role.py, completely untouched by S5 or S2)
- ticker-specificity logic (_is_ticker_specific, completely untouched)
- Gold benchmark v1 and its SHA-256
- conflict admissibility scores (pending explicit re-verification)

## Recommended Implementation Sequencing

**Phase 1: S5 Option B implementation (additive secondary-alpha marking)**
- implement additive field
- offline replay against all six runs
- targeted regression tests for the 7 blast-radius cases
- verify zero change to the 23 currently-hit Alphas
- Expected outcome: Safer attribution visibility; does NOT by itself claim QQQ A201 recovery

**Phase 2: S5 Option D follow-up investigation (separate, not yet scoped)**
- locate exact lineage-resolution code
- trace its blast radius the same way Section 5 did for attribution
- design a bounded fix
- Expected outcome: Only after this phase can QQQ A201 recovery be credibly claimed

**Phase 3: S2 Option A implementation (MSFT A304-type pattern recognition)**
- identify the exact deterministic-rules extraction module
- add the narrow 'X could trigger/cause Y' pattern
- offline replay against all six runs
- targeted fixtures for MSFT A304 plus negative controls
- Expected outcome: Plausible MSFT A304 recovery, contingent on resulting assertion_status strength

**Phase 4: Targeted regression tests for all four changes combined**
- unit tests per prior audit's Section 16 test plan plus this audit's Section 18 controls
- Expected outcome: Full offline confidence before any live validation

**Phase 5: Offline replay against all six FINAL_FRESH_SELECTED runs' persisted artifacts**
- recompute activation levels under combined S5+S2 changes with zero Provider/TradingAgents calls
- Expected outcome: Confirms or revises this audit's Scenario 3 estimate (69.37%) before committing to a fresh six-ticker run

**Phase 6: Only then, a fresh six-ticker production regression**
- explicit new authorization required
- not performed or scheduled by this audit
- Expected outcome: End-to-end confirmation in a genuinely fresh pipeline execution

## Stop Conditions Check

- requires changing gold: False
- requires lowering activation threshold: False
- requires counting candidate or capped active as hit: False
- requires bypassing evidence authority: False
- creates uncontrolled multi alpha attribution: AVOIDED by explicitly recommending Option B (bounded, additive) over a blind union -- Section 5's blast-radius data would make an uncontrolled union approach a genuine stop-condition trigger if it were chosen instead
- requires broad taxonomy rewrite: False
- introduces cross ticker leakage: False
- cannot preserve primary secondary semantics: False
- blast radius cannot be bounded: PARTIALLY -- S5's blast radius (7 edges, 3 tickers) IS bounded and enumerated in this audit (Section 5); S2 Option A's blast radius is NOT yet bounded (would require the same kind of scan against all six runs' claim text for the target pattern before implementation)

**Overall recommendation:** NO hard STOP triggered for either S5 Option B or S2 Option A as scoped. Proceed only to the offline investigation/enumeration phases (1 and the S2-equivalent of Section 5) before any code change, consistent with the prior audit's own sequencing discipline.

---

**Gold benchmark SHA-256 unchanged throughout this audit:** `99b1cd0247637054de360c3b5c0c00c7d8052152f3db1d29045eae1850bd8e9a`

**Provider calls: 0. TradingAgents calls: 0. No ticker run. No code/test/threshold/taxonomy/Gold changes.**
