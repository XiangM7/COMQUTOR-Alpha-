# v0.2 QQQ Post-Fix Fresh Run Manifest

**Step 7B.1: establish the authority of exactly ONE genuinely fresh QQQ research run, generated after Step 7A (negative invalidation veto) and Step 7A.2 (positive directional-easing requirement).** This task creates the run only — it does not evaluate Gold PASS/FAIL, does not adjudicate detected Alpha or conflict correctness, and does not reuse the old QQQ evidence trigger as authority for this new corpus.

## Purpose

Generate one new, force-refreshed QQQ run under current post-remediation production code, establishing new-run authority for the next steps (7B.2 independent evidence-trigger adjudication, 7B.3 comparison) — exactly analogous to how the original six-ticker authoritative corpus was established, but for a single ticker, post-fix.

## Remediation State

All authorities verified byte-identical before this task began and unmodified throughout: Gold Contract, Evidence Trigger Matrix (explicitly **not** reused as authority for this new run — it belongs to the historical `f88c8956-...` corpus only), Final Acceptance Table, Acceptance Adjudication, Evidence Failure Analysis, Step-7A Remediation, Step-7A.1 Residual Audit, and Step-7A.2 Remediation (JSON + MD).

Current production semantics confirmed unchanged from Step 7A.2's own final state:

| File | SHA256 |
|---|---|
| `comqutor_alpha/structure_engine/claim_semantics.py` | `f0d9d891c1ee459f149677da19639434f3b236901b455e180e841b354688299b` |
| `comqutor_alpha/structure_engine/alpha_mapper.py` | `36d36ffebac280578e540372e33eb657622b39d2530927510f28cb1cadcaed29` |
| `tests/test_qqq_a001_mapping_remediation.py` | `74c055d1379215684fd68aac3910369e93808d070fc145c126a1f780cbd97c07` |

Confirmed present: the Step-7A A001 invalidation veto, the Step-7A.2 A001 positive-requirement gate, and `POSITIVE_EASING`-only final positive semantic acceptance.

**Known validation-environment issue carried forward** (not repaired here): Step-7A.2's broader backend suite showed 39 of 42 test errors traced to one shared test fixture (`tests/replay/conftest.py:221`) whose synthetic mock always canned-selects A001 for unrelated content — classified `TEST_INFRASTRUCTURE_ARTIFACT`, not a proven production regression. This context does not excuse ignoring any real production failure found in this fresh run (none were found).

## Execution

**Runner discovery**: `scripts/run_regression.py` was inspected and ruled out — its own help text states it "Never calls a Provider or TradingAgents... Never runs LLM-driven analysis" (zero-Provider Architecture Replay only, for regression comparison against saved runs). The actual live-run mechanism is `scripts/start_live_comqutor.sh` (starts the API server with the real-execution env vars) followed by `POST /api/research`, per `docs/audit_artifacts/v0_1_3_msft_a304_fresh_validation.md`'s own documented precedent for the historical authoritative runs.

**User authorization**: enabling live execution required flipping `COMQUTOR_REAL_TRADINGAGENTS_ENABLED`/`COMQUTOR_WEEK2_LLM_ENABLED`/`COMQUTOR_REAL_FORCE_REFRESH_ENABLED`, previously noted as gated behind product-approval item PD-006. The user explicitly confirmed proceeding before any live action was taken.

**An existing `comqutor-api` server was found already running** (PID 27595, left over from an earlier, unrelated session — log file `/private/tmp/comqutor_live_start_msft_a304.log`), already configured with `real_execution: "configured"` and `live_semantic_pipeline: "ready"`. Per this task's own safety rule ("never reuse or kill another server"), that existing server was used as-is rather than starting a second one or touching its environment.

**Exact command**:
```
curl -s -X POST http://127.0.0.1:8000/api/research -H "Content-Type: application/json" -d '{"ticker":"QQQ","force_refresh":true}'
```

Response confirmed `"cache_disposition": "force_refreshed"` — a genuinely fresh, non-cached run, not a reuse of any prior QQQ output.

**Attempts: 1. Infrastructure retries: 0.** One minor client-side polling error occurred (the first status check used the bare `GET /api/research/{run_id}` record-lookup endpoint instead of the `/status` lifecycle endpoint, briefly returning `RUN_NOT_FOUND` while the run was genuinely in progress) — corrected immediately by switching to the correct endpoint; no second run was ever submitted, and the run itself never failed or restarted.

## New Run Authority

| Field | Value |
|---|---|
| Ticker | QQQ |
| **New run_id** | `f239a53f-4ebe-455c-bb76-5f5485903901` |
| Historical run_id (not reused, not modified) | `f88c8956-cb62-48aa-9951-89f8e8a95f83` |
| Analysis date | 2026-09-11 |
| Created at | 2026-09-11T17:07:25.960769+00:00 |
| Started at | 2026-09-11T17:07:26.763880+00:00 |
| Completed at | 2026-09-11T17:59:47.245706+00:00 |
| Elapsed | 3140s (~52.3 min) |
| Selected analysts | market, sentiment, news, fundamentals |
| LLM provider / models | deepseek / deepseek-v4-flash (quick + deep) |
| Overall completion status | **completed** |
| Current HEAD | `9f228723fad5406c72e62beca67ec70ea0fdb004` (unchanged) |
| Branch | `comqutor-structure-layer` |

