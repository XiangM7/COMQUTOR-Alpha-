# Round 21 test evidence (only the tests affected by this round's code; no full regression was run on purpose)

Affected set = every test file that references a module changed this round (95 files). Run order and code state:

| run | files | result | code state |
|---|---|---|---|
| first pass (in session, not saved as a file) | 16 | 376 passed | before the last small edits (sign-word grounding, `numbers_not_found_in_saved_data`, unreproduced-percentage section) |
| `affected_remaining.*` | the other 79 | 1626 passed, 14 skipped, **24 failed -- all 24 are in the round-15 42-nodeid baseline** (`remaining_vs_baseline.json`: 0 new) | same (before the last small edits) |
| `final_code_rerun.*` (A) | 20 = 9 of the first 16 + 11 files whose tests run the grounding/trace/export/pipeline path | **365 passed, 0 failed** | FINAL code |
| `final_code_rerun_b.*` (B) | the other 7 of the first 16 | **171 passed, 0 failed** | FINAL code |

So all 16 first-pass files and every file that exercises the changed paths were re-run on the final code (27 files, 536 passed, 0 failed).
Frontend (`frontend_vitest_final.txt`): vitest 39 files / 547 tests passed; `tsc -b` exit 0; `eslint src` exit 0 (no output).
Not run: the full backend suite, e2e, any real-model request.
Baseline source: `round15_recovery_prep_20261006/regression_evidence/full_run.junit.xml` (42 failing nodeids, all explained in the regression attribution manifest).

After these runs one more test was added to `tests/test_t1_closure_grounding_dependency_trace.py` (a newly written run carries the `fact_dependency_contract` marker; the saved AMD originals do not): that file (39 tests) plus `tests/test_tradingagents_output_writer.py` ran together afterwards -- 56 passed.
