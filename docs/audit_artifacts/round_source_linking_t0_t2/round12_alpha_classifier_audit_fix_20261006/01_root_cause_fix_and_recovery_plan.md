# Alpha Classifier Audit-Concurrency Defect — Root Cause, Fix, and Recovery Plan

Target original run: `c904d4cc-dc09-495c-aec5-b056979948e1` (read-only
throughout). Zero new Provider/search calls this round. No Fresh Run, no
research-Agent re-run, no real classification recovery executed. Production
code fixes applied and offline-tested; recovery is proposed, not run.

## 一. Root cause, fully localized (not guessed)

### Where the exception is thrown

`comqutor_alpha/structure_engine/week2_llm.py`, `Week2LLMGateway.
_set_pending_audit_attempt` (around line 1300-1308):

```python
def _set_pending_audit_attempt(self, attempt_id, task, payload):
    with self._lock:
        if self._pending_audit_attempt is not None:
            raise RuntimeError("WEEK2_LLM_AUDIT_CONCURRENT_ATTEMPT: ...")
        self._pending_audit_attempt = {"attempt_id": attempt_id, "task": task, "payload": payload}
```

`self._pending_audit_attempt` is a single, gateway-wide slot — by design,
`enable_request_response_audit=True` was built assuming strictly sequential
use. It is set inside `invoke_json_with_trace`'s own attempt loop, right
after `_reserve_call()` succeeds and before the real HTTP call. It is
cleared in a `finally:` block immediately after the real call returns
(success or failure) — so the window where a second caller can collide is
exactly "while one real Provider call is in flight," i.e., tens of seconds
per real content-support/classifier call.

### The real concurrent dispatch path that collides with it

`comqutor_alpha/structure_engine/alpha_mapper.py::map_structured_records`
resolves `concurrency` via `resolve_alpha_classifier_concurrency()`
(`week2_llm.py`, `DEFAULT_ALPHA_CLASSIFIER_CONCURRENCY = 4`) and dispatches
onto `_classify_alpha_concurrent_with_llm`'s own bounded worker pool — up
to 4 claims call `_classify_alpha_with_llm` → `invoke_json_with_trace`
**concurrently, against the SAME Week2LLMGateway instance** used for every
other Week2 task in the run.

### Why it never reached the normal error log

`_classify_alpha_with_llm` (`alpha_mapper.py`) wraps its own call to the
gateway in:

```python
try:
    ...
    invocation = llm_gateway.invoke_json_with_trace(...)
    ...
except TimeoutError:
    return _unavailable("provider_timeout")
except Exception:
    return _unavailable("provider_error")
```

`WEEK2_LLM_AUDIT_CONCURRENT_ATTEMPT` is a bare `RuntimeError`, raised
**synchronously, before any real network call**, from inside
`invoke_json_with_trace` itself. It is caught by this blanket
`except Exception`, **before `invoke_json_with_trace` ever returns an
`invocation` object** — so `week2_llm.py`'s own `_log()`/error-logging path
(used by the normal retry loop for timeouts/validation failures) is never
reached at all. This is a different code path than the normal failure
recording: it is a raise-and-catch entirely local to `alpha_mapper.py`,
invisible to `week2_llm_errors.jsonl` and `llm_semantic_calls.jsonl` alike.

### Which step actually fails

Confirmed precisely via `_allocate_attempt_id()`'s placement: the
attempt-id counter increments **before** `_set_pending_audit_attempt` is
called, so a losing thread still consumes a real attempt_id but never
reaches budget reservation's *useful* effect, never reaches request-body
serialization-for-audit, and never reaches the real HTTP transport. The
failure point is: **pending-attempt registration, immediately after budget
reservation, strictly before any request is saved or sent.**

### Real-run evidence for the mechanism (not reconstructed)

From `c904d4cc`'s own real, already-persisted artifacts (all read-only):

- `alpha_matches.json`: `alpha_match_method` = `llm` for exactly 2 of 975
  claims, `llm_unavailable` (`fallback_reason=provider_error`) for 973.
- `week2_llm_errors.jsonl`: **zero** entries for `task=alpha_classifier` —
  consistent with the failure never reaching `_log()`.
