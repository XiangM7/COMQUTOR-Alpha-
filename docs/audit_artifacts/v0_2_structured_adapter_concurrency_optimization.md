# V0.2 — John Requirement B, Phase B2 Slice 2B: Bounded Concurrency for `structured_adapter`

**Companion artifact:** `docs/audit_artifacts/v0_2_structured_adapter_concurrency_optimization.json` (SHA256 `3e6c01ea101620e9904f283a74f7036094f75d14fa7f0108ffc8ced4bc804b05`)
**Status:** PASS
**Repository state:** branch `comqutor-structure-layer`, HEAD `9f228723fad5406c72e62beca67ec70ea0fdb004` throughout (directly verified via `git rev-parse HEAD` at the end of this task). No commits, no pushes, no destructive git operations.

## 1. Objective

Reduce wall-clock latency of the `structured_adapter` semantic stage via bounded concurrency only — no change to semantic coverage, structured outputs, Provider-call count (beyond normal retry/cache behavior), taxonomy, Alpha mapping/stance/structure semantics, activation, conflict logic, Gold, or Alpha Memory.

## 2. Independence proof (required before any implementation)

The true independent unit of `structured_adapter` work is one **(agent, batch-of-≤64-segments)** pair. Verified directly from `outputs/runs/f239a53f-.../llm_semantic_calls.jsonl` (QQQ post-fix), not assumed: exactly 8 calls = 4 LLM-eligible agents (`market_agent`, `sentiment_agent`, `news_agent`, `fundamental_agent`) × up to 2 batches each. No batch reads or depends on another batch's or agent's result — each is a self-contained payload, validator, and enrichment/fallback outcome.

Three classes of shared-mutable-state hazard were found and resolved (see JSON `independence_proof.shared_mutable_state_found` for full detail):
1. **`filter_audit`/`canonical_relations_audit` index-slice attribution** — resolved via fresh, thread-local accumulators per worker.
2. **`global_audit`/`per_agent` aggregation** — resolved via a serial, main-thread-only merge after all concurrent work completes.
3. **Recorder `call_sequence` monotonicity** — `adapt_raw_agent_outputs`'s own `_llm_batch_enrichment` does invoke+finalize together, the same single-phase pattern that caused Slice 2A's discovered `RECORDER_SEQUENCE_NOT_MONOTONIC` race. Resolved proactively via a **new `_DeferredFinalizeGatewayProxy`** that defers `finalize_semantic_invocation` calls until a sequence-sorted serial replay phase — generalizing Slice 2A's fix with **zero changes** to `adapt_raw_agent_outputs`/`_llm_batch_enrichment`.

**Verdict: `STRUCTURED_ADAPTER_CONCURRENCY_SAFE`.**

## 3. Implementation

- New: `_DeferredFinalizeGatewayProxy`, `_run_one_raw_agent_output`, `_adapt_run_outputs_concurrently` in `comqutor_alpha/structure_engine/structured_output_adapter.py`.
- `adapt_run_outputs` gained an optional `concurrency` parameter (env-resolved by default). When `concurrency <= 1`, or there is ≤1 raw agent output, the **exact original serial loop runs byte-for-byte unchanged**.
- New `resolve_structured_adapter_concurrency()` in `week2_llm.py`, mirroring the existing `resolve_alpha_classifier_concurrency`/`resolve_evidence_stance_concurrency` pattern exactly: env var `COMQUTOR_WEEK2_ADAPTER_CONCURRENCY`, default 4, ceiling 8.
- Granularity chosen: **agent-level**, not the finer batch-level, as a deliberate simplicity/risk tradeoff — batch-level flattening was simulated and shown to offer no measured benefit over agent-level on this dataset, while requiring refactoring the internals of well-tested functions. See JSON `concurrency_selection.granularity_tradeoff_disclosed`.

## 4. Concurrency selection (C1/C2/C4/C6/C8 across all seven B1 runs)

| Run | C1 (s) | C2 (s) | C4 (s) | C6 (s) | C8 (s) | C1→C4 reduction |
|---|---|---|---|---|---|---|
| NVDA | 621.9 | 360.1 | 180.1 | 180.1 | 180.1 | 71.04% |
| QQQ_historical | 560.1 | 335.7 | 180.1 | 180.1 | 180.1 | 67.85% |
| MSFT | 699.0 | 360.1 | 180.1 | 180.1 | 180.1 | 74.23% |
| SNDK | 723.3 | 384.2 | 204.1 | 204.1 | 204.1 | 71.78% |
| TSM | 658.4 | 360.1 | 180.1 | 180.1 | 180.1 | 72.65% |
| AMD | 653.8 | 373.9 | 193.8 | 193.8 | 193.8 | 70.36% |
| QQQ_postfix | 595.3 | 324.6 | 167.0 | 167.0 | 167.0 | 71.95% |

