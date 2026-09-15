# COMQUTOR Alpha — Demo Sanity Cleanup

**Product Demo Hardening — Phase 2C.** Objective: remove two avoidable stakeholder-demo distractions from the normal product flow — (P1-3) make "research only / not financial advice" positioning explicit, and (P1-4) remove the operator-only Replay-All control from the normal `/research` landing page — without altering any research semantics.

## Executive Result

**PASS.** A single, stable "Research analysis only — not financial advice." statement now appears in the `AppShell` footer, visible on every page (the landing page and the full result flow) without opening a tooltip or documentation page. `ReplayAllPanel` — the operator "Reprocess saved outputs" control — no longer appears on `/research`; it has been relocated, unmodified, to a new, non-primary, un-advertised route (`/operator`), where its confirmation dialog, `POST /api/replay-all` call, and success/error handling all continue to work exactly as before. Phase 2B's Structural Snapshot remains fully intact. No backend, taxonomy, mapper, activation, graph, or conflict code was touched.

## Pre-Implementation Inspection

Before editing, `AppShell.tsx`, `ResearchPage.tsx`, `ReplayAllPanel.tsx`, `App.tsx`, `ResearchRunPage.tsx`, and `styles.css` were read in full:

- `AppShell` had no footer — only a header (brand + tagline) and a `<main>` landmark, wrapping every route in `App.tsx`. Adding one footer here makes the disclaimer automatically global and single-source-of-truth, appearing on `/research` and every `/runs/:runId/...` result page alike.
- `ReplayAllPanel` was mounted directly and unconditionally on `ResearchPage.tsx`, between the Recent Runs panel and the product explainer panel — visible to every visitor with no gating of any kind.
- No existing admin/operator/dev-only route or surface existed anywhere in the router.
- The router is a single flat `react-router-dom` `<Routes>` tree with six routes — no nested or lazy admin area to extend.

**Conclusion**: P1-3 needed one new footer element in `AppShell`. P1-4 needed one new, narrowly-scoped route (`/operator`) hosting the unmodified `ReplayAllPanel`, plus removing its mount from `ResearchPage.tsx`. Both are minimal, additive, presentation-only changes — no existing pattern needed to be reused because none existed, and none needed to be invented beyond the smallest necessary addition.

## P1-3 — Research-Only Positioning

**Exact copy**: *"Research analysis only — not financial advice."*

