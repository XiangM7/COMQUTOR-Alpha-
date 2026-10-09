# v0.2 Candidate 3 — ONE-SHOT INDEPENDENT FINAL VALIDATION RESULT

**Validation type: `ONE_SHOT_INDEPENDENT_FINAL_VALIDATION`.** This is the one and only planned Candidate 3 evaluation pass against the frozen 150-sample Final Gold. Candidate 3 is now permanently closed for this validation cycle — no tuning, no rerun, no Candidate 4 based on these results.

Final Gold SHA256 (verified unchanged before this run): `a3c402ce391cfba1bd49d3d84a352e222e2775118f24b9ebf2a003183e2392de`

Candidate 3: classifier `d53b2d7511f4c4a8089db746d09e4c79cb38f22597dac6459920ca3deac1171d` (`week2.alpha_classifier.v6`), batch `a03c8f673ffd387a866bc8dd585c4c96cf5464b80a50cb6e4c3fc5f894f68379` (`week2.alpha_classifier_batch.v4`) — verified byte-identical to the Day 4G freeze both before and after this run.

Provider: `anthropic` / `claude-sonnet-4-6`.

## Headline

| Metric | Value |
|---|---:|
| Correct | 124 |
| Incorrect | 26 |
| **Final Alpha accuracy** | **82.67%** |
| Frozen Alpha target | ≥ 80.00% |
| **FINAL_ALPHA_TARGET_MET** | **YES** |

Development metric (historical context only, never combined with these samples): 81.00% on the 100-sample Development Gold (Day 4G).

## NONE Precision / Recall / F1

| Metric | Value |
|---|---:|
| NONE precision | 96.08% (98/102) |
| NONE recall | 84.48% (98/116) |
| NONE F1 | 89.91% |

## Non-NONE Performance

| Metric | Value |
|---|---:|
| Gold NONE count | 116 |
| Gold non-NONE count | 34 |
| Non-NONE correct | 26 |
| **Non-NONE accuracy/recall** | **76.47%** |

## Error Breakdown

| Category | Count |
|---|---:|
| False positives (Gold NONE, system selected an Alpha) | 18 |
| False negatives (Gold = an Alpha, system said NONE) | 4 |
| Wrong-Alpha substitutions | 4 |
| **Total incorrect** | **26** |

## Per-Class Precision / Recall

| Alpha | Gold Support | TP | FP | FN | Precision | Recall |
|---|---:|---:|---:|---:|---:|---:|
| NONE | 116 | 98 | 4 | 18 | 96.08% | 84.48% |
| A301 | 9 | 7 | 2 | 2 | 77.78% | 77.78% |
| A304 | 8 | 6 | 10 | 2 | 37.50% | 75.00% |
| A101 | 6 | 3 | 0 | 3 | 100.00% | 50.00% |
| A601 | 5 | 4 | 4 | 1 | 50.00% | 80.00% |
| A201 | 4 | 4 | 3 | 0 | 57.14% | 100.00% |
| A103 | 2 | 2 | 3 | 0 | 40.00% | 100.00% |
| A001 | 0 | — | — | — | N/A (zero support) | N/A (zero support) |
| A003 | 0 | — | — | — | N/A (zero support) | N/A (zero support) |
| A102 | 0 | — | — | — | N/A (zero support) | N/A (zero support) |
| A501 | 0 | — | — | — | N/A (zero support) | N/A (zero support) |

A001, A003, A102, A501 have zero Gold examples in this final set. Their final-set coverage is reported as zero; no precision/recall conclusion is drawn for unsupported classes — this is a fact about the frozen dataset's composition, not a system failure.

## Dominant Error Patterns (see full detail in `v0_2_candidate3_final_error_audit.md`)

- **Valuation boundary (A304)** remains the single largest error source (11/26), consistent with the same pattern already observed on the development set.
- **Two wrong-Alpha substitutions are a direct, documented side effect of Candidate 3's own new A103-over-A101 tie-break rule**, introduced to fix the opposite confusion direction — reported honestly, not corrected.
- **The bare-sentiment-percentage → A601 false-positive pattern recurred** (`gold-final-116`), matching the one new regression already seen in the Day 4G development run — confirming this specific gap was not fully closed.

## Provider Telemetry

| Field | Value |
|---|---:|
| Provider calls | 150 |
| Successful | 150 |
| Retries | 0 |
| Timeouts | 0 |
| Unresolved failures | 0 |
| Elapsed seconds | 210.93 |
| Tokens | NOT_MEASURED |
| Cost | NOT_MEASURED |

## Integrity

Final Gold hash unchanged after run: **YES**. Candidate 3 hashes unchanged after run: **YES**. Used for tuning: **NO**. Candidate 3 modified after result: **NO**. Candidate 4 created: **NO**.

**FINAL_ALPHA_VALIDATION_COMPLETE = YES.**
