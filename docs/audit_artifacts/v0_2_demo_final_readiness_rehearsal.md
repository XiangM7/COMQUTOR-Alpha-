# COMQUTOR Alpha — Final Demo Readiness Rehearsal

**Product Demo Hardening — Phase 3.** A read-only, end-to-end rehearsal of the actual stakeholder demo, using the real serving environment (real Postgres DB, real `comqutor-api`, real frontend) against the three accepted persisted demo runs. No product code was changed. No Provider/TradingAgents calls. No fresh research. No `POST /api/research`. No `POST /api/replay-all` against real data.

## Executive Decision

**`DEMO_READY_WITH_MINOR_CAVEATS`**

Zero demo-blocking findings. All three persisted runs are fully live-servable; the NVDA, QQQ, and SNDK stories all render exactly as expected, with human-readable Alpha names, no internal jargon leaking into the default view, working evidence drill-down, an intact disclaimer, and clean operator-tooling separation. One bounded, non-desktop-affecting layout issue (small-viewport horizontal overflow from long claim-ID text) and two polish-level, non-product findings (framework deprecation console warnings; a rehearsal-script navigation artifact) remain, none of which affect the planned 1440×900 desktop demo.

## Environment Verification

- **Active database**: `postgresql+psycopg://127.0.0.1:5433/comqutor_alpha` — confirmed via `resolve_database_url()`, credentials never inspected or printed.
- **`GET /health`**: `{"status":"ok"}`
- **`GET /ready`**: `{"status":"ready","database":"ready","job_manager":"ready","real_execution":"configured","live_semantic_pipeline":"ready"}`
- **`scripts/verify_persisted_run_serveability.py`** against NVDA/QQQ/SNDK: **exit code 0**, all three `FULLY_LIVE_SERVABLE`, dominant/main-conflict fields matching expectations exactly (NVDA: dominant A301, conflict A101/A304; QQQ: no dominant, conflict A301/A304; SNDK: dominant A201, no conflict).
- **Serving path**: a Vite dev server was pointed at the already-running real `comqutor-api`; the rehearsal used real-browser automation (Playwright/Chromium) against this real stack — no mocked component fixtures anywhere in this phase.

## Landing Page

**PASS.** `/research` loads cleanly with no visible error. `ReplayAllPanel`/"Reprocess saved outputs" is absent; no operator controls are visible. The ticker form and analyst selection are understandable at a glance; Recent Runs behaves normally. The global disclaimer ("Research analysis only — not financial advice.") is visible and not visually overwhelming. No raw engineering jargon (`regime_level`, `B2`, `SHADOW`, `phi_id`, `activation_modulation_applied`, `NO_LOCAL_STRUCTURE_SUPPORT`, `LINEAGE_UNRESOLVED`) is visible by default; `candidate` is at most `TECHNICAL_ONLY`. No absolute local filesystem paths are visible. No horizontal overflow at 1440×900.

## NVDA Primary Demo

**Classification: `PRIMARY_READY`.**

The first screen (Structural Snapshot, visible immediately after the short research summary, no extra navigation required) already answers "what does COMQUTOR think is happening?" within seconds: five active structures, a clear **dominant structure — A301 Revenue Expansion**, and the **main conflict — A101 AI Expansion vs A304 Multiple Compression**. This naturally communicates a strong AI/growth thesis in tension with valuation risk, exactly the intended story, without further explanation needed.

**Drill-down** (Research → Structure Graph → Conflict Radar → back to Research): all routes load without a manual refresh, route continuity is preserved, Alpha naming stays consistent across pages, no duplicate or conflicting conclusions appear, evidence is inspectable, and the Conflict Radar's Counter Evidence section is present.

**"Why?" test — rated `EASY`.** The structural conclusion → Alpha → evidence → source/agent chain is reachable via one explicit "View structure graph" link from the first screen; each Alpha card's "Evidence (N)" disclosure directly reveals claim text, agent, match score, and relation — no raw JSON or terminal required. Basic evidence (agent, claim, confidence) is additionally already visible on the Research page's own Analyst findings panel with zero navigation.

**Technical Details test**: default view uses stakeholder language throughout; expanding a Technical Details disclosure reveals the raw activation level, raw qualification/reason codes, and Alpha Memory's raw mode/`activation_modulation_applied` value — real, structured technical transparency, never an arbitrary JSON dump. Auditability is intact.

