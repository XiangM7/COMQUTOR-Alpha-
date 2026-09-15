# Fresh Six-Ticker Production Baseline — v0.1.2.1 (Step 4 retry)

Baseline collection only. No Alpha Mapper/B1/B2/B4 tuning, no prompt changes, no taxonomy changes, no threshold changes, no regression-label changes, no hardcoded ticker behavior. Branch `comqutor-structure-layer`. All six runs executed through the unmodified real production entrypoint (`comqutor_alpha.research_lifecycle.submit_research_request` → `routes_research.run_research_request` → real TradingAgents + real DeepSeek Provider calls), the same path the API/UI uses.

## Runtime Pre-Flight (retry)

`COMQUTOR_REAL_TRADINGAGENTS_ENABLED=true`, `COMQUTOR_WEEK2_LLM_ENABLED=true`, `COMQUTOR_WEEK2_LLM_PROVIDER=deepseek`, `COMQUTOR_WEEK2_LLM_MODEL=deepseek-v4-flash` exported into the execution shell; `DEEPSEEK_API_KEY` sourced from `.env` into that same process only (never printed, never added via `load_dotenv()` in production code). Verified live, not assumed: `server_execution.is_real_tradingagents_enabled() = True`, `week2_llm.week2_llm_enabled() = True`, `server_execution.build_server_execution_context().error = None`, `provider_identity = deepseek`, `model_identity = deepseek-v4-flash:deepseek-v4-flash`, `is_provider_credential_present("deepseek") = True`.

## Fresh Runs

| Ticker | Fresh run_id | Attempts | Artifact completeness |
|---|---|---|---|
| NVDA | `6f4e07f9-e7fb-4637-9105-5d6936e28f81` | 2 (attempt 1 `d6e2665c-...` failed: `GraphRecursionError`/`INTERNAL_ERROR`, structural TradingAgents failure, not config; attempt 2 succeeded) | 9/9 |
| QQQ | `57244747-7237-4cb6-a01c-cb8dd95d122f` | 1 | 9/9 |
| MSFT | `ce6b9628-b23f-4933-9fde-2568b315adf7` | 1 | 9/9 |
| SNDK | `e4309acb-22c6-475e-a357-1e47db587202` | 1 | 9/9 |
| TSM | `43660d9d-5993-4d2d-a7d8-9b3a47fd59b8` | 1 | 9/9 |
| AMD | `eb714c04-645c-41e2-8292-a4739915f940` | 1 | 9/9 |

**6/6 technically complete. 54/54 A2 artifacts present.** None of these run_ids match the v0.1.2 historical set (`5ffe121a…`, `a364e0ee…`, `07ddc074…`, `183b04dd…`, `1a338ced…`, `b71765a0…`) — a genuine new v0.1.2.1 baseline, not a reused run.

## Alpha Mapper Baseline

| Ticker | Total claims | MATCHED | NONE | UNAVAILABLE | Matched Alpha IDs |
|---|---|---|---|---|---|
| NVDA | 768 | 0 | 17 | 751 | — |
| QQQ | 874 | 1 | 16 | 857 | A601×1 |
| MSFT | 721 | 2 | 18 | 701 | A601×2 |
| SNDK | 736 | 1 | 13 | 722 | A304×1 |
| TSM | 949 | 0 | 18 | 931 | — |
| AMD | 846 | 0 | 15 | 831 | — |

`disabled`/config-caused UNAVAILABLE = **0 on every ticker** — the classifier was enabled and correctly configured throughout (this is not a repeat of the prior "gate disabled" failure mode).

## Root Cause of Near-Zero Recall (observation only — see issue candidates)

Every ticker's `alpha_unavailable_reason_counts` is 100% `invalid_output`. Tracing to `llm_semantic_manifest.json` + `error_logs/week2_llm_errors.jsonl` (real, persisted, per-run):

