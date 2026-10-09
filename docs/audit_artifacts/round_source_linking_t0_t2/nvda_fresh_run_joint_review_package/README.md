# NVDA Fresh Run -- joint review package

`run_id`: `034a0a60-430e-41f8-8321-03a11389707a` | ticker: NVDA | analysis_date: 2026-10-02

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

No Alpha is reported as officially dominant and no main conflict is
reported. This is **not** because signal was weak -- six Alphas reached the
highest raw Activation band (`regime_level`) and a seventh reached
`dominant`. It is because a separate, later gate (Entity Exposure
qualification) found zero qualifying current-run evidence for every Alpha
and blended that down below the regime/dominant threshold. See
`01_conclusions_and_alpha_candidates.md` for the full table and explanation
-- this nuance matters for review and is not optional reading.

## Contents (the 7 parts)

1. **`01_conclusions_and_alpha_candidates.md`** -- key conclusions, the
   Activation-vs-Exposure-gate picture, main Alpha candidates by claim
   count, and both sides of all 8 evaluated conflict candidates.
2. **`02_claim_index_full.json`** -- the complete index of all 1040
   structured claims from this run, each with its real source-linkage
   status/reason, Alpha match (if any), and stance signals.
3. **`03_source_registry.json`** -- the 45 real registered sources (URL,
   publication time, retrieval time, source type), copied verbatim.
4. **`04_derived_metrics/`** -- real input data for every derived metric
   (Activation, Exposure, Conflict, structure graph), with their formula
   versions, copied verbatim from this run's own persisted artifacts.
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

1. Read `01_conclusions_and_alpha_candidates.md` first for the overall
   picture and the Activation-vs-Exposure nuance.
2. Open `06_review_form_blank.csv` in a spreadsheet tool; cross-reference
   `claim_id` against `02_claim_index_full.json` for full claim/evidence
   text and `03_source_registry.json` for any linked source's real URL and
   timestamps.
3. Consult `05_frozen_taxonomy_and_rules/` for the exact rules the model
   was instructed to apply, and `04_derived_metrics/` for the real
   computation inputs behind any Activation/Exposure/Conflict number in
   question.
4. Only after independent review is complete, compare against
   `07_model_predictions_and_existing_eligibility_SEPARATE.json` -- not
   before, and not as a substitute for forming an independent judgment.
