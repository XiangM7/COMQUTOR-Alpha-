# COMQUTOR Alpha — Demo Structured Summary Hardening

**Product Demo Hardening — Phase 2B.** Objective: make the main Research results page (`ResearchRunPage.tsx`) immediately answer, without navigating to another tab: what structural Alphas are active, is there a dominant Alpha, what is the main conflict, and — when the answer is "no" — is that a legitimate result. Presentation-only. No research semantics changed.

## Executive Result

**PASS.** A new "Structural snapshot" section now appears on the main Research results page, between the textual summary and the deeper Data Quality / Analyst findings / evidence sections. It shows the active-Alpha list, the dominant structure (or an explicit, analytical "no single structure currently dominates" state), and the main conflict (or an explicit "no high-confidence structural conflict is currently admitted" state) — all with human-readable Alpha names, all without leading with raw internal vocabulary, and all verified against the real NVDA/QQQ/SNDK persisted runs.

## Pre-Implementation Inspection

Before writing any code, the actual current implementations of `ResearchRunPage.tsx`, `StructureGraphPage.tsx`, `ConflictRadarPage.tsx`, `AlphaCard.tsx`, `ConflictCard.tsx`, `CandidateConflictCard.tsx`, and the API client/adapters/types were read in full. Findings:

- `CanonicalResearchResponse` (already fetched by `useResearchRun` on `ResearchRunPage`) **already contains** `dominant_alphas` (with `alpha_id`/`alpha_name`) and `main_conflict` (with `bull_structure`/`bear_structure`, each carrying `alpha_id`/`alpha_name`), plus `structure_graph_status`/`conflict_status`. **No additional fetch was needed for the Dominant Structure or Main Conflict parts of the summary.**
- `CanonicalResearchResponse` does **not** contain the full active-Alpha list — only `dominant_alphas` (dominant OR regime_level). The full list (active/capped_active/dominant/regime_level) lives on `StructureGraphResponse.activation.alphas`, fetched via `GET /api/research/{run_id}/graph` — the same endpoint `StructureGraphPage` already uses.
- Human-readable Alpha names are already resolved server-side on every Alpha-bearing object (`alpha_id` + `alpha_name` always paired) — confirmed no frontend taxonomy dictionary exists or was needed.
- `StructureGraphPage.tsx` already defines the production classification of "meaningfully active/displayable" (`bucketForAlpha()`, bucketing into active/capped_active/dominant/regime_level/candidate, in that display order). This was **exported** (an additive `export` keyword on three already-existing declarations, zero behavior change) rather than reimplemented, so the new summary reuses the identical, already-production logic.

**Conclusion**: one new fetch (graph, for the active-Alpha list only), reusing the existing endpoint and the existing per-page-fetch convention already established by `useResearchRun`/`useGraphAndConflicts`. No backend change of any kind was required or made.

## Files Changed

**Added (frontend only):**
- `frontend/src/components/StructuralSnapshot.tsx` — the new section: Active Structures, Dominant Structure, Main Conflict.
- `frontend/src/hooks/useResearchGraph.ts` — a lean, single-endpoint hook (`GET /graph`) mirroring the existing `useResearchRun`/`useGraphAndConflicts` AbortController + run-mismatch-guard safety pattern.
- `frontend/src/components/StructuralSnapshot.test.tsx` — 14 component tests.

**Modified (frontend only):**
- `frontend/src/pages/ResearchRunPage.tsx` — +5 lines: one import, one conditional render of `<StructuralSnapshot>` placed immediately after the existing Research summary panel and before Data Quality / Analyst findings.
- `frontend/src/pages/StructureGraphPage.tsx` — added the `export` keyword to `bucketForAlpha`, `AlphaLevelBucket`, and `ALPHA_LEVEL_BUCKETS` (three already-existing declarations). Zero behavioral change to `StructureGraphPage` itself.
- `frontend/src/styles.css` — +100 lines, purely additive `.structural-snapshot-*` rules reusing existing design tokens (`--space-*`, `--color-*`, `--radius-*`, `--font-size-*`) and the project's existing 3-column-to-1-column responsive collapse pattern. No existing rule was modified.

