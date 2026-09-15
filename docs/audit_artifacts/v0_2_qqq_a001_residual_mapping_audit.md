# v0.2 QQQ A001 Residual Mapping Audit

**Step 7A.1: adjudicate whether the 29 QQQ claims still mapped to A001 after the Step-7A repair are semantically legitimate.** Diagnostic gate before spending a new live QQQ run — no code changed, no test changed, no frozen authority touched.

## Purpose

Step 7A reduced offline A001 mappings on the authoritative QQQ run from 66 to 29. Surviving a new veto is not proof of validity. This audit independently classifies each of the 29 against A001's actual taxonomy semantics — never using "the mapper selected A001" as evidence of correctness — to decide whether a fresh, live QQQ validation run is warranted yet.

## Frozen Authority

All seven authorities verified byte-identical before this audit began and unmodified throughout: Gold Contract, Evidence Trigger Matrix, Final Acceptance Table, Acceptance Adjudication, Evidence Failure Analysis, and both Step-7A Remediation files (JSON + MD).

**Frozen QQQ A001 evidence trigger: `ABSENT`.** This audit does not, and cannot, rewrite that trigger.

## 66 → 29 Remediation Result

| Metric | Value |
|---|---:|
| Historical run | `f88c8956-cb62-48aa-9951-89f8e8a95f83` |
| Before Step 7A | 66 mapped |
| After Step 7A | 29 mapped |
| Vetoed by Step 7A | 37 |
| Positive controls (Step 7A) | 4/4 pass |
| Negative controls (Step 7A) | 6/6 pass |

## Residual Row-Level Audit

Each of the 29 was inspected independently against the actual claim text, factors, direction, and matched evidence stance — never against the fact that the mapper selected A001.

**Headline finding: 0 of 29 residual claims are `VALID_A001_SUPPORT`.**

| Classification | Count |
|---|---:|
| `VALID_A001_SUPPORT` | **0** |
| `A001_MENTION_ONLY` | 1 |
| `A001_OPPOSITION_OR_INVALIDATION` | 19 |
| `GENERIC_RATE_MACRO_CONTEXT` | 8 |
| `A003_LIQUIDITY_BETTER_FIT` | 0 |
| `A501_RECESSION_BETTER_FIT` | 0 |
| `A304_VALUATION_BETTER_FIT` | 0 |
| `OTHER_ALPHA_BETTER_FIT` | 0 |
| `AMBIGUOUS` | 1 |
| **Total** | **29** |

`valid_positive_a001`: **0 true, 1 uncertain, 28 false.**

## Valid A001 Support

**None found.** Not one of the 29 residual claims materially expresses actual rate cuts, a rate-cut cycle, clear monetary easing, falling policy/discount rates, or credible expected easing with an explicit cuts-direction. The single highest-scoring residual claim (`fundamental_agent:43`, score 0.8639, carrying the literal `Rate Cut Cycle` factor label) is a **generic conditional mechanism explainer** ("Falling rates...would tend to support valuations, while rising rates would pressure them") — it explains what *would* happen under a hypothetical, without asserting that rates are actually falling or that a cut cycle is underway or expected. This is the textbook case Section 8 warned against: keyword/factor density inflating score without directional content.

## Residual False Positives

**28 of 29 are clear false positives** (1 genuinely ambiguous, mixed-content case set aside):

- **19 — `A001_OPPOSITION_OR_INVALIDATION`.** Claims describing an *adverse* rate environment for growth assets: "rate headwind" (×5), "rate repricing" causing selloffs (×5), explicit rising-rate statements ("when discount rates rise," "rates are rising — as they are now," "far more sensitive to rising discount rates"), and explicit negations of the easing case ("reduces the case for Fed easing," "reduces case for Fed cuts," "a dramatic reversal from any lingering easing expectations"), plus an explicit hike assertion ("the market is pricing a hike"). None of these support A001's thesis — several are its direct opposite.
- **8 — `GENERIC_RATE_MACRO_CONTEXT`.** Generic rate-sensitivity framing with no direction stated at all (e.g. "QQQ is sensitive to the interest-rate environment," bare "Rate Sensitivity: High" metric labels, a pure non-farm-payrolls data point with no rate/Fed language in the claim text itself, a content-free "cost of capital" rhetorical fragment).
- **1 — `A001_MENTION_ONLY`.** A conditional hedge about a hike *not* being delivered — a hypothetical absence-of-hike, never an assertion of an actual cut.
- **1 — `AMBIGUOUS`** (`news_agent:22`): cites a Fed Governor's conditional preference to leave rates *unchanged* (not cut) as a "dovish counterpoint," while the claim's own stated base case is markets "pricing a hike." Even the dovish reference never describes a cut. Net framing leans hawkish, but the internal mix keeps this short of clean opposition.

