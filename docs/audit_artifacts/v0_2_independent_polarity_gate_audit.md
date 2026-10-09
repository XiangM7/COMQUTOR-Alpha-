# v0.2 Independent Polarity Gate — Provenance Audit

**This is an audit only. No polarity evaluation was rerun, no historical artifact was modified, no production code was changed.** The frozen Alpha result (124/150 = 82.67%, `FINAL_ALPHA_TARGET_MET = YES`) is unaffected and unchanged.

Frozen polarity target: **≥ 80.00%**. Independence is established from provenance, never inferred from score alone.

## Eligibility Criteria (all must hold)

A. Gold/reference polarity labels fixed independently of the system result.
B. Evaluated samples not used to tune/design/remediate the polarity classifier being validated.
C. Exact evaluated system/rule state frozen before the independent run.
D. Result not selectively rerun or denominator-adjusted after errors were observed.
E. Reported denominator/accuracy reproducible from preserved artifacts.
F. Accuracy ≥ 80.00%.

## Polarity Evidence Inventory

| Dataset | N | Correct | Accuracy | Status |
|---|---:|---:|---:|---|
| Holdout #1 (H1) | 100 | 79 | 79.00% | `HISTORICAL_NONINDEPENDENT_EVIDENCE` — fails F outright |
| **Holdout #2 (H2)** | **141** | **123** | **87.23%** | **`ELIGIBLE_INDEPENDENT_FINAL_EVIDENCE`** |
| H4 Reviewer-v2 Dev | 47 | 39 | 82.98% | `DEVELOPMENT_OR_TUNING_EVIDENCE` — self-labeled dev re-review |
| Holdout #5 (H5) | 61 | 52 | 85.25% | `HISTORICAL_NONINDEPENDENT_EVIDENCE` — primary diagnostic corpus |
| "old-50" set | 50 | — | N/A | `INSUFFICIENT_PROVENANCE` — review never completed (`review_status: pending` for all 50) |

## H2 Provenance — Detailed Determination

**Reported result, verified directly from source: 123/141 = 87.23%.**

A prior Day 4C audit (`v0_2_alpha_holdout_provenance.json`) marked H2 `eligible_as_final_independent: false` — but that determination was scoped to the **Alpha** dimension (H2's Alpha number genuinely is obsolete: pre-Pure-LLM-migration architecture). It did not separately re-derive polarity-specific eligibility. This task does that re-derivation from scratch, against the six criteria above:

- **A — Labels independent:** YES. H2 used a two-phase blind LLM review architecture (`phase4_stance_review`) that never showed the reviewer any system output.
- **B — Not used to tune/design/remediate:** YES, verified directly. `git diff c454245..HEAD -- comqutor_alpha/structure_engine/evidence_stance_llm.py` shows only concurrency/retry infrastructure changes; the `evidence_stance_classifier` **prompt text itself is byte-identical** between H2's freeze commit (`c454245`) and the current HEAD (programmatically diffed and confirmed). H5 — not H2 — is the documented source of the Day 3 fix, and that fix (a `POSITIVE_WORDS` lexicon addition feeding `infer_direction()`) does not even reach the stance classifier's prompt payload (verified: no `semantic_polarity`/`direction` field is read by `evidence_stance_llm.py`'s payload builder).
- **C — System frozen before run:** YES. H2's own report states B1 `prompt_version: evidence_stance.llm_classifier.v3` was "already manually approved for freeze prior to this task."
- **D — No post-hoc manipulation:** YES. All 141 rows retained; disclosed caveats (39 LLM-flagged near-duplicates, 14 Alpha-only stale rows) are transparency notes, not denominator edits — "141 source rows = 141 system-stance rows = 141 independent-stance-review rows," verified by the report's own set-equality assertion.
- **E — Reproducible:** YES. `item2_blind_holdout_141_v2.csv`'s SHA256 was recomputed and matches the manifest-recorded `5c11f7f6...` exactly; `polarity_correct_count: 123` / `sample_count: 141` read directly from `item2_blind_holdout2_summary.json`.
- **F — ≥ 80%:** YES, 87.23%.

**Conclusion: H2 is `ELIGIBLE_INDEPENDENT_FINAL_EVIDENCE` for polarity.** This is scoped to polarity only — H2's Alpha ineligibility stands, unaffected and unchanged.

## Gate Decision

| Field | Value |
|---|---|
| INDEPENDENT_POLARITY_VALIDATION_EXISTS | **YES** |
| POLARITY_TARGET_MET | **YES** |
| Qualifying artifact | `docs/audit_artifacts/item2_blind_holdout2_summary.json` |
| Qualifying numerator/denominator | 123 / 141 |
| Qualifying accuracy | **87.23%** |
| Rerun performed | NO |

## Day 5 Status

`FINAL_ALPHA_TARGET_MET` remains **YES** (unchanged, closed in Day 4I). `POLARITY_TARGET_MET` is now **YES** per this audit. `DAY_5_READY` is **not** automatically set by this finding — Day 5 readiness still requires a separate review of John's remaining formal/package/demo gates, not performed in this task.
