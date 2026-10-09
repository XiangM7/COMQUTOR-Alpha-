# The one failing test that is not in the round-15 baseline — and why it is not T2's

`tests/test_evidence_review_sample.py::test_58_sample_rows_trace_back_to_real_artifacts`

**What it asserts.** Every sampled evidence row's `claim_id` starts with the id of the run directory the sample was taken from.

**What happens.** The sample takes, per ticker, the latest saved run (`comqutor_alpha/regression/run_selection.py: select_run_for_ticker`: latest analysis date, then creation time).
For AMD that is now `dependency-20261007T220450Z-33128621`, the offline derived execution Round 21 created (2026-10-07T22:04:53Z). A derived execution keeps the **root run's** claim ids
(`c904d4cc-…:news_agent:news_report:claim:19`), so the prefix test fails for the 6 AMD rows.

**Evidence (all read-only).**
1. `select_run_for_ticker("AMD", "outputs/runs")` returns the dependency run; calling the test fixture's own `build_evidence_review_sample(...)` on the real `outputs/runs` gives 6 rows whose
   `claim_id` does not start with `source_run_id`, all from that run.
2. Control: the same call over a copy of `outputs/runs` (APFS clone, deleted afterwards) **without** the `dependency-*` runs: AMD's latest run becomes `requal-20261007T174744Z-664040d6`
   (another derived execution, created before Round 21) and the same 6-row failure appears. So the cause is the family of derived AMD executions (recovery / requal / dependency, rounds 16-21),
   not one run.
3. The round-15 baseline (2026-10-06), taken before those derived runs existed, did not fail this test (its one failure in this file is `test_60_…`, which still fails).
4. No T2 file is on this code path: `comqutor_alpha/evaluation/evidence_review_sample.py` imports the taxonomy loader, the replay pipeline and the file store only.

**What was done.** Nothing: the test was not edited, skipped or re-pinned, and no run directory was touched. The fix belongs to the AMD recovery work (the test, or the sample builder, should resolve the
claim-id prefix through the derived run's `root_run_id`); it is recorded here and in the report as an open item.
