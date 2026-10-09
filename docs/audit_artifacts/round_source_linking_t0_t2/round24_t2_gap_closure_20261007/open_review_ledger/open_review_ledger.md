# Open-review ledger — NVDA / QQQ disputes recorded on their own

- Generated: 2026-10-08T06:03:23Z | Execution type: **A_REEVALUATION** | Provider calls: **0**
- Policy: An item is closed only by a recorded review decision (closure_records). A later run's PASS never closes an earlier run's item, and a PASS whose coverage shows no rule was exercised (pass_is_vacuous) says nothing about the declared rules at all. Two kinds of finding are listed apart from the open items because they are not disputes: a diagnostic (an engine-defined reading with no approval basis, which decides no verdict) and a rule that could not be evaluated for the run (reported, never closed and never mistaken for a review decision).
- Closure records: **0** (no recorded review decision closes any item below).

## What John's text names

- *NVDA 当前的 A304__A601 继续保留为待审核结果* — COMQUTOR Alpha 下一轮开发任务单, T2 第四 (pair `A304__A601`)
- *QQQ 新 run 的 PASS 不能替代旧 run 尚未关闭的复核* — COMQUTOR Alpha 下一轮开发任务单, T2 第四

## NVDA

- Saved runs: **18** — status counts `{"alpha_semantic_unavailable": 3, "needs_review": 11, "not_evaluable": 4}`; open items: **7**; diagnostic findings (decide nothing): **11**; rule evaluations that could not be made: **30**.
- Most recent saved run: `034a0a60` (2026-10-02) → **needs_review**.
- PASS runs dated after the first open item: **0**; items they close: **0**.

| Run | Analysis date | formal_status | Vacuous PASS | Admitted conflicts | Open items |
|---|---|---|---|---|---|
| 4ca7dafa | 2026-07-17 | not_evaluable |  | — | 0 |
| c0323fdb | 2026-07-28 | alpha_semantic_unavailable ALPHA_MATCHES_PAYLOAD_MISSING |  | — | 0 |
| 0e044e37 | 2026-07-30 | not_evaluable |  | — | 0 |
| e434f80b | 2026-07-30 | not_evaluable |  | — | 0 |
| e3eb3909 | 2026-08-11 | needs_review |  | A101__A304, A301__A304 | 0 |
| 5ffe121a | 2026-08-14 | needs_review |  | A301__A304, A304__A601 | 1 |
| 1496aac6 | 2026-08-21 | alpha_semantic_unavailable ALL_CLAIMS_MATCH_STATUS_UNAVAILABLE |  | — | 0 |
| 6f4e07f9 | 2026-08-25 | needs_review |  | — | 0 |
| _step5a_ | 2026-08-25 | not_evaluable |  | — | 0 |
| 948be419 | 2026-08-27 | needs_review |  | A101__A304, A301__A304, A304__A601 | 1 |
| a8d47429 | 2026-08-28 | needs_review |  | A101__A304, A301__A304 | 0 |
| 40bd7e3d | 2026-09-01 | alpha_semantic_unavailable ALL_CLAIMS_MATCH_STATUS_UNAVAILABLE |  | — | 0 |
| c9abf687 | 2026-09-02 | needs_review |  | A101__A304, A304__A601 | 1 |
| 2f8ee897 | 2026-09-02 | needs_review |  | A101__A304, A301__A304, A304__A601 | 1 |
| 57d7b4c4 | 2026-09-04 | needs_review |  | A101__A304, A301__A304, A304__A601 | 1 |
| 421bca7a | 2026-09-16 | needs_review |  | A101__A304, A304__A601 | 1 |
| ded99ecd | 2026-09-17 | needs_review |  | A304__A601 | 1 |
| 034a0a60 | 2026-10-02 | needs_review |  | — | 0 |

### NVDA — items

