# COMQUTOR Alpha — Product Demo Readiness Audit

**Phase: Product Demo Hardening — Phase 1 (Audit Only).** Gold v0.2 acceptance is closed (`v0_2_final_acceptance_closure.json`, SHA256 `51f7d2e047b844dd1ff3ce3ceeb35cd94b4966ff8a43eeb2c2ff5d4d4ca2cf10`, `release_blocking_status=PASS`, `overall_closure_status=PASS_WITH_REVIEW`) and is **not reopened** by this audit. This document evaluates a different, orthogonal question: is the *product/demo experience* — the actual UI a stakeholder would see — clear, reliable, fast enough, and credible? A system can be semantically accepted (Gold v0.2 PASS) while still having demo-UX gaps; that is exactly the situation found here. Read-only: 0 production code changes, 0 test changes, 0 Provider calls, 0 TradingAgents calls, 0 fresh ticker runs.

## Executive Assessment

**`DEMO_READY_WITH_HARDENING`**

The underlying data model is strong: evidence traceability is genuinely rich (claim text, agent, source, direction, ticker attribution, timestamp all present), progress/loading UX is well-instrumented (real percent/ETA/stage checklist, never a fake timer), error handling is careful (curated safe copy, no raw dumps found), and human-readable Alpha names are already threaded through the API and UI (not merely a docs convenience). But several concrete, bounded gaps would materially hurt a stakeholder demo today: the core "what does the system see and why" story is split across three separate tabs instead of appearing on the results page; internal jargon (`regime_level`, `candidate`, "B2 Conflict Evidence Admissibility gate", `Alpha Memory`/`SHADOW`/`phi_id`) leaks into the default view; an operator-flavored batch-reprocess panel sits unguarded on the public landing page; and — most importantly — this audit empirically found that the QQQ post-fix run's live API/DB state currently can't serve its own graph/conflict data despite complete file artifacts, which would look broken live even though nothing is wrong with the underlying research. None of this touches Alpha taxonomy, mapping semantics, activation thresholds, or Gold behavior — it is presentation and serving-infrastructure work.

## Current Demo Flow

**Startup**: backend via the `comqutor-api` console script (`uvicorn` on `127.0.0.1:8000` by default, never `0.0.0.0`), requiring `COMQUTOR_CORS_ORIGINS` to be explicitly set (no wildcard permitted) and falling back to local SQLite if no `COMQUTOR_DATABASE_URL` is configured. Frontend via Vite dev server fixed at `127.0.0.1:5175`. There is no combined Docker service for the COMQUTOR API/frontend today (`docker-compose.yml` only defines the upstream TradingAgents CLI container and an optional Postgres profile). A live research run additionally requires `COMQUTOR_REAL_TRADINGAGENTS_ENABLED`/`COMQUTOR_WEEK2_LLM_ENABLED`, set only from an operator shell — by design, not toggleable from the UI.

**User flow stages**:

| Stage | Module | Visible? | Latency | Demo Risk |
|---|---|---|---|---|
| Ticker input | `ResearchForm.tsx` | Yes | instant | LOW |
| Request submission | `useResearchSubmission.ts` → `POST /api/research` | Yes | instant (async job queue) | LOW |
| TradingAgents research/debate | orchestration layer | Indirect (progress stage) | ~3m20s | LOW — well-instrumented |
| Structured claims extraction | Week2 LLM `structured_adapter` | Indirect | ~9m57s | LOW |
| Alpha mapping + evidence-stance classification | `alpha_mapper.py`, `evidence_stance_llm.py` | Indirect | **~38m45s (~74% of total)** | **MEDIUM** — one static message for ~39 minutes |
| Graph build / activation / conflict / audit | `graph_engine/*`, `conflict_engine/*` | Indirect | ~3 seconds | LOW |
| Final result presentation | `ResearchRunPage.tsx` / `StructureGraphPage.tsx` / `ConflictRadarPage.tsx` | Yes | — | **HIGH** — see P0 findings |

Terminal/manual intervention points: enabling live execution requires an operator shell (by design); there is no discoverable UI affordance today for a presenter to reliably "load a known-good persisted run" beyond the Recent Runs table (which is not framed as a demo tool) or knowing a `run_id` to navigate to directly.

## What the User Sees

