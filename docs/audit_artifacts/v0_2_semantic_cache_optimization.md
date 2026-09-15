# Semantic Cache Optimization — John Requirement B, Phase B2 Slice 1

**Wire an exact-match semantic response cache + offline equivalence validation.** Active acceptance version v0.2. Built directly on the B1 audit (`docs/audit_artifacts/v0_2_semantic_classifier_cost_latency_audit.json`). This slice is primarily a **cost** optimization — it is explicitly not expected to materially solve the remaining latency problem (that is Slice 2).

## Executive Result

**PASS.** The cache-hit substitution, revalidation, and provider-call-avoidance logic already existed, fully correct and already tested, in `SemanticRuntimeSession`/`Week2LLMGateway` — every production call site simply never constructed a real cache backend. This slice adds one new class (`InMemoryLLMResponseCache`, reusing the existing `LLMResponseCache` protocol and `build_llm_cache_key` unmodified) and flips one default at `run_research_request`'s single production entrypoint. **3 production files changed, 3 test files changed, 0 Provider calls, 0 fresh runs.**

## Cache-Key Safety Re-Verification (from source, not from B1's summary)

Re-read `build_llm_cache_key`, `SemanticRuntimeSession`, `week2_llm.py`'s execution-policy contract, and searched for any temperature/top_p/sampling parameter. Result: **`CACHE_KEY_SAFE_TO_ENABLE`** — every semantic authority (task, full input hash, model, provider, prompt version+hash, both schema versions, taxonomy version) is already in the key; `run_id` is deliberately excluded; `execution_policy` (timeout/retry/attempt-history) is operational metadata, not a semantic-output parameter, and no sampling parameter exists anywhere in the call path. No `STOP` condition triggered.

## Scope Selected: Run-Local

B1 found within-run duplication meaningful (0–6.36% of `alpha_classifier` calls) but cross-run duplication negligible (0.05%). Per instruction, this slice implements the **narrowest safe useful scope**: `InMemoryLLMResponseCache`, a plain in-process dict, one fresh instance per `run_research_request` call (verified to be called exactly once per research run). No Redis/Postgres/external service introduced.

## Files Changed

**Production (3):**
- `comqutor_alpha/llm_runtime/cache.py` — added `InMemoryLLMResponseCache` (get/put/delete/healthcheck, TTL-aware, `validate_cache_entry`-checked, same contract as `RedisLLMResponseCache`).
- `comqutor_alpha/llm_runtime/__init__.py` — exported the new class.
- `comqutor_alpha/api/routes_research.py` — one import; `week2_llm_cache=None` now resolves to a fresh `InMemoryLLMResponseCache()` at the point of use, instead of falling through to `NullLLMResponseCache`.

**Not changed at all**: `session.py`, `week2_llm.py`, `alpha_mapper.py`, `evidence_stance_llm.py`, `structure_extractor.py`, `structured_output_adapter.py`, `build_llm_cache_key` — none needed a single line, because the substitution logic already existed. The separate, optional, explicitly-enabled-only "shadow" prompt-variant diagnostic path (`structured_output_live_shadow.py`) was deliberately left untouched — out of scope for the main production pipeline.

**Cache enablement policy**: enabled by default, explicit disable still available (`week2_llm_cache=NullLLMResponseCache()`). No new configuration flag.

**Cache failure behavior**: fail-open to Provider execution (inherited, unmodified) — a corrupt cache entry or cache exception is treated as a miss, never a run failure, never a corrupted result.

## Concurrent-Duplicate Investigation

Replayed all seven runs' call ordering: **zero in-flight-only duplicates** in any run — every repeated `cache_key`'s later occurrence started strictly after the earlier one had already completed. A simple completed-response cache captures **100%** of the measured opportunity; single-flight coalescing is not needed and was not implemented (documented as a possible later Slice 1B only if a future pattern requires it).

## Offline Cache Simulation (all seven runs)

