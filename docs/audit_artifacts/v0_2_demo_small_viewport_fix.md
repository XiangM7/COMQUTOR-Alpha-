# COMQUTOR Alpha — Small-Viewport Overflow Fix and Product Demo Hardening Closure

**Product Demo Hardening — Phase 3B.** Objective: fix exactly one remaining Phase-3 finding — **F1**, a small-viewport horizontal overflow caused by an unwrapped claim-ID string — verify no regression, and close Product Demo Hardening if resolved cleanly.

## Executive Result

**PHASE 3B = PASS. PRODUCT_DEMO_HARDENING_STATUS = CLOSED. FINAL_DEMO_READINESS = DEMO_READY.**

F1 is fully resolved with a one-rule, narrowly-scoped CSS fix. No desktop regression. No backend or semantic change. Phase 2B/2C/2D behavior fully preserved. Blockers: 0. Material non-blockers: 0.

## F1 Reproduction (Before Fix)

Real-browser (Playwright/Chromium) reproduction at 768×900 — Phase 3's own recorded viewport — against the real running `comqutor-api` (Postgres-backed) and the three real persisted demo runs:

| Page | Viewport | `scrollWidth` | Overflow |
|---|---|---|---|
| Research landing | 768 | 768 | 0px (never affected) |
| NVDA Research | 768 | **866** | **98px** |
| QQQ Research | 768 | **849** | **81px** |
| SNDK Research | 768 | **948** | **180px** |
| NVDA Structure Graph | 768 | 768 | 0px (see note) |
| NVDA Conflict Radar | 768 | 768 | 0px (never affected) |

**NVDA Structure Graph note**: individual `AlphaCard` evidence-claim-ID `<code>` elements measured wide internally (up to 680px) even while their containing `<details>` was closed, but a direct expand-and-remeasure test proved this does **not** affect `document.scrollWidth` even once the disclosure is opened — confirmed not part of F1 and correctly left unmodified, per the task's "prove the offending element" and "avoid changing all `code`/technical strings unless they share the same proven layout defect" instructions.

## Exact Root Element

- **Route**: `/runs/{run_id}/research`
- **Component**: `FindingCard` (`frontend/src/pages/ResearchRunPage.tsx`) — the ordinary Positive/Negative Analyst findings card
- **Element**: `<code>{record.claim_id}</code>` inside `<p className="analyst-output-confidence">`
- **Root CSS cause**: the global `code` rule in `styles.css` sets only font/background/padding — no `overflow-wrap`/`word-break`. A `claim_id` (`"<run_id>:<agent>:<source>:claim:<n>"`, no spaces) has no default line-break opportunity, so at a narrow viewport it renders at full intrinsic width and pushes the page wider than the viewport.
- **Missing precedent**: the project already had an identical fix for this exact defect on `.unclassified-finding-card` (`overflow-wrap: anywhere`) — the plain `.analyst-output-card` base class (used by ordinary findings) had never received the same treatment.

## Implementation Fix

**One CSS rule, adjacent to the existing precedent it mirrors:**

```css
.analyst-output-card {
  overflow-wrap: anywhere;
}
```

This is the narrowest, claim-ID/metadata-value-specific fix — **not** a change to the global `code` selector, `AlphaCard`'s evidence-claim-id, Alpha ID badges, ticker symbols, headings, buttons, or navigation. Since `.analyst-output-card` is the shared base class for every finding card (ordinary and unclassified alike), this one rule closes the gap for ordinary Positive/Negative findings without touching anything else. `overflow-wrap: anywhere` only takes effect when a line would otherwise overflow — ordinary prose (which already has spaces to wrap at) is visually unaffected; the claim ID itself is never truncated, ellipsized, hidden, or altered.

