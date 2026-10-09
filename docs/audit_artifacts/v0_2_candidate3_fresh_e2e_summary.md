# v0.2 Candidate 3 — Fresh E2E Summary (NVDA + QQQ)

**Run type: `FRESH_END_TO_END_VALIDATION`.** Operational/product validation evidence — never merged, averaged, or substituted for the scored gates below.

## Four Evidence Tiers (kept explicitly separate)

| Tier | Artifact | Denominator | Result |
|---|---|---:|---:|
| 1. Frozen regression evidence | `v0_2_day4_frozen_regression.json` (historical, untouched) | — | — |
| 2. Independent Alpha validation | `v0_2_candidate3_final_validation_result.json` | 124/150 | **82.67%** ✅ ≥80% |
| 3. Independent polarity validation | `item2_blind_holdout2_summary.json` | 123/141 | **87.23%** ✅ ≥80% |
| 4. Fresh E2E evidence | `v0_2_candidate3_fresh_e2e_nvda.json` / `_qqq.json` | N/A — not a scored gate | operational only |

**These four tiers are never combined.** Tiers 2 and 3's percentages are not recomputed, diluted, or affected by tier 4's structural outcomes in any way.

## NVDA (run `ded99ecd-a186-4a90-859e-0f1a0efa43db`)

Completed in 1923s (32m03s). Dominant: A301, A304. Active: A601. Main conflict admitted: **A304__A601** — a canonical taxonomy pair, cleanly admitted under the frozen admissibility formula, but **not** on NVDA's own allowed list (`A101__A304`, `A301__A304`). Fresh run conflict status: **`REVIEW_REQUIRED`**, reported honestly per explicit instruction not to force PASS. Provider calls: 819 (deepseek/deepseek-v4-flash), 18 retries, 0 timeouts. Artifact completeness: 9/9 pass.

## QQQ (run `0d890564-2479-4361-94e8-25c48af3b9a8`)

Completed in 1721s (28m41s). Dominant: none (legitimate — never required). Active: A003, A304, A501, A601. Main conflict admitted: **A003__A501** — on QQQ's own allowed list, genuine ETF-level evidence on both sides. Fresh run conflict status: **`PASS`**. The historically-cited off-list `A301__A304` conflict did **not** reproduce this run — it was suppressed on its own merits, not forced. Provider calls: 812 (deepseek/deepseek-v4-flash), 24 retries, 0 timeouts. Artifact completeness: 9/9 pass.

This fresh PASS does **not** retroactively resolve QQQ's standing, carried Formal Gold `REVIEW_REQUIRED` status from the earlier frozen-input run — that historical record and its unadopted `RULE_CHANGE_RECOMMENDATION` remain unchanged; a different run on a different day simply produced a different, on-list conflict.

## Raw Performance Accounting

| | NVDA | QQQ |
|---|---:|---:|
| Wall-clock | 1923s | 1721s |
| Total Provider calls | 819 | 812 |
| Alpha-classification calls | 754 | 747 |
| Retries | 18 | 24 |
| Timeouts | 0 | 0 |
| Tokens | NOT_AVAILABLE | NOT_AVAILABLE |
| Measured cost | NOT_AVAILABLE | NOT_AVAILABLE |
| Estimated cost | Not made — no reliable token basis exists | Not made — no reliable token basis exists |

No inference was made that QQQ's ~10.5% shorter wall-clock time implies a proportional cost reduction — cost remains `NOT_AVAILABLE` for both, independently.

## Post-Run Integrity

Final Alpha Gold SHA256 unchanged: **YES**. Candidate 3 classifier/batch hashes unchanged: **YES**. Production code changed: **NO**.

## Day 5 Readiness

| Gate | Status |
|---|---|
| Alpha gate | Closed (82.67% ≥ 80%) |
| Polarity gate | Closed (87.23% ≥ 80%) |
| NVDA Fresh E2E | Complete, inspectable |
| QQQ Fresh E2E | Complete, inspectable |
| **LATEST_VERSION_FRESH_E2E_REQUIREMENT_COMPLETE** | **YES** |
| **DAY_5_READY** | **YES** |

`DAY_5_READY = YES` means ready to **begin** the separate Day 5 package/demo task — it does not mean Day 5 itself has already passed, and Formal Gold PASS is not automatically declared from Fresh completion alone.
