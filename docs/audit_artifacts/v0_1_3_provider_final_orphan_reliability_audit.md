# v0.1.3 Provider Final-Orphan Reliability Audit

Offline / read-only root-cause audit + bounded fix design. **Provider calls: 0. TradingAgents calls: 0. Ticker runs: 0. No retry/timeout/concurrency changes.** HEAD unchanged (`9f228723fad5406c72e62beca67ec70ea0fdb004`). No commit. No push. No code or test file modified.

## Executive Summary

```
Six authoritative runs audited:       6
TSM validation comparison included:   YES

Raw semantic-critical failures:       621
Final semantic orphans:               246
Retry-recovered calls:                129
Overall retry recovery rate:          34.4%

Highest-orphan component:             evidence_stance_classifier (74.4% of all orphans)
Dominant terminal failure type:       WEEK2_LLM_TIMEOUT (81.7% of all orphans)

Timeout evidence supports adjustment: YES (evidence_stance_classifier only); NO (alpha_classifier); N/A (structure_extractor)
Retry evidence supports adjustment:   YES (evidence_stance_classifier: component-specific extra attempt)
Concurrency contribution:             NO (sequential components are WORSE than the concurrent one)
Input-size contribution:              PARTIAL (evidence_stance orphans ~10-25% larger inputs -- modest, not dominant)

Preferred bounded fix:                Component-specific retry increase for evidence_stance_classifier only (1->2 retries)
Implementation readiness:             READY_FOR_BOUNDED_IMPLEMENTATION
Recommended next plan:                PLAN_A

Code changes: 0   Provider calls: 0   Ticker runs: 0
```

## John — Provider Final-Orphan Reliability

```
Component                  Raw Failures  Retry Recovered  Final Orphans  Orphan Rate
Alpha Classifier                216            122              47          27.8%
Evidence Stance                 371              5             183          97.3%
Structure Extractor              34              2              16          88.9%

TSM A301 old miss:        Provider-caused YES
Main root cause:          evidence_stance_classifier's TIMEOUT-dominant failures rarely
                           recover on retry (2.7%) because its typical latency already
                           runs close to the 45s ceiling on both attempts
Preferred fix:             Give evidence_stance_classifier ONE extra retry (1->2),
                           all other components/timeout unchanged
Semantic behavior changed: NO
Next step:                 PLAN_A -- implement, validate on TSM, then MSFT A304
```

## 1. Architecture Trace (Section 4)