**Placement**: `AppShell` footer — a single, global, stable placement rendered on every route. It is **not** duplicated a second time on `ResearchRunPage` specifically: since `AppShell` wraps every page, the same footer already appears throughout the full result flow, satisfying "visible during the result flow" without repeating the exact sentence excessively (per the task's own explicit guidance against over-repetition). The statement is plain, readable text, not color-only, and requires no interaction to discover.

**Content unaffected**: no research summary text, Alpha output, conflict output, scores, evidence, API payload, research prompt, or LLM behavior was touched — this is a `styles.css` + `AppShell.tsx` presentation change only.

## P1-4 — Replay-All Separation

**Before**: `ReplayAllPanel` ("Reprocess saved outputs", triggering `POST /api/replay-all`) rendered unconditionally on the public `/research` landing page.

**After**: Relocated to a new route, `/operator` (`OperatorPage.tsx`), with an explicit heading ("Operator Tools") and explanatory copy ("Maintenance and replay utilities for persisted research runs."). The component itself, `ReplayAllPanel.tsx`, was **not modified at all** — same confirmation dialog, same `POST /api/replay-all` request, same success/failure rendering, same safe-error-copy behavior. `/research` no longer renders it or its "Reprocess saved outputs" heading.

**Access model**: directly navigable by known URL (`/operator`), **not** linked from the stakeholder-facing header or navigation, and **not** authenticated — this phase is UI separation, not access control, exactly as scoped. No "ADMIN" button was added to the normal header.

**No conflation with research/Provider execution**: `OperatorPage`'s copy and the unmodified `ReplayAllPanel` dialog still state explicitly that replay "will not rerun TradingAgents or call an LLM provider" — verified by a dedicated test asserting this exact sentence renders and that "start research" language never appears on the operator page.

**Nothing deleted**: the `ReplayAllPanel` component, the `/api/replay-all` backend endpoint, and replay semantics are all completely unchanged — confirmed via full test coverage of the relocated panel (below).

## Files Changed

**Added:**
- `frontend/src/pages/OperatorPage.tsx` — the new operator route.
- `frontend/src/components/AppShell.test.tsx` — 6 tests for the disclaimer.
- `frontend/src/pages/ResearchPage.test.tsx` — 4 tests confirming Replay-All's absence and the normal workflow's presence.
- `frontend/src/pages/OperatorPage.test.tsx` — 7 tests confirming Replay-All's full functional preservation at its new location.

**Modified:**
- `frontend/src/components/AppShell.tsx` — +3 lines (one `<footer>` with the disclaimer).
- `frontend/src/pages/ResearchPage.tsx` — −3 lines (removed the `ReplayAllPanel` import and mount only).
- `frontend/src/App.tsx` — +2 lines (one import, one new route). All six pre-existing routes unchanged.
- `frontend/src/styles.css` — +18 lines, purely additive `.app-footer`/`.app-disclaimer` rules reusing existing design tokens.

**Backend files changed: 0. Backend API schema changed: no. Alpha taxonomy / mapper / activation / graph / conflict / evidence semantics: unchanged. Replay-All backend endpoint: unchanged, not deleted.**

## Routes Changed

Added: `/operator → OperatorPage`. Removed: none. Unchanged: `/research`, `/runs/:runId/processing`, `/runs/:runId/research`, `/runs/:runId/structure`, `/runs/:runId/conflicts`, `*`. No authentication was added or implied.

## Product Language Safety

The existing global `productLanguage.test.ts` scanner (which checks every source file for banned phrases like "guaranteed return", "risk-free", etc.) still passes — 1/1 — covering the two new pages and the new disclaimer text. The new copy was additionally checked for "guaranteed", "risk-free", "buy", "sell", and "should invest" in a recommendation sense: none found. No app-wide P1-2 jargon cleanup was attempted.

## Accessibility & Responsive Behavior

The disclaimer is plain text (a `<p>` element), not color-dependent, and renders identically on desktop and mobile. `OperatorPage` uses a semantic `h1` heading, and its controls (the relocated `ReplayAllPanel`) retain their existing labels and `role="dialog"`/`aria-modal`/`aria-labelledby` confirmation behavior unchanged. No horizontal overflow was introduced; no layout system redesign occurred.

## Phase-2B Regression Check

Explicitly re-run this phase: `ResearchRunPage.test.tsx` — **47/47 passed**; `StructuralSnapshot.test.tsx` — **14/14 passed**. Active Alpha structures, dominant/no-dominant state, and main-conflict/no-conflict state all continue to render exactly as verified in Phase 2B.

## Test Results

- **Focused Phase-2C tests** (`AppShell.test.tsx`, `ResearchPage.test.tsx`, `OperatorPage.test.tsx`): **17/17 passed.**
- **Product-language test**: **1/1 passed.**
- **Full frontend unit suite**: `npx vitest run` — **24 test files, 269 tests, 0 failed, 0 new regressions.**
- **TypeScript build**: `npx tsc -b` — **0 errors.**
- **Production build**: `npm run build` — **succeeded** (65 modules transformed, 636ms).
- **Relevant e2e** (`e2e/w5-demo.spec.ts`): **blocked** by the same pre-existing, unrelated Python packaging issue documented in the Phase-2B audit (`scripts/seed_w5_demo.py`: `ModuleNotFoundError: No module named 'scripts'`). Identical failure signature — confirmed not introduced or worsened by this phase. Not fixed, per this phase's explicit instruction not to modify unrelated Python packaging.

## Zero-Provider Proof

0 Provider calls, 0 TradingAgents calls, 0 fresh ticker runs, 0 `POST /api/research` calls. The only `POST /api/replay-all` invocations anywhere in this phase's work are inside mocked frontend tests (`vi.spyOn`) — never against a running server or real persisted data.

## Phase 2C Success Criteria

| Criterion | Met |
|---|---|
| Research-only/not-financial-advice positioning clearly visible | Yes |
| ReplayAllPanel absent from normal `/research` | Yes |
| Replay-All capability remains available for operators | Yes |
| Normal research workflow unchanged | Yes |
| Phase-2B Structural Snapshot intact | Yes |
| No backend changes | Yes |
| No semantic changes | Yes |
| Frontend tests/build pass | Yes |
| No new regressions | Yes |

**Overall: PASS.**

## Next Recommended Phase

**Product Demo Hardening — Phase 2D: default-view jargon cleanup** — translate/hide `regime_level`, `candidate`, "B2 Conflict Evidence Admissibility", raw reason codes, and `Alpha Memory`/`SHADOW`/`phi_id` from normal stakeholder views, while preserving an advanced technical path where useful. **Not implemented in this phase.**

---

**Gold v0.2 closure changed: no. Phase-1 audit changed: no. Phase-2A artifact changed: no. Phase-2B artifact changed: no. Backend files changed: 0. Semantic files changed: 0. Provider calls: 0. TradingAgents calls: 0. Fresh ticker runs: 0. Commits: 0. Pushes: 0. Destructive git operations: 0.**

**PRODUCT DEMO HARDENING — PHASE 2C ONLY. DEMO DISTRACTIONS REMOVED. NO SEMANTICS CHANGED. NO RESEARCH RERUN.**
