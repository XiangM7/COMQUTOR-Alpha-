# COMQUTOR Alpha — Invalidation-Condition Coverage Completion (John Follow-Up Requirement A)

**Active acceptance version: v0.2.** Gold acceptance CLOSED. Product Demo Hardening CLOSED (`FINAL_DEMO_READINESS=DEMO_READY`). This is a product-completeness follow-up, not a reopening of Gold acceptance.

## Executive Result

**PASS.** All 10 MVP Alpha IDs now resolve to truthful invalidation-condition UI behavior. `unwired = 0`. Backend production files changed: **0**. Taxonomy files changed: **0**. API schema changed: **no**. No new Alpha semantics were authored.

## The Real Gap (Not What It Looked Like)

Two genuinely separate invalidation-condition sources already existed in the codebase:

1. **`comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml`** — each of the 10 MVP Alphas' own `invalidation_conditions` field (2–3 phrases each), already fully populated for every Alpha. Already exposed, unchanged, via `GET /api/alpha-library`.
2. **`comqutor_alpha/config/alpha_invalidation_conditions_v0.1.yaml`** (loaded by `comqutor_alpha/conflict_engine/invalidation_registry.py`) — a *separately versioned, separately approved* registry. Its own header and loader docstring are explicit: the taxonomy's list "predates this registry and is not treated as a formal Product Owner approval source here." Only **A101** has ever been formally approved (`source: John`); every other Alpha is `approval_status: not_defined`. This registry powers only the Conflict Radar's `ConflictEvidenceSections.tsx`, shown only for the two Alphas on either side of an admitted main conflict.

**The historical "only A101 covered" finding was accurate — for source #2.** It is not a bug: it is an honestly-reported, intentional approval gate for a narrower feature (Conflict Radar bull/bear invalidation comparison), and it was left **completely untouched** in this task.

**The actual coverage gap was plumbing, not content or approval**: `AlphaCard` — the general per-Alpha card used throughout `StructureGraphPage` — never rendered any invalidation-condition section at all, for any Alpha, even though real taxonomy content already existed and was already API-exposed for all 10 Alphas. No frontend code had ever fetched `GET /api/alpha-library`. Coverage status: **AVAILABLE_BUT_NOT_WIRED**.

## Single-Source-of-Truth Data Flow (New)

```
alpha_taxonomy_v1.yaml (invalidation_conditions)
  -> GET /api/alpha-library (unchanged, zero backend edits)
  -> useAlphaLibrary() hook (one fetch, module-level cache, shared by every AlphaCard)
  -> AlphaCard's new "Invalidation conditions" section
```

