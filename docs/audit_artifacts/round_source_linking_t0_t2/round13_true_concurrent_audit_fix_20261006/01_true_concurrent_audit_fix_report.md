# Round 13: True Concurrent Audit Support for Week2LLMGateway

2026-10-06. Builds directly on round 11 (defect discovery, forced-serial
interim fix) and round 12 (client audit wiring, recovery script, budget/
terminology corrections) for the AMD `c904d4cc-dc09-495c-aec5-b056979948e1`
Fresh Run. This round's own mandate, verbatim from the controlling
instruction: *"当前第一优先级改为：确认失败机制，并完成真正支持并行的审计
修复... 强制串行不能作为本次并行修复的最终完成结果"* -- forced
serialization is explicitly **not** an acceptable final deliverable this
round. This report documents the real redesign that replaces it.

Scope discipline, unchanged from rounds 11-12 and re-confirmed throughout
this round: zero real Provider/search calls, no Fresh Run, no real
recovery execution, no model/prompt/scoring/taxonomy change, no v3 feature
mixing, the original `c904d4cc` run and its historical artifacts read-only
(hash-verified unchanged, see 六 below), new artifacts in this independent
directory only, no commit/push/Demo.

---

## 一. The pre-fix failure mechanism (re-confirmed, precise)

This section restates round 11's own finding with the exact code
references as they existed **before** this round's fix, since the
instruction explicitly asked for this to be reconfirmed in this round's own
context, not merely cited from an earlier round's report.

**Where the shared pending state lived.** `Week2LLMGateway.__init__` held a
single instance attribute:

```python
self._pending_audit_attempt: dict[str, Any] | None = None
```

one dict, not a collection, not keyed by attempt -- so the Gateway could
track at most **one** in-flight attempt's identity at any instant, no
matter how many real concurrent callers existed.

**How parallel calls shared it.** `invoke_json_with_trace`'s attempt loop
called `self._set_pending_audit_attempt(attempt_id, task, payload)`
immediately before `call_with_timeout(lambda: task_model.invoke(prompt),
...)`, and `self._reset_pending_audit_attempt()` in the corresponding
`finally`. The setter, guarded by `self._lock`, raised
`RuntimeError("WEEK2_LLM_AUDIT_CONCURRENT_ATTEMPT: ...")` if
`self._pending_audit_attempt is not None` when a second thread called it --
i.e. any second concurrent caller arriving before the first had reached its
own `finally`/reset.

**Exact throw site.** Inside `Week2LLMGateway._set_pending_audit_attempt`
(pre-fix), under `with self._lock:`, immediately on detecting
`self._pending_audit_attempt is not None`.

**Was budget already reserved? Was HTTP already sent?** Yes to the first,
no to the second, for the *rejected* caller. `invoke_json_with_trace`'s
loop calls `self._reserve_call()` (which increments the real
`self._call_count` against `self.max_calls`) **before** allocating
`attempt_id`/calling `_set_pending_audit_attempt`. A concurrent caller that
lost the race consumed one real call-budget unit, then raised
`WEEK2_LLM_AUDIT_CONCURRENT_ATTEMPT` before `call_with_timeout` ever ran --
so zero bytes reached the network for that attempt, but the budget ledger
already reflected it as spent. (This exact fact is what made round 12's
original "~1227 remaining" report wrong -- corrected there to the
precise 1242 consumed / 258 remaining, re-confirmed unchanged by this
round's own fix, which does not touch `_reserve_call`'s ordering.)

**Which handler converted it to `provider_error`.**
`alpha_mapper._classify_alpha_with_llm`'s own call site:

```python
try:
    if llm_gateway is not None:
        ...
        invocation = llm_gateway.invoke_json_with_trace(...)
        ...
except TimeoutError:
    return _unavailable("provider_timeout")
except Exception:
    return _unavailable("provider_error")
```

`WEEK2_LLM_AUDIT_CONCURRENT_ATTEMPT` is a bare `RuntimeError`, not a
`TimeoutError` -- it fell into the generic `except Exception`, which has no
visibility into *why* the call failed. This is the exact mechanism by which
973 of 975 real `alpha_classifier` attempts in the real `c904d4cc` run
became indistinguishable, at the result level, from a genuine Provider
outage.

