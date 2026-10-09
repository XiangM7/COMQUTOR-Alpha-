# v0.2 Alpha FINAL Gold — v1 (FROZEN)

**Status: `FINAL_GOLD_FROZEN`**

Adjudicator mode: `INDEPENDENT_EXTERNAL_LLM_ADJUDICATION`

System predictions seen during Gold adjudication: **NO**

Candidate 3 outputs seen during Gold adjudication: **NO**

Used for tuning: **NO**

Sample count: **150**

SHA256 (`v0_2_alpha_final_gold_v1.json`, as written to disk): `a3c402ce391cfba1bd49d3d84a352e222e2775118f24b9ebf2a003183e2392de`

This file must not be modified after this hash was computed. Any future correction requires a new version (`v2`), never an edit in place.

## Provenance

| Provenance | Count |
|---|---:|
| Original final-independent-set samples (first-pass accepted) | 130 |
| Round-1 reserve replacements (accepted) | 16 |
| Round-2 reserve replacements (accepted) | 2 |
| Round-3 reserve replacements (accepted) | 2 |
| **Total** | **150** |

Full replacement chain (every excluded sample and which reserve draw resolves it, across all 3 rounds) is preserved in `docs/audit_artifacts/v0_2_alpha_final_replacement_log.json` — nothing was deleted from that audit history.

## Reserve Consumption Summary

| Stage | Reserve Samples Consumed |
|---|---:|
| Development chain (rounds 1–2) | 18 |
| Final round 1 | 20 |
| Final round 2 | 4 |
| Final round 3 | 2 |
| **Total consumed** | **44** |
| **Untouched reserve remaining** | **6** |

## Final Label Distribution (recomputed from the frozen file, not copied)

| Alpha ID | Count |
|---|---:|
| NONE | 116 |
| A301 | 9 |
| A304 | 8 |
| A101 | 6 |
| A601 | 5 |
| A201 | 4 |
| A103 | 2 |
| A001 | 0 |
| A003 | 0 |
| A102 | 0 |
| A501 | 0 |
| **Total** | **150** |

## Final Confidence Distribution (recomputed from the frozen file, not copied)

| Confidence | Count |
|---|---:|
| high | 120 |
| medium | 30 |
| low | 0 |
| **Total** | **150** |

## Candidate 3 State at Freeze Time

| Prompt | SHA256 |
|---|---|
| Classifier (`week2.alpha_classifier.v6`) | `d53b2d7511f4c4a8089db746d09e4c79cb38f22597dac6459920ca3deac1171d` |
| Batch (`week2.alpha_classifier_batch.v4`) | `a03c8f673ffd387a866bc8dd585c4c96cf5464b80a50cb6e4c3fc5f894f68379` |

Candidate 3 final evaluations against this Gold: **0**. Provider final evaluations: **0**. This Gold has not yet been used to score any candidate.

## What This File Does Not Contain

No COMQUTOR Alpha prediction, mapper score, Provider result, or any Candidate 1/2/3 result appears anywhere in this file or its samples. Every `expected_label`/`confidence`/`adjudication_reason` was produced by an independent external LLM adjudication process that never saw system output, per `docs/audit_artifacts/v0_2_alpha_human_adjudication_rubric.md` and `docs/audit_artifacts/v0_2_final_alpha_adjudication_policy.md`.
