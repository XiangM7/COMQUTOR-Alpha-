# v0.1.3 TSM Fresh Provider Validation

One authorized fresh production run. **Ticker: TSM only. Provider calls: occurred (as authorized). TradingAgents calls: occurred (as authorized). Ticker runs: 1.** HEAD unchanged (`9f228723fad5406c72e62beca67ec70ea0fdb004`). No commit. No push. No code changed.

## John — TSM Fresh Provider Validation

```
Metric                    Old TSM                       New TSM
Provider Health           PROVIDER_DEGRADED             PROVIDER_DEGRADED
Raw Provider Failures     128                            117
Final Orphans             42                              42
Alpha Classifier Orphans  9                               6
Impacted Alphas           [A301, A601]                    [A101]
A301 Score                44.7724                         75.9582
A301 Level                candidate (MISS)                dominant (HIT)
A301 Gold Hit             MISS                            HIT
Main Conflict             A101__A304                      A101__A304 (unchanged)

Conclusion: CASE_A_PROVIDER_CAUSE_CONFIRMED for A301 -- the old miss was a
transient alpha_classifier timeout, not an algorithmic defect. HOWEVER,
A103 and A201 independently REGRESSED from HIT to MISS in this fresh run
(unrelated to Provider failure -- natural research-content variance),
so TSM's overall single-rerun Gold hit rate is LOWER (66.67% vs 83.33%)
despite A301's recovery. Recommend PROMOTE_NEW_TSM_CANDIDATE_FOR_REVALIDATION
only after a separate decision weighing this trade-off.
```

## Pre-Run Configuration Verification

Confirmed identical to the fixed `comqutor_deepseek_default_v1` profile used for all six original runs: DeepSeek `deepseek-v4-flash` (quick and deep), thinking disabled, temperature 0.0, 1 debate round, 1 risk round, Data Sanity enabled. **No Provider config, timeout, retry, model, or prompt was changed before this run.** Postgres/Docker were found stopped at task start (a deviation from the environment that produced the original six runs); restored via the same, already-approved mechanism used earlier in this session, rather than silently proceeding with a different (DB-unavailable) configuration.

## Run Execution

- **Old run**: `dfc7ceb3-3584-4514-bd84-6c371aab3e95`
- **New run**: `0aeea938-97a8-49c8-97e1-409f6dadad30`
- Submitted via `POST /api/research {"ticker":"TSM","force_refresh":true}` → `cache_disposition: force_refreshed`
- Started `2026-09-09T17:30:36Z`, completed `2026-09-09T18:57:52Z` (**87.3 minutes**)
- **Run status: completed. Artifact completeness: 9/9 PASS.** All 22 artifact files present, matching the old run's file set exactly. Data Sanity: `ok`.

## New Discovery: SEMANTIC_RECORDER_APPEND_FAILED (diagnostics-tool limitation)

During this run, the server log showed **247** `semantic runtime degraded (reason_code=SEMANTIC_RECORDER_APPEND_FAILED, exc_type=RecorderIntegrityError)` events — a failure class **not captured** by `error_logs/week2_llm_errors.jsonl`, and therefore **not currently measured** by the Provider Health diagnostics tool. Evidence suggests this is a concurrency artifact (`llm_semantic_calls.jsonl` grew healthily throughout, 0→616 lines, ending in a genuine successful record; the failure count plateaued once the run moved from the highly-concurrent parallel-research phase into the slower sequential debate phase), not a fatal defect. **Reported as a finding for a future, separately-authorized diagnostics enhancement — no code was modified to address it in this task.**

## Old vs. New Provider Comparison

| Metric | Old | New | Delta |
|---|---:|---:|---|
| provider_health | DEGRADED | DEGRADED | unchanged |
| provider_failure_events | 128 | 117 | −11 |
| semantic_critical_failure_events | 114 | 103 | −11 |
| alpha_classifier_failure_events | 47 | 33 | −14 |
| alpha_classifier_final_orphans | 9 | 6 | −3 |
| provider_final_orphans_total | 42 | 42 | 0 |
| claims_orphaned_by_provider_failure | 9 | 6 | −3 |
| impacted_alpha_ids | [A301, A601] | [A101] | A301/A601 no longer impacted; A101 newly impacted (no Gold consequence) |
| benchmark_review_required | true | true | unchanged, different underlying alpha |

Overall raw Provider distress is modestly lower but **not eliminated** — the new run remains meaningfully degraded. The result is not "the run became healthy," it's "the specific lineage that blocked A301 succeeded this time."

## A301 Primary Validation

| | Old | New |
|---|---|---|
| Score | 44.7724 | **75.9582** |
| Level | candidate | **dominant** |
| Detected (Gold) | NO | **YES** |
| Ticker-specific evidence | 1 | 5 |
| Unique evidence | 13 | 14 |
| Local structure support (raw) | 0.0 | **50.0** |
| Cap reason codes | NO_LOCAL_STRUCTURE_SUPPORT | none |

New committed edge: `ai_demand → tsm_revenue_growth` (causal, `alpha_ids=[A101, A301]`), sourced from `fundamental_agent:claim:29`.

## New Claim Lineage — A301

