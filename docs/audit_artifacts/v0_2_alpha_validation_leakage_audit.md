# v0.2 Alpha Validation Leakage Audit

No new validation samples were selected in this task — this documents the exclusion methodology and current known-touched claim-ID set that any future new-holdout sampling must exclude. Full detail in `v0_2_alpha_validation_leakage_audit.json`.

## Known Touched Claim-ID Counts (by source)

| Source | Distinct claim_ids |
|---|---:|
| Holdout #1 | 100 |
| Holdout #2 | 141 |
| Holdout #3 | 152 |
| Holdout #4 | 200 |
| Holdout #5 | 200 |
| "old-50" | 45 |
| **Total (deduplicated union)** | **838** |

Pairwise overlap between all six sets confirmed zero by claim_id — consistent with each holdout's own documented construction discipline of excluding every prior set.

## Checks a Future New-Holdout Sample Must Apply

1. Duplicate `sample_id` within the new set itself
2. Exact `claim_id` duplicate against the 838-claim_id union above
3. Exact-text duplicate (claim + evidence string) against H1–H5 + old-50
4. Normalized-text duplicate (via the repository's existing `normalize_claim_for_dedupe` utility), per H2/H4's own established practice
5. Overlap with any literal example sentence used in the `alpha_classifier`/`alpha_classifier_batch` prompt text — confirmed by direct inspection that only the generic, non-holdout "A101 vs A103" illustrative phrasing is used, no holdout sentence is embedded
6. Overlap with any hardcoded test fixture claim/evidence string
7. Overlap with any sample referenced in the Candidate 1/2 design artifacts (`v0_2_day4_alpha_holdout_failure_analysis.json`, `v0_2_day4c_candidate1_regression_analysis.json`, `v0_2_alpha_prompt_candidate2.json`)

## Exclusions Made This Task

**None.** No new sample was proposed or selected — this audit exists to hand the exact exclusion set and checklist to whichever future task performs the actual sampling described in `v0_2_new_alpha_holdout_creation_plan.md`.
