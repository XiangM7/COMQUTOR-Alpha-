# Gold v0.2 — Acceptance Adjudication

**Step 5: root-cause trace for the blocking FAIL and unresolved blocking/Silver REVIEWs surfaced in Step 4.** This task explains WHY the observed results occurred. It does not tune the system, does not fix any discovered defect, and does not change the frozen Step-4 acceptance outcome.

## Executive Result

**Release entering Step 5: FAIL**
**Release after Step 5: FAIL** (unchanged)

**Primary blocking defect:** `QQQ-A001-RATE-CUT-CYCLE` — conditional-force violation, root cause `SYSTEM_ERROR` (semantic-mapping false positive).

**Formal Gold**

- NVDA: **PASS**
- QQQ: **FAIL**
- SNDK: **PASS**

**Silver (non-blocking)**

- MSFT: **FAIL** (two failure modes traced — see below)
- TSM: **PASS**
- AMD: **PASS**

Gold v0.2, the Evidence Trigger Matrix, and the Step-4 Final Acceptance Table were all verified byte-identical to their frozen hashes before this task began, and remain unmodified.

---

## Queue Reconciliation

The Step-4 final numbered response (item 37) listed only **two** Step-5 items — `QQQ-A001-RATE-CUT-CYCLE` and `MSFT-CAPEX-BURDEN-CONDITIONAL` — matching the `requires_step5_adjudication=true` flags actually set in the Step-4 JSON's per-rule records and its `step5_review_queue` field.

However, that same Step-4 response also separately reported (item 30) **"Formal Gold blocking REVIEW count = 1,"** naming `QQQ-A003-LIQUIDITY-EXPANSION` — a blocking, unresolved REVIEW that by its nature also warrants adjudication attention, even though its own `requires_step5_adjudication` flag was left `false` in the Step-4 JSON (its outcome was already fully determined by the frozen UNCERTAIN trigger with no root-cause ambiguity to trace).

**This was a reporting-scope omission in the two-item queue framing, not a data error in the Step-4 JSON itself** — the JSON's blocking/REVIEW fields were internally consistent throughout. Per this task's instruction, the omission is corrected here by including `QQQ-A003-LIQUIDITY-EXPANSION` as **Case B** below, without modifying the frozen Step-4 file.

**Reconciled queue: 3 cases** (A, B, C below).

---

## Case A — QQQ-A001-RATE-CUT-CYCLE (Formal Gold, Blocking, FAIL)

**Frozen condition:** ABSENT (STRONG contrary evidence)
**Actual:** ACTIVE (score 66.4226, direction=positive)
**Step-4 result:** FAIL
**Step-5 disposition: FAIL (unchanged).** `conditional_force_violation = true`.

### Stage Trace: Evidence → Mapping → Qualification → Activation → Exposure → Final Level

| Stage | Finding |
|---|---|
| **Evidence** | **CORRECT.** The upstream corpus genuinely and predominantly describes a rate-**HIKE**/hawkish environment (93% no-cut probability, 72% hike probability) — this matches, and independently corroborates, the frozen ABSENT/STRONG-contrary determination from Step 3. |
| **Mapping** | **← FIRST INCORRECT STAGE.** `alpha_matches.json` shows 66 claims across 7 distinct agents assigned `matched_alpha="A001"` by the LLM classifier, on **topical** proximity to "interest rate policy" — without requiring directional alignment to A001's specific falling-rate/easing thesis. The separate, already-implemented, direction-aware `evidence_stance.py` shadow classifier independently scores these same 66 claims as: 13 `supports_alpha`, 10 `opposes_alpha`, 41 `neutral_background`, 2 `mentions_alpha` — i.e. a large majority do not actually support a rate-cut thesis, and several directly oppose it. |
| **Qualification** | Existing gates (`local_structure_support` cap, entity-exposure `would_block_*` flags) are direction-agnostic — they check evidentiary structure/locality and historical-exposure blocking, not net directional alignment with the Alpha's own polarity. None is designed to catch a direction-blind topical mapping error, so none fired. |
| **Activation** | Given its (incorrectly pooled) inputs, the deterministic Activation Scorer v2 formula computed correctly: `evidence_quality` (raw 97.73, from 26 unique semantic groups — pure volume) and `agent_independence` (raw 70.0, from 7 distinct agents — pure breadth) are the two highest-weighted components (0.35 + 0.20 = 0.55 combined weight) and are **volume/breadth-based, not net-direction-based**. This large, direction-mixed pool alone was sufficient to push the uncapped score to 66.42, past the "active" threshold. |
| **Exposure** | `entity_alpha_exposures.json`: `historical_mapping=0.8` (static/seed-based prior) vs `current_evidence=0.216` (much lower, arguably a more direction-aware signal), blended to `final_exposure=0.604`. However `qualification_effect_applied=false` and `would_block_dominant`/`would_block_regime_level=false` for this run — exposure did **not** actively alter this outcome. Not the active cause here, though the high `historical_mapping` input is a latent risk factor worth separate attention. |
| **Final Level** | `active` (66.42, direction=positive). Secondary observation: among the 66 claims' own claim-level `direction` field, the split is close to even-to-slightly-negative (17 negative vs 16 positive, 23 unknown, 10 neutral) — yet the alpha-level rollup reads "positive." This doesn't change the root-cause conclusion but is flagged as a related anomaly. |

