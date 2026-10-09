# v0.2 Evidence Error Statistics — Automated (Day 2)

All numbers below are computed directly from row-level data at read time by `docs/audit_artifacts/v0_2_evidence_error_statistics.json`'s build script — nothing here is a manually-maintained aggregate table. Primary row-level authority: `docs/audit_artifacts/evidence_review_summary_v2.json`'s `row_level_audit.detailed_rows` (200 rows, each carrying already-adjudicated `alpha_match` / `polarity_eligible` / `polarity_match` / `critical_reversal` fields). Cross-checked against `docs/audit_artifacts/item2_blind_holdout5_comparison.csv` (200 rows, same underlying samples).

## Alpha Match

| Numerator (correct) | Denominator (scored) | Failures | Excluded | Exclusion reason | Accuracy |
|---:|---:|---:|---:|---|---:|
| 166 | 200 | 34 | 0 | none — every row is alpha-scored | **83.00%** |

## Polarity

| Numerator (correct) | Denominator (scored) | Failures | Excluded | Exclusion reason | Accuracy |
|---:|---:|---:|---:|---|---:|
| 52 | 61 | 9 | 139 | 138 rows carry no polarity claim at all (`polarity_eligible=False`); 1 row (`holdout5-005`, AMD) is explicitly excluded via the pre-existing `directional_eligibility_contract` — `adjudication_outcome=BOTH_REASONABLE_AMBIGUOUS` → `eligibility_class=AMBIGUOUS_DIRECTION`. This is the frozen source authority's own pre-existing rule, not a new exclusion decision made today. | **85.25%** |

## Error Accounting

| Metric | Value |
|---|---:|
| Alpha error records | 34 |
| Polarity error records | 9 |
| Total error records | 43 |
| Overlapping samples (same sample_id in both failure sets) | 5 — `holdout5-003`, `holdout5-016`, `holdout5-017`, `holdout5-057`, `holdout5-154` |
| Distinct erroneous samples | 38 |

## Critical Reversal

| Metric | Value |
|---|---:|
| Accepted-gate critical reversal count (within the 61 polarity-eligible rows) | **0** |
| Raw pre-exclusion critical reversal count (all 200 rows) | **1** — `holdout5-005` (AMD), excluded from the accepted gate by the same `directional_eligibility_contract` above |

## Verification Against the Task's Expected Values

Every one of the following was independently re-derived from row-level data and matched exactly — **no discrepancy against the task's stated expected values**:

- Alpha Match: 166/200, 34 failures, 83.00% — ✓
- Polarity: 52/61, 9 failures, 85.25% — ✓
- Error accounting: 34 + 9 = 43 total, 5 overlap, 38 distinct — ✓
- Critical reversal: 0 accepted / 1 raw — ✓

## Discrepancy Found and Reported (Section 6 Requirement)

One real discrepancy **was** found while deriving these numbers, and is reported here rather than silently reconciled:

Deriving the Polarity statistic **naively** from `item2_blind_holdout5_comparison.csv`'s own `polarity_correct` column (any non-blank value counted as scored) yields **62 scored / 10 failures**, not 61/9 — one row too many. The extra row is `holdout5-005` (AMD): it does carry a `polarity_correct=False` value in the flat comparison CSV, but that CSV has no explicit eligibility field, so a naive read does not know to apply the `directional_eligibility_contract`'s `AMBIGUOUS_DIRECTION` exclusion. The authoritative 61/9 figures come from `evidence_review_summary_v2.json`'s `row_level_audit.detailed_rows`, where each row already carries an adjudicated `polarity_eligible` boolean that correctly marks `holdout5-005` as ineligible. Both derivations are recorded side-by-side in the JSON companion's `discrepancy_report` field; the naive one was not used for any reported total.

Alpha Match numbers agree exactly between both source files (166/34 in both) — no discrepancy there.

## Row-Level Records

The 34 Alpha Match and 9 Polarity failure records themselves — `sample_id`, `error framework` (Alpha Match vs Polarity), `actual output`, `expected output`, `error category`, `root cause`, `severity`, `high_confidence_wrong` — are unchanged from `docs/audit_artifacts/v0_2_evidence_failure_analysis.md`'s existing Row-Level Tables (34 rows + 9 rows). Per Section 8's instruction, no prior adjudication was rewritten to simplify these statistics; this document only automates the aggregate accounting, reusing the same row-level fields already present in that file plus the row-level authority CSVs/JSON above. Every error record's `high_confidence_wrong` status is preserved verbatim from `review_alpha_confidence`/`review_decision` fields already in `evidence_review_summary_v2.json`.
