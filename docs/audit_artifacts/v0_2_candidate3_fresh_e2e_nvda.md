# v0.2 Candidate 3 — Fresh E2E: NVDA

**Run type: `FRESH_END_TO_END_VALIDATION`** — operational/product validation evidence. Not old-result re-evaluation, not development regression, not Final Gold evaluation, not Candidate 3 tuning, not a replacement for the frozen Alpha (82.67%) or polarity (87.23%) validation.

| | |
|---|---|
| run_id | `ded99ecd-a186-4a90-859e-0f1a0efa43db` |
| Start / End | 2026-09-17T22:43:57Z → 2026-09-17T23:16:01Z |
| Wall-clock | 1923s (32m03s) |
| Candidate 3 prompt confirmed in run | `week2.alpha_classifier.v6` |
| Final status | `completed` |

## Provider Accounting

| | |
|---|---:|
| Provider / model | deepseek / deepseek-v4-flash (live server's unified research profile — a different but equally real Provider path from the formal paid Alpha/polarity validation, which used Anthropic) |
| Total semantic Provider calls | 819 |
| — alpha_classifier | 754 |
| — evidence_stance_classifier | 34 |
| — structure_extractor | 3 |
| — structured_adapter | 10 |
| Retries | 18 |
| Timeouts | 0 |
| Error-tagged records | 7 |
| Fallback count | 10 |
| Rejected count | 3 |
| Tokens | Field present, every value null — effectively unavailable (same disclosed limitation as the Day 4B precedent) |
| Cost | `NOT_AVAILABLE` — no reliable token counts to estimate from |

## Structure / Alpha Result

**Dominant:** A301 (Revenue Expansion, positive, activation 74.21, 18 evidence groups/3 agents), A304 (Multiple Compression, negative, activation 71.73, 23 evidence groups/5 agents).
**Active:** A601 (Narrative Momentum, positive, activation 69.66, 43 evidence groups/5 agents).
Graph coherence: 100.0 (8 valid edges, 7 Alphas covered). 0 blocked Alphas.

## Main Conflict — Full Arbitration Picture

**Admitted: `A304__A601`** (bear=A304, bull=A601), conflict_level **low**, conflict_score **9.544**, canonical taxonomy pair (contradiction_weight 0.80), admissibility status `admitted` (zero reason codes — cleared every bar).

All 6 canonical candidate pairs were arbitrated:

| Pair | Outcome | Reason |
|---|---|---|
| A001__A501 | rejected | Missing left evidence, direction role unresolved |
| A003__A501 | suppressed | Both sides below score/evidence threshold |
| A101__A304 | suppressed | Bull score below threshold |
| **A301__A304** | **suppressed** | **`NO_BULL_TICKER_SPECIFIC_SUPPORT`** — see below |
| **A304__A601** | **admitted** | Cleared all bars |
| A501__A601 | suppressed | Bear score below threshold, insufficient bear evidence |

**Why not A301__A304 (NVDA's own allowed pair)?** A301 is independently dominant (74.21, higher than A304's 71.73) with real evidence (18 groups, 3 agents) — but none of that evidence cleared the conflict engine's *stricter*, conflict-specific ticker-specific-support bar for the bull role against A304 in this run. This is a mechanically-grounded suppression under the same `week4.conflict_admissibility.b2.v1` formula that governs every ticker — not a bug, not a forced result, not cherry-picked.

**Why A304__A601?** Both sides have genuine, ticker-specific evidence: A304 (bear) 3 ticker-specific groups (e.g., "No Fed cuts in 2026... discount rates stay high; multiple headwind"), A601 (bull) 9 ticker-specific groups (e.g., "passive inflows into VOO/QQQ are, in effect, forced NVDA buying"; "NVDA gained on the Fed reaction day... market is currently prioritizing the demand story").

## Frozen Rule Check

NVDA's own allowed main-conflict baseline: `[A101__A304, A301__A304]`. The admitted conflict (`A304__A601`) is **not** on this list, though it **is** a canonical taxonomy pair (contradiction_weight 0.80) and was cleanly admitted under the identical frozen admissibility formula used for every ticker.

- `forbidden_dominant_without_strong_evidence`: **PASS** — both dominant Alphas have real, multi-agent evidence.
- `do_not_force`: **PASS** — A301 was not force-admitted into the conflict despite its dominance; it was suppressed on its own evidentiary merits.
- Evidence for the admitted dominant/conflict Alphas: **genuine and ticker-specific**, confirmed directly from the run's own evidence payload.

**Distinguishing note from the QQQ A301__A304 precedent:** unlike QQQ's case (described as the richest, most cross-corroborated evidence base in that run), this NVDA conflict is explicitly `conflict_level: low`, `conflict_score: 9.544` — a genuine but comparatively weak signal. Disclosed honestly, not inflated to match the QQQ precedent's confidence.

**NVDA Fresh run conflict status: `REVIEW_REQUIRED`.** This is this fresh run's own honest rule-check finding — reported per explicit instruction not to force PASS. It does **not** modify the frozen baseline, does **not** alter any historical frozen NVDA record from a different run/day, and is separate from the closed Final Alpha/polarity gates.

## Completeness

Required artifacts: 9/9 present (`pass`). Optional artifacts present: `entity_alpha_exposures.json`, `summary.json`, `evidence_stance_audit.json`, `unclassified_findings.json`. Research / Structure Graph / Evidence / Conflict Radar: all **available**.

Source-citation caveat: the existence of a `claim_id` is an internal identifier into this run's own persisted agent-output records — it is not, by itself, proof that the underlying source was externally verified.