### Conclusion

| Field | Value |
|---|---|
| `step4_result` | FAIL |
| `root_cause_primary` | **SYSTEM_ERROR** |
| `root_cause_secondary` | **SEMANTIC_MAPPING_FALSE_POSITIVE** |
| `mechanism` | A high-volume, multi-agent debate about "the interest rate environment" (triggered by one news event — a strong jobs report shifting Fed-hike odds) was topically matched to A001 across 66 claims from 7 agents, even though most of that debate is about a hike, not a cut, and 10/66 claims directly oppose the alpha. Volume-based scoring components alone pushed A001 to active. |
| `first_incorrect_stage` | MAPPING |
| `upstream_evidence_correct` | **yes** |
| `mapping_correct` | **no** |
| `qualification_correct` | **no** — existing gates are sound for their own purpose but none checks directional alignment |
| `activation_correct_given_inputs` | **yes** — the formula is not itself buggy; it faithfully aggregated the (mis-mapped) inputs it received |
| `gold_change_required` | **NO** — the frozen ABSENT trigger is independently corroborated by this trace, not contradicted by it |
| `production_fix_recommended` | **yes** |
| `fix_scope` (description only, not implemented) | For directional/cyclical macro Alphas (A001, A501, A003), require net directional alignment between a claim's stance and the Alpha's own polarity before the claim counts toward that Alpha's evidence pool — e.g. wire the existing (currently shadow-only) `evidence_stance.py` classification into the Alpha Mapper's admission path for these Alphas, or add an equivalent direction-gate at the LLM matching stage. |

---

## Case B — QQQ-A003-LIQUIDITY-EXPANSION (Formal Gold, Blocking, REVIEW)

**Frozen trigger:** UNCERTAIN
**Actual system treatment:** `candidate`, score=0.0, `reason_codes=["NO_QUALIFYING_EVIDENCE"]`
**Step-4 result:** REVIEW

### Trace

Zero claims were assigned `matched_alpha="A003"` in this run (`alpha_matches.json`). Activation shows `evidence_quality.raw=0.0`, `agent_independence.distinct_agents=0`, no supporting claim IDs. This is a clean "no evidence found" outcome, not a mapping or scoring anomaly — slightly stronger, in fact, than Step 3's own UNCERTAIN/WEAK characterization (which found only indirect recession-relief framing via broader upstream text search, not any claim the deterministic/LLM mapper itself was willing to commit to A003).

**Implementation behavior classification: `reasonable_given_uncertain_evidence`.**

### Resolution

Per this task's explicit policy, the question answered is "does system provenance reveal a defect worth fixing," not "can this REVIEW be forced into PASS." No deterministic acceptance resolution is possible, and none is invented.

**Acceptance remains: REVIEW.**
`human_resolution_needed = true.`

Because release already carries a blocking FAIL from Case A, this unresolved REVIEW does not change the overall release result.

---

## Case C — MSFT-CAPEX-BURDEN-CONDITIONAL (Silver, Non-Blocking, REVIEW)

