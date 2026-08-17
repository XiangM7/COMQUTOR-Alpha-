# A4 Regression Runner + J2 Provisional Labels — Final Report

**Task:** `A4_REGRESSION_RUNNER` + `J2_PROVISIONAL_LABELS`
**Branch:** `comqutor-structure-layer`
**HEAD:** `b5837e80a4550fc35165d0013a8ef0f27ccb4c8f` (unchanged throughout — no commit, no push)
**Commit:** none. **Push:** none. **Provider calls:** 0. **TradingAgents calls:** 0.

## Status

**A4 IMPLEMENTATION COMPLETE.**
**J2 PROVISIONAL LABEL SET COMPLETE.**
**J2 SHADOW EVALUATION COMPLETE.**
**J2 FORMAL PRODUCT OWNER APPROVAL PENDING.**

All six requested tickers had a qualified, replay-eligible saved run, so **`SIX_TICKER_LIVE_COVERAGE_PARTIAL` does NOT apply** — coverage is complete (`six_ticker_live_coverage: "complete"` in the report).

## 1. What this is

A repeatable, offline, auditable regression flow with zero Provider/TradingAgents calls:

```
saved TradingAgents outputs (outputs/runs/<run_id>/raw_agent_outputs.json)
  -> the existing Architecture Replay offline-reprocess path
     (comqutor_alpha.replay.pipeline.run_structure_replay)
  -> the current, unmodified COMQUTOR architecture
     (Alpha Mapper -> Activation v2 -> B3 Exposure -> B4 classification -> B2 Conflict Admissibility)
  -> actual Alpha/Graph/Conflict results
  -> compared against J2's provisional expectations
  -> outputs/regression/regression_report.json
```

## 2. Files created (all new; no existing production file was modified)

- `comqutor_alpha/regression/__init__.py`, `labels.py`, `run_selection.py`, `evaluator.py`, `report.py`
- `comqutor_alpha/config/j2_provisional_regression_labels_v0.1.yaml`
- `scripts/run_regression.py`
- `tests/test_a4_regression_runner.py`
- `docs/audit_artifacts/a4_regression_runner_report.md` / `.json`

**Not touched:** `comqutor_alpha/replay/pipeline.py` (only imported/called), any B1–B5/A3 module, the Alpha taxonomy, the Conflict taxonomy, the Alpha Mapper threshold, Activation Score, ConflictScore, `evaluation/golden_case.py`'s separate J3-scoped human-label harness (a different, pre-existing system this task explicitly must not touch or parallel-build).

## 3. Existing mechanisms found and reused (task section 3's audit)

