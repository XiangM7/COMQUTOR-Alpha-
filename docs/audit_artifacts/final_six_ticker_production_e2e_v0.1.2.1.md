# FINAL Fresh Six-Ticker Production E2E — v0.1.2.1 (Step 10)

Branch `comqutor-structure-layer`, HEAD `9f228723fad5406c72e62beca67ec70ea0fdb004` (unchanged — no commit, no push). Real TradingAgents + real DeepSeek (`deepseek-v4-flash`) Provider calls throughout. Production semantics were frozen for the entire run — no code change between or during tickers.

## Final run_ids (new, not reused from any prior step)

| Ticker | run_id |
|---|---|
| NVDA | `948be419-b542-4096-a536-ff567ef459c2` |
| QQQ | `defeb528-673e-44f7-8d94-c0abdfef03d4` |
| MSFT | `c715460c-5fa3-43d8-9949-97fb6b33e8ec` |
| SNDK | `519c93f4-7fcd-4879-9ca9-dd65badc0fb8` |
| TSM | `5be841d5-0924-4943-8d37-ccd4168228cb` |
| AMD | `4d8385ef-dff0-4574-b6e7-73fec1eaa5e1` |

## Whole-ticker retries (all one external cause, now resolved)

The DeepSeek Provider account returned **402 Payment Required** partway through the run — NVDA's own run (23 min, hundreds of real LLM calls) exhausted the account's remaining credit, so QQQ/MSFT/SNDK/TSM/AMD's first attempts all failed instantly with `INTERNAL_ERROR`. The user topped up the account; a live preflight call confirmed the 402 no longer occurred; all 5 tickers were re-run and completed successfully with zero further retries needed. This is a genuine external Provider-account constraint, not a code or semantic defect. Failed attempts are preserved as audit history (5 failed run_ids, listed in the JSON artifact) — never deleted.

## Artifact completeness: 54 / 54

All 6 tickers × 9 required artifacts (`metadata.json`, `raw_agent_outputs.json`, `structured_agent_outputs.json`, `evidence_facts.json`, `alpha_matches.json`, `structure_graph.json`, `alpha_activations.json`, `conflicts.json`, `run_audit.json`) present — freshly verified against these 6 new run_ids, not reused from any historical count.

## Semantic runtime health — honest, mixed result

| Ticker | Eligible | MATCHED | NONE | UNAVAILABLE | Coverage | Internal ≥95% benchmark |
|---|---|---|---|---|---|---|
| NVDA | 822 | 192 | 186 | 444 | **45.99%** | **FAIL** |
| QQQ | 724 | 298 | 414 | 12 | **98.34%** | PASS |
| MSFT | 689 | 2 | 25 | 662 | **3.92%** | **FAIL** |
| SNDK | 834 | 320 | 501 | 13 | **98.44%** | PASS |
| TSM | 793 | 0 | 0 | 793 | **0.00%** | **FAIL** |
| AMD | 844 | 328 | 494 | 22 | **97.39%** | PASS |
| **Overall** | 4706 | 1140 | 1620 | 1946 | **58.65%** | **3/6** |

**3 of 6 tickers failed the internal 95% runtime-health benchmark** — NVDA, MSFT, and TSM suffered severe DeepSeek `provider_error` storms (435 / 659 / 793 provider-error events respectively) during Week2 semantic classification, downgrading most claims to UNAVAILABLE. This is **not** a code or semantic-prompt regression — production semantic code was frozen throughout this task (verified below). A real-world wall-clock gap of ~14 hours was observed between the QQQ and MSFT runs within this same process (their `started_at`/`ended_at` timestamps vs. much shorter monotonic `elapsed_seconds`), consistent with the host machine suspending and resuming during MSFT's execution window — a plausible, not certain, contributing factor, noted honestly rather than asserted as proven.

**This is reported, not repaired**, per this task's explicit instruction: no tuning, no re-run for semantic-quality reasons. The internal 95% figure remains an `internal_engineering_runtime_benchmark` — never a John release gate, regression acceptance, or semantic-accuracy claim.

