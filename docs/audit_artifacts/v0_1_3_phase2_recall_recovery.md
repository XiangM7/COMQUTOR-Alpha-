# v0.1.3 Phase 2 Legitimate Recall Recovery

Design/implementation phase. **Provider calls: 0. TradingAgents calls: 0. Ticker runs: 0. HEAD unchanged (`9f228723fad5406c72e62beca67ec70ea0fdb004`). No commit. No push.**

## John — Phase 2 Recall Recovery

```
Ticker  Alpha  Root Cause                                    Implemented?  Recovered?  Needs Fresh Run?
NVDA    A102   Research/query coverage gap (Provider-facing) NO            NO          YES
MSFT    A102   Second independent fact genuinely absent      NO            NO          YES (uncertain)
AMD     A102   Research/query coverage gap; no wrongly-       NO            NO          YES
                rejected explicit claim exists
TSM     A301   LLM provider-timeout data artifact (NOT the   NO            NO          YES (non-deterministic)
                ticker-specificity issue prior audit assumed)
MSFT    A304   Extraction blind spot needs regex-capable +   NO            NO          NO (needs a code
                negation-aware factor matching (broader                    architecture upgrade,
                than a phrase-alias fix)                                   not new research)

Current Alpha Hit:            61.0317%
Offline confirmed recovered:  0
Fresh-run dependent:          up to 3 (NVDA/MSFT/AMD A102, uncertain)
Projected maximum (Phase 2):  74.127%  (PROJECTION_ONLY, still short of 75%)
Gold unchanged:                YES
P0/P1 intact:                  YES
New regressions:               0
```

## Executive Summary

```
Targets reviewed:                    5
READY_TO_IMPLEMENT:                  0
IMPLEMENTED:                         0
DEFERRED_NOT_READY:                  5

Offline-replayable recovered hits:   0
Fresh-run-dependent potential:       up to 3 (uncertain)

Current official Alpha Hit:          61.0317%
Offline diagnostic Alpha Hit:        61.0317% (unchanged -- zero deterministic fixes implemented)
Projected maximum (Phase 2 set):     74.127%  PROJECTION_ONLY, NOT_ACCEPTANCE_RESULT

Can current Phase 2 target set plausibly reach >=75%:  NO (mathematically impossible --
  QQQ and SNDK, both out of scope, cap the macro-average below 75% regardless of Phase 2 success)

P0/P1 regressions:   0
New regressions:     0
Gold unchanged:      YES
```

**Headline**: zero code changes implemented. Rigorous, evidence-based investigation of all 5 targets found each requires either a live Provider/LLM call (forbidden this phase) or an architectural change broader than the "narrowest blind-spot fix" this task authorizes. Two targets — TSM A301 and MSFT A304 — were found to have **more precise root causes than the prior audits assumed**, materially superseding those earlier, more optimistic characterizations. This is reported as a discrepancy per Section 3's explicit instruction.

## NVDA A102

STRONG_GOLD. Inspected the actual research-agent prompts (`tradingagents/agents/analysts/{fundamentals,news,sentiment,market}_analyst.py`): each uses one generic, shared, ticker-agnostic, Alpha-agnostic `system_message` with zero concept of "A102" or inference-specific facts. Confirmed via raw data: 14 raw "inference" occurrences (8 unique), all competitive-threat framed; zero mention anywhere of token volume, tokens generated/processed, or serving demand. A neutral, bounded prompt addition is conceivable, but editing this shared Provider-facing prompt template is exactly the kind of "broad research-agent redesign" Section 7 says to mark **DESIGN_DEFERRED** rather than implement, and it cannot be validated without a live Provider call. **DEFERRED_NOT_READY.**

## MSFT A102

STRONG_GOLD. P0/P1's correctness fix remains intact and unchanged (ticker-specific evidence 0→1, score 34.9674→44.9674). Searched all 12 raw agent outputs for every "inference" mention: exactly one raw statement exists (fundamental_agent's Copilot/Azure claim), duplicated only within that same report, correctly deduped when restated by bull_researcher, correctly excluded when quoted by bear_researcher. **Classification: F — legitimately absent.** No research/extraction/dedupe bug found. Per Section 9's explicit permission, this is left as `candidate` — acceptable. **DEFERRED_NOT_READY.**

