# J3 Provisional Semantic Benchmark Integration + J2 v0.2 Evaluation Contract

**Branch:** `comqutor-structure-layer` **HEAD (before and after):** `b5837e80a4550fc35165d0013a8ef0f27ccb4c8f` (unchanged)
**Worktree:** preserved, no destructive git operations **Commit:** none **Push:** none **Subagents used:** 0

Machine-readable companion: [`j3_semantic_benchmark_j2_v0_2_report.json`](j3_semantic_benchmark_j2_v0_2_report.json).

## 1. What this segment did

Formally integrates the already-completed independent LLM blind review of the 50-row Evidence sample (J3)
into the test/regression system, and upgrades the J2 provisional labels to a five-category v0.2 evaluation
contract. Both remain **provisional and shadow-only** — neither enters production inference, neither
overrides a historical run, neither participates in real-time Alpha/Conflict calculation.

## 2. Files

**Added:**
- `comqutor_alpha/evaluation/j3_semantic_benchmark.py` — builds the J3 benchmark by joining the embedded, verbatim 50-row reviewer verdicts with the existing blind packet's identity/claim-text fields by `sample_id`.
- `comqutor_alpha/regression/semantic_benchmark.py` — the independent-J3-vs-B1-LLM-vs-deterministic three-way comparison, fail-closed against the task's own historical numbers.
- `comqutor_alpha/regression/labels_v2.py` — J2 v0.2 loader/validator (five mutually-exclusive conflict-pair categories per ticker).
- `comqutor_alpha/regression/evaluation_contract.py` — re-interprets an already-computed `evaluate_ticker` result through the v0.2 contract; never re-replays or re-derives anything.
- `comqutor_alpha/config/j2_provisional_regression_labels_v0.2.yaml` — the six-ticker v0.2 label file.
- `comqutor_alpha/config/j3_provisional_semantic_benchmark_v0.1.json` — the generated J3 benchmark (a deliverable, not source).
- `tests/test_j3_semantic_benchmark_j2_v0_2.py` — 61 tests covering all 43 required checks.
- This report (`.md` + `.json`).

**Extended additively (old behavior unchanged when new params/flags are omitted):**
- `comqutor_alpha/regression/report.py` — `build_regression_report()` gained optional `semantic_benchmark=`/`evaluation_contract=` params; omitting both reproduces the old report shape byte-for-byte.
- `scripts/run_regression.py` — gained opt-in `--labels-v2`/`--semantic-benchmark` flags and exit codes 5/6; the default (no new flags) CLI behavior, label version, and exit-code policy are unchanged.

**Never touched this segment:** `j2_provisional_regression_labels_v0.1.yaml`, `regression/labels.py`, `regression/run_selection.py`, `regression/evaluator.py`, B1's prompt/stance module (`week2_llm.py`), the 5-value stance vocabulary (`evidence_stance.py`), B2 admissibility / ConflictScore (`conflict_engine/*`), and the canonical taxonomy (`alpha_taxonomy_v1.yaml`).

## 3. J3 provisional semantic benchmark

Built from the task's own embedded, verbatim 50-row reviewer verdicts joined against the existing blind
packet by `sample_id` — never re-inferred, never re-sampled, never written back to the source packet.

| | |
|---|---|
| Row count | 50 |
| Authority | `independent_llm_provisional` |
| `human_review_performed` | `false` |
| `john_approved` | `false` |
| Stance distribution | `supports_alpha=26, opposes_alpha=16, mentions_alpha=5, supports_counter_alpha=2, neutral_background=1` |
| Confidence distribution | `high=38, medium=12` |

Both distributions reproduce the task's stated numbers exactly (verified by test, not assumed).

## 4. Three-way semantic comparison

| Metric | Value |
|---|---|
| Independent J3 vs. original B1 LLM | **39/50 = 78%** |
| Independent J3 vs. deterministic baseline | **22/50 = 44%** |
| Both agree | 18 |
| B1 LLM only | 21 |
| Deterministic only | 4 |
| Neither | 7 |
| Disagreement rows (11) | `evrs-006, 007, 008, 013, 020, 026, 034, 036, 040, 042, 045` |
| Strict reversal rows (7) | `evrs-002, 003, 019, 027, 039, 043, 047` — **independent J3 supports the original B1 LLM on all 7** |
| Support-pool false positives | 0 |
| Support-pool false negatives | 4 (`evrs-020, 026, 034, 040`) |