## John's 12 historical Alpha callouts: 7 / 12 DETECTED on this run

All 5 misses are on **MSFT** (A101, A102, A304) and **TSM** (A103, A304) — the exact two tickers that catastrophically failed semantic runtime health above (3.92% and 0.00% coverage). Classified `NOT_DETECTED_SOURCE_PRESENT`, not a semantic recall defect: Step 5B's isolated, healthy-runtime validation already proved 12/12 DETECTED when the Alpha Mapper actually gets to classify the claims. This fresh run's shortfall is fully attributable to the runtime-health degradation on those two tickers, not to any change in Alpha Mapper semantics.

## Step 6 Evidence Qualification — verified live, not just offline

Read directly from the real production `structure_graph.json.activation.alphas[*].evidence_qualification` field on all 6 fresh runs (never an offline replay):

| Metric | Total |
|---|---|
| Primary Research evidence (raw claim count, by agent) | 2079 |
| Secondary/Decision/Debate evidence (raw claim count, by agent) | 2627 |
| Unknown-role evidence | 0 |
| Raw unique evidence facts (pre-qualification, sum across 60 alpha-records) | 576 |
| Qualified (activation-eligible) evidence facts | 378 |
| Secondary excluded from activation (not-ticker-specific + causality-unproven + duplicate) | 213 |
| Secondary qualified as genuine causal evidence | 33 |
| Duplicate Secondary restatements prevented from inflating support | 11 |

Reason-code breakdown: `PRIMARY_QUALIFIED`=359, `SECONDARY_NOT_TICKER_SPECIFIC`=195, `SECONDARY_CAUSALITY_UNPROVEN`=7, `SECONDARY_QUALIFIED_CAUSAL_EVIDENCE`=33, `SECONDARY_DUPLICATE_OF_PRIMARY`=11.

Confirms Step 6's qualification layer is genuinely active in the real, live production path — not merely exercised by offline tests.

## Activation / B4 + Step 7 Display Normalization — live, 60/60 observed

All 60 ticker/Alpha combinations classified with zero exceptions. Thresholds unchanged (active ≥50, dominant ≥70, regime ≥86). `candidate_active` remains `CANDIDATE_ACTIVE_REQUIRES_PRODUCT_DEFINITION` — not introduced. Full per-alpha detail (score, `target_level`/`qualified_level`/`activation_level`, `is_blocked`, reason codes) in the JSON artifact.

## Final main conflicts

| Ticker | Main conflict |
|---|---|
| NVDA | A101__A304 |
| QQQ | A101__A304 |
| MSFT | **null** (no qualifying evidence survived the 3.92%-coverage runtime failure) |
| SNDK | A304__A601 |
| TSM | **null** (no qualifying evidence survived the 0%-coverage runtime failure) |
| AMD | A101__A304 |

Both nulls are honest, expected B2 outcomes given the runtime-health failures above — not a bug.

## Negative constraints: PASS (0 violations)

MSFT `A102__A304`, SNDK/TSM/AMD `A201__A304` all remain correctly non-admitted.

## Call accounting

- **TradingAgents**: 11 ticker attempts (6 pre-topup + 5 post-topup), 6 completions, 5 whole-ticker retries (all one external cause).
- **Week2 semantic Provider** (exact, from persisted `llm_semantic_manifest.json`): **5532 total attempts**, 1852 successful classifications, 390 timeouts, 3912 transport/provider errors (the storms described above), 0 rate limits, 18 validation failures, 0 budget exhaustions.

## Performance

Total monotonic wall-clock across all 6 final successful runs: **10,189.7 seconds (2.83 hours)** of active execution. Real calendar time spanned considerably longer due to the mid-sequence credit-top-up pause and the observed ~14-hour host-suspend gap.

## No production changes

Alpha Mapper, taxonomy, B1, B2, B4, Step-6 evidence qualification, Step-7 display normalization, conflict ontology, and regression labels are all unchanged throughout this task.
