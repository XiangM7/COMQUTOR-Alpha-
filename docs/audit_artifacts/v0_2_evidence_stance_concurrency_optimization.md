# Evidence-Stance Concurrency Optimization — John Requirement B, Phase B2 Slice 2A

**Bounded concurrency for `evidence_stance_classifier`.** Latency optimization only — zero semantic change, zero Provider-call-count change (beyond normal retry variance), zero Provider calls during validation. Builds on B1 (PASS) and B2 Slice 1's cache (PASS, unchanged, remains enabled).

## Executive Result

**PASS**, with one important disclosed finding. Stance batches are proven independent. Bounded concurrency (default 4, mirroring `alpha_classifier`'s own proven default) was implemented. **Testing this slice's own new code surfaced a genuine, reproducible latent race** in the shared concurrent-dispatch pattern (`SemanticCallRecorder`'s sequence-monotonicity check versus out-of-order batch completion) — fixed locally, inside `evidence_stance_llm.py`'s own orchestration only, with zero changes to `alpha_mapper.py`, `session.py`, or `recorder.py`. Offline simulation estimates a **~74% reduction** in the stance stage (QQQ post-fix: 1604.2s → 416.3s), **~40% of total semantic wall clock**, and **~38% of the whole research run** — all explicitly labeled offline estimates pending a live timing validation.

## Independence Proof

Traced `apply_llm_stance_upgrade → chunk_items → _process_batch` directly from source (not assumed):

- **Inputs**: each `StanceRequestItem` carries its own independent payload; no batch reads another's input.
- **Outputs**: each item's own unique `candidate` dict — verified no two items across the whole run ever share a candidate object.
- **Shared mutable state found**: `StanceRunStats` (the run-wide counter accumulator) — the only genuinely shared object across batches. **Fixed**: every mutating method now lock-protected.
- **Ordering**: results are written **in place** onto pre-existing candidate objects referenced from `matches` — there is no completion-order-dependent output list, so batch completion order cannot affect the final artifact's content or order.
- **Framework infrastructure** (`Week2LLMGateway`'s call-budget counter/error logger, `SemanticRuntimeSession`'s trace allocation and cache access): already lock-protected — the same infrastructure `alpha_classifier`'s own concurrency=4 already relies on in production.

**Verdict: `EVIDENCE_STANCE_CONCURRENCY_SAFE`**, with one infrastructure item requiring a fix (below).

## Critical Finding: Recorder Sequence Race (Discovered and Fixed)

Naively dispatching evidence-stance batches concurrently — mirroring `alpha_classifier`'s own pattern exactly — **reproducibly triggered `RECORDER_SEQUENCE_NOT_MONOTONIC`**, silently dropping completed stance results from the persisted call log (caught by the existing fail-soft degradation mechanism, so no crash, but real data loss). Reproduced deterministically with a real `Week2LLMGateway`/`SemanticRuntimeSession` and a zero-delay fake model — **ordinary thread-scheduling nondeterminism alone was sufficient**, no artificial delay variance needed.

**Root cause**: `SemanticCallRecorder.append` (and the equivalent static replay validator) require `call_sequence` to increase strictly in append/file order. Sequence numbers are allocated the moment a worker thread *begins* its call; the corresponding `finalize`/`append` happens only after that thread's work *completes*. Under real concurrency, completion order need not match allocation order.

**Scope**: this is a structural characteristic of the *shared* concurrent-dispatch pattern, not unique to evidence-stance — `alpha_classifier`'s own existing concurrency=4 is built on the identical pattern and is theoretically exposed to the same race, though its far more uniform, much shorter per-call durations (mean ~2s vs. evidence-stance's mean ~48.6s, max 135s) make the specific reversal scenario statistically rarer. **Disclosed transparently as a pre-existing, latent characteristic this slice's own stress-testing surfaced — not a new defect this slice introduced.**

**Fix (local to this slice only)**: split `_process_batch` into `_invoke_batch` (phase 1 — issues the Provider request, safe to run concurrently) and `_finalize_batch` (phase 2 — gateway finalization + per-item result application, byte-identical logic to the original). The concurrent orchestration dispatches phase 1 across the thread pool, waits for all batches, **sorts them by each invocation's own `trace_handle.call_sequence`** (recovering true allocation order regardless of completion order), then runs phase 2 serially in that order — guaranteeing the recorder always receives strictly ascending sequences. **Zero changes to `session.py`, `recorder.py`, `week2_llm.py`'s `invoke_json_with_trace`, or `alpha_mapper.py`/`alpha_classifier`'s own code.** `alpha_classifier` is left exactly as it was — this latent characteristic there is flagged as a candidate for a small, separately-authorized follow-up using the same technique, not implemented here.

**Verification**: reproduced the failure 5/5 times before the fix; **20/20 clean runs** after it, including the exact real-session/recorder/manifest test that originally caught it.

## Concurrency Implementation

- **Mechanism**: `ThreadPoolExecutor`, mirroring `alpha_mapper._classify_alpha_concurrent_with_llm`'s proven pattern exactly.
- **Previous concurrency**: 1 (fully serial). **New default**: 4.
- **Resolution**: new `week2_llm.resolve_evidence_stance_concurrency()`, mirroring `resolve_alpha_classifier_concurrency()` exactly — env var `COMQUTOR_WEEK2_STANCE_CONCURRENCY` (deliberately separate from `alpha_classifier`'s, since the two tasks have very different per-call cost profiles), default 4, hard ceiling 8.
- `concurrency<=1` or a single batch reproduces the **exact** prior serial behavior — verified byte-identical.
- `structured_adapter` and `alpha_classifier` concurrency: **unchanged**, not touched.

## Seven-Run Scheduling Simulation

Greedy list-scheduling using each run's own persisted call latencies (not an idealized `sum/workers` division):

| Run | C1 (s) | C2 (s) | C4 (s) | C6 (s) | C8 (s) | C1→C4 reduction |
|---|---|---|---|---|---|---|
| NVDA | 2739.9 | 1372.7 | 720.3 | 472.3 | 360.1 | 73.7% |
| QQQ historical | 2216.4 | 1136.0 | 595.7 | 415.6 | 325.6 | 73.1% |
| MSFT | 2671.3 | 1350.6 | 718.2 | 450.2 | 360.1 | 73.1% |
| SNDK | 3629.3 | 1840.4 | 940.0 | 630.3 | 493.4 | 74.1% |
| TSM | 2805.3* | 1426.6 | 720.3 | 526.3 | 360.1 | 74.3% |
| AMD | 405.4 | 225.1 | 135.1 | 90.0 | 90.0 | 66.7% |
| **QQQ post-fix** | **1604.2** | **812.4** | **416.3** | **282.3** | **247.7** | **74.05%** |

*TSM's actual observed serial span (4600.4s) exceeds this pure-latency-sum C1 estimate — evidence of real-world gaps between calls not captured by the model; disclosed as a methodology caveat, not smoothed over.

**Median C1→C4 reduction: 73.7%.** Diminishing returns confirmed past C4 (e.g. QQQ post-fix: C4→C6 saves 134.0s, C6→C8 only 34.6s further).

## Concurrency Selection: 4

Chosen for latency benefit + Provider pressure + long-tail behavior + existing precedent + implementation simplicity — **not** because it was fastest in simulation (C6/C8 shown for comparison only, per instruction). Reuses the exact value already validated safe against the real Provider for `alpha_classifier`, rather than a new, untested ceiling. **Provider pressure**: up to 4 concurrent stance batches, potentially overlapping with `alpha_classifier`'s own independent pool of up to 4 (worst case 8 simultaneous requests across both tasks) — a real consideration, mitigated by reusing an already-proven per-pool cap rather than raising it further in this slice.

## Deterministic Output Order

Artifact order: guaranteed by design (write-by-reference onto pre-existing objects) and by test (`test_one_slow_batch_does_not_reorder_or_corrupt_other_results` — an artificially slow first-submitted batch finishes last; every claim's result and the `matches` list order are unaffected). Recorder order: guaranteed by the sequence-sorted finalize fix above.

## Exact Semantic Equivalence

Unchanged: claim IDs, Alpha IDs, stance labels, fallback outputs/reasons, validation behavior, qualification behavior, evidence-pool membership, downstream graph/activation/conflict derivation (no code touched on any of those paths). Verified via `test_concurrency_1_and_concurrency_4_produce_identical_semantic_results` — byte-identical stance/method values and identical stats between concurrency=1 and concurrency=4.

## Cache Interaction (Slice 1)

**Gap found**: `InMemoryLLMResponseCache`'s get/put/delete each perform a check-then-act sequence not atomic as a whole under concurrent access — a live concern now that evidence-stance's new concurrency shares the same cache instance alongside `alpha_classifier`'s pre-existing concurrency. **Fix**: one `threading.Lock`, held across each method's own check-then-act sequence. Zero changes to the cache-key design, protocol, `RedisLLMResponseCache`, `NullLLMResponseCache`, or eligibility rules. Verified via `test_cache_correct_under_concurrent_stance_batches`: 40 claims across 4 concurrent batches populate the cache without exception; a second, independent gateway sharing the same cache instance serves all 4 batches from cache (0 Provider calls) with identical results.

## Telemetry Concurrency Safety

Verified valid under concurrency (after the sequence-ordering fix): exactly 4 records for 4 batches, ascending `call_sequence` `[0,1,2,3]`, no gaps/duplicates, correct task/validation/provider-status fields. `StanceRunStats` counters verified accurate via lock-protected mutation and direct assertion in the error-isolation test (10 fallback / 20 LLM results / 3 batches, exactly as scripted).

## Retry / Fallback Preservation

Zero changes to max retries, retry conditions, backoff, timeout classification, fallback triggers, or validation-retry behavior — all remain entirely inside `Week2LLMGateway.invoke_json_with_trace`, called once per batch exactly as before. A failed/timed-out batch's fallback is isolated to its own items only — verified via `test_one_timed_out_batch_preserves_fallback_semantics_for_itself_only` (10 items correctly fell back while 20 others, in two concurrently-running batches, correctly received LLM results).

## Offline Replay / Pipeline Equivalence

Semantic mismatches: **0**. Pipeline mismatches: **0** — no code was touched in `comqutor_alpha/graph_engine/`, `comqutor_alpha/conflict_engine/`, or `alpha_mapper.py`'s matching/activation logic, so these outcomes are structurally incapable of having changed. NVDA (dominant A301, main conflict A101__A304) and SNDK (dominant A201, no admitted conflict) match the task's stated baseline exactly. **QQQ post-fix** (`f239a53f-...`): A001 non-detected (level=candidate) and no dominant Alpha both confirmed unchanged; actual main conflict **A301__A304**, matching the task's stated baseline exactly.

**Correction note**: an earlier revision of this artifact incorrectly attributed here the **historical** QQQ run's (`f88c8956-...`) actual main conflict (`A304__A601`) to the **post-fix** run (`f239a53f-...`), by misciting `v0_2_six_run_gold_conformance_audit.json`'s own QQQ entry — that entry describes the historical run, not the post-fix one; the six-run audit's figures were never wrong, only this artifact's citation of them was. Directly re-verified independently from both runs' own `run_audit.json.conflict_summary.main_conflict_id`, and cross-checked against `v0_2_final_acceptance_closure.json`, which explicitly states: *"Post-fix QQQ actual main conflict is A301__A304, not the more strongly evidence-triggered A601__A304 family."* The two runs are kept explicitly distinct below — neither run's conflict is used as evidence for the other:

| | Historical QQQ | Post-fix QQQ |
|---|---|---|
| `run_id` | `f88c8956-cb62-48aa-9951-89f8e8a95f83` | `f239a53f-4ebe-455c-bb76-5f5485903901` |
| Actual main conflict | `A304__A601` | `A301__A304` |
| A001 | (defect: falsely detected) | non-detected (candidate) |
| Acceptance | FAIL (QQQ A001 defect) | PASS (6/6 blocking rules) |

This slice's own timing simulation (C1/C4/etc.) was **always** based on the post-fix run (`f239a53f-...`)'s own persisted call durations throughout — the conflation affected only this narrative note, never the timing figures.

## QQQ A001 Preservation

`alpha_mapper.py` (which owns the A001 remediation) was **not modified** by this slice — confirmed via `git diff` (zero lines changed). `tests/test_qqq_a001_mapping_remediation.py` re-run and passes unmodified. **Preserved.**

## 34+9 Benchmark

Expected and verified impact: **NONE**. Zero changes to evidence-stance validation/fallback logic or Alpha-mapper matching logic; the 34+9 benchmark's own separate, older holdout sample is not exercised by this task.

## Second Finding: Test-Double Thread Safety (Discovered and Fixed)

Full-suite regression testing surfaced a second, independent latent issue: `tests/test_evidence_stance_llm.py::test_14_batch_size_is_capped_at_ten` began failing **intermittently** (reproduced 1/5–1/20 runs) once `apply_llm_stance_upgrade` started defaulting to real concurrency. **Root cause**: the shared `FakeStanceGateway` test double maps each call to its scripted response by call *count* (`self._responses[len(self.calls) - 1]`) — neither thread-safe nor order-independent, an assumption that held under the old always-serial default but not under real concurrency. **Fix**: added a lock to `FakeStanceGateway` (same class of fix as `StanceRunStats`/`InMemoryLLMResponseCache`), and pinned the one affected test to `concurrency=1` explicitly, since its actual purpose (verifying `chunk_items`' batch-size capping) doesn't require concurrent execution at all. **Test-file-only change** — zero production impact. Verified: 20/20 clean runs after the fix.

## Test Results

- Focused concurrency tests: **12/12 pass**, stress-tested **20/20 clean runs**.
- Existing evidence-stance tests: **90/90 pass** (1 pinned to `concurrency=1` for the reason above; behavior otherwise unmodified).
- Cache Slice-1 tests: **20/20 pass** against the now-hardened `cache.py`.
- Combined targeted batch (evidence-stance + retry-fix + concurrency + llm_runtime + semantic-runtime + semantic-artifact-pipeline + alpha-mapper + A001 + structure-extractor): **338/338 pass.**
- Full backend suite: see final response for the complete, freshly re-run tally. Root-cause-verified: exactly **one expected new pin failure** (`test_case17_production_semantic_modules_remain_untouched[...evidence_stance_llm.py]` — the same baseline-pin mechanism already disclosed for `alpha_mapper.py` in Slice 1, now also correctly firing for this task's own authorized change to `evidence_stance_llm.py`; not a regression, an unavoidable and expected consequence of any legitimate change to a pinned file) plus the identical 69-item pre-existing/unrelated baseline from Slice 1. **Net new regressions: 0.**

## Estimated Latency Improvement (OFFLINE ESTIMATE, not a measured benchmark)

QQQ post-fix: stance stage 1604.2s → 416.3s (**−1187.9s, −74.05%**). Estimated whole semantic pipeline: 2937.6s → 1749.7s (**−40.44%**). Estimated whole research run: **−37.82%**. Seven-run median stance-stage reduction: **73.7%**.

## Live Timing Validation

**Recommended: yes**, as a separate, explicitly-authorized benchmark step — not executed here. Offline/synthetic validation proves correctness; it cannot prove real wall-clock benefit under actual Provider network/rate-limit conditions with two concurrent pools running at once.

## Next Step

**Phase B2 Slice 2B — structured_adapter concurrency**, reusing this slice's same proven pattern (including the sequence-ordering technique this slice discovered), followed by one **combined, explicitly-authorized live timing validation** covering both slices together. Not implemented here.

---

**Gold closure changed: no. Alpha Memory: SHADOW, untouched. Provider calls: 0. TradingAgents calls: 0. Fresh ticker runs: 0. Commits: 0. Pushes: 0. Destructive git operations: 0.**

**JOHN REQUIREMENT B — PHASE B2 SLICE 2A — PASS.**