1. **No pre-existing A4 runner, `regression_report`, `expected_alphas`, or `missing_expected` concept existed anywhere** (`rg` returned zero matches) — this is a genuinely new task, not an extension of something already there.
2. **`comqutor_alpha.replay.pipeline.run_structure_replay`** ("Raw Rebuild Diagnostic Replay", Track D) is the one existing path that reprocesses a saved run's `raw_agent_outputs.json` through the current, unmodified pipeline (`adapt_run_outputs -> build_alpha_matches_payload -> build_extracted_structures_payload -> build_structure_graph_stage/score_and_assemble_structure_graph -> detect_alpha_conflicts`) with **zero Provider calls by construction** (`llm_gateway=None` throughout; its own `ReplayResult` already tracks `llm_provider_calls`/`tradingagents_calls`/`market_data_provider_calls`/`database_writes`, all always `0`). It never mutates the source run's directory (writes to a brand-new `outputs/replays/<replay_id>/`-style directory) and independently re-verifies the source raw artifact's sha256/size/mtime are unchanged before claiming success. When `persist=True` (the default), it already calls the exact same `finalize_completed_run_artifacts`/`write_run_audit_artifact`/`build_and_write_artifact_manifest` a live run uses — so a single replay call produces a complete, A2-conformant artifact bundle (including, additively, A3's own `unclassified_findings.json`, not used by A4 but confirmed present).
3. **`comqutor_alpha.audit.ticker_consistency.audit_ticker_consistency`/`resolve_expected_ticker`** (A1) — reused verbatim for each replayed ticker's consistency check.
4. **A2's `REQUIRED_ARTIFACT_FILENAMES`** (9-artifact contract) — reused, read-only, for the informational `artifact_completeness` field on run selection; never re-derived or widened.
5. **B4's already-computed, already-split top-level collections** (`active_alphas`/`dominant_alphas`/`regime_level_alphas`/`candidate_alphas`/`blocked_alphas` on `structure_graph.json`) — reused directly for `detected_alphas`; a pure dominant-only view is recovered by set difference against `regime_level_alphas` (since the legacy `dominant_alphas` field is intentionally blended dominant∪regime_level "for backward compatibility, never redefine an A2-frozen field") — never a re-classification.
6. **B2's already-computed `conflicts`/`main_conflict`/`arbitration.candidate_evaluations[*].admissibility`** (via `conflicts.json`, the same A2 canonical export a live run produces) — reused directly for conflict comparison; `conflict_schema.conflict_id`/`canonical_pair_key` (already producing the exact `"A101__A304"` format J2's own labels use) reused for pair identity, never a second pairing scheme.
7. **B1's already-attached `evidence_stance`/`stance_method`/`counter_alpha_id`** on `alpha_matches.json`'s `candidate_scores[]` — reused read-only for the contract-integrity checks; `evidence_stance.VALID_EVIDENCE_STANCES`/`SUPPORTS_ALPHA`/`SUPPORTS_COUNTER_ALPHA` reused verbatim, never a new vocabulary.
8. **Run history/completeness**: `GraphPersistenceRepository.get_research_run_record`/`list_research_run_records` (DB) exist but, on this machine's actual database, only `NVDA`'s `e3eb3909...` run (finalized live during the prior A3 segment) has a row — every other saved run predates any DB registration for this local SQLite file. A4's run selection is therefore primarily **file-system-based** (see §5), with the database checked and reported **separately** (`database_record_status`), never assumed to agree with file state.
9. **`comqutor_alpha.config.entity_alpha_exposure_seed_v0.1.yaml`** (B3's own already-approved seed) — read directly for the dominance-guard's `exposure_state` cross-check field; no parallel copy of these numbers was created anywhere (they were, in fact, already the exact numbers the task supplied in section 6 — confirmed byte-for-byte identical).

## 4. J2 label schema and status

`comqutor_alpha/config/j2_provisional_regression_labels_v0.1.yaml`:

```yaml
schema_version: regression_labels.v1
label_version: j2.provisional.v0.1
status: provisional_ai_predicted
evaluation_mode: shadow
evaluation_authority: provisional
approved_by: null
approved_at: null
formal_product_owner_approval: pending
```

Loaded and structurally validated by `comqutor_alpha/regression/labels.py` (`load_j2_labels`). Never read by the Alpha Mapper, Activation, Exposure, or Conflict Detector — read only by the A4 evaluator. `evaluation_mode`/`formal_product_owner_approval`/`approved_by` are read verbatim from the file; **no environment variable is read anywhere in the loader** (tested explicitly — setting `J2_FORCE_AUTHORITATIVE`/`COMQUTOR_LABEL_AUTHORITY`/`REGRESSION_AUTHORITATIVE` has zero effect). A claim of `evaluation_mode: authoritative` without `formal_product_owner_approval: approved` + real `approved_by`/`approved_at` values is a hard load-time validation error (`LABEL_AUTHORITATIVE_CLAIM_MISSING_APPROVAL_PROVENANCE`) — the only way to promote this file is a human edit, never a code or env-var path.

### PREDICTED_CONFLICT_PAIR_NOT_DECLARED

Verified against the real, current canonical conflict taxonomy (6 pairs: `A001__A501`, `A003__A501`, `A101__A304`, `A301__A304`, `A304__A601`, `A501__A601`). Four of J2's per-ticker `allowed_main_conflicts` entries are **not** declared in the taxonomy:

| Ticker | Undeclared pair |
|---|---|
| MSFT | `A102__A304` |
| SNDK | `A201__A304` |
| TSM | `A201__A304` |
| AMD | `A201__A304` |

Per task section 5: the taxonomy was **not** modified to accommodate these, and the predictions were **not** silently dropped — they remain verbatim in the label file and are reported both by the loader (`labels["undeclared_conflict_pairs"]`) and by the CLI (a `NOTE:` line per ticker) and in `regression_report.json`'s top-level `undeclared_conflict_pairs`. Their real taxonomy consequence (they can never be admitted or even reach candidate status, since the taxonomy itself doesn't recognize them as a conflict pair) is reported honestly in each affected ticker's `expected_pair_status` (`"not_reached"`), never faked as `"admitted"`.

## 5. Saved-run selection rule

`comqutor_alpha/regression/run_selection.py::select_run_for_ticker`. Never creates a new run, never calls a Provider. Pure file-system scan of `outputs/runs/*/metadata.json` for a matching ticker (case-insensitive), then:

