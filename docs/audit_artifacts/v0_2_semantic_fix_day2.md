# v0.2 Semantic Fix — Day 2

Authority: `docs/audit_artifacts/v0_2_john_frozen_gold_baseline.yaml`. No Gold rule, taxonomy, or frozen conflict pair was changed. **No production code was changed in this task** — see Headline Finding below for why, and Section 15 verification for the local test run performed against the *unchanged* code.

## Headline Finding

For all three of John's priority categories, **the current on-disk production code/config does not reproduce the historical system outputs** recorded in the row-level failure analysis:

- **Category B (verified directly, all 9 cases):** every one of the 9 Polarity-failure claims was re-run through `comqutor_alpha.structure_engine.evidence_stance.classify_evidence_stance()` today, with its exact original text and target Alpha, against the current on-disk `alpha_taxonomy_v1.yaml`. All 9 return `neutral_background` — **none reproduces the historically-recorded system output** (`mentions_alpha` ×4 or `opposes_alpha` ×5). The deterministic classifier does not even land in the same output family as what was reviewed.
- **Category A/C (corroborated, not independently re-run through the full Alpha Mapper):** `docs/audit_artifacts/v0_2_evidence_failure_analysis.json`'s own pre-existing `field_availability_note` (written by a prior task, for `holdout5-001`) already recorded that `outputs/runs/<holdout_run_id>/alpha_matches.json` does **not** reproduce the historical `system_matched_alpha_id` for these samples — it shows deterministic-only no-match / all-zero candidate scores. A direct keyword-overlap check performed today against the *current* `alpha_taxonomy_v1.yaml` keyword lists for two representative Category A/C samples (`holdout5-001`, `holdout5-057`) found zero or near-zero keyword hits for either the system's or the reviewer's Alpha — consistent with the same conclusion: the current keyword/candidate-scoring config does not reproduce the historical decision either.

**Conclusion:** the 200-row holdout5 dataset's system outputs (both Alpha Match and Polarity) were produced by a pipeline snapshot — code, taxonomy, or LLM-path state — that no longer matches what is on disk today. This is not a new defect discovered today; it means **no sample's failure can be causally reproduced against current code**, so no production change can be verifiably "directly justified by the accepted row-level failure analysis" — the task's own explicit gate for permitted changes. Applying a code change anyway, without being able to confirm it addresses what actually happened, would be an unverified, undocumented behavior change to sensitive semantic-classification code, and would risk exactly the outcome the task explicitly forbids: disguising an unresolved case as fixed.

**All 21 cases across categories A/B/C are therefore marked `UNRESOLVED`, each with this precise, per-sample-verified reason** — not a blanket excuse, and not silence: Category B's reason cites the exact re-run output and reason codes per sample; Category A/C's reason cites the pre-existing non-reproduction note plus today's keyword check.

## Repair Matrix

### Category A — Growth/cycle vs risk-structure confusion (8 cases)

| Sample | System → Expected | Root Cause | Responsible Path | Status |
|---|---|---|---|---|
| holdout5-004 | A201 → A304 | SEMANTIC_CLASSIFICATION | `alpha_mapper.py` + taxonomy keywords | UNRESOLVED |
| holdout5-056 | A301 → A501 | SEMANTIC_CLASSIFICATION | `alpha_mapper.py` + taxonomy keywords | UNRESOLVED |
| holdout5-071 | A304 → A103 | TAXONOMY_BOUNDARY | `alpha_mapper.py` + taxonomy keywords | UNRESOLVED |
| holdout5-146 | A304 → A101 | INPUT_AMBIGUITY | `alpha_mapper.py` + taxonomy keywords | UNRESOLVED |
| holdout5-151 | A201 → A304 | SEMANTIC_CLASSIFICATION | `alpha_mapper.py` + taxonomy keywords | UNRESOLVED |
| holdout5-154 | A301 → A304 | INPUT_AMBIGUITY | `alpha_mapper.py` + taxonomy keywords | UNRESOLVED |
| holdout5-158 | A601 → A304 | SEMANTIC_CLASSIFICATION | `alpha_mapper.py` + taxonomy keywords | UNRESOLVED |
| holdout5-174 | A201 → A304 | SEMANTIC_CLASSIFICATION | `alpha_mapper.py` + taxonomy keywords | UNRESOLVED |