**Noted discrepancy (not adjudicated, out of scope):** three residual rows (`sentiment_agent:49`, `bull_researcher:15`, `research_manager:8`) carry a shadow-classifier `matched_evidence_stance` of `supports_alpha` despite their actual text describing an adverse/rising-rate scenario for A001 — independently consistent with Step 6's `MENTION_VS_OPPOSITION_OVERCALL`-adjacent stance-calibration finding, flagged here for visibility only.

## Residual Error Mechanisms

| Mechanism | Count | Description |
|---|---:|---|
| `GENERIC_MACRO_OVERMATCH` | 19 | Generic "rate headwind"/"rate repricing"/"rate pressure"/sensitivity language with no explicit cut/easing assertion, and no Step-7A trigger phrase either |
| `NEGATION_MISREAD` | 3 | Explicit negation of the easing case ("reduces the case for...cuts/easing," "reversal from...easing expectations") not covered by the current veto |
| `RATE_DIRECTION_MISREAD` | 3 | Explicit rising-rate statements ("when discount rates rise," "rates are rising," "sensitive to rising discount rates") not covered |
| `MODALITY_MISREAD` | 2 | Conditional/hedged hike-absence framing, not a cut assertion |
| `KEYWORD_OVERMATCH` | 1 | Dense rate/cut vocabulary (including the literal `Rate Cut Cycle` factor label) with a purely conditional, non-directional mechanism explanation |
| `POST_DECISION_VETO_INCOMPLETE` | 1 | "pricing a hike" — an explicit hike assertion that escapes the Step-7A veto because that fix's hike-coverage requires "rate hike(s)"/"hike odds"/"probability or odds of a hike" phrasing; the bare "pricing a hike" construction (no "rate"/"odds"/"probability" immediately adjacent) is not covered — a concrete, identified gap, not a new/different mechanism |

**Total: 29.** The dominant mechanism (`GENERIC_MACRO_OVERMATCH`, 65.5% of residuals) is a distinct, intermediate class the Step-7A blocklist was never designed to catch: content that is topically about "the rate environment" being adverse or non-directional, without using any of the specific hike/hawkish/no-cut/rising-yield phrasings the existing veto enumerates.

## Consistency with Frozen ABSENT Trigger

**Fully consistent — and further corroborating.** Zero of the 29 residual claims constitute meaningful current Rate Cut Cycle evidence. The frozen trigger asked whether meaningful current easing evidence was present, not whether the words "rate cut" appeared anywhere in the corpus — and this row-level inspection confirms the answer remains no, independent of and in addition to the original Step-3 evidence-trigger work.

**Inconsistent with frozen trigger: NO.**

## Fresh-Run Readiness Decision

### READY_FOR_FRESH_QQQ_VALIDATION: **NO**

A systematic residual false-positive mechanism remains. 19/29 (65.5%) of the surviving mappings are `GENERIC_MACRO_OVERMATCH` — a repeatable semantic gap distinct from anything Step 7A targeted. A further 8 show explicit opposition/negation/rising-direction content that also escapes the current veto, plus one concrete, identified phrasing gap. **Zero of the 29 are genuine positive A001 evidence.** A fresh live QQQ run against comparable market conditions would very likely re-create a comparable pool of topically-matched-but-non-directional-or-opposing evidence, since the underlying LLM mapping tendency (topic match regardless of direction) that Step 7A only partially addressed is still fully intact for this broader class of phrasing.

This is exactly the "repeatable semantic gap" / "the live run would predictably re-create unsupported A001 evidence" condition this task's own gate defines as **not ready**.

### SECOND_REMEDIATION_RECOMMENDATION (not implemented)

**Residual mechanism:** `GENERIC_MACRO_OVERMATCH` (dominant, 19/29) plus `RATE_DIRECTION_MISREAD` (3), `NEGATION_MISREAD` (3), `MODALITY_MISREAD` (2), and the one identified `POST_DECISION_VETO_INCOMPLETE` phrasing gap.

**Affected claim IDs:** 27 of 29 rows (all except the two purely content-free rows — the "cost of capital" rhetorical fragment and the bare payrolls data point — which have no rate-direction language of any kind to gate on).

**Likely production location:**
- `comqutor_alpha/structure_engine/claim_semantics.py` — new positive-requirement predicate, symmetric counterpart to `ALPHA_SPECIFIC_INVALIDATION_PATTERNS`.
- `comqutor_alpha/structure_engine/alpha_mapper.py` — apply the positive-requirement gate in `map_claim_to_alpha`, alongside the existing Step-7A negative veto.

