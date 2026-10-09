# T2 Scenario (f) fix — six-ticker impact (2026-10-04)

**Incident note (full disclosure):** verifying this fix, I ran the existing
`run_six_ticker_acceptance_typea_2026-09-29.py` script, which writes to its
own hardcoded path `t2_six_ticker_acceptance_verdicts_2026-09-29.json` —
this **overwrote** that dated historical artifact with today's (post-fix)
results, which I should have checked/copied before running. I located an
intact copy inside an earlier delivery package in `~/Library/Mobile
Documents/.Trash/COMQUTOR_John_Acceptance_Delivery_20261003T235956Z/...`
and restored the file to its exact original (pre-overwrite) byte content
— confirmed via diff (now empty). This file documents the real,
intentional before/after difference without touching that file again.

## What changed

Before this round, `run_formal_acceptance` had no mechanism to detect an
admitted conflict pair that matches none of a ticker's declared
`required_conflicts`/`conditional_conflicts`/`allowed_conflicts`/
`product_decision_pending`/`remove_while_undeclared` categories — such a
pair was never flagged anywhere in the result, even though John's own
task sheet names this exact scenario by example: "NVDA当前的A304__A601继续
保留为待审核结果" (NVDA's current A304__A601 should continue to be kept as
a pending-review result).

New `_undeclared_admitted_conflicts()` detects this directly; a non-empty
result now folds into `needs_review` (never `fail`, never changes the
conflict's own admission or the research answer) and is surfaced in a new,
additive `undeclared_admitted_conflicts` field.

## Six-ticker comparison (Type A re-evaluation, same already-persisted run
artifacts, zero Provider calls, zero recompute — only the acceptance/
verdict layer re-executed)

| Ticker | Admitted conflicts | `formal_status` BEFORE this fix | `formal_status` AFTER this fix | Reason for the change |
|---|---|---|---|---|
| NVDA | A304__A601 | `needs_review` (via an unrelated should_detect_if_supported soft-miss) | `needs_review` (same status, but NOW also because `undeclared_admitted_conflicts: ["A304__A601"]` — previously this specific pair was never flagged by anything) | No status change, but the real reason John named is now actually tracked |
| QQQ | A003__A501, A304__A601, A501__A601 | `needs_review` | `needs_review` (`undeclared_admitted_conflicts: ["A304__A601", "A501__A601"]`) | Same |
| SNDK | (none admitted) | `needs_review` | `needs_review` (`undeclared_admitted_conflicts: []`) | No change — nothing admitted, nothing undeclared |
| **MSFT** | A301__A304, A304__A601 | **`pass`** | **`needs_review`** (`undeclared_admitted_conflicts: ["A304__A601"]`) | **Real status change** — A304__A601 was silently passing before |
| **TSM** | A101__A304, A301__A304, A304__A601 | **`pass`** | **`needs_review`** (`undeclared_admitted_conflicts: ["A304__A601"]`) | **Real status change** |
| **AMD** | A101__A304, A301__A304, A304__A601 | **`pass`** | **`needs_review`** (`undeclared_admitted_conflicts: ["A304__A601"]`) | **Real status change** |

**3 of 6 tickers (MSFT/TSM/AMD) genuinely flip from a bare `pass` to
`needs_review`** — this is the fix doing exactly what John's scenario (f)
asked: an admitted conflict outside every declared category now genuinely
routes to review instead of silently passing. No conflict's own admission
changed, no research answer changed, no score changed — confirmed by the
`admitted_conflicts`/`candidate_conflicts`/`main_conflict` fields being
byte-identical before and after in every one of the six tickers.
