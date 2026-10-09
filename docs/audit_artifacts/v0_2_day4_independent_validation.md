# v0.2 Day 4 Independent Frozen Holdout Validation — Phase D

Metric family: **DAY4_INDEPENDENT_VALIDATION**. Full detail in `v0_2_day4_independent_validation.json`.

## Independence Verification

`docs/audit_artifacts/item2_blind_holdout4_frozen.csv` (Alpha, N=200) and `item2_blind_holdout2_comparison.csv` (Polarity, N=141) — **not** used to derive Day 2/3's failure analysis or fixes (only `item2_blind_holdout5` was). Verified directly, not asserted:

- **Zero `claim_id` overlap** between holdout4 and holdout5 (200 vs. 200 claim_ids, direct set intersection = 0).
- **Zero `sample_id` overlap** between holdout2 and holdout5.
- Holdout4's frozen CSV SHA256 recomputed today and matches its own report's stated hash exactly — file integrity confirmed, not assumed.
- Holdout4 is the most rigorous available independent set: 200 samples (25/ticker × 8 tickers), explicit historical-exclusion of every earlier set, and its own report documents that sampling was verified **not** dependent on current or historical Alpha Mapper output — the exact kind of independence this task requires, not manufactured by renaming.

## Alpha Match — Independent Result (Holdout #4)

| Numerator | Denominator | Exclusions | Accuracy | Target | Met? |
|---:|---:|---:|---:|---:|---|
| 148 | 200 | 0 | **74.00%** | ≥80% | **NO** |

**Caveat (disclosed, not hidden):** this official metric reflects the `alpha_classifier` prompt as it stood at Holdout #4's own recorded HEAD (`8ecf6bfdf7fd8203e223b220be8ca244da92d1f1`) — confirmed by direct `git show` to still carry `prompt_version=week2.alpha_classifier.v1`, i.e. **before** the v3 rewrite in commit `c454245` that Day 3 identified as the likely fix. This number is not evidence the current prompt fails — it predates the fix by the same margin the Day 2/3 samples did. No denominator or exclusion was altered to approach the 80% target.

## Polarity — Independent Result (Holdout #2)

No single non-H5 independent set in the repository carries both Alpha and Polarity review at Holdout #4's rigor; Holdout #4 is Alpha-only. Holdout #2 (141 samples) is the only other independent set with Polarity review.

| Numerator | Denominator | Exclusions | Accuracy | Target | Met? |
|---:|---:|---:|---:|---:|---|
| 123 | 141 | 0 | **87.23%** | ≥80% | **YES** |

**Caveats (disclosed):** Holdout #2's own methodology separately flags 39 rows as duplicates and 14 as "stale historical data" — reported here exactly as Holdout #2's own official summary computed them, not re-excluded or re-included by this task. Also predates commit `c454245`, same age caveat as the Alpha result above.

**Critical support/opposition reversals:** **0** (Holdout #2's own count, zero sample IDs).

## What Was Not Done

These are the two sets' own already-computed, frozen, human-reviewed official metrics — not re-run today. A fresh local-deterministic-only re-derivation (mirroring Phase A's method) was not additionally performed against these two sets: Phase A already demonstrates that such a re-derivation tests only the always-weak, never-authoritative deterministic fallback, not the actual LLM-backed capability these 80% targets are meant to measure, so it would not have added a materially different signal here.
