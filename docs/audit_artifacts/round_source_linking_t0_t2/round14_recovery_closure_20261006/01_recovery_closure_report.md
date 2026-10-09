# Round 14 — closure of the parallel-audit repair; real AMD classification recovery prepared (not run)

Target run: `c904d4cc-dc09-495c-aec5-b056979948e1` (read-only). 2026-10-06.
Written for: the project owner reviewing whether to authorize the real recovery.

**Boundaries kept.** Zero real Provider or search calls (every test and script here uses `httpx.MockTransport` or a trapped transport). No Fresh Run, no Research-Agent or content-verification re-run, no real recovery (`--execute` is still hard-blocked; evidence: `recovery_execute_blocked_output.log`, exit 1). No change to model, prompt, verification standard, thresholds, taxonomy or reference labels. No commit, no push, no Demo work. The round-13 parallel audit fix, its 12 tests and the 973-claim fake-HTTP proof are kept; forced serialization and "audit off" were never brought back.

**Original run and history are byte-identical** after every run in this round: 72 protected files (the original run, the AMD 34-item artifacts, the historical request/response run, earlier rounds' reports) — `protected_files_after_all_runs_diff.json` → `identical: true`. One exclusion is stated rather than hidden: `round11…/server_stdout_round2.log` is the stdout of a backend that is **still running** from the earlier AMD launcher and keeps appending `GET /ready` / `GET /api/research` polling lines; it is a live log, not a result. (That backend is idle but alive — see section 9.)

## Headline

| | |
|---|---|
| Final full regression | `34 failed, 4658 passed, 56 skipped, 186 deselected, 3 errors` in 38:05, exit 1 — **37 nodeids, every one pre-existing or environmental; none introduced by this work** |
| Flaky concurrency test | root cause shown (test synchronization, **not** the gateway); original fails 14.4 % on the *pre-repair* gateway too; rewritten test 0/500 |
| claim → semantic call → attempt → request/response | closed without touching the prompt, payload or cache key; byte-identical request body proven |
| Mid-batch crash recovery | both new crash modes proven; 975 identities preserved by a real assembler, not set arithmetic |
| Completion disclosure | one shared 4-state judgment in API, summary sentence and UI |
| Recovery plan | frozen: 973 requests, retries 0/0, concurrency 4, audit on; **not sent** |
| Open blockers for sending | none that cause mis-binding, loss, duplicate paid sends or over-budget; four open items listed in section 9 |

I also made mistakes during this round that the full run exposed; they are listed plainly in section 2 (a first "fix" of the flaky test that was wrong, a call-convention break, replay's private validator mirror, and a summary-text regression). All are fixed and have regression tests.

---

## 二. Regression: exact accounting

Three full runs, identical command except where noted:

| Run | Code state | Result | Exit |
|---|---|---|---|
| A (your retained result) | end of round 13 | `40 failed, 4637 passed, 18 skipped, 3 errors` | 1 |
| B | round 14 edits, **before** fixing what B exposed | `82 failed, 4638 passed, 18 skipped, 3 errors` | 1 |
| C (final) | all fixes | `34 failed, 4658 passed, 56 skipped, 3 errors` | 1 |

Command: `pytest tests/ -q -p no:cacheprovider --ignore=tests/test_live_launcher_database_isolation.py -k "not live and not fresh_run and not nvda_fresh and not qqq"`. Run C **drops** the earlier `--deselect` of `test_existing_three_task_instructions_text_unchanged`, so that test is now counted. Logs: `regression_evidence/` (A is in the round-13 directory, unchanged).

### What run B exposed — my own regressions (44 new nodeids, 42 mine)

* **33 in `tests/replay/*`** — `replay/source_bundle.py` keeps a *private mirror* of the semantic-record validator. My round-14 optional fields (`claim_ids`, `cache.source_call_id`) were rejected there, so exact replay of any run recorded after my change would have failed closed. The file's own history comment documents this exact trap for earlier additive fields. Fixed (mirror + validation); test `test_replay_validator_accepts_the_new_optional_fields_end_to_end_and_still_rejects_malformed_ones`.
* **8 in `test_week2_runtime_capacity_repair.py` + 1 in `test_evidence_stance_llm.py`** — my `claim_ids=` keyword on `invoke_json_with_trace` broke every gateway-like object with the old 3-argument signature, and the resulting `TypeError` was swallowed by `_classify_alpha_with_llm`'s blanket `except` into a **fake `provider_error`** (I reproduced this: it returns `unavailable/provider_error`). Fixed by explicit signature detection (not exception catching) and by making the adapter's `_DeferredFinalizeGatewayProxy` transparent to keywords. Guard tests fail on the old behavior.
* The other two new nodeids: `test_polling_reaches_completed` (pollution, below) and the phase1b1 test (previously deselected).

I also introduced one more regression and caught it in a targeted run, before run C: my "classification not performed" summary sentence pre-empted the established evidence-gate message for runs whose classifier is deliberately disabled (`test_week4_pipeline_api`). Now the summary is overridden only for fault-caused incompleteness; a disabled classifier keeps the established messages while the structured status still says "incomplete".

### The six "passes alone, fails in the full run" tests — mechanism found

The round-13 report called these full-suite-scale flakiness without a mechanism. They were **test pollution**, now proven with an env/thread probe (a pure observer plugin) over a full run:

* `tests/test_phase_c_script_transport_level_fixed_response.py` runs the Phase-C script, which `load_dotenv(.env)`s and assigns `os.environ["COMQUTOR_WEEK2_LLM_ENABLED"/"MAX_RETRIES"/"MAX_CALLS"]` directly; the tests only monkeypatch the API key. Those writes (and `.env`'s `COMQUTOR_DATABASE_URL`) outlived the module.
* **1,523 of 4,741 tests started with leaked values**; the first is `…::test_21_inputs_produce_21_single_claim_requests_at_the_real_transport`. Every later test (`w5_*`, `week1a`, `week4`…) then ran with the Week2 gateway switched on — which is why `week2_llm_errors.jsonl` appeared in an offline run and why the API polling jobs stalled.
* Fix: an autouse `patch.dict(os.environ)` restore in that test module (no assertion changed). Run C probe: **0 of 4,751** tests started with a leaked value; all six now pass.
* Side effect worth knowing: the leak had also been *accidentally* enabling 38 Postgres integration tests (it re-injected `COMQUTOR_TEST_DATABASE_URL`). With the leak gone they skip, as conftest intends ("not configured") — hence skips 18 → 56. I ran them explicitly with the test URL from `.env` (database `comqutor_alpha_test`, name checked to end in `_test`): **52 passed** (38 + the other 14 Postgres tests). Evidence: `regression_evidence/env_leak_evidence_sanitized.json` (the raw probe log is not kept — it recorded a DB password).

### Run C: the 37 remaining nodeids (`regression_attribution_manifest.md/.json`)

Counts come from JUnit and match pytest: **34 failure elements + 3 error elements = 37 nodeids; none has more than one event** (the 3 errors are `setup`-stage; the 34 are `call`-stage).

Evidence for each nodeid: (1) the same test against the current tree with the **five files the repair thread edited replaced by their recorded pre-thread versions** (Claude Code file-history backups, each verified by diffing against the adjacent recorded version — the delta is exactly my edits), (2) a pristine `git archive HEAD`, (3) direct verification of the cause. "Same cause" required the failure *message* to match, not just the outcome.

| Category | Count | Notes |
|---|---|---|
| 1 frozen-hash check triggered by this work's authorized change | **0** | |
| 2 fails before the work too, same cause | **36** | **19** (13 + 6; 3 of them setup errors): the static `evidence_review_summary_v2.json` lacks asserted keys (committed file; pure JSON read, no repo code on the path); **10** hash-pin tests (5 `case17` params + `case10`, `step10`, `step11`, `a6`, `source_integrity`); and one each: `e42`, `test_60_sample`, `v0_1_3 section_d`, `b2`, `w5_demo_seed`, `structured_adapter_concurrency`, `phase1b1` |
| 3 functional regression from this work | **0** (after fixes above) | |
| 4 pollution / environment | **1** | shadow smoke asserts no dotfile in the shared `outputs/evaluations/`; a Finder `.DS_Store` is there |
| 5 not yet attributable | **0** | |

**Frozen hashes — old pins untouched.** `frozen_hash_change_inventory.json` records, per pinned file, pinned vs committed-HEAD vs *recorded pre-thread* vs current hash. `alpha_mapper.py` and `week2_llm.py` were already unmet before my thread (pre-thread `ed725d06…` and `508d5bbe…` vs pins `506a228e…` and `5c9106a3…`). Every pin test would still fail with the thread's edits removed (per-test verdicts in the inventory). Two pins also contradict each other: `alpha_taxonomy_v1.yaml` is pinned to `c031168c…` by four tests and to `18a0dc6b…` by `msft_a102::a6`, so they can never all pass. `test_e42` hard-codes `b5837e80…` but HEAD is `7a9aefa5…`. **This inventory is a technical record, not a re-approval by John or anyone**, and I did not alter any pin, assertion or skip. The repair thread's change list and the evidence for each change is in the same file.

Not hidden, not fixed here (scope): `test_structured_adapter_concurrency_touches_no_alpha_mapping_code` fails on a comment I wrote on 10-05 12:36 that contains the word `alpha_mapper` (a one-line rewording would fix it); the two `w5_demo_seed` tests fail whenever their file runs alone (and one passes inside the full run — state-dependent).

---

## 三. The flaky test: `test_concurrent_success_timeout_and_retry_all_preserve_their_own_attempts`

"4 of 5 pass" was not evidence, so I measured. Experiments use **recorded** states: the original test (file-history v10) and the pre-repair gateway (week2_llm v17 etc.), vs the final gateway. `flaky_test_root_cause_experiments.json`:

| Test | Gateway | Natural timing | Call 3's persist slowed 0.15 s |
|---|---|---|---|
| original | pre-repair | **72/500 fail (14.4 %)** | 20/20 fail |
| original | final | **80/500 fail (16.0 %)** | 20/20 fail |
| rewritten | pre-repair | 0/500 | 0/20 |
| rewritten | final | 0/500 | 0/20 |

The original never established either order it asserts. Failing assertion lines over 300 natural runs: 45× `persist_sequence` (call 3 must persist before call 1) and 6× `call_sequence` (call 3 must *start* last — thread start order isn't guaranteed). The failure rate is the same before and after the contextvar redesign, and slowing only call 3's persist reproduces it deterministically → **test synchronization, not identity, terminal-state, retry or log races in production code.**

**My first fix was wrong** (and my "15/15 passes" was luck): I made call 1's `model.invoke()` wait for call 3's persist, but that wait runs inside the gateway's own 0.05 s per-call timeout, so call 1 could itself time out (1–2 % natural, 100 % with a slowed persist — measured). The rewrite removes that: threads start one at a time, each only after the previous call has begun (guaranteeing `call_sequence`), and call 1's *persist* (outside any timeout) waits for call 3's. All assertions and timing parameters are unchanged.

---

## 四. claim identity without touching the model input

Chain: `claim_id → semantic call_id → attempt_id → request/response`.

* Carried out of band: an explicit `claim_ids=` keyword on `invoke_json_with_trace`/`start_call`, stored on the trace; optional `claim_ids` on semantic records; optional `cache.source_call_id` and a cache-entry `source_call_id` so a cache-served claim names the real call it reused. `semantic_call_id` and `claim_ids` are now on **both** the request and the response audit records (the response record had neither before).
* Not touched: the payload dict (which becomes the prompt), the prompt, taxonomy, and the cache key.
* **Proof the model input is unchanged:** `test_claim_ids_never_change_the_real_request_body` (byte-identical request body with and without `claim_ids`); and against the *original real run*: today's `prompt_identity_sha256('alpha_classifier')` equals the `prompt_sha256` on its real calls (`ac48723f…`), and the payload rebuilt today for both original successful calls hashes to exactly the `input_sha256` the real run recorded (`capture_effective_request_config.py`).
* Four-way concurrent run with two identical-text claims: distinct chains, correct per-claim binding; timeout + late response keep their own identity; cache reuse cites the real source call; `content_support_verification` (which already carried identity inside its payload) is unaffected. 10 tests in `tests/test_claim_identity_traceability.py`.

---

## 五. Mid-batch crash recovery

Round 13's "75 saved, then crash" test is kept. New, on the real execution path:

1. **Responses audited, batch checkpoint never written** → recovered from the real audit log (`reconcile_claim_states_from_audit_log`), not re-sent; the lost full match record is rebuilt **offline with zero model calls** (`rematerialize_match_record` runs the production mapping on the saved decision) and is asserted equal to the record that was lost.
2. **Request sent, no valid response saved** → state `unknown_inflight`: never automatically re-sent, never turned into NONE or success. A previously `failed` claim likewise stays a failure and is not retried.
3. A valid NONE is a completed classification and is reused; unsent claims stay pending.
4. `assemble_recovered_alpha_matches` rebuilds all **975** records in original order from only: the two verbatim originals, persisted full records, offline re-materializations, or the *original failure record* — and raises if identity is not exactly preserved. Tests: full run (973 recovered + 2 reused, completion = complete), early stop (19 answered, 954 still read as failures — never as NONE), and the crash gap.
5. Fake-HTTP output cannot become real output (enforced, not a convention): a fake run refuses to write under `outputs/runs/` and drops a marker file; checkpoints carry an `origin` and a resume under a different origin is refused; a real-origin run refuses any directory with the marker or a fake checkpoint.

I do **not** promise exactly-once sending under a network fault or process kill. What the records and stop rules guarantee is that nothing is *automatically* re-sent when its state is unknown. One bounded residual: after a crash, identical-input twins of an already-answered claim that were served from the (in-memory, per-process) cache in the crashed batch may be sent again — at most 18 in the whole run (see section 7) and always inside the 973 cap.

---

## 六. Classification completion is disclosed once, read by all

`compute_alpha_classification_completion` reads only `alpha_matches.json`'s persisted fields and separates: valid select, valid NONE, **call failure** (real attempt, no usable result), **not executed** (never sent: classifier off, budget spent, input too large, or the Gateway's own audit refused — split into configuration vs fault). Gateway audit refusals used to be mislabeled `invalid_output`; they are now `audit_unavailable` (still a failure, never NONE).

For `c904d4cc` as frozen: **975 claims = 0 valid select + 2 valid NONE + 973 call failures + 0 not executed → `incomplete`** (never "complete, no active").

Shared 4-state status (`incomplete` / `complete_no_active` / `complete_active_no_dominant` / `complete_has_dominant`) in `build_research_response` (new fields), the run-summary sentence (never says "none exists" while claims are unclassified; positive findings are never overridden), and the Structural Snapshot UI (adapter strict about counts; frontend 359/359, `tsc` and ESLint clean). Disclosed limits: for a *deliberately disabled* classifier the API status is `incomplete` but the summary sentence keeps its established wording; and `summary.json` (the persisted structure-only export) is **unchanged** because `replay/exact_semantic.py` regenerates it byte-identically for historical runs — the per-claim detail is in the exported `alpha_matches.json`.

---

## 七. Recovery configuration (frozen; nothing sent)

`recover_alpha_classification.py --dry-run` (default) → `recovery_dry_run_output.log`. **973 to recover + 2 valid reused = 975.** The 2 reused results bind to real successful semantic calls whose validated output matches (`verify_valid_results_binding`); one (`market_report:claim:1`) has **2 exact-text twins inside the 973** that will get their own fresh decision (cache keys include `run_id`) — a model could answer differently for identical input; that would be reported, not overridden.

**955 vs 973.** Counting with today's own payload code (proved identical to the original run's recorded input hashes): 973 claims have **955 unique request inputs**. The earlier "16 duplicates" counted duplicate *groups* (14 pairs + 2 triples); they contain **18 extra claims** (973 − 955). The fake run's 955 sends are those unique inputs; the semantic cache served the other 18. A cache hit never reserves Gateway budget and is not extra allowance; real sends are 955–973 (two identical inputs dispatched concurrently can both miss), hard cap 973.

**Effective request** (real client construction path, transport faked; `effective_request_config.json`):

| Parameter | Value | Source |
|---|---|---|
| provider / model | `deepseek` / `deepseek-v4-flash` | explicit env |
| application retries / client retries | 0 / 0 | **must be exported**; `.env` sets `COMQUTOR_WEEK2_LLM_MAX_RETRIES=1` and `load_dotenv` never overrides — with 1, alpha_classifier silently gets a retry and the stance task gets `max(1,2)=2`; client retries hard-coded 0 |
| request cap | 973 (independent; **not** the 258 left of the original 1500) | explicit env |
| concurrency / audit | 4 / on | explicit env |
| timeout | 45 s | **from `.env`** (code default is 20 s) — recommend exporting it to freeze it |
| max_tokens | none sent (alpha_classifier has no override; original real request_control `max_tokens_value=None`) | default |
| request body | only `model`, one `user` message (~9.3k chars), `stream:false`; no thinking/reasoning key | what the client sends |
| observed in 2 original real calls | ~1.96k input tokens; 85 and 459 output tokens, of which **72 and 446 are reasoning tokens** (provider default; the repo sends no thinking control); 1.8–3.0 s | not a cap or guarantee |

**Enforced, not just documented:** `preflight_gateway_config` makes the executor refuse to start if application retries ≠ 0, the Gateway cap exceeds the independent cap, audit is off, concurrency ≠ 4, or the model ≠ the frozen one (tests included).

**Frozen send order (all inside the 973):** the fixed 19 analytical SUPPORTS claims first, in the existing list order — the first 4 are the real parallel-configuration gate (all four must be protocol-complete with correct identity; a valid NONE counts), then the other 15, then the remaining 954. Stop scheduling new requests on: local audit failure, HTTP 401/403, empty claim identity, wrong model, cap reached, or a failed stage-A gate. A single later claim failure is saved and not retried. Stop rules are exercised by tests (auth failure after 4 sends, gate failure, single-failure-not-retried, audit failure mid-stage, cap, unknown/failed exclusion).

---

## 八. Recompute and T1 preparation

* **Downstream is zero-call:** `routes_research._run_week3_graph_pipeline` takes no gateway, and graph/conflict engines contain no model reference; proven with every model/network seam trapped, on the frozen inputs and on the assembled 975-record payload (`test_recovery_downstream_zero_model_calls.py`, assembly tests).
* **One necessary new model task is *not* in the 973:** the production flow follows classification with `evidence_stance_classifier` (batches of 10 items, up to 3 target Alphas per *matched* claim, none for NONE). It is not sent by the recovery plan. Its size is only known after classification: `stance_followup_budget()` computes it from the recovered matches with no call (requests ≈ ⌈items/10⌉, retries 0 only if `MAX_RETRIES=0` is exported). It needs its own authorization.
* **The 19 fixed analytical SUPPORTS claims today** (`nineteen_claims_status.py`, re-runnable on a recovered run): all 19 are content-verified `SUPPORTS` and all 19 are **call failures** (`provider_error`); 0 valid matches, 0 valid NONE, 0 in the official pool. After a recovery the same tool reports, per claim, the classification, whether it reached the official verified pool and with what activation level, and the first gate that blocked it.
* **Still unmet for T1 / John (not asserted either way):** semantic discovery of sources for the 714 `NOT_PROVIDED` claims (open since round 11); the Export ZIP's internal bytes were never byte-verified; the original AMD 34-item ledger has not been re-run against the new run's sources; John's own acceptance has not been given. API/Export/UI preservation of the same references after recovery is a post-recovery check, not done here. "Produces an active or a Conflict" is **not** a T1 criterion I used.

---

## 九. What is still open

**Recovery blockers (mis-binding, loss, duplicate paid sends, over-budget, wrong consumption):** none known. Items that remain, none of which sends a request by itself:

1. **Authorization** for the 973-request recovery and, separately, the contingent stance task; the launcher must export `COMQUTOR_WEEK2_LLM_MAX_RETRIES=0` (preflight will refuse otherwise) and should export the 45 s timeout.
2. **Derived-run identity is undecided:** how the assembled 975-record payload becomes a viewable run (new run id and `based_on_run_id`, regenerating run-level artifacts consistently) is a design decision I did not make. Assembly and the zero-call recompute are proven on a scratch copy only.
3. **Twin disclosure** (2 claims) and the bounded crash-time twin re-send (≤ 18) described above.
4. **A backend from the earlier AMD launcher is still running** and its UI is polling it. I never called it, but a running backend with real-execution flags means "zero real calls" also depends on nobody submitting a run from that UI. I did not stop it.

**Disclosed, not in scope:** the 37 pre-existing failures above and the stale/contradictory frozen pins (need an owner decision to re-certify; I changed none); `summary.json` stays structure-only; `.DS_Store`; the `alpha_mapper` comment.

## Files (all under `round14_recovery_closure_20261006/` unless noted)

`regression_attribution_manifest.{md,json}`, `frozen_hash_change_inventory.json`, `regression_evidence/` (final run log + JUnit [one synthetic test-fixture token redacted], run B log, pre-thread and HEAD outcomes, sanitized env-leak evidence, 973-claim re-run log), `flaky_test_root_cause_experiments.{py,json}`, `effective_request_config.{py,json}`, `recovery_dry_run_{output.log,report_*.json}`, `recovery_execute_blocked_output.log`, `nineteen_claims_status*.{py,json}`, `protected_files_*`, and the builders/runners. New tests live in `tests/` (`test_claim_identity_traceability`, `test_alpha_classification_completion`, `test_recovery_staged_executor`, `test_recovery_mid_batch_crash`, `test_recovery_downstream_zero_model_calls`, plus the round-13 `test_week2_llm_true_concurrent_audit`). The recovery script remains at `round12…/recover_alpha_classification.py`.