1. **Replay-eligible** (hard requirement — `metadata.json` + `raw_agent_outputs.json` present) candidates only; a replay-ineligible run is never selected.
2. Among those, **prefer** ones whose A2 9-artifact `file_artifact_completeness` passes (checked read-only — this module never writes `artifact_manifest.json` into a source run's own directory).
3. Deterministic tie-break: latest `analysis_date`, then latest `created_at`, then `run_id` lexicographically — never directory/OS/DB incidental order.

`database_record_status` is reported independently (`found:<status>` / `not_found` / `not_checked` / `DATABASE_READ_FAILED`) and never influences selection — confirmed via the real run of this repository's actual database, which currently has a row for only 1 of the 6 selected runs (§3.8).

## 6. Six-ticker coverage table (real saved runs, this repository, this run)

| Ticker | Run ID | Analysis date | File artifact completeness | DB record | Replay | Label evaluation |
|---|---|---|---|---|---|---|
| NVDA | `e3eb3909-3744-4a02-9b32-b225cf6ef665` | 2026-08-11 | pass | found:completed | completed | evaluated |
| QQQ  | `a364e0ee-3bb4-4032-88b7-5cd82e379805` | 2026-07-31 | fail (predates A2 finalizer) | not_found | completed | evaluated |
| MSFT | `0cb43bae-1a4d-4003-bb29-55d420498842` | 2026-07-31 | fail (predates A2 finalizer) | not_found | completed | evaluated |
| SNDK | `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f` | 2026-07-27 | fail (predates A2 finalizer) | not_found | completed | evaluated |
| TSM  | `1a338ced-118e-44d2-b3f6-2444bfb9d7e6` | 2026-08-03 | fail (predates A2 finalizer) | not_found | completed | evaluated |
| AMD  | `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6` | 2026-07-31 | fail (predates A2 finalizer) | not_found | completed | evaluated |

"File artifact completeness: fail" for 5/6 tickers means those saved runs' **own, original** on-disk artifact bundle predates the A2 Sprint-1 finalizer (missing `evidence_facts.json`/`alpha_activations.json`/`conflicts.json`) — it does **not** block replay (Architecture Replay only requires `raw_agent_outputs.json` + `metadata.json`, both present for all 6), and Architecture Replay's own output bundle is itself A2-complete regardless. Reported honestly, never silently upgraded to "pass" or silently excluded.

## 7. Per-ticker expected vs. detected (real replay results)

| Ticker | Missing expected | Unexpected | Main conflict | Allowed | Match |
|---|---|---|---|---|---|
| NVDA | `A103, A201` | `A001` | `A301__A304` | `A101__A304, A301__A304` | **True** |
| QQQ  | `A001, A003` | `A301` | `None` | `A001__A501` | False (candidate, `BULL_SCORE_BELOW_THRESHOLD`) |
| MSFT | `A101, A102, A304` | — | `None` | `A102__A304` | False (`A102__A304` undeclared -> not_reached) |
| SNDK | `A201, A301, A304` | — | `None` | `A201__A304, A301__A304` | False (`A301__A304` candidate; `A201__A304` undeclared -> not_reached) |
| TSM  | `A103, A304` | — | `None` | `A201__A304, A301__A304` | False (`A301__A304` candidate; `A201__A304` undeclared -> not_reached) |
| AMD  | `A101, A201` | `A501` | `A301__A304` | `A101__A304, A201__A304` | False (real main conflict is a pair J2 did not predict for AMD at all; `A101__A304` only reached candidate) |

Every mismatch above is a **provisional review finding**, not a formal regression failure (task sections 11–12; none of them changed the CLI's exit code — see §11). `evidence_polarity_errors = 0` and `ticker_consistency = pass` for all 6 tickers; `dominance_guard_review_required` is empty for all 6 (no J2-flagged "should not be dominant" alpha actually reached dominant/regime_level in the real replay).

Every non-null `expected_pair_status: "candidate"` entry carries B2's own real, already-computed admissibility failure reason codes verbatim (e.g. QQQ's `A001__A501`: `BULL_SCORE_BELOW_THRESHOLD`; SNDK's `A301__A304`: `BULL_SCORE_BELOW_THRESHOLD, INSUFFICIENT_BULL_SUPPORTING_EVIDENCE, NO_BULL_TICKER_SPECIFIC_SUPPORT, BEAR_SCORE_BELOW_THRESHOLD, NO_BEAR_TICKER_SPECIFIC_SUPPORT`) — never fabricated, never a reason invented to explain the gap.

Full per-ticker detail (every field in task section 13's schema) is in `outputs/regression/regression_report.json`, produced by the exact fixed command:

```
python scripts/run_regression.py --tickers NVDA QQQ MSFT SNDK TSM AMD
```

## 8. Stance source

Every one of the 6 tickers reports `stance_source: "deterministic_baseline"`. This is expected and structural, not a gap: Architecture Replay always calls `build_alpha_matches_payload` with no `llm_gateway` (its own docstring: *"Architecture Replay, which never passes one"*), so B1's LLM stance upgrade is always a zero-cost no-op for every replayed candidate (`stance_method` stays `None`, i.e. "never attempted" — not "unavailable"; the underlying deterministic `evidence_stance` classification always runs). A saved run's own already-persisted `alpha_matches.json` may have been produced with live LLM stance at the time it first ran, but A4 never reads that file — only the fresh, zero-Provider replay output, per the task's own "never call an LLM Provider" constraint. This is disclosed explicitly, not hidden.

## 9. Evidence polarity: contract-integrity scope only

`evidence_polarity_errors` counts only mechanically-verifiable contract violations: invalid stance vocabulary, an `illegal`/unexpected `counter_alpha_id`, a promoted `matched_evidence_stance` that disagrees with its own `candidate_scores[]` entry, and a B2 bull/bear supporting-evidence-pool item whose `evidence_stance` is not `supports_alpha`. All 6 real tickers: **0**. This is never reported as "B1 semantic accuracy" — `semantic_polarity_accuracy` stays `null` and `semantic_polarity_review_status` stays `"PENDING_J3_HUMAN_REVIEW"` for every ticker, exactly per task section 12. The B1 50-row sample was **not** re-run.

## 10. A known, honestly-diagnosed replay characteristic (found while writing the determinism test)

`evidence_fact_group_id` (and therefore the on-disk ordering of `evidence_fact_groups`) is intentionally scoped to `(run_id, ticker, claim_ids)` (`evidence_fact_index.evidence_fact_group_id`). Since every Architecture Replay invocation mints a fresh `replay_run_id`, this ID (and any ordering derived from sorting by it) legitimately differs between two separate replay calls of the *same* source run — this is by design (the same reason `claim_id`s/`run_id`s themselves differ), not a determinism bug. It has **zero effect** on anything A4 actually compares (activation scores, `qualified_level`, `alpha_id`-keyed sets, `conflict_id` which is Alpha-ID-based) — confirmed by the dedicated determinism test, which compares only the `alpha_id`-keyed classification/scoring fields and found them **exactly identical** across two independent replay runs of the same source. This is a different, unrelated characteristic from the previously-known `RECENCY_FALLBACK_SCORE`/`as_of` replay confound noted during the B4 segment; noted here for anyone building further replay-comparison tooling.

## 11. CLI behavior

```
python scripts/run_regression.py --tickers NVDA QQQ MSFT SNDK TSM AMD
```

- Tickers normalized to uppercase; duplicates deduped with a stderr `NOTE:`; an unrecognized ticker is a clear `ERROR:` + exit 2 (first batch is exactly the 6 supported tickers).
- Prints each ticker's `run_id`/`run_selection_status`/`offline_reprocess_status`/`main_conflict_match` as it evaluates, then the `regression_report.json` path, then `provider_calls`/`tradingagents_calls`, then `overall_execution_status`/`six_ticker_live_coverage`.
- Never starts the API or frontend. Never calls a Provider.
- **Exit code policy** (documented in the script's own `--help`, never silent):
  - `0` — every requested ticker's evaluation ran to completion, **including** a `coverage_partial` run (a provisional mismatch alone never flips the exit code; the printed summary and report always show the real status, so `0` is never a disguised failure).
  - `2` — invalid CLI arguments.
  - `3` — the J2 label file failed to load/validate.
  - `4` — the runner crashed, or any ticker's ticker-consistency check reported `"fail"`, or a replay's own source-artifact hash-identity check failed.
- Repeated execution against the same artifacts is deterministic in content (verified: two full runs' `regression_report.json` are byte-identical except `generated_at` and the per-run `replay_run_id` values, both legitimately non-deterministic identifiers).

**Real run result:** exit code `0`, `provider_calls=0`, `tradingagents_calls=0`, `overall_execution_status=complete`, `six_ticker_live_coverage=complete`.

## 12. Safety verification

- Every one of the 6 real source run directories (`outputs/runs/<run_id>/`) was hashed (all files, sorted, sha256) **before** and **after** two full six-ticker CLI runs (12 replay invocations total). **All 6 unchanged, both times.**
- `ReplayResult.llm_provider_calls`/`tradingagents_calls`/`market_data_provider_calls`/`database_writes` are `0` for every ticker, every run — read directly from Architecture Replay's own tracked counters, never independently re-counted or asserted without evidence.
- The runner never writes into `outputs/runs/`; every replay artifact lives under an independent workspace (`outputs/regression/replays/<replay_id>/` by default, overridable via `--replay-output-root`).
- `regression_report.json` is written only to `outputs/regression/regression_report.json` (or `--report-path`) — never overwrites a source run.

## 13. Targeted and full test results

- **New dedicated suite:** `tests/test_a4_regression_runner.py` — **41/41 passed** (Section A Labels: 7, Section B Run selection: 6, Section C Alpha comparison: 7, Section D Conflict comparison: 4, Section E Evidence polarity: 4, Section F Safety: 6, plus 7 report-assembly/stance-source tests). Section F genuinely exercises a real saved run (module-scoped shared fixture, one real replay reused across 4 assertions, plus 2 more real-replay tests for determinism and the full CLI) — never mocked.
- **Ruff:** clean on every new file.
- **Full backend regression:** established fresh both before and after this segment's own test file was added — see exact counts below (§14). Zero new regressions: the pre-existing 3 failures (unrelated to A4 — `test_source_integrity.py`'s frozen-baseline mismatch and `test_w5_demo_seed.py`'s `NVDA_MAIN_CONFLICT_NOT_ARBITRATED`, both pre-dating this segment) are the only failures, identical before and after.
- **Frontend:** not touched this segment (no shared type/API contract change) — per task section 19 step 10, frontend tests/typecheck/build were correctly **not** re-run "just for form."

## 14. Full regression exact counts

Before this segment's own `tests/test_a4_regression_runner.py` existed (i.e. immediately after the A3 segment): **3415 passed, 3 failed, 47 skipped**.

Full suite including the new A4 test file: **3456 passed, 3 failed, 47 skipped, 17 warnings, 69 subtests passed** (`681.57s`) — exactly `3415 + 41` new passing tests, the same 3 pre-existing failures, zero new ones:

```
FAILED tests/structured_output_shadow/test_source_integrity.py::test_current_semantic_components_match_approved_phase1_master_baseline
FAILED tests/test_w5_demo_seed.py::test_seed_is_complete_idempotent_and_reusable_without_provider
FAILED tests/test_w5_demo_seed.py::test_only_nvda_and_qqq_are_seeded
```

Both are pre-existing and unrelated to A4 (root-caused in the A3 segment's own report: a frozen SHA-256 baseline predating B1's Evidence Stance changes, and a demo-seed golden fixture predating B2's stricter Conflict Evidence Admissibility gate — neither `alpha_mapper.py`/`week2_llm.py` nor `scripts/seed_w5_demo.py` were touched by A4).

## 15. Explicit non-goals confirmed not done

No J3 50-Evidence human semantic review, no John-20 Alpha Mapper gold audit, no B1 live environment configuration fix, no cold-start history repair, no repository cleanup, no old-artifact deletion, no low-confidence threshold product decision, no new Alpha invalidation content, no new ticker added beyond the fixed 6, no real Provider run. The `evidence_fact_group_id` replay-scoping characteristic (§10) is recorded as a follow-up note only, never expanded into A4's own scope.

## 16. Completion checklist

| Criterion | Status |
|---|---|
| Runner reuses existing offline reprocess path, never a parallel one | ✅ §3 |
| J2 labels versioned, centrally located, schema-validated | ✅ §4 |
| Provisional status structurally un-upgradeable via env var | ✅ §4 (tested) |
| Undeclared conflict pairs reported, taxonomy never modified | ✅ §4 |
| Deterministic run selection; file/DB status reported independently | ✅ §5–6 |
| `detected_alphas` = active∪dominant∪regime_level only | ✅ §7 |
| Conditional alphas never miscounted either direction | ✅ tested (C14/C15) |
| Main conflict only ever comes from admitted; candidate never promoted | ✅ §7 (tested D20/D21) |
| B2 candidate failure reasons preserved verbatim | ✅ §7 |
| Dominance guard is a review flag only, no reclassification | ✅ §7 |
| Evidence polarity scope is contract-integrity only, never semantic accuracy | ✅ §9 |
| Provider calls = 0, TradingAgents calls = 0 | ✅ §11–12 |
| Source artifacts hash-identical before/after | ✅ §12 |
| Repeated execution deterministic (content, not identifiers) | ✅ §11 |
| Fixed six-ticker CLI command runs end-to-end | ✅ §11 |
| No commit, no push | ✅ HEAD unchanged |