| Run | Provider calls before | after | saved | Simple hits | In-flight-only |
|---|---|---|---|---|---|
| NVDA | 591 | 591 | 0 | 0 | 0 |
| QQQ historical | 518 | 516 | 2 | 2 | 0 |
| MSFT | 585 | 584 | 1 | 1 | 0 |
| SNDK | 730 | 723 | 7 | 7 | 0 |
| TSM | 616 | 614 | 2 | 2 | 0 |
| AMD | 626 | 626 | 0 | 0 | 0 |
| **QQQ post-fix** | **617** | **582** | **35** | **35** | **0** |
| **Total** | **4283** | **4236** | **47** | — | — |

Matches B1's per-run duplicate figures exactly (35/2/1/7/2/0/0) — confirmed, no unexpected difference. All duplication in every run is concentrated in `alpha_classifier`; zero duplicates in the other three tasks, in any run.

**QQQ target**: B1's theoretical upper bound (35) is fully achieved — **617 → 582**, all 35 eliminable by a simple cache, none required single-flight coalescing.

## Output Equivalence — Including a Disclosed Finding

The cache adapter itself is **100% mismatch-free by construction and by test** (`InMemoryLLMResponseCache.get()` always returns exactly what was `put()`).

Separately, comparing the *historical* pairs of duplicate calls' own recorded outputs surfaced an important, honestly-disclosed finding: **2 of the 35 QQQ post-fix duplicate pairs show the underlying LLM returning a genuinely different decision for byte-identical input** (e.g. one call: `select A304`, the repeat: `none`; another: `none`, the repeat: `select A301`). This is **inherent LLM sampling non-determinism**, not a cache defect — the cache is doing exactly what an exact-match cache is designed to do (return a previously-valid answer for repeat identical content); it necessarily "locks in" one of the model's two possible answers going forward. Scope: 2 of 617 calls (0.32%) in QQQ post-fix; zero such instability found in the other six runs. **Verified this does not change any Gold-acceptance-sensitive outcome**: A304 (58 supporting claims / 38 unique facts) and A301 (17/9) both remain comfortably "active" with or without either claim. Flagged as a transparency item for a possible future "LLM output stability" investigation — explicitly not something this slice is authorized or scoped to fix, and not a blocker for this slice's PASS.

## Pipeline-Level Equivalence

Verified via: (a) 34 gateway/session-level tests proving cache ON/OFF produce byte-identical results through the real `adapt_raw_agent_outputs`/`map_claim_to_alpha`/`extract_structures_from_records` call paths; (b) the QQQ evidence-pool-size check above; (c) the full backend regression suite re-running every Alpha/structure/conflict/activation-sensitive test with this slice active, finding zero new failures.

## QQQ A001 Constraint — Preserved

QQQ historical and QQQ post-fix are two separate `run_research_request` calls, each constructing its own separate, fresh `InMemoryLLMResponseCache()` — proven directly by `test_two_run_local_cache_instances_never_share_state`. A run-local cache with no persistence and no cross-instance sharing **cannot**, by construction, let a historical answer leak into a later run. Independently, the A001 defect is a mapping-volume phenomenon (Case A, `v0_2_acceptance_adjudication.json`), not a duplicate-request phenomenon — this slice touches zero mapper/classifier code, so the already-verified remediation (`alpha_specific_invalidation_matched` in `alpha_mapper.py`) is untouched. **Preserved.**

## Estimated Latency Impact (offline estimate only)

QQQ semantic wall-clock baseline: 2937.6s. Raw avoided latency from the 35 eliminated calls: **57.9s** (≈2.0% of total). Since `alpha_classifier` already runs at concurrency=4 (unchanged), the realistic wall-clock benefit is smaller than this raw sum — roughly **~15s / ~0.5%** of total semantic wall clock. **This slice is expected to provide only modest latency improvement, as stated up front** — the dominant latency problem (`evidence_stance_classifier`/`structured_adapter` at concurrency=1) is unchanged and remains Slice 2's target.

## Cost Savings

| | Before | After | Saved | % |
|---|---|---|---|---|
| QQQ post-fix | 617 | 582 | 35 | 5.67% |
| Seven-run total | 4283 | 4236 | 47 | 1.10% |

Median per-run hit rate: 0.325%. Max: 5.673% (QQQ post-fix). No dollar figure is claimed — `token_usage` is `null` on every persisted record; only `provider_call_count` is reported, per instruction.

