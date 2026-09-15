# COMQUTOR Alpha — Demo Jargon Cleanup

**Product Demo Hardening — Phase 2D.** Objective: translate or hide internal engineering vocabulary from the normal stakeholder experience while preserving every raw value verbatim under an explicit advanced/technical-details path. Core principle: **default view = product language, technical details = original internal language.** No auditability deleted. No semantics altered.

## Executive Result

**PASS.** A single shared, pure formatter (`formatActivationLevelForDisplay`) now translates every activation-level value shown to a stakeholder (`dominant`/`regime_level` → "Dominant", `active`/`capped_active` → "Active", `candidate` → "Emerging", `watch` → "Watchlist", `inactive` → "Inactive"). Raw reason codes, `B2`/admissibility pipeline-stage language, `SHADOW`, and `activation_modulation_applied` no longer lead the default view anywhere in the app — each is preserved verbatim inside a context-local "Technical details" disclosure. A real-run verification pass against all three demo tickers on the live system confirmed every audited term is now `TECHNICAL_ONLY` or `NOT_PRESENT` — zero `VISIBLE_DEFAULT` occurrences remain — and that verification pass itself caught and fixed one genuine remaining leak (`NO_LOCAL_STRUCTURE_SUPPORT` on `StructureGraphPage`'s Blocked-alphas list) before this phase closed.

## Jargon Inventory (Before)

A frontend-wide `grep` for every listed term (plus a broader sweep) found real, confirmed user-visible leaks in:

| Term / Pattern | Location | Classification |
|---|---|---|
| Raw activation level (`regime_level`/`candidate`/`capped_active`/etc.) | `AlphaCard.tsx` main level row, `ConflictCard.tsx` `activationLevelText()`, `StructureGraphPage.tsx` Blocked-alphas badge | TRANSLATE |
| Raw reason codes in parentheses | `AlphaCard.tsx` Qualification ceiling / Score was capped / Cap reason rows; `StructureGraphPage.tsx` Blocked-alphas Reason line | HIDE_DEFAULT_SHOW_TECHNICAL |
| Raw level tokens embedded in prose | `AlphaCard.tsx` Target level / Blocked rows | TRANSLATE |
| Raw `regime_gate_failures` codes | `AlphaCard.tsx` Regime qualification row | HIDE_DEFAULT_SHOW_TECHNICAL |
| `B2` / Conflict Evidence Admissibility | `CandidateConflictCard.tsx` default copy | HIDE_DEFAULT_SHOW_TECHNICAL |
| Raw admissibility scores/counts/reason codes | `CandidateConflictCard.tsx` always-visible `<dl>` | HIDE_DEFAULT_SHOW_TECHNICAL |
| "No B2 evidence gaps identified." | `ConflictEvidenceSections.tsx` | TRANSLATE |
| `SHADOW` badge | `ResearchRunPage.tsx` Alpha Memory heading | HIDE_DEFAULT_SHOW_TECHNICAL |
| "Activation modulation: On/Off" | `ResearchRunPage.tsx` Alpha Memory panel | TRANSLATE + raw value HIDE_DEFAULT_SHOW_TECHNICAL |
| Raw reason codes in Blocked-alphas "Reason:" | `StructureGraphPage.tsx` (found only via the real-run verification pass) | HIDE_DEFAULT_SHOW_TECHNICAL |

**Already compliant before this phase**: `phi_id` (already gated behind an existing "Technical detail" disclosure), `diagnostic_reason_codes` and `local_edge_exclusion_reasons` (already behind their own `<details>`), and Phase-2B's `StructuralSnapshot.tsx` (already clean by design).

**Terms that remain (Section 6's acceptable list)**: Alpha, Active, Dominant, Structure, Main Conflict, Evidence, Counter-evidence, Uncertainty, Risk, Invalidation, Research status, human-readable Alpha names, and Alpha IDs shown alongside a human-readable name (e.g. "A301 — Revenue Expansion") for traceability.

## Translation Decisions

**Activation level** — `dominant`→Dominant, `regime_level`→Dominant, `active`→Active, `capped_active`→Active, `candidate`→Emerging, `watch`→Watchlist, `inactive`→Inactive. An unrecognized future value is humanized conservatively (underscore→space, title case), never crashes, never silently mapped to a known state. **Display translation only** — no stored/API value is ever mutated, and no new backend/semantic activation level was introduced.

**Conflict language** — the candidate-conflict badge changed from "Candidate conflict" to "Potential conflict"; its default copy changed from "did not clear the B2 Conflict Evidence Admissibility gate" to "Evidence is not yet strong enough for inclusion as the main structural conflict."; the rejected-before-evaluation copy dropped its inline "B2" phrasing; "No B2 evidence gaps identified." became "No evidence gaps identified."

**Alpha Memory** — default copy now states plainly: "Historical memory is shown for context and does not alter the current activation result." (with a narrowest-accurate defensive branch for a hypothetical future `activation_modulation_applied = true`, currently unreachable since the type contract constrains that field to the literal `false`). The `SHADOW` badge was removed from the default heading; the raw `mode` value is preserved verbatim under Technical details.

**`StructureGraphPage` scope decision (documented, not silent)**: its five section headings ("Active/Capped active/Dominant/Regime-level/Candidate alphas") and overview `<dl>` stat labels were deliberately left unchanged, per the task's own instruction that this page "must remain useful to technical users" and must not be "oversimplified into only cards." The literal raw underscored token `regime_level` never appears in this page's rendered text either way (only the already-humanized hyphenated "Regime-level" compound does); "candidate" appears capitalized in a section title. This is a considered boundary, not an oversight.

## Files Changed

**Added**: `frontend/src/utils/activationLevelDisplay.ts` (the shared `formatActivationLevelForDisplay` helper, consumed by `AlphaCard.tsx`, `ConflictCard.tsx`, and `StructureGraphPage.tsx` — no per-component duplicate translation logic anywhere) and its 12-test suite `activationLevelDisplay.test.ts`.

**Git-tracking note**: this file was initially placed at `frontend/src/lib/activationLevelDisplay.ts`. `git status` showed nothing for that path — the repository's root `.gitignore` has a generic `lib/` rule (evidently intended for a Python venv's `lib/` directory) that, having no leading slash, also silently matches `frontend/src/lib/` at any depth. Rather than modify the shared root `.gitignore`, the directory was renamed to `frontend/src/utils/` (confirmed clear of any `.gitignore` pattern) — a smaller, fully frontend-scoped fix. All imports were updated; the full test suite (290/290), typecheck, and production build were all re-confirmed passing after the move.

**Modified**: `AlphaCard.tsx` (translated level/target/blocked rows, stripped inline raw codes, one new consolidated "Technical details" disclosure), `ConflictCard.tsx` (`activationLevelText()` now routes through the shared formatter), `CandidateConflictCard.tsx` (plain "Potential conflict" language, full raw admissibility diagnostic moved to Technical details), `ConflictEvidenceSections.tsx` (one line: "No evidence gaps identified."), `StructureGraphPage.tsx` (Blocked-alphas list: translated badge/levels/reason, raw codes moved to a new per-item Technical details — added after the real-run audit found this specific gap), `ResearchRunPage.tsx` (Alpha Memory panel: `SHADOW` badge removed, plain default copy, raw mode/modulation preserved under Technical details).

**Backend files changed: 0. Backend API schema changed: no. Alpha taxonomy / mapper / evidence-stance / activation threshold / conflict admissibility / Alpha Memory behavior: unchanged.**

## Technical Details Mechanism

Native `<details>`/`<summary>` — keyboard-accessible by default, collapsed by default, labeled "Technical details" everywhere newly added (pre-existing disclosures kept their own established labels: "Full diagnostic detail", "Why edges did not qualify", "Technical detail" for `phi_id`). Every disclosure is **context-local** — one per `AlphaCard`, one per `CandidateConflictCard`, one per `StructureGraphPage` Blocked-alphas list item, one in the Alpha Memory panel. No page-level or global JSON inspector was created; only fields the backend actually provided are ever rendered.

## Default-View String Audit (After)

Performed via a real-run, read-only Playwright verification against the already-running `comqutor-api` server (Postgres-backed) for all three candidate demo tickers, across `ResearchRunPage`, `StructureGraphPage`, and `ConflictRadarPage` (6 page/ticker combinations). No `POST /api/research`, no `POST /api/replay-all`, no Provider/TradingAgents calls.

| Term | Result |
|---|---|
| `regime_level` | NOT_PRESENT (Research/Conflict pages) / TECHNICAL_ONLY (Structure Graph) |
| `candidate` | TECHNICAL_ONLY everywhere observed |
| `B2` | NOT_PRESENT (Research/Structure pages) / TECHNICAL_ONLY (Conflict Radar) |
| `Conflict Evidence Admissibility` | NOT_PRESENT everywhere observed |
| `SHADOW` | TECHNICAL_ONLY everywhere observed |
| `phi_id` | NOT_PRESENT everywhere observed |
| `activation_modulation_applied` | NOT_PRESENT everywhere observed |
| `NO_LOCAL_STRUCTURE_SUPPORT` | NOT_PRESENT (Research/Conflict pages) / TECHNICAL_ONLY (Structure Graph — **fixed during this phase** after being found `VISIBLE_DEFAULT` on first pass) |
| `LINEAGE_UNRESOLVED` | TECHNICAL_ONLY (Structure Graph, when present) / NOT_PRESENT elsewhere |

**Target met: every term is `TECHNICAL_ONLY` or `NOT_PRESENT` on every page/ticker combination checked — zero `VISIBLE_DEFAULT` remain.** Translated terms ("Active", "Dominant", "Emerging", "Potential conflict") were confirmed actually rendering on the real pages.

## Real-Run Verification

A Vite dev server was started against the already-running real `comqutor-api` (`VITE_COMQUTOR_API_BASE_URL=http://127.0.0.1:8000`) and driven by a throwaway Playwright script (deleted after use — not the blocked `w5-demo` harness) for all three run_ids across all three normal stakeholder-reachable pages. Zero Provider calls, zero TradingAgents calls, zero fresh ticker runs, zero `POST` to any research or replay endpoint.

- **NVDA** (`57d7b4c4-...`): Structural snapshot present; jargon audit PASS.
- **QQQ** (`f239a53f-...`): "No single structure currently dominates." rendered correctly; jargon audit PASS.
- **SNDK** (`e8e0f398-...`): "No high-confidence structural conflict is currently admitted." rendered correctly; jargon audit PASS.

The throwaway dev server and verification scripts were stopped and deleted after use; the real `comqutor-api` server was left running, untouched.

## Regression Checks

- **Phase 2B (Structural Snapshot)**: confirmed clean — no raw `regime_level`/`candidate`/`B2`/`phi_id`/`SHADOW` anywhere. `StructuralSnapshot.test.tsx` 14/14 passed (re-run explicitly).
- **Phase 2C (disclaimer / operator separation)**: "Research analysis only — not financial advice." still renders once, globally; `ReplayAllPanel` still absent from `/research`, still fully available at `/operator`. `AppShell.test.tsx` 6/6, `ResearchPage.test.tsx` 4/4, `OperatorPage.test.tsx` 7/7 passed (re-run explicitly).

## Test Results

- **Focused Phase-2D tests**: `activationLevelDisplay.test.ts` (new, 12 tests) plus updated/added tests across `AlphaCard.test.tsx`, `ConflictCard.test.tsx`, `CandidateConflictCard.test.tsx`, `ConflictEvidenceSections.test.tsx`, `ConflictRadarPage.test.tsx`, `StructureGraphPage.test.tsx`, `ResearchRunPage.test.tsx` — all passing.
- **Full frontend unit suite**: `npx vitest run` — **25 test files, 290 tests, 0 failed, 0 new regressions.**
- **Product-language test**: **1/1 passed.**
- **TypeScript build**: `npx tsc -b` — **0 errors.**
- **Production build**: `npm run build` — **succeeded** (66 modules transformed).
- **Relevant e2e** (`e2e/w5-demo.spec.ts`): **blocked** by the same pre-existing, unrelated Python packaging issue documented in Phase 2B/2C (`scripts/seed_w5_demo.py: ModuleNotFoundError: No module named 'scripts'`). Not fixed — out of scope. **Mitigated** by the separate real-run Playwright verification above, which bypassed the blocked seed script entirely by pointing directly at the already-running, already-populated real server.

## Zero-Provider Proof

0 Provider calls, 0 TradingAgents calls, 0 fresh ticker runs, 0 `POST /api/research`, 0 `POST /api/replay-all` against real data. All changes are presentation-only; the real-run verification used only `GET`-driven page loads against already-persisted data.

## Success Criteria

| Criterion | Met |
|---|---|
| Stakeholder default views no longer require internal engineering vocabulary | Yes |
| Important technical information not destroyed | Yes |
| Raw values remain available in an intentional advanced path | Yes |
| Phase-2B summary remains clean | Yes |
| Phase-2C disclaimer/operator separation intact | Yes |
| No backend changes | Yes |
| No semantic changes | Yes |
| Tests/build pass | Yes |
| No new regressions | Yes |

**Overall: PASS.**

## Next Recommended Phase

**Product Demo Hardening — Phase 3: Demo rehearsal / final readiness validation** — test the actual presentation sequence (NVDA primary, QQQ secondary, SNDK edge case) and identify only remaining demo blockers. **Do not** start semantic or latency optimization next. **Not implemented in this phase.**

---

**Gold v0.2 closure changed: no. Phase-1 audit changed: no. Phase-2A/2B/2C artifacts changed: no. Backend files changed: 0. Semantic files changed: 0. Provider calls: 0. TradingAgents calls: 0. Fresh ticker runs: 0. Commits: 0. Pushes: 0. Destructive git operations: 0.**

**PRODUCT DEMO HARDENING — PHASE 2D ONLY. DEFAULT VIEW SPEAKS PRODUCT LANGUAGE. TECHNICAL DETAILS PRESERVE AUDITABILITY. NO SEMANTICS CHANGED. NO RESEARCH RERUN.**
