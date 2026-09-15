# v0.1.3 Structure–Evidence Authority Unification Design Audit

Offline / read-only design analysis only. **No code, test, threshold, taxonomy, or Gold changes. Provider calls: 0. TradingAgents calls: 0. No ticker run.**

## John — Proposed Structure Authority Fix

```
Problem:
Structure and Evidence qualification independently classify the same claim.

Observed impact:
S5 (wrong Alpha attributed)     = 1  (QQQ A201)
S6 (claim fails qualification)  = 4  (QQQ A301, SNDK A103, SNDK A301, TSM A301)

Recommended fix:
Let an edge count as structural support for an Alpha if that Alpha already
has independently-qualified evidence elsewhere, even when the edge's own
specific claim doesn't -- without ever relaxing which evidence qualifies.

Preserves: B1 / B2 / B4 / thresholds / Gold / Primary-Secondary rules -- all untouched.

Potentially recoverable priority cases: 1 / 5  (TSM A301 only)

Can this design alone plausibly move 61.03% to >=75%: NO
(new macro-average would be 63.81% -- still 11.19pp short)

No code changed.
```

## Executive Summary

Observed Structure Starvation cases: **7**

S5 Alpha-Edge Alignment: **1** (QQQ A201)
S6 Locality Qualification: **4** (QQQ A301, SNDK A103, SNDK A301, TSM A301)
S2 Extraction Recall: **2** (MSFT A304, MSFT A601)

Shared authority mismatch affects: **4 / 7** (the S6 cases only — S5 and S2 have different mechanisms)

Recommended design: **Option B — Alpha-Level Independent-Qualification Fallback for Local Structure Support**

Addresses S5: **NO** · Addresses S6: **YES (partially — 1 of 4 fully recovers)** · Addresses S2: **NO**

Priority cases plausibly recoverable: **1 / 5** (TSM A301)

Would authority unification alone plausibly close the Alpha Hit gap: **NO**

Implementation risk: **MEDIUM** (bounded by contract, but full six-run blast radius not yet exhaustively enumerated)

> **Important correction versus the prior task's framing:** The prior structure-starvation audit's one-edge counterfactuals assumed each candidate edge's OWN specific claim could simply become 'qualifying'. This deeper trace shows that assumption would require RELAXING the Secondary/ticker-specific rule for that exact claim in 3 of 4 S6 cases (their claims are verified SINGLETON evidence-fact-groups with no Primary co-member -- see Section 2/7 below) -- which Section 5 of this task explicitly forbids. This audit instead designs a fix that preserves every existing evidence rule exactly and is honest that it recovers fewer cases as a result: only TSM A301 crosses to a hit under the recommended, rule-preserving design; QQQ A301 and SNDK A103 gain real but insufficient credit; SNDK A301 gains none (blocked by an orthogonal edge-type exclusion); QQQ A201 needs a separate, unaddressed attribution fix.

---

## Current Authority Split

### A. Evidence Qualification Authority