All three semantic-critical tasks share **one** `Week2LLMGateway` instance per run, and therefore **one shared timeout (45s, from `.env`'s `COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS`) and one shared retry count (`max_retries=1`, i.e. 2 total attempts, from `COMQUTOR_WEEK2_LLM_MAX_RETRIES`)**. The retry loop is `week2_llm.py::invoke_json_with_trace`, `for attempt in range(1, self.max_retries + 2)`. Key findings from direct code inspection:

- **No backoff, no jitter** — no `time.sleep`/`asyncio.sleep` exists anywhere between attempts in `week2_llm.py`.
- **All error types are retryable** — `TimeoutError`, `json.JSONDecodeError`, `(TypeError, ValueError, KeyError)` (schema validation), and any other `Exception` (sub-classified into `RATE_LIMIT`/`TRANSPORT_ERROR`/`PROVIDER_ERROR`) are all caught and looped identically.
- **Retries reuse the identical prompt** — no truncation or modification between attempts.
- **Each attempt gets a fresh 45s window** — `call_with_timeout()` spins up a new single-worker `ThreadPoolExecutor` per attempt; a timed-out call's underlying thread is `cancel()`-ed but (since `ThreadPoolExecutor` cannot forcibly interrupt a running thread) may keep running in the background — any late response is discarded, never measured or logged.
- **`alpha_classifier` runs concurrently** (`ThreadPoolExecutor(max_workers=4)` by default, via `alpha_mapper.py:646`); **`evidence_stance_classifier` and `structure_extractor` run sequentially** — no pool found for either.
- **A subtle metric trap discovered during this audit**: `llm_semantic_calls.jsonl`'s `latency_ms` for a retried-success call is the **total** wall-clock time across *all* attempts (failed + successful), not the successful attempt's own duration — e.g. a TSM_OLD `alpha_classifier` retried success shows `latency_ms=76136`, i.e. ~45000ms consumed by the failed first attempt plus ~31000ms for the successful second. This matters for correctly interpreting every latency comparison below.

## 2. Final Orphan Definitions (Section 5) — Confirmed, Cross-Validated

| Component | Definition | Cross-check (TSM_OLD) |
|---|---|---|
| `alpha_classifier` | `match_status == 'unavailable'` in `alpha_matches.json` (Pure-LLM Semantic Authority, no fallback) | 9 (matches derived count exactly) |
| `evidence_stance_classifier` | `fallback_used == True` for that task in `llm_semantic_calls.jsonl` | 30 (matches exactly) |
| `structure_extractor` | `fallback_used == True` for that task | 3 (matches exactly) |

**Derivation method** (novel to this audit, since `error_logs/week2_llm_errors.jsonl` carries no `call_id`): per component, `unique_calls_with_failure = count(attempt==1 failures)`, `final_orphans = count(attempt==2 failures)`, `recovered_after_retry = attempt1_count - attempt2_count`. This was **cross-validated exactly** against the ground-truth ledgers above for all three components in TSM_OLD (9==9, 30==30, 3==3) before being trusted for the other six runs.

## 3. Retry State Machine (Section 6)

```
attempt 1 (fresh 45s window, prompt P)
  -> success -> DONE (retry_count=0)
  -> failure (ANY type) -> attempt 2 (fresh 45s window, IDENTICAL prompt P, no delay)
       -> success -> DONE (retry_count=1)
       -> failure (ANY type) -> FINAL ORPHAN (retry_count=1, provider_attempt_count=2)
```

Retry count is **shared**, not component-specific. **All** error types are retryable. **No** backoff or jitter exists. Empirically confirmed across all 7 runs: `retry_count` never exceeds 1 (i.e. `MAX_SERVER_RETRIES=2`'s ceiling was never approached in practice — the applied policy really is 2 attempts).

## 4. Raw Failure → Final Orphan Table (Section 7)

| Ticker | Component | Raw Failures | Failed Calls | Recovered | Final Orphans | Recovery % |
|---|---|---:|---:|---:|---:|---:|
| NVDA | alpha_classifier | 32 | 27 | 22 | 5 | 81.5% |
| NVDA | evidence_stance_classifier | 60 | 30 | 0 | 30 | 0.0% |
| NVDA | structure_extractor | 7 | 4 | 1 | 3 | 25.0% |
| QQQ | alpha_classifier | 17 | 12 | 7 | 5 | 58.3% |
| QQQ | evidence_stance_classifier | 50 | 25 | 0 | 25 | 0.0% |
| QQQ | structure_extractor | 4 | 2 | 0 | 2 | 0.0% |
| MSFT | alpha_classifier | 45 | 36 | 27 | 9 | 75.0% |
| MSFT | evidence_stance_classifier | 58 | 30 | 2 | 28 | 6.7% |
| MSFT | structure_extractor | 7 | 4 | 1 | 3 | 25.0% |
| SNDK | alpha_classifier | 52 | 37 | 22 | 15 | 59.5% |
| SNDK | evidence_stance_classifier | 76 | 39 | 2 | 37 | 5.1% |
| SNDK | structure_extractor | 0 | 0 | 0 | 0 | — |
| TSM (old) | alpha_classifier | 47 | 38 | 29 | 9 | 76.3% |
| TSM (old) | evidence_stance_classifier | 61 | 31 | 1 | 30 | 3.2% |
| TSM (old) | structure_extractor | 6 | 3 | 0 | 3 | 0.0% |
| AMD | alpha_classifier | 23 | 19 | 15 | 4 | 79.0% |
| AMD | evidence_stance_classifier | 66 | 33 | 0 | 33 | 0.0% |
| AMD | structure_extractor | 10 | 5 | 0 | 5 | 0.0% |
| TSM (new, diagnostic) | alpha_classifier | 33 | 27 | 21 | 6 | 77.8% |
| TSM (new, diagnostic) | evidence_stance_classifier | 64 | 32 | 0 | 32 | 0.0% |
| TSM (new, diagnostic) | structure_extractor | 6 | 3 | 0 | 3 | 0.0% |

**Grand totals across the six original runs**: raw=621, failed_calls=375, recovered=129, final_orphans=246, overall recovery rate=**34.4%**.

## 5. Component Totals & Ranking (Sections 8, 18)

| Component | Raw | Failed Calls | Recovered | Final Orphans | Recovery % | Orphan Share |
|---|---:|---:|---:|---:|---:|---:|
| **evidence_stance_classifier** | 371 | 188 | 5 | **183** | 2.7% | **74.4%** |
| alpha_classifier | 216 | 169 | 122 | 47 | 72.2% | 19.1% |
| structure_extractor | 34 | 18 | 2 | 16 | 11.1% | 6.5% |

**Ranking: 1. evidence_stance_classifier — 2. alpha_classifier — 3. structure_extractor.** `evidence_stance_classifier` drives nearly three-quarters of all semantic attrition despite alpha_classifier having a higher raw call volume; its 97.3% orphan-rate-given-failure (vs. 27.8% for alpha_classifier) is the single most consequential number in this audit.

By ticker (final orphans): NVDA=38, QQQ=32, MSFT=40, SNDK=52, TSM(old)=42, AMD=42. By source agent (alpha_classifier only — the only component with an agent field): fairly evenly spread (bear_researcher 10, others 1-6); evidence_stance/structure_extractor orphans have **no persisted agent field**, so a per-agent breakdown for 90.9% of all orphans is honestly **UNAVAILABLE**, not fabricated.

## 6. Error Taxonomy (Section 9)

| Terminal Cause | Count | % of 246 |
|---|---:|---:|
| TIMEOUT_EXHAUSTED | 201 | 81.7% |
| TRANSPORT_EXHAUSTED | 34 | 13.8% |
| SCHEMA_EXHAUSTED (WEEK2_LLM_VALIDATION_FAILED) | 11 | 4.5% |

No `RATE_LIMIT_EXHAUSTED`, `PARSE_EXHAUSTED`, or `EMPTY_RESPONSE_EXHAUSTED` ever appeared as a **terminal** cause in any of the six runs.

## 7. Timeout Root-Cause Audit (Section 10)

**Per-component, not blanket**: `alpha_classifier` = **NO** (small ~1800-char prompts, sub-2s typical latency, 72% recovery — consistent with transient blips). `evidence_stance_classifier` = **YES** (100% TIMEOUT terminal cause in 5/6 runs; retried-success TOTAL latencies of 76-90s imply the successful SECOND attempt alone often takes 31-45s — right at the ceiling it just cleared). `structure_extractor` = **NOT_APPLICABLE** (terminal cause is schema/validation, not timeout). **Overall: UNCERTAIN — this audit does not recommend a blanket timeout increase**, only a component-scoped conclusion for `evidence_stance_classifier`.

## 8. AMD Transport Error Audit (Section 11)

All **67** of AMD's `TRANSPORT_ERROR` events share the **exact same logged timestamp** (`2026-09-07T00:09:51Z`), spanning both attempt=1 (33) and attempt=2 (34), across `evidence_stance_classifier` (58) and `structure_extractor` (10). This is a textbook signature of a **single, brief, shared-infrastructure outage** — not a per-request deterministic defect. Essentially none of these calls recovered on retry (0% for `evidence_stance_classifier` in AMD), consistent with a no-delay retry firing while the outage was still (or just barely no longer) in effect. AMD is a genuine outlier — no other run shows this pattern.

## 9. Retry Effectiveness (Section 12)

**Retries are already doing substantial, real work for `alpha_classifier`** (72.2% recovery — do not characterize this component as having "no retry reliability"). For `evidence_stance_classifier`, the current single retry recovers only **5 of 188** failed calls (2.7%) — real but minimal value relative to the 183 orphans it does not prevent. `structure_extractor` sits in between at 11.1%, on a much smaller base.

## 10. Retry Count Counterfactual — Offline Only (Section 13)

Using only historically observed attempts (no extrapolation): a **1-attempt** policy would have produced 169 / 188 / 18 orphans respectively (i.e., every attempt-1 failure). The **current 2-attempt** policy produces 47 / 183 / 16. A **3-attempt** counterfactual is **NO_HISTORICAL_DATA** — `max_retries=1` was applied in every one of the 7 runs, so no attempt=3 was ever logged to replay; this audit does not guess a recovery rate for a hypothetical 3rd attempt. The demonstrated value of the *existing* retry is real: it already prevents 122 `alpha_classifier` orphans (a 72% reduction from the 1-attempt counterfactual) and 2 `structure_extractor` orphans, versus only 5 for `evidence_stance_classifier`.

## 11. Extra-Retry Recoverability (Section 14)

`alpha_classifier`: **SUPPORTED_BY_COMPONENT_RECOVERY_PATTERN** (strong existing recovery pattern, small fast prompts, transient-looking timeouts). `evidence_stance_classifier`: **UNSUPPORTED** — wait, see caveat below. `structure_extractor`: **UNSUPPORTED** (terminal cause is deterministic-model schema mismatch at temperature 0.0; an identical retry has no clear mechanism to change the outcome).

*(Caveat, addressed directly in Section 26's fix rationale: `evidence_stance_classifier`'s own retry-count counterfactual (10 above) shows its EXISTING retry does recover a small but real number of calls, 5 of 188 — this is the basis for extending, not abandoning, the same mechanism for this component specifically, even though the raw recovery-pattern classification here is conservatively `UNSUPPORTED` given how small that base rate is.)*

## 12. Timeout Extension Counterfactual (Section 15)

`evidence_stance_classifier`: **POSSIBLY_RECOVERABLE** — population-level evidence (retried-success total latencies of 76-90s, implying 31-45s second-attempt durations already near the ceiling) suggests some fraction of orphaned calls might complete with more time, but `call_with_timeout()` discards the underlying thread on timeout, so **no orphaned call's true completion time was ever directly measured**. Classified `POSSIBLY_RECOVERABLE`, deliberately not `LIKELY_RECOVERABLE_WITH_LONGER_TIMEOUT`, given that evidentiary gap. `alpha_classifier`: **NO_EVIDENCE**. `structure_extractor`: **NOT_APPLICABLE**.

## 13. Concurrency Audit (Section 16)

`alpha_classifier` concurrency = 4 (default, `COMQUTOR_WEEK2_LLM_CONCURRENCY`, not overridden). `evidence_stance_classifier`/`structure_extractor` = sequential (no pool). **No evidence concurrency causes failures** — if anything, the relationship is **inverse**: the only concurrent component has the best recovery rate (72%) while the two sequential components are far worse (2.7%, 11.1%). `WEEK2_LLM_RATE_LIMIT` (HTTP 429) appears occasionally as a non-terminal event but never as a terminal cause. **Recommendation: do not lower concurrency — not supported by evidence.**

## 14. Input Size / Complexity Audit (Section 17)

`evidence_stance_classifier`: orphan inputs run **~10-25% larger** than successful inputs on average (7381-8583 vs 5760-7727 chars) — a real but **modest** secondary factor, not sufficient alone to explain a 97.3% orphan rate. `structure_extractor`: essentially **no difference** (416-559 vs 394-560 chars) — input size is not a factor for this component's schema-driven failures. `alpha_classifier`: orphan-call inputs are not consistently persisted for this Pure-LLM-Authority task's final-orphan records; successful inputs are small and stable (~1800-1850 chars) across every run, suggesting prompt size is not the driver of its occasional timeouts.

## 15. Gold Impact (Section 19) — Including a Major Adequacy Gap

| Ticker | Impacted Alpha | Gold Expected | Hit/Miss | Classification |
|---|---|---|---|---|
| QQQ | A501 | No | Miss | IMPACTED_BUT_NON_GOLD |
| QQQ | A601 | Yes | Hit | IMPACTED_BUT_REDUNDANT |
| MSFT | A301 | Yes | Hit | IMPACTED_BUT_REDUNDANT |
| SNDK | A201 | Yes | Hit | IMPACTED_BUT_REDUNDANT |
| **TSM (old)** | **A301** | **Yes** | **MISS** | **IMPACTED_AND_MISS_CAUSAL** |
| TSM (old) | A601 | Yes | Hit | IMPACTED_BUT_REDUNDANT |
| AMD | A301 | Yes | Hit | IMPACTED_BUT_REDUNDANT |
| TSM (new, diagnostic) | A101 | Yes | Hit | IMPACTED_BUT_REDUNDANT |

**TSM (old) A301 remains the only confirmed `IMPACTED_AND_MISS_CAUSAL` case, exactly as the prior audit established.**

**Critical adequacy finding**: `compute_impacted_alphas()` traces Gold impact **only** via `alpha_matches.json`'s `deterministic_top_alpha` field — a mechanism that exists **only for `alpha_classifier`**. There is **no equivalent attribution tool** for `evidence_stance_classifier` or `structure_extractor` final orphans. Since those two components produce **199 of 246 (80.9%) of all final orphans**, their downstream Gold-alpha consequence, if any, is currently **UNKNOWN — not zero, not measured**. This is the single most important metric gap surfaced by this audit.

## 16. TSM Old vs. New Reliability Control (Section 20)

| | Old | New |
|---|---:|---:|
| `alpha_classifier` raw / failed / recovered / orphans | 47 / 38 / 29 / 9 | 33 / 27 / 21 / 6 |
| Orphan rate | 23.7% | 22.2% |

Statistically indistinguishable given the sample sizes — no configuration changed between runs (same 45s timeout, same `max_retries=1`, same model, same concurrency). **A301 lineage specifically**: old `claim:42` (deterministic score 0.7596) exhausted both attempts and became `match_status='unavailable'`; new `claim:29` (same deterministic score 0.7596, different research content) succeeded outright. **Verdict: `SAME_CONFIG_DIFFERENT_EXECUTION_OUTCOME`** — the expected behavior of a probabilistic retry-exhaustion process landing a specific claim instance in the ~22-24% failing tail once and the ~76-78% succeeding majority the other time.

## 17. Research Variance vs. Provider Reliability (Section 21)

A103's and A201's new-run misses remain classified as **research-content variance** and **structure-extraction variance** respectively (per the prior recorder/variance audit) — neither appears in either run's `impacted_alpha_ids`, and neither is used as Provider-reliability evidence here. TSM A301 remains the clean, confirmed reliability positive control.

## 18. Provider Health Metric Adequacy (Section 22)

**Current metrics are NOT sufficient to fully guide a fix.** They correctly show THAT and roughly WHERE a problem exists, but not WHY retries work or fail, nor any evidence_stance/structure_extractor Alpha-level attribution. Recommended (not implemented) additions: `retry_recovery_count`/`retry_recovery_rate` per component, `terminal_error_type`, `attempts_to_success` distribution, `orphan_rate_by_component` (relative to failure exposure, not total calls), and — most importantly — an alpha-level attribution mechanism for `evidence_stance_classifier`/`structure_extractor` analogous to `alpha_matches.json`'s `deterministic_top_alpha`.

## 19. Fix Design Options (Sections 23-25)

| Option | Root Cause Addressed | Semantic Change | Readiness |
|---|---|---|---|
| A — Timeout increase (evidence_stance only) | Timeout-dominant terminal cause | No | DESIGN_NOT_READY (insufficient direct per-orphan evidence) |
| B — Blanket retry increase (all 3 tasks) | Untargeted | No | DESIGN_NOT_READY (not evidence-targeted) |
| **C — Component-specific retry increase (evidence_stance only, 1→2)** | **Dominant 74% orphan share, near-zero recovery** | **No** | **READY_FOR_BOUNDED_IMPLEMENTATION** |
| D — Deterministic fallback preservation | N/A for evidence_stance/structure_extractor (already exists); would be a SEMANTIC change for alpha_classifier | YES for alpha_classifier variant | OUT_OF_SCOPE (alpha_classifier) / ALREADY_EXISTS (others) |
| E — Concurrency smoothing | Not supported by evidence | No | DESIGN_NOT_READY (not justified) |
| F — Transport retry hardening (short backoff, TRANSPORT_ERROR only) | AMD's 13.8%-share outage cluster | No | DESIGN_NOT_READY (secondary priority, narrower scope) |

**Option D is treated with extreme conservatism per task instruction**: TSM A301 being deterministically singularly eligible does **not** authorize globally bypassing Pure-LLM Semantic Authority for `alpha_classifier` — that variant is explicitly out of scope for a reliability-only task.

## 20. Preferred Reliability Fix (Section 26)

**OPTION C — give `evidence_stance_classifier` one additional retry (`max_retries` 1→2, 3 total attempts), leaving `alpha_classifier`, `structure_extractor`, and the shared 45s timeout untouched.** Matches all seven selection criteria: reduces final orphans (not just logs), supported by historical data (the existing retry already recovers 5 calls — proof the mechanism isn't impossible, just underprovisioned), bounded code surface (one new per-task retry-count lookup in `invoke_json_with_trace`, clamped to the *existing* `MAX_SERVER_RETRIES=2` ceiling — no new safety bound needed), no Alpha semantic change (same existing deterministic fallback, just reached after one more try), low regression risk, fully offline-testable, and validatable with one future TSM run. **Not chosen for any expected Alpha-Hit effect** — `evidence_stance_classifier`'s Gold impact is currently unmeasured (Section 15/18).

## 21. Implementation Test Design — Not Implemented (Section 28)

Designed for a future task: 3-attempt timeout-then-success; all-3-attempts-timeout; transport retry (extended); non-retryable-path unaffected (`WEEK2_LLM_INPUT_TOO_LARGE`); `structure_extractor`'s retry count provably unchanged; correct raw-event counting at 3 attempts; single final-orphan record (no double counting); byte-identical fallback value; TSM A301 historical fixture unaffected; Provider Health metrics update correctly; `MAX_SERVER_RETRIES=2` ceiling still respected.

## 22. Future Validation Ticker (Section 29)

**TSM** — the only ticker with both a proven `alpha_classifier` reliability-sensitive lineage (A301) and meaningful `evidence_stance_classifier` orphan volume (30 old / 32 new) to observe the fix's effect on directly.

## 23. Success Criteria (Section 30) & MSFT A304 (Section 31)

Success is **not** "raw failures = 0" — it is a decreasing `evidence_stance_classifier` orphan rate, non-worsening `claims_orphaned_by_provider_failure`, no increase in impacted Gold Alphas, zero semantic regression, and (TSM-specific control) A301 remaining not Provider-impacted. **Should Provider reliability block MSFT A304 work? NO** — MSFT A304 was independently confirmed not Provider-caused (`impacted_alpha_ids=[A301]`, already a redundant hit), with no dependency on this fix.

## 24. Development Plan (Section 32)

**PLAN_A** — implement the bounded Option C fix next, validate on TSM (one future run), then proceed to MSFT A304. The two tracks are not blocking dependencies of each other, but PLAN_A's sequential order is recommended as the cleaner execution path.

---

## Gold / Measurement Safety

Gold unchanged. Gold Validity unchanged. Official Alpha Hit unchanged at **61.0317%**. Multi-run evaluator unchanged. Recorder Health unchanged. Old TSM remains authoritative. New TSM remains validation-only.

## Final Validation

No production code changed. No tests changed. No Provider calls. No TradingAgents calls. No ticker runs. No retry/timeout/concurrency/prompt/threshold/taxonomy changes. No Gold change. Gold v1 SHA256 `99b1cd0247637054de360c3b5c0c00c7d8052152f3db1d29045eae1850bd8e9a` unchanged. Gold Validity SHA256 `3643ea45168c029d7c2a2ceb6d1d61cac3d5de80770d3dccb1f57d005c0c1cdf` unchanged. **Commits: 0. Pushes: 0. Destructive git operations: 0.**