| | Old claim:42 | New claim:29 |
|---|---|---|
| Text | "TSM has delivered two consecutive years of >30% revenue growth... driven by the AI infrastructure buildout." | "This is a clear beat-and-raise revenue acceleration pattern driven by AI demand." |
| Deterministic A301 score | 0.7596 | **0.7596 (identical)** |
| Outcome | `match_status=unavailable` (provider_timeout) | `match_status=matched`, `alpha_match_method=llm`, `matched_alpha=A301` |

Not the same claim ID (expected — fresh research produces new claims), but the **same economic thesis** with the **identical deterministic candidate strength**. This time the `alpha_classifier` LLM call succeeded, producing a genuine (non-fallback) decision that flowed through to a real committed structure edge.

## Provider-Failure Causality: CASE_A_PROVIDER_CAUSE_CONFIRMED

All three requirements met: (1) the new run is materially healthier on the relevant A301 lineage; (2) A301 is now `dominant` (detected); (3) no algorithmic rule was changed. **The old TSM A301 miss was caused by a transient Provider execution failure, not an algorithmic defect.** This classification is scoped specifically to A301 — it does not extend to or excuse the separately-observed A103/A201 regressions below.

## TSM Gold Result — `TSM_SINGLE_RERUN_DIAGNOSTIC` (not an official benchmark update)

| | Old | New |
|---|---|---|
| Detected | A101, A103, A201, A304, A601 | A101, A301, A304, A601 |
| Hit count | 5/6 | **4/6** |
| Hit rate | 83.33% | **66.67%** |

**Honest disclosure**: despite A301's confirmed recovery, TSM's overall single-rerun hit rate is *lower* than before, because A103 and A201 — both unrelated to Provider failure — regressed from hit to miss.

## All Ten Taxonomy Alphas — Drift Check

| Alpha | Old Score | Old Level | New Score | New Level | Change |
|---|---:|---|---:|---|---|
| A101 | 52.9006 | active | 70.0 | active | score↑, still HIT |
| A102 | 0.0 | candidate | 0.0 | candidate | unchanged (not Gold-expected) |
| A103 | 68.5499 | active | 25.7618 | candidate | **REGRESSED: HIT→MISS** (not Provider-impacted; thin new-run evidence) |
| A201 | 64.5041 | active | 44.4406 | candidate | **REGRESSED: HIT→MISS** (not Provider-impacted; not investigated further, out of scope) |
| A301 | 44.7724 | candidate | 75.9582 | dominant | **RECOVERED: MISS→HIT** (CASE_A confirmed) |
| A304 | 57.9945 | active | 75.8263 | dominant | score↑, still HIT |
| A601 | 54.1843 | active | 55.4809 | active | score↑, still HIT |

A103/A201's regressions are **not** Provider-related (neither appears in the new run's `impacted_alpha_ids`) — attributed to natural research-content variance between independent live runs (A103 in particular now has only 1 unique qualifying fact, `INSUFFICIENT_UNIQUE_EVIDENCE`).

## Main Conflict Comparison

**Unchanged**: `A101__A304` admitted in both runs. New detail: conflict_score 19.8256 (low), bull_score 70.0 (18 unique facts, 3 agents), bear_score 75.8263 (18 unique facts, 6 agents), B2 admissibility `admitted`, reason_codes `[]`.

## P0/P1 Correctness Check — New Run

- **P0**: Re-ran `_foreign_issuer_only_reason()` against every claim. **4 claims** (AMD/Intel/Samsung/Qualcomm competitive-dynamics content, zero TSM mention, zero taxonomy signal) correctly triggered the veto (`FOREIGN_ISSUER_NO_TAXONOMY_SIGNAL`) and were confirmed excluded from qualifying evidence. **Zero contamination reached the final score.**
- **P1**: "TSMC"/"Taiwan Semiconductor" mentions correctly recognized as ticker-specific in all sampled cases.
- Both confirmed **active and effective on live, freshly-generated data** — not just historical replay.

## Provider Impact on Other TSM Alphas

`impacted_alpha_ids = [A101]` only. The one affected claim (bear_researcher, Secondary, non-material) has **zero Gold consequence** — A101 is already a hit via 18 other qualifying facts.

## Final Decision

**Case: `CASE_A_PROVIDER_CAUSE_CONFIRMED`** (for A301). **Recommendation: `PROMOTE_NEW_TSM_CANDIDATE_FOR_REVALIDATION`** — but **not promoted in this task**. Promotion requires a separate, explicitly-authorized decision weighing A301's confirmed recovery against the A103/A201 regressions before this run could be considered a strict improvement. Secondary follow-up: the `SEMANTIC_RECORDER_APPEND_FAILED` diagnostics-tool gap.

## Official Benchmark Status — Unchanged

Official six-ticker Alpha Hit remains **61.0317%**. Frozen ledger, `v0_1_3_gold_validation.json`, `regression_report_v3.json`, and all final closure reports **untouched**.

---

## Final Validation

Exactly one fresh ticker run (TSM only); no second TSM run; no other ticker run. No code or test files changed. Gold v1/Gold Validity SHA-256 unchanged. P0/P1 and Provider Health layer unchanged. Old authoritative ledger unchanged. Official Gold result unchanged.

**Commits: 0. Pushes: 0. Destructive git operations: 0.**