## AMD A102

STRONG_GOLD. Re-confirmed 0/8 MI-series claims are truly A102-eligible (not re-litigated per Section 10). Searched raw data for AMD-specific inference-deployment/serving/token content: only one generic, industry-wide statement exists, already correctly excluded as non-ticker-specific. No explicit AMD-specific inference claim exists anywhere that current semantics wrongly reject — Section 11's semantic-change stop condition is not met. **DEFERRED_NOT_READY.**

## TSM A301

**Discrepancy found.** Re-traced the current state directly: score 44.7724, `local_structure_support` raw 0.0, one incident graph edge, zero qualifying. Two candidate edges examined:

1. `ai_demand→tsm_revenue_growth` (neutral_risk_analyst): the underlying claim genuinely never mentions TSM/TSMC/Taiwan Semiconductor anywhere in its full text — correctly `SECONDARY_NOT_TICKER_SPECIFIC`. No fix possible without fabrication.
2. `ai_infrastructure→tsm_revenue_growth` (fundamental_agent:claim:42, **"TSM has delivered two consecutive years of >30% revenue growth... driven by the AI infrastructure buildout"**): this claim IS ticker-specific, IS Primary, and the **deterministic** Alpha Mapper layer scored it a clean, eligible A301 match (`deterministic_top_alpha='A301'`, score 0.7596). But its final `matched_alpha` is `None` because the original run's LLM call for this claim **timed out** (`alpha_match_fallback_reason='provider_timeout'`). Per this codebase's own documented, intentional Pure-LLM-Semantic-Authority design, a timeout never falls back to the deterministic answer — a deliberate invariant, not a bug.

This is a **materially different root cause** than the prior audit's "S6 locality-qualification" characterization. The real blocker is a Provider-call artifact from the original run, correctable only by a live LLM retry (forbidden this phase) or a separately-authorized decision about timeout-retry policy — not a structure-extraction or ticker-specificity bug. **Offline counterfactual** (if claim:42 were granted A301 commitment): local structure raw would rise toward 50.0 (+10.0 contribution), projecting a new score of **≈54.77 — crossing 50**. Not implemented, since doing so requires overriding the intentional no-fallback design. **DEFERRED_NOT_READY.**

## MSFT A304

**Discrepancy found.** Claim:82 ("Any slowdown in Azure growth could trigger multiple compression") is confirmed `PRIMARY_QUALIFIED`/eligible/`factor_score=1.0`. Traced the exact extraction blind spot: `structure_extractor.py::_extract_edges()` requires **≥2 distinct factors** to form any edge; this claim produces only one (`Valuation Risk`, via "multiple compression"). No `FACTOR_ALIASES` entry recognizes "slowdown in Azure growth" as a second, growth-adjacent factor. Separately confirmed the causal grammar is already sufficient — "trigger" is already a recognized `FORWARD_CAUSAL_VERB` — so the *only* missing piece is the second factor.

Searched all six runs for the same pattern: **near-identical phrasing recurs in NVDA, TSM (×2), and AMD** ("Any slowdown in AI infrastructure spending would directly pressure revenue"; "any slowdown in hyperscaler spending/capex..."; "AI demand slowdown could trigger significant multiple compression"). This is a real, recurring, generalizable pattern — not an MSFT-only one-off. But the existing `FACTOR_ALIASES`/`term_in_text` matcher is **literal-phrase-only**; every found example uses a non-adjacent "slowdown in [X] growth/spending/capex" word order that no literal phrase alias can represent without a broader regex-capability upgrade (blast radius across all 20+ factor categories, not just this one). A bare "slowdown" alias — the only literal option that would catch the real examples — was tested against MSFT's own separate claim, **"...not a slowdown scenario"**, and would incorrectly tag it despite its explicit negation: a concrete, demonstrated regression risk, not a hypothetical one. **DEFERRED_NOT_READY.**

