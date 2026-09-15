# v0.1.3 Offline Closure — Go/No-Go (Items 1–10)

Branch `comqutor-structure-layer`, HEAD `9f228723fad5406c72e62beca67ec70ea0fdb004` (unchanged — no commit, no push).

**Provider calls this closure phase: 0. TradingAgents calls this closure phase: 0.** (Two real NVDA smoke-test runs plus a 10-call health probe happened earlier, under separate explicit authorization, *before* the STOP instruction — nothing new since.)

## Issue status

| # | Issue | Status |
|---|---|---|
| 1 | Six-ticker regression results | **FIXED** (schema/logic/tests only — not yet populated, per instruction) |
| 2 | Formal evidence review metrics | **FIXED** |
| 3 | Entity exposure seed status consistency | **FIXED** |
| 4 | Alpha level alignment (A301) | **FIXED** |
| 5 | Evidence polarity | **FIXED** |
| 6 | v0.1.3 feedback loop | **SPEC BLOCKED** (found, but Phase 2 per Development Plan — not invented) |
| — | Conflict state separation | **FIXED** |
| — | High-value unclassified recovery | **COMPLETE** |

## Highlights

- **Issue 4 root cause**: a decision-logic bug in `alpha_level_classifier.py` (category A — scorer/classifier stage), not persistence/API/display/frontend. All four downstream layers traced and confirmed correct by construction. Proven on a **real historical MSFT run** where A301 (score 58.87, 0/16 ticker-specific evidence, 0 local structure edges) was genuinely shown `active` before the fix and now gates to `candidate`.
- **Issue 5 root cause**: presentation-only bug in `conflict_detector.py`'s `bull_structure`/`bear_structure` (B1 stance and B5's evidence UI were already correct). Proven on the same real MSFT run: bear-side displayed claim count drops 24→16 (A101/A304) and 24→16 (A304/A601) while the frozen `conflict_score`/admitted-conflict-set/`main_conflict` stay byte-identical.
- **Issue 6**: authoritative spec found in `docs/specs/COMQUTOR_Alpha_Development_Plan_v1.0.docx` — the "Alpha Memory" cross-run feedback concept is explicitly marked **Phase 2**, not MVP. Only a static descriptive registry exists today. Not invented; flagged as a Product-authority open question.

## Tests

Full suite: **3965 passed**, 21 failed, 3 errors, 47 skipped, 69 subtests passed. **Zero new failures attributable to this task** — every failure traced to one of three pre-existing, already-documented causes (an earlier task's deliberate `evidence_review_summary_v2.json` schema stripping; a stale frozen-HEAD test; pre-existing unstaged changes in `replay/`/`w5_demo_fixtures.py` predating this session).

## Does any fix change research-result semantics?

Yes, by design, for Sections C and D — that's the point of the fix. No, for this closure phase's own additions (regression_report_v3, formal_metrics, seed_status_consistency) — all purely additive.

## Must the existing healthy NVDA run be superseded?

**No.** Both fixes were already live when NVDA run `2f8ee897` executed — its research artifacts already reflect them. Only its `run_audit.json` was regenerated (offline, zero new calls) to pick up this phase's additive fields.

## Files changed this phase

`comqutor_alpha/regression/regression_report_v3.py` (new), `comqutor_alpha/api/routes_research.py`, `docs/audit_artifacts/evidence_review_summary_v2.json`, plus 6 test files (3 new: `test_regression_report_v3.py`, `test_v0_1_3_offline_replay_proof.py`, and additions to `test_evidence_review_v2.py`/`test_run_audit_v2.py`/`test_alpha_display_normalization.py`/`test_step10_final_e2e_qa.py`/`test_step11_provider_health_rerun.py`). Full list in the JSON twin of this report.

## Next step

**STOP HERE.** Awaiting explicit re-authorization before any fresh six-ticker run or further Provider/TradingAgents call.
