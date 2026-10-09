# NVDA Fresh Run -- joint review package (v2)

`run_id`: `034a0a60-430e-41f8-8321-03a11389707a` | ticker: NVDA | analysis_date: 2026-10-02

## What changed from v1 (the prior package is kept, unchanged, alongside this one)

v1 (`../nvda_fresh_run_joint_review_package/`) is preserved as-is for the record. **v2 corrects a real error in v1's own narrative, not a re-run or any change to the underlying research**: v1 described the oldest, most permissive diagnostic Activation score set (`v1`, `week3.activation.mvp_v1`) as if it were this run's headline/official result. This run's actual primary/official Activation layer (`v2_verified`) is **0.0 for every single Alpha**, for a specific, fully traced reason: zero of this run's 1040 claims have ever been through human review. See `08_source_coverage_root_cause_analysis.md` (new in v2) for the complete chain, and `09_concurrent_audit_fix_and_request_reconciliation.md` (new in v2) for a real, separately-discovered concurrency bug in this round's own audit-trail recorder, its fix, and a precise accounting of this run's actual Week2 request usage. Parts 2-7 below are otherwise unchanged from v1 (same real data; only the headline narrative in Part 1 is corrected).

## Important context before reviewing

This run's PostgreSQL state was originally written to the **production**
database by a launcher-script bug (not by this package or its contents).
It was backed up, the production rows were deleted after verification, and
the backup was restored into the isolated test database. This package is
built from the real, unaffected file-based run artifacts plus that
verified, restored data -- **never from the original production rows
directly, and never from a re-run of this research**. Full incident
details: `../incident_prod_db_writes_20261002/INCIDENT_REPORT_AND_CLEANUP_PLAN.md`
and `../incident_prod_db_writes_20261002/RESTORATION_VERIFICATION_MANIFEST.md`.

No part of this package's own Alpha/Conflict/Activation results was altered,
re-computed, or re-run to produce this package -- every number here is
exactly what the original research produced.

## What this run actually found (read this before the claim index)

No Alpha is officially dominant and no main conflict is reported. This is
**not** a weak-signal result papered over, and **not** a strong result
being understated -- it is an **unreviewed** one. Two diagnostic score sets
(`v1`, `v2`) found real structured signal without requiring human review;
the official, human-review-gated layer (`v2_verified`) correctly shows zero
everywhere because no claim in this run has been reviewed yet. Read
`01_conclusions_and_alpha_candidates.md` for the full three-way score table
and `08_source_coverage_root_cause_analysis.md` for the complete, code-traced
explanation of why -- this nuance matters for review and is not optional
reading.

## Contents (the 7 original parts, plus 2 new analysis documents)

1. **`01_conclusions_and_alpha_candidates.md`** -- key conclusions, the
   corrected v1/v2/v2_verified Activation picture, main Alpha candidates by
   claim count, and both sides of all 8 evaluated conflict candidates
   (verified directly against `conflicts.json`, not reconstructed from
   memory).
2. **`02_claim_index_full.json`** -- the complete index of all 1040
   structured claims from this run, each with its real source-linkage
   status/reason, Alpha match (if any), and stance signals.
3. **`03_source_registry.json`** -- the 45 real registered sources (URL,
   publication time, retrieval time, source type), copied verbatim.
4. **`04_derived_metrics/`** -- real input data for every derived metric
   (Activation -- all three score sets, Exposure, Conflict, structure
   graph), with their formula versions, copied verbatim from this run's own
   persisted artifacts.
5. **`05_frozen_taxonomy_and_rules/`** -- the frozen Alpha taxonomy
   (`alpha_taxonomy_v1.yaml`) and the exact Alpha-classifier prompt
   (`v7`) actually used for this run's real classification calls.
6. **`06_review_form_blank.csv`** -- one row per claim (1040 rows), blank,
   for independent review of source locatability, claim fidelity, Alpha
   judgment, stance judgment, and eligibility issues. **"CANNOT_JUDGE" is
   an explicitly valid answer in every judgment column** -- do not force a
   judgment where the real source material does not support one (expected
   to be common here, since 1016 of 1040 claims have no linked external
   source). `review_status` defaults to `PENDING_REVIEW` for every row;
   `reviewer_id` is blank and must be filled in by whoever actually
   reviews it.
7. **`07_model_predictions_and_existing_eligibility_SEPARATE.json`** -- the
   model's own predictions and this run's existing eligibility
   conclusions, kept in a **separate** file from the review form so an
   independent reviewer's judgment is never contaminated by or confused
   with what the model already concluded.
8. **`08_source_coverage_root_cause_analysis.md`** (new in v2) -- precise,
   code-traced source-coverage root-cause breakdown for all 1040 claims,
   and the complete raw-claim -> source-link -> content-support-review ->
   verified-eligibility -> Activation -> Exposure -> official-result chain
   explaining `current_evidence=0`.
9. **`09_concurrent_audit_fix_and_request_reconciliation.md`** (new in v2)
   -- a real concurrency bug discovered in this round's own semantic-call
   audit recorder (fixed, with targeted tests against the real Gateway/
   Session/Recorder path), and a precise reconciliation of this run's
   actual Week2 request usage against its 700-request budget, including
   which counts are certain and which are permanently unrecoverable.

Plus **`file_manifest.json`**: every file in this package with its size and
sha256 hash, for integrity checking.

## Labeling rules for any review recorded against this package

- A reviewer's judgment recorded anywhere against this package (in the CSV,
  or elsewhere) must be labeled with its real `reviewer_id`. An AI
  reviewer (e.g. ChatGPT) must be labeled `AI_REVIEW` / `reviewer_id=
  ChatGPT` (or similarly explicit) -- **never** `HUMAN_REVIEWED` and never
  presented as John's approval. No field in this package has been
  pre-filled to simulate a review having already happened.
- Agreement between a model prediction and a reviewer's judgment is not
  evidence of correctness by itself -- both are recorded as what they are
  (a model prediction, a reviewer's judgment), not conflated.

## Usage

1. Read `01_conclusions_and_alpha_candidates.md` first, then
   `08_source_coverage_root_cause_analysis.md` for the full why.
2. Open `06_review_form_blank.csv` in a spreadsheet tool; cross-reference
   `claim_id` against `02_claim_index_full.json` for full claim/evidence
   text and `03_source_registry.json` for any linked source's real URL and
   timestamps.
3. Consult `05_frozen_taxonomy_and_rules/` for the exact rules the model
   was instructed to apply, and `04_derived_metrics/` for the real
   computation inputs behind any Activation/Exposure/Conflict number in
   question -- note `04_derived_metrics/alpha_activations.json` itself
   contains all three score sets (`v1`, `v2`, `v2_verified`); only
   `v2_verified` is official.
4. Only after independent review is complete, compare against
   `07_model_predictions_and_existing_eligibility_SEPARATE.json` -- not
   before, and not as a substitute for forming an independent judgment.