**Minimal conceptual fix:** Add a general **"Alpha-Specific Positive Requirement" gate**, symmetric to the Step-7A negative veto: for Alphas whose thesis requires directional confirmation (initially just A001), require the final `matched_alpha`'s own claim text to contain an explicit *directional* cut/easing cue drawn from a curated directional subset of the taxonomy's own A001 keywords (`rate cut`, `falling rates`, `lower rates`, `fed cut`, `easing cycle`) — explicitly **excluding** the taxonomy's own generic/non-directional keywords (`discount rate`, `duration`, `treasury yield`) from satisfying this positive gate alone, since those are topic-adjacent but direction-neutral (precisely why `fundamental_agent:43`, containing the literal `Rate Cut Cycle` factor label, still scored 0.8639 while asserting nothing directional). A claim lacking this positive cue is vetoed to `no_match` regardless of LLM selection or the negative veto's silence. This is more general and less enumeration-dependent than continuing to grow the negative blocklist, and would likely subsume most of the negative veto's role for A001 going forward.

**Required positive controls:**
- The same 4 Step-7A positive controls must still pass the new positive gate.
- New: a claim containing *only* a generic/non-directional A001 keyword (`discount rate`, `duration`, or `treasury yield`) with no cut/easing cue must **not** pass — proving the positive gate correctly excludes generic-keyword-only text.

**Required negative controls:**
- All 19 `GENERIC_MACRO_OVERMATCH` residual claims from this audit must fail the positive gate.
- The 3 `RATE_DIRECTION_MISREAD`, 3 `NEGATION_MISREAD`, and 2 `MODALITY_MISREAD` residual claims must also fail the positive gate independently.
- `bull_researcher:7`'s "pricing a hike" phrasing must fail the positive gate.

**Implementation status: NOT IMPLEMENTED** — recommendation only, per this task's explicit no-code-change authorization.

## Next Step

**SECOND_REMEDIATION (Step 7A.2)**: implement the Alpha-Specific Positive Requirement gate described above, add the listed positive/negative controls, re-run this same residual-audit methodology against the updated offline replay, and only then proceed to **Step 7B — one fresh QQQ validation run**.

---

## Complete Row Table (29 of 29)