No second hardcoded frontend registry was created. The B5 Conflict Radar registry (source #2 above) is a separate, intentionally narrower, already-correct feature and was not touched or merged into this flow.

## Approval-Provenance Discipline

The new section is labelled **"Invalidation conditions"** — never "John-approved" or "Approved" — because the taxonomy list carries no separate approval marker of its own. A source-transparency line makes clear these are Alpha-definition content, not current-run output:

> From this Alpha's definition, not this run's analysis.

The existing B5 registry's own "approved" / "not yet product-approved" wording (`ConflictEvidenceSections.tsx`) is unchanged — that *is* an accurate, provenance-backed claim for that narrower feature.

## Coverage Matrix

| Alpha | Name | Conditions | API exposed | Rendered | Fallback | Status |
|---|---|---|---|---|---|---|
| A001 | Rate Cut Cycle | 3 | ✅ | ✅ | — | COVERED |
| A003 | Liquidity Expansion | 3 | ✅ | ✅ | — | COVERED |
| A101 | AI Expansion | 3 | ✅ | ✅ | — | COVERED |
| A102 | Inference Explosion | 2 | ✅ | ✅ | — | COVERED |
| A103 | AI Infrastructure | 2 | ✅ | ✅ | — | COVERED |
| A201 | Semiconductor Supercycle | 2 | ✅ | ✅ | — | COVERED |
| A301 | Revenue Expansion | 3 | ✅ | ✅ | — | COVERED |
| A304 | Multiple Compression | 2 | ✅ | ✅ | — | COVERED |
| A501 | Recession Risk | 3 | ✅ | ✅ | — | COVERED |
| A601 | Narrative Momentum | 3 | ✅ | ✅ | — | COVERED |

**10/10 COVERED. 0 unwired. 0 authoritative content gaps.** (No Alpha needed the honest fallback this time — the fallback path still exists and is tested, for whenever a future Alpha genuinely lacks taxonomy content.)

## Implementation

**Backend: 0 files changed.** `GET /api/alpha-library` already exposed `invalidation_conditions` for all 10 Alphas — verified, not modified.

**Frontend files changed:**
- `frontend/src/api/types.ts` — `AlphaLibraryEntry`/`AlphaLibraryResponse` types (with explicit doc-comment distinguishing this from the B5 approval registry).
- `frontend/src/api/adapters.ts` — `adaptAlphaLibraryResponse`.
- `frontend/src/api/client.ts` — `getAlphaLibrary()`.
- `frontend/src/hooks/useAlphaLibrary.ts` (new) — module-level cached fetch, shared across every consumer.
- `frontend/src/components/AlphaCard.tsx` — new `invalidationConditions` prop and "Invalidation conditions" section, honest empty-state fallback, no raw null/undefined ever shown.
- `frontend/src/pages/StructureGraphPage.tsx` — one `useAlphaLibrary()` call, mapped by `alpha_id`, passed to both `AlphaCard` call sites.
- `frontend/src/styles.css` — minimal overflow-wrap/word-break rules for the new list, following the existing `.alpha-card-diagnostic-reasons` and Phase 3B small-viewport pattern.

**No per-Alpha N+1 fetch behavior**: verified by a dedicated test — 5 simultaneous `useAlphaLibrary()` consumers produce exactly 1 network call; a page rendering 2 `AlphaCard`s produces exactly 1 `getAlphaLibrary` call.

## Demo-Run Verification (Persisted Artifacts Only — No Fresh Research)

| Ticker | Run ID | Alphas present | Missing in taxonomy | Empty conditions |
|---|---|---|---|---|
| NVDA | `57d7b4c4-...` | all 10 | none | none |
| QQQ | `f239a53f-...` (post-fix) | all 10 | none | none |
| SNDK | `e8e0f398-...` | all 10 | none | none |
| MSFT (Silver) | `43472ace-...` | all 10 | none | none |
| TSM (Silver) | `dfc7ceb3-...` | all 10 | none | none |
| AMD (Silver) | `949f685a-...` | all 10 | none | none |

Every Alpha appearing in any of these six persisted runs has real, non-empty taxonomy content — every `AlphaCard` rendered from these runs shows real invalidation conditions, never the fallback.

## Tests

- **Focused**: `AlphaCard.test.tsx`, `api/adapters.test.ts`, `api/client.test.ts`, `hooks/useAlphaLibrary.test.ts`, `pages/StructureGraphPage.test.tsx` — 78 tests, all passing.
- **Full frontend unit suite**: `npx vitest run` — **26 test files, 310 tests, 0 failed** (baseline: 25 files / 293 tests; delta: +1 file, +17 tests, 0 removed, 0 failed).
- **Product-language test**: 1/1 passed.
- **TypeScript**: `npx tsc -b` — 0 errors.
- **Production build**: `npm run build` — succeeded, 67 modules transformed.

Covered explicitly: A101 still renders correctly; a second, non-A101 Alpha (A201) renders from the exact same source, proving no hardcoded A101-only path remains; human-readable list formatting (no raw YAML/JSON); honest fallback for a genuinely empty condition list; no raw `null`/`undefined` ever shown; conditions never labelled "approved"/"John-approved"; conditions never described as current-run LLM output; no per-Alpha N+1 fetch.

## Preserved Work (Not Reopened)

StructuralSnapshot (deliberately out of scope — it uses `AlphaChip`, not `AlphaCard`), the global "Research analysis only — not financial advice." disclaimer, the `/research` vs `/operator` separation, Phase 2D's Technical-details partitioning, Phase 3B's small-viewport `overflow-wrap` fix, and NVDA/QQQ/SNDK demo dominant-Alpha/main-conflict behavior are all verified unchanged.

## Alpha Memory

`ALPHA_MEMORY_MODE=SHADOW`, `ALPHA_MEMORY_ACTIVATION_MODULATION=OFF` — untouched by this task.

## No Live Execution

Provider calls: 0. TradingAgents calls: 0. Fresh ticker runs: 0. `POST /api/research`: 0.

## Success Decision

**PASS.**

## Next Recommended Task

John Requirement B: **Semantic-classifier cost/latency reduction** (Alpha mapping + evidence stance + structure extraction consumed ~74% of the QQQ fresh-run wall-clock time). Not implemented here — requires a separate analysis of call volume, cacheability, batching, concurrency, duplicate semantic classifications, and fallback/retry behavior, without changing accepted semantics.

---

**Gold changed: no. Production semantics changed: no. Taxonomy changed: no. Backend production files changed: 0. Provider calls: 0. TradingAgents calls: 0. Fresh ticker runs: 0. Commits: 0. Pushes: 0. Destructive git operations: 0.**

**JOHN FOLLOW-UP REQUIREMENT A — INVALIDATION-CONDITION COVERAGE COMPLETION — PASS.**
