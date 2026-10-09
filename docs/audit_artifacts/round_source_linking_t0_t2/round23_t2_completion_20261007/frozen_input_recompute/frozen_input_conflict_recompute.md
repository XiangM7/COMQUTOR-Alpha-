# Frozen-input conflict recompute — t2-frozen-input-recompute-20261007

- Execution type: **FROZEN_INPUT_RECOMPUTE** | Provider calls: **0** | Model calls: **0** | Generated: 2026-10-08T02:16:59Z
- Only the deterministic conflict detector is re-run, on each saved run's own saved alpha_activations.json and alpha_matches.json, under the current taxonomy. Nothing is written into the run directories. The runs predate source linking, so the verified-evidence gate is off, exactly as when their conflicts.json was written: this says what the evidence-driven admissibility gate does with the new pairs on real saved inputs, not whether that evidence is verified.

## 1. Admitted conflicts: what the run saved vs what the current taxonomy yields on the same saved inputs

| Ticker | Run | Status | Saved admitted | Recomputed admitted | Added | Main conflict (saved → recomputed) |
|---|---|---|---|---|---|---|
| NVDA | ded99ecd | RECOMPUTED | A304__A601 | A304__A601 | — | A304__A601 → A304__A601 |
| QQQ | 0d890564 | RECOMPUTED | A003__A501, A304__A601, A501__A601 | A003__A501, A304__A601, A501__A601 | — | A003__A501 → A003__A501 |
| SNDK | e8e0f398 | RECOMPUTED | — | — | — | None → None |
| MSFT | 64568bfb | RECOMPUTED | A301__A304, A304__A601 | A301__A304, A304__A601 | — | A301__A304 → A301__A304 |
| TSM | fc09821e | RECOMPUTED | A101__A304, A301__A304, A304__A601 | A101__A304, A201__A304, A301__A304, A304__A601 | A201__A304 | A101__A304 → A101__A304 |
| AMD | d5b60b8a | RECOMPUTED | A101__A304, A301__A304, A304__A601 | A101__A304, A201__A304, A301__A304, A304__A601 | A201__A304 | A301__A304 → A301__A304 |

## 2. The two pairs T2 made evaluable (A102__A304, A201__A304)

| Ticker | Pair | Saved | Recomputed | Reason codes (recomputed) | Supporting facts bull / bear | Scores bull / bear |
|---|---|---|---|---|---|---|
| NVDA | A102__A304 | not_reached | candidate | BULL_SCORE_BELOW_THRESHOLD | 2 / 17 | 36.2508 / 71.7302 |
| NVDA | A201__A304 | not_reached | candidate | BULL_SCORE_BELOW_THRESHOLD | 6 / 17 | 31.8193 / 71.7302 |
| QQQ | A102__A304 | not_reached | candidate | BULL_SCORE_BELOW_THRESHOLD, INSUFFICIENT_BULL_SUPPORTING_EVIDENCE | 1 / 10 | 35.7243 / 62.9705 |
| QQQ | A201__A304 | not_reached | candidate | BULL_SCORE_BELOW_THRESHOLD, NO_BULL_TICKER_SPECIFIC_SUPPORT | 2 / 10 | 49.6909 / 62.9705 |
| SNDK | A102__A304 | not_reached | not_reached | — | None / None | None / None |
| SNDK | A201__A304 | not_reached | candidate | NO_BEAR_TICKER_SPECIFIC_SUPPORT | 15 / 7 | 84.22 / 53.7399 |
| MSFT | A102__A304 | not_reached | candidate | BULL_SCORE_BELOW_THRESHOLD, INSUFFICIENT_BULL_SUPPORTING_EVIDENCE, NO_BULL_TICKER_SPECIFIC_SUPPORT | 1 / 21 | 41.9468 / 71.1556 |
| MSFT | A201__A304 | not_reached | not_reached | — | None / None | None / None |
| TSM | A102__A304 | not_reached | not_reached | — | None / None | None / None |
| TSM | A201__A304 | not_reached | admitted | — | 12 / 7 | 61.5376 / 64.9288 |
| AMD | A102__A304 | not_reached | candidate | BULL_SCORE_BELOW_THRESHOLD | 7 / 17 | 48.0399 / 81.5323 |
| AMD | A201__A304 | not_reached | admitted | — | 13 / 17 | 62.5918 / 81.5323 |

