# v0.1.3 TSM Post-Retry Live Validation

One authorized fresh production run. **Ticker: TSM only. Provider calls: occurred. TradingAgents calls: occurred. Ticker runs: 1.** HEAD unchanged (`9f228723fad5406c72e62beca67ec70ea0fdb004`). No commit. No push. No code changed after seeing the result.

## Executive Summary

```
Pre-fix TSM run:               0aeea938-97a8-49c8-97e1-409f6dadad30
Post-fix TSM run:               fc09821e-c7cf-40a7-bd76-c98172e16992

Run complete:                   YES

Evidence stance old retry:      1
Evidence stance new retry:      2

Pre-fix stance final orphans:   32
Post-fix stance final orphans:  37

Third-attempt successes:        0
Third-attempt exhausted:        37

Retry effectiveness:            CASE_R4_EXTRA_RETRY_USED_BUT_NO_RECOVERY

Keep retry fix:                 MORE_VALIDATION_REQUIRED

A301:                           51.6447 / active / NOT Provider-impacted

TSM 3-run mean Gold Hit:        77.78%
Official six-ticker Alpha Hit:  61.0317% unchanged

No code changed after validation.
```

## John — Evidence-Stance Retry Live Validation

```
Metric                       | Pre-Fix TSM   | Post-Fix TSM
------------------------------|---------------|---------------
Evidence Stance Final Orphans |     32        |     37
Evidence Stance Orphan Rate   |    100.0%     |    97.4%
Retry-Recovered Calls         |     0         |     1 (at attempt 2, not 3)
3rd-Attempt Successes         |    n/a        |     0 (of 37 trials)
Provider Final Orphans        |     42        |     59
Impacted Alphas               |   [A101]      |     []
A301                          | 75.96/dominant|  51.64/active (both HIT, both non-impacted)
TSM Gold Hit                  |   4/6         |    5/6

Retry Fix Verdict:   MORE_VALIDATION_REQUIRED (no recovery observed, no meaningful downside either)
Next Step:           NEXT_MSFT_A304 (retry fix inconclusiveness does not block it)
Official benchmark unchanged: 61.0317%
```

## Pre-Run Snapshot

HEAD `9f228723fad5406c72e62beca67ec70ea0fdb004`, Gold v1/Validity SHA-256 confirmed unchanged. Retry policy confirmed in code: `evidence_stance_classifier` = 2 retries (3 max attempts, `EVIDENCE_STANCE_CLASSIFIER_MAX_RETRIES=2`); `alpha_classifier`/`structure_extractor` = 1 retry (2 max attempts, unchanged); `MAX_SERVER_RETRIES` ceiling = 2, unchanged. Timeout = 45s, unchanged. Provider/model = DeepSeek `deepseek-v4-flash`, `comqutor_deepseek_default_v1` profile — identical to every prior run this session. **Closed-status prerequisites reconfirmed**: P0/P1 (26/26), Provider Health (32/32), Measurement Foundation (46/46), Evidence-Stance Retry Fix (18/18) — all green immediately before execution.

**Operational note**: a pre-existing server process (PID 38207, started 10:30:21) predating the retry-fix code edit (14:10:15) was found occupying port 8000. It was stopped and the server restarted via the approved `scripts/start_live_comqutor.sh` launcher (new PID 72821, started 15:15:30) — otherwise this "post-fix" validation would have silently exercised stale, pre-fix retry code.

## Run Execution

- **New run**: `fc09821e-c7cf-40a7-bd76-c98172e16992`
- Submitted via `POST /api/research {"ticker":"TSM","force_refresh":true}` → `cache_disposition: force_refreshed` (the same already-established mechanism used for the pre-fix validation run — not invented here)
- Started `2026-09-09T22:15:45.918579Z`, completed `2026-09-09T23:48:12.083008Z` — **92.44 minutes**
- Config differences from the pre-fix run: **none**, other than the approved `evidence_stance_classifier` retry increase.

## Run Completeness

**Run completed: YES. Semantic status: PASS. Artifact completeness: 9/9.** Graph: 12 nodes, 11 edges. Claims present: 852. Alpha outputs, Provider logs, and diagnostics all present and readable.

**Data Sanity: CRITICAL** — `NO_MARKET_DATA_AVAILABLE` (Yahoo Finance returned no OHLCV data for TSM on 2026-09-09). This is an **external market-data provider issue**, entirely unrelated to the Week2 semantic/LLM Provider pipeline this fix targets — it does not touch `llm_semantic_calls.jsonl`, `error_logs`, `alpha_matches.json`, or `structure_graph.json`, all of which are present, non-empty, and internally consistent. **Classification: `VALID_FOR_RETRY_EFFECTIVENESS_ANALYSIS`**, not `RUN_INVALID_FOR_RETRY_EFFECTIVENESS` — reported honestly, not suppressed, but does not block the semantic-pipeline comparison this task requires.

## Primary Reliability Metrics (Post-Fix)

