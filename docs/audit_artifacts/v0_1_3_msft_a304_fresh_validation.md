# v0.1.3 MSFT A304 Fresh Validation

One authorized fresh production run. **Ticker: MSFT only. Provider calls: occurred (as authorized). TradingAgents calls: occurred (as authorized). Ticker runs: 1.** HEAD unchanged (`9f228723fad5406c72e62beca67ec70ea0fdb004`). No commit. No push. No code changed during or after validation.

## Executive Summary

```
Old MSFT run:              43472ace-454f-4c69-892c-adca91c25be7
New MSFT run:               64568bfb-fe0c-453c-9872-831a8dc339a0

Run complete:                YES

A304 old:                    43.3642 / candidate   (corrected -- see note below)
A304 offline post-fix:       48.3642 / candidate   (corrected -- see note below)
A304 fresh:                  71.1556 / dominant / DETECTED

Relevant fresh causal edge (via THIS fix):   NO -- 0 pattern matches, 0 new edges
False-positive structures:                    0
A304 Provider impacted:                       NO

Validation result:  CASE_M3_FRESH_RESEARCH_NOT_COMPARABLE
                     (A304 itself reached dominant via an UNRELATED,
                      pre-existing canonical-relation pathway, NOT this fix)

Keep A304 fix:       YES

Old MSFT Gold Hit:   3/6 (50.0%)
New MSFT Gold Hit:   4/6 (66.67%)
Two-run mean:        58.33%

Official six-ticker: 61.0317% unchanged
No code changed during validation.
```

## Important Correction to the Prior Offline Replay

Before reporting the three-way comparison, a methodological error in the **prior** task's offline replay (`v0_1_3_msft_a304_negation_extraction_fix`) was found and corrected. That replay called `build_and_score_structure_graph()` without supplying `run_timestamp`/`as_of`, causing the `recency` component to fall back to a generic value (raw 50.0, contribution 5.0) instead of the true run's actual value (raw 100.0, contribution 10.0, `age_days=0`). This **−5.0** artifact applied uniformly to both the "before" and "after" simulations in that task, which coincidentally made the previously-reported "after" value (43.3642) equal to the *true, unmodified, persisted* "before" value (also 43.3642) — a coincidence, not evidence the fix had no effect.