| Run | Kind | Rule family | Pair / Alpha | Status | Detail |
|---|---|---|---|---|---|
| 5ffe121a | review | undeclared_admitted_conflict | A304__A601 | open | review_required |
| 948be419 | review | undeclared_admitted_conflict | A304__A601 | open | review_required |
| c9abf687 | review | undeclared_admitted_conflict | A304__A601 | open | review_required |
| 2f8ee897 | review | undeclared_admitted_conflict | A304__A601 | open | review_required |
| 57d7b4c4 | review | undeclared_admitted_conflict | A304__A601 | open | review_required |
| 421bca7a | review | undeclared_admitted_conflict | A304__A601 | open | review_required |
| ded99ecd | review | undeclared_admitted_conflict | A304__A601 | open | review_required |

### NVDA — diagnostic findings (engine-defined, no approval basis, decide no verdict; not disputes)

| Rule family | Pair | Diagnostic result | Runs |
|---|---|---|---|
| should_detect_if_supported | A101__A304 | needs_review | 1 |
| should_detect_if_supported | A101__A304 | pending_review | 4 |
| should_detect_if_supported | A301__A304 | needs_review | 2 |
| should_detect_if_supported | A301__A304 | pending_review | 4 |

### NVDA — rules that could not be evaluated (reported, not disputes)

| Rule / pair | Blocking | Reason | Runs |
|---|---|---|---|
| NVDA-A101-AI-GROWTH | True | RUN_NOT_BOUND_TO_FROZEN_TRIGGER_MATRIX | 10 |
| NVDA-A304-VALUATION-RISK | True | RUN_NOT_BOUND_TO_FROZEN_TRIGGER_MATRIX | 10 |
| NVDA-GROWTH-VS-VALUATION-CONFLICT | True | RUN_NOT_BOUND_TO_FROZEN_TRIGGER_MATRIX | 10 |

## QQQ

- Saved runs: **11** — status counts `{"alpha_semantic_unavailable": 2, "needs_review": 4, "not_evaluable": 1, "pass": 4}`; open items: **4**; diagnostic findings (decide nothing): **3**; rule evaluations that could not be made: **0**.
- Most recent saved run: `0d890564` (2026-09-17) → **needs_review**.
- PASS runs dated after the first open item: **2**; items they close: **0**.

| Run | Analysis date | formal_status | Vacuous PASS | Admitted conflicts | Open items |
|---|---|---|---|---|---|
| a364e0ee | 2026-07-31 | pass | yes | — | 0 |
| 57244747 | 2026-08-25 | pass | yes | — | 0 |
| _step5a_ | 2026-08-25 | alpha_semantic_unavailable ALPHA_MATCHES_PAYLOAD_MISSING |  | — | 0 |
| _step5a_ | 2026-08-25 | alpha_semantic_unavailable ALPHA_MATCHES_PAYLOAD_MISSING |  | — | 0 |
| _step5a_ | 2026-08-25 | not_evaluable |  | — | 0 |
| defeb528 | 2026-08-28 | needs_review |  | A101__A304, A304__A601 | 1 |
| f88c8956 | 2026-09-04 | pass |  | A304__A601 | 0 |
| f239a53f | 2026-09-11 | needs_review |  | A301__A304, A304__A601 | 1 |
| 85cfd878 | 2026-09-14 | needs_review |  | A101__A304, A304__A601 | 1 |
| a4dae9c5 | 2026-09-16 | pass |  | — | 0 |
| 0d890564 | 2026-09-17 | needs_review |  | A003__A501, A304__A601, A501__A601 | 1 |

### QQQ — items

| Run | Kind | Rule family | Pair / Alpha | Status | Detail |
|---|---|---|---|---|---|
| defeb528 | review | undeclared_admitted_conflict | A101__A304 | open | review_required |
| f239a53f | review | undeclared_admitted_conflict | A301__A304 | open | review_required |
| 85cfd878 | review | undeclared_admitted_conflict | A101__A304 | open | review_required |
| 0d890564 | review | undeclared_admitted_conflict | A501__A601 | open | review_required |

### QQQ — diagnostic findings (engine-defined, no approval basis, decide no verdict; not disputes)

| Rule family | Pair | Diagnostic result | Runs |
|---|---|---|---|
| should_detect_if_supported | A001__A501 | needs_review | 2 |
| should_detect_if_supported | A001__A501 | pending_review | 1 |

