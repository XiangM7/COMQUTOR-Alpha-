# v0.2 Demo Walkthrough Checklist

**Verified live against the actual running application/API (`http://127.0.0.1:8000`) this task** — not assumed from older demo audits. Full detail in `v0_2_demo_walkthrough_checklist.json`.

## Selected Demo Runs

| Ticker | run_id | Classification | Live Servable | Walkthrough Status |
|---|---|---|---|---|
| NVDA | `ded99ecd-a186-4a90-859e-0f1a0efa43db` | FRESH_E2E (2026-09-17) | YES | **PASS** |
| QQQ | `0d890564-2479-4361-94e8-25c48af3b9a8` | FRESH_E2E (2026-09-17) | YES | **PASS** |
| SNDK | `e8e0f398-7b26-4462-8135-a1410ea5b335` | PERSISTED_DEMO (2026-09-04, reused — never called "Fresh") | YES | **PASS** |

## Per-Ticker Endpoint Verification (all HTTP 200, artifact completeness 9/9 pass)

| | Research | Graph | Conflicts | Evidence | Artifacts |
|---|---|---|---|---|---|
| NVDA | ✅ | ✅ | ✅ | ✅ | ✅ 9/9 |
| QQQ | ✅ | ✅ | ✅ | ✅ | ✅ 9/9 |
| SNDK | ✅ | ✅ | ✅ | ✅ | ✅ 9/9 |

No indexing/DB serving issue found for any of the three — no blocker to report, no backfill/reindex needed.

## Why Each Run Was Selected

- **NVDA:** best demonstrates rich dominant-Alpha structure, genuine conflict admission under the frozen formula, and an honest `REVIEW_REQUIRED` finding — chosen for the `do_not_force` demonstration, not because it's bullish-looking.
- **QQQ:** cleanly demonstrates both a legitimate absence of a dominant Alpha and an actual evidence-supported, on-allow-list conflict.
- **SNDK:** the only completed SNDK run available; demonstrates a legitimate no-main-conflict state — valuable precisely because the product must not manufacture conflicts.

## Walkthrough Checklist (A–K, per Section 11)

| Step | NVDA | QQQ | SNDK |
|---|---|---|---|
| A. Research view opened | ✅ | ✅ | ✅ |
| B. run_id/date traceable | ✅ | ✅ | ✅ |
| C. Structure Graph opened | ✅ | ✅ | ✅ |
| D. Active/dominant state identified | ✅ | ✅ | ✅ |
| E. Evidence opened | ✅ | ✅ | ✅ |
| F. Alpha traced to evidence | ✅ | ✅ | ✅ |
| G. Conflict Radar opened | ✅ | ✅ | ✅ |
| H. Main-conflict state explained | REVIEW_REQUIRED | PASS | legitimately none |
| I. Insufficiency/do-not-force shown | ✅ | ✅ | ✅ |
| J. UI doesn't imply "no structure" from incompleteness | N/A — all 3 runs fully completed | | |
| K. Source-citation behavior honest | ✅ stated explicitly for all three | | |

## Results

`ACTUAL_DEMO_WALKTHROUGH_COMPLETE = YES`. `ACTUAL_DEMO_WALKTHROUGH_PASS = YES` — none of the semantic REVIEW findings were converted to a walkthrough FAIL, since each is accurately represented, evidence-inspectable, correctly rule-applied, and not concealed.

`DEMO_RECORDING_REQUIRES_MANUAL_CAPTURE = YES` — this coding environment cannot record the desktop/browser session directly. No video file has been created or claimed. `docs/audit_artifacts/v0_2_demo_walkthrough_script.md` is the guide for that recording.
