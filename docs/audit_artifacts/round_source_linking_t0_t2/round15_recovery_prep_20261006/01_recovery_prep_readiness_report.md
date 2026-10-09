# Round 15 — AMD classification recovery: pre-send preparation (2026-10-06)

Scope of this round: the two zero-call preparations (derived-run save/view path; classification vs direction-task isolation) and a directly executable, frozen recovery plan. **Zero real Provider or search calls were made. No Fresh Run, no commit/push, no Demo. Verification standards, scoring thresholds, taxonomy, prompts and human-review policy are unchanged.** The real recovery has not been started; it is launched by the next explicit execution instruction.

## 1. Derived run: save / view path

`comqutor_alpha/classification_recovery.py::finalize_classification_recovery_execution` builds a **new** execution `recovery-<UTC stamp>-<8 hex>` with `based_on_run_id = c904d4cc-…`. It follows the existing review re-evaluation precedent (new id, `run_id`-only rebasing, same production completion flow `_run_week3_graph_pipeline`) and deliberately does **not** copy that precedent's one write into the original run (the `reevaluation_executions.jsonl` index).

| Item | What happens |
|---|---|
| Original run | Read-only. File hashes are recorded before anything is written, stored in the lineage artifact, and compared again at the end. |
| Copied (only `run_id` fields equal to the original id are rebased) | raw_agent_outputs, structured_agent_outputs, extracted_structures, source_registry, market_data_snapshot, data_sanity. Each copy records `content_equal_modulo_run_id`. |
| Assembled | `alpha_matches.json`: all 975 claims in the original order — 2 reused original results + recovered classifications + any original failure kept as a failure. |
| Recomputed (zero model calls) | structure graph, activations, exposures, conflicts, evidence facts, summary, run_audit, artifact manifest, formal acceptance — the same production pipeline. |
| Not copied | The original's model-call ledgers and TradingAgents usage files (they describe the original run's spend). |
| Identity | `claim_id`, `agent_output_id`, `source_agent_output_id`, claim text, evidence, source links and verification bindings are preserved verbatim. `recovery_lineage.json` holds a 975-entry `claim_identity_map` (original id → derived id, how each classification was obtained, original vs derived method / matched Alpha / fallback reason). |
| Database | `research_runs` row (`execution_mode='recovery'`, unique fingerprint so the original's completed-cache entry can never be reused) + `agent_outputs` rows under the new id. |
| API / History / Export | `GET /api/research/{id}` carries an additive `lineage` block (only for recovery runs); History lists the run; `/artifacts` and the Export ZIP include `recovery_lineage.json` and `evidence_stance_followup_manifest.json` (listed only when present, so every other run's manifest is byte-identical to before). |

Proof (`tests/test_classification_recovery_derived_run.py`, 23 tests; fake HTTP over the REAL frozen AMD inputs, scratch directory + scratch SQLite):

* derived run reaches `completed`; its API response, `/status`, History row, graph and conflicts routes agree;
* the real `outputs/runs/c904d4cc…` directory is **byte-identical** before and after (all files hashed); nothing is appended into the original;
* the original and derived runs' `/agent-outputs` are equal apart from `run_id`; the Export ZIP's `alpha_matches.json` has 975 claims, all under the new run id, no failed classification left;
* the original run's own response is unchanged and still reads `incomplete` with 973 failures — and a *partial* recovery stays `incomplete` in the derived run (unrecovered claims are never turned into NONE);
* bad inputs (claim order swapped, evidence text edited, id equal to base, already-finalized, missing base) are refused **without creating a directory**.

**Found while building it** (all fixed, all covered):
* `canonical_relations[*].run_id` also carries the run identity. The old re-evaluation precedent never rebased it. A residual-run-id check now fails closed instead of producing a mixed-identity run (it fired on 37 fields during testing).
* The API tests initially read `partial`: `tests/conftest.py` deletes `COMQUTOR_DATABASE_URL` before every test body, so DB/output env must be set per test.

UI: verified at the **adapter level** — the real API JSON of the derived run and of the original (`ui_fixture/`) goes through `adaptCanonicalResearchResponse` (`frontend/src/api/derivedRunResponse.test.ts`): original → `incomplete`, 973 failures; derived → `complete_*`, 975 claims. No browser render was done; no UI component was changed.

## 2. Classification vs direction-task isolation

`tests/test_classification_recovery_derived_run.py` (same file):

* **Valid-match scenario, not NONE-only.** The fake transport returns a valid Alpha selection (alternating A304/A102) for every request. Running the actual `run_staged_recovery` over 19 + 30 claims: 49 requests, **all `alpha_classifier`** in the audit log, 49 handler calls (nothing else reached the wire), all 49 claims matched, and the direction follow-up would have had real work (≥ 49 items, ≥ 5 requests) — still zero sent.
* **Control.** The same input through `build_alpha_matches_payload` (the path a normal run uses) **does** send `evidence_stance_classifier` requests. So the assertion can see the failure. Through the guard they are refused (12 classification requests, 0 direction requests).
* **Mechanism.** The recovery path calls `map_structured_records` directly (no direction step by construction) and every call goes through `TaskAllowlistGateway(['alpha_classifier'])`, which refuses any other task on all three Provider entry points before forwarding. The mapping layer swallows exceptions into per-claim fallbacks, so refusals are also recorded and the executor stops with `task_isolation_violation`; a second line checks the audited tasks per batch.
* **Direction requests are independent.** After classification the run writes `evidence_stance_followup_manifest.json`: the needed (claim, Alpha) pairs, `ceil(pairs/10)` independent request budget, a reuse check (only an existing LLM direction result for the same claim and Alpha counts; a deterministic stance never does), `requires_separate_authorization: true`, `counted_against_classification_cap: false`, `sent_by_this_manifest: 0`. For the original AMD run there is nothing to reuse (no matches existed).

## 3. Frozen recovery plan (`frozen_recovery_config.json`, `recovery_dry_run_output.log`)

| | |
|---|---|
| Scope | 975 claims: 2 valid NONE reused (each bound to a real successful matching call), 973 recovered. Order: the 19 analytical SUPPORTS first (order only; scope is all 973); the first 4 are the parallel-configuration gate; then the other 15; then 954 in frozen order. |
| Request cap | **≤ 973** Provider requests, sent or failed, independent of the original 1500. A resume counts requests already audited. Expected real sends 955–973 (identical-input claims may hit the cache; a hit never reserves budget). Research Agent / data / content-verification / direction calls: 0. |
| Config | model deepseek-v4-flash; client retries 0 (hard-coded) and application retries 0; **timeout 45 s, exported explicitly**; concurrency 4; audit on. |
| Re-proved against today's tree | prompt hash and the request input hashes for the reused claims equal what the original run really sent; the request shape (URL, body keys `messages/model/stream`, no `max_tokens`) is checked on **every audited request**, together with model, `x-stainless-read-timeout=45.0` and `x-stainless-retry-count=0`. |
| Stop rules | local audit failure · HTTP 401/403 · task-isolation violation · request without a claim id · wire config mismatch · cap would be exceeded · first-4 gate not protocol-complete. A stop schedules no new batch; the batch in flight finishes and each call is finalized individually (in-flight calls are never claimed cancelled). |
| Outcomes | valid NONE is a completed classification and is never retried; a failed response is saved and never auto-resent; an unknown (request audited, no response) is never auto-resent. |
| Checkpoints | per batch: `checkpoint_recovery.json`, `recovery_match_records.jsonl`, the request/response audit; claim state is reconciled from the audit log so a crash between a response and its checkpoint loses nothing. |
| Resume | same `--execution-id`; the stage-A gate is evaluated from the audit log, so a resume cannot wave through a failed first-4 check (fixed this round — it was previously evaluated only right after a batch). |
| Derived run | created only if no stop rule fired; a stopped run keeps checkpoint/audit and creates no run. |

## 4. Gate and launch

`--execute` does nothing — no gateway, no directory, no request — unless the operator's shell exports `COMQUTOR_RECOVERY_REAL_EXECUTION_ACK=recover-973-alpha-classifier-requests-plan-593271724790d08e` (bound to the frozen plan hash; any change to the plan, cap, model, timeout, concurrency or task list changes it), and the environment matches the frozen one. Authorization and configuration are judged against the **shell's own exports, snapshotted before the repo imports** (the repo's `.env` load can inject `COMQUTOR_DATABASE_URL` and sets `MAX_RETRIES=1`). It also requires a `*_test` database plus `COMQUTOR_REQUIRE_DATABASE_NAME`, and refuses `COMQUTOR_WEEK2_ALPHA_CLASSIFIER_MAX_TOKENS` / `COMQUTOR_WEEK2_LLM_BASE_URL` (they would change the request shape the original run used).

```
export COMQUTOR_RECOVERY_REAL_EXECUTION_ACK=recover-973-alpha-classifier-requests-plan-593271724790d08e
bash docs/audit_artifacts/round_source_linking_t0_t2/round15_recovery_prep_20261006/launch_real_recovery.sh
# resume: EXECUTION_ID=recovery-… RECOVERY_MAX_CALLS=<973 minus requests already audited> bash …/launch_real_recovery.sh
```

Exit codes: 0 finalized run · 1 blocked before sending · 2 stopped by a stop rule (resumable) · 3 finalized but not `ok`. Verified safely (`recovery_execute_blocked_output.log`): launcher without the variable → refused; launcher with a deliberately wrong value → shell checks pass, the Python gate refuses before anything is built; `--execute` directly → refused; `outputs/runs` listing unchanged.

## 5. Verification

* Recovery / identity / completion tests: **88 passed** (derived run 23, gate 8, staged executor 23, mid-batch crash 3, downstream zero-call 3, completion + identity traceability 28). Frontend: typecheck clean, **361 vitest passed** (359 + 2 new), eslint clean on the new file.
* Full backend run, **unfiltered**: `39 failed, 4881 passed, 56 skipped, 3 errors` in 43:43. Compared by nodeid with the round-14 baseline (`regression_evidence/comparison_to_round14_baseline.json`):
  * **Correction to round 14.** Its baseline run used `--ignore=tests/test_live_launcher_database_isolation.py -k "not live and not fresh_run and not nvda_fresh and not qqq"`, so 186 tests never ran, and "37 nodeids" described only the filtered set. Applying the same filter to this run gives exactly the same 37 failing nodeids — none extra, none missing.
  * The 5 outside that filter: **`test_w5_demo_seed.py::test_only_nvda_and_qqq_are_seeded`** — hidden before by `not qqq`; fails with the same `NVDA_MAIN_CONFLICT_NOT_ARBITRATED` as its baselined sibling on the **pristine committed HEAD and on the pre-repair-thread tree** (run directly this round), so it predates this work. **4 × `test_live_launcher_database_isolation.py`** — fail with the launcher's own "Port 8000 is already occupied": the still-running `comqutor-api` backend (started 10:35) holds the port (probe in `port_8000_probe.txt`). I did **not** stop that backend to make them pass, so I have not seen them pass in this environment; they are independent of this work by construction (they run the shell launcher with a patched exec line).
  * Unfiltered, pre-existing / environmental failures are therefore 42 nodeids, not 37. I did not re-pin any hash, delete an assertion, or add a skip.
* Protected set (original run, AMD 34-item list, historical request/response run, earlier rounds): **72 of 72 files identical**, checked before and after the full run. A first full run was stopped and restarted because I edited files it imports lazily mid-run; only the clean second run is reported.

## 6. Limits and open risks

* All derived-run proofs use fake-HTTP decisions (3 selections, the rest NONE) on the real frozen inputs: they prove the mechanism, nothing about real AMD classification quality.
* The derived run's database writes were exercised on SQLite only. The real run writes to the isolated Postgres `_test` database through the same repository methods production uses on every run, but this exact finalize path has not been run there — writing a fake run into the database the UI reads was not acceptable for a zero-call round.
* The UI check is adapter-level, not a browser render.
* If classification finds matches, direction results are **not** produced by this recovery: the manifest sizes them, and sending them needs its own authorization. Until then, scores use the deterministic stance the mapping step already attaches; "has a score" is not "activated".
* Not started in this round (per scope): the direction requests, rescoring and API/UI/Export verification on real results, and the T1 evidence package for John.

## 7. Files

Code: `comqutor_alpha/classification_recovery.py` (new); small additive edits in `storage/file_store.py` (two allowlist names), `api/artifact_export.py` (present-only manifest entries), `api/routes_research.py` (`lineage` block for recovery runs only). Driver: round-12 `recover_alpha_classification.py`. Tests: the two new backend files above, `frontend/src/api/derivedRunResponse.test.ts`, plus two edits in `tests/test_recovery_staged_executor.py`: one assertion updated for the richer `stop_detail` (it now also reports requests already sent by earlier processes), and the gateway helper now exports the 45 s timeout explicitly like the real launcher. This directory: `launch_real_recovery.sh`, `frozen_recovery_config.json` (+ `build_frozen_config.py`), `recovery_dry_run_output.log` / `recovery_dry_run_report_*.json`, `recovery_execute_blocked_output.log`, `protected_files_diff_round15*.json`, `ui_fixture/`, `regression_evidence/`.