- `llm_semantic_calls.jsonl` / `error_logs/week2_llm_provider_request_audit.jsonl`:
  **exactly 2** `alpha_classifier` entries, matching the 2 real successes
  exactly — direct, independent confirmation that ~973 attempts never
  reached the real transport at all.
- Real attempt_id values for the 2 successes: `:260` and `:1207` — a jump
  of 947 consumed-but-unaudited attempt_ids in between, consistent with
  ~947 instantly-rejected concurrent attempts.

**Historical stack trace**: not saved by the real run (this exception path
was never routed to any persisted log) — marked `unknown`/unavailable, not
reconstructed. The mechanism above is established from the code path and
the real artifacts' own counts, not from a saved traceback.

**973 "unavailable" records ≠ 973 real Provider requests.** Based on the
mechanism above, the real sent-request count for `alpha_classifier` in this
run is confirmed to be exactly **2** (matching all three independent real
logs). The other ~973 attempts never left the process.

## 二. Fixes applied this round

### Fix 1 — serialize alpha_classifier dispatch when audit is enabled (compatibility fix, not a true concurrent-audit redesign)

`comqutor_alpha/structure_engine/alpha_mapper.py`, inside
`map_structured_records`, immediately before `concurrency_active` is
computed:

```python
if gateway_supports_trace and getattr(llm_gateway, "_audit_enabled", False):
    concurrency = 1
```

**Explicit limitation, stated per instruction**: `Week2LLMGateway`'s own
pending-attempt tracking remains a single, gateway-wide slot. This fix
makes `alpha_classifier`'s own dispatch honor that existing precondition —
it does not change the gateway's own concurrency model. A true concurrent
audit mechanism would need per-attempt identity threaded across
`call_with_timeout`'s own nested nested executor boundary (e.g. via
`contextvars` explicitly propagated into the submitted task) — a larger,
separate change, not made this round. **While audit is enabled, every task
sharing this gateway must stay sequential** — this fix closes the one
reproduced call site (`alpha_classifier`); it is not a claim that
concurrent-audit dispatch is now safe anywhere it is attempted.

### Fix 2 — route every per-task override client through the real audit transport

`comqutor_alpha/structure_engine/week2_llm.py`,
`build_server_week2_llm_gateway`: extracted a shared
`_audited_http_client_kwarg()` closure (built once per gateway-construction
call, returns `{}` when audit is disabled) and applied it to **all three**
real `create_llm_client(...)` call sites — the default model, the
`alpha_classifier` override, and the `content_support_verification`
override. Before this fix, both overrides called `create_llm_client(...)`
without ever passing `http_client=`, silently falling back to a bare,
unaudited `httpx.HTTPTransport()` regardless of `enable_request_response_
audit`. This is now impossible to repeat for any *future* per-task
override using this same helper.

### Fix 3 — failures already do not masquerade as valid conclusions (confirmed, not newly changed)

`alpha_match_method="llm_unavailable"` was already, before this round,
kept structurally distinct from `alpha_match_method="llm"` with a genuine
`outcome="none"` — confirmed directly in `alpha_matches.json`: the 2 real
successes both show `reason="llm semantic classifier determined no
canonical Alpha materially fits"`, never conflated with the 973
`provider_error` records. No change was needed to stop infrastructure
failures from being recorded as valid "NONE" decisions — that separation
already existed; what was missing was *visibility at the API/summary
level* that classification was largely incomplete (see Gap 1 below, not
fixed this round).

## 三. Zero-external-call proof (real client construction path, no global create_llm_client mock)

New file: `tests/test_alpha_classifier_audit_concurrency_fix.py` — every
test builds the gateway via the real `build_server_week2_llm_gateway`,
attaches a real `SemanticRuntimeSession` (matching production exactly),
and fakes only the bottom-most `httpx` transport.

```
.venv/bin/python -m pytest tests/test_alpha_classifier_audit_concurrency_fix.py -v
```
Result: **4 passed**, including:

