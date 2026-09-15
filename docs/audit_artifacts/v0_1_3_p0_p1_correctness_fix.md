# v0.1.3 P0/P1 Evidence Correctness Fix

Implementation authorized. **Provider calls: 0. TradingAgents calls: 0. Ticker runs: 0. HEAD unchanged (`9f228723fad5406c72e62beca67ec70ea0fdb004`). No commit. No push.**

## Executive Summary

```
P0 Cross-company contamination:        FIXED
P1 company_names propagation:          FIXED
Known AMD A201 contamination:          FIXED

Production company_names non-empty:    5/6 supported corporate tickers
                                        (NVDA, MSFT, AMD, TSM, SNDK)
                                        QQQ intentionally excluded -- ETF, deferred

39 known false negatives:
  now ticker-recognized:                39
  now qualifying activation evidence:   39
  still independently blocked:          0

Remaining confirmed C1 contamination:   0

New regressions:                        3 (see below -- explained, not hidden)

Provider calls: 0    TradingAgents calls: 0    Ticker runs: 0
Gold unchanged: YES
```

## Code Changes

- **Created** `comqutor_alpha/graph_engine/issuer_aliases.py` — static, deterministic `CANONICAL_ISSUER_ALIASES` registry (NVDA/MSFT/AMD/TSM/SNDK; QQQ intentionally absent) and `company_names_for_ticker()` lookup.
- **Modified** `comqutor_alpha/graph_engine/pipeline.py` — wires `company_names=company_names_for_ticker(graph.get("ticker"))` into the single production call to `score_alpha_activations_v2` (previously omitted entirely).
- **Modified** `comqutor_alpha/graph_engine/activation_scorer_v2.py` — adds `_foreign_issuer_only_reason()` (P0 gate) and wires it as an additive veto inside `_qualify_groups_for_activation`, applied *after* the existing Primary/Secondary decision.
- **Created** `tests/test_p0_p1_evidence_correctness_fix.py` — 26 targeted tests (A–P + production wiring).

No other production or test file was modified.

## P0 Ownership Contract

**Invariant**: a semantic Alpha match (`matched_alpha`, however derived — deterministic or Pure-LLM Semantic Authority) is never by itself sufficient to make a claim count as activation-qualifying evidence for the current run ticker. Ticker/entity ownership is independently deterministic.

`_foreign_issuer_only_reason()` returns `FOREIGN_ISSUER_NO_TAXONOMY_SIGNAL` only when **all three** conditions hold:
1. the current ticker's own symbol/issuer aliases are absent from the claim text;
2. at least one *other* covered ticker's symbol/issuer alias is present;
3. every canonical Alpha's `keyword_score` **and** `factor_score` are exactly zero in the claim's own `candidate_scores`.

**Why three conditions**: empirically validated during design against all six persisted runs. A broader "another company is named" veto flagged 628 legitimate claims (mostly ticker-agnostic macro evidence). A narrower "foreign known-ticker mention, own-ticker absent" rule still flagged 23 claims, 22 of which were legitimate relational/competitive/ETF-constituent evidence (e.g. "a direct target for Nvidia's competitive response" in an AMD run — "NVIDIA" is itself an A101 taxonomy keyword, so this correctly carries real deterministic signal and must not be vetoed). The three-condition conjunction fires on **exactly the one confirmed contamination case** across the entire six-run, 750+-match corpus and nothing else.

The vetoed claim remains fully visible in `evidence_fact_groups`' audit view, marked `activation_eligible=False` with the new reason code — never deleted.

## P1 Company Alias Contract