**Why normal error logs never recorded it.** `invoke_json_with_trace`
itself never ran far enough to construct a `Week2LLMInvocation` or call
`self._log(...)` for this failure mode -- the `RuntimeError` was raised and
caught entirely *outside* `invoke_json_with_trace`, inside
`_classify_alpha_with_llm`'s own try/except, which discards the exception
after converting it to the generic fallback reason. Neither
`week2_llm_errors.jsonl` nor `llm_semantic_calls.jsonl` (both written from
inside `invoke_json_with_trace`/`finalize_semantic_invocation`) ever saw
this attempt. This is the precise mechanism that made the defect invisible
to every log a normal post-run audit would check.

**Reproduction this round.** Re-confirmed by temporarily reverting the
contextvar change in a scratch checkout and re-running
`test_real_concurrent_dispatch_no_longer_fails_with_contextvar_identity_fix`
against the pre-fix code: the test fails with exactly
`RuntimeError: WEEK2_LLM_AUDIT_CONCURRENT_ATTEMPT...` surfacing as
`alpha_match_method="llm_unavailable"`, `alpha_match_fallback_reason=
"provider_error"` for most of the 8 claims -- the same signature as the
real run. (Not left reverted; this was a throwaway verification, not part
of the committed diff.)

---

## 二. The fix: real per-attempt identity via `contextvars`, not forced serialization

Per the instruction's explicit requirement ("可以使用显式上下文传递，或正确
传播的contextvars等现有机制；不要假定contextvars会自动跨线程传播... 选一
种能在真实调用链证明有效的最小实现"), this round:

1. **Removed** `self._pending_audit_attempt` entirely from
   `Week2LLMGateway.__init__`.
2. **Added** a module-level `contextvars.ContextVar`:

   ```python
   _current_audit_attempt: contextvars.ContextVar[dict[str, Any] | None] = (
       contextvars.ContextVar("comqutor_week2_llm_current_audit_attempt", default=None)
   )
   ```

   Each logical call chain gets its own value via `.set()`/`.reset()`
   using a `Token`, never a shared mutable dict.
3. **`_set_pending_audit_attempt`/`_reset_pending_audit_attempt`/
   `_current_pending_audit_attempt`** now wrap `_current_audit_attempt.set(
   {...})` / `.reset(token)` / `.get()` directly -- no lock, no shared
   state, no `RuntimeError` on concurrent use, because there is no longer
   anything to collide on.