**Frontend files changed**: `frontend/src/styles.css` (+16 lines: one rule + comment), `frontend/src/styles.layout.test.ts` (+17 lines: 2 new tests, following this project's own established CSS-rule-text assertion pattern), `frontend/src/pages/ResearchRunPage.test.tsx` (+20 lines: 1 new behavioral test). **Backend files changed: 0. Semantic files changed: 0.**

## Claim ID Integrity

Verified after the fix: the claim ID renders **completely** (84 characters, exact match), contains no ellipsis, and its computed `user-select` remains `auto` (fully copyable). The underlying value was never changed — this is a layout-only fix.

## Before/After Measurement

| Page | Before `scrollWidth` (768 viewport) | After `scrollWidth` | Before overflow | After overflow |
|---|---|---|---|---|
| NVDA Research | 866 | 768 | 98px | **0px** |
| QQQ Research | 849 | 768 | 81px | **0px** |
| SNDK Research | 948 | 768 | 180px | **0px** |
| Research landing | 768 | 768 | 0px | 0px |
| NVDA Structure Graph | 768 | 768 | 0px | 0px |
| NVDA Conflict Radar | 768 | 768 | 0px | 0px |

## Desktop Regression (1440×900)

**PASS.** NVDA Research, Structure Graph, and Conflict Radar all show `scrollWidth === clientWidth === 1440`, no overflow. No awkward premature wrapping, no collapsed card width, no layout shift, no new whitespace problem.

## Small-Viewport Regression (768×900)

**PASS.** Zero horizontal overflow on Research landing, NVDA Research, NVDA Structure Graph, NVDA Conflict Radar, QQQ Research, and SNDK Research — every page the task required.

## Optional Narrow-Viewport Sanity (390×844)

**PASS.** NVDA Research: `scrollWidth === clientWidth === 390`, no catastrophic overflow from the same claim-ID element at an even narrower width.

## Real-Run Verification

Confirmed against the real running server and the three real persisted runs (no `POST /api/research`, no fresh research):

- **NVDA** (`57d7b4c4-...`): dominant **A301 Revenue Expansion**, main conflict **A101 AI Expansion vs A304 Multiple Compression** — unchanged.
- **QQQ** (`f239a53f-...`): **"No single structure currently dominates."**, main conflict **A301 Revenue Expansion vs A304 Multiple Compression** — unchanged.
- **SNDK** (`e8e0f398-...`): dominant **A201 Semiconductor Supercycle**, **"No conflicts detected..."** — unchanged.

No structural or product conclusion changed.

## Phase 2B / 2C / 2D Preservation

Structural Snapshot intact; global disclaimer ("Research analysis only — not financial advice.") present on `/research`; `ReplayAllPanel` absent from `/research` and present at `/operator` with its "Operator Tools" heading. Phase 2D's jargon cleanup was not re-audited in full this phase (this CSS-only change touches no component logic or copy that could regress it) — no risk introduced.

## Test Results

- **Focused F1 tests**: 2 new tests in `styles.layout.test.ts` (CSS-rule-text assertions, this project's established pattern for verifying `styles.css` since jsdom doesn't apply real CSS) + 1 new behavioral test in `ResearchRunPage.test.tsx` — all passing.
- **Full frontend unit suite**: `npx vitest run` — **25 test files, 293 tests, 0 failed** (baseline before Phase 3B: 290/290 across 25 files; delta: +3 new tests, 0 removed, 0 failed).
- **Product-language test**: 1/1 passed.
- **TypeScript build**: `npx tsc -b` — 0 errors.
- **Production build**: `npm run build` — succeeded (66 modules transformed).

## Console / Network Interpretation

0 genuine console errors. The known React Router future-flag warnings were re-observed and are **not** classified as a new regression (unchanged from Phase 3's baseline). `net::ERR_ABORTED` network events were re-observed with the exact same signature as Phase 3 (status/graph/conflicts/history/ready endpoints cancelled by rapid automated navigation triggering the app's own intentional `AbortController` cleanup) and are **not** classified as a product failure.

## Findings Remaining

**Material non-blockers: 0.** Polish findings F2 (React Router deprecation warnings) and F3 (rehearsal-script network aborts) remain exactly as classified in Phase 3 — explicitly out of scope per this task's own instruction, unchanged, not demo-blocking.

## Final Demo Readiness

| | |
|---|---|
| NVDA | PRIMARY_READY |
| QQQ | SECONDARY_READY |
| SNDK | EDGE_CASE_READY |
| Desktop | PASS |
| Small viewport | PASS |
| Blockers | 0 |
| Material non-blockers | 0 |

**`FINAL_DEMO_READINESS = DEMO_READY`.**

## Final Runbook

**Not rewritten.** F1's fix is presentation-only (one CSS rule) and changes no step of the established sequence. Carried forward unchanged from Phase 3: the ~7.5 minute total stakeholder demo, NVDA-primary/QQQ-secondary/SNDK-edge-case roles, the two-minute pre-demo checklist, and the persisted-run demo strategy.

## Product Demo Hardening Closure

**`PRODUCT_DEMO_HARDENING_STATUS = CLOSED`.** Phase 3 found 0 blockers and exactly one material non-blocker (F1); Phase 3B resolves it cleanly with no new regression. The remaining Phase-3 polish findings do not justify another hardening phase. No Phase 3C. No Phase 4.

**Next recommended action: the actual stakeholder demo, or normal product development.**

---

**Gold v0.2 closure changed: no. Phase-3 rehearsal changed: no. Backend files changed: 0. Semantic files changed: 0. Provider calls: 0. TradingAgents calls: 0. Fresh ticker runs: 0. Commits: 0. Pushes: 0. Destructive git operations: 0.**

**PRODUCT DEMO HARDENING — PHASE 3B ONLY. F1 RESOLVED. PRODUCT DEMO HARDENING CLOSED. FINAL_DEMO_READINESS = DEMO_READY.**