## Implementation Changes

None. Zero production files changed, zero test files changed.

## Targeted Tests

No new tests added (nothing implemented). Re-ran existing suites: `tests/test_p0_p1_evidence_correctness_fix.py` — 26 passed; the 3 SHA-guard tests — 3 passed.

## Offline Replay

Re-verified (no delta possible, since no code changed) that all 5 targets' current persisted scores match the prior audits exactly. NVDA A102=0.0, MSFT A102=44.9674, AMD A102=35.6327, TSM A301=44.7724. `FRESH_RUN_REQUIRED_FOR_REAL_VALIDATION` applies to the three A102 research-coverage targets — but note TSM A301 and MSFT A304 are **not** fixable by a fresh run alone either (TSM needs the same LLM call to not time out — non-deterministic even on rerun; MSFT A304 needs a COMQUTOR-side code upgrade, not new research).

## Alpha Hit Projection

- **A. Real offline-replayable conversions**: 0
- **B. Requires-fresh-run potential**: NVDA A102, MSFT A102 (uncertain), AMD A102
- **C. Still unresolved**: TSM A301 (provider-timeout/architecture decision), MSFT A304 (regex + negation upgrade)
- **Current official**: 61.0317%. **Offline diagnostic**: 61.0317% (unchanged).
- **Maximum plausible projection** if all 5 Phase 2 targets legitimately recovered: **74.127% — PROJECTION_ONLY, NOT_ACCEPTANCE_RESULT.**

## Minimum 75% Math Recheck

| Ticker | Denom. | Current hits | Current rate | Max hypothetical (Phase 2) |
|---|---:|---:|---:|---:|
| NVDA | 7 | 5 | 71.4286% | 85.7143% (+A102) |
| QQQ | 6 | 3 | 50.0000% | 50.0000% (out of scope) |
| MSFT | 6 | 3 | 50.0000% | 83.3333% (+A102, +A304) |
| SNDK | 5 | 2 | 40.0000% | 40.0000% (out of scope, negative control) |
| TSM | 6 | 5 | 83.3333% | 100.0000% (+A301) |
| AMD | 7 | 5 | 71.4286% | 85.7143% (+A102) |

Current macro-average: **61.0317%**. Maximum hypothetical macro-average with all 5 Phase 2 targets recovered: **74.127%**.

**Is ≥75% mathematically reachable from the current Phase 2 target set? NO.** QQQ and SNDK are untouched (out of scope) and their unrecovered per-ticker rates mathematically cap the macro-average below 75% regardless of perfect Phase 2 success — reaching 75% would additionally require at least one QQQ and/or SNDK conversion, both explicitly excluded from this task.

## Regression Safety

AMD A201 contaminated claim remains excluded (C1=0); `company_names` propagation remains active; QQQ ETF behavior unchanged; SNDK A102 remains inactive; P0/P1 CLOSED PASS intact; SHA guards 3/3 pass; targeted tests 26/26 pass; main conflict admissions unchanged (NVDA/TSM/AMD: `A101__A304`; QQQ: `A304__A601`; MSFT/SNDK: none). **New regressions: 0** (zero code changed).

## Deferred Work

All 5 targets, each with the specific blocking condition documented above — flagged for future, separately-authorized, properly-scoped design tasks (a Provider-prompt authorization process for the three A102 research gaps; a timeout-retry policy decision for TSM A301; a regex-capable, negation-aware factor-extraction design for MSFT A304).

---

## Final Validation

- Gold v1 SHA-256 / Gold Validity SHA-256: unchanged
- P0 contamination / P1 company_names: still fixed
- SNDK A102 negative control / QQQ ETF: intact / unchanged
- No thresholds/taxonomy/Gold/B1/B2/B4/Alpha-Hit-rule changes
- Full backend new regressions: 0 (no code changed)

**Provider calls: 0. TradingAgents calls: 0. Ticker runs: 0. No commit. No push. No destructive git operations.**
