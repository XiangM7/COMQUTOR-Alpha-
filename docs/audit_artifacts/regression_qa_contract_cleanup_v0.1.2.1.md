# Regression QA Contract Cleanup — v0.1.2.1

QA/regression contract repair only. No Alpha Mapper, B1/B2/B4, canonical conflict taxonomy, or regression label YAML was modified. No fresh six-ticker regression run, no TradingAgents call, no Provider call, no commit, no push. Branch `comqutor-structure-layer`, HEAD `9f228723fad5406c72e62beca67ec70ea0fdb004`.

## Run Alignment

| Ticker | qa_closure_index.json | item6_a2_artifact_completeness.json | a4_regression_runner_report.json (current_selection, new) | a4 historical snapshot (preserved) |
|---|---|---|---|---|
| NVDA | `5ffe121a-68fd-473b-82b5-c9465332d8a2` | `5ffe121a-68fd-473b-82b5-c9465332d8a2` | `5ffe121a-68fd-473b-82b5-c9465332d8a2` | `e3eb3909-3744-4a02-9b32-b225cf6ef665` (kept, labeled historical) |
| QQQ | `a364e0ee-3bb4-4032-88b7-5cd82e379805` | `a364e0ee-3bb4-4032-88b7-5cd82e379805` | `a364e0ee-3bb4-4032-88b7-5cd82e379805` | same (unchanged since original snapshot) |
| MSFT | `07ddc074-9ab2-4b16-8957-acbf94012144` | `07ddc074-9ab2-4b16-8957-acbf94012144` | `07ddc074-9ab2-4b16-8957-acbf94012144` | `0cb43bae-1a4d-4003-bb29-55d420498842` (kept, labeled historical) |
| SNDK | `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f` | `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f` | `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f` | same |
| TSM | `1a338ced-118e-44d2-b3f6-2444bfb9d7e6` | `1a338ced-118e-44d2-b3f6-2444bfb9d7e6` | `1a338ced-118e-44d2-b3f6-2444bfb9d7e6` | same |
| AMD | `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6` | `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6` | `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6` | same |

**All identical after repair: 6/6.** `a4_regression_runner_report.json` was not string-replaced in place — its original `six_ticker_coverage`/`expected_vs_detected_summary` (report_created 2026-08-13, HEAD `b5837e80...`) remain byte-for-byte as historical provenance under a new `historical_snapshot_notice`, while a new, clearly-named `current_selection` block mirrors `qa_closure_index.json` (the single authoritative source — nothing independently re-selects run IDs).

## Label Authority

Unchanged from Step 1 (not reclassified in this step): **0 APPROVED_GOLD**, **15 DOCUMENTED_EXPECTATION**, **22 PROVISIONAL_AI_PREDICTED**, **0 REJECTED_OR_SUPERSEDED** Alpha expectations (37 total); **2 DOCUMENTED_EXPECTATION**, **5 PROVISIONAL_AI_PREDICTED**, **4 REJECTED_OR_SUPERSEDED** main-conflict expectations (11 total, 0 APPROVED_GOLD). What Step 3 adds is a code-level contract (`comqutor_alpha.regression.authority_contract`) that *enforces* this classification in reporting, rather than leaving it as audit-document knowledge someone has to remember to apply by hand.

## Regression Metrics

**Diagnostic Metrics** (informational, never gate a release):
- Per-ticker `diagnostic_expected_alphas` / `diagnostic_hit_rate`, computed from DOCUMENTED_EXPECTATION and PROVISIONAL_AI_PREDICTED Alpha labels against each ticker's already-detected Alphas.
- Per-ticker `expectations[].diagnostic_match` for every currently-referenced main-conflict expectation, each tagged with its own `expectation_authority` and `evaluation_mode: "diagnostic"`.
- All of this is populated in `docs/audit_artifacts/qa_closure_index.json` (`main_conflict_qa`, `expected_alpha_qa`) from the already-persisted `outputs/regression/regression_report.json` — no rerun.

**Release Acceptance Metrics** (only APPROVED_GOLD may produce these):
- `ticker_acceptance_status` / `ticker_acceptance_result` per ticker — currently `NOT_GOLD_EVALUABLE` / `null` for all six, because zero gold expectations exist.
- `gold_acceptance_hit_rate` per ticker — currently `null` for all six (never `0%`).
- The two release gates below.

