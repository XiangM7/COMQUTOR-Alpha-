# v0.1.3 Recorder Health Diagnostics

Measurement/observability implementation, kept entirely separate from Provider Health. **Provider calls: 0. TradingAgents calls: 0. Ticker runs: 0.** HEAD unchanged (`9f228723fad5406c72e62beca67ec70ea0fdb004`). No commit. No push. `recorder.py` and `session.py` semantic behavior untouched.

## Executive Summary

```
Recorder Health implemented:            YES
Architecture role:                      AUDIT_TRACE_ONLY
New TSM recorder failure events:        247
Canonical semantic losses:              0
Recorder Health (new TSM):              RECORDER_DEGRADED
Old TSM recorder data:                  UNAVAILABLE (no surviving log for that run's window)
Recorder events counted as Provider
  failures/orphans/impacted-Alpha:      NO (invariant test-proven)
Recorder source durability:             EPHEMERAL_LOG_ONLY
recorder.py / session.py modified:      NO
Second semantic logging system built:   NO
```

## What Was Built

A single new, purely observational module: `comqutor_alpha/regression/recorder_health_diagnostics.py`, plus `tests/test_recorder_health_diagnostics.py` (18 tests). Zero existing production files modified — `recorder.py` and `session.py` are read-only inputs to this task's architectural proof, never edited.

## Architecture Recap (Proven, Not Re-Derived)

`SemanticCallRecorder.append()` raises `RecorderIntegrityError` on a persistence fault. Its sole caller, `SemanticRuntimeSession.finalize_call()`, catches that exception internally and calls `self._mark_degraded("SEMANTIC_RECORDER_APPEND_FAILED", exc, incomplete=True)` — the exception never propagates. `Week2LLMGateway.finalize_semantic_invocation()` wraps this in a second blanket try/except and returns `None`, discarded by every task-level caller (`alpha_mapper.py`, `structure_extractor.py`, `evidence_stance_llm.py`), each of which had already fixed its semantic result (`invocation.validated_output`) before the recorder/finalize call ran. **Recorder failures are therefore architecturally `AUDIT_TRACE_ONLY`** — this was proven in the prior `v0_1_3_tsm_recorder_variance_audit` task via direct code trace and is reused verbatim here, not re-derived.

## Data Source Investigation (Task Section 23)

Inspected whether a run-scoped persisted artifact records these events:

- `SemanticRuntimeSession._degraded_reason_codes` is a **deduplicated** list — a reason code is appended at most once per session (`session.py:211-212`), so even if it were persisted it could never carry a count of 247.
- It is, in fact, **never written into `llm_semantic_manifest.json`** — verified directly: the manifest schema has no `degraded_reason_codes` key for either TSM run.
- The manifest's `complete` field does flip to `False` when any incomplete-flagged degradation occurs, but this is **not recorder-specific** (both the OLD and NEW TSM runs show `complete=False`, for different underlying reasons) and carries no event count.
- **The only available source for the actual per-event count is the process-level launcher log** (e.g. `/tmp/comqutor_live_start.log`) — an ephemeral, non-run-scoped text log, not a canonical persisted run artifact.

Conclusion: **B. only launcher/process logs contain them.** This module never claims otherwise — every result carries an explicit `recorder_source_durability` field (`EPHEMERAL_LOG_ONLY` when a log source is supplied, `UNAVAILABLE` when none is), and no default log path is hardcoded as if canonical; callers must supply `log_path`/`log_text` explicitly.

## Metrics Implemented

`recorder_failure_events`, `recorder_health` (`RECORDER_HEALTHY` iff `recorder_failure_events == 0`, else `RECORDER_DEGRADED` — a conservative, purely observational state that never alters `semantic_status`, Provider Health, `benchmark_review_required`, or any Alpha output), `audit_trace_loss_events`, `canonical_semantic_losses` (architecturally fixed at `0`), `recorder_failure_error_types`, `recorder_failure_components` (honestly `None` — the log format has no task/component field), `recorder_traceability_unknown_count` (equals `recorder_failure_events`, since per-claim attribution is unavailable for all of them).

## TSM Results

| | Old (`dfc7ceb3`) | New (`0aeea938`) |
|---|---|---|
| `recorder_failure_events` | UNAVAILABLE | **247** |
| `recorder_health` | UNAVAILABLE | **RECORDER_DEGRADED** |
| `canonical_semantic_losses` | UNAVAILABLE | **0** |
| `recorder_source_durability` | UNAVAILABLE (no surviving log) | EPHEMERAL_LOG_ONLY |

The old run's recorder health is honestly reported as **UNAVAILABLE**, not a fabricated `RECORDER_HEALTHY` — no ephemeral log survives from that run's earlier execution window, and this module never guesses zero in the absence of a source.

## Recorder vs. Provider Separation (Task Section 22 — Required Invariant)

Confirmed both by unit test and by direct comparison on the real new TSM run:

| Metric | Value | Affected by 247 recorder failures? |
|---|---:|---|
| `provider_failure_events` | 117 | No |
| `provider_final_orphans_total` | 42 | No |
| `impacted_alpha_ids` | `["A101"]` | No |
| `benchmark_review_required` | `true` | No (same reason as before: A101, unrelated to recorder) |

`tests/test_recorder_health_diagnostics.py::test_recorder_events_do_not_become_provider_failures` and `::test_separation_holds_even_when_provider_is_independently_degraded` lock this invariant in as a regression test — a future code change that accidentally merges the two failure classes will fail these tests.

## Explicitly Not Done

No change to `recorder.py` or `session.py`. No retry added to recorder writes. No new semantic logging system. No new default/hardcoded "canonical" log path introduced. No Provider Health field redefinition.

## Tests

`tests/test_recorder_health_diagnostics.py`: **18 passed** — covering zero-events-healthy (A), one-failure-degraded (B), 247-event counting (C), Provider-failure/orphan/impacted-Alpha non-pollution (D/E/F), the architecturally-proven zero canonical loss (G), honest ephemeral-source reporting (H), unknown claim-level attribution (I), and no-artifact-mutation (J).

---

## Final Validation

Gold v1 / Gold Validity SHA-256 unchanged. `recorder.py`/`session.py` semantic behavior untouched. Recorder failures confirmed, by test and by real data, never to pollute Provider Health's independently-computed metrics. **Provider calls: 0. TradingAgents calls: 0. Ticker runs: 0. Commits: 0. Pushes: 0. Destructive git operations: 0.**