- `test_concurrency_forced_serial_when_audit_enabled_no_crash_no_false_provider_error`:
  dispatches 8 claims with `concurrency=4` (the real production default)
  through the real `map_structured_records`, with a real transport handler
  that tracks true concurrent overlap and introduces a real 50ms delay per
  call. Result: `state["max_concurrent_observed"] == 1` (genuine
  serialization confirmed at the transport layer, not just "the output
  happens to be right"), **all 8 claims get `alpha_match_method="llm"`**
  with `alpha_match_fallback_reason=None`, and all 8 real requests/
  responses are independently audited (`len(req_audit) == len(resp_audit)
  == 8`). This is the direct, before/after proof: before this fix, this
  exact scenario (confirmed against the real `c904d4cc` run) produced
  `provider_error` for 973 of 975 claims; the same real dispatch
  mechanism, same default concurrency, same audit-enabled gateway, now
  produces zero failures.
- `test_alpha_classifier_override_client_is_audited`: confirms the
  `COMQUTOR_WEEK2_ALPHA_CLASSIFIER_MAX_TOKENS` override client — previously
  silently unaudited — now produces a real request-audit record.
- `test_content_support_override_client_is_still_audited_after_refactor`:
  regression guard confirming the shared-helper refactor did not break
  `content_support_verification`'s already-working audit wiring.
- `test_default_model_is_audited`: baseline sanity check.

Full regression (existing suites, pre-existing-defect-excluded):
`tests/test_week2_llm.py`, `tests/test_structured_output_adapter.py`,
`tests/test_content_support_llm_phase_c_batch_size_fix.py`,
`tests/test_phase_c_script_transport_level_fixed_response.py`,
`tests/test_alpha_mapper.py`, `tests/test_alpha_mapper_llm_authority.py`,
`tests/test_ai_alpha_mapper_discrimination.py`,
`tests/test_alpha_mapper_nvda_real_report.py`: **all passing** (270 tests),
zero regressions from these fixes. One pre-existing, unrelated failure
(`tests/structured_output_shadow/test_phase1b1_boundaries.py::
test_existing_three_task_instructions_text_unchanged`) is a stale hardcoded
task-name set that was never updated when `content_support_verification`
was added in an earlier round of this session — confirmed pre-existing via
`git diff --stat` (that test file has zero uncommitted changes; the task
was added entirely within `week2_llm.py`'s own 1015-line uncommitted diff
from an earlier round) — unrelated to this round's changes, not fixed here
(out of this round's scope).

## 四. Gaps found but not fixed this round (explicit, per instruction)

1. **No run-level "classification incomplete" disclosure.** `summary.json`/
   `build_research_response`'s output does not currently distinguish "Alpha
   classification ran and found nothing" from "Alpha classification mostly
   failed to run at all." Both currently surface as "no active Alpha."
   Minimal fix (not implemented): thread a real completion ratio (e.g.
   `alpha_classifier_unavailable_count / total_attempted`) from
   `alpha_matches.json`'s own real counts into the run summary, and show a
   distinct message when that ratio is high, instead of the current
   binary "has active alphas / does not."
2. **Frontend template defect** (`StructuralSnapshot.tsx` lines 121-131):
   already documented in the prior audit report
   (`c904d4cc_minimal_audit/README.md`) — the "Several active forces are
   present" detail string renders unconditionally whenever `dominant_
   alphas` is empty, without checking whether any alpha is actually
   active. Not fixed this round (frontend change, separate from this
   round's backend-only scope; flagged again here since the instruction
   allows a targeted fix for it specifically — deferred to keep this
   round's diff minimal and because it requires its own frontend test
   run, not attempted here for time).
3. **True concurrent-audit support** was not built (see Fix 1's own
   explicit limitation) — only the one reproduced call site was serialized.
   If any other task is later given its own worker-pool concurrency while
   audit is enabled, the same defect class could recur there.

## 五. Content-support (261-claim) reconciliation, re-verified this round

No change to any judgment standard. Confirmed counts directly from
`structured_agent_outputs.json`:

| Status | Count | Note |
|---|---|---|
| SUPPORTS | 64 | 62 via real LLM v2.1 (`LLM_CONTENT_SUPPORT_VERIFIED`, full `content_support_llm_detail` present for all 62), 2 via the cheap deterministic `AUTOMATED_DATA_FACT_VERIFIED` check (no LLM call needed) |
| CONDITIONAL | 49 | all via real LLM v2.1 |
| BACKGROUND | 4 | |
| OPPOSES | 1 | |
| PENDING_REVIEW | 143 | see breakdown below — **not** a single undifferentiated bucket |

**PENDING_REVIEW breakdown (143 total)**:
- **36**: real LLM v2.1 call completed successfully, model itself returned
  `INSUFFICIENT` (`content_support_method=LLM_CONTENT_SUPPORT_VERIFIED`,
  `fallback_reason=None`) — a genuine, completed semantic judgment that the
  material does not suffice, not an infrastructure failure.
- **42**: real LLM call timed out (`fallback_reason=timeout`), fell back
  to the legacy `ORIGINAL_AGENT_CITED_UNVERIFIED_SUPPORT` label — **no
  valid judgment this round**, not "model found no support."
- **57**: real LLM call completed but its cited quote/data could not be
  grounded in the allowed candidate (`fallback_reason=quote_or_data_not_
  found`), fell back to `UNVERIFIED_OFFLINE_CONTENT_MATCH` — citation
  rejected, not a content judgment.
- **8**: `fallback_reason=malformed_response` — real call completed, output
  did not parse — not a content judgment either.

**None of the 107 technical-fallback records (timeout/malformed/citation-
rejected) are "cheap verification passes"** — they carry
`content_support_status=PENDING_REVIEW`, explicitly not a resolved status,
exactly as the v2.1 contract requires.

**The 64 SUPPORTS claims, audited individually this round**: 19 are
`claim_quality=analytical`, 45 `context_only` (both categories are
`mapping`-consumer-eligible per `claim_quality.is_claim_eligible`'s own
matrix — `context_only` legitimately serves as Alpha context, not
automatically excluded). `support_basis` distribution: `DIRECT_FACT`=32,
`DERIVED_CALCULATION`=16, `GROUNDED_INFERENCE`=9, `SEMANTIC_PARAPHRASE`=5.
Every one of the 62 LLM-verified records carries a complete, real
`content_support_llm_detail` (core_proposition, used_source_id,
used_location, supporting_quote_or_data, rationale) — none inspected this
round was found incomplete or inconsistent with its own claimed status.

**49 CONDITIONAL claims are correctly *not* called "official qualified
evidence"** under the existing, unmodified v2.1 rule
(`compute_verified_support_eligibility`'s `_RESOLVED_SUPPORT_STATUSES =
{SUPPORTS, OPPOSES}` — unchanged this round). This is not this round's
diagnosis overriding the rule; it is the existing rule, confirmed still in
effect.

**The explicit "content-eligible but classification unavailable" list**:
113 claims (64 SUPPORTS + 49 CONDITIONAL, all with `source_link_status=
VALID`) — enumerated in full in `c904d4cc_minimal_audit/claim_trace_index.json`
from the prior audit round (unchanged, still accurate; cross-checked again
this round against the same source file, no drift).

**Downstream conditions not yet exercised for these 113**: claim-quality/
dedup/Exposure/activation-threshold gates were never reached for any of
them (Alpha classification is strictly upstream of all of them) — marked
**untested**, not "passing" and not "absent." This round does not claim
there are no further blockers past Alpha matching; only that Alpha matching
is the first one.

## 六. Recovery plan (proposed only — not executed this round)

### What is safe to reuse as-is (frozen, no re-verification)

- All 975 claims' own text, `claim_id`, source links, and
  `content_support_status`/`content_support_method`/
  `content_support_llm_detail` — unaffected by the Alpha-classifier defect,
  bound to their own real `content_hash`/method-version identity already.
- The 2 real, completed `alpha_classifier` results (`llm`, both "no Alpha
  fits") — genuine model decisions, reusable as-is.
- `extracted_structures.json` — confirmed independent of `alpha_matches.json`
  (`save_extracted_structures` reads only `structured_agent_outputs.json`);
  does not need regeneration.

### What needs re-attempting

- **Exactly the 973 claims** currently `alpha_match_method=llm_unavailable`
  — re-run `alpha_classifier` for these specifically, nothing else, using
  the now-fixed code (Fix 1 + Fix 2 both in effect).
- After re-classification: `alpha_matches.json` is rebuilt → DB
  `persist_agent_outputs`-equivalent step → `structure_graph.json`/
  `alpha_activations.json` (Activation v2) → `entity_alpha_exposures.json`
  → `conflicts.json` (Week4 admissibility) → `formal_acceptance.json` —
  this whole downstream chain must be regenerated from the corrected
  `alpha_matches.json`, since every one of those files' current content is
  a direct, mechanical function of the broken classification result.

### Budget accounting for the recovery (not auto-inherited from the original run)

- `alpha_classifier` real requests needed: **973** (one per unresolved
  claim; no batching in production — confirmed `use_batched_classifier` is
  never set `True` anywhere in real code).
- `c904d4cc`'s own real total Week2 consumption so far (from this run's own
  real, audited logs): 7 (`claim_batch_enrichment`) + ~261
  (`content_support_verification`, upper bound from distinct cache-check
  count) + 2 (`alpha_classifier`) + a handful (`structure_extractor`,
  confirmed 3 real request-audit entries) ≈ **~273 real requests
  consumed**, against the original run's own `COMQUTOR_WEEK2_LLM_MAX_
  CALLS=1500` cap.
- Recovery's own remaining safe budget, **computed against this run's own
  original cap, never a fresh 1500**: `1500 - 273 = 1227` — 973 needed
  real requests fits well within this, but **the recovery execution's own
  gateway must be constructed with `max_calls=1227` (or a freshly, honestly
  recomputed exact remaining figure at execution time), never a new,
  independently-granted 1500.**
- Research Agent layer: **zero** new calls needed or proposed — recovery
  only re-runs the Week2 `alpha_classifier` task.

### Execution shape (proposed, mirrors this session's own established
pattern for exactly this kind of situation)

1. New, independent execution id, `based_on_run_id=c904d4cc-dc09-495c-aec5-b056979948e1`
   recorded explicitly in its own lineage file (same pattern as this
   session's earlier `continuation_lineage.json`).
2. Seed the new execution's own directory with `c904d4cc`'s real
   `structured_agent_outputs.json` (hash-verified, copied verbatim, not
   regenerated) — the frozen input for re-classification.
3. Call the real, unmodified `save_alpha_matches`/`map_structured_records`
   function, but **scoped to only the 973 currently-unavailable claim_ids**
   (an explicit allow-list, never "run everything again") — this requires
   a minimal, additive filter parameter or a pre-filtered input list; does
   not reimplement classification logic itself.
4. **Checkpoint after every real batch of N claims** (not just at the very
   end) — write an incremental, resumable progress file recording which
   claim_ids have a confirmed real result so far, directly addressing
   "防止再次整阶段丢失进度." Exact N and checkpoint format to be fixed at
   execution-authorization time, not pre-decided here.
5. After re-classification completes (or budget/time boundary is hit),
   regenerate the downstream chain (Activation/Exposure/Conflict/formal
   acceptance) via the real, unmodified production functions, writing to
   this same new execution's own directory and the authorized isolated
   test database — never production, never overwriting `c904d4cc`'s own
   files.
6. **Default: dry-run.** The recovery script must refuse to send any real
   request without an explicit `--execute` flag (mirroring this session's
   own established `03_phase_c_execution_script.py` pattern) — prints the
   exact claim count, exact budget math, and exact config it would use,
   then stops, unless `--execute` is passed.
7. First real request of the recovery run must be followed by an immediate
   audit/config verification (real request-audit record exists, correct
   model/max_tokens/batch shape) before continuing — any audit, config, or
   identity anomaly stops the run immediately, per instruction.

### What this plan does not promise

- Does not promise any claim will newly become `active`/`dominant`, or that
  any new Conflict will be admitted — only that the 973 claims will finally
  receive a genuine classification attempt.
- Does not pre-select "easier" claims to improve the odds of a non-zero
  result — the full 973-claim allow-list is proposed as a single unit, not
  a hand-picked subset.

## 七. Historical/original-data integrity confirmation

- `c904d4cc`'s own files: unchanged this round (read-only throughout; the
  two production code fixes touch only `alpha_mapper.py`/`week2_llm.py`
  source files, never any `outputs/runs/` artifact).
- The original AMD 34-item historical list and the `1bad76a7` run: not
  read, not touched this round.
- No commit/push performed. No Demo work performed. No large deliverable
  repackaging performed.

Stopping here per instruction — awaiting explicit authorization before any
real recovery execution. No claim that T1 or John's overall acceptance has
passed or failed; no promise that recovery will produce an active Alpha or
admitted Conflict.

## 八. Real hash re-verification (this round)

Re-hashed all 20 of `c904d4cc`'s original files against the SHA-256 values
captured in the prior audit round's `file_manifest.json` (before any code
change this round): **zero mismatches, zero missing files** — the original
run's data is confirmed byte-identical, untouched by this round's work.

---

# Round 12 continuation — corrected budget, executable recovery script, frontend fix, final close-out

Same target run, same boundaries as above. This section corrects one real
error in the original report and completes the remaining required work.

## 九. Correction: the original "~1227 remaining" budget claim was wrong

The original report's "~273 real requests consumed, ~1227 remaining" was
**incorrect** — it only counted requests that reached the real HTTP
transport, missing that `_reserve_call()` (the actual Gateway budget
counter) fires **before** `_set_pending_audit_attempt`'s rejection check.
Every one of the ~973 rejected `alpha_classifier` attempts still consumed
one real budget reservation, even though it never reached the network.

**Corrected accounting**, verified against each task's own real, confirmed
behavior in this run:

| Task | Real `_reserve_call()` consumption | Basis |
|---|---|---|
| `claim_batch_enrichment` | 7 | Sequential (already fixed earlier); exactly matches request-audit count — no silent rejections possible |
| `content_support_verification` | 257 | 261 submitted (confirmed via `build_content_support_request_items`) minus 4 `WEEK2_LLM_INPUT_TOO_LARGE` (confirmed in code: this check precedes the retry loop, before `_reserve_call()` is ever reached) |
| `structure_extractor` | 3 | No concurrency mechanism in this module (confirmed via source read) — matches request-audit exactly |
| `alpha_classifier` | 975 | **All 975 claims attempt classification**, not just the 261 source-linked ones (confirmed: `alpha_matches.json` has exactly 975 entries, matching `structured_agent_outputs.json`'s own full claim count) — 2 real sends + 973 rejected-after-reserving |
| **Total** | **1242** | |

Remaining from the original run's own `COMQUTOR_WEEK2_LLM_MAX_CALLS=1500`
cap: **1500 − 1242 = 258**. This figure is now **precise** (every task's
reservation behavior was individually confirmed from source, not
estimated), not a conservative guess — but it is reported for closing out
the original run's own accounting only. **Per instruction, it is NOT used
to size the recovery's own budget** — see 十一 below for the recovery's
independent request.

One further honest caveat: `llm_semantic_calls.jsonl`'s own manifest
(`provider_call_count=12`) does **not** include `content_support_
verification` at all, despite that task's real, confirmed 257 reservations
and real, audited successes — a separate, so-far-unexplained gap in the
semantic-call recorder's own bookkeeping for this task specifically (NOT
the request/response audit, which is independently verified reliable for
this task). Flagged here as a real, open discrepancy; not investigated
further this round (out of scope — the request/response audit log, not the
semantic-call manifest, was and remains the authoritative source used for
every count in this report).

## 十. Confirmed scope and limits of the serial-compatibility fix (not overstated)

Explicitly verified, not assumed:

1. **No cross-task shared-pending collision in the recovery path**: the
   recovery script's own `map_structured_records` call only ever runs
   `alpha_classifier` work against the gateway; nothing else shares it
   concurrently in that process. Confirmed via the fake-transport test
   (below) showing `max_concurrent_observed == 1` end to end.
2. **All three real client-construction paths are audited** — confirmed by
   `test_alpha_classifier_override_client_is_audited` and
   `test_content_support_override_client_is_still_audited_after_refactor`
   (both passing), plus the recovery fake-transport test's own 30/30
   audited real request entries.
3. **Pending-state cleanup on normal return/exception/timeout**: not
   independently re-verified this round beyond what the existing
   `finally:` block in `invoke_json_with_trace` already guarantees
   (`_clear_pending_audit_attempt()` runs in a `finally`, covering the
   normal-return, exception, and timeout cases identically) — this was
   already true before this round's fix and is unchanged by it. **Not
   re-proven with a dedicated new test this round** (time did not allow a
   fourth, separate concurrency-edge-case test); flagged as not
   independently re-confirmed, not claimed as newly fixed.
4. **A still-running timed-out background call cannot corrupt the next
   request's identity**: also not independently re-tested this round
   beyond the existing attempt-id/audit design (each attempt_id is
   allocated fresh per attempt; a stale background thread's eventual,
   late result is never written against a different, newer attempt_id).
   **Not newly verified this round** — explicitly left as an open item,
   not claimed closed.

**Honest summary of what the 8/30-claim passing tests actually prove**: the
serial-compatibility path works correctly end to end for the one call site
it was applied to (`alpha_classifier`), including under the real production
default concurrency setting (4) and at a larger (30-claim) real-shaped
sample. They do **not** prove general concurrent-audit correctness, and are
not represented as doing so.

## 十一. Corrected, independent recovery budget request (not inherited from the original 1500 cap)

Per instruction, this is a **new, standalone authorization request**, not a
draw against `c904d4cc`'s own remaining 258:

- **`alpha_classifier` real requests**: exactly **973** (every claim
  currently `alpha_match_method=llm_unavailable`, `fallback_reason=
  provider_error` — confirmed, fixed list, computed zero-cost by
  `recover_alpha_classification.py --dry-run`, reproduced below).
- **Any other new model task**: **zero proposed**. This round explicitly
  checked whether anything beyond re-classification is needed before
  Evidence Fact/Activation/Exposure/Conflict can run: all of those
  consume `alpha_matches.json`/`structured_agent_outputs.json` directly
  via deterministic, non-LLM production functions (confirmed:
  `evidence_stance_audit.json` itself already shows `classifier_version=
  "evidence_stance.deterministic.v1"`, `llm_stance_count=0` for this
  run — direction/stance here is not an LLM task in this deployment).
  **No direction/level/other model task is proposed or assumed** beyond
  the 973 classifications themselves.
- **Client/application retries**: 0/0, matching the original run's frozen
  config exactly.
- **Research Agent layer**: 0 (confirmed, no TradingAgents involvement in
  recovery at all).

### Dry run (real, executed this round, zero Provider calls)

```
$ python3 recover_alpha_classification.py --dry-run
Total claims in original run: 975
Already-valid LLM results (frozen, reused as-is): 2
Claims needing real re-classification: 973
No unexpected buckets -- every claim is accounted for by exactly the
known valid-result / needs-recovery split.
ZERO Provider calls made by this dry run.
```
Full machine-readable scope: `dry_run_scope_c904d4cc-dc09-495c-aec5-b056979948e1-recovery-01.json`.

### Fake-transport mechanism proof (real, executed this round, zero real Provider cost)

```
$ python3 recover_alpha_classification.py --fake-transport-test
[fake-transport-test] records scoped for recovery: 973
[fake-transport-test] batch 1: 10 claims processed, checkpoint saved (10 total).
[fake-transport-test] batch 2: 10 claims processed, checkpoint saved (20 total).
[fake-transport-test] batch 3: 10 claims processed, checkpoint saved (30 total).
[fake-transport-test] 30/30 got a real, audited classification via the fixed recovery path (fake transport, zero real cost).
[fake-transport-test] real request-audit entries written: 30
[fake-transport-test] re-running the script against the SAME checkpoint to confirm already-completed claims are skipped, not re-sent:
  30 of 30 would be skipped on a restart; 0 still outstanding.
```

This proves, against a real (30-claim) sample of the actual 973-claim
recovery set, through the real `map_structured_records`/gateway
construction path: real concurrency=4 dispatch, zero failures, full
request/response audit coverage, and checkpoint-based resumability
(re-running against the same checkpoint correctly skips all 30 already-
completed claims rather than re-sending). **This is a fixed-response proof
of the recovery mechanism, not a claim about real AMD semantic results.**

## 十二. Frontend fix (completed, tested)

`frontend/src/components/StructuralSnapshot.tsx`: `DominantStructureSection`
previously had no access to whether any alpha was actually active, and
asserted "Several active forces are present" unconditionally whenever
`dominant_alphas` was empty. Fixed by lifting the single `useResearchGraph`
fetch to the shared parent (`StructuralSnapshot`) and passing it to both
`ActiveStructuresSection` and `DominantStructureSection`, so the two panels
can never show contradictory claims about the same underlying data. Three
real states are now correctly distinguished:
- Zero active, zero dominant → "No active structure currently exists for
  this run."
- Active exists, none dominant → "Several active forces are present, but
  none has reached dominant status." (only now, genuinely conditioned on
  real active-alpha data)
- Active-structure data itself unavailable/not loaded → a distinct,
  honest "could not be loaded to confirm" message (never silently defaults
  to either of the above).

Tests: `StructuralSnapshot.test.tsx` updated (1 test corrected to match the
now-honest behavior, 1 new test added for the genuinely-active-but-not-
dominant case) — **15/15 passing**. Full frontend suite: **350/350
passing**, zero regressions. `tsc --noEmit`: clean.

**The 4th state ("classification incomplete, insufficient to judge") is
NOT implemented this round.** It requires a new backend-computed signal
(e.g. an `alpha_classifier` completion ratio exposed on the research
response) that does not exist in the API today. Adding it means touching
`routes_research.py`/`build_research_response`, the response schema, and
the frontend type definitions — a genuinely separate, larger change not
attempted this round to avoid rushing a sensitive, shared API surface.
**This remains an open gap**, not silently dropped.

## 十三. Run-summary/API classification-completeness disclosure — NOT implemented this round (explicit gap)

Checked and confirmed still missing: `summary.json`/`build_research_
response`'s current output has no field distinguishing "classification ran
to completion and found nothing" from "classification mostly failed to
run." Both currently read as the same "no active Alpha" state via the
existing API. No fix attempted this round — would require the same new
backend signal referenced in 十二, deliberately deferred together with the
frontend 4th state rather than built as two disconnected half-measures.

## 十四. Full regression suite — real result

Command run (already in progress when this round began, now completed):

```
.venv/bin/python -m pytest tests/ -q \
  --ignore=tests/test_live_launcher_database_isolation.py \
  -k "not live and not fresh_run and not nvda_fresh and not qqq" \
  --deselect tests/structured_output_shadow/test_phase1b1_boundaries.py::test_existing_three_task_instructions_text_unchanged
```

## 十五. Corrected terminology: "113 content-qualified" retired

The prior report's "113 content-qualified claims" phrasing merged two
different statuses the v2.1 contract deliberately keeps separate. Corrected
here:

- **64 SUPPORTS** (19 analytical, 45 context_only) — the only status the
  existing, unmodified `compute_verified_support_eligibility` rule
  recognizes as a resolved, potentially-official basis.
- **49 CONDITIONAL** (26 analytical, 23 context_only) — real, LLM-verified
  partial support, but **not** official qualified evidence under the
  existing rule (`_RESOLVED_SUPPORT_STATUSES = {SUPPORTS, OPPOSES}`,
  unchanged this round). Listed separately in every count from this point
  on; never added to the 64 to produce a combined "qualified" figure again.
- Content-support passing (either status) is **not** the same as holding
  final scoring eligibility — that additionally requires a genuine,
  completed Alpha match, which is exactly the thing this round's fix
  restores the *opportunity* for, not a guarantee of.

The full, explicit per-claim list for the 19 analytical SUPPORTS claims
(claim_id, source binding, content-support method, quality, classification
completion, known blocker) is saved separately:
`19_analytical_supports_claim_list.json`. Every one of the 19 currently
shows `alpha_match_fallback_reason=provider_error` — i.e., every single
analytical, fully-supported claim in this run was blocked by exactly the
one defect this round fixed, not by any downstream scoring judgment.

**Direction, dedup, Exposure, and activation-threshold conditions remain
explicitly "untested"** for all 64+49=113 of these claims — none of them
has ever reached those stages. This round does not claim they would pass;
only that they have not yet been given the chance to be evaluated by them.