`CANONICAL_ISSUER_ALIASES`: NVDA→(NVIDIA, NVIDIA Corporation), MSFT→(Microsoft, Microsoft Corporation), AMD→(Advanced Micro Devices[, Inc.], Ryzen, Instinct, Epyc), TSM→(TSMC, Taiwan Semiconductor[ Manufacturing[ Company]]), SNDK→(SanDisk, SanDisk Corporation). QQQ has no entry (`ETF_ENTITY_HANDLING_DEFERRED=True`). No existing ticker-metadata source was found anywhere in the codebase (confirmed by the prior audit's exhaustive grep) — this is a new, minimal, static registry, not a repurposed pre-existing field.

## Targeted Tests

`tests/test_p0_p1_evidence_correctness_fix.py` — **26 passed, 0 failed**, covering all 16 required scenarios (A–P) plus two production-wiring tests (MSFT non-empty, QQQ empty via monkeypatched real call site).

## Full Regression

| Run | Passed | Failed | Errors | Skipped |
|---|---:|---:|---:|---:|
| Baseline (this task's hunks precisely reverted, verified byte-exact) | 4017 | 21 | 3 | 47 |
| With P0/P1 changes | 4040 | 24 | 3 | 47 |

**New regressions: 3**, all explained:

- `test_evidence_review_v2.py::test_case17_production_semantic_modules_remain_untouched[...activation_scorer_v2.py]`
- `test_step10_final_e2e_qa.py::test_production_semantic_files_unchanged_during_step10`
- `test_step11_provider_health_rerun.py::test_production_semantic_files_unchanged_during_step11`

All three are frozen-SHA256 guards pinning `activation_scorer_v2.py`'s exact bytes to a hash recorded at a prior authorized-change checkpoint (each carries its own comment: *"Hash updated deliberately for that authorized change... this guard's job is to catch an UNREVIEWED future drift, not to freeze the files forever"*). This task's P0 addition to `activation_scorer_v2.py` is itself exactly such an authorized, reviewed change — the codebase's own established pattern would update these three hash constants. **This task did not**, because doing so requires modifying test files, which the task's explicit safety rules prohibit without further authorization. Reported honestly rather than worked around. The other 21 failures (+3 errors) are byte-identical between both runs — confirmed unrelated to this task (a stale `FROZEN_SESSION_HEAD` constant, and `evidence_review_summary_v2.json` schema issues from unrelated earlier work).

## Six-Run Offline Blast Radius

Apples-to-apples replay (`company_names=()` vs the new registry, identical code path, no Provider/LLM calls, no artifact mutation): **zero status-band transitions anywhere** across all six runs / 46 alpha-ticker combinations. Every change was a same-band score increase (or, for AMD A201, a combined P0-decrease + P1-increase net change). **The Expected Alpha Hit metric is unchanged: 61.0317% before and after.**

## AMD A201 Before/After

| | Evidence count | Score | Ticker-specific | Level |
|---|---:|---:|---:|---|
| Original (contaminated) | 5 | 25.7333 | 0 | candidate |
| P0 only (isolated, prior audit) | 4 | 21.0667 | 0 | candidate |
| P0+P1 combined (this patch) | 4 | 23.5667 | 1 | candidate |

No Alpha Hit or conflict impact — AMD A201 was, and remains, a miss.

## MSFT A102 Before/After

| | Ticker-specific | Unique evidence | Score | Level |
|---|---:|---:|---:|---|
| Before | 0 | 1 | 34.9674 | candidate |
| After | 1 | 1 | 44.9674 | candidate |

Still short of the 50.0 threshold by 5.0326 — exactly as the prior audit's counterfactual predicted. No Alpha Hit impact.

## Negative Controls

- **23 currently-hit Gold alphas**: 12 `UNCHANGED`, 11 `EXPECTED_CORRECTNESS_CHANGE` (score increased, status unchanged), 0 `UNEXPECTED_CHANGE`, 0 `NOT_REPLAYABLE`.
- **SNDK A102**: before/after both `candidate`/0.0 — no artificial activation.
- **QQQ**: zero score/status/evidence changes across all 6 scored alphas — ETF handling stays deferred/unchanged.
- **Other Alpha level changes**: none anywhere. **Main conflict changes**: none (NVDA/TSM/AMD admit `A101__A304`, QQQ admits `A304__A601`, MSFT/SNDK admit none — all unchanged).

## Deferred Work

NVDA A102 research coverage; MSFT A102 unique-evidence/agent-independence gap; AMD A102 inference-vs-training semantic gap; SNDK A102 Gold review; QQQ ETF constituent ownership model; TSM A301 / MSFT A304 structure recovery; Alpha Hit ≥75%. None solved here.

---

## Final Validation

- Gold v1 SHA-256: unchanged (`99b1cd0247637054de360c3b5c0c00c7d8052152f3db1d29045eae1850bd8e9a`)
- Gold Validity Judgment SHA-256: unchanged (`3643ea45168c029d7c2a2ceb6d1d61cac3d5de80770d3dccb1f57d005c0c1cdf`)
- No thresholds/taxonomy/B1/B2/B4/Primary-Secondary/fact-dedupe/Alpha-Hit-semantics/A102-semantics changes; QQQ ETF behavior not broadened
- `company_names` verified to reach the real production scorer (monkeypatched call-site test)
- 3 new regressions, named and explained above; not worked around by modifying tests

**Provider calls: 0. TradingAgents calls: 0. No ticker run. No commit. No push. No destructive git operations.**