### Category C — A101/A102/A103 boundary confusion (4 cases)

| Sample | System → Expected | Root Cause | Responsible Path | Status |
|---|---|---|---|---|
| holdout5-001 | A101 → A103 | TAXONOMY_BOUNDARY | `alpha_mapper.py` + taxonomy keywords | UNRESOLVED |
| holdout5-003 | A101 → A103 | TAXONOMY_BOUNDARY | `alpha_mapper.py` + taxonomy keywords | UNRESOLVED |
| holdout5-057 | A102 → A101 | TAXONOMY_BOUNDARY | `alpha_mapper.py` + taxonomy keywords | UNRESOLVED |
| holdout5-164 | A102 → A101 | TAXONOMY_BOUNDARY | `alpha_mapper.py` + taxonomy keywords | UNRESOLVED |

### Category B — Cautious/questioning/skeptical wording (9 cases)

| Sample | System → Expected | Current re-run result (verified today) | Status |
|---|---|---|---|
| holdout5-003 | mentions_alpha → supports_alpha | `neutral_background` (CONTEXT_ONLY) | UNRESOLVED |
| holdout5-016 | mentions_alpha → supports_alpha | `neutral_background` (NON_SUBSTANTIVE) | UNRESOLVED |
| holdout5-017 | opposes_alpha → mentions_alpha | `neutral_background` (GENERIC_BACKGROUND) | UNRESOLVED |
| holdout5-040 | opposes_alpha → mentions_alpha | `neutral_background` (NON_SUBSTANTIVE) | UNRESOLVED |
| holdout5-057 | mentions_alpha → supports_alpha | `neutral_background` (NON_SUBSTANTIVE) | UNRESOLVED |
| holdout5-070 | mentions_alpha → supports_alpha | `neutral_background` (CONTEXT_ONLY) | UNRESOLVED |
| holdout5-154 | opposes_alpha → mentions_alpha | `neutral_background` (GENERIC_BACKGROUND) | UNRESOLVED |
| holdout5-196 | opposes_alpha → mentions_alpha | `neutral_background` (CONTEXT_ONLY) | UNRESOLVED |
| holdout5-198 | opposes_alpha → mentions_alpha | `neutral_background` (NON_SUBSTANTIVE) | UNRESOLVED |

Full per-row detail (`original_input`, `pre_fix_output`, `expected_output`, `root_cause`, `responsible_code_path`, `minimal_proposed_fix`, `change_reason`, and for Category B the exact `verification` block) is in the companion `v0_2_semantic_fix_day2.json`.

## Day 2 Local Verification (Section 15 — development verification only, not formal validation)

To confirm the current, *unchanged* deterministic stance/semantics code is internally healthy (a due-diligence check, not a fix-verification step, since no fix was applied):

```
pytest tests/test_evidence_stance_classifier.py tests/test_week2_semantics.py -q
56 passed in 0.56s
```

No Provider calls, no market-data retrieval, no TradingAgents research, frozen/static fixtures only. This is **development verification only** — not a `FRESH_RUN`, not formal validation, and not evidence that any of the 21 cases above is fixed (they are not; no code changed).

## Why No Fix Was Applied

Section 10 of the Day 2 task permits modifying semantic-classification code or prompts **"ONLY where directly justified by the accepted row-level failure analysis"**, and Section 14 requires marking a case `UNRESOLVED` with an exact reason rather than disguising it as fixed. Having verified that the current code does not reproduce any of the 21 sampled failures, no change could meet the "directly justified" bar for any specific sample — so, per the task's own instructions, none was made. This is reported as the Day 2 finding for Objective C, not as an incomplete task.
