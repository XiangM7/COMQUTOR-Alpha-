# v0.2 Candidate 3 — Fresh E2E: QQQ

**Run type: `FRESH_END_TO_END_VALIDATION`** — operational/product validation evidence. Not old-result re-evaluation, not development regression, not Final Gold evaluation, not Candidate 3 tuning, not a replacement for the frozen Alpha (82.67%) or polarity (87.23%) validation.

| | |
|---|---|
| run_id | `0d890564-2479-4361-94e8-25c48af3b9a8` |
| Start / End | 2026-09-17T23:17:00Z → 2026-09-17T23:45:42Z |
| Wall-clock | 1721s (28m41s) |
| Candidate 3 prompt confirmed in run | `week2.alpha_classifier.v6` |
| Final status | `completed` |

## Provider Accounting

| | |
|---|---:|
| Provider / model | deepseek / deepseek-v4-flash |
| Total semantic Provider calls | 812 |
| — alpha_classifier | 747 |
| — evidence_stance_classifier | 23 |
| — structure_extractor | 8 |
| — structured_adapter | 10 |
| Retries | 24 |
| Timeouts | 0 |
| Error-tagged records | 7 |
| Fallback count | 14 |
| Rejected count | 7 |
| Tokens | Field present, every value null — unavailable |
| Cost | `NOT_AVAILABLE` |

## Structure / Alpha Result

**Dominant:** none. **Active:** A003 (Liquidity Expansion, +, 63.92, 7 groups/3 agents), A304 (Multiple Compression, −, 62.97, 12 groups/3 agents), A501 (Recession Risk, −, 54.94, 4 groups/2 agents), A601 (Narrative Momentum, +, 54.32, 33 groups/5 agents). Graph coherence: 100.0 (16 valid edges, 10 Alphas covered). 0 blocked.

**No dominant Alpha this run is legitimate** — per explicit instruction, a dominant Alpha is never required; four Alphas cleared "active" with real evidence, none crossed the higher dominant threshold.

## Main Conflict — Full Arbitration Picture

3 of 6 canonical candidate pairs were admitted:

| Pair | Outcome | Score | On QQQ allow-list? |
|---|---|---:|---|
| A001__A501 | suppressed | — | — |
| **A003__A501** | **admitted (selected as main)** | **23.92** | **YES** |
| A101__A304 | suppressed | — | — |
| A301__A304 | suppressed | — | — |
| A304__A601 | admitted | 9.69 | YES |
| A501__A601 | admitted | 17.31 | no |

**Main conflict: `A003__A501`** (bull=A003, bear=A501), conflict_level low, admissibility `admitted` (zero reason codes), bull ticker-specific support 5, bear ticker-specific support 1.

Evidence is genuinely QQQ/ETF-level, not one constituent: bull side cites "QQQ inflows totaled nearly $1B on 2026-09-16 (etf.com)" — fund-flow data intrinsic to the ETF itself. Bear side cites recession-risk/credit-spread macro commentary.

**The historically-cited off-list `A301__A304` conflict did NOT reproduce this run.** It was suppressed (`BULL_SCORE_BELOW_THRESHOLD`, `INSUFFICIENT_BULL_SUPPORTING_EVIDENCE`, `NO_BULL_TICKER_SPECIFIC_SUPPORT`) on its own evidentiary merits under the identical formula — nothing was rewritten or forced to produce this outcome.

## Frozen Rule Check

QQQ's allowed main-conflict baseline: `[A001__A501, A003__A501, A304__A601]`. The admitted, highest-scored main conflict (`A003__A501`) **is on this list**.

- `forbidden_dominant_without_strong_evidence`: N/A — no Alpha reached dominant level.
- `do_not_force`: **PASS** — A301__A304 was not forced; it was suppressed on its own merits.
- Lack of a dominant Alpha: **legitimate**, explicitly permitted.

**QQQ Fresh run conflict status: `PASS`.**

This is this fresh run's own honest finding. It does **not** retroactively resolve, override, or reinterpret the standing, carried QQQ Formal Gold `REVIEW_REQUIRED` status from the earlier frozen-input run that produced the off-list `A301__A304` conflict (a different run, different day, different evidence) — that historical record and its unadopted `RULE_CHANGE_RECOMMENDATION` remain unchanged. This run simply produced a different, on-list conflict instead.

## Completeness

Required artifacts: 9/9 present (`pass`). Research / Structure Graph / Evidence / Conflict Radar: all **available**.

Source-citation caveat: a `claim_id`'s existence is an internal identifier into this run's own persisted agent-output records, not proof of external source verification.
