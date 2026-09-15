# QA Source-of-Truth Cleanup — v0.1.2.1

Orchestration/metadata cleanup only. No production code, Alpha Mapper, B1/B2/B4, conflict taxonomy, or regression label was modified. No rerun, no Provider call, no commit, no push. Branch `comqutor-structure-layer`, HEAD `9f228723fad5406c72e62beca67ec70ea0fdb004`. This step exposes inconsistencies; it does not resolve them.

## Current Selected Runs

| Ticker | Selected Run | Regression | Completeness | Final QA | Consistent? |
|---|---|---|---|---|---|
| NVDA | `5ffe121a-68fd-473b-82b5-c9465332d8a2` | ✓ | ✓ | — (absent) | VALID (live sources agree); **STALE** reference in `a4_regression_runner_report.json` (shows `e3eb3909-3744-4a02-9b32-b225cf6ef665`) |
| QQQ | `a364e0ee-3bb4-4032-88b7-5cd82e379805` | ✓ | ✓ | — (absent) | VALID (all three sources checked agree) |
| MSFT | `07ddc074-9ab2-4b16-8957-acbf94012144` | ✓ | ✓ | — (absent) | VALID (live sources agree); **STALE** reference in `a4_regression_runner_report.json` (shows `0cb43bae-1a4d-4003-bb29-55d420498842`) |
| SNDK | `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f` | ✓ | ✓ | — (absent) | VALID (all three sources checked agree) |
| TSM | `1a338ced-118e-44d2-b3f6-2444bfb9d7e6` | ✓ | ✓ | — (absent) | VALID (all three sources checked agree) |
| AMD | `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6` | ✓ | ✓ | — (absent) | VALID (all three sources checked agree) |

"Regression" = `outputs/regression/regression_report.json`. "Completeness" = `docs/audit_artifacts/item6_a2_artifact_completeness.json`. "Final QA" = no v0.1.2.1 Final QA Closure Report exists anywhere in the repository, for any ticker — this column is not a mismatch, it is an absent source.

**a4_regression_runner_report.json is treated as historical, not as a live competing source**: it is an implementation-completion report for the A4 tool itself (fields like `a4_implementation_complete`, `files_created`), not a regenerated QA result. Its own `six_ticker_coverage` snapshot disagrees with the two currently-regenerated artifacts (regression report + completeness) for NVDA and MSFT only — flagged explicitly in the consistency report rather than silently ignored or silently resolved.

## Current Authoritative Artifacts

| QA Area | Authoritative Current Artifact | Status |
|---|---|---|
| Regression report | `outputs/regression/regression_report.json` | CURRENT |
| Regression label authority | `docs/audit_artifacts/regression_label_authority_audit_v0.1.2.1.json` | CURRENT |
| Evidence-review acceptance | *(none)* | **PENDING_V2** — legacy `docs/audit_artifacts/evidence_review_summary.json` not selected |
| Artifact completeness | `docs/audit_artifacts/item6_a2_artifact_completeness.json` | CURRENT (54/54) |
| Neutral audit | `docs/audit_artifacts/neutral_unclassified_audit_msft_07ddc074.json` | CURRENT (MSFT only — no equivalent exists for the other five tickers) |
| Final QA report | *(none)* | **PENDING** |
| Ticker consistency | `docs/audit_artifacts/ticker_consistency_summary.json` | CURRENT |
| a4 regression runner report | `docs/audit_artifacts/a4_regression_runner_report.json` | STALE (see above) |

## Regression Authority

Per Step 1's audit (authoritative for this step; not reclassified here): the regression evaluator's live default label file is `j2_provisional_regression_labels_v0.1.yaml` (`label_version: j2.provisional.v0.1`), which is self-declared `provisional_ai_predicted`, `formal_product_owner_approval: pending`. **0 of 11** currently-referenced main-conflict expectations and **0 of 37** Alpha expectations across all six tickers qualify as `APPROVED_GOLD`. Current labels — both v0.1 and v0.2 — remain valid for **diagnostics only**: `may_use_for_production_pass_fail: false` is set explicitly in `qa_closure_index.json` and must not be silently flipped. A mismatch between a detected result and a non-gold expectation is represented as `NOT_GOLD_EVALUABLE`, never as a production `FAIL`.

