# v0.1.3 Retrospective Gold Validation

Offline only. **Provider calls: 0. TradingAgents calls: 0. No ticker run. No production code changed.**

## Gold Benchmark Authority

```
Benchmark:            alpha_conflict_gold.v1
Gold dimensions:      Expected Alpha Hit, Main Conflict Match
As-of:                2026-09-08
Frozen:               YES
Validation:           RETROSPECTIVE_GOLD_VALIDATION
Benchmark SHA256:     99b1cd0247637054de360c3b5c0c00c7d8052152f3db1d29045eae1850bd8e9a
```

**Methodology note**: Because `alpha_conflict_gold.v1` was created **after** the outputs of the current six FINAL_FRESH_SELECTED runs were already available, this comparison is retrospective and must not be represented as a blind prospective benchmark. For a fully prospective acceptance test: (1) keep `alpha_conflict_gold.v1` unchanged, (2) its SHA-256 is already frozen above, (3) run a **new** six-ticker regression afterward, (4) compare those new outputs against this same already-frozen Gold. That prospective rerun is not part of this task.

---

## Expected Alpha Hit Gold Results

| Ticker | Gold Expected | Actual Hits | Misses | Hit Rate |
|---|---|---|---|---:|
| NVDA | A101,A102,A103,A201,A301,A304,A601 (7) | A101,A103,A301,A304,A601 | A102, A201 | 5/7 = 71.43% |
| QQQ | A101,A103,A201,A301,A304,A601 (6) | A103,A304,A601 | A101, A201, A301 | 3/6 = 50.00% |
| MSFT | A101,A102,A103,A301,A304,A601 (6) | A101,A103,A301 | A102, A304, A601 | 3/6 = 50.00% |
| SNDK | A102,A103,A201,A301,A601 (5) | A201,A601 | A102, A103, A301 | 2/5 = 40.00% |
| TSM | A101,A103,A201,A301,A304,A601 (6) | A101,A103,A201,A304,A601 | A301 | 5/6 = 83.33% |
| AMD | A101,A102,A103,A201,A301,A304,A601 (7) | A101,A103,A301,A304,A601 | A102, A201 | 5/7 = 71.43% |

Official metric (macro-average of per-ticker hit rates — `authority_contract.expected_alpha_gate()`, unmodified):

**Expected Alpha Hit Rate: 61.03%**

Target: **>=75%**

**Status: FAIL**

*(Pooled/micro alternative for reference only, not the official metric: 23/37 = 62.16%.)*

Detected-Alpha definition reused unmodified from `regression_report_v3._detected_alphas()`: a claim's Alpha counts as detected only at level `active`, `dominant`, or `regime_level` — `candidate`, `blocked`, `ambiguous`, `unavailable` never count. Actual detected Alphas read directly from each run's persisted `run_audit.json`, not recomputed, not copied from any prior diagnostic report.

---

## Main Conflict Gold Results

| Ticker | Gold Main Conflict | Actual | Match |
|---|---|---|---|
| NVDA | `A101__A304` | `A101__A304` | ✅ |
| QQQ | `A304__A601` | `A304__A601` | ✅ |
| MSFT | `A301__A304` | none admitted | ❌ |
| SNDK | `NO_ADMITTED_MAIN_CONFLICT` | none admitted | ✅ |
| TSM | `A101__A304` | `A101__A304` | ✅ |
| AMD | `A101__A304` | `A101__A304` | ✅ |

**Main Conflict Match: 5/6 = 83.33%**

Target: **>=4/6**

**Status: PASS**

Actual main conflicts read directly from each run's persisted `run_audit.json` `conflict_summary.main_conflict_id` — not copied from the task prompt.

---

## Final Revalidation Update

```
Previous status:    NOT_GOLD_EVALUABLE
Reason:             No approved Gold existed at that time
                     (see v0_1_3_final_revalidation.json/.md — left unmodified,
                     historically accurate for when it was written)

New status:         Gold benchmark alpha_conflict_gold.v1 has now been
                     explicitly frozen (this task)

Current six-run evaluation mode: RETROSPECTIVE_GOLD_VALIDATION

Expected Alpha Hit Rate:  61.03%  ->  FAIL  (target >=75%)
Main Conflict Match:      5/6 = 83.33%  ->  PASS  (target >=4/6)
```

`v0_1_3_final_revalidation.json/.md` is **not** rewritten as though Gold existed before it did — it stands exactly as originally written. This document is the authoritative successor for Gold-evaluable status going forward.

**No PASS was manufactured.** Expected Alpha Hit genuinely fails the ≥75% target against this newly-frozen Gold; Main Conflict Match genuinely passes the ≥4/6 target. Both are reported as computed.

**Provider calls: 0. TradingAgents calls: 0. No ticker run. No production code changed.**