**Conclusion (unchanged from the task's own premise, now formally verified in code):** B1 LLM remains the
semantic authority; deterministic remains fallback-only. `compare_j3_benchmark()` raises
`J3SemanticComparisonMismatchError` and fails closed if any of these numbers cannot be reproduced from the
located source data — it never silently reports a different conclusion.

## 5. J2 v0.2 evaluation contract

v0.1 (`j2_provisional_regression_labels_v0.1.yaml`) is preserved byte-identical
(`sha256:3eec746e…cacbe9f1`) and remains the CLI default. v0.2 is additive, opt-in only via
`--labels-v2`, and replaces v0.1's flat "expected Alpha" list with five explicit categories per ticker:
`structural_expectations` (ticker-general, never per-run-strict), `run_bound_expectations` (only strict
once bound to one reference run's identity), `required_conflicts` (real fail on miss — **empty for all six
tickers**, since no ticker has a formally approved, artifact-complete, version-locked reference run yet),
`conditional_conflicts` (informational-only miss), and `product_decision_pending` (unresolved, never
pass/fail, never silently added to the taxonomy).

| Ticker | Conditional | Product decision pending | Removed (non-canonical) | Allowed |
|---|---|---|---|---|
| NVDA | A101__A304, A301__A304 | — | — | — |
| QQQ | A001__A501 | — | — | — |
| MSFT | — | **A102__A304** (Development Plan conflicts with canonical taxonomy) | — | — |
| SNDK | A301__A304 | — | A201__A304 | — |
| TSM | A301__A304 | — | A201__A304 | — |
| AMD | A101__A304 | — | A201__A304 | A301__A304 (real, canonical — permitted, not auto-required) |

The v0.2 loader rejects an undeclared pair in any executable category (`required`/`conditional`/`allowed`)
outright — stricter than v0.1's lenient allow-and-flag — and rejects mutual-exclusivity violations (the
same pair in two categories) and a canonical pair mis-labeled `remove_while_undeclared`.

## 6. A4 evaluator behavior under v0.2

`apply_v2_contract()` re-interprets an already-computed `evaluate_ticker()` result; it never re-replays,
never lowers a B2 threshold, never changes an Alpha score, never modifies a stance or the taxonomy, never
promotes a candidate conflict to admitted. A ticker is `evaluated` only when
`run_selection_status=="selected"` **and** `offline_reprocess_status=="completed"` **and**
`artifact_completeness=="pass"` — otherwise the whole ticker reports `not_evaluable`, never a false
"fail". `product_decision_pending`/`remove_while_undeclared` are label-level facts and are shown
regardless of evaluability (confirmed for MSFT/SNDK/TSM/AMD below, all of which are `not_evaluable`).

## 7. Real six-ticker shadow evaluation (offline, zero Provider calls)

```
python scripts/run_regression.py --tickers NVDA QQQ MSFT SNDK TSM AMD \
  --labels-v2 comqutor_alpha/config/j2_provisional_regression_labels_v0.2.yaml \
  --semantic-benchmark comqutor_alpha/config/j3_provisional_semantic_benchmark_v0.1.json \
  --report-path outputs/regression/regression_report_v0.2.json
```

| Ticker | Artifact completeness | Evaluation status | Main conflict match | stance_source |
|---|---|---|---|---|
| NVDA | pass | **evaluated / pass** | True | `deterministic_baseline` |
| QQQ | fail | not_evaluable | False | `deterministic_baseline` |
| MSFT | fail | not_evaluable (product decision still shown: A102__A304) | False | `deterministic_baseline` |
| SNDK | fail | not_evaluable (removed pair still shown: A201__A304) | False | `deterministic_baseline` |
| TSM | fail | not_evaluable (removed pair still shown: A201__A304) | False | `deterministic_baseline` |
| AMD | fail | not_evaluable (removed pair still shown: A201__A304) | False | `deterministic_baseline` |

`provider_calls=0`, `tradingagents_calls=0` for the whole run. Every ticker's `stance_source` is
`deterministic_baseline` — this proves only the offline deterministic-fallback replay path, **not**
current B1-LLM-authoritative end-to-end behavior (no live run was executed).

