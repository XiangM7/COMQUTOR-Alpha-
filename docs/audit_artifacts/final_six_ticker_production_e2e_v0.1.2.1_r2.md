# FINAL Fresh Six-Ticker Production E2E — Composite Repaired Baseline (Step 11, r2)

**This r2 artifact is the current, authoritative final six-ticker E2E result.** It supersedes `final_six_ticker_production_e2e_v0.1.2.1.json` (Step 10) for final-acceptance purposes — that file is preserved unmodified as historical evidence of the original attempt and the provider-error storm it uncovered.

Branch `comqutor-structure-layer`, HEAD `9f228723fad5406c72e62beca67ec70ea0fdb004` (unchanged). Zero production semantic code changed.

## Final composite run_ids

| Ticker | run_id | Provenance |
|---|---|---|
| NVDA | `a8d47429-a47a-446b-93c4-dd718b8e2ff9` | **Step 11** (replaces degraded `948be419-...`, 45.99%) |
| QQQ | `defeb528-673e-44f7-8d94-c0abdfef03d4` | Step 10 (retained, healthy) |
| MSFT | `6cd2566d-e0f1-4306-995f-74f39efb21eb` | **Step 11** (replaces degraded `c715460c-...`, 3.92%) |
| SNDK | `519c93f4-7fcd-4879-9ca9-dd65badc0fb8` | Step 10 (retained, healthy) |
| TSM | `0a44ec41-c181-488d-94b8-00a333e85ddb` | **Step 11** (replaces degraded `5be841d5-...`, 0.00%) |
| AMD | `4d8385ef-dff0-4574-b6e7-73fec1eaa5e1` | Step 10 (retained, healthy) |

## Artifact completeness: 54 / 54

## Semantic runtime health: **6 / 6 meet the internal 95% benchmark**

| Ticker | Coverage | Status |
|---|---|---|
| NVDA | **98.74%** | PASS |
| QQQ | 98.34% | PASS |
| MSFT | **98.91%** | PASS |
| SNDK | 98.44% | PASS |
| TSM | **98.53%** | PASS |
| AMD | 97.39% | PASS |
| **Overall** | **98.38%** | **6/6** |

A complete reversal from Step 10's 3/6 — the three replacement runs confirm the earlier degradation was a genuine, transient DeepSeek provider-error storm, now resolved.

## John's 12 historical Alpha callouts: **12 / 12 DETECTED**

Reproduces Step 5B's isolated healthy-runtime finding exactly, now confirmed on a real, live, full production run. Diagnostic only — never approved gold.

## Step 6 Evidence Qualification — live, composite

Primary Research evidence: 2174 · Secondary/Decision/Debate evidence: 2520 · Unknown-role: 0 · Raw unique evidence facts: 1017 · Qualified (activation-eligible): 637 · Secondary excluded: 414 · Secondary qualified causal evidence: 70 · Duplicate restatements prevented: 30.

## Activation / B4 + Step 7 Display — 60/60, 0 ambiguous

`candidate`=33, `active`=17, `capped_active`=1, `dominant`=9, `regime_level`=0, `blocked`=2. Thresholds unchanged (50/70/86). `candidate_active` remains `CANDIDATE_ACTIVE_REQUIRES_PRODUCT_DEFINITION`.

## Final main conflicts: **6 / 6 non-null**

| Ticker | Main conflict |
|---|---|
| NVDA | A101__A304 |
| QQQ | A101__A304 |
| MSFT | A101__A304 |
| SNDK | A304__A601 |
| TSM | A101__A304 |
| AMD | A101__A304 |

Every ticker now produces an admitted conflict — MSFT and TSM's Step-10 nulls (caused entirely by their runtime-health failures) are resolved.

## Negative constraints: PASS (0 violations)

## No production changes

Alpha Mapper, taxonomy, B1, B2, B4, Step-6, Step-7, conflict ontology, regression labels all unchanged.
