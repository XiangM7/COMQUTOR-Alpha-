# Test results

Files: FINAL_t2_affected.junit.xml, FINAL_upstream_cited.junit.xml

Total **215**: 1 failed, 214 passed

## Not passing

| Test | Outcome | First line of the message |
|---|---|---|
| `tests.test_msft_a102_a304_taxonomy_adjudication.TestSectionAAllOutcomes::test_a6_b1_b2_b3_b4_invariant_modules_are_byte_identical` | failed | AssertionError: /Users/xiangmao/COMQUTOR-Alpha-/comqutor_alpha/structure_engine/alpha_mapper.py hash changed |

## Against the baseline (full_suite_AFTER.junit.xml)

- Tests in common: 119; not in the baseline: 96
- **Passed in the baseline and not passing now: 0**
- Failing in both: 1
  - `tests.test_msft_a102_a304_taxonomy_adjudication.TestSectionAAllOutcomes::test_a6_b1_b2_b3_b4_invariant_modules_are_byte_identical` (same message: True)
- Failing in the baseline, passing now: 0
