# Round 22 test evidence (only the tests affected by this round's code; no full regression was run on purpose)

| file | what it is | result |
|---|---|---|
| `round22_new_and_closure_tests.txt` | the three new backend test files + the Round-21 closure file (`-v`) | 68 passed |
| `backend_affected.log` / `.junit.xml` / `backend_affected_files.txt` | every test file that references a module changed this round (58 files) + the whole `tests/replay` directory, run on the FINAL code | 987 passed, 14 skipped, 1 failed |
| `backend_affected_vs_baseline.json` | the failing test compared with the recorded pre-existing baseline (round 15, 42 failing nodeids, all explained) by `compare_with_baseline.py` | the 1 failure is IN the baseline (`test_b2_admissibility_integration::test_b2_result_is_computed_once_and_identical_across_detector_db_and_export`); **new failures: 0** |
| `postgres_integration.txt` | PostgreSQL integration tests against the isolated `*_test` database (URL never printed) | 14 passed |
| `frontend_vitest.txt`, `frontend_tsc.txt`, `frontend_eslint.txt` | full frontend suite, typecheck, lint (an empty tsc / eslint file means no output = exit code 0) | vitest 557 passed (40 files); tsc exit 0; eslint exit 0 |
| `capture_layer_before_trace_changes.*` | an EARLIER partial run (capture layer + replay) made before the evidence-trace changes; kept for transparency, superseded by `backend_affected.*` | 237 passed |

Browser evidence is in `../browser_walkthrough_round22_conflict*` and `../browser_walkthrough_round22_regression*` (GET-only; every non-GET request is aborted and counted: 0).
Not run: the full backend suite, e2e, any real-model or real-provider request.
