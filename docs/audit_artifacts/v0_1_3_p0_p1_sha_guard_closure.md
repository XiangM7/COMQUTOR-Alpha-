# v0.1.3 P0/P1 SHA Guard Closure

Narrow test-baseline maintenance only. **Provider calls: 0. TradingAgents calls: 0. Ticker runs: 0. HEAD unchanged (`9f228723fad5406c72e62beca67ec70ea0fdb004`). No commit. No push.**

## John — P0/P1 Final Regression Closure

```
P0 contamination fix:                      PASS
P1 company_names fix:                      PASS
Targeted tests:                            26/26 PASS
Stale SHA guards:                          3/3 updated and PASS
Backend new regressions:                   0
Gold unchanged:                            YES
Production semantics changed in this task: NO
Provider calls: 0    TradingAgents calls: 0    Ticker runs: 0
```

## Previous State

`NEW_REGRESSIONS = 3` — stale frozen SHA256 expectations after the approved v0.1.3 P0/P1 evidence-correctness change to `activation_scorer_v2.py`.

## Independent Verification

Directly re-ran the exact 3 previously-reported tests in isolation (not relying on the prior report):

| Test | Protected file | Old expected SHA256 | Actual SHA256 |
|---|---|---|---|
| `test_evidence_review_v2.py::test_case17_production_semantic_modules_remain_untouched[...activation_scorer_v2.py]` | `activation_scorer_v2.py` | `3cb44fd8...bac15` | `c1b0a479...2911e` |
| `test_step10_final_e2e_qa.py::test_production_semantic_files_unchanged_during_step10` | `activation_scorer_v2.py` | `3cb44fd8...bac15` | `c1b0a479...2911e` |
| `test_step11_provider_health_rerun.py::test_production_semantic_files_unchanged_during_step11` | `activation_scorer_v2.py` | `3cb44fd8...bac15` | `c1b0a479...2911e` |

All 3 classified **STALE_BYTE_HASH_GUARD**. All three protect the identical single file with the identical old→new hash transition.

## Intentional-Change Verification

Reconstructed the exact pre-P0/P1 byte content of `activation_scorer_v2.py` by programmatically reversing the three known P0 hunks (import, `_foreign_issuer_only_reason` function, veto-wiring block). Diffing the reconstruction against the current file shows **the only delta is exactly those three additions** — nothing else changed. As independent cross-proof, the reconstructed file's own SHA256 computes to exactly the OLD frozen hash (`3cb44fd8...bac15`) the guards expected — confirming the guards were frozen against precisely this pre-P0 state, and the sole change since is the approved P0 patch. Targeted P0/P1 tests (26/26) confirm the known AMD contamination remains removed.

## Guard Updates

Modified exactly 3 test files — one dict-value change each (old SHA256 → new SHA256), plus a one-line rationale comment matching the codebase's own established style for this exact dict (short note + pointer to the relevant test file):

- `tests/test_evidence_review_v2.py`
- `tests/test_step10_final_e2e_qa.py`
- `tests/test_step11_provider_health_rerun.py`

New canonical hash (computed directly via `shasum -a 256`, never hard-coded): `c1b0a479a1d06c94811004c2ea62d95598427ea4541e0f770a5d4633e642911e`

No test removed, skipped, xfailed, weakened, wildcarded, or made conditional. No production code touched.

## Test Results

| Suite | Result |
|---|---|
| 3 affected guard tests | 3 passed, 0 failed |
| P0/P1 targeted tests | 26 passed, 0 failed |
| Full backend suite | 4043 passed, 21 failed, 3 errors, 47 skipped |

**Failure-set comparison**: the exact sorted list of 21 failed + 3 errored test names is **byte-for-byte identical** to the pre-P0/P1 reverted-baseline run captured in the prior closure task. `PRE_EXISTING_FAILURES = 21` (+3 errors). `NEW_REGRESSIONS = 0`.

## Test-Only Change Verification

- Production files changed by this task: **0**
- Test/baseline files changed: exactly the 3 SHA guard files above
- `pipeline.py`, `activation_scorer_v2.py`, `issuer_aliases.py`, `test_p0_p1_evidence_correctness_fix.py`: all byte-identical to their state at this task's start (diffed directly against preserved backups)

## P0/P1 Core Behavior Reverified

- AMD contaminated A201 claim: still does not qualify
- Remaining confirmed C1 contamination: **0**
- Corporate `company_names` propagation: active (NVDA/MSFT/AMD/TSM/SNDK non-empty, QQQ empty)
- SNDK A102 negative control: still passes
- QQQ ETF behavior: unchanged

## Benchmark Hashes

- Gold v1: `99b1cd0247637054de360c3b5c0c00c7d8052152f3db1d29045eae1850bd8e9a` — unchanged
- Gold Validity: `3643ea45168c029d7c2a2ceb6d1d61cac3d5de80770d3dccb1f57d005c0c1cdf` — unchanged

---

## Final Acceptance

**P0/P1: CLOSED PASS**

All required conditions met: the 3 failures were confirmed pure stale SHA guards; no guard was removed or weakened; all 3 updated guard tests pass; P0/P1 targeted tests still pass; full backend comparison shows `NEW_REGRESSIONS = 0`; production files unchanged during this closure task; Gold hashes unchanged; zero ticker/Provider/TradingAgents calls.

**Provider calls: 0. TradingAgents calls: 0. Ticker runs: 0. No commit. No push. No destructive git operations.**
