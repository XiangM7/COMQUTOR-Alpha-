# v0.1.3 Evidence-Stance Retry Reliability Fix

Implementation authorized. **No live Provider validation yet. No ticker runs. No Alpha semantic changes.** HEAD unchanged (`9f228723fad5406c72e62beca67ec70ea0fdb004`). No commit. No push.

## Executive Summary

```
Fix implemented:              YES
Target:                       evidence_stance_classifier only

Old retry budget:             1
New retry budget:             2
Old max attempts:             2
New max attempts:             3

Alpha classifier changed:     NO
Structure extractor changed:  NO
Timeout changed:              NO
Fallback changed:             NO
Alpha semantics changed:      NO
Provider behavior changed:    YES -- one task-specific extra retry only

Targeted tests:                18/18 PASS
New regressions:               0
Provider calls:                0
Ticker runs:                   0
Gold unchanged:                YES
```

## John — Provider Reliability Fix

```
Item                | Result
---------------------|--------------------------------------------
Target               | evidence_stance_classifier
Current issue        | 183 final orphans (74.4% of all orphans)
Old Retry            | 1
New Retry            | 2
Max Attempts         | 2 -> 3
Timeout              | unchanged (45s, shared)
Alpha Semantics      | unchanged
Alpha Classifier     | unchanged
Structure Extractor  | unchanged
New Regressions      | 0

Live validation:      NOT RUN
Next:                 One authorized TSM validation run
```

## 1. Retry Semantics Verified Before Editing

`week2_llm.py::invoke_json_with_trace`'s loop is `for attempt in range(1, effective_max_retries + 2)`. Confirmed: `effective_max_retries=1` → attempts 1,2 (initial + 1 retry = **2 total**); `effective_max_retries=2` → attempts 1,2,3 (initial + 2 retries = **3 total**). No off-by-one — verified by the canonical third-attempt-success fixture (`model.calls==3`, `provider_attempt_count==3`, `retry_count==2`).

## 2. Global Ceiling Confirmed Unchanged

`MAX_SERVER_RETRIES = 2` — untouched. The new `evidence_stance_classifier` value (2) **equals** this ceiling exactly; it does not exceed it. The code's interpretation matched the prior audit's assumption exactly — no stop-and-report was needed.

## 3. Implementation

**One production file changed: `comqutor_alpha/structure_engine/week2_llm.py`.** Added a module-level constant `EVIDENCE_STANCE_CLASSIFIER_MAX_RETRIES = min(2, MAX_SERVER_RETRIES)` and a new function `_resolve_task_max_retries(task, default_max_retries)`, called once immediately before the existing retry loop in `invoke_json_with_trace`. Every other line of that method, every other method in the file (`_invoke_json_legacy`, `invoke_prebuilt_json_prompt`), and every other file are byte-identical to before this change.

**Resolver semantics**: `task == 'evidence_stance_classifier' AND default_max_retries > 0` → `max(default_max_retries, 2)`; otherwise → `default_max_retries` unchanged. An explicit `default_max_retries == 0` is respected as an intentional "no retries at all" signal and is **never** raised, even for `evidence_stance_classifier`.

**A design correction made during implementation**: the first version of the resolver unconditionally forced `evidence_stance_classifier` to 2 retries regardless of the caller's configured value. Running the full backend suite exposed that this broke `tests/llm_runtime/test_evidence_stance_classifier_registration.py::test_d_malformed_response_fails_closed_not_a_registry_error`, which explicitly constructs a Gateway with `max_retries=0` to isolate single-attempt validation-failure behavior with a single canned Provider response — the unconditional override caused a 2nd/3rd attempt against an exhausted fake model. The resolver was corrected to respect an explicit zero, fixing the regression while leaving the approved production behavior (1→2 at the `.env`-configured default of 1) fully intact.

## 4. No Timeout / Backoff / Concurrency / Model / Prompt Change

Confirmed by direct diff: `DEFAULT_TIMEOUT_SECONDS`, `call_with_timeout`, all timeout-related constants — untouched. No `time.sleep`/`asyncio.sleep` added. `alpha_mapper.py` (the only file with a `ThreadPoolExecutor` for semantic-critical tasks) — untouched. `_TASK_INSTRUCTIONS`, `_provider_prompt_prefix`, model construction/factory code — untouched.

## 5. No Semantic Fallback Change

`fallback_used` remains `True` on final exhaustion, with the exact same shape as before — confirmed by `test_evidence_stance_exhaustion_produces_exactly_one_semantic_call_record`: exactly **one** persisted `llm_semantic_calls.jsonl` record for the one logical call, regardless of how many internal attempts (2 or 3) occurred. Only the number of attempts leading up to that fallback changed.

## 6. Retryable Error Contract Preserved

Timeout, transport error, and parse/schema validation failures remain retryable (unchanged branches). The one **non-retryable** path — `WEEK2_LLM_INPUT_TOO_LARGE`, rejected before the loop ever starts — is confirmed unaffected by the retry-budget increase (`model.calls == 0` regardless of task).

## 7. Required Tests — All 18 Pass