| Metric | Value |
|---|---:|
| `provider_health` | PROVIDER_DEGRADED |
| `provider_call_attempts_total` | 724 |
| `provider_failure_events` | 184 |
| `alpha_classifier_final_orphans` | 13 |
| `evidence_stance_final_orphans` | 37 |
| `structure_extractor_final_orphans` | 9 |
| `provider_final_orphans_total` | 59 |
| `claims_orphaned_by_provider_failure` | 13 |
| `impacted_alpha_ids` | `[]` |
| `benchmark_review_required` | false |

**Evidence-stance detail**: attempt distribution 38/37/37 (attempts 1/2/3). 38 failed calls, 112 raw failure events, exactly **1** retry-recovered call (at attempt 2 — the old policy already supported this), **37 final orphans**, orphan-rate-given-failure **97.37%**.

## Primary Effectiveness Comparison (Pre-Fix vs. Post-Fix)

| Metric | Pre-Fix | Post-Fix | Delta |
|---|---:|---:|---:|
| Evidence-stance failed calls | 32 | 38 | +6 |
| Evidence-stance failure events | 64 | 112 | +48 |
| Evidence-stance retry-recovered calls | 0 | 1 | +1 |
| Evidence-stance final orphans | 32 | 37 | +5 |
| Evidence-stance orphan rate given failure | 100.0% | 97.37% | −2.63pp |
| Provider final orphans (total) | 42 | 59 | +17 |
| Claims orphaned by Provider failure | 6 | 13 | +7 |
| Impacted Alpha IDs | `[A101]` | `[]` | — |
| Benchmark review required | true | false | — |

**Raw failure events are not the primary metric** — final orphans, orphan rate, retry recovery, and impacted Alphas are. The orphan-rate improvement (100%→97.37%) traces to exactly one recovered call at **attempt 2**, not attempt 3 — **not causally attributable to the new fix**.

## Third-Attempt Analysis — The Critical Question

**`third_attempt_success_count = 0`. `third_attempt_exhaustion_count = 37`.**

The third attempt was genuinely exercised **37 times** live in this run — direct, real evidence the fix is active in production — but **zero** of those 37 calls recovered on attempt 3. Per the task's own instruction, this is not classified as failure merely because "no call needed a third attempt" (37 calls *did* need and use it); the honest classification is that the opportunity was used but did not pay off this run.

**Terminal cause breakdown of the 37 exhausted calls**: 13 via `WEEK2_LLM_TIMEOUT`, 24 via `WEEK2_LLM_TRANSPORT_ERROR`. The 24 transport-terminal calls (72 evidence-stance + 18 structure-extractor raw events) all logged within a **1-2 second window** (`23:48:08Z`–`23:48:09Z`) at the very end of the run — a brief, shared-infrastructure disruption event, structurally identical to (but larger than) the AMD transport cluster found in the prior reliability audit. With no backoff between attempts, three back-to-back fast-failing attempts fired inside the *same* brief outage window for every affected call — a retry-**count** increase alone was never expected to escape that (Option F, backoff, was explicitly deferred). This single event confounds roughly two-thirds (24 of 37) of this run's third-attempt trials, leaving only 13 timeout-terminal calls as a genuinely independent test of "does an unmodified 3rd attempt help a near-timeout-boundary task" — and none of those 13 recovered either, consistent with (not contradicting) the prior audit's own cautious "possibly, not proven" framing.

## Retry Benefit Classification

**`CASE_R4_EXTRA_RETRY_USED_BUT_NO_RECOVERY`.** Excludes CASE_R1 (0 successes), CASE_R3 (a real opportunity *did* occur, 37 times), CASE_R2 (the one observed improvement has a fully known, non-third-attempt lineage), and CASE_R5 (no meaningful cost/latency/operational regression — see below). No arbitrary percent-improvement threshold was invented; this is a direct read of the observed attempt sequences.

## Latency / Cost Observation