| Claim ID | Agent | Short Meaning | Classification | Positive A001? | Direction | Rationale |
|---|---|---|---|---|---|---|
| `...sentiment_agent:34` | sentiment_agent | Chips shrugging off the rate headwind | A001_OPPOSITION_OR_INVALIDATION | False | NO_EASING_DIRECTION | "rate headwind" = anti-easing framing |
| `...sentiment_agent:45` | sentiment_agent | Semiconductor strength into rate headwind | A001_OPPOSITION_OR_INVALIDATION | False | NO_EASING_DIRECTION | "rate headwind" = anti-easing framing |
| `...sentiment_agent:49` | sentiment_agent | Long-duration growth under pressure, rate repricing | A001_OPPOSITION_OR_INVALIDATION | False | NO_EASING_DIRECTION | Bearish rate-repricing consequence claim |
| `...news_agent:12` | news_agent | NFP +162K, unemployment 4.1% | GENERIC_RATE_MACRO_CONTEXT | False | NO_EASING_DIRECTION | No rate/Fed language in claim text itself |
| `...news_agent:15` | news_agent | Resilient labor market reduces case for Fed easing | A001_OPPOSITION_OR_INVALIDATION | False | NEGATED_EASING | Explicit negation of easing case |
| `...news_agent:21` | news_agent | Reversal from lingering easing expectations | A001_OPPOSITION_OR_INVALIDATION | False | NEGATED_EASING | Explicit reversal FROM easing |
| `...news_agent:22` | news_agent | Waller: leave rates unchanged; market prices hike as base case | AMBIGUOUS | uncertain | CONDITIONAL_EASING | Mixed; even dovish ref is "unchanged" not "cut" |
| `...news_agent:48` | news_agent | Netflix drop on rate repricing | A001_OPPOSITION_OR_INVALIDATION | False | NO_EASING_DIRECTION | Hawkish-repricing consequence |
| `...news_agent:53` | news_agent | Strong economy reduces case for Fed cuts | A001_OPPOSITION_OR_INVALIDATION | False | NEGATED_EASING | Explicit negation of cut case |
| `...news_agent:55` | news_agent | Rate-Sensitive Growth theme, Netflix -4%, Bearish | A001_OPPOSITION_OR_INVALIDATION | False | NO_EASING_DIRECTION | Explicit bearish rate-repricing consequence |
| `...fundamental_agent:42` | fundamental_agent | QQQ sensitive to interest-rate environment | GENERIC_RATE_MACRO_CONTEXT | False | NO_EASING_DIRECTION | No direction specified |
| `...fundamental_agent:43` | fundamental_agent | Falling rates would tend to support valuations... | GENERIC_RATE_MACRO_CONTEXT | False | CONDITIONAL_EASING | Generic conditional explainer, not a directional assertion |
| `...fundamental_agent:48` | fundamental_agent | High-beta play on direction of rates/liquidity | GENERIC_RATE_MACRO_CONTEXT | False | NO_EASING_DIRECTION | No direction specified |
| `...fundamental_agent:67` | fundamental_agent | Rate Sensitivity: High (metric label) | GENERIC_RATE_MACRO_CONTEXT | False | NO_EASING_DIRECTION | Bare metric label, no direction |
| `...bull_researcher:7` | bull_researcher | Market pricing a hike; strong jobs report | A001_OPPOSITION_OR_INVALIDATION | False | NEGATED_EASING | Explicit hike assertion; escapes veto phrasing |
| `...bull_researcher:15` | bull_researcher | Chip complex shrugging off same pressure | A001_OPPOSITION_OR_INVALIDATION | False | NO_EASING_DIRECTION | Underlying "pressure" = rate pressure |
| `...bear_researcher:4` | bear_researcher | "On the Rate Headwind" (heading) | A001_OPPOSITION_OR_INVALIDATION | False | NO_EASING_DIRECTION | Anti-easing framing |
| `...bear_researcher:8` | bear_researcher | When discount rates rise, PV falls more for QQQ | A001_OPPOSITION_OR_INVALIDATION | False | NEGATED_EASING | Explicit rising-rate conditional |
| `...bear_researcher:13` | bear_researcher | Cracking under same rate pressure | A001_OPPOSITION_OR_INVALIDATION | False | NO_EASING_DIRECTION | Adverse rate-pressure framing |
| `...bear_researcher:15` | bear_researcher | Structural repricing of entire rate outlook | GENERIC_RATE_MACRO_CONTEXT | False | NO_EASING_DIRECTION | Generic repricing language, no explicit direction in isolation |
| `...bear_researcher:49` | bear_researcher | Rates are rising, as they are now | A001_OPPOSITION_OR_INVALIDATION | False | NEGATED_EASING | Clearest explicit current-rising-rate statement |
| `...bear_researcher:50` | bear_researcher | Rate environment actively undermining the cycle | A001_OPPOSITION_OR_INVALIDATION | False | NO_EASING_DIRECTION | Adverse/anti-easing framing |
| `...research_manager:8` | research_manager | QQQ sensitive to rising discount rates | A001_OPPOSITION_OR_INVALIDATION | False | NEGATED_EASING | Explicit rising-rate statement |
| `...aggressive_risk_analyst:11` | aggressive_risk_analyst | Hardware complex into the rate headwind | A001_OPPOSITION_OR_INVALIDATION | False | NO_EASING_DIRECTION | Anti-easing framing |
| `...conservative_risk_analyst:14` | conservative_risk_analyst | Sold off on rate repricing | A001_OPPOSITION_OR_INVALIDATION | False | NO_EASING_DIRECTION | Hawkish-repricing consequence |
| `...conservative_risk_analyst:27` | conservative_risk_analyst | "Ignores the cost of capital" | GENERIC_RATE_MACRO_CONTEXT | False | NO_EASING_DIRECTION | Content-free rhetorical fragment |
| `...conservative_risk_analyst:43` | conservative_risk_analyst | If the hike is not delivered, market will rally | A001_MENTION_ONLY | False | CONDITIONAL_EASING | Conditional hedge, not a cut assertion |
| `...neutral_risk_analyst:9` | neutral_risk_analyst | Selling off on rate repricing | A001_OPPOSITION_OR_INVALIDATION | False | NO_EASING_DIRECTION | Hawkish-repricing consequence |
| `...neutral_risk_analyst:16` | neutral_risk_analyst | Market digested the rate risk (technicals-focused) | GENERIC_RATE_MACRO_CONTEXT | False | NO_EASING_DIRECTION | Generic, technicals-dominant framing |

(Full claim/evidence text, match scores, and per-row source references are in the JSON companion file.)

---

**Production files changed: 0. Test files changed: 0. Provider calls: 0. TradingAgents calls: 0. Fresh ticker runs: 0. Gold changed: no. Trigger Matrix changed: no. Final Acceptance changed: no. Step-5 Adjudication changed: no. Step-6 Failure Analysis changed: no. Step-7A Remediation changed: no. Commits: 0. Pushes: 0. Destructive git operations: 0.**

**STEP 7A.1 ONLY. 29 RESIDUAL MAPPINGS AUDITED. NO CODE CHANGE. NO QQQ RUN. READY_FOR_FRESH_QQQ_VALIDATION = NO.**
