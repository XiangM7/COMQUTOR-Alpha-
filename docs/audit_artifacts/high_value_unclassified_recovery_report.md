# High-Value Unclassified Recovery Closure — v0.1.2.1 (Step 9 / John #7)

**This is the authoritative closure artifact for John's request: "recover ≥20 important no_alpha_match claims to existing structures."** It supersedes the preliminary `high_value_true_none_candidates_v0.1.2.1.json` scan (preserved unmodified as historical analysis).

Branch `comqutor-structure-layer`, HEAD `9f228723fad5406c72e62beca67ec70ea0fdb004` (unchanged — no commit, no push). Zero Provider calls, zero TradingAgents calls — pure audit over the already-persisted Step 5A healthy six-ticker semantic outputs.

## Scope

- Source: `outputs/runs/_step5a_coverage_{nvda,qqq,msft,sndk,tsm,amd}/alpha_matches.json` (99.20% coverage, 2091 MATCHED / **2764 NONE** / 39 UNAVAILABLE).
- Only `match_status == "no_match"` rows are eligible — **UNAVAILABLE excluded entirely**, per task section 3.
- **Total valid NONE rows: 2764.**

## Candidate discovery (broadened beyond the original 23 keyword hits)

The existing deterministic `candidate_scores` diagnostics were used *only to find rows worth manual review* — never as semantic authority — via four methods:

| Method | Description | Count |
|---|---|---|
| Deterministic eligible diagnostic | `candidate_scores[*].eligible == true` for some Alpha despite final NONE | 179 |
| Liquidity-pattern re-scan | Broadened Step 5B's preliminary "company balance-sheet liquidity" pattern (originally 15, not individually itemized) to 36 individually-verified rows | 36 |
| Known Step 5B preliminary rows | The exact 1 strong + 3 weak/borderline rows from the preliminary scan | 4 |
| Targeted A101/A102/A103 search | AI-gated Alphas are structurally excluded from the deterministic eligible pool by the hard gate, so a separate mechanism-keyword search was required | 3 |
| **Total reviewed (deduplicated)** | | **209** |

## High-value definition (audit-only, not introduced into production)

No single authoritative "high_value" field exists in the persisted schema. Reused existing fields (`assertion_status`, `agent`/source role, `candidate_scores[*]`) under an audit-only rubric: substantive asserted claim; ticker-specific where the mechanism requires it; first-order research source preferred; materially causal fit to one canonical Alpha; not a duplicate; meaningful to the Alpha's actual thesis. This rubric is diagnostic only — never wired into production semantics.

## Results

| Classification | Count |
|---|---|
| **STRONG_RECOVERY_CANDIDATE** | **0** |
| **BORDERLINE_RECOVERY_CANDIDATE** | **0** |
| CORRECT_NONE | 208 |
| DUPLICATE_OR_LOW_VALUE | 1 |
| INSUFFICIENT_CONTEXT | 0 |

## Preliminary Step 5B candidates — re-adjudicated, not defended

**AMD Treasury-yields / A001 (Step 5B's "1 strong candidate")**: *"Macro context: Lower Treasury yields, easing selling pressure, positive Asian markets."* — **DOWNGRADED_BORDERLINE → DUPLICATE_OR_LOW_VALUE.** The semantic fit to A001 is genuine (falling yields easing selling pressure is a real discount-rate signal). But this exact macro fact is **already matched as A001 evidence 5 other times** in the same AMD run (near-identical restatements by `news_agent`, `sentiment_agent`, `bull_researcher`). Recovering this one additional copy would add zero new material evidence — Step 5B's preliminary scan did not check for in-run duplication against the already-matched pool.

**3 weak/borderline candidates (NVDA/AMD competitive-risk framing, AMD market-share)**: independently re-reviewed from scratch (not assumed correct) — all three **confirmed CORRECT_NONE**. Each is a competitive-positioning or market-share statement, not a demand-expansion/buildout assertion under A101/A103's actual mechanisms.

**15 keyword false-positives (company balance-sheet liquidity)**: re-scanned exhaustively and **extended to 36 individually-verified rows** across NVDA/MSFT/SNDK/TSM/AMD. All confirmed CORRECT_NONE — current-ratio/net-cash company-level metrics remain semantically unrelated to A003's macro monetary-liquidity-expansion thesis.

## Special precision safeguards applied

Every reviewed candidate was checked against the task's per-Alpha precision guidance: A601 rows (76 of the 179) were overwhelmingly technical-momentum/generic-sentiment/debate-meta-language keyword collisions, not narrative/attention/crowded-flow assertions — confirmed by a targeted second pass for stronger A601 vocabulary (`crowded`, `reflexive`, `investor attention`, `positioning`), which surfaced only one marginal multi-topic sentence, itself confirmed CORRECT_NONE. A304 rows were bare valuation metrics, never an asserted de-rating mechanism. A301 rows were historical GAAP line items, never a forward demand-expansion claim. A201 rows were chip/semiconductor keyword collisions in market-color context, never an asserted industry-cycle upturn.

## Target status

**Requested target**: ≥20 important recoveries.
**Observed result**: 0 strong + 0 borderline.

**`TARGET_NOT_SUPPORTED_BY_HEALTHY_SEMANTIC_DATA`**

> The healthy semantic data does not support forcing ≥20 recoveries.

This is not a QA failure caused by refusing to tune the model. It means the historical target was based on assumptions not reproduced under healthy (post-Step-5A) semantic execution, which resolved the runtime-starvation artifact that originally made the Alpha Mapper appear to be missing widespread recall.

## No production changes

Alpha Mapper, taxonomy, B1, B2, B4, Step-6 evidence qualification, and Step-7 display normalization are all untouched. No claim ID was hardcoded, no keyword fallback added, no ticker rule added, no persisted Alpha mapping rewritten.

## Files

**Created**: `docs/audit_artifacts/high_value_unclassified_recovery_report.json`, this file, `tests/test_high_value_unclassified_recovery.py`.
**Preserved unmodified**: `docs/audit_artifacts/high_value_true_none_candidates_v0.1.2.1.json` (preliminary historical analysis).
**Updated (additive)**: `docs/audit_artifacts/qa_closure_index.json` (`step9_high_value_unclassified_recovery` block).
**Provider calls**: 0. **TradingAgents calls**: 0. **Commit**: NO. **Push**: NO.