Pre-fix duration: 87.28 min. Post-fix: 92.44 min (**+5.16 min, +5.9%**). Provider call attempts: 658 → 724 (**+66, +10%**). Of the 66 extra attempts, 24 (the transport cluster's third attempts) failed near-instantly and consumed negligible wall-clock time; the remaining 13 (timeout-terminal third attempts) could each add up to ~45s — up to ~9.75 minutes theoretical maximum, roughly explaining most of the observed increase. **Incremental latency risk: LOW-MEDIUM. Incremental cost risk: LOW-MEDIUM.** Not all wall-clock variance is attributed to the retry policy — TradingAgents/Provider latency varies run-to-run for many unrelated reasons, as established throughout this session's TSM reproducibility work.

## Provider Health / Recorder Health

Provider Health remains `PROVIDER_DEGRADED` in both runs — overall `PROVIDER_HEALTHY` is not required for the fix to be useful, and none of the seven TSM/six-ticker runs studied this whole session have achieved it. Recorder Health (post-fix): **274 recorder_failure_events, RECORDER_DEGRADED, canonical_semantic_losses=0** — read from a new, separate log file (`/tmp/comqutor_live_start_postfix.log`) created specifically for this run to avoid mixing with the pre-fix run's log, per the task's log-traceability requirement. Recorder failures remain architecturally kept out of Provider reliability metrics.

## A301 Control

| | Pre-Fix Validation | Post-Fix |
|---|---|---|
| Score / Level | 75.9582 / dominant | 51.6447 / active |
| Detected (Gold) | YES | YES |
| Provider impacted | NO | NO |

A301 remains a Gold hit and remains **not** Provider-impacted — the retry fix did not damage this control. The score/level decrease is consistent with ordinary research-content variance across independent live runs (the same phenomenon documented extensively for A103/A201 this session), not retry-fix harm, since A301's lineage is `alpha_classifier`-driven, not `evidence_stance_classifier`-driven.

## All Gold TSM Alphas (Post-Fix)

| Alpha | Score | Level | Detected | Provider Impacted |
|---|---:|---|---|---|
| A101 | 70.0000 | active | YES | NO |
| A103 | 42.3237 | candidate | NO | NO |
| A201 | 61.5376 | active | YES | NO |
| A301 | 51.6447 | active | YES | NO |
| A304 | 64.9288 | active | YES | NO |
| A601 | 60.9620 | active | YES | NO |

**5/6 = 83.33% Gold hit this run.** Per task instruction, this is **not** used as evidence for or against the retry fix — A103's miss is governed by research-content/structure variance (established throughout this session), not evidence-stance retry behavior.

## Three-Run Reproducibility Diagnostic (Not an Official Benchmark)

Using the Multi-Run Evaluator across `dfc7ceb3` (old), `0aeea938` (pre-fix validation), and `fc09821e` (post-fix):

| Alpha | 3-Run Detection Frequency |
|---|---:|
| A101 | 1.00 |
| A103 | 0.33 |
| A201 | 0.67 |
| A301 | 0.67 |
| A304 | 1.00 |
| A601 | 1.00 |

**3-run TSM mean Gold Hit: 77.78%.** Variable Gold Alphas: A103, A201, A301. Pairwise Gold Jaccards: old↔pre-fix=0.50, pre-fix↔post-fix=0.80, old↔post-fix=0.667. **Mean pairwise Gold Jaccard: 0.6556.** Labeled `TSM_THREE_RUN_REPRODUCIBILITY_DIAGNOSTIC` — **not** promoted into the official six-ticker benchmark.

## Main Conflict

`A101__A304` — admitted, `conflict_score=16.6549` (low), `bull_score=70.0`, `bear_score=64.9288`, B2 admissibility status `admitted`, reason codes `[]`. **Unchanged** from both the old authoritative run and the pre-fix validation run.

## P0/P1 Validation

**P0: PASS** — `_foreign_issuer_only_reason()` unmodified this task, confirmed callable against live data. 0 of 26 spot-checked competitor-mentioning claims triggered the veto — consistent with its own documented narrow, 3-condition, rare-firing design (own-ticker terms absent AND a system-covered foreign ticker present AND zero deterministic taxonomy signal). Zero firings this run is not a failure signal.

**P1: PASS** — "TSMC" (39 mentions) and "Taiwan Semiconductor" (10 mentions) present in raw research; every one of the 6 Gold Alphas shows nonzero `ticker_specific_evidence_count` this run, confirming alias recognition remains active on live data.

## Keep / Revert Recommendation

**`MORE_VALIDATION_REQUIRED`.** Neither KEEP's criterion (useful recovery or clearly improved final-orphan behavior without meaningful downside) nor REVERT's criterion (no useful recovery AND meaningful latency/cost downside or operational regression) is cleanly met: no third-attempt recovery occurred, but no meaningful downside was found either. Two-thirds of this run's third-attempt trials were dominated by one atypical, brief transport-outage cluster that a retry-count change alone could never be expected to fix — making this single run's evidence base non-representative of steady-state conditions. **Not reverted in this task** — recommendation only.

## Next Development Step

**`NEXT_MSFT_A304`.** MSFT A304 was independently confirmed not Provider-caused in two prior audits and remains true regardless of this run's inconclusive retry-fix result — its blocker is a regex/negation-aware extraction capability gap, unrelated to `evidence_stance_classifier`. **Should Provider reliability block MSFT A304 work? NO.** A further TSM (or other-ticker) replicate to resolve the retry-effectiveness question is a reasonable idea for the future, recommended only, not scheduled, and not a blocker.

---

## Gold / Git Validation

Gold v1 SHA256 `99b1cd0247637054de360c3b5c0c00c7d8052152f3db1d29045eae1850bd8e9a` — unchanged. Gold Validity SHA256 `3643ea45168c029d7c2a2ceb6d1d61cac3d5de80770d3dccb1f57d005c0c1cdf` — unchanged. HEAD unchanged. Frozen ledger unchanged. No commit. No push. No destructive git operation. **No code changed after seeing the result.**

**Production files changed: 0. Test files changed: 0. Provider calls: occurred (as authorized). TradingAgents calls: occurred (as authorized). Ticker runs: 1 (TSM only). Commits: 0. Pushes: 0. Destructive git operations: 0.**