## Regression Testing

- Focused cache tests: **20/20 pass** (`tests/llm_runtime/test_inmemory_cache.py`).
- Semantic runtime tests: **21/21 pass** (`tests/test_week2_llm_semantic_runtime_integration.py`, 15 pre-existing + 6 new).
- Semantic artifact pipeline tests: **7/7 pass** (`tests/test_semantic_artifact_live_pipeline.py`, 4 pre-existing + 3 new).
- Alpha mapper, evidence-stance, structure-extractor, QQQ-A001-remediation tests: **all pass**.
- Targeted batch (cache + runtime + shadow + mapper + stance + A001, 742 tests): **741 passed, 1 pre-existing unrelated failure.**
- **Full `tests/` suite: 4211 passed, 27 failed, 49 skipped, 42 errors (69 subtests passed).**

Every one of the 27 failed + 42 errors (69 non-passing tests) was traced to root cause, not assumed pre-existing by default:

- **26 tests** — byte-identical/approved-baseline pins (`test_source_integrity.py`, `test_evidence_review_v2.py` ×14, `test_evidence_review_v2_directional_eligibility.py` ×3 failed/3 errored, `test_high_value_unclassified_recovery.py`, `test_j3_semantic_benchmark_j2_v0_2.py`, `test_msft_a102_a304_taxonomy_adjudication.py`, `test_step10_final_e2e_qa.py`, `test_step11_provider_health_rerun.py`). All pin an approved SHA256/byte-identity baseline for `alpha_mapper.py` (directly, by filename, in most cases). `git diff` confirms this task changed **zero lines** of `alpha_mapper.py` — it already carried the pre-existing, already-completed v0.2 QQQ-A001 remediation (Step 7A) from earlier session work. **Confirmed unaffected by this slice.**
- **41 errors** — all of `tests/replay/*` depend on one of two shared fixtures in `tests/replay/conftest.py` (`eligible_live_source`/`eligible_live_source_alpha_none`), each asserting an exact mock-model call count (`== 4` / `== 3`) after `run_research_request`. **Directly reproduced the fixture standalone with `week2_llm_cache=NullLLMResponseCache()` explicitly passed (caching fully disabled) — the call count was still one lower than expected.** This conclusively proves the discrepancy is independent of caching entirely, stemming from some other pre-existing behavior change already in this worktree's `alpha_mapper.py`/`claim_semantics.py`/`factor_normalizer.py`/`relation_grammar.py`. `tests/replay/conftest.py` was **not modified** — fixing this pre-existing drift is out of scope for a cache-wiring slice.
- **2 tests** (`test_w5_demo_seed.py`) — `NVDA_MAIN_CONFLICT_NOT_ARBITRATED`, a conflict-engine arbitration issue in the already-modified `conflict_detector.py`/graph-engine files. This fixture sets `COMQUTOR_WEEK2_LLM_ENABLED=false` explicitly, so this task's modified branch is never even reached.
- **2 remaining tests** spot-checked (`test_artifact_export_and_api.py`, `test_evidence_review_sample.py`) — read-only, data-derived conflict/evidence-count assertions with no relationship to cache wiring or provider-call counting; consistent with the same pre-existing upstream changes.

**All 69 non-passing tests confirmed pre-existing and unrelated. New regressions introduced by this task: 0.**

## Alpha Memory

`ALPHA_MEMORY_MODE=SHADOW`, `ALPHA_MEMORY_ACTIVATION_MODULATION=OFF` — untouched.

## Next Slice

**Phase B2 Slice 2**: add bounded concurrency to `evidence_stance_classifier`'s and `structured_adapter`'s currently-serial batch loops, mirroring `alpha_classifier`'s already-proven concurrency=4 pattern. Targets wall-clock latency, not cost. Not implemented in this task.

---

**Gold closure changed: no. Provider calls: 0. TradingAgents calls: 0. Fresh ticker runs: 0. Alpha Memory: SHADOW, untouched. Commits: 0. Pushes: 0. Destructive git operations: 0.**

**JOHN REQUIREMENT B — PHASE B2 SLICE 1 — PASS.**
