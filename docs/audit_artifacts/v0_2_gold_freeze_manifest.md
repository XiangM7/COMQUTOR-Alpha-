# Gold v0.2 Freeze Manifest

**`FROZEN_GOLD_V0_2`.** Freeze timestamp: `2026-09-10T21:04:41+00:00`.

## Contract Files

| File | SHA256 |
|---|---|
| `docs/audit_artifacts/v0_2_gold_operational_contract.json` | `e2df7139e19ec998afc6335caf4d53528dd3f4356a46d4e9a88d9d04b520000f` |
| `docs/audit_artifacts/v0_2_gold_operational_contract.md` | `8e184d7ed41cbe253b5aa7e97e150e9c7f4dbfd6852d411e9874dbe299bf9f04` |

**Prior draft JSON SHA256** (Step 1, superseded): `1ddbb9c538be83c79fdb02110afd798ed83cd59469e48412183dbcaa1f0cd8b1`

## Tier / Blocking Policy

- **Formal Gold (blocking)**: NVDA, QQQ, SNDK
- **Silver Diagnostic (non-blocking)**: MSFT, TSM, AMD
- Silver failures can later produce a diagnostic FAIL, but cannot alone cause a release-blocking FAIL.

## Rule Summary

| Hit Type | Count |
|---|---:|
| `ALPHA_HIT` | 12 |
| `COMPOSITE_STRUCTURE_HIT` | 3 |
| `NEGATIVE_CONTROL_HIT` | 2 |
| `CONDITIONAL_ACCEPTANCE_HIT` | 2 |
| **Total** | **19** |

Rule count changed from 18 (Step 1 draft) to 19 at freeze: `MSFT-A102-INFERENCE` was split into `MSFT-A102-DIRECT-INFERENCE-TRIGGER` and `MSFT-A102-INDIRECT-INFERENCE-SUPPORT` per John's final decision (item G).

## Resolved Review Items — 9 of 9

| # | Rule ID | Final Decision |
|---|---|---|
| A | `NVDA-A301-FUNDAMENTAL-GROWTH` | `should_detect_if_supported` + `conditional_only` |
| B | `QQQ-A001-RATE-CUT-CYCLE` | `should_detect_if_supported` + `conditional_only` |
| C | `QQQ-A003-LIQUIDITY-EXPANSION` | `should_detect_if_supported` + `conditional_only` |
| D | `QQQ-A501-RECESSION-RISK` | `should_detect_if_supported` + `conditional_only` |
| E | `QQQ-ETF-CONTEXT-CONTROL` | Forbidden-dominant scope locked to **A301 only**; A101/A103/A304/A501/A601 explicitly not forbidden |
| F | `SNDK-A201-SEMICONDUCTOR-CYCLE` | `should_detect_if_supported` + `conditional_only`; anti-over-AI control confirmed as the **stronger, blocking** component of SNDK Gold |
| G | `MSFT-A102-INFERENCE` | **Split**: direct inference-mechanism evidence → `must_detect_if_evidence_present`; generic AI-adoption evidence → `should_detect_if_supported` |
| H | `MSFT-CAPEX-BURDEN-CONDITIONAL` | `do_not_force` A304 from capex alone; requires linkage to margin/FCF/ROIC-return/valuation/multiple-compression/equivalent downside transmission |
| I | `TSM-AI-TO-FOUNDRY-TRANSMISSION` | `A103 → A201` confirmed **NOT canonical**; removed from acceptable paths; A103 downgraded to `OPTIONAL_SUPPORTING_ALPHA`; canonical paths limited to `A101 → A201 → A301` |

**Remaining review items: 0.**

## Gold Immutability Rule

**After this freeze, Gold v0.2 rules must NOT be edited in response to actual Alpha results, conflict mismatches, low Gold Hit, unexpected failures, or release outcome.** Any future semantic change to Gold requires a **new Gold version** (e.g. v0.3). Gold v0.2 must never be silently mutated once comparison against real run results begins.

## Anti-Leakage

```
actual_run_results_inspected:      false
actual_detected_alphas_inspected:  false
actual_main_conflicts_inspected:   false
acceptance_computed:               false
gold_rules_modified_after_result_inspection: false
```

Sources consulted this task: the existing Step-1 draft contract (own prior output) and `alpha_taxonomy_v1.yaml` (re-checked for the A103/A201 relation question, item I). No fresh-run artifact, `alpha_activations.json`, detected-Alpha set, actual conflict, final acceptance report, or retrospective benchmark result was inspected in Step 2.

## No Acceptance Yet

`v0_2_final_acceptance_table` — **not created**. `v0_2_evidence_trigger_matrix` — **not created**. Both belong to later steps; this task ends immediately after the Gold v0.2 freeze.

## Final Validation

Exactly 6 tickers; exactly 3 Formal Gold; exactly 3 Silver. All 9 prior review items resolved, 0 remaining. No new production Alpha ID. No new taxonomy edge — `A103 → A201` explicitly confirmed non-canonical. No fixed expected-Alpha model recreated. No actual run result inspected. No PASS/FAIL calculated.

**Production files changed: 0. Test files changed: 0. Provider calls: 0. TradingAgents calls: 0. Ticker runs: 0. Commits: 0. Pushes: 0. Destructive git operations: 0.**
