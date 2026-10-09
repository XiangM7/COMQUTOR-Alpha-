# test_evidence — raw test output (not edited)

| File | What it is |
|---|---|
| `t2_core_BEFORE_this_round.log` / `.junit.xml` | The T2 core set (9 test files) run at the START of this round, on the tree as the previous rounds left it: 171 passed, 2 failed. The 2 failures are stale frozen pins unrelated to T2's logic (an alpha_mapper byte pin; a hard-coded old HEAD). |
| `msft_replay_BEFORE_this_round.log` | `test_v0_1_3_offline_replay_proof.py::test_section_d_real_msft_conflicts_drop_misattributed_display_claims_without_changing_the_score` at the start: it failed with "Extra items in the left set: 'A102__A304'" - the T2 taxonomy change made that pair evaluable and the test still expected only the two older pairs. It was listed among the "pre-existing" baseline failures; its cause was T2. |
| `full_suite_AFTER.log` / `.junit.xml` | The FULL suite (about 5,000 tests) on the final tree of this round. |
| `full_suite_vs_baseline.json` | `summarize_test_evidence.py` on that JUnit file: totals, the 16 T2 test files one by one, and every failing test checked against the round-15 baseline (42 failing nodeids, each explained in round14's attribution manifest). A failure outside the baseline is listed as NEW. |
| `t2_fast_set_AFTER.log` / `.junit.xml` | The T2 fast set re-run AFTER the last edit of the round (a lint-only import reorder touched three files after the full suite had already imported them). |

No test was skipped, deleted or loosened to produce these results; the only assertions changed are listed in the report (section 5).