(Full per-run figures in the JSON's `seven_run_scheduling_simulation.per_run`.)

- **Median C1→C4 reduction: 71.78%** (min 67.85% QQQ_historical, max 74.23% MSFT).
- **C2 vs C4:** C4 gives a *large* incremental benefit over C2 (46–50% further reduction in every run) — not a diminishing-returns zone. C4 was chosen, not C2, because Section 15's "prefer C2 if C4 offers only a small gain" condition does not apply here.
- **C4 vs C6/C8:** identical in every single run — there are exactly 4 independent agent-level lanes, so concurrency above 4 is a provable no-op. **Selected default: 4**, matching the real fan-out shape exactly and reusing the same cap already validated for `alpha_classifier` and `evidence_stance_classifier`.

## 5. Correctness guarantees verified

- **Deterministic output order**: original agent/segment order preserved regardless of completion order (`test_one_slow_agent_does_not_reorder_or_corrupt_other_agents_records`).
- **Recorder sequencing**: ascending, gap-free `call_sequence`, stress-tested 15/15 clean.
- **Semantic equivalence**: concurrency=1 vs concurrency=4 produce byte-identical records (excluding `run_id`/`timestamp`).
- **Cache correctness** (Slice 1 reused as-is): a third concurrent caller correctly shares the already-lock-hardened `InMemoryLLMResponseCache`.
- **Retry/fallback isolation**: one agent's induced failure falls back to `deterministic_splitter` for itself only; unrelated concurrently-running agents are unaffected.
- **A001 preserved**: `alpha_mapper.py` untouched (byte-identical diff to before this task); structural test confirms `structured_output_adapter.py` never references any A001-remediation function.
- **Pipeline equivalence**: zero code touched in `alpha_mapper.py`, `evidence_stance_llm.py`, `graph_engine/`, or `conflict_engine/` — NVDA/QQQ-postfix/SNDK outcomes structurally incapable of having changed.

## 6. Test results

- New focused suite `tests/test_structured_adapter_concurrency.py`: **13/13 pass**, stress-tested **25/25 clean** (one test-only timestamp-comparison bug found and fixed — zero production impact).
- Existing structured-adapter/semantic-runtime/cache/stance-concurrency/alpha-mapper/A001/structure-extractor combined batch: **457/457 pass**.
- Graph/activation/conflict/research-pipeline regression suites: **573/573 pass**.
- Full backend suite (`tests/ -q --tb=no -rfE`): **4235 passed, 28 failed, 42 errors, 49 skipped, 69 subtests passed** — this exactly matches the pre-existing baseline (27 pre-existing failures + 1 already-failing baseline-pin test now additionally reflecting this task's own authorized hash changes = 28; 42 pre-existing `replay/conftest.py` `OfflineSemanticModel` call-count fixture errors, unrelated to this task = 42). **Zero net-new failing or erroring tests.**
  - Root-caused example: `tests/structured_output_shadow/test_source_integrity.py::test_current_semantic_components_match_approved_phase1_master_baseline` — was already failing (on `alpha_mapper.py`'s pre-existing A001 hash), now also differs on `structured_output_adapter.py`/`week2_llm.py` — classified `SOURCE_BASELINE_PIN_EXPECTED_CHANGE`, same single test, no new failure count.
  - Root-caused example: `tests/test_j3_semantic_benchmark_j2_v0_2.py::...test_e42_head_unchanged_from_session_frozen_starting_commit` — asserts against a **stale hardcoded constant** (`b5837e80a4550fc35165d0013a8ef0f27ccb4c8f`) from an older, unrelated task's own test file; directly verified via `git rev-parse HEAD` that the actual, correct HEAD is still `9f228723fad5406c72e62beca67ec70ea0fdb004` throughout this task — classified `PRE_EXISTING_UNRELATED`, not a repository-safety violation.
  - Root-caused example: `tests/replay/test_exact_semantic_replay.py::...` (and the other 41 `replay/` errors) — pre-existing `tests/replay/conftest.py` `OfflineSemanticModel` call-count fixture expectation (unrelated to this task's changes) — classified `PRE_EXISTING_UNRELATED`.

## 7. Combined offline latency model (Slice 1 + Slice 2A + Slice 2B, no double-counting)

Reference run: QQQ post-fix (`f239a53f-4ebe-455c-bb76-5f5485903901`).

| Component | Value |
|---|---|
| Baseline total run wall-clock | 3141 s |
| Baseline semantic wall-clock | 2937.6 s |
| Cache (Slice 1) savings | 15 s |
| Stance concurrency (Slice 2A) savings | 1187.9 s |
| Adapter concurrency (Slice 2B) savings | 428.3 s |
| **Combined semantic wall-clock after** | **1306.4 s** |
| **Combined total wall-clock after** | **1509.8 s** |
| **Combined total reduction** | **51.93%** |

No double-counting: the four semantic stages (`structured_adapter`, `alpha_classifier`, `evidence_stance_classifier`, `structure_extractor`) run sequentially relative to each other (per B1), so per-stage savings sum directly. **This is an offline, simulation-based estimate only — not a measured live benchmark.**

## 8. QQQ provenance guard

- **Historical QQQ**: `f88c8956-cb62-48aa-9951-89f8e8a95f83`, `actual_main_conflict=A304__A601`.
- **Post-fix QQQ**: `f239a53f-4ebe-455c-bb76-5f5485903901`, `actual_main_conflict=A301__A304`, A001 non-detected (candidate level), no dominant Alpha.
- These are never conflated. This slice's own timing reference is the post-fix run exclusively, verified directly from its own `llm_semantic_calls.jsonl`.

## 9. Next recommended step

Per instruction: **STOP optimizing further.** The recommended next step is **ONE COMBINED LIVE TIMING VALIDATION** covering Slice 1 (cache) + Slice 2A (evidence-stance concurrency) + Slice 2B (structured-adapter concurrency) together, against the real Provider, to determine whether John Requirement B can be closed. This validation is **NOT executed in this task** — zero Provider calls, zero fresh research runs were made.