| Element | Status |
|---|---|
| Ticker | GOOD |
| Structural thesis / summary | GOOD |
| Alpha list | PRESENT_BUT_UNCLEAR — only on the separate Structure Graph tab |
| Dominant Alpha | PRESENT_BUT_UNCLEAR — already fetched into the page's data, just not rendered on the main Research tab |
| Main conflict | PRESENT_BUT_UNCLEAR — already fetched, only rendered on the separate Conflict Radar tab |
| Evidence per Alpha | GOOD — claim text, agent, match score, relation, assertion status, claim ID all shown |
| Evidence against thesis | GOOD — a populated `counter_evidence` mechanism exists and renders in real runs |
| Confidence / uncertainty | PRESENT_BUT_UNCLEAR — scattered per-claim percentages, no single aggregate indicator |
| Invalidation conditions | GOOD UI, honest gap underneath — dedicated section with an honest "not yet approved" fallback; but only **one** Alpha (A101) currently has an approved invalidation-conditions entry, so most tickers will show the fallback state |
| "Research only" positioning | PRESENT_BUT_UNCLEAR — no single prominent disclaimer; scattered tagline/explainer copy plus a test guardrail blocking overclaiming phrases |

**Internal fields at risk of leaking to users** (Section 8/23 classification): `regime_level` and `candidate` are shown as literal activation-level values, not just section titles (TRANSLATE); "B2 Conflict Evidence Admissibility gate" appears verbatim in user-facing prose (HIDE the internal name); raw Alpha IDs appear alone in conflict titles and "Target Alpha: {id}" labels without a paired name (should always pair — currently TRANSLATED inconsistently); "Entity Exposure"/"Alpha Memory"+"SHADOW" badge/`phi_id` are shown with no glossary (OPTIONAL_ADVANCED_VIEW candidates, some already gated behind `<details>`); raw reason codes are shown in parentheses alongside humanized labels (keep humanized, move raw code to the existing advanced disclosure only). Provider failures/retries are correctly never exposed (HIDDEN by construction, not just UI filtering).

## Frontend Architecture

React 18.3.1 + TypeScript 5.6.3 (strict mode) + Vite 5.4.8, `react-router-dom` 6.26.2, no UI component library (hand-written CSS, dark-mode + reduced-motion aware, responsive at 640/768/1024px breakpoints). No global state store — local component state plus small custom hooks (`useResearchSubmission`, `useRunPolling`, `useResearchRun`); cross-page continuity relies on `run_id` in the URL. API client (`api/client.ts`) resolves its base URL from `VITE_COMQUTOR_API_BASE_URL`, defaulting to same-origin — no hardcoded `localhost` anywhere in `src/`. Every response is validated through `adapters.ts` before use. Loading UX is genuinely good: real backend-driven progress percent, ETA range, elapsed time, and an ordered stage checklist. Error UX is centralized and careful — curated safe copy, `ErrorPanel` never renders raw error objects or stack traces. One flagged item: `ReplayAllPanel`, an operator-flavored batch-reprocess action, sits unguarded on the public `/research` landing page.

## Backend / API Contract

`POST /api/research` is a fully asynchronous job-queue endpoint — it returns `{run_id, status, cache_disposition, ...}` immediately (200/202, or a mapped 4xx/5xx for configuration/validation errors) and never blocks the request thread on the pipeline. `GET /api/research/{run_id}/status` is a rich, DB-only polling contract (percent, stage, ETA, elapsed). `GET /api/research/{run_id}` is the full canonical result, fail-closed to `status="partial"` unless graph, conflict, ticker-consistency, and artifact-completeness checks all pass. **`GET /api/alpha-library` already exposes the full Alpha ID → human name (`name_en`/`name_cn`) + description + invalidation-conditions + conflict-pair mapping** — the human-readable translation layer exists at the API boundary today, not only in docs. Provider reliability data (the authoritative Step 7B.3 figures: 617 requests, 25 timeouts, 9 validation failures, 34 recoverable semantic-critical events, 0 fatal failures) is recorded only in an internal, non-API-exposed sidecar file — a normal client has zero visibility into retry noise, by construction. Security/sanity: no hardcoded absolute paths, an explicit scrubber strips path/credential/traceback-shaped substrings from any warning detail before it reaches a client, no `debug=True`, `.env` correctly gitignored/untracked, CORS defaults closed.

**Critical finding**: this audit empirically confirmed (read-only GET calls, no Provider/TradingAgents calls) that the QQQ post-fix run `f239a53f-4ebe-455c-bb76-5f5485903901` has complete, internally-consistent file artifacts on disk, but its rows are **missing from the current DB**. Since `/status`, `/graph`, and `/conflicts` are DB-only reads with no file fallback, calling them against this run returns `RUN_STATUS_NOT_FOUND`/`GRAPH_NOT_READY`/`CONFLICTS_NOT_READY`, and the full result downgrades to `status="partial"`, `main_conflict=null`, `dominant_alphas=[]`. **This does not affect Gold v0.2 acceptance validity** — Gold's authority is the file artifacts, read directly, exactly as this entire acceptance process has done throughout — but it is a direct demo-breaking risk if this run_id is opened live via the UI. Whether NVDA/SNDK have the same gap was not verified in this pass and should be checked before demo day.