## QQQ Secondary Demo

**Classification: `SECONDARY_READY`.**

The no-dominant state renders exactly as the accepted copy: **"No single structure currently dominates."** — alongside five visible active structures, this reads as a considered analytical conclusion, not missing data or a loading failure. The main conflict (**A301 Revenue Expansion vs A304 Multiple Compression**) renders correctly. Default-view jargon audit: **zero leaks** (`regime_level`/`B2`/`Conflict Evidence Admissibility`/`activation_modulation_applied`/`NO_LOCAL_STRUCTURE_SUPPORT`/`LINEAGE_UNRESOLVED` all `NOT_PRESENT`; `candidate`/`SHADOW`/`phi_id` at most `TECHNICAL_ONLY`).

## SNDK Edge-Case Demo

**Classification: `EDGE_CASE_READY`.**

**Dominant — A201 Semiconductor Supercycle** renders correctly; **no admitted main conflict** renders as a legitimate analytical result via the existing approved copy ("No conflicts detected... This does not mean the position carries no risk."), never resembling a conflict-engine failure or missing data, and never implying zero risk.

## Cross-Ticker Consistency

**PASS.** Alpha naming, dominant/no-dominant/conflict/no-conflict wording, Technical Details labeling, navigation, disclaimer text, and layout hierarchy are all identical in pattern across NVDA, QQQ, and SNDK. The product feels like one coherent system, not three different experiences.

## Desktop Visual Pass (1440×900)

**PASS** across Research landing, NVDA Research/Structure Graph/Conflict Radar, QQQ Research, and SNDK Research/Conflict Radar: no horizontal overflow, no clipped cards, no awkward wrapping, no overlapping text, no giant blank space, no unreadable density. Footer/disclaimer placement is consistent; Technical Details disclosures lay out cleanly both collapsed and expanded.

## Small-Viewport Sanity Pass (768×900)

The Structural Snapshot grid itself stacks correctly to a single column as designed, conflict labels stay readable, Technical Details doesn't break layout, and the footer/disclaimer stays legible. **However, a genuine, screenshot-confirmed horizontal overflow was found** on the NVDA/QQQ/SNDK Research pages (not on the landing page): long, unbroken claim-ID strings inside `<code>` elements in the Analyst findings panel (and similarly in `AlphaCard`'s own evidence claim-ID text) have no `overflow-wrap`/`word-break` rule, pushing the page to a measured `scrollWidth` of 866px against the 768px viewport. **This does not occur at the planned 1440×900 desktop demo width** — classified `MATERIAL_NONBLOCKER` (see Finding F1).

## Browser Console / Network

**0 console errors.** **26 console warnings**, 100% React Router v7 "future flag" deprecation notices — framework-level, non-application-logic, and invisible to a normal demo audience (DevTools are not open during a stakeholder demo). **24 "failed" network events**, all `net::ERR_ABORTED`, 100% attributable to the rehearsal script's own rapid, automated page-to-page navigation triggering the app's intentional, already-tested AbortController cancellation-on-unmount behavior — not a defect a human presenter clicking at normal pace would meaningfully reproduce. Both are disclosed in full per the task's own instruction not to declare readiness without disclosure, even though root-cause analysis attributes neither to a real product defect.

## Presenter Timing

An initial `networkidle`-based measurement produced misleading ~16-second figures for several pages; investigation traced this to the Vite dev server's persistent HMR WebSocket preventing true network idle, not real user-perceived latency. A corrected, content-based measurement (time until the actual first-screen content appears) was used instead:

| Page | Time to first-screen content |
|---|---|
| Research landing | 218ms |
| NVDA Research → Structural Snapshot | 676ms |
| QQQ Research → Structural Snapshot | 625ms |
| SNDK Research → Structural Snapshot | 781ms |
| NVDA Structure Graph | 412ms |
| NVDA Conflict Radar | 453ms |
| SNDK Conflict Radar | 307ms |

**Classification: `FAST`.** All pages render their core content in well under one second against already-persisted real data.

**Estimated full stakeholder-demo duration**: orientation ~0.5 min, NVDA main story ~1.5 min, NVDA evidence drill-down ~2 min, QQQ example ~1.5 min, SNDK example ~1.5 min, close ~0.5 min — **total ≈ 7.5 minutes** (range 6–9 depending on Q&A depth), within the recommended 5–10 minute target.

