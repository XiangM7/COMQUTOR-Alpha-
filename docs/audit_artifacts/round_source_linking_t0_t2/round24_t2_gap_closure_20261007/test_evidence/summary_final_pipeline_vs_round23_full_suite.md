# Test results

Files: FINAL_pipeline_path.junit.xml

Total **1039**: 1 failed, 1037 passed, 1 skipped

## Not passing

| Test | Outcome | First line of the message |
|---|---|---|
| `tests.test_b2_admissibility_integration::test_b2_result_is_computed_once_and_identical_across_detector_db_and_export` | failed | AssertionError: assert {'admissibili..._b': 'B', ...} == {'conflict_id...id': 'A', ...} |
| `tests.test_content_support_reevaluation_postgres_integration::test_reevaluation_official_result_and_history_protection_on_real_postgres` | skipped | COMQUTOR_TEST_DATABASE_URL is not set |

## Against the baseline (full_suite_AFTER.junit.xml)

- Tests in common: 1031; not in the baseline: 8
- **Passed in the baseline and not passing now: 0**
- Failing in both: 2
  - `tests.test_b2_admissibility_integration::test_b2_result_is_computed_once_and_identical_across_detector_db_and_export` (same message: True)
  - `tests.test_content_support_reevaluation_postgres_integration::test_reevaluation_official_result_and_history_protection_on_real_postgres` (same message: True)
- Failing in the baseline, passing now: 0