| Step | File | Function | Key Fields | Authority |
|---|---|---|---|---|
| raw claim | `outputs/runs/<run_id>/structured_agent_outputs.json / alpha_matches.json` | `Alpha Mapper (comqutor_alpha/structure_engine/alpha_mapper.py)` | claim_id, matched_alpha, match_status, candidate_scores[*].{alpha_id,eligible,evidence_stance,relation,assertion_status} | CANONICAL for per-claim Alpha relevance/B1 stance |
| canonical eligibility selection | `comqutor_alpha/graph_engine/evidence_fact_index.py (or equivalent evidence_fact_index module)` | `select_supporting_alpha_claims(matches, alpha_id, policy_version=ALPHA_ACTIVATION_EVIDENCE_V1)` | eligible_records (committed match, non-empty claim/evidence, finite score, relation in {activation,conditional,mixed}, assertion_status != negated) | CANONICAL -- single shared eligibility selector reused by activation and shadow-audit layers |
| shape into per-claim dict | `comqutor_alpha/graph_engine/activation_scorer_v2.py` | `_gather_qualifying_evidence()` | claim_id, agent, relation, assertion_status, semantic_group, duplicate_group_id, relation_triple | derived view, never re-decides eligibility |
| canonical fact grouping | `comqutor_alpha/graph_engine/activation_scorer_v2.py + evidence_fact_index.py` | `_group_evidence() -> group_evidence_candidates()` | evidence_fact_group_id, member claim_ids | CANONICAL -- same grouping the Evidence Integrity shadow layer uses |
| Primary/Secondary + ticker-specific qualification | `comqutor_alpha/graph_engine/evidence_source_role.py, called from activation_scorer_v2.py::_qualify_groups_for_activation()` | `qualify_evidence_group(members, is_ticker_specific=_is_ticker_specific_member)` | source_agent, source_role, activation_eligible, activation_qualification_reason | CANONICAL -- the ONE centralized source-role authority (module's own docstring) |
| ticker-specificity decision | `comqutor_alpha/graph_engine/activation_scorer_v2.py` | `_is_ticker_specific(record, ticker, company_names, entities_by_claim)` | boolean, token-boundary text match against ticker/company names | CANONICAL, invoked as a callback by evidence_source_role.py (never duplicated there) |
| final qualifying pool for scoring | `comqutor_alpha/graph_engine/activation_scorer_v2.py::score_alpha_v2()` | `qualified_claim_ids / qualifying_for_scoring` | the exact claim_ids that feed evidence_quality, agent_independence, ticker_specificity, AND local_structure_support | CANONICAL terminus -- this is 'the' Evidence Authority result per alpha |

### B. Structure Authority

| Step | File | Function | Key Fields | Authority |
|---|---|---|---|---|
| claim/input | `outputs/runs/<run_id>/structured_agent_outputs.json` | `TradingAgents canonical relation output + Alpha Mapper's alpha_matches.json` | claim text, matched_alpha, match_status, plausible_alphas (ambiguous) | reuses Alpha Mapper output as input, does not re-run B1 |
| Structure Extractor | `comqutor_alpha/structure_engine/ (structure extraction module producing extracted_structures.json)` | `builds raw nodes/edges incl. canonical-relation edges via lineage resolution to a source claim` | source, target, edge_type, assertion_status, lineage_status, source_claim_ids | independently decides RELATION existence/type/lineage -- does NOT re-decide B1 stance or Alpha eligibility, but DOES independently resolve which single claim a canonical relation's supporting quote lineage-matches to |
| node creation/merge | `comqutor_alpha/graph_engine/graph_builder.py` | `_normalize_input_nodes()` | id, label, canonical_factor, source_claim_ids (union merge across duplicate instances) | structural identity only, no re-classification |
| edge creation/merge | `comqutor_alpha/graph_engine/graph_builder.py` | `_normalize_and_merge_edges()` | source, target, edge_type, assertion_status (merged via _merge_assertion_status), source_claim_ids | structural identity/merge only |
| edge Alpha_ids attribution -- THE DIVERGENCE POINT | `comqutor_alpha/graph_engine/graph_builder.py` | `_committed_alpha_ids_for_claim(claim_info) + _claim_provenance_index()` | alpha_ids (from claim_info['matched_alpha'] ONLY, requiring match_status=='matched') | INDEPENDENTLY RE-DERIVES Alpha relevance from the Alpha Mapper's raw matched_alpha field for ONE lineage-anchor claim, WITHOUT checking evidence_source_role qualification (Primary/Secondary/ticker-specific) AT ALL, and without considering candidate_scores' fuller eligible/multi-alpha picture -- only the single mutually-exclusive matched_alpha winner. |
| alpha-link reason codes | `comqutor_alpha/graph_engine/graph_builder.py` | `_edge_alpha_link_reason_codes(edge, committed_alpha_ids)` | LINEAGE_UNRESOLVED, LINEAGE_AMBIGUOUS, NO_COMMITTED_ALPHA_MATCH | diagnostic only |
| ticker-local / qualifying-support classification -- SECOND DIVERGENCE POINT | `comqutor_alpha/graph_engine/activation_scorer_v2.py` | `_local_structure_component(qualifying_for_scoring, graph_edges, alpha_id) + _edge_claim_pool(edge)` | qualifying_local_edge_count, local_edge_exclusion_reasons (RELATION_OR_ASSERTION_NOT_QUALIFYING) | CORRECTLY defers to canonical qualified_claim_ids for the ELIGIBILITY check (intersects edge's source_claim_ids against the SAME alpha's qualifying_for_scoring pool) -- this part IS already unified. The divergence is entirely upstream, at the alpha_ids-attribution step, which used a DIFFERENT (role-unaware) criterion to decide the edge even reaches this check with the 'right' alpha_ids in the first place. |

### Key Finding

Contrary to a naive framing, the LOCAL-STRUCTURE ELIGIBILITY CHECK ITSELF (_local_structure_component) already correctly defers to canonical Evidence Authority (qualifying_for_scoring) -- it does not independently re-decide evidence qualification. The actual divergence is ONE STEP EARLIER: _committed_alpha_ids_for_claim() (graph_builder.py) decides which alpha(s) an edge is 'for' using ONLY the Alpha Mapper's single matched_alpha field for ONE lineage-anchor claim, entirely bypassing the later Evidence-Source-Role/ticker-specific qualification that the SAME claim will separately be checked against downstream. Two different, sequential gates on the same claim, computed by two different functions in two different files, with the earlier one blind to the later one's criteria.

## Duplicated Decisions

| Decision | Evidence Authority | Structure Implementation | Same Semantics? | Disagreement? | Affected Cases |
|---|---|---|---|---|---|
| Does this claim support Alpha X (B1/Alpha relevance)? | Alpha Mapper matched_alpha / candidate_scores[*].evidence_stance (alpha_matches.json) | graph_builder.py::_committed_alpha_ids_for_claim() reads the SAME matched_alpha field | True | False | — |
| Is this claim ticker-specific? | activation_scorer_v2.py::_is_ticker_specific() (token-boundary text match) | NOT independently computed by Structure at all -- graph_builder.py never checks ticker-specificity when attributing alpha_ids | N/A (Structure has no opinion) | True | QQQ A301, TSM A301, SNDK A103, SNDK A301 (partially) |
| Does source role (Primary/Secondary) qualify this claim for activation input? | evidence_source_role.py::qualify_evidence_group() (the one centralized authority) | NOT independently computed by Structure at all -- alpha_ids attribution never checks source_role | N/A (Structure has no opinion) | True | QQQ A301, TSM A301, SNDK A103, SNDK A301 |
| May Secondary evidence independently count? | evidence_source_role.py -- default-deny unless ticker-specific AND strong-causal | Structure's alpha_ids attribution grants a Secondary claim's matched_alpha full display/attribution status with no such restriction | False | True | QQQ A301, TSM A301 |
| Does a relation belong to Alpha X (single vs. multi-alpha)? | candidate_scores[*] can mark MULTIPLE alphas eligible for the same claim | _committed_alpha_ids_for_claim() uses matched_alpha, which is SINGULAR/mutually-exclusive per claim by construction | False | True | QQQ A201 |
| May an edge count as activation-support? | n/a -- Evidence Authority has no edge concept | activation_scorer_v2.py::_local_structure_component() -- correctly requires the edge's OWN source_claim_ids to intersect the SAME alpha's canonical qualified_claim_ids | True | False | — |
| Does a canonical-relation edge's single lineage-anchor claim represent the full evidentiary basis for that relation, or could OTHER already-qualified claims about the same relation also count? | qualifying_for_scoring is the FULL per-alpha pool, not claim-by-claim | each edge is pinned to exactly the ONE claim its lineage resolver picked, with no fallback to the alpha's wider qualified pool | False | True | TSM A301, QQQ A301, SNDK A103 |

## Recommended Canonical Authority

- **Alpha semantic mapping**: Alpha Mapper (comqutor_alpha/structure_engine/alpha_mapper.py) -- unchanged, sole owner
- **B1 stance**: Alpha Mapper's evidence_stance field (candidate_scores) -- unchanged, sole owner
- **ticker specificity**: activation_scorer_v2.py::_is_ticker_specific() -- unchanged, sole owner; Structure must NEVER independently re-derive this
- **Primary/Secondary evidence qualification**: evidence_source_role.py::qualify_evidence_group() -- unchanged, sole owner; Structure must NEVER independently re-derive this
- **source-role qualification**: evidence_source_role.py::source_role_for_agent() -- unchanged, sole owner
- **Alpha activation evidence eligibility**: activation_scorer_v2.py's qualified_claim_ids / qualifying_for_scoring -- unchanged, sole owner (the canonical terminus)
- **structure node semantics**: graph_builder.py -- Structure's own domain, unaffected by this design
- **structure edge semantics (type/direction/lineage)**: graph_builder.py / Structure Extractor -- Structure's own domain, unaffected
- **edge Alpha attribution**: RECOMMENDED CHANGE: should remain Mapper-sourced (matched_alpha, unchanged) for WHICH alpha an edge is FOR, but must stop being treated as sufficient for SCORING eligibility on its own -- attribution and scoring-eligibility should be explicitly two different questions, not implicitly conflated by omission
- **ticker-local edge qualification**: activation_scorer_v2.py::_local_structure_component() -- remains the sole scoring-eligibility gate, unchanged mechanism, but recommended to add ONE additional canonical-pool-existence check (see Section 9/11)
- **qualifying activation-support edge**: activation_scorer_v2.py -- unchanged owner, contract extended per Section 11

## Key Design Idea Assessment

**Proposal:** A Structure edge should inherit canonical Evidence authority through lineage instead of independently re-classifying the same claim.

**Finding:** This is ALREADY the case for the eligibility CHECK itself (_local_structure_component correctly checks the edge's claim against canonical qualified_claim_ids). The actual gap is one step earlier: alpha_ids ATTRIBUTION (_committed_alpha_ids_for_claim) does not consult canonical Evidence-Source-Role/ticker-specific authority at all, and is pinned to a single claim rather than the alpha's full qualified pool.

- Technically feasible: **True**
- Minimal-change: **True**
- Semantically safe: **YES, IF scoped exactly as specified in Section 11 -- decouples 'is this edge FOR alpha X' (unchanged, Mapper-sourced) from 'may this edge count as X's local structure support' (extended to check the alpha's OWN canonical qualified-pool existence, not just this one claim)**
- Risk of broadening activation improperly: LOW if scoped as an alpha-level existence check (does X have ANY qualified evidence) rather than any claim-level relaxation -- never lets an ineligible claim itself become eligible
- Risk of Secondary duplicate double-counting: NONE -- the design change touches only local_structure_support's edge-eligibility gate; it does not add, remove, or reweight any claim in evidence_quality/agent_independence/ticker_specificity, so Secondary-restatement-of-Primary dedup (SECONDARY_DUPLICATE_OF_PRIMARY) is completely untouched
- Risk of cross-Alpha contamination: NONE if the existence check is per-(ticker, alpha_id) exactly as qualified_claim_ids already is -- no cross-alpha pooling introduced
- Risk of cross-ticker leakage: NONE -- qualified_claim_ids is already computed per single run/ticker; no new cross-ticker data path introduced

---

## Case Studies

### QQQ A201 (S5)

- **Originating claim:** f88c8956-cb62-48aa-9951-89f8e8a95f83:aggressive_risk_analyst:risk_debate_state.aggressive_history:claim:13 -- text: 'Dell is up 300% year-to-date on a blowout beat.' (a fragment of a longer paragraph the canonical relation's own supporting quote actually draws from)
- **Canonical Mapper result for that claim:** matched_alpha=A301; that claim's OWN candidate_scores entry for A301 shows eligible=False, evidence_stance=neutral_background -- i.e. even the alpha the edge WAS attributed to shows this specific isolated claim as weak/ineligible on its own merits
- **Structure edge alpha_ids:** ['A301'] only, sourced purely from that one claim's matched_alpha
- **Why A201 disappeared:** The canonical-relation edge ('AI CapEx --causal--> Semiconductor Cycle', asserted with a rich supporting quote about the whole hardware complex) was lineage-resolved to a NARROW, tangentially-related sentence ('Dell is up 300%...') rather than to the richer paragraph. graph_builder.py's alpha_ids attribution NEVER independently considers the edge's own source/target node semantics (e.g. the literal string 'semiconductor_cycle') against the Alpha taxonomy -- it defers entirely to whatever that one lineage-anchor claim's own, separately-computed Alpha-Mapper classification happens to be, and that claim was never matched to A201 at all.
- **Does canonical Mapper authority already support A201?** UNVERIFIED/WEAK for this specific lineage-anchor claim -- checked directly, A201 does not appear as a strong candidate for claim:13 either. A201 DOES have its own healthy, independently-qualified evidence pool elsewhere in the run (evidence_quality raw=40.27, no evidence-side qualification codes fail), but that pool was never consulted by the attribution step.
- **Could the edge safely inherit A201 through lineage?** Only if lineage resolution or attribution were widened to consider MULTIPLE claims from the same canonical-relation quote, or to fall back to node/relation-name-based Alpha-taxonomy matching -- NEITHER of which is 'simple lineage inheritance'; both are more invasive than the S6 fix and were NOT validated as safe by this audit.
- **Safest fix:** **D** — - another approach, NOT (A) reuse Mapper alpha_ids as-is (already tried, doesn't reach A201), NOT (B) blind union (would attribute A201 based on a claim that doesn't actually support A201 either -- a genuine false-attribution risk), NOT (C) replace Structure attribution entirely (far too broad). This case requires either improving lineage resolution to anchor on the canonical relation's full supporting quote rather than a single fragment claim, or a separate, explicitly-scoped node-label-to-taxonomy matching step -- OUT OF SCOPE for the minimal, safe design recommended in this audit. Recommendation: treat QQQ A201 as a SEPARATE follow-up investigation, not bundled into the S6 fix.
- **Union risk:** A blind union (attribute the edge to BOTH A301 and A201 whenever either's matched_alpha OR ambiguous plausible_alphas mention them) would risk attributing edges to alphas the specific claim does not actually, substantively support -- exactly the false-attribution pattern already observed on A301 itself (matched_alpha=A301 yet that alpha's own candidate score for the claim is eligible=False). Union is not recommended without an additional per-alpha eligibility check at attribution time, which reintroduces the same complexity this audit is trying to minimize.

### S6 Locality Qualification Cases

| Case | Edge Exists | Alpha Assoc. Correct | Lineage Resolved | Evidence Qual. Status | Structure/Locality Status | Disagreement Source |
|---|---|---|---|---|---|---|
| QQQ A301 | True | YES (A301 correctly among alpha_ids) | YES (resolved) | FAILS -- SECONDARY_NOT_TICKER_SPECIFIC (edge1's claim); edge2's 3 of 4 claims never independently matched to A301 by the Mapper at all | FAILS -- RELATION_OR_ASSERTION_NOT_QUALIFYING (correctly derived FROM the evidence qualification failure -- not an independent Structure decision) | source-role qualification mismatch (Secondary/ticker-specific bar applied downstream, never checked at attribution time) |
| SNDK A103 | True | YES (A103 correctly among alpha_ids) | YES (resolved) | FAILS -- both source claims are entirely ABSENT from A103's evidence_fact_groups (never independently Alpha-Mapper-matched to A103 at all) | FAILS -- RELATION_OR_ASSERTION_NOT_QUALIFYING | Alpha mapping mismatch (not a role/ticker-specific issue for these particular claims -- they simply never entered A103's qualifying pool at all) |
| SNDK A301 | True | YES (A301 correctly among alpha_ids) | YES (resolved) | FAILS -- all 4 source claims absent from A301's evidence_fact_groups | FAILS -- RELATION_OR_ASSERTION_NOT_QUALIFYING, COMPOUNDED by edge_type='conflicting' which EDGE_CONTRIBUTIONS never scores regardless of qualification | Alpha mapping mismatch (primary) + edge-type/polarity exclusion (secondary, orthogonal issue closer to S4 in spirit) |
| TSM A301 | True | YES (A301 correctly among alpha_ids, no alpha_link_reason_codes) | YES (resolved) | FAILS -- SECONDARY_NOT_TICKER_SPECIFIC (the sole source claim) | FAILS -- RELATION_OR_ASSERTION_NOT_QUALIFYING | source-role qualification mismatch (identical mechanism to QQQ A301) |

**QQQ A301:** The edge's claim(s) fail evidence_source_role.py's SECONDARY_NOT_TICKER_SPECIFIC rule (Secondary-sourced, not independently ticker-specific) -- a genuine, correctly-applied rule, not a bug (Primary-qualified pool exists for this alpha: YES (3 PRIMARY_QUALIFIED claims exist for A301, but none is this edge's claim))

**SNDK A103:** Alpha mapping mismatch: the graph attributed the edge to A103 via matched_alpha, but neither underlying claim's OWN candidate score set independently confirms A103 as their eligible/qualifying match (Primary-qualified pool exists for this alpha: YES (6 PRIMARY_QUALIFIED claims exist for A103, but neither is this edge's claim))

**SNDK A301:** Two independent problems layered: (1) Alpha mapping mismatch (same as SNDK A103), AND (2) edge polarity ('conflicting') is excluded from local_structure_support scoring by design, so even full requalification would not help (Primary-qualified pool exists for this alpha: YES (9 PRIMARY_QUALIFIED + 1 SECONDARY_QUALIFIED_CAUSAL_EVIDENCE = 10 total qualified claims exist for A301, but none is this edge's claim, AND the edge type would still score 0 even if they were))

**TSM A301:** Same source-role qualification mismatch pattern as QQQ A301: a genuinely Secondary, non-ticker-specific debate claim happens to be the ONE claim a canonical relation lineage-resolved to, while 13 OTHER PRIMARY_QUALIFIED claims exist for the same alpha but were never the lineage anchor for any edge (Primary-qualified pool exists for this alpha: YES (13 PRIMARY_QUALIFIED claims -- the largest pool of any S6 case))

**Note:** Do NOT lump all four together: QQQ A301 and TSM A301 share the IDENTICAL mechanism (source-role/ticker-specific mismatch on a lineage-anchor claim, singleton evidence-fact-group, non-empty independent Primary pool elsewhere). SNDK A103 and SNDK A301 share a DIFFERENT mechanism (Alpha-mapping mismatch -- the claims were never independently matched to that alpha at all, not merely role-disqualified). SNDK A301 additionally carries a THIRD, orthogonal issue (edge-type/polarity exclusion) not present in the other three.

### S2 Extraction Recall Cases

**MSFT A304** — `covered_by_authority_unification = False`
> No edge of any kind connecting valuation-risk concepts to an MSFT outcome node exists anywhere in extracted_structures.json. The failure happens BEFORE any alpha-attribution or evidence-qualification step could even run -- there is no edge and no claim-to-edge lineage to unify authority over. This requires Structure Extractor relation-recall work (e.g. expanding which financial-narrative patterns produce a causal/supportive edge), entirely outside the scope of an authority-unification fix.

**MSFT A601** — `covered_by_authority_unification = False`
> Identical situation -- no narrative/momentum node or edge exists at all. Authority unification only ever operates on an EXISTING edge's claim lineage; it cannot manufacture a missing edge.

---

## Design Options

### OPTION A -- Structure edges inherit canonical evidence eligibility AND Alpha IDs directly from source fact lineage (single-claim binding, as literally stated in the task prompt)

- Files affected: `comqutor_alpha/graph_engine/graph_builder.py (_committed_alpha_ids_for_claim)`
- Functions affected: `_committed_alpha_ids_for_claim`, `_edge_alpha_link_reason_codes`
- Semantics changed: Attribution would require the SAME claim to ALSO pass evidence_source_role qualification before being tagged as alpha_ids at all
- Semantics NOT changed: B1, thresholds, taxonomy, Gold
- Complexity: **LOW** · Regression risk: **MEDIUM -- would REMOVE alpha_ids from edges whose claim fails role-qualification, changing existing display/audit output (alpha_ids currently shown on many edges across the codebase) for cases that currently pass** · Auditability: HIGH (single source of truth for attribution) · Backward compatibility: LOW -- changes existing persisted-artifact shape/content for ANY run, not just the 7 miss cases
- Addresses S5: False · Addresses S6: False · Addresses S2: False
- Risk of false activation: NONE (this direction only ever REMOVES attribution, never adds) · Risk of double count: NONE
- **Verdict:** REJECTED as literally specified -- it makes the systems agree by being STRICTER, not by recovering any of the 7 misses. It does not increase Alpha Hit Rate at all and actively risks unrelated regression by changing alpha_ids on edges outside the 7 known cases.

### OPTION B -- Keep Structure alpha_ids as-is (Mapper-sourced), but at LOCAL-STRUCTURE-ELIGIBILITY time, ADD an alpha-level existence check: an edge already correctly alpha_ids-tagged to X may count as qualifying support if EITHER (a) its own claim is in X's qualified_claim_ids (current, unchanged behavior) OR (b) X's qualified_claim_ids is non-empty at all (i.e. real, canonically-qualified Primary/ticker-specific evidence independently exists for X elsewhere in the run)

- Files affected: `comqutor_alpha/graph_engine/activation_scorer_v2.py`
- Functions affected: `_local_structure_component()`
- Semantics changed: An edge whose own specific claim fails qualification may still count IF the target alpha independently has qualifying evidence elsewhere -- decouples 'is this edge FOR alpha X' from 'does X have real evidence' without ever relaxing what counts as real evidence
- Semantics NOT changed: B1, Primary/Secondary rules, ticker-specificity rule, thresholds, taxonomy, Gold, evidence_quality/agent_independence/ticker_specificity scoring inputs (untouched)
- Complexity: **LOW-MEDIUM** · Regression risk: **LOW-MEDIUM -- only affects local_structure_support's raw/contribution for alphas that have BOTH (i) a Mapper-attributed-but-unqualified edge AND (ii) a non-empty qualified pool from OTHER claims; must verify no currently-PASSING case relies on the current stricter same-claim requirement to stay correctly at candidate** · Auditability: HIGH -- exact, easily-logged condition ('alpha has >=1 qualified claim') · Backward compatibility: HIGH -- strictly additive; existing same-claim-qualifying edges are unaffected; only previously-EXCLUDED edges can newly count
- Addresses S5: False · Addresses S6: YES (partially -- see counterfactual math; only TSM A301 crosses to a hit, QQQ A301/SNDK A103 gain insufficient credit, SNDK A301 unaffected due to edge-type exclusion) · Addresses S2: False
- Risk of false activation: LOW -- still requires genuinely-qualified evidence to exist for the SAME alpha; never invents evidence · Risk of double count: NONE -- does not touch evidence_quality/agent_independence, which are the components that could double-count
- **Verdict:** RECOMMENDED -- see Section 10

### OPTION C -- Introduce a shared normalized authority record ('AlphaEvidenceAuthority') per (ticker, alpha_id, run_id) consumed by BOTH the Structure Extractor's attribution step and the Activation Scorer's eligibility step

- Files affected: `new module e.g. comqutor_alpha/graph_engine/alpha_evidence_authority.py`, `comqutor_alpha/graph_engine/graph_builder.py`, `comqutor_alpha/graph_engine/activation_scorer_v2.py`
- Functions affected: `_committed_alpha_ids_for_claim (rewritten to consult the shared record)`, `_local_structure_component (rewritten to consult the shared record)`, `new build_alpha_evidence_authority() function`
- Semantics changed: Both attribution and eligibility would be recomputed from one shared, precomputed structure instead of two separately-derived paths
- Semantics NOT changed: B1, Primary/Secondary, ticker-specificity, thresholds, taxonomy, Gold (the shared record would still be built FROM the same unchanged canonical functions)
- Complexity: **HIGH -- requires restructuring the pipeline's data flow (the shared record must be computed once, early, and threaded through both graph_builder.py and activation_scorer_v2.py, which currently run somewhat independently within the same pipeline stage)** · Regression risk: **HIGH -- touches the widest surface area of any option; any subtle difference in how the shared record is derived versus the current two paths could shift MANY existing edges' alpha_ids or qualification status simultaneously across all six tickers, not just the 7 known cases** · Auditability: HIGHEST in the long run (single source of truth) but hardest to verify correct during the transition · Backward compatibility: LOW -- largest behavior-shape change
- Addresses S5: YES in principle (attribution could consult the full qualified pool, not just matched_alpha) · Addresses S6: YES in principle · Addresses S2: False
- Risk of false activation: MEDIUM -- broader surface increases the chance of an unintended new match somewhere in the six-ticker set · Risk of double count: LOW if implemented correctly, but harder to verify given the larger change surface
- **Verdict:** NOT RECOMMENDED FOR NOW -- correct long-term direction, but too large a change surface for a 'smallest safe fix'; revisit only if Option B's narrower fix proves insufficient after real implementation and testing

## Preferred Minimal Design

**Recommended: OPTION B — Alpha-Level Independent-Qualification Fallback for Local Structure Support**

Why preferred:
- 1. Preserves B1/B2/B4 exactly -- touches only the local_structure_support component's edge-inclusion test, never evidence_quality/agent_independence/ticker_specificity/direction_consistency
- 2. Preserves Primary/Secondary rules exactly -- never lets a Secondary-only, non-ticker-specific claim count on its own; only recognizes that OTHER, already-legitimately-qualified evidence exists
- 3. No threshold changes
- 4. No Gold changes
- 5. No broadening by default -- the fallback only activates when a real, canonically-qualified pool already exists for that exact alpha in that exact run
- 6. Reduces duplicate classification less invasively than Option C -- it does not restructure the pipeline, only adds one alternate condition at one existing call site
- 7. Improves auditability -- the new condition ('alpha has independent qualified evidence') is a simple, already-computed boolean, trivially logged
- 8. Minimal code surface -- one function, one file
- 9. Easy to regression-test -- the existing 7 cases plus a bounded set of negative controls (Section 16) fully characterize its behavior
- 10. Directly addresses the diagnosed S6 mechanism (4 of 7 cases), with honest, quantified partial success (only TSM A301 fully crosses; two others gain but remain short)

Why others are inferior:
- **Option A**: Makes the systems agree by REMOVING attribution in disagreement cases -- net negative for Alpha Hit Rate, plus unrelated regression risk to every OTHER edge's alpha_ids in the six-ticker set, not scoped to the 7 known cases.
- **Option C**: Architecturally the most correct long-term direction, but its regression-risk surface (touching graph_builder.py's node/edge merge AND activation_scorer_v2.py's scoring simultaneously, across all six tickers) is disproportionate to the size of the observed problem (7 misses, and only 4 of them even in scope). Not the 'smallest safe fix' the task asks for.

**Explicit scope limit:** Option B does NOT address S5 (QQQ A201) or S2 (MSFT A304/A601). It is scoped exclusively to the S6 mechanism.

## Exact Contract

1. E retains its existing lineage to F (source_claim_ids) -- UNCHANGED, no new lineage mechanism introduced.

2. E's alpha_ids attribution (which alphas E is FOR) continues to come SOLELY from F's canonical matched_alpha (graph_builder.py::_committed_alpha_ids_for_claim) -- UNCHANGED, never widened to candidate_scores or plausible_alphas by this contract.

3. E is eligible as qualifying local-structure support for alpha X if EITHER: (a) F's claim_id is a member of X's canonical qualified_claim_ids (CURRENT, UNCHANGED behavior), OR (b) X's canonical qualified_claim_ids is non-empty for this run (i.e. real, independently Primary-qualified-or-ticker-specific-Secondary-qualified evidence exists for X elsewhere) AND E's edge_type/assertion_status combination has a nonzero EDGE_CONTRIBUTIONS weight (excludes 'conflicting'-type edges from ever qualifying via this fallback, since a conflicting/opposing relation is not itself supportive of a bullish alpha's activation).

4. Condition (b) is evaluated PER (ticker, alpha_id) using the EXACT SAME qualified_claim_ids set already computed by _qualify_groups_for_activation -- no new qualification logic, no re-derivation of Primary/Secondary/ticker-specific status.

5. Structure may NARROW eligibility (e.g. by never letting a 'conflicting'-type edge qualify, as already true today) but may NEVER broaden it beyond what canonical Evidence Authority already independently supports for that alpha.

6. Same fact-group dedupe remains fully enforced -- this contract does not touch _group_evidence()/evidence_fact_group_id in any way.

7. Secondary-only claims remain governed exactly by evidence_source_role.py -- this contract never grants a Secondary-only, non-ticker-specific claim eligibility on its own merits; it only recognizes when a DIFFERENT, already-qualified claim's existence corroborates the alpha overall.

8. ticker-specific status continues to come exclusively from activation_scorer_v2.py::_is_ticker_specific() -- never re-derived by Structure.

9. This contract applies ONLY to the local_structure_support scoring component -- it does not change what alpha_ids display on an edge for audit/provenance purposes (Section 3's attribution ownership is otherwise unchanged).

## Non-Goals

- No threshold relaxation (ACTIVE_THRESHOLD/DOMINANT_THRESHOLD/REGIME_LEVEL_THRESHOLD remain 50.0/70.0/86.0)
- No candidate->active shortcut outside the exact contract in Section 11
- No counting capped_active as a hit
- No Gold edits (alpha_conflict_gold.v1 remains frozen, SHA-256 unchanged)
- No fuzzy Alpha matching (the fallback is an exact, already-computed set-membership/non-emptiness check, never a similarity score)
- No cross-ticker memory influence (qualified_claim_ids is already scoped to one run/ticker)
- No Alpha Memory modulation (activation_modulation_applied remains hardcoded false; this design touches only comqutor_alpha/graph_engine, never comqutor_alpha/memory)
- No 'structure edge automatically equals qualifying support' (the fallback still requires a real, independently-qualified pool to exist -- an edge with alpha_ids but NO qualified evidence anywhere for that alpha gains nothing)
- No Secondary duplicate inflation (evidence_quality/agent_independence/ticker_specificity inputs are completely untouched by this design)
- No bypass of ticker-specific evidence (condition (b) still requires the EXISTING qualified pool, which itself already enforces ticker-specificity for Secondary claims)
- No bypass of B1 stance (matched_alpha/evidence_stance/candidate_scores remain the unchanged, sole source of Alpha-relevance and stance)

---

## Counterfactual Recovery — 5 Priority Cases

| Case | Gains qualifying edge? | Would it become a hit? | Remaining blockers |
|---|---|---|---|
| QQQ A201 | NO | N/A -- no edge to evaluate | S5 attribution gap remains completely unaddressed; would need a separate fix (out of scope, see Section 6). |
| QQQ A301 | YES | NO | New score = 37.7754 + 10.0 = 47.78, still 2.22pp short of the 50.0 ACTIVE_THRESHOLD. The second candidate edge is edge_type='conflicting', excluded by the contract's own condition (b) restriction regardless. |
| SNDK A103 | YES | NO | New score = 39.0305 + 10.0 = 49.03, short of 50.0 by 0.97pp -- the closest near-miss, but still short under this exact, unchanged scoring formula. |
| SNDK A301 | NO | N/A -- edge remains ineligible under the contract | No causal/supportive edge exists at all for SNDK A301; the recommended design cannot help without a genuinely new (correctly-typed) edge, which is an extraction matter, not an authority-unification matter. |
| TSM A301 | YES | YES | New score = 44.7724 + 8.0 = 52.77, crossing the 50.0 threshold with 2.77pp to spare. No remaining blocker under this design. |

## Can This Design Alone Close the 75% Gap?

- Current macro-average: **61.0317%**
- Minimum additional legitimate hits needed: **5**
- Authority-unification recoverable count: **1** (TSM A301)
- Partial but insufficient: QQQ A301 (47.78, short by 2.22pp), SNDK A103 (49.03, short by 0.97pp)
- Unaffected: QQQ A201 (different mechanism, S5), SNDK A301 (edge-type excluded by contract)
- Macro-average if only the recoverable case(s) recover: **63.8095%**

**FEWER THAN 5 -- authority unification alone (Option B, the recommended minimal design) CANNOT reach >=75%. It recovers exactly 1 of the 7 structure-starvation cases as a confirmed hit (macro-average 63.81%, still 11.19pp short of target), with 2 more cases meaningfully improved but not crossing. This is not a claimed PASS from a counterfactual -- it is an honest quantification that this specific safe fix is a real but partial contribution, not a complete solution to the Alpha Hit gap on its own.**

## Regression Risks

- **Pattern:** Secondary facts generating structure edges with alpha_ids attached — Observed: YES -- e.g. NVDA's admitted main-conflict structure includes bear_researcher/aggressive_risk_analyst-sourced claims among source_agent_output_ids on several edges
  - Risk: Option B's condition (b) could theoretically newly qualify OTHER Secondary-sourced edges across the six-ticker set beyond the 7 known misses, wherever an alpha with a non-empty qualified pool also has an unqualified-claim edge -- this needs to be explicitly enumerated before implementation, not assumed bounded to 7 cases.
- **Pattern:** Same fact mapping to multiple Alphas via alpha_ids list — Observed: YES -- e.g. QQQ's 'valuation_risk --conflicting--> qqq_revenue_growth' edge carries alpha_ids=['A301','A304'] simultaneously
  - Risk: Confirms edges CAN legitimately carry multiple alpha_ids already; Option B does not change this, but any per-alpha existence check must be evaluated independently per alpha_id in the list, never conflating the two.
- **Pattern:** Candidate Alphas (not just misses) with structure edges present — Observed: YES -- several 'candidate'-level alphas across the six runs have >=1 alpha-tagged edge that already fails RELATION_OR_ASSERTION_NOT_QUALIFYING for the same reason as the 7 miss cases (not exhaustively enumerated in this audit)
  - Risk: Option B could shift SOME currently-candidate Alphas (outside the 7 Gold misses) toward active/dominant if they happen to have both an unqualified edge AND a non-empty qualified pool -- this is only a risk if such a shift would be WRONG; per the contract it is not wrong (the alpha genuinely has independently qualified evidence), but it IS a behavior change requiring explicit before/after enumeration across all six runs before implementation.
- **Pattern:** Opposing/neutral evidence producing structure relations — Observed: YES -- multiple 'conflicting'-type edges exist with real alpha_ids across all four audited tickers
  - Risk: LOW -- Option B's contract explicitly excludes 'conflicting'-type edges from qualifying via condition (b) (Section 11, item 3), so this pattern is already defused by design, not merely assumed safe.

| Risk Category | Level |
|---|---|
| false positive alpha activation | MEDIUM -- bounded by the contract (still requires a real qualified pool) but the FULL blast radius across all six runs was not exhaustively enumerated in this offline audit; requires the Section 16 test/fixture work before implementation |
| duplicate evidence inflation | LOW -- evidence_quality/agent_independence/ticker_specificity are completely untouched |
| conflict score changes | LOW -- local_structure_support does not feed conflict_detector.py's admissibility scoring directly (separate B2 pipeline); no evidence found of a shared code path |
| alpha level changes | MEDIUM -- any alpha whose score sits within ~20pts of ACTIVE_THRESHOLD with a currently-unqualified-but-alpha-tagged causal/supportive edge could shift from candidate to active; the six-run blast radius must be enumerated, not assumed limited to the 7 diagnosed misses |
| graph edge count changes | NONE -- this design changes SCORING eligibility only, never adds/removes/merges an edge (graph_edge_count is unaffected) |
| main conflict changes | LOW-MEDIUM -- an alpha level change (candidate->active) could in principle change which alphas are eligible to participate in conflict admissibility; not directly evidenced in this audit but not ruled out either |

**Caveat:** This audit did NOT exhaustively re-score all six runs' full Alpha sets under the proposed contract (that would itself be an implementation/test action, out of scope for a read-only design audit). The risk levels above are bounded by the contract's own restrictions, not by exhaustive counterfactual re-scoring.

## Test Plan

Unit tests required:
- test_lineage_inheritance_unchanged -- an edge's source_claim_ids/alpha_ids attribution is byte-identical before/after (Option B touches only local_structure_support, never graph_builder.py)
- test_canonical_alpha_mapping_reuse -- _committed_alpha_ids_for_claim behavior is completely unchanged (regression-pin its existing output on a fixture)
- test_canonical_ticker_specific_reuse -- _is_ticker_specific is not called or re-derived anywhere in the new condition (b) path; it is only ever read via the already-computed qualified_claim_ids
- test_primary_secondary_preserved -- a Secondary-only, non-ticker-specific claim's OWN activation_eligible remains False; it can never itself become eligible via this design
- test_fact_group_dedupe_preserved -- SECONDARY_DUPLICATE_OF_PRIMARY classification and _group_evidence() output are unaffected
- test_opposing_neutral_evidence_cannot_support_activation -- a 'conflicting'-type edge NEVER gains eligibility via condition (b), even when the target alpha has a non-empty qualified pool
- test_multiple_alpha_mapping_behavior -- an edge with alpha_ids=['A301','A304'] is evaluated independently for each alpha; qualifying for one never implies qualifying for the other
- test_structure_narrowing_allowed -- an edge that fails BOTH condition (a) and (b) remains correctly excluded (e.g. SNDK A301's conflicting-type edge)
- test_structure_broadening_forbidden_without_canonical_support -- an alpha with an EMPTY qualified_claim_ids pool gains NOTHING from condition (b) regardless of how many alpha-tagged edges exist (covers a hypothetical worse version of MSFT A304/A601-like cases, confirming S2 remains untouched)

Regression fixtures required:
- QQQ A201 (expect: still candidate, unaffected by this design)
- QQQ A301 (expect: local_structure_support raw rises to 50.0, but final level remains candidate -- 47.78 < 50)
- SNDK A103 (expect: raw rises to 50.0, final level remains candidate -- 49.03 < 50)
- SNDK A301 (expect: completely unaffected -- edge_type exclusion)
- TSM A301 (expect: raw rises to 40.0, final level becomes active -- 52.77 >= 50, THE ONLY EXPECTED LEVEL CHANGE)

Negative control cases: All 23 currently-HIT Gold Alphas across the six runs, plus a sample of currently-correctly-candidate Alphas from OUTSIDE the Gold benchmark's expected sets (e.g. any alpha in each run's activation_summary not in the Gold set) -- must be enumerated and pinned to confirm ZERO of them change level under the new contract, given Section 15's flagged risk that the blast radius was not exhaustively verified in this offline audit.

## Implementation Plan

**Phase 1: Enumerate full blast radius**
- Files: `outputs/runs/<all six run_ids>/alpha_activations.json (read-only enumeration script, not a code change)`
- Functions: —
- Expected effect: Offline script (not production code) computes, for every Alpha in every one of the six runs, whether it currently has (i) an alpha-tagged-but-unqualified edge AND (ii) a non-empty qualified_claim_ids pool -- producing the exact list of Alphas Option B would affect, closing Section 15's caveat BEFORE any code change.

**Phase 2: Introduce the condition (b) check**
- Files: `comqutor_alpha/graph_engine/activation_scorer_v2.py`
- Functions: `_local_structure_component() -- add an additional inclusion branch alongside the existing edge_claims & alpha_claim_ids intersection check`
- Expected effect: An edge whose own claim fails intersection may still be included if alpha_claim_ids (the alpha's own qualified pool) is non-empty AND the edge's edge_type/assertion_status has a nonzero EDGE_CONTRIBUTIONS weight.

**Phase 3: Preserve structure-specific narrowing**
- Files: `comqutor_alpha/graph_engine/activation_scorer_v2.py`
- Functions: `_local_structure_component()`
- Expected effect: Explicitly re-verify the 'conflicting' edge-type exclusion and any other existing narrowing rule still applies identically under the new branch -- no accidental widening of what edge types can ever contribute.

**Phase 4: Add regression tests**
- Files: `tests/test_activation_scorer_v2.py (existing file, extend)`
- Functions: `new test functions per Section 16`
- Expected effect: Pin exact before/after behavior for the 5 priority cases plus the negative-control set from Phase 1's enumeration.

**Phase 5: Offline replay against existing persisted artifacts**
- Files: `none (offline script only, reusing existing run_audit.json/alpha_activations.json for the six FINAL_FRESH_SELECTED runs)`
- Functions: —
- Expected effect: Recompute local_structure_support/activation levels for all six runs' full Alpha sets under the new logic WITHOUT any Provider/TradingAgents call, confirming Phase 1's predicted blast radius matches reality exactly before touching Gold-evaluated numbers.

**Phase 6: Only then consider a fresh six-ticker regression**
- Files: —
- Functions: —
- Expected effect: A NEW live run would be required only to confirm the fix behaves identically end-to-end in a genuinely fresh pipeline execution -- not required to validate the offline replay itself, and explicitly NOT authorized or performed by this design audit.

## Stop Conditions Check

- lineage from structure edge to canonical fact unreliable: False
- canonical evidence authority not deterministically accessible: False
- fix requires threshold relaxation: False
- fix requires rewriting B1 B2 B4: False
- fix would double count secondary evidence: False
- fix would make structure inherit every mapper alpha without relation compatibility: False
- regression risk cannot be bounded: PARTIALLY TRUE -- Section 15 explicitly flags that the full six-run blast radius was NOT exhaustively enumerated in this offline audit (that enumeration is Phase 1 of implementation, not yet performed). This is a bounded, addressable gap (a read-only enumeration script), not an unbounded one, so it does NOT trigger a hard STOP, but implementation must not proceed past Phase 1 until that enumeration is complete and reviewed.

**Overall recommendation:** PROCEED TO PHASE 1 (enumeration) ONLY, under explicit future authorization. Do not proceed to Phase 2 (actual code change) until Phase 1's blast-radius enumeration is complete and reviewed. No STOP condition is definitively triggered, but the regression-risk caveat must be resolved first.

---

**Gold benchmark SHA-256 unchanged throughout this audit:** `99b1cd0247637054de360c3b5c0c00c7d8052152f3db1d29045eae1850bd8e9a`

**Provider calls: 0. TradingAgents calls: 0. No ticker run. No code/test/threshold/taxonomy/Gold changes.**