## Evidence Traceability

A single claim record already carries: claim excerpt (`claim`), agent/source role (`agent`, `output_type`), source/citation (`source_type`, `source_section`, `source_agent_output_id`), direction (`direction`, `semantic_polarity`, `assertion_status`), ticker attribution (`ticker`, `entities`), and an ISO8601 `timestamp`. This is already fully available — no new semantics are required to answer "why are you saying this?" for any Alpha. Opposing evidence is likewise already computed and populated (`evidence_ui.counter_evidence`, confirmed non-empty in the real QQQ run).

## Structural Summary / Conflict Presentation

Compared against the ideal hierarchy (WHAT the system sees → WHY → structural conflict → risks/invalidation → evidence → optional technical detail), the current product has all the *pieces* but not the *hierarchy*: Alpha list, dominant Alpha, and main conflict live on separate tabs rather than a single top-level summary, so a viewer must actively navigate to reconstruct the story the hierarchy implies. No duplicated-information or raw-agent-report-leakage issues were found; the main gap is ordering/consolidation, not missing content.

## Invalidation / Risk Presentation

`AVAILABLE_NOW` at the presentation layer for opposing evidence (counter_evidence is already computed and renderable). For formal "approved" invalidation conditions specifically, the underlying registry is `AVAILABLE_WITH_PRESENTATION_ONLY` for exactly one Alpha (A101, approved by "John," v0.1) and `REQUIRES_NEW_SEMANTICS`-adjacent-but-really-just-content-work (human/product sign-off, not new code logic) for every other Alpha — the UI's honest fallback messaging for `not_defined` entries is already correct behavior, it simply means most demo tickers will show the fallback state today.

## Latency and Progress UX

Total wall clock for the QQQ post-fix run: **~52 minutes 21 seconds** (~3141s, consistent with the ~3140s figure already on record), broken down as: TradingAgents debate ~3m20s, structured-claims extraction ~9m57s, **Alpha mapping + evidence-stance classification ~38m45s (~74% of total — the dominant latency source)**, deterministic graph/activation/conflict assembly ~3 seconds. The progress bar, percent, ETA range, and stage checklist are all real and backend-driven (never a fake timer) — but during the dominant ~39-minute semantic-classification stage, the viewer sees only one static stage message the entire time, which is the main risk of a viewer perceiving the app as frozen despite the numeric progress indicators still moving.

## Failure-State UX

Errors are consistently funneled through curated, safe copy (`ErrorPanel`, never a raw dump). The two most notable gaps: (1) a contract-mismatch error surfaces a dev-facing instruction ("check `VITE_COMQUTOR_API_BASE_URL`") that a non-technical viewer couldn't act on; (2) there is no explicit "no single structure dominates" empty-state message when `dominant_alphas` is empty (confirmed real state for QQQ), whereas the analogous "no admitted conflict" state (confirmed real for SNDK) *does* already have good, confident copy ("No conflicts detected... This does not mean the position carries no risk."). The missing-DB-row scenario (see Backend / API Contract) is the most severe failure mode found — a fully successful run can present as broken/partial live.

## Demo Mode Options

| Mode | Latency | Credibility | Failure Risk | Recommendation |
|---|---|---|---|---|
| LIVE_FULL_RESEARCH | ~52 min | High if it works, low if it stalls | High for a time-boxed live setting | Not recommended as the primary path |
| PERSISTED_RUN_DEMO | seconds | Medium-high, framed honestly | Low, contingent on the P0 DB fix | Recommended as the backbone |
| HYBRID_DEMO | instant primary + optional ~52 min | High | Low for the primary path | **Recommended overall** — lead with a persisted run, offer a live run only as an optional, time-expectation-set closer |

## Recommended Demo Tickers

- **Primary: NVDA** (`57d7b4c4-dbb9-4134-b962-ee2a873941cc`) — dominant Alpha (A301 Revenue Expansion, 78.49), 4 other active Alphas, 3 admitted conflicts with a clear main conflict (A101__A304), full evidence traceability. Chosen for having the most complete, legible structure — not for being bullish.
- **Secondary: QQQ** (`f239a53f-4ebe-455c-bb76-5f5485903901`) — **USABLE_WITH_CAVEAT**. Good "no dominant Alpha, real conflict" story and the product's own A001 remediation narrative if wanted, but requires resolving the DB-availability gap first and honestly disclosing the A301-evidence-strength REVIEW diagnostic if probed.
- **Edge case: SNDK** (`e8e0f398-7b26-4462-8135-a1410ea5b335`) — dominant Alpha (A201 Semiconductor Supercycle, 84.22) but **zero admitted conflicts** — a legitimate, valuable state to show deliberately rather than avoid, per the guidance not to assume every ticker has a main conflict.
- MSFT/TSM/AMD were not inspected in this pass (optional per task scope); MSFT specifically is not recommended given its known Silver-tier FAIL/REVIEW findings.