## Artifact Integrity

| Check | Result |
|---|---|
| Required artifact count | 9 |
| Present required artifacts | **9/9** |
| Missing required artifacts | none |
| Artifact completeness | **pass** |
| Ticker consistency (`run_audit.json`) | **pass**, 0 inconsistencies |
| Run-ID consistency across all present artifacts | **pass** |
| JSON parse validity | all present JSON artifacts parsed successfully |
| Data sanity status | **ok** (0 warnings, 0 critical, 276 OHLCV rows) |
| Graph node/edge count | 10 nodes / 11 edges (existence/count only — not semantically adjudicated) |

Only basic integrity/count metadata was inspected, per this task's explicit scope — graph edge semantics, conflict correctness, and Alpha-activation correctness were **not** evaluated.

## Provider Health

| Metric | Value |
|---|---:|
| Semantic Provider calls | 617 |
| Accepted | 584 |
| Rejected | 5 |
| Fallback | 11 |
| Cache hits | 0 |
| Total semantic records | 595 |
| Semantic-critical error events (`error_logs/week2_llm_errors.jsonl`) | 34 |
| — `WEEK2_LLM_TIMEOUT` | 25 |
| — `WEEK2_LLM_VALIDATION_FAILED` | 9 |
| By task: `evidence_stance_classifier` / `claim_batch_enrichment` / `structure_extractor` / `alpha_classifier` | 16 / 10 / 6 / 2 |
| Recorder-only failures (separate from semantic-critical) | 0 |

All 34 logged error events are genuine Week2 semantic-Provider-layer timeouts/validation retries (recoverable — the run still reached `accepted_count=584` and completed normally), not recorder/audit-trace failures. Two non-fatal, non-semantic data-vendor degradations were also observed and are unrelated to Provider/LLM health: Reddit RSS rate-limiting (429, automatic backoff/retry) and FRED macro-data vendor not configured (automatic fallback to the next vendor, per `tradingagents/dataflows/interface.py`).

## Anti-Bias / No-Rerun Statement

This was the **first and only** QQQ research submission of this task. No rerun was considered or performed for any reason — not because A001 appeared or disappeared, not because of Provider output quality, not because a conflict looked unexpected, and not because any score "looked bad." The single completed run above is, by this task's own rule, the validation candidate — full stop.

## Semantic Adjudication Status

**Not performed.** `semantic_adjudication.performed = false`. No detected-Alpha correctness, no main-conflict correctness, and no Gold PASS/FAIL were evaluated in this task. The old QQQ evidence trigger (A001 ABSENT, A003 UNCERTAIN, A304 PRESENT, A501 ABSENT, A601 PRESENT, A301 ETF-evidence UNCERTAIN) belongs **only** to the historical run `f88c8956-...` and was **not** reused, assumed, or carried forward as authority for this new run's evidence corpus.

**Disclosure**: basic artifact-integrity checking of the non-required `summary.json` (verifying it parses and carries the expected schema keys) incidentally exposed two high-level semantic fields (`dominant_alpha_ids`, `main_conflict_id`). Recorded transparently here; neither value is repeated in this manifest, and neither was used for any judgment in this task.

## Next Step

Because `RUN_USABLE_FOR_POSTFIX_VALIDATION = YES`:

**STEP 7B.2 — new-run QQQ evidence-trigger adjudication**, independent of Alpha-activation/conflict output, using only upstream-of-activation persisted evidence (`structured_agent_outputs.json`, `raw_agent_outputs.json`, `evidence_facts.json`, etc.) for run `f239a53f-4ebe-455c-bb76-5f5485903901` — exactly the same anti-circularity discipline Step 3 originally applied to the historical six-ticker corpus.

---

**No Gold PASS/FAIL was calculated. The historical QQQ acceptance remains FAIL** — `v0_2_final_acceptance_table.*` was not touched, and this new run does not overwrite history; it creates new, separate post-fix validation evidence. This new run requires its own evidence-trigger adjudication (Step 7B.2) before any post-fix acceptance comparison (Step 7B.3) can occur.

**Production files changed: 0. Test files changed: 0. Gold changed: no. Historical trigger matrix changed: no. Historical acceptance changed: no. Old six-run ledger changed: no. New run promoted into old ledger: no. QQQ ticker runs: 1. Other ticker runs: 0. Commits: 0. Pushes: 0. Destructive git operations: 0.**

**STEP 7B.1 ONLY. ONE FRESH QQQ RUN CREATED. NOT ADJUDICATED. OLD QQQ TRIGGER NOT REUSED.**
