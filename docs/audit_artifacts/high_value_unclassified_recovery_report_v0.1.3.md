# High-Value Unclassified Recovery — v0.1.3 (Section G)

**Status: rollforward from v0.1.2.1, pending fresh v0.1.3 six-ticker runs.**

Branch `comqutor-structure-layer`, HEAD `9f228723fad5406c72e62beca67ec70ea0fdb004` (unchanged — no commit, no push).

## Why this is a rollforward, not a fresh review

Section G runs before Sections I/J (the one authorized real NVDA smoke test and the fresh six-ticker v0.1.3 production run set) execute. No fresh v0.1.3 run data exists yet, so the only "healthy semantic runs" available are the same Step 5A six-ticker coverage-validation runs that `docs/audit_artifacts/high_value_unclassified_recovery_report.json` (v0.1.2.1) already reviewed exhaustively — 209 candidates individually adjudicated.

This v0.1.3 session's own code changes (Section B entity-exposure API overlay, Section C alpha_level_classifier Active-level gate, Section D conflict_detector display filter) all sit strictly **downstream** of Alpha Mapper matching — none of them re-scores `match_status`/`candidate_scores`. The 2091 MATCHED / 2764 NONE / 39 UNAVAILABLE split and every one of the 209 reviewed rows' verdicts are therefore unchanged from v0.1.2.1.

## Results (unchanged from v0.1.2.1)

| Classification | Count |
|---|---|
| STRONG_RECOVERY_CANDIDATE | 0 |
| BORDERLINE_RECOVERY_CANDIDATE | 0 |
| CORRECT_NONE | 208 |
| DUPLICATE_OR_LOW_VALUE | 1 |
| INSUFFICIENT_CONTEXT | 0 |

**Target**: ≥20 important recoveries. **Observed**: 0 strong + 0 borderline.
**`TARGET_NOT_SUPPORTED_BY_HEALTHY_SEMANTIC_DATA`** — not a refusal to tune the model; the healthy semantic data genuinely does not contain ≥20 recoverable high-value unclassified claims.

## What could change this once fresh v0.1.3 runs land

A pre-existing, unrelated repair already staged in `comqutor_alpha/structure_engine/alpha_mapper.py`/`week2_llm.py` (batch size 40→15, bounded concurrency) fixes the timeout starvation that produced some of the 39 UNAVAILABLE rows in the Step 5A run. A fresh v0.1.3 run could convert some of those into real MATCHED/NONE verdicts, changing the NONE pool. **This report must be regenerated against the real v0.1.3 six-ticker `selected_run_id`s once Section J completes** — tracked as an open action item for Sections K/L/M, not silently dropped.

## No production changes

Alpha Mapper, taxonomy, B1, B2, B4, Step-6 evidence qualification, and Step-7 display normalization are all untouched by Section G.

**Provider calls: 0. TradingAgents calls: 0. Commit: NO. Push: NO.**

See `docs/audit_artifacts/high_value_unclassified_recovery_report.json` for the full 209-row per-candidate detail this rollforward is based on.