**Frozen:** `capex_present = PRESENT`, `capex_downside_linkage_present = PRESENT`
**Actual A304:** `candidate`, score=43.3642 (not detected)

### Trace: Evidence → Mapping → Qualification → Activation/Admissibility → Final State

52 claims were `matched_alpha="A304"` in `alpha_matches.json`, spanning 11 distinct agents, and they include exactly the capex-downside-linkage evidence Step 3 cited — e.g. `fundamental_agent`: *"Any slowdown in Azure growth could trigger multiple compression"*; *"Despite the capex surge, free cash flow remained robust... though it declined modestly from FY2025's $71.6B"*; `portfolio_manager`: *"declining FCF efficiency (FCF fell to $67.0B from $74.1B while capex...)"*.

However, the `evidence_source_role_v1` qualification policy (`comqutor_alpha/graph_engine/evidence_source_role.py`) classified the 39 raw unique evidence facts as:

| Qualification reason | Count |
|---|---:|
| `PRIMARY_QUALIFIED` | 13 |
| `SECONDARY_NOT_TICKER_SPECIFIC` | 25 |
| `SECONDARY_QUALIFIED_CAUSAL_EVIDENCE` | 1 |
| **Qualified total** | **14** |

The 25 `SECONDARY_NOT_TICKER_SPECIFIC` facts are restatements of the same underlying findings by "secondary"-role debate agents (`bear_researcher`, `bull_researcher`, `portfolio_manager`, `research_manager`, `conservative_risk_analyst`, `neutral_risk_analyst`, `aggressive_risk_analyst`, `trader`) — reducing `agent_independence.distinct_agents` from 11 (raw) to 4 (qualified: `aggressive_risk_analyst`, `fundamental_agent`, `news_agent`, `sentiment_agent`). The resulting uncapped activation score (43.36) fell short of the "active" threshold.

**This distinction matters, exactly as anticipated by this task's framing:** Gold's semantic evidence trigger being PRESENT (a Step-3, evidence-only, upstream-of-activation text-search finding) does **not** by itself prove B2/B4 production admissibility requirements were satisfied. This case is a direct, concrete illustration of that documented distinction — the genuine capex-downside-linkage evidence is present among the 14 qualified groups, but the aggregate falls short of the active bar once debate-agent volume is correctly excluded.

### Classification

**Root cause primary: `ADMISSIBILITY_GATE_REASONABLE_SUPPRESSION`.**

This appears to be `evidence_source_role_v1` operating as designed — deliberately down-weighting debate-agent restatement of already-counted primary facts to prevent duplicate-evidence overweighting — rather than a mapping loss or code defect. No claim was lost outright.

A residual, unresolved open question (not asserted as a defect): whether `SECONDARY_NOT_TICKER_SPECIFIC` is too aggressive when a debate-agent claim explicitly restates hard, ticker-specific figures already established by a primary agent (PEG 1.66, P/E 27.8x, FCF $67.0B, capex $115.9B). This trace did not find decisive evidence either way, so `SYSTEM_ERROR` was **not** asserted, and the finding is **not** upgraded past REVIEW.

**Acceptance remains: REVIEW.** Non-blocking (Silver).

---

## Known Non-Blocking Failure Carried Forward (Not Deep-Traced)

| Ticker | Rule | Result | Blocking | Note |
|---|---|---|---|---|
| MSFT | `MSFT-A102-DIRECT-INFERENCE-TRIGGER` | FAIL | No | Step-4 comparison was already deterministic (frozen trigger PRESENT/STRONG, `must_detect_if_evidence_present`; actual A102 remained `candidate`, score 34.967). Not placed in the Step-5 queue because no deeper trace is needed to explain the acceptance outcome itself. Recorded here so it is not lost from the closure package. |

---

## Additional Composite-Conflict Review Audit

**NO_ADDITIONAL_COMPOSITE_CONFLICT_REVIEW_CASES.**

All three `COMPOSITE_STRUCTURE_HIT` rules (`NVDA-GROWTH-VS-VALUATION-CONFLICT`, `TSM-AI-TO-FOUNDRY-TRANSMISSION`, `AMD-AI-GROWTH-VS-VALUATION`) resolved PASS in the Step-4 JSON; none was marked REVIEW for a "composite trigger PRESENT but no allowed conflict admitted" scenario. Step 5 was not broadened beyond the three reconciled cases above.