## Evidence Review Source

`docs/audit_artifacts/evidence_review_summary.json` currently mixes three differently-scoped result sets in one file: a legacy 50-row top-level block (`reviewed_count=50`, `alpha_match_accuracy=0.72`, `polarity_accuracy=0.78`, both `target_met=false`, `human_review_performed=false`, `john_approved=false`), a `v0.1.2_qa_summary` block (200-row H5: Alpha 166/200=83.00%, Polarity 52/62=83.87%, both `status=pass`), and an `item2_200row_development_re_review` block (a separate 200-row/47-row development-re-review result: 77.00% / 82.98%). This file is **not deleted or rewritten** in this step. Because `evidence_review_summary_v2.json` does not yet exist, `qa_closure_index.json` records `evidence_review_summary_current.status = "PENDING_V2"` with `legacy_conflict_detected = true` — the mixed legacy file is explicitly *not* selected as the v0.1.2.1 acceptance source, so current QA orchestration stops silently reading whichever of its three layers happens to be looked at first.

## Contradictions Found

1. **Run-id staleness (NVDA)** — `a4_regression_runner_report.json` references `e3eb3909-3744-4a02-9b32-b225cf6ef665`; current regeneration uses `5ffe121a-68fd-473b-82b5-c9465332d8a2`.
2. **Run-id staleness (MSFT)** — `a4_regression_runner_report.json` references `0cb43bae-1a4d-4003-bb29-55d420498842`; current regeneration uses `07ddc074-9ab2-4b16-8957-acbf94012144`.
3. **Evidence-review metric layering** — three differently-scoped result sets (50-row legacy, 200-row H5, 200-row/47-row dev-review) coexist as top-level-and-nested content in one file with no single selected acceptance source.
4. **Regression metric vs. label authority** — `regression_report.json`'s `main_conflict_match` is computed against `j2.provisional.v0.1`'s `allowed_main_conflicts`, which still lists MSFT `A102__A304` even though PD-017 + direct taxonomy verification (Step 1 audit) classify it `REJECTED_OR_SUPERSEDED`.
5. **MSFT authority contradiction** — v0.1 (live default) still treats `A102__A304` as allowed; v0.2 and PD-017 both reject it.
6. **SNDK/TSM/AMD authority contradiction** — same pattern for `A201__A304`: allowed in v0.1 (live default), removed in v0.2, not canonical in the live taxonomy.

Full machine-readable detail: `docs/audit_artifacts/qa_source_consistency_report_v0.1.2.1.json`.

## Current QA Status

- **Source consistency**: 6/6 across the two currently-regenerated artifacts (regression report, completeness report). Final-QA source absent for all six tickers (not a mismatch — nothing exists to check against). 2/6 tickers (NVDA, MSFT) have a stale reference in a historical, non-regenerated report.
- **Artifact completeness**: 54/54 (all six tickers, 9/9 core artifacts each), read directly from `item6_a2_artifact_completeness.json`, not recomputed.
- **Semantic diagnostics**: available per ticker (`diagnostic_expected_alpha_hit_rate` in `qa_closure_index.json`), explicitly marked `use_for_release_acceptance: false`.
- **Gold-evaluable acceptance**: 0/6 tickers have any `APPROVED_GOLD` main-conflict or Alpha expectation. No ticker is release-acceptance evaluable today.
- **Pending acceptance work**: (1) human Product Owner approval of at least one frozen reference run + expectation per ticker; (2) creation of `evidence_review_summary_v2.json` as the clean v0.1.2.1 acceptance source; (3) creation of a v0.1.2.1 Final QA Closure Report.