## Known Technical Debt and Demo Relevance

| Item | Classification |
|---|---|
| 39 synthetic replay test errors (`tests/replay/conftest.py`) | NOT_DEMO_RELEVANT |
| Alpha Match accuracy 83.00% | DEMO_RELEVANT_NONBLOCKING |
| Polarity accuracy 85.25% | DEMO_RELEVANT_NONBLOCKING |
| MSFT Silver FAIL/REVIEW | NOT_DEMO_RELEVANT (MSFT not a recommended demo ticker) |
| QQQ A301__A304 conflict diagnostic REVIEW | DEMO_RELEVANT_NONBLOCKING — the reason QQQ is USABLE_WITH_CAVEAT, not GOOD_DEMO_CASE |

## P0 / P1 / P2 Hardening Backlog

**P0 (demo-breaking)**
1. Resolve the DB-availability gap for the QQQ post-fix run (complete file artifacts, missing DB rows → live API reports NOT_FOUND/NOT_READY). Backend, SMALL-MEDIUM scope, semantic-risk NONE, no Provider rerun needed.
2. Verify (and if needed backfill) live-servability for every run_id actually chosen for the stakeholder demo before demo day. Backend, SMALL scope, semantic-risk NONE.

**P1 (materially improves clarity/reliability)**
1. Surface Alpha list / dominant Alpha / main conflict on the primary Research results page instead of requiring tab navigation. Frontend, MEDIUM, PRESENTATION_ONLY, semantic-risk NONE.
2. Translate/hide default-view jargon (`regime_level`, `candidate`, "B2 Admissibility gate", raw reason codes, Alpha Memory/SHADOW/phi_id). Frontend, MEDIUM, PRESENTATION_ONLY, semantic-risk NONE.
3. Add one prominent "research only, not financial advice" disclaimer. Frontend, SMALL, PRESENTATION_ONLY, semantic-risk NONE.
4. Gate or relocate `ReplayAllPanel` off the public landing page. Frontend, SMALL, semantic-risk NONE.
5. Add a single aggregate confidence/uncertainty indicator per Alpha/thesis. Likely frontend-only, MEDIUM, semantic-risk LOW (display-only, must never feed back into Gold thresholds).
6. Root-cause the `llm_semantic_manifest.json` `complete:false` inconsistency on an otherwise-successful run. Backend, SMALL, INFRASTRUCTURE, semantic-risk NONE.

**P2 (polish / future optimization)**
1. Expand the approved Invalidation Conditions registry beyond A101 (content/sign-off work, not code). PRODUCT_LOGIC, semantic-risk LOW.
2. Investigate caching/deduplication/batching for the semantic-classification stage that dominates ~74% of run latency — explicitly **not** to be implemented without a fresh Provider-run validation, since anything touching classification call patterns could alter which evidence qualifies. INFRASTRUCTURE/SEMANTIC_LOGIC boundary, semantic-risk MEDIUM if done carelessly, NONE if purely a byte-identical caching layer.
3. Progressive rendering of results as scoring completes. Low priority given already-good progress UX.

## Recommended First Implementation Slice

**Structured top-level result summary on the primary Research results page** — render the Alpha list, dominant Alpha, and main conflict directly on `ResearchRunPage.tsx` using data already fetched into the page's `research` object but currently unrendered there, instead of requiring navigation to the separate Structure Graph / Conflict Radar tabs.

This directly fixes the single biggest first-impression clarity gap (P1-1), is entirely frontend and **PRESENTATION_ONLY**, requires **no taxonomy or backend change**, requires **no Provider rerun**, and is fully testable locally against the existing NVDA/QQQ/SNDK persisted runs. **Caveat**: this slice does not address the P0 DB-availability gap — that should be investigated and resolved in parallel (or first), since it affects whether any of these tickers can even be opened live via the UI/API today, independent of how the results page is laid out.

---

**Gold v0.2 closure changed: no. Production files changed: 0. Test files changed: 0. Provider calls: 0. TradingAgents calls: 0. Fresh ticker runs: 0. Product Demo Hardening implementation started: NO. Product Demo Hardening audit started: YES. Commits: 0. Pushes: 0. Destructive git operations: 0.**

**PRODUCT DEMO HARDENING — PHASE 1 (AUDIT) ONLY. NO PRODUCT CODE MODIFIED. GOLD v0.2 ACCEPTANCE NOT REOPENED.**
