# v0.2 Candidate 3 — Baseline Development Result

**Run type:** `BASELINE_DEVELOPMENT_EVALUATION` — real Provider-backed run of the **current, unmodified** production Alpha semantic classifier (`week2.alpha_classifier.v3`) against the frozen 100-sample Development Gold. This is a development metric, not an independent validation result.

Development Gold SHA256 (verified unchanged before this run): `e8a78cbbb9359eb1361ca43891b52e71fa38528e0b6914c91aa5c9d874902ada`

Provider: `anthropic` / `claude-sonnet-4-6`

## Headline

| Metric | Value |
|---|---:|
| Correct | 64 |
| Incorrect | 36 |
| **Accuracy** | **64.00%** |

## NONE Precision / Recall

| Metric | Value |
|---|---:|
| NONE precision | 98.00% (49/50) |
| NONE recall | 61.25% (49/80) |

The classifier is extremely precise when it *does* say NONE (almost never wrong), but it significantly under-uses NONE — Gold calls for NONE on 80/100 samples but the system only lands there for 50/100.

## Error Breakdown

| Category | Count |
|---|---:|
| False positives (Gold NONE, system selected an Alpha) | 31 |
| False negatives (Gold = an Alpha, system said NONE) | 1 |
| Wrong-Alpha substitutions (both non-NONE, different Alpha) | 4 |
| **Total incorrect** | **36** |

The dominant failure mode is the **opposite** of Candidate 1's over-conservatism: this baseline is over-eager to select an Alpha from thematic/topical/technical evidence that does not actually engage a canonical mechanism.

## Confusion Pairs (Gold → System)

| Gold → System | Count |
|---|---:|
| NONE → A301 | 7 |
| NONE → A304 | 7 |
| NONE → A201 | 5 |
| NONE → A101 | 5 |
| NONE → A601 | 3 |
| NONE → A103 | 3 |
| NONE → A102 | 1 |
| A301 → A201 | 2 |
| A301 → A304 | 1 |
| A103 → A101 | 1 |
| A304 → NONE | 1 |

## Provider Telemetry

| Field | Value |
|---|---:|
| Provider calls | 100 |
| Retries | 0 |
| Timeouts | 0 |
| Unavailable results | 0 |
| Chunk count | 1 |
| Elapsed seconds | 182.61 |
| Tokens | NOT_MEASURED — harness does not capture per-call token counts |
| Cost | NOT_MEASURED — no token counts captured, no provider billing query performed |

## Safety

Final 150-sample independent holdout touched: **NO**.