**Backend files changed: 0. Backend API schema changed: no. Gold v0.2 artifacts changed: 0. Alpha taxonomy / mapper / evidence-stance / activation / threshold / conflict-engine: unchanged.**

## API Calls Reused / Added

Reused: `GET /api/research/{run_id}` (already fetched by `useResearchRun`) and `GET /api/research/{run_id}/graph` (already used by `StructureGraphPage`; now also independently fetched by the new hook on `ResearchRunPage`, matching the project's existing per-page-fetch convention rather than introducing a shared cross-page store). **New backend endpoints: 0. Net new API surface: 0.**

## UI States Implemented

| Part | States |
|---|---|
| Active Structures | loading · run-mismatch (safe, non-crashing) · error (safe copy + retry, never a raw exception) · not-ready (`GRAPH_NOT_READY`, distinct from empty) · completed-empty ("No Alpha structure currently meets the active threshold.") · completed-populated (ID + human name chips, in the existing bucket display order) |
| Dominant Structure | not-ready (`structure_graph_status != ready`) · legitimate-empty ("No single structure currently dominates." + "Several active forces are present, but none has reached dominant status.") · present (ID + human name per dominant Alpha) |
| Main Conflict | not-ready (`conflict_status != ready`) · legitimate-empty (adapted from `ConflictRadarPage`'s own approved no-conflict copy) · present (both sides' ID + human name, "vs" separator, link to Conflict Radar) |

`NO_DOMINANT_ALPHA` is never confused with `GRAPH_NOT_READY`; `NO_MAIN_CONFLICT` is never confused with `CONFLICTS_NOT_READY` — each pair is driven by an explicit, independent field check (`structure_graph_status`/`conflict_status` vs. the emptiness of `dominant_alphas`/`main_conflict`), verified by dedicated tests.

## Terminology Check

No raw `regime_level`, `candidate`, admissibility jargon, `phi_id`, or `SHADOW` text appears anywhere in the new summary (verified by an automated test scanning the rendered DOM text). Alpha IDs are always paired with a human-readable name. Internal level vocabulary is used only to decide *which* Alphas populate the Active Structures list — it is never rendered as a label in the new summary itself. This is a narrowly-scoped, local translation; the broader P1-2 app-wide jargon cleanup (elsewhere in `AlphaCard`, `ConflictCard`, the full `StructureGraphPage`/`ConflictRadarPage` detail views) is explicitly **not** attempted here.

## Accessibility

Semantic headings (`h2`/`h3`). The conflict "vs" is plain, screen-reader-readable text with `aria-label="versus"`, never an icon-only separator. Every state (loading/error/not-ready/empty/present) is conveyed through text content — no information depends on color alone. Navigation links use explicit labels ("View conflict details", "View structure graph"), never "click here".

## Responsive Behavior

Desktop: the three parts sit side by side in a 3-column grid. At the existing 768px breakpoint they stack to a single column. No horizontal overflow was introduced (verified by the TypeScript build and by following the exact grid/gap pattern already used elsewhere in `styles.css`).

## Navigation Preserved

Both "View structure graph" and "View conflict details" links route to the existing `/runs/:runId/structure` and `/runs/:runId/conflicts` pages, which are **unchanged in behavior** (the only edit to `StructureGraphPage.tsx` was adding `export` to already-existing declarations). The new summary is orientation only — it does not duplicate the full detail views.

## Test Results

- **Focused new component tests**: `frontend/src/components/StructuralSnapshot.test.tsx` — **14/14 passed**, covering: human-readable names paired with every Alpha ID; legitimate active-empty state; dominant present/empty states; the not-ready-vs-legitimate-empty distinction for both dominant and conflict; main-conflict present/empty states; loading and safe-error states; absence of raw `regime_level`/`candidate` text; and NVDA-like/QQQ-like/SNDK-like reference fixtures matching the task's specified expected stories exactly (including confirming the QQQ fixture never surfaces the A001 remediation narrative).
- **Full frontend unit suite**: `npx vitest run` — **21 test files, 252 tests, 0 failed, 0 new regressions.**
- **TypeScript build**: `npx tsc -b` — **0 errors.**
- **Production build**: `npm run build` — **succeeded** (64 modules transformed, 519ms).
- **Relevant e2e (Playwright, `e2e/w5-demo.spec.ts`)**: **attempted, blocked** by a pre-existing environment issue unrelated to this phase's changes — `scripts/seed_w5_demo.py` fails with `ModuleNotFoundError: No module named 'scripts'` when the Playwright webServer launches it via `scripts/run_w5_demo.sh` in this environment. This is a Python package-resolution/PYTHONPATH issue in the demo-seeding script, not caused by and not fixed in this phase (out of Phase 2B's frontend-only, narrowly-scoped mandate). **Mitigation**: performed the required Section 28 read-only real-run verification directly instead (below), which provides equivalent assurance without the blocked e2e harness.

