# v0.2 Candidate 3 — Development Result

**Run type: `DEVELOPMENT_METRIC_ONLY`.** This is a development metric against the SAME 100-sample Development Gold used to design Candidate 3 — it is NOT an independent validation and must never be cited as one. The sealed 150-sample final independent holdout was not touched.

Development Gold SHA256 (verified unchanged before this run): `e8a78cbbb9359eb1361ca43891b52e71fa38528e0b6914c91aa5c9d874902ada`

Provider: `anthropic` / `claude-sonnet-4-6`. Prompt versions at time of run: `week2.alpha_classifier.v6` / `week2.alpha_classifier_batch.v4`.

## Headline

| Metric | Baseline (v3) | Candidate 3 (v6) | Delta |
|---|---:|---:|---:|
| Correct | 64 | 81 | +17 |
| Incorrect | 36 | 19 | -17 |
| **Accuracy** | **64.00%** | **81.00%** | **+17.00pp** |

## NONE Precision / Recall

| Metric | Baseline | Candidate 3 |
|---|---:|---:|
| NONE precision | 98.00% (49/50) | 98.44% (63/64) |
| NONE recall | 61.25% (49/80) | 78.75% (63/80) |

NONE recall improved sharply (the dominant baseline failure mode) while NONE precision held essentially flat — the classifier is now both more willing to say NONE where appropriate AND still almost never wrong when it does.

## Regression Chain

| | Count |
|---|---:|
| Old baseline errors fixed | 18 |
| Old baseline errors still remaining | 18 |
| **New regressions introduced** | **1** |

The single new regression (`gold-dev-045`, MU — "Average Brokerage Recommendation (ABR) is bullish — Wall Street consensus favors adding MU to portfolios", Gold=NONE, System=A601) is an isolated side effect: the new A601 clause's "crowd positioning" language was over-applied to a single analyst-consensus rating rather than the richer narrative/media-attention dynamics it was meant to target (contrast with the correctly-labeled A601 cases, e.g. `gold-dev-025`/`039`/`096`/`099`, which each describe multiple bullish opinion pieces, StockTwits sentiment, cross-name thematic rallies, or explicit institutional-caution narratives). This is one isolated sample, not a systematic new failure class — 18 old errors were fixed for every 1 new one introduced.

## Confusion Pairs (Gold → System, remaining 19 errors)

| Gold → System | Count |
|---|---:|
| NONE → A304 | 5 |
| NONE → A301 | 4 |
| NONE → A201 | 3 |
| NONE → A601 | 2 |
| NONE → A101 | 1 |
| NONE → A102 | 1 |
| NONE → A103 | 1 |
| A301 → A304 | 1 |
| A301 → NONE | 1 |

## Provider Telemetry

| Field | Value |
|---|---:|
| Provider calls | 100 |
| Retries | 0 |
| Timeouts | 0 |
| Unavailable results | 0 |
| Elapsed seconds | 150.1 |
| Tokens | NOT_MEASURED |
| Cost | NOT_MEASURED |

## Safety

Final 150-sample independent holdout touched: **NO**. Independent validation claimed: **NO**.