**NVDA, reported honestly:** its main conflict (`A301__A304`) matches the historical observation and both
of its v0.2 conditional pairs (`A101__A304`, `A301__A304`) are admitted — but its full structural Alpha
set does **not** completely match: `missing_expected=[A103, A201]`, `unexpected_alphas=[A001]`. Match on
the headline conflict is not claimed to mean a full label-set match.

Only NVDA has a complete source artifact; the other five are known-incomplete (matches A4's prior finding,
unchanged) and are correctly reported `not_evaluable` under v0.2 rather than hard-failed.

## 8. Source integrity — SHA-256 before/after

All identical; none written back to; none silently mutated.

| Artifact | SHA-256 |
|---|---|
| `j3_llm_blind_review_packet.json` | `53bfa2e6…cbcbe609b` |
| `j3_llm_comparison_reference.json` | `6c57805d…8792f891494` |
| `b1_llm_stance_50_validation_after_parser_fix.csv` | `9fb31287…83754abe2` |
| `j2_provisional_regression_labels_v0.1.yaml` | `3eec746e…cacbe9f1` |
| `alpha_taxonomy_v1.yaml` | `c031168c…eab1e7939c` |

All six saved run directories' `raw_agent_outputs.json` hash identical before and after replay (per-run
`source_raw_artifact_unchanged=True`, `evaluate_ticker`'s own before/after check, for all of
NVDA/QQQ/MSFT/SNDK/TSM/AMD). The historical `outputs/regression/regression_report.json` (v0.1, from the
A4 segment) was never overwritten — this segment's shadow run was written to the separate
`outputs/regression/regression_report_v0.2.json`.

## 9. Tests

`tests/test_j3_semantic_benchmark_j2_v0_2.py` — **61 passed**, covering all 43 required checks (several
split into precise sub-cases): Section A (J3 construction, 18 tests), Section B (semantic comparison, 10
tests), Section C (J2 v0.2 schema, 16 tests), Section D (A4 integration, 10 tests), Section E (invariants,
8 tests — including HEAD-unchanged and "no unstaged edit on top of B1/B2/ConflictScore/taxonomy" checks).

Related existing suites re-run and unaffected: `tests/test_a4_regression_runner.py` (41 passed, confirms
`report.py`'s extension stayed backward compatible) and `tests/test_j3_review_packet_export.py` (29
passed). Ruff clean on all 7 new/modified Python files.

**Full backend regression (required this segment — regression/evaluation runtime was modified):**

```
3546 passed, 3 failed, 47 skipped, 69 subtests passed in 675.76s
```

The 3 failures are the same pre-existing set as the prior A3 checkpoint baseline (3415 passed / 3 failed /
47 skipped), unrelated to this segment:
`structured_output_shadow/test_source_integrity.py::test_current_semantic_components_match_approved_phase1_master_baseline`
(frozen SHA-256 baseline predates B1's Evidence Stance changes) and
`test_w5_demo_seed.py::test_seed_is_complete_idempotent_and_reusable_without_provider` +
`::test_only_nvda_and_qqq_are_seeded` (predate B2's stricter admissibility gate). The full delta
(3546 − 3415 = 131) is accounted for exactly by this session's own new tests since that checkpoint: +41
(A4) +29 (J3-export) +61 (this segment). **Zero new failures introduced by this segment.**

Frontend was not modified this segment and was **not** rerun.

## 10. Non-goals honored

No new Provider LLM review · no new TradingAgents analysis · no J4 paid six-ticker live run · no
production stance correction · no historical run mutation · no taxonomy revision · no MSFT A102__A304
product approval · no B1 prompt tuning · no deterministic heuristic expansion · no B2 threshold tuning ·
no frontend feature · no repository cleanup · no commit · no push.

## 11. Completion declarations

`J3 PROVISIONAL SEMANTIC BENCHMARK INTEGRATION COMPLETE`
`J2 V0.2 EVALUATION CONTRACT COMPLETE`
`A4 V0.2 SHADOW EVALUATION COMPLETE`

`J3 HUMAN REVIEW NOT PERFORMED`
`J3 FORMAL JOHN APPROVAL NOT CLAIMED`
`J2 LABELS REMAIN PROVISIONAL`
`MSFT A102__A304 PRODUCT DECISION PENDING`
`PROVIDER CALLS = 0`
`TRADINGAGENTS CALLS = 0`
`COMMIT = none`
`PUSH = none`