Re-running the identical replay with the correct `run_timestamp='2026-09-04'`/`as_of='2026-09-04'` (read from the persisted `structure_graph.json`'s own fields) produces a "before" (patterns disabled) score of **43.3642 — an exact match to the true persisted ground truth**, confirming the replay methodology is otherwise sound, and a corrected "after" (current production code) score of **48.3642**.

**What remains true**: the delta finding (`local_structure_support` raw 0.0→25.0, contribution +5.0, exactly one new qualifying edge, every other component unaffected) is fully correct and unaffected — the uniform recency artifact cancelled out in the before/after delta. **What was wrong**: the prior task's reported absolute numbers (38.3642 / 43.3642); the corrected, verified absolutes are **43.3642 / 48.3642**. This report uses the corrected values throughout.

## John — MSFT A304 Fresh Validation

```
Metric               | Old        | Offline Fix (corrected) | Fresh
-----------------------|------------|--------------------------|----------
A304 Score             | 43.3642    | 48.3642                  | 71.1556
A304 Level              | candidate  | candidate                | dominant
A304 Detected           | NO         | NO                       | YES
Local Structure         | 0 edges    | 1 edge (raw 25.0)        | 1 qualifying (of 3 incident)
Qualifying Evidence     | 14         | 14                       | 30

Fresh causal edge (via this fix):  NO -- 0/1005 fresh claims matched the new patterns
False positives:                    0
Provider impacted:                  NO
Validation:                         CASE_M3_FRESH_RESEARCH_NOT_COMPARABLE
                                     (A304's fresh dominant status is via an
                                      UNRELATED canonical-relation pathway)
Next:                                NEXT_A102_RESEARCH

Official benchmark unchanged: 61.0317%
```

## Pre-Run Snapshot

HEAD `9f228723fad5406c72e62beca67ec70ea0fdb004`; Gold v1/Validity SHA-256 confirmed unchanged. Provider configuration (`comqutor_deepseek_default_v1`, DeepSeek `deepseek-v4-flash`, thinking disabled, 1 debate/1 risk round) and evidence-stance retry policy (2 retries / 3 max attempts) confirmed unchanged and identical to the old authoritative run. All six closed-status prerequisites (P0/P1, Provider Health, Measurement Foundation, Recorder Health, Evidence-Stance Retry Fix, A304 Extraction Fix) reconfirmed intact before execution.

**Operational note**: no server process was running at task start; Docker and Postgres were also stopped. Both were started fresh (`docker compose up -d postgres`, then the approved `scripts/start_live_comqutor.sh` launcher, new PID 27595 started `11:49:28`, well after the fix files' last modification at `11:13:13`) — guaranteeing the fresh run executed the current, fixed code.

## Run Execution

- **New run**: `64568bfb-fe0c-453c-9872-831a8dc339a0`
- Submitted via `POST /api/research {"ticker":"MSFT","force_refresh":true}` → `cache_disposition: force_refreshed`
- Started `2026-09-10T18:49:55Z`, completed `2026-09-10T20:27:12Z` — **97.28 minutes**
- No configuration differences from the old authoritative run found.

## Run Validity

**Run completed: YES. Semantic status: PASS. Artifact completeness: 9/9.** Graph: 10 nodes, 10 edges. 1005 claims present. Alpha outputs, structure artifacts, and Provider logs all present and readable. **Data Sanity: ok.** Not `CASE_M5_RUN_INVALID`.

## Fresh A304-Relevant Research

Scanned all 1005 fresh claims for adverse-growth/valuation-compression keywords: **97 matched.** This run's actual narrative is a **macro/rate-driven** multiple-compression debate (Fed rate-cut-cycle repricing, rising discount rates, a 27.8x trailing multiple vs. SPY's stronger return) — **not** a growth-deceleration-driven narrative like the old run's claim:82.

A related growth thread was found: *"slowing growth and softer bookings"* (the Dynamics 365 narrative), appearing across several agents. It does **not** match any of the 7 `FACTOR_ALIAS_PATTERNS` — those patterns require "slowdown", "decelerating", "growth deceleration/deterioration", "slower", or "weaker" forms; "**slowing** growth" was deliberately excluded in the prior task (to avoid firing on its own negation, "growth is NOT slowing", with no required-test benefit at the time).

A genuine live negative-control instance was also found: `fundamental_agent:claim:95` — *"Revenue growth is accelerating, not decelerating: +17.8% YoY..."* (`assertion_status: negated`) — correctly produces **no** adverse structure.

## Comparable Positive Structures

**Zero** claims in the fresh corpus matched any of the 7 patterns — verified directly by pattern search, not merely inferred from an absent edge. The new extraction capability was **not exercised** in this run, neither positively nor negatively. This is a legitimate, expected outcome of this run's actual research content, not a defect.

## False-Positive Structure Scan

Before/after full-pipeline replay (patterns enabled vs. disabled) on this run's own persisted records: **0 new edges, 0 removed edges, 0 alpha score/status changes** attributable to the patterns. Of the 97 keyword-matching claims: 0 `TRUE_POSITIVE`, 1 explicit `NEGATED_CORRECTLY_EXCLUDED` instance identified, the large majority `DESCRIPTIVE_CORRECTLY_EXCLUDED` (technical-indicator "compression"/"contraction" — ATR, MACD, volatility — entirely unrelated to Revenue Growth/Valuation Risk), several `RISK_ONLY_CORRECTLY_EXCLUDED` (Valuation Risk recognized alone via its pre-existing alias, no adverse-growth pairing attempted), 0 `AMBIGUOUS`. **`UNEXPECTED_FALSE_POSITIVE = 0`** — clean closure criterion met.

## A304 Final State (Fresh)

| | Value |
|---|---|
| Score | 71.1556 |
| Level | **dominant** |
| Detected | **YES** |
| Ticker-specific evidence | 14 |
| Unique/qualifying evidence | 30 |
| Distinct supporting agents | 6 |
| Incident graph edges | 3 |
| Qualifying local edges | 1 |
| Ceiling / reason codes | none / `[]` |

**The one qualifying local edge is `ai_capex → valuation_risk` (causal, asserted), sourced via `tradingagents_canonical_relation`** — TradingAgents' own LLM canonical-relation output, entirely independent of the new `FACTOR_ALIAS_PATTERNS` mechanism. The other two incident edges (`valuation_risk → msft_revenue_growth`, conflicting; `rate_cut_cycle → valuation_risk`, supportive) are also canonical-relation-sourced and non-qualifying for A304's local-structure count.

## A304 Three-Way Comparison

| Metric | Old Persisted | Offline Post-Fix (corrected) | Fresh Post-Fix |
|---|---:|---:|---:|
| Score | 43.3642 | 48.3642 | 71.1556 |
| Level | candidate | candidate | **dominant** |
| Detected | NO | NO | **YES** |
| Local structure edges | 0 | 1 | 1 (of 3 incident) |
| Local structure raw support | 0.0 | 25.0 | n/a (canonical-relation-sourced) |
| Ticker-specific evidence | 5 | 5 | 14 |
| Qualifying evidence | 14 | 14 | 30 |

The offline-derived result is explicitly **not** an official run and is not treated as one. Fresh A304's recovery is **not** attributable to the offline-validated extraction fix — confirmed by the zero-new-edges finding above.

## Live Validation Classification

**`CASE_M3_FRESH_RESEARCH_NOT_COMPARABLE`** — for the specific extraction capability under test. The fresh corpus does not contain legitimate growth-slowdown-phrased content matching any of the 7 supported forms: zero pattern matches, zero new edges, confirmed by direct search and by full before/after replay. This makes the run inconclusive for validating **this specific fix** live.

**Important disambiguation**: A304 *the Alpha* independently reached `dominant`/detected status this run — via a completely separate, pre-existing mechanism (`tradingagents_canonical_relation` edges), driven by this run's genuinely different (rate-and-capex-driven) research narrative. This Gold-adjacent outcome is **not** evidence for or against the extraction fix and must not be conflated with it, per this task's own explicit instruction not to judge the fix by unrelated Gold outcomes.

`CASE_M1` is not selected (A304's recovery is not attributable to this fix). `CASE_M2` is not selected (A304 in fact reached ≥50, via the unrelated pathway). `CASE_M4` is not selected (A304 confirmed not Provider-impacted). `CASE_M5` is not selected (run is fully valid).

## Provider Health

`provider_health: PROVIDER_DEGRADED`, `provider_failure_events: 82`, `semantic_critical_failure_events: 70`, `alpha_classifier_final_orphans: 2`, `evidence_stance_final_orphans: 11`, `structure_extractor_final_orphans: 6`, `provider_final_orphans_total: 19`, `impacted_alpha_ids: []`, `benchmark_review_required: false`. **A304 Provider impacted: NO.**

## Evidence-Stance Retry Observation (Not Used to Judge A304)

Attempt distribution: 26/18/11 (attempts 1/2/3). Retry-count distribution: 30 calls at 0 retries, 8 at 1 retry, 18 at 2 retries (i.e. reached the 3rd attempt). **7 third-attempt successes, 11 third-attempt exhaustions** (final stance orphans). Retry policy confirmed unchanged (2 retries / 3 max attempts). A304's own lineage is entirely canonical-relation-sourced and unaffected by evidence-stance retries — this data is reported for completeness only.

## Recorder Health

`recorder_failure_events: 345`, `recorder_health: RECORDER_DEGRADED`, `canonical_semantic_losses: 0`. Kept separate from Provider semantic impact, per architecture.

## All Gold Alphas — Old vs. New

| Alpha | Old | New | Provider Impacted | Drift Class |
|---|---|---|---|---|
| A101 | 55.6974 / active / HIT | 37.0165 / candidate / miss | NO | RESEARCH_VARIANCE |
| A102 | 34.9674 / candidate / miss | 41.9468 / candidate / miss | NO | RESEARCH_VARIANCE |
| A103 | 86.4726 / dominant / HIT | 82.6727 / dominant / HIT | NO | RESEARCH_VARIANCE |
| A301 | 65.1479 / active / HIT | 70.0 / active / HIT | NO | RESEARCH_VARIANCE |
| A304 | 43.3642 / candidate / miss | 71.1556 / dominant / HIT | NO | RESEARCH_VARIANCE (unrelated pathway) |
| A601 | 32.7558 / candidate / miss | 66.5385 / active / HIT | NO | RESEARCH_VARIANCE |

## MSFT A102 — Side Observation Only

| | Old | New |
|---|---:|---:|
| Score | 34.9674 | 41.9468 |
| Level | candidate | candidate |
| Ticker-specific evidence | 0 | 2 |
| Unique qualifying evidence | 1 | 3 |
| Distinct agents | 1 | 2 |

A102 remains `candidate` in both runs; evidence availability improved modestly but not decisively. **No code change authorized or made for A102 in this task.**

## Two-Run MSFT Reproducibility (Diagnostic Only)

Old Gold Hit **3/6 (50.0%)**; New Gold Hit **4/6 (66.67%)**; two-run mean **58.33%**. Per-Gold-Alpha detection frequency: A101=0.5, A102=0.0, A103=1.0, A301=1.0, A304=0.5, A601=0.5. Gold detected-set Jaccard **0.4**; all-Alpha detected-set Jaccard **0.2857**. Variable Gold Alphas: **A101, A304, A601**. **Not promoted to the official benchmark.**

## Main Conflict

Old authoritative: `NO_ADMITTED_MAIN_CONFLICT`. Fresh: **`A301__A304`, admitted**, `conflict_score=11.2814` (low), `bull_score=70.0` (A301), `bear_score=71.1556` (A304). **Admission changed: YES.** Trace: both A301 (Revenue Expansion, bull) and A304 (Multiple Compression, bear) independently reached qualifying strength this run with sufficient distinct-agent/evidence-group support to pass B2 admissibility (`week4.conflict_admissibility.b2.v1`) — a legitimate, unmodified conflict admission driven by this run's own research content and A304's unrelated canonical-relation-driven recovery, not by the extraction fix.

## P0/P1 Validation

**P0: PASS** — 0 competitor-only-mentioning claims (without an MSFT/Microsoft term) found this run; the narrow veto simply did not encounter its trigger pattern, consistent with its documented rare-firing design. **P1: PASS** — "Microsoft" (40) and "MSFT" (121) mentions present; alias recognition confirmed active on live data.

## Other Alpha Drift

A001 (RESEARCH_VARIANCE, active→candidate), A003/A201 (unchanged), A501 (RESEARCH_VARIANCE, candidate→active). No `PROVIDER_VARIANCE` or `UNEXPLAINED` classification was needed — Provider Health confirms `impacted_alpha_ids=[]`, and every observed change traces to ordinary research-content differences between two independent live runs, consistent with the research-variance pattern documented throughout this whole v0.1.3 effort.

## No Patch After Result

`factor_normalizer.py`, `relation_grammar.py`, `week2_llm.py`, the activation scorer, tests, Provider settings, and Gold were all confirmed **unmodified** during and after this validation.

## Next Development Step

**`NEXT_A102_RESEARCH`.** The extraction fix is sufficiently validated at the design/deterministic-test/corpus-blast-radius level (21 unit tests, 186 total scanned claims across both live MSFT runs' corpora combined, zero false positives in either). This run surfaced no genuine extraction defect independent of evidence sufficiency — it simply lacked the specific supported phrasing. No further A304 extractor engineering is justified. MSFT A102 remains the clearer, more concrete open item.

## Keep A304 Fix?

**`KEEP_A304_FIX`.** Generic extraction behavior is correct (21 deterministic tests plus this run's clean, zero-false-positive live exposure). No false positives occurred. Regression controls remain valid (the live "accelerating, not decelerating" instance was correctly excluded via pre-existing mechanisms). Fresh behavior is fully consistent with intended semantics — the fix had no qualifying input to act on this run, an honest, expected outcome, not a failure. A304 crossing 50 played no role in this recommendation.

---

## Final Validation

Exactly one ticker run (MSFT only); no second MSFT run; no other ticker. Gold v1 SHA256 `99b1cd0247637054de360c3b5c0c00c7d8052152f3db1d29045eae1850bd8e9a` unchanged. Gold Validity SHA256 `3643ea45168c029d7c2a2ceb6d1d61cac3d5de80770d3dccb1f57d005c0c1cdf` unchanged. Frozen ledger unchanged. Official Alpha Hit unchanged at 61.0317%. Production code changed during validation: 0. Tests changed during validation: 0. A304 implementation, evidence-stance retry policy, Provider settings, and P0/P1 behavior all confirmed unchanged. **Commits: 0. Pushes: 0. Destructive git operations: 0.**
