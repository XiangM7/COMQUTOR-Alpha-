# v0.2 MVP Functional Completeness Audit (READ ONLY)

**Question answered:** Is the current COMQUTOR Alpha MVP functionally complete against John's authoritative product-scope document? Full detail in `v0_2_mvp_functional_completeness_audit.json`.

**Branch:** `comqutor-structure-layer` · **HEAD:** `7a9aefa5c7b5c820515447c6289aeef80eac9bdc` (unchanged from Section 0 baseline). **Tracked files modified by this audit: 0.** No Provider calls made. No code/UI/export/history changes made.

**Method:** Every status below comes from directly reading the actual page/component source (`frontend/src/pages/*.tsx`, `frontend/src/components/*.tsx`) and backend export code (`comqutor_alpha/api/artifact_export.py`) — never from file existence, internal JSON presence, or test-pass status alone. `DAY_5_COMPLETE = YES` was explicitly NOT assumed to mean every MVP product function exists.

**Authoritative scope:** No separate repo document contains this task's exact wording (its distinctive term "Structure Feedback Lite" has zero repo-wide hits), so this task's own Section 1 text is treated as John's authoritative scope statement, per its own instruction not to let old internal backlog files override it. `docs/specs/COMQUTOR_Alpha_Development_Plan_v1.0.docx` was consulted as supporting context only.

## Completeness Matrix (18 rows)

| # | Capability | Status | Route | Severity |
|---|---|---|---|---|
| 1 | Ticker submission + readiness guard | IMPLEMENTED | `/research` | N/A |
| 2 | Fresh Research live progress workflow | IMPLEMENTED | `/runs/:id/processing` | N/A |
| 3 | Results view + jargon-friendly framing | IMPLEMENTED | `/runs/:id/research` | N/A |
| 4 | Evidence detail (claim/evidence/agent/confidence/claim_id) | IMPLEMENTED | embedded | LOW (no dedicated route) |
| 5 | Unclassified findings transparency | IMPLEMENTED | embedded | N/A |
| 6 | External source independence verification | **MISSING** | — | MEDIUM |
| 7 | Alpha Memory (shadow-only recurrence) | IMPLEMENTED | embedded | LOW (tests unconfirmed) |
| 8 | Structure Graph nodes/edges, taxonomy mapping | IMPLEMENTED | `/runs/:id/structure` | N/A |
| 9 | Alpha-level partition + orthogonal Blocked view | IMPLEMENTED | `/runs/:id/structure` | N/A |
| 10 | Zero-edge/no-dominant honest empty states | IMPLEMENTED | structure, conflicts | N/A |
| 11 | Per-Alpha invalidation conditions (taxonomy-level) | IMPLEMENTED | `/runs/:id/structure` | LOW |
| 12 | Conflict Radar: admitted/candidate/rejected with reasons | IMPLEMENTED | `/runs/:id/conflicts` | N/A |
| 13 | Evidence traceability per conflict side | IMPLEMENTED | embedded | LOW (tests unconfirmed) |
| 14 | **Approved invalidation/follow-up registry per conflict** | IMPLEMENTED | embedded | LOW (tests unconfirmed) |
| 15 | Run history (find/reopen historical runs) | **PARTIAL** | `/research` | MEDIUM |
| 16 | Result export (full run summary) | **PARTIAL** | one narrow link | **HIGH** |
| 17 | Persistence/traceability across restart (user-facing) | IMPLEMENTED | run pages | N/A |
| 18 | Formal Gold PASS/REVIEW verdict visibility | MISSING (by design) | — | LOW |

## Key Findings

**Evidence detail is real and embedded**, not a separate route: `ResearchRunPage.tsx`'s Analyst Findings panel shows claim, evidence text, agent, confidence, and `claim_id` for every finding, deterministically sorted and capped with More/Less.

**Invalidation/follow-up conditions ARE user-visible — and more richly than expected.** Two complementary surfaces exist:
- `StructureGraphPage.tsx` → every `AlphaCard` → a taxonomy-level "Invalidation conditions" section, explicitly labeled "From this Alpha's definition, not this run's analysis."
- `ConflictRadarPage.tsx` → every conflict/candidate card → `ConflictEvidenceSections.tsx`'s **"What would invalidate {bull/bear alpha}?"** section, sourced from an *approved* registry with `approval_status`, `Source`, and `Version` provenance, and an honest "not yet product-approved" fallback.

This directly answers the audit's central open question: this is not buried in raw JSON — it renders on the product's own pages for NVDA/QQQ/SNDK alike.

**Run history is real but capped.** `ResearchPage.tsx`'s "Recent research runs" table correctly distinguishes status and routes completed/partial vs. in-progress runs correctly — but it only ever fetches the 10 most recent runs. The backend API (`getResearchHistory`) already supports `cursor`/`ticker`/`status` filtering, but no UI control (search, filter, "load more") exposes it. A run outside the 10 most recent has no in-product discovery path.

**Result export is the weakest area.** The only `download` control anywhere in `frontend/src` is a single link scoped to `unclassified_findings.json` — a QA artifact, not a run summary. `comqutor_alpha/api/artifact_export.py` builds a complete, John-required 9-artifact set plus a manifest, but this is backend/audit-trail persistence reached only via direct API calls (as this and prior audit sessions did) — never via any frontend button. Internal completeness at the file level does not satisfy the user-facing requirement.

**External source independence verification does not exist structurally.** Every `source` field in `frontend/src/api/types.ts` is a structural graph-edge or Alpha-Memory identifier, never an external citation/publisher/URL. This confirms, at the code level, the limitation already disclosed throughout Day 4K/5 ("a claim_id is not external source verification").

## Five-Area Determination (non-averaged)

| Area | Status |
|---|---|
| A. Research page / jargon | FULLY USABLE |
| B. Evidence detail | FULLY USABLE |
| C. Structure Graph | FULLY USABLE |
| D. Conflict Radar + invalidation | FULLY USABLE |
| E. Run history + result export | **NOT FULLY USABLE** (both halves PARTIAL) |

`MVP_CORE_FUNCTIONS_COMPLETE` requires **all five** areas fully usable — it is never averaged, and strong Alpha-validation results (82.67%/87.23%) were not allowed to compensate for Area E.

## Final Determination

- **`MVP_CORE_FUNCTIONS_COMPLETE = NO`** — Area E is only PARTIAL on both halves (run history capped at 10 with no discovery path beyond that; result export limited to one narrow QA artifact, not a full run summary).
- **`MVP_DEMO_CRITICAL_FLOW_COMPLETE = YES`** — Research → Structure Graph → Evidence → Conflict Radar, including the do-not-force/insufficiency demonstration, does not depend on run-history search or export, and was independently re-confirmed at the source-code level this session (consistent with the Day 5 live-endpoint verification).

**FINAL CONCLUSION: NOT_FUNCTIONALLY_COMPLETE**