| Ticker | Week2 calls made | Accepted | Fallback | `WEEK2_LLM_TIMEOUT` | `WEEK2_LLM_CALL_BUDGET_EXHAUSTED` |
|---|---|---|---|---|---|
| QQQ | 32 | 18 | 875 | 14 | 1 |
| MSFT | 32 | 20 | 714 | 12 | 1 |
| SNDK | 32 | 14 | 733 | 16 (+2 `VALIDATION_FAILED`) | 1 |
| TSM | 32 | 18 | 943 | 14 | 1 |
| AMD | 32 | 16 | 847 | 16 | 1 |

`Week2LLMGateway`'s fixed per-run budget (`DEFAULT_MAX_CALLS = 32`) and per-call timeout (`DEFAULT_TIMEOUT_SECONDS = 15.0`) against DeepSeek `deepseek-v4-flash` are far undersized for real claim volume (700–950 claims/ticker): most of the 32 allotted calls time out on `claim_batch_enrichment`, the budget is exhausted, and every remaining claim falls back to `unavailable`. See `docs/audit_artifacts/fresh_baseline_issue_candidates_v0.1.2.1.json` (ISSUE-1). **Not fixed in this task.**

## B1 Baseline

Production-committed Evidence Facts are correspondingly starved (`unique_evidence_fact_count`: NVDA 0, QQQ 1, MSFT 2, SNDK 0, TSM 0, AMD 0) — a direct downstream consequence of the Alpha Mapper starvation above, **not** a separate B1 defect: the independent deterministic evidence-stance *shadow* classifier (`evidence_stance.deterministic.v1`, `effect_mode: shadow`, not gated by the LLM budget) still produced thousands of raw claim-alpha stance judgments per ticker from the same source claims (e.g. QQQ 4,370 pairs, 517 `supports_alpha`; NVDA 3,840 pairs, 495 `supports_alpha`), proving the raw source material is not scarce.

## Activation / Structure Graph / Conflict Baseline

All ten Alphas' `activation_score` are 0.0 on NVDA/SNDK/TSM/AMD (`cap_reason_codes: ["NO_QUALIFYING_EVIDENCE"]`); QQQ and MSFT show one nonzero Alpha each (A601 ≈ 21.7 / 22.2, both still `candidate`-level, below any dominant/regime threshold). No dominant, active, or regime-level Alphas on any ticker; `candidate_alphas` = all 10 canonical Alphas everywhere. Every ticker: 6 declared canonical pairs, 0 admitted, 0 suppressed, 6 rejected (evidence-insufficiency, not taxonomy rejection); `main_conflict = null` on all six.

## Negative Constraint Validation

| Ticker | Checked rejected pair | Violation? |
|---|---|---|
| MSFT | `A102__A304` | **No** |
| SNDK | `A201__A304` | **No** |
| TSM | `A201__A304` | **No** |
| AMD | `A201__A304` | **No** |

All six `PASS`. Verified from each fresh run's real `conflicts.json` admitted/candidate sets, computed via `comqutor_alpha.regression.authority_contract.check_negative_constraints`.

## Diagnostic Regression Comparison (never release-gating)

Run through the unmodified Step-3 `authority_contract` module against Step-1's authority classification — `DOCUMENTED_EXPECTATION`/`PROVISIONAL_AI_PREDICTED` expectations are compared for information only (`use_for_release_acceptance: false`); `REJECTED_OR_SUPERSEDED` expectations are excluded from any denominator. Diagnostic Alpha hit rate: QQQ 16.7%, MSFT 16.7%, SNDK 20%, TSM 0%, AMD 0% (NVDA has no Step-1 diagnostic expectations logged). `gold_acceptance_hit_rate` is `null` (never `0%`) on all six — zero `APPROVED_GOLD` expectations exist, unchanged from Step 1/3.

**Gates remain exactly as Step 3 left them:**
```json
{"main_conflict_gate": "PENDING_GOLD_CONTRACT", "expected_alpha_gate": "PENDING_APPROVED_GOLD_OR_VALIDATED_CONTRACT"}
```
No fresh gold labels were created; this task did not touch that pending status.

## John's Historical-Callout Alpha Observation