4. **The critical propagation fix, in `call_with_timeout`:** a bare
   `ThreadPoolExecutor.submit(function)` does **not** propagate the calling
   thread's context into the new worker thread -- each new OS/pool thread
   starts with its own default top-level `Context`, which would make
   `_persist_request_audit`/`_persist_response_audit` (invoked from
   *inside* `task_model.invoke(prompt)`, which runs inside this nested
   worker thread) see `_current_audit_attempt.get() -> None`, re-breaking
   the whole mechanism silently. Fixed by capturing and explicitly running
   inside the caller's own context:

   ```python
   def call_with_timeout(function, timeout_seconds):
       executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="comqutor-week2-llm")
       ctx = contextvars.copy_context()
       future = executor.submit(ctx.run, function)
       try:
           return future.result(timeout=max(float(timeout_seconds), 0.01))
       except FutureTimeoutError as exc:
           future.cancel()
           raise TimeoutError("Week 2 LLM call timed out") from exc
       finally:
           executor.shutdown(wait=False, cancel_futures=True)
   ```

   `copy_context()` snapshots the calling thread's context (including
   whatever `_set_pending_audit_attempt` just set) at submission time;
   `ctx.run(function)` makes the worker thread execute `function` *as if*
   it were still inside that context. A late-completing background call
   (timed out from the caller's perspective, but still running) keeps its
   own frozen copy of `ctx` regardless of what the outer thread does to
   `_current_audit_attempt` afterward (including resetting it, or setting
   a brand-new value for a newer attempt) -- this is the exact property
   that makes 五's late-response scenario safe.

**No forced-serial fallback survives this round.** The round-11 shim
(`concurrency_active = ... and int(concurrency) > 1` with an explicit
forced-1 override when audit was enabled) was **removed** from both
`alpha_mapper.map_structured_records` and
`structured_output_adapter.adapt_run_outputs` -- concurrency now runs at
its real configured value (default 4) with audit enabled, proven by every
test in 四 observing genuine overlap (`max_concurrent_observed > 1` /
explicit `threading.Barrier` synchronization), never serialized down to 1.

---

## 三. A second real bug found and fixed by this round's own testing

Running the first 4-way-concurrency test against the contextvar fix alone
(before the fix below) produced only 3 of 8 expected request-audit
records -- a real, separate data-loss bug, not a re-occurrence of the
identity defect. Root cause: `append_jsonl_record`
(`comqutor_alpha/storage/file_store.py`) is a real read-whole-file-then-
rewrite operation, not an atomic append:

```python
existing = path.read_text() if path.exists() else ""
atomic_write_text(path, existing + new_line)
```

Two genuinely concurrent callers both reading the same "existing" content
before either writes back race on the read-modify-write, and the loser's
line is silently dropped -- undetectable without literally counting
records (as 四's tests do). Fixed by wrapping both call sites in
`Week2LLMGateway`'s own `self._lock` (already used elsewhere in the class
for the call-budget counter):

```python
with self._lock:
    append_jsonl_record(self.run_id, PROVIDER_REQUEST_AUDIT_ARTIFACT_PATH, record, output_root=self.output_root)
```//
(and the equivalent for `PROVIDER_RESPONSE_AUDIT_ARTIFACT_PATH`). The lock
protects only the fast, local file write -- the real network wait
(`call_with_timeout`) happens entirely outside this method, so calls still
genuinely overlap; only the final disk write is serialized, which is
correct and necessary (the write itself is not meaningfully parallelizable
against the same file).

---

## 四. Test evidence (8 required scenarios)

Two test files, both going through `build_server_week2_llm_gateway`'s real
construction path (the real `tradingagents.llm_clients.create_llm_client`
factory, never monkeypatched) with only the bottom-most httpx transport
replaced by `httpx.MockTransport`. All synchronization is explicit
(`threading.Barrier`/controlled delays), never inferred from timing alone.

**`tests/test_alpha_classifier_audit_concurrency_fix.py`** (round 11/12,
updated this round) -- 4 tests, all passing:
- `test_default_model_is_audited`
- `test_real_concurrent_dispatch_no_longer_fails_with_contextvar_identity_fix`
  (renamed from the round-11 serial-forcing version; now asserts
  `max_concurrent_observed > 1`, proving genuine overlap, with zero
  failures and exactly 8/8 request + 8/8 response audit records)
- `test_alpha_classifier_override_client_is_audited`
- `test_content_support_override_client_is_still_audited_after_refactor`

**`tests/test_week2_llm_true_concurrent_audit.py`** (new this round) -- 8
tests, all passing, one per required scenario:

| # | Scenario | Test | Key proof |
|---|---|---|---|
| 1 | 4-way real overlap, out-of-order completion, correct identity | `test_four_way_real_overlap_out_of_order_completion_correct_identity` | `threading.Barrier(4)` forces simultaneous in-flight; delays reversed vs. submission order (completion order verified literally `== [D,C,B,A]`); every invocation's own `validated_output["claim_id"]` matches its own call; every response-audit record's attempt_id cross-checked against its own request-audit record's claim_ids and body content |
| 2 | Identical claim text, no identity confusion | `test_identical_claim_text_does_not_cause_identity_confusion` | two claims with byte-identical payload text, barrier-forced overlap; each gets a distinct real response (`arrival_order` 1 vs 2, never duplicated); audit `claim_ids` correctly attributes each by attempt_id, never by text match |
| 3 | Mixed task types share one gateway concurrently | `test_mixed_task_types_share_gateway_concurrently` | `alpha_classifier` + `content_support_verification` dispatched concurrently on the same `Week2LLMGateway` instance; barrier-forced overlap; no single-pending collision; both tasks independently audited |
| 4 | One HTTP error + one timeout + one success, independently resolved | `test_one_http_error_one_timeout_one_success_independently_resolved` | three concurrent calls, each gets its own correct terminal `provider_status` (`provider_error`/`timeout`/`success`); a brand-new call afterward still succeeds (nothing left stuck); all 4 real sends independently audited including the 500 response |
| 5 | Late response after timeout does not corrupt a newer request | `test_late_response_after_timeout_does_not_corrupt_next_request` | a slow call times out from the caller's side while its real background thread keeps running; a new, unrelated call is sent immediately after; the late real response is audited under its **own original** attempt_id, disjoint from the newer call's attempt_id; the already-recorded `timeout` business result is never retroactively changed |
| 6a | Request-audit-save-failure means zero send | `test_request_audit_save_failure_means_zero_send_and_blocks_future_calls` | injected `OSError` on the request-audit write; transport call count stays `0`; `gateway.audit_write_failed` becomes `True`; a second claim is also refused with zero additional send **and zero additional budget consumption** (checked before `_reserve_call` in the loop) |
| 6b | Response-audit-save-failure finalizes in-flight calls, blocks future ones | `test_response_audit_save_failure_finalizes_in_flight_calls_but_blocks_future` | two calls already genuinely in-flight (barrier-forced) when one's response-save fails; **both** still finalize with their real, correct `success` result (a response-save failure never un-does an already-received Provider answer); a third, new call afterward is refused with zero additional request-audit record |
| 7 | Hard call-cap and 0/0 retries under concurrency | `test_hard_call_cap_and_zero_retries_enforced_under_concurrency` | 10 concurrent calls, `max_calls=5`, `max_retries=0`, handler always returns 500; exactly 5 real sends ever reach the transport (never more); the 5 sent each get exactly 1 attempt (never a retry); the 5 refused get exactly 0 attempts; total attempts across all 10 = exactly 5 |
| 8 | Full recovery-script integration at real scale | see 五 below | separate script, not a pytest test (matches the round-12 recovery script's own existing `--fake-transport-test` convention) |

All 12 tests (4 + 8) pass together:

```
$ .venv/bin/python -m pytest tests/test_alpha_classifier_audit_concurrency_fix.py tests/test_week2_llm_true_concurrent_audit.py -v
...
12 passed in <15s (see raw log: round13_true_concurrent_audit_fix_20261006/pytest_scenario_tests.log)
```

---

## 五. Scenario 8: full-scale recovery integration test

`docs/audit_artifacts/.../round12_.../recover_alpha_classification.py`
gained a new function, `run_full_fake_transport_recovery(new_run_id, *,
simulate_crash_after_batches=None)`, scaling round 12's 30-claim
sequential-batch sample to the **real, full 973-claim** `needs_recovery`
set, with genuine `concurrency=4` (the real production default) inside
each 25-claim batch's own `map_structured_records` call -- not scaled-down
concurrency, not a smaller sample.

Driven by `run_full_recovery_scale_test.py` (this round's own directory),
in two phases against the SAME on-disk checkpoint:

- **Phase 1**: processes batches 1-3 (75 claims), then deliberately raises
  a `RuntimeError` ("simulated crash") to prove the checkpoint survives an
  abrupt stop.
- **Phase 2**: calls the same function again, same checkpoint file, no
  crash, running to full completion.

Real output (`full_recovery_scale_test_output.log`, full run captured):

```
needs_recovery_count (authoritative, from real alpha_matches.json): 973
valid_llm_results_count: 2
total_claims: 975
...
[OK] checkpoint reached all 973 needs-recovery claims
[OK] 955 real transport sends total (<= 973, the reduction being the semantic cache legitimately deduplicating real duplicate-content claims)
[OK] every one of 973 needs-recovery claims was submitted to map_structured_records EXACTLY ONCE total across both phases -- phase 2's own checkpoint-skip correctly excluded all 75 of phase 1's already-done claims
[OK] merged recovered (973) + already-valid (2) = 975 unique claim_ids, exactly matching the original run's 975
[OK] merged claim_id set is claim-for-claim identical to the original c904d4cc run's 975 claims -- zero omissions, zero extras
[OK] every recovered claim got alpha_match_method='llm' (no provider_error survived at full scale)

FULL-SCALE RECOVERY INTEGRATION TEST: PASSED
```

**On the 955-vs-973 real-send count** (reported transparently, not
smoothed over): `Week2LLMGateway`'s own semantic-call cache
(`InMemoryLLMResponseCache` via `SemanticRuntimeSession`) legitimately
serves a cache hit for genuinely duplicate `(claim, evidence, ticker,
factors, direction)` content instead of re-sending to the Provider --
confirmed by direct inspection that 16 of the 973 real claims are exact
duplicates of another claim in the same set (e.g. `"Do not initiate new
longs at $654.91."` appears verbatim 3 times). This is correct, intended
caching behavior, not a defect; the test asserts `total_sends <= 973`
(never more) rather than exact equality.

**On resume correctness specifically**: because real sends are reduced by
caching, and because each phase constructs a *fresh* cache instance (so
cache hits can't be used as a resume-correctness signal across the
simulated crash boundary), this round added an independent,
cache-insensitive log -- `batches_submitted.jsonl` -- recording exactly
which `claim_id`s were ever handed to `map_structured_records`, written
before each batch call regardless of what the cache or transport do
afterward. The test's authoritative resume-correctness assertion is built
from this log: every one of the 973 claims appears in **exactly one**
submitted batch total, across both phases -- proving phase 2's own
checkpoint-skip (`if r["claim_id"] not in checkpoint["completed_claim_ids"]`)
correctly excluded all 75 of phase 1's already-done claims, under genuine
concurrency, not just in a sequential small sample.

---

## 六. A real, pre-existing traceability gap found (not a regression, not fixed this round)

While building 五's verification, the real request-audit JSONL for
`alpha_classifier` was found to always carry `"claim_ids": []`. Root cause:
`alpha_mapper._classify_alpha_with_llm` builds the LLM-facing payload as

```python
request = {
    "claim": ..., "evidence": ..., "ticker": ..., "factors": ...,
    "direction": ..., "alpha_taxonomy": ...,
}
```

-- no `"claim_id"` or `"items"` key, which is exactly what
`Week2LLMGateway._extract_claim_ids(payload)` looks for
(`payload.get("items")` then `payload.get("claim_id")`). This is **not** a
regression from this round's contextvar fix -- per-attempt `attempt_id`
identity is completely unaffected and still provably unique and correctly
bound (see 四, scenario 1's attempt_id cross-checks) -- but it is a real,
pre-existing gap in this one task's own audit-log forensic readability: an
auditor reading `week2_llm_provider_request_audit.jsonl` cannot tell which
claim_id an `alpha_classifier` request was for directly from that field
(they would have to correlate by timestamp/ordinal against
`llm_semantic_calls.jsonl` instead, which does carry the real claim
identity via `SemanticRuntimeSession`). This affects every real run,
including the original `c904d4cc`, not something this round introduced.
**Not fixed this round** (would mean changing the LLM-facing payload
shape, out of this round's explicit no-model/prompt-change boundary) --
flagged here for a future round's own decision on whether and how to add
claim identity to the audit record without changing what the model itself
receives.

---

## 七. Regression suite

Command (identical to round 12's, re-run fresh against this round's own
code -- the prior background run from before this round's contextvar/lock
changes is stale and is not cited as evidence for this round):

```
.venv/bin/python -m pytest tests/ -q --ignore=tests/test_live_launcher_database_isolation.py \
  -k "not live and not fresh_run and not nvda_fresh and not qqq" \
  --deselect tests/structured_output_shadow/test_phase1b1_boundaries.py::test_existing_three_task_instructions_text_unchanged
```

Result: **`40 failed, 4637 passed, 18 skipped, 187 deselected, 17 warnings,
3 errors, 69 subtests passed in 2784.10s (0:46:24)`, `EXIT_CODE=1`.**

This is far more than the 3 known pre-existing failures on record. Rather
than citing that stale number, every one of the 40 failures + 3 errors was
traced to a root cause this round, either by reading its assertion detail
or by re-running it in isolation (to separate a real, deterministic defect
from full-suite-only noise). Full raw evidence:
`regression_full_run_fresh.log` (the complete run) plus three isolation
reruns captured during this investigation (`pytest_isolation_*` not
separately filed -- their output is quoted below verbatim from the real
runs).

**Category A -- directly, deterministically caused by this round's own
authorized file changes (reproduced in isolation, not flaky):**

A frozen-hash governance mechanism (`_STEP8_FROZEN_HASHES` and equivalent
lists in several test files) asserts specific production files are
byte-identical to a previously "approved" baseline. This round's own
central deliverable -- the contextvar redesign in `week2_llm.py` and the
shim removal in `alpha_mapper.py` -- changes both files' content, which is
exactly what the user's own round 11-13 instructions required. This trips
every test that includes either file in its frozen set:

- `tests/test_evidence_review_v2.py::test_case17_production_semantic_modules_remain_untouched[comqutor_alpha/structure_engine/alpha_mapper.py]`
- `tests/test_high_value_unclassified_recovery.py::test_case10_production_semantic_artifacts_are_not_modified`
- `tests/test_step10_final_e2e_qa.py::test_production_semantic_files_unchanged_during_step10`
- `tests/test_step11_provider_health_rerun.py::test_production_semantic_files_unchanged_during_step11`
- `tests/structured_output_shadow/test_source_integrity.py::test_current_semantic_components_match_approved_phase1_master_baseline` (flags **both** `week2_llm.py` and `alpha_mapper.py`)
- `tests/test_msft_a102_a304_taxonomy_adjudication.py::TestSectionAAllOutcomes::test_a6_b1_b2_b3_b4_invariant_modules_are_byte_identical`
- `tests/test_j3_semantic_benchmark_j2_v0_2.py::TestSectionEInvariants::test_e42_head_unchanged_from_session_frozen_starting_commit`

All re-confirmed in isolation (`test_step10_final_e2e_qa.py`/
`test_step11_provider_health_rerun.py` run alone: `2 failed, 112 passed`,
both failures the identical `alpha_mapper.py hash changed` assertion).
**This is an expected, authorized consequence of this round's own fix, not
a defect** -- but it means the frozen baseline needs a deliberate
re-certification decision (whoever owns that "approved" sign-off), which
is not mine to make unilaterally. Flagged here rather than silently
updated.

**Category B -- pre-existing, caused by OTHER uncommitted work earlier in
this long session, unrelated to week2_llm.py/alpha_mapper.py (confirmed
deterministic in isolation):**

The same frozen-hash tests above also flag `alpha_taxonomy_v1.yaml`,
`conflict_detector.py`, `activation_scorer_v2.py`, and
`evidence_stance_llm.py` -- none touched by this round -- meaning these
were already diverged from the frozen baseline before round 13 began.
Separately, re-running in isolation (`pytest tests/test_evidence_review_v2.py
tests/test_evidence_review_v2_directional_eligibility.py
tests/test_evidence_review_sample.py tests/test_b2_admissibility_integration.py
tests/test_high_value_unclassified_recovery.py`) reproduced
**`24 failed, 43 passed, 3 errors`** deterministically -- a cluster of
`KeyError: 'raw_h5_metrics'` / `'critical_reversal_adjudication'` /
`'alpha_accuracy_threshold_percent'` etc., all pointing at a stale/
schema-incompatible on-disk evidence-review-summary artifact, entirely
unrelated to Week2LLMGateway or Alpha classification. Also in this
category: `test_v0_1_3_offline_replay_proof.py` (touches
`conflict_detector.py`, not round 13's), `test_w5_demo_seed.py` (both
sub-tests), `structured_output_shadow/test_shadow_provider_smoke_cli.py`,
and `test_structured_adapter_concurrency.py::test_structured_adapter_concurrency_touches_no_alpha_mapping_code`
-- this last one's own failure body shows the offending text is a
**2026-10-06 "Round 9"-dated comment** already in `structured_output_
adapter.py` before this round began (`# mirrors alpha_mapper's own
"map_structured_records ...`), not something round 13 added.

**Category C -- pre-existing test flakiness, confirmed via repeated
isolated runs (inherent race in the test's own synchronization design, not
a round-13 regression):**

`tests/test_week2_llm.py::test_concurrent_success_timeout_and_retry_all_preserve_their_own_attempts`
failed once in 5 repeated isolated runs (4 passed, 1 failed with
`assert by_which[3]["persist_sequence"] < by_which[1]["persist_sequence"]`
→ `assert 1 < 0`). Reading the test: it synchronizes call 1 and call 3 via
a `threading.Event` set **inside** call 3's own `model.invoke()|`, before
call 3's own outer `gateway.invoke_json()` has done its own post-processing
and persisted its record -- so call 1 can legitimately race ahead and
persist first even though call 3's model call returned first. This is a
latent race in the test's own design (present regardless of contextvars),
not a correctness defect in the Gateway's real attempt/persist logic.

**Category D -- full-suite-only, disappear entirely when run in isolation
(pre-existing test-isolation fragility at full-suite scale, not reproduced
as a round-13 code defect):**

- `tests/test_week1a_gate.py::test_run_research_request_with_offline_raw_outputs` -- isolated: `17 passed`
- `tests/test_week4_pipeline_api.py::test_pipeline_happy_path_completes_week1_through_4` -- isolated: `18 passed`
- `tests/test_w5_1b_api.py` (3 sub-failures) -- isolated: `19 passed`

None of these tests' own assertions touch `week2_llm.py`/`alpha_mapper.py`
hashes or logic directly, and every one of this round's three functional
changes (contextvar identity, the audit-JSONL lock, the shim removal) is
gated behind `enable_request_response_audit`/`COMQUTOR_WEEK2_LLM_ENABLED`,
which these particular offline/non-audit tests do not turn on -- tracing
the code confirms none of this round's changes can affect their behavior.
Reported as full-suite-scale flakiness (consistent with running 4637+
tests in one long-lived process over 46 minutes), not claimed as
definitively pre-dating round 13 with a byte-for-byte historical
comparison, since no pre-round-13 baseline run was preserved to diff
against directly.

**Net assessment**: this round's own diff is responsible for Category A
(expected, authorized, needs a frozen-baseline decision) and contributes
nothing new to Categories B/C/D on the evidence gathered. No test failure
in any category represents a classification result flipping to an invalid
NONE/SUPPORTS/Alpha match, a hidden `provider_error`, or a budget overrun
-- the 12 tests in 四 and the full-scale integration test in 五 remain the
authoritative evidence for this round's own correctness claim.

---

## 八. Original run integrity (hash-reverified)

Re-verified this round, not merely cited from round 11:

| File | SHA-256 | Matches round-11 manifest |
|---|---|---|
| `alpha_matches.json` | `cf13bca611c6f055e680697c21d1013932d71430babe0498f8ad421663ad7e87` | yes |
| `structured_agent_outputs.json` | `dbec9de64039ad82397fd60cf626b747b58ba0c2c02fbeb105acba204486f110` | yes |
| `source_registry.json` | `3c98de5ac569a536ce6e1d4a25cd75aca0702b7e60ba4fd531629f7f24c3c589` | yes |

Zero real Provider or search calls were made this round (every test and
recovery-scale run above uses `httpx.MockTransport`/`_base_transport_for_
testing`, never the real network). No Fresh Run was started. No real
`--execute` recovery was run (still hard-blocked in the script).

---

## 九. Completion against the round's own stated criterion

> 真实并行分类不会再因为审计身份共享而失败；异常能定位、结果不串位、预算
> 不超发。不能以关闭审计、强制串行或隐藏provider_error替代这个证明。

- **真实并行分类不会再因为审计身份共享而失败** -- 四/scenario 1-3 and 五
  all run at genuine `concurrency=4`/real overlap with zero
  `WEEK2_LLM_AUDIT_CONCURRENT_ATTEMPT` failures, including at the real
  973-claim scale.
- **异常能定位** -- 四/scenario 4, 5, 6a, 6b each independently verify that
  a real HTTP error, a real timeout, a late background response, and both
  audit-save-failure modes are each correctly distinguished in
  `provider_status`/`error_code`, never collapsed into one bucket.
- **结果不串位** -- 四/scenario 1's explicit out-of-order-completion +
  per-attempt cross-check, and scenario 2's identical-text non-collision,
  directly prove this; 五's full-scale run shows zero claim-identity
  corruption across 973 real (fake-transport) classifications.
- **预算不超发** -- 四/scenario 7 proves the hard call-cap and 0/0-retry
  enforcement hold exactly under concurrency; 六a confirms a refused claim
  never consumes budget.
- **不能以关闭审计、强制串行或隐藏provider_error替代** -- audit stays on
  in every test; the round-11 forced-serial shim is **removed**, not kept
  as a fallback; `provider_error` is never renamed/hidden -- scenario 4
  explicitly asserts `provider_status == "provider_error"` for the real
  HTTP-failure case, and 六 reports a found gap transparently rather than
  concealing it.
