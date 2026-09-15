# v0.1.3 Final Revalidation

Offline only. **Provider calls: 0. TradingAgents calls: 0. No ticker run. No production code changed.**

| Metric | Result | Target | Status |
|---|---:|---:|---|
| Ticker consistency | 6/6 | 6/6 | PASS |
| Artifact completeness | 6/6 | 6/6 | PASS |
| Graph edges | 6/6 >=3 | 6/6 | PASS |
| Expected Alpha Hit Rate | — | >=75% | NOT_GOLD_EVALUABLE |
| Main Conflict Match | — | >=4/6 | NOT_GOLD_EVALUABLE |
| Alpha Match Accuracy | 166/200 = 83.00% | >=80% | PASS |
| Polarity Accuracy | 52/61 = 85.25% | >=80% | PASS |
| Critical Reversal | 0 | 0 | PASS |

## John QA Acceptance Snapshot

```
Ticker consistency        6/6 PASS
Artifact completeness     6/6 PASS
Graph edges               6/6 PASS (all >=3)

Expected Alpha Hit        NOT_GOLD_EVALUABLE
Main Conflict Match       NOT_GOLD_EVALUABLE

Alpha Match Accuracy      166/200 = 83.00% PASS
Polarity Accuracy         52/61 = 85.25% PASS
Critical Reversal         0 PASS
```

No recomputed metric differs from previously reported values — everything below reproduces byte-identically, independently re-derived from source, not copied.

## Final Selected Runs

| Ticker | Run ID |
|---|---|
| NVDA | `57d7b4c4-dbb9-4134-b962-ee2a873941cc` |
| QQQ | `f88c8956-cb62-48aa-9951-89f8e8a95f83` |
| MSFT | `43472ace-454f-4c69-892c-adca91c25be7` |
| SNDK | `e8e0f398-7b26-4462-8135-a1410ea5b335` |
| TSM | `dfc7ceb3-3584-4514-bd84-6c371aab3e95` |
| AMD | `949f685a-3945-4fd0-b7b9-362b37c90721` |

Excluded: TSM's first attempt (`be4916f6-d319-4a1f-aa60-bebdc26d55ca`) — orphaned by an infrastructure interruption, reconciled to `failed`, not used anywhere in this revalidation.

---

## 1. Ticker Consistency

Recomputed from current persisted artifacts for each ticker: `metadata.json` (requested), `run_audit.json` (persisted), the ledger (selected_run_id + ticker), `alpha_matches.json`/`structure_graph.json` (run artifact), `regression_report_v3.json` (regression ledger). All six agree across every layer.

**ticker_consistency_pass_count: 6/6 — PASS**

## 2. Artifact Completeness

| Ticker | Run ID | Present | Required | Status |
|---|---|---:|---:|---|
| NVDA | `57d7b4c4` | 9 | 9 | PASS |
| QQQ | `f88c8956` | 9 | 9 | PASS |
| MSFT | `43472ace` | 9 | 9 | PASS |
| SNDK | `e8e0f398` | 9 | 9 | PASS |
| TSM | `dfc7ceb3` | 9 | 9 | PASS |
| AMD | `949f685a` | 9 | 9 | PASS |

**artifact_completeness_pass_count: 6/6 — PASS**

## 3. Graph Edge Count

Read directly from each run's `run_audit.json` (not recomputed):

- NVDA: **9**
- QQQ: **9**
- MSFT: **7**
- SNDK: **7**
- TSM: **8**
- AMD: **8**

**graph_edges_pass_count: 6/6 (all >=3) — PASS**

## 4. Expected Alpha Hit Rate

**Gold evaluability checked first.** `authority_contract.alpha_expectations_for_ticker()` against the Regression Label Authority Audit shows **zero** APPROVED_GOLD alpha expectations across all six tickers.

**Status: NOT_GOLD_EVALUABLE.** Reason: no approved frozen Gold benchmark exists for the six FINAL_FRESH_SELECTED runs.

Diagnostic-only (never compared against the ≥75% acceptance target): NVDA 71.43%, QQQ 50.0%, MSFT 50.0%, SNDK 60.0%, TSM 83.33%, AMD 71.43% — average 64.37%. **DIAGNOSTIC_ONLY / NOT_AN_ACCEPTANCE_GATE.**

## 5. Main Conflict Match

**Gold evaluability checked first.** Zero main-conflict expectations across all six tickers carry acceptance-eligible authority. MSFT's only recorded expectation (`A102__A304`) is explicitly `REJECTED_OR_SUPERSEDED` and was **not** used. All others are `DOCUMENTED_EXPECTATION` or `PROVISIONAL_AI_PREDICTED` — neither is Gold.

**Status: NOT_GOLD_EVALUABLE.** Not forced to 4/6; no superseded expectation used; current outputs not used as their own Gold.

**Actual output (not a Gold comparison):**

| Ticker | Actual main conflict |
|---|---|
| NVDA | `A101__A304` (admitted) |
| QQQ | `A304__A601` (admitted) |
| MSFT | none admitted (all 6 declared pairs evaluated) |
| SNDK | none admitted (all 6 declared pairs evaluated) |
| TSM | `A101__A304` (admitted) |
| AMD | `A101__A304` (admitted) |

## 6. Frozen Evidence Review Authority

Located: `docs/audit_artifacts/evidence_review_summary_v2.json` and `.md`. Confirmed: 200 row-level judgments present, all headline metrics reconstructable directly from those rows. The human-reviewed labels (`item2_blind_holdout5_review_frozen.csv`) are **frozen** and were only read, never modified, by this revalidation.

## 7. Alpha Match Accuracy

Recomputed directly from `item2_blind_holdout5_comparison.csv`'s `alpha_correct` column across all 200 rows — **not** assumed from a prior report.

**166 / 200 = 83.00%** — target ≥80% — **PASS**. No change from previously reported.

34 failures: `holdout5-001, 003, 004, 005, 008, 016, 017, 033, 035, 043, 056, 057, 059, 063, 071, 081, 083, 086, 102, 103, 104, 143, 146, 151, 154, 158, 162, 163, 164, 167, 171, 174, 177, 185`

## 8. Polarity Accuracy

Recomputed directly from the same CSV, restricted to `review_material_alpha_fit==True` rows (62), excluding `holdout5-005` (formally adjudicated `BOTH_REASONABLE_AMBIGUOUS` → `AMBIGUOUS_DIRECTION`, ineligible under the existing, **unmodified** eligibility contract).

**52 / 61 = 85.25%** — target ≥80% — **PASS**. No change from previously reported.

9 failures: `holdout5-003, 016, 017, 040, 057, 070, 154, 196, 198`

## 9. Critical Support/Opposition Reversal

Recomputed directly from the same 61 eligible rows.

**Count: 0** — target 0 — **PASS**. No change from previously reported. (One raw reversal, `holdout5-005`, exists in the pre-eligibility 62-row pool but is excluded by the general rule above, not omitted or hidden.)

## 10. Consistency with Current Final Runs

The Blind Holdout #5 evidence review set draws from **17 historical run_ids across 8 tickers** (including GOOGL and MU, outside the current six-ticker scope) — **zero overlap** with the six FINAL_FRESH_SELECTED run IDs. This is an **intentionally frozen benchmark**, reviewed before this session's fresh six-ticker production run set ever existed. It was **not** rewritten to force fresh-run linkage — doing so would itself violate the review's own frozen-benchmark integrity guarantee (`production_semantic_drift = 0`, per `item2_blind_holdout5_internal_report.md` Section 12).

---

**Provider calls: 0. TradingAgents calls: 0. No ticker run. No production code changed.**