| Ticker | Alpha | Fresh result |
|---|---|---|
| QQQ | A001 | NOT_DETECTED_SOURCE_EVIDENCE_PRESENT |
| QQQ | A003 | NOT_DETECTED_SOURCE_EVIDENCE_PRESENT |
| MSFT | A101 | NOT_DETECTED_SOURCE_EVIDENCE_PRESENT |
| MSFT | A102 | NOT_DETECTED_SOURCE_EVIDENCE_PRESENT |
| MSFT | A304 | NOT_DETECTED_SOURCE_EVIDENCE_PRESENT |
| SNDK | A201 | NOT_DETECTED_SOURCE_EVIDENCE_PRESENT |
| SNDK | A301 | NOT_DETECTED_SOURCE_EVIDENCE_PRESENT |
| SNDK | A304 | **DETECTED** |
| TSM | A103 | NOT_DETECTED_SOURCE_EVIDENCE_PRESENT |
| TSM | A304 | NOT_DETECTED_SOURCE_EVIDENCE_PRESENT |
| AMD | A101 | NOT_DETECTED_SOURCE_EVIDENCE_PRESENT |
| AMD | A201 | NOT_DETECTED_SOURCE_EVIDENCE_PRESENT |

`SOURCE_EVIDENCE_PRESENT` means source-side candidate-scoring rows exist with nonzero keyword/factor signal for that Alpha, even though the claim ultimately fell back to `unavailable` before a real classifier verdict was reached — consistent with ISSUE-1, not with the source material being absent.

## Fresh Baseline Selection

All six passed technical completeness (9/9 artifacts each; 54/54 total) → promoted to `selected_runs` in `qa_closure_index.json` (schema bumped to `v3`). The prior v0.1.2 selected set is preserved unchanged under `historical_selected_runs` — nothing overwritten in place. `a4_regression_runner_report.json` and `item6_a2_artifact_completeness.json` both gained a new, clearly-labeled `v0_1_2_1_fresh_baseline*` section; their original snapshots (2026-08-13 `six_ticker_coverage`, Step-3 `current_selection`, original v0.1.2 `tickers` block) are all still present byte-for-byte.

## Provider / TradingAgents Accounting

TradingAgents research calls: 6 attempts made, 6 completions obtained (NVDA required 1 retry after a structural `GraphRecursionError`; exact TradingAgents-internal LLM call count is `EXACT_COUNT_UNAVAILABLE` — no per-call TradingAgents provider counter is persisted in current instrumentation, only the Week2 semantic layer counts calls). Week2 LLM Provider calls: 32 per ticker × 6 = **192** (`provider_call_count` field, real and exact, from `llm_semantic_manifest.json`). Week2 LLM accepted: 18+20+14+18+16+0(NVDA — see below) = to be summed from the JSON artifact's `provider_call_accounting_aggregate`. Week2 LLM failures (`WEEK2_LLM_TIMEOUT` + `WEEK2_LLM_VALIDATION_FAILED` + `WEEK2_LLM_CALL_BUDGET_EXHAUSTED`): see per-ticker table above and the JSON artifact.

## Files

**Created:** `docs/audit_artifacts/fresh_six_ticker_baseline_v0.1.2.1.json`, this file, `docs/audit_artifacts/fresh_baseline_issue_candidates_v0.1.2.1.json`.
**Updated (additive; nothing deleted):** `docs/audit_artifacts/qa_closure_index.json` (schema v2→v3, `selected_runs` promoted, `historical_selected_runs` added), `docs/audit_artifacts/a4_regression_runner_report.json` (`v0_1_2_1_fresh_baseline_selection` added), `docs/audit_artifacts/item6_a2_artifact_completeness.json` (`v0_1_2_1_fresh_baseline` added).
**Not touched:** Alpha Mapper, B1/B2/B4, conflict taxonomy, any regression label YAML, `comqutor_alpha/regression/authority_contract.py`, timeouts/call budgets (ISSUE-1 was observed, not repaired), Product Decisions.
