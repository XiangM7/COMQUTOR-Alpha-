# v0.2 Alpha Development Gold — v1 (FROZEN)

**Status: `DEVELOPMENT_GOLD_FROZEN`**

Adjudicator mode: `INDEPENDENT_EXTERNAL_LLM_ADJUDICATION`

System predictions seen during adjudication: **NO**

Sample count: **100**

SHA256 (`v0_2_alpha_dev_gold_v1.json`, as written to disk in this repository): `e8a78cbbb9359eb1361ca43891b52e71fa38528e0b6914c91aa5c9d874902ada`

This file must not be modified after this hash was computed. Any future change requires a new version (`v2`), never an edit in place.

## Provenance

| Provenance | Count |
|---|---:|
| Original development samples (first-pass accepted) | 85 |
| Round-1 reserve replacements (accepted) | 12 |
| Round-2 reserve replacements (accepted) | 3 |
| **Total** | **100** |

Full replacement chain (which excluded sample each replacement resolves) is preserved in `docs/audit_artifacts/v0_2_alpha_dev_replacement_log.json` — nothing was deleted from that audit history.

## Final Label Distribution (recomputed from the frozen file, not copied)

| Alpha ID | Count |
|---|---:|
| NONE | 80 |
| A301 | 9 |
| A601 | 4 |
| A304 | 4 |
| A101 | 1 |
| A103 | 1 |
| A201 | 1 |
| A001 | 0 |
| A003 | 0 |
| A102 | 0 |
| A501 | 0 |
| **Total** | **100** |

## Final Confidence Distribution (recomputed from the frozen file, not copied)

| Confidence | Count |
|---|---:|
| high | 72 |
| medium | 28 |
| low | 0 |
| **Total** | **100** |

## What This File Does Not Contain

No COMQUTOR Alpha prediction, mapper score, Provider result, Candidate 1/2 result, or system confidence appears anywhere in this file or its samples. Every `expected_label`/`confidence`/`adjudication_reason` was produced by an independent external LLM adjudication process that never saw system output, per `docs/audit_artifacts/v0_2_alpha_human_adjudication_rubric.md`.