## Forbidden-Dominant / Conditional-Force Audit

Verified directly from the Step-4 JSON:

- `forbidden_dominant_violations = 0` (no rule has `forbidden_dominant_violation: true`) — **confirmed, matches Step-4 report.**
- `conditional_force_violations = 1`, reconciling exactly to `QQQ-A001-RATE-CUT-CYCLE` — **confirmed, matches Step-4 report.**

No inconsistency found.

## Alpha Memory

Not revisited or modified. Carried forward unchanged: **6/6 shadow, `activation_modulation_applied = false`.** Not considered a candidate root cause for any case in this task — no persisted evidence implicates it.

---

## Remediation Backlog (Recommendations Only — Nothing Implemented)

| Priority | Blocking | Affected | Likely Module | Remediation Concept (minimal) | Regression Tests Needed | New Gold Version? | New Fresh Runs After Fix? |
|---|---|---|---|---|---|---|---|
| P1 | Yes | `QQQ-A001-RATE-CUT-CYCLE` (and structurally similar directional Alphas A501, A003) | `structure_engine/week2_llm.py` (Alpha Mapper), `graph_engine/activation_scorer_v2.py` | Gate directional-Alpha admission on net stance alignment — wire `evidence_stance.py`'s classification (or equivalent) into the Alpha Mapper's admission path for these Alphas, rather than pooling any topically-adjacent claim regardless of support/opposition. | A fixture reproducing a direction-mixed, high-volume single-topic debate that currently activates A001 incorrectly; assert it no longer reaches "active" post-fix. Extend to A501/A003. | NO | YES |
| P2 | No | `MSFT-CAPEX-BURDEN-CONDITIONAL` | `graph_engine/evidence_source_role.py` | Review whether `SECONDARY_NOT_TICKER_SPECIFIC` should recognize debate-agent restatements carrying hard, ticker-specific figures already established by a primary agent, rather than blanket exclusion — open question, not a confirmed defect. | A fixture with a primary-agent fact and several secondary-agent restatements of the same ticker-specific figure; assert intended behavior once decided. | NO | YES |
| P2 | No | `MSFT-A102-DIRECT-INFERENCE-TRIGGER` | `structure_engine/week2_llm.py`, `graph_engine/activation_scorer_v2.py` | Not deep-traced this task; recorded for future investigation. | TBD pending dedicated trace. | NO | YES |

---

## Gold v0.2 Survives Failure

**Gold v0.2 remained immutable after comparison and throughout this adjudication.** A release FAIL is a valid acceptance outcome and does not invalidate the benchmark — Gold's purpose is to expose defects, not to be tuned until results look acceptable.

Every root cause identified in this task is a **production-system finding**, not a Gold-authority defect. No case met the bar for `GOLD_LABEL_NEEDS_UPDATE` or `MARKET_CONDITION_CHANGED` — no persisted evidence proves the frozen benchmark authority itself became invalid — and neither classification was used as an escape hatch.

---

## Final Validation

- Gold JSON/MD: unchanged, hashes match frozen values.
- Evidence Trigger Matrix JSON/MD: unchanged, hashes match frozen values.
- Step-4 Final Acceptance Table JSON/MD: unchanged, hashes match frozen values (`799228ce...e08b732` / `0a4afdd4...2d1bd9d6`).
- `QQQ-A001-RATE-CUT-CYCLE` remains **FAIL**.
- `QQQ-A003-LIQUIDITY-EXPANSION` remains **REVIEW** (no deterministic resolution invented).
- MSFT Silver failures remain **non-blocking**.
- No production fix performed. No test changed. No threshold retuned. No taxonomy retuned.
- Provider calls = 0. TradingAgents calls = 0. Ticker runs = 0.
- All new files use `v0_2` naming.

**STEP 5 ONLY. DIAGNOSE, DO NOT FIX. GOLD REMAINS FROZEN. TRIGGER MATRIX REMAINS FROZEN. STEP-4 ACCEPTANCE REMAINS FROZEN.**