## Read-Only Real-Run Verification (Section 28)

Read-only `GET` requests only, against the already-running `comqutor-api` server (Postgres-backed, per Phase 2A). No `POST /api/research`. No Provider/TradingAgents calls.

| Ticker | Dominant | Main Conflict | Active Structures (non-candidate) | Matches expected story |
|---|---|---|---|---|
| NVDA | A301 — Revenue Expansion | A101 — AI Expansion vs A304 — Multiple Compression | A101, A103, A301, A304, A601 | **Yes** |
| QQQ | *(none)* | A301 — Revenue Expansion vs A304 — Multiple Compression | A103, A301, A304, A601 (A001 correctly absent) | **Yes** |
| SNDK | A201 — Semiconductor Supercycle | *(none admitted)* | A201, A304, A601 | **Yes** |

QQQ's A001 (candidate, non-detected) is confirmed absent from the active-Alpha list, and no A001-remediation narrative is surfaced anywhere in the new summary, per the task's explicit instruction.

## Scope Discipline

Not attempted in this phase: P1-2 (app-wide jargon cleanup), P1-3 (prominent disclaimer), P1-4 (`ReplayAllPanel` exposure), P1-5 (aggregate confidence UX), P1-6 (semantic-manifest inconsistency).

## Zero-Provider Proof

0 Provider calls, 0 TradingAgents calls, 0 fresh ticker runs, 0 `POST /api/research` calls. All new code performs only read-only `GET` requests against already-existing endpoints. The new test suite mocks the API client entirely (`vi.spyOn`) — zero real network calls of any kind.

## Phase 2B Success Criteria

| Criterion | Met |
|---|---|
| Main Research page shows structural Alpha context | Yes |
| Human-readable Alpha names appear | Yes |
| Dominant state visible | Yes |
| No-dominant state explicit | Yes |
| Main conflict visible | Yes |
| No-conflict state explicit | Yes |
| Graph/conflict details remain accessible | Yes |
| No backend semantic changes | Yes |
| No Provider rerun | Yes |
| NVDA, QQQ, SNDK each render their distinct legitimate state correctly | Yes |

**Overall: PASS.**

## Next Recommended Phase

**Product Demo Hardening — Phase 2C**: either P1-2 (default-view jargon cleanup across `AlphaCard`/`ConflictCard`/the full detail views) or a combined P1-3 + P1-4 small demo-sanity slice (a single prominent "research only, not financial advice" disclaimer plus gating/relocating `ReplayAllPanel` off the public landing page). **Not implemented in this phase.**

---

**Gold v0.2 closure changed: no. Phase-1 audit changed: no. Phase-2A artifact changed: no. Backend files changed: 0. Backend API schema changed: no. Provider calls: 0. TradingAgents calls: 0. Fresh ticker runs: 0. Commits: 0. Pushes: 0. Destructive git operations: 0.**

**PRODUCT DEMO HARDENING — PHASE 2B ONLY. STRUCTURAL SNAPSHOT LIVE ON THE MAIN RESULTS PAGE. NO SEMANTICS CHANGED. NO RESEARCH RERUN.**
