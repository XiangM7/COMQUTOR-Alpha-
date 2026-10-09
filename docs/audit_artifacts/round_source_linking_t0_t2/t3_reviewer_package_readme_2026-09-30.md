# Alpha-classification blind-review deliverable package (2026-09-30, fourth follow-up round)

This package is ready to hand to John or a designated reviewer. It has not been sent to anyone, and no field in it has been filled in, signed, or judged on anyone's behalf.

**Scope**: this package covers **Alpha classification only** — which single Alpha ID (or NONE) best matches each claim's own stated mechanism. It does not cover, and no field here should be read as covering, source-support verification, claim-fidelity, Evidence-Stance/Polarity, or downstream Activation/Conflict eligibility. See `t3_diagnostic_evaluation_driver.py`'s own `STEPS_COVERED` for the same disclosure in code form.

## What's in this package

1. **`t3_human_review_worksheet_2026-09-30.csv`** — the file to actually open and fill in (any spreadsheet tool). One row per sample: `claim_text`, `alpha_judgment_feasibility`, `source_material_completeness_status`, and three blank columns (`your_judgment`, `your_rationale`, `reviewer_id`). No hidden system answer is anywhere in this file.
2. **`t3_human_review_form_2026-09-30.json`** — the underlying JSON the worksheet was generated from and that the filled worksheet gets merged back into. `hidden_system_answers` lives here as a separate top-level object, never inside `review_items` — don't open it until every row above has a judgment.
3. **`t3_sample_material_completeness_2026-09-30.json`** — the backing audit for both `source_material_completeness_status` and `alpha_judgment_feasibility`: confirms all 40 claim texts are located verbatim in their own run's real agent-output files, states plainly that none of the six underlying runs have a structured `source_registry.json` (all predate that chain), and flags the one sample (`prod-run-014`) whose opening pronoun lacks a clear antecedent.
4. **`t3_targeted_diagnostic_sample_2026-09-30.json`** — the full sample records (including `source_location`, `run_id`, `analysis_date`) for anyone who wants to trace a specific item back to its original run on disk.

## How to fill in and return the worksheet

1. Open `t3_human_review_worksheet_2026-09-30.csv`. For each row, read `claim_text` and decide which single Alpha ID (A001, A003, A101, A102, A103, A201, A301, A304, A501, A601 — the full real taxonomy, not only the 7 names that happen to appear in this sample pool's own stratification-quota keys) best matches its own stated mechanism, or `NONE` if none does. **CORRECTION (2026-10-05)**: this instruction, the review form's own `instructions_for_reviewer`, and the import script's validation previously listed only 7 of these 10 IDs — copied from `requested_quota`'s sampling-stratification keys (which control which claims were selected, never which answers are legal) rather than from the real classifier's own candidate set (`comqutor_alpha.structure_engine.alpha_mapper`: `allowed_ids = set(taxonomy)`). Fixed in the import script; no review judgment or prediction data was changed by this correction.
2. If the material genuinely isn't enough to decide — check `alpha_judgment_feasibility` and `source_material_completeness_status` first — write the literal value `UNABLE_TO_JUDGE` in `your_judgment` rather than guessing. This is an accepted, explicit answer, not a failure to complete the row.
3. Fill in `your_rationale` (one line) and `reviewer_id`. Leave a row entirely blank if not yet reviewed — a partially-filled worksheet can be imported and re-imported as more rows are completed.
4. **Import it back into the real evaluation script**, which merges filled rows into `t3_human_review_form_2026-09-30.json` (blank rows are left untouched, invalid values are rejected and reported, never silently accepted):
   ```bash
   cd /Users/xiangmao/COMQUTOR-Alpha-
   .venv/bin/python3 docs/audit_artifacts/round_source_linking_t0_t2/t3_diagnostic_evaluation_driver.py import-worksheet \
     --review-form-file docs/audit_artifacts/round_source_linking_t0_t2/t3_human_review_form_2026-09-30.json \
     --worksheet-file docs/audit_artifacts/round_source_linking_t0_t2/t3_human_review_worksheet_2026-09-30.csv
   ```
5. Once imported, `t3_diagnostic_evaluation_driver.py live ... --score` will read the real judgments from `t3_human_review_form_2026-09-30.json` — see the main round report for that exact command and its budget parameters.

`quota_category` is a sampling stratification label chosen by this round's own search process, not a confirmed-correct answer — it exists so the pool covers specific diagnostic boundaries (A304 vs. its neighbors, A101 vs. A103, etc.), not to hint at the intended judgment.

## What NOT to assume from this package

- `development_exposure_status` (in the JSON form; not a worksheet column) marked `ALREADY_USED_FOR_FROZEN_FINAL_VALIDATION_SCORE` means exactly that — 25 of the 40 items were already scored into the historical 82.67% result and are not unseen data for that purpose.
- `NOT_PREVIOUSLY_USED` (13 of the 15 newer `prod-run-*` items) means only what it says: an exact `claim_id` search across every file in `docs/audit_artifacts/` found no prior appearance. It is not a formal, audited holdout-set guarantee.
- `PARTIALLY_EXPOSED` (2 of the 40 items) means the exact `claim_id` already appears in a formal-acceptance trigger-matrix artifact, not a labeled Gold/dev/error-analysis set — it has not previously been used as a human-judged training example, but it is not brand-new either.
- `source_material_completeness_status` of `RAW_AGENT_REPORT_TEXT_ONLY` means the claim is verifiably present in a TradingAgents analyst's own generated report — it does **not** mean the analyst's underlying real-world source (a news article, filing, etc.) has been independently verified. Do not ask the reviewer to guess at that external fact from the report text alone — that is exactly what `UNABLE_TO_JUDGE` exists for if it blocks a genuine Alpha-classification decision.

## What this round did not do

No sample was rewritten to pad the count, and no new samples were added — the 40-item pool is frozen. No report title was substituted for real supporting content. No generated text was presented as "source-verified" beyond what `t3_sample_material_completeness_2026-09-30.json` actually shows. No reviewer name, verdict, or rationale was entered anywhere in this package by anyone other than the eventual human reviewer, and the package has not been sent to John or anyone else.
