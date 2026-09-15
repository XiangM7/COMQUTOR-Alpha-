# Provider Health Recheck + Degraded-Ticker Clean Rerun — v0.1.2.1 (Step 11)

Branch `comqutor-structure-layer`, HEAD `9f228723fad5406c72e62beca67ec70ea0fdb004` (unchanged — no commit, no push). Zero production semantic code changed (verified by frozen-hash checks, same as Step 10).

## Preflight: PASS

`COMQUTOR_REAL_TRADINGAGENTS_ENABLED=true`, `COMQUTOR_WEEK2_LLM_ENABLED=true`, provider `deepseek`, model `deepseek-v4-flash`, credential present, single-claim semantic unit, claim concurrency 4, ticker concurrency 1, workload-aware call budget enabled — all verified from the actual runtime process, matching Step 5A's repaired configuration exactly.

## Live health probe: PASS

10 representative single-claim `alpha_classifier` requests via the real production call path (`_classify_alpha_with_llm` + `build_server_week2_llm_gateway`), concurrency 4, over real persisted claims: **10/10 successes, 0 errors, 0 timeouts, 0 payment errors.** Latencies 1.1–3.3s, matching Step 5A's established healthy baseline. Provider clearly usable — proceeded to full ticker reruns.

## Reruns

| Ticker | Old run (Step 10) | Old coverage | New run (Step 11) | New coverage | Replacement |
|---|---|---|---|---|---|
| NVDA | `948be419-b542-4096-a536-ff567ef459c2` | 45.99% | `a8d47429-a47a-446b-93c4-dd718b8e2ff9` | **98.74%** | **YES** |
| MSFT | `c715460c-5fa3-43d8-9949-97fb6b33e8ec` | 3.92% | `6cd2566d-e0f1-4306-995f-74f39efb21eb` | **98.91%** | **YES** |
| TSM | `5be841d5-0924-4943-8d37-ccd4168228cb` | 0.00% | `0a44ec41-c181-488d-94b8-00a333e85ddb` | **98.53%** | **YES** |

All three reruns completed with all 9/9 required artifacts, materially healthy semantic execution health (well above the internal 95% benchmark), and no configuration-invalid condition — all three qualify as valid replacements per this task's Replacement Rule.

## A genuine dedup hit, caught before it could corrupt the baseline

**MSFT and TSM's first rerun attempt each returned the exact same run_id as their Step-10 degraded run — in 0.1 seconds.** This was not a real rerun: it was a request-fingerprint reuse/dedup hit. `analysis_date` resolved identically to Step 10's own later-running tickers (Step 10's sequence crossed a calendar-day boundary mid-run), so the fingerprint matched an existing terminal row and the system correctly-by-design served the cached (degraded) result instead of executing anything new.

This was caught immediately — before reporting anything as a valid replacement — by comparing every returned run_id against the known Step-10 degraded run_id. Once detected, both tickers were re-invoked with `force_refresh=True` (`COMQUTOR_REAL_FORCE_REFRESH_ENABLED` set only for this explicit, deliberate in-process call, never as a standing configuration change). Both retries succeeded with genuinely new run_ids and `disposition=force_refreshed`. NVDA never hit this because its own `analysis_date` differed from Step 10's (it ran on an earlier calendar day in Step 10, so the same-day Step 11 request naturally produced a fresh fingerprint).

This is exactly the kind of "actual artifact/run-integrity reason" this task anticipated — reported honestly, not silently absorbed.

## Final baseline status: **REPAIRED**

## Mixed-time composite set — justified

The final composite six-ticker set mixes Step-10 runs (QQQ, SNDK, AMD) with Step-11 runs (NVDA, MSFT, TSM). This is acceptable and explicitly verified:

1. **Same production code state** — zero production semantic files changed between Step 10 and Step 11 (frozen-hash tests confirm byte-identical `alpha_mapper.py`, `activation_scorer_v2.py`, `conflict_detector.py`, `alpha_level_classifier.py`, `evidence_source_role.py`, `alpha_display_normalizer.py`, taxonomy).
2. **Same semantic contract** — Alpha Mapper v3, B1 v3, B2/B4 thresholds, Step-6/Step-7 behavior all unchanged.
3. **Same Provider/model configuration** — deepseek/deepseek-v4-flash, same workload-aware call budget, same concurrency=4.
4. **Only the three externally-degraded runs were replaced** — QQQ/SNDK/AMD were not rerun (no consistency defect was found in them).

## Call accounting (Step 11 only — not merged with Step 10)

| | |
|---|---|
| Health-probe Provider calls | 11 (1 minimal + 10 production-shaped) |
| NVDA TradingAgents attempts | 1 |
| MSFT TradingAgents attempts | 2 (1 dedup hit + 1 force-refreshed real execution) |
| TSM TradingAgents attempts | 2 (1 dedup hit + 1 force-refreshed real execution) |
| Whole-ticker retries | 2 |
| Week2 Provider attempts (NVDA+MSFT+TSM new runs only) | 1777 |
| Week2 timeouts (same scope) | 366 |
| Week2 transport/provider errors (same scope) | **1** — dramatically lower than Step 10's storm counts (435/659/793 on the same three tickers) |
| Week2 rate limits / budget exhaustion | 0 / 0 |

## No production changes

Alpha Mapper, Week2 semantic prompt, taxonomy, B1, B2, B4, Step-6 evidence qualification, Step-7 display normalization, conflict ontology, regression labels, timeout/concurrency/budget settings, and ticker-specific rules are all unchanged throughout this task.