## What Was Not Shown By Default

Confirmed the scripted 5–10 minute sequence never requires showing: Gold acceptance JSON, `run_audit.json`, a terminal, the raw database, Provider retry logs, Replay All, Alpha Memory raw fields, raw reason codes, or internal test results. All remain available only as an optional technical deep-dive if specifically asked.

## Findings

| ID | Severity | Summary |
|---|---|---|
| F1 | **MATERIAL_NONBLOCKER** | Small-viewport (768px) horizontal overflow from unwrapped claim-ID `<code>` text in the Analyst findings panel / `AlphaCard` evidence — confirmed via screenshot (`scrollWidth` 866px vs. 768px viewport). Does not affect the planned 1440×900 desktop demo. Likely fix: add `overflow-wrap`/`word-break` to the relevant `<code>` selectors — not attempted here (read-only phase). |
| F2 | POLISH | 26 React Router v7 future-flag deprecation console warnings — framework-level, no application-logic impact. |
| F3 | POLISH | 24 `net::ERR_ABORTED` network events, entirely a rehearsal-script navigation-speed artifact of the app's own intentional request-cancellation behavior — not a product defect. |

**Blocker count: 0. Material non-blocker count: 1. Polish count: 2.**

## E2E Packaging Issue

The pre-existing, unrelated Python packaging issue in `scripts/seed_w5_demo.py` (carried forward from Phases 2B–2D) is classified **`NOT_DEMO_RELEVANT`**: the actual stakeholder demo startup path (real Postgres + `comqutor-api` + frontend) never invokes this seed script or any e2e test runner. This phase's own real-browser rehearsal independently and successfully exercised the actual demo path end-to-end, proving the blocked harness has no bearing on demo-day readiness. Not fixed in this phase.

## Final Demo Runbook

**Startup check**: Postgres available → `GET /health` → `GET /ready` → `python scripts/verify_persisted_run_serveability.py <NVDA> <QQQ> <SNDK>` (exit 0, all `FULLY_LIVE_SERVABLE`) → frontend loads.

**Demo order**: (1) `/research` — 30s orientation. (2) NVDA Research — show Structural Snapshot (dominant + main conflict). (3) NVDA Structure Graph → expand an Alpha's Evidence → Conflict Radar, for the "Why?" answer. (4) QQQ Research — show the no-dominant state and its conflict. (5) SNDK Research — show the dominant state and no-conflict state (optionally open Conflict Radar).

**Close**: return to the research-only, not-financial-advice framing (already visible throughout via the footer).

**Optional technical deep dive (only if asked)**: Technical Details disclosures; Gold v0.2 acceptance provenance (`docs/audit_artifacts/`); architecture (structure/graph/conflict engines); Provider/retry internals (discuss verbally only — not exposed in the UI).

## Two-Minute Pre-Demo Checklist

- [ ] Confirm the API process resolves `COMQUTOR_DATABASE_URL` to the real Postgres DSN (not the local SQLite fallback) — e.g. via `scripts/start_live_comqutor.sh` or an equivalent env-loaded launch.
- [ ] `curl -s http://127.0.0.1:8000/health`
- [ ] `curl -s http://127.0.0.1:8000/ready`
- [ ] `python scripts/verify_persisted_run_serveability.py <NVDA_RUN_ID> <QQQ_RUN_ID> <SNDK_RUN_ID>` (exit code 0 expected)
- [ ] Open the frontend URL, confirm `/research` loads without a visible error.
- [ ] Open the NVDA Research page, confirm the Structural Snapshot renders with a dominant Alpha and main conflict.
- [ ] Glance at the browser DevTools console for red (error) entries only — warnings are expected and benign.

---

**Gold v0.2 closure changed: no. Phase 1–2D artifacts changed: no. Product code files changed: 0. Test files changed: 0. Backend files changed: 0. Provider calls: 0. TradingAgents calls: 0. Fresh ticker runs: 0. Commits: 0. Pushes: 0. Destructive git operations: 0.**

**PRODUCT DEMO HARDENING — PHASE 3 ONLY. DEMO_READY_WITH_MINOR_CAVEATS. NO PRODUCT CODE CHANGED DURING REHEARSAL. NO RESEARCH RERUN.**