## Main Conflict

John's requested `>= 4/6` main-conflict match target is **preserved, not deleted**:

```json
{"requested_target": ">=4/6", "current_evaluable_gold_cases": 0, "status": "PENDING_GOLD_CONTRACT", "use_for_current_production_acceptance": false, "gate_result": null}
```

It is pending because Step 1 found **zero** approved-gold main-conflict expectations across all six tickers — the gate has nothing valid to count against yet. It is not reported as `1/6 FAIL`; the previously-observed `main_conflict_match: true` for NVDA (against provisional/documented, non-gold expectations) is retained as a **diagnostic** fact, not folded into this gate. `comqutor_alpha.regression.authority_contract.main_conflict_gate()` will switch to `ACTIVE` and compute a real `N/M` the moment at least one ticker acquires an APPROVED_GOLD expectation — proven by `test_case3_gate_activates_once_a_real_gold_case_exists`.

## Expected Alpha Hit Rate

John's requested `>= 75%` target is likewise **preserved**:

```json
{"target": 0.75, "current_status": "PENDING_APPROVED_GOLD_OR_VALIDATED_CONTRACT", "current_gold_hit_rate": null, "gate_result": null}
```

Pending for the same reason: zero approved-gold expected-Alpha labels exist for any ticker. A diagnostic hit rate is still computed and shown per ticker (e.g. TSM's provisional/documented positive-Alpha overlap), explicitly marked `use_for_release_acceptance: false`, so the underlying signal isn't hidden — it just can't decide a release by itself.

## Negative Constraints

Absence of positive gold does not disable already-approved negative checks. `comqutor_alpha.regression.authority_contract.check_negative_constraints()` verifies, from the already-persisted `admitted_conflicts`/`candidate_conflicts` in `outputs/regression/regression_report.json`, that no ticker's real output currently contains a rejected/non-canonical pair:

| Ticker | Checked rejected pair(s) | Violation? |
|---|---|---|
| MSFT | `A102__A304` (PD-017) | **No** |
| SNDK | `A201__A304` | **No** |
| TSM | `A201__A304` | **No** |
| AMD | `A201__A304` | **No** |
| NVDA / QQQ | *(none currently rejected)* | n/a |

All six currently `PASS` this negative check. Had any ticker's real admitted-or-candidate set contained one of these pairs, `negative_constraint_status` would be `FAIL` regardless of the positive-gold gates being pending — tested explicitly in `test_case4_absence_of_positive_gold_does_not_disable_negative_check`.

## Remaining Blockers

- **Evidence Review v2** — `evidence_review_summary_v2.json` still does not exist; the legacy mixed-metric file remains un-selected as the v0.1.2.1 acceptance source (`qa_closure_index.json:authoritative_artifacts.evidence_review_summary_current.status = "PENDING_V2"`, unchanged from Step 2). Out of scope for Step 3.
- **Fresh six-ticker baseline** — this step deliberately did not call TradingAgents, Alpha Mapper, or rerun regression. The six selected runs remain whatever Step 2 found selected; Step 4 establishes a fresh baseline only after this contract is clean.
- **Production semantic repair** — explicitly deferred until a fresh baseline (Step 4) demonstrates it's actually needed; this step touched only `comqutor_alpha/regression/` (QA-layer code) and `docs/audit_artifacts/*` (QA metadata).

## Files Changed / Tests Run

**Created:**
- `comqutor_alpha/regression/authority_contract.py`
- `tests/test_regression_authority_contract.py`
- `docs/audit_artifacts/regression_qa_contract_cleanup_v0.1.2.1.md` (this file)

**Updated (additive; nothing deleted):**
- `docs/audit_artifacts/a4_regression_runner_report.json`
- `docs/audit_artifacts/qa_closure_index.json`
- `docs/audit_artifacts/qa_source_consistency_report_v0.1.2.1.json`

**Not touched:** production Alpha Mapper, B1/B2/B4, conflict taxonomy, any regression label YAML, `outputs/regression/regression_report.json`, `outputs/runs/*`.

**Tests:** `tests/test_regression_authority_contract.py` — 17/17 passed (all six required cases plus authority-vocabulary invariants). `tests/test_a4_regression_runner.py` — re-run to confirm no regression from the `authority_contract.py` addition (see final response for the exact count).
