# v0.2 Day 4B — Fresh E2E (NVDA, QQQ)

Metric family: **DAY4_FRESH_E2E**. Validation type: `FRESH_RUN`. Full detail in `v0_2_day4_fresh_e2e.json`.

## Pre-Run Identity

Branch `comqutor-structure-layer`, HEAD `7a9aefa5c7b5c820515447c6289aeef80eac9bdc`, Gold baseline SHA256 `b8165911b78aa46fa4993a6b209d47e2b66e152547a618e2587facd97eb79a9c`, `alpha_classifier` prompt SHA256 `36bf5a632dee1e3cd8f4b2ac04fa3498db63cf99275d309157365c59c5bf77e9` (batch: `291f69db9c495eebc75c52cbf5d9ce9f97401af3ec7a735765f01f43af6d876e`). Research profile: `comqutor_deepseek_default_v1` (deepseek / deepseek-v4-flash). Executed via the already-running production API server, which already had both real-execution flags set on its own process.

## Fresh NVDA

| | |
|---|---|
| run_id | `421bca7a-29ea-4176-8116-4c84e2ea957f` |
| Start / End | 2026-09-16T22:44:24Z → 2026-09-16T23:19:24Z |
| Wall-clock | 2100s (35.0 min) |
| Provider calls | 704 (alpha_classifier 629, evidence_stance_classifier 40, structure_extractor 2, structured_adapter 9) |
| Retries / timeouts | 26 / 0 |
| Tokens | field present but recorded as 0 for every call under this provider — effectively unavailable |
| Cost | `COST_NOT_DIRECTLY_MEASURED` |
| Artifact completeness | pass (9/9) |
| Detected (active) | A101, A304, A601 |
| Dominant | none |
| Main conflict | **A101__A304** — in the frozen NVDA baseline |
| Must-detect rules | A101 active ✓, A304 active ✓ — both satisfied |
| Prompt used | confirmed `week2.alpha_classifier.v4` in this run's own manifest |

**NVDA Formal Gold: `PASS`.**

## Fresh QQQ

| | |
|---|---|
| run_id | `a4dae9c5-0443-48ac-a313-10151922b923` |
| Start / End | 2026-09-16T23:21:34Z → 2026-09-17T00:17:12Z |
| Wall-clock | 3338s (55.6 min) |
| Provider calls | 1914 (alpha_classifier 1019, evidence_stance_classifier 10, structure_extractor 4, structured_adapter 10) |
| Retries / timeouts | 871 / 10 (856 transport errors + 10 timeouts — unusually high, explains the longer wall-clock; run still completed with full artifact integrity) |
| Tokens | same limitation as NVDA — unavailable |
| Cost | `COST_NOT_DIRECTLY_MEASURED` |
| Artifact completeness | pass (9/9) |
| Detected (active) | A601 only |
| Dominant | none |
| Main conflict | **None admitted** — does **not** reproduce the historical `A301__A304` |
| Rule-level check | A001/A003/A304/A501 all non-mandatory (should_detect/conditional_only), none violated; A601 (should_detect) satisfied; forbidden-dominant constraint on A301 satisfied (not dominant) |
| Prompt used | confirmed `week2.alpha_classifier.v4` |

Per explicit instruction, absence of a conflict is **not** automatically a failure — this run's own rule-level evaluation is clean.

**QQQ Formal Gold: `REVIEW_REQUIRED`** (carried, unchanged). This specific fresh run did not reproduce `A301__A304` and violates nothing on its own, but the standing product-owner-approval question raised by the earlier frozen-input run's `A301__A304` finding is a governance question, not something one non-reproducing fresh run resolves. **Frozen QQQ baseline: unchanged. `RULE_CHANGE_RECOMMENDATION`: not adopted.**