| # | Test | Result |
|---|---|---|
| 1 | Third-attempt success | PASS — `model.calls=3`, `retry_count=2`, `provider_attempt_count=3`, `validated_output=42`, 2 logged failures |
| 2 | Full exhaustion (3 attempts) | PASS — `model.calls=3`, `validation_accepted=False`, 3 logged failures |
| 3 | Transport retry | PASS — 2 `ConnectionError`s then success, both logged as `WEEK2_LLM_TRANSPORT_ERROR` |
| 4 | Non-retryable path | PASS — oversized-payload rejection unaffected by retry budget |
| 5 | Alpha classifier negative control | PASS — `model.calls=2`, unaffected; TSM A301 historical fixture reconfirmed |
| 6 | Structure extractor negative control | PASS — `model.calls=2`, unaffected |
| 7 | Failure-event counting | PASS — exact attempt-tagged log lines verified |
| 8 | Final-orphan, no double counting | PASS — exactly 1 record for 3 internal attempts |
| 9 | Fallback value unchanged | PASS — same shape, `fallback_used=True` |
| 10 | TSM A301 reliability fixture | PASS |
| 11 | Provider Health consistency | PASS — timeout/timeout/success → `provider_failure_events=2`, `final_orphans=0`; timeout×3 → `provider_failure_events=3`, `final_orphans=1` |
| + | Explicit zero-retries respect (2 tests) + 5 resolver unit tests | PASS |

**Total: 18/18 PASS.**

## 8. Provider Health Metrics / Alpha Attribution — Deferred

The prior audit's recommended metric additions (`retry_recovery_rate`, `terminal_error_type`, `attempts_to_success`, `orphan_rate_by_component`) and the evidence-stance Alpha-attribution mechanism were **not** added in this task — both require a small-but-real schema/design decision beyond a mechanical retry-count change, and the attribution mechanism was explicitly flagged non-trivial in the prior audit. Deferred per task scope.

## 9. Historical Offline Counterfactual (Section 28)

None of the 183 historical `evidence_stance_classifier` final orphans across the six authoritative runs (plus 32 in the TSM validation run) have a **recorded 3rd-attempt outcome** — `max_retries=1` (2 total attempts) was the applied policy for every one of the 7 historical runs. **Classification: `FUTURE_BENEFIT_UNKNOWN`** for all of them — explicitly not `OBSERVED_RECOVERABLE`, since no third attempt was ever actually made or logged. This audit does not invent one.

## 10. Expected Impact (Honest)

Historical exact final-orphan reduction: **UNKNOWN** (not observable from existing data). Future expected direction: **DOWN**. Raw failure events: **may increase** (not a regression by itself). Latency: **may increase** only for calls that would already have failed twice. Provider cost: **may increase modestly**, scoped to the already-failing tail. Semantic behavior: **unchanged**.

## 11. Latency / Cost Bound

Old max attempts per `evidence_stance_classifier` call: **2** (max 90s wall-clock at the shared 45s timeout). New max: **3** (max 135s). **Incremental latency risk: LOW. Incremental Provider-cost risk: LOW** — the increase applies only to the ~183-per-six-runs already-failing tail, not the common successful case.

## 12. Deferred Items

Global timeout changes; `alpha_classifier`/`structure_extractor` retry changes; AMD transport hardening (Option F); concurrency changes; evidence-stance Alpha-attribution mechanism; MSFT A304 extraction; A102 research coverage; A201 recovery; new benchmark runs; Provider Health metric additions.

## 13. Future Live Validation (Not Executed)

**Recommended ticker: TSM.** Focus metrics for that future, separately-authorized run: `evidence_stance_classifier` final-orphan count and orphan rate, overall `provider_final_orphans_total`, `impacted_alpha_ids`, A301 remaining non-Provider-impacted (negative control), Gold Alpha stability, Provider cost/latency. Success is **not** defined as raw failures decreasing.

---

## Gold / Measurement Safety

Gold unchanged. Gold Validity unchanged. Official Alpha Hit unchanged at **61.0317%**. P0/P1, Provider Health, Measurement Foundation, and Recorder Health all intact. Old TSM remains authoritative; new TSM remains not promoted.

## Final Validation

**Production files changed: 1** (`comqutor_alpha/structure_engine/week2_llm.py`). **Test files changed: 2** (`tests/structured_output_shadow/test_source_integrity.py` — required frozen SHA guard update; `tests/test_evidence_stance_retry_fix.py` — new). Full backend suite: **21 failed, 4139 passed, 3 errors, 47 skipped** (baseline: 21 failed, 4121 passed, 3 errors, 47 skipped) — every failed/error test name matches baseline exactly. **New regressions: 0** (two regressions surfaced mid-implementation by the full-suite run were diagnosed and fixed before this closure, not left outstanding). No timeout, Provider model, prompt, semantic fallback, or threshold change. Gold v1 SHA256 `99b1cd0247637054de360c3b5c0c00c7d8052152f3db1d29045eae1850bd8e9a` unchanged. Gold Validity SHA256 `3643ea45168c029d7c2a2ceb6d1d61cac3d5de80770d3dccb1f57d005c0c1cdf` unchanged. **Provider calls: 0. TradingAgents calls: 0. Ticker runs: 0. Commits: 0. Pushes: 0. Destructive git operations: 0.**
