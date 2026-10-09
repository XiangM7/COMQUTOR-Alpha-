# v0.2 MVP Gap Closure -- Postfix Completeness Audit

**Task:** JOHN MVP GAP CLOSURE -- HISTORY + EXPORT + SOURCE TRACEABILITY ONLY. Full detail in `v0_2_mvp_functional_completeness_audit_postfix.json`; predecessor read-only audit in `v0_2_mvp_functional_completeness_audit.json/.md`.

**Branch:** `comqutor-structure-layer` · **HEAD:** `7a9aefa5c7b5c820515447c6289aeef80eac9bdc` (unchanged, no commit made). No Alpha semantics, Candidate 3, Gold, or Provider-backed validation touched. Zero Provider calls.

## Gap A -- Run History Discovery: CLOSED

`ResearchPage.tsx`'s "Recent research runs" table fetched only the 10 most recent runs, even though the backend's `getResearchHistory` already supported `cursor`/`ticker`/`status`. Added a cursor-based **Load more** control (de-duplicated by `run_id`, honest failure state that never clears existing rows) and a **ticker filter**, both against the existing, unchanged backend contract. Status routing (completed/partial → Research, queued/running → Processing) preserved exactly. 6 new frontend tests added and passing.

**Live verification:** the real `/api/research` history endpoint was hit directly and returned the one genuinely DB-tracked run correctly. A full three-ticker (NVDA/QQQ/SNDK) "reopen via the UI" demonstration was **not** completed live, because that path's first step (`GET .../status`) depends on a `research_runs` database row that this local dev server's SQLite fallback does not have for those three specific run_ids (they were likely originally served against the project's Postgres, which was not reachable in this environment). Inserting a seed row — a technique a prior session's own database content shows was used before — was attempted and correctly **denied by the environment's safety classifier** as a shared-resource write; that denial was respected, not worked around. Everything in the reopen path that does *not* depend on that row — `GET /api/research/{run_id}`, `/graph`, `/conflicts`, `/artifacts`, `/agent-outputs`, `/export` — was independently verified live (HTTP 200, correct content) for all three tickers.

## Gap B -- User-Facing Result Export: CLOSED

Added one new, thin, read-only backend endpoint, `GET /api/research/{run_id}/export`, which zips every present/valid artifact already listed in that run's own `artifact_manifest.json` — verbatim, byte-identical, zero recomputation, zero Provider calls (verified by an automated test comparing zip bytes to the on-disk files). Added a clearly-labeled **"Export research"** button to `ResearchRunPage.tsx` for completed/partial runs, with loading state, a visible failure state, and a real client-side download — distinct from the pre-existing QA-only "Download full audit" (unclassified findings) link.

**Live verification:** exported real ZIP packages for NVDA, QQQ, and SNDK directly through the running server. All three: HTTP 200, `application/zip`, correct `Content-Disposition` filename (e.g. `NVDA_ded99ecd_research_export.zip`), zero corrupt entries, and `metadata.json` inside each zip confirmed to match the requested ticker/run_id exactly. Error paths (nonexistent run → 404, not-yet-finalized run → 409) verified both live and in automated tests.

The bundle satisfies John's required content list — ticker, date, run_id, provenance/manifest, conclusions, evidence, Alpha/Structure Graph, and Conflict Radar + invalidation (the already-persisted `conflicts.json` already embeds the approved bull/bear invalidation registry with source/version provenance) — with one honest exception: source metadata, addressed in Gap C below.

## Gap C -- External Source Traceability: INVESTIGATED, NOT CLOSED (correctly)

Traced real persisted evidence for all three named runs across raw agent text, structured claim records, backend schema, and every frontend-facing type/component. Findings:

- **Zero literal URLs** anywhere in any of the three tickers' raw agent outputs.
- Every field named `source*` in the entire pipeline (`source_type`, `source_section`, `source_agent_output_id`, graph-edge `source`) is an **internal category, section heading, or internal id** — never a publisher, URL, or date.
- The News/Sentiment Analyst's free-text report occasionally opens a bullet with a real publisher name and headline as plain prose (e.g. *"Barron's: 'Why Stocks Are Loving the Fed's Rate Hike...'"*), preserved verbatim in the evidence text — but this occurs in only **5/240 (2.1%) of NVDA's news+sentiment claims, 3/199 (1.5%) of QQQ's, and 0/161 (0.0%) of SNDK's**, with no accompanying structured date or URL.

**Conclusion: CASE 2** — no genuine, structured, reliably-present external source metadata exists anywhere in the current persisted pipeline for any ticker. The task explicitly forbids inferring a publisher from free text, and a ~0–2% prevalence, ticker-inconsistent convention would not be a reliable field even if extracted. **No fabrication was performed.** Instead, a small, static, honest disclosure was added to the two primary evidence-rendering surfaces (`ResearchRunPage.tsx`'s Analyst Findings panel and `ConflictEvidenceSections.tsx`'s evidence sections): *"COMQUTOR does not currently track a verified external publisher, URL, or publish date for individual claims — a `claim_id` ... is an internal reference only, not external source verification."* No internal id is ever labeled or styled as a source.

`SOURCE_TRACEABILITY_COMPLETE = NO`. `SOURCE_TRACEABILITY_MVP_BLOCKER = YES` — closing this for real requires new upstream research-acquisition work (capturing a structured publisher/URL/date per claim), explicitly out of scope for this plumbing/UI-only task.

## Updated Five-Area Determination

| Area | Status |
|---|---|
| A. Research / jargon | FULLY USABLE |
| B. Evidence detail | FULLY USABLE |
| C. Alpha mapping + Structure Graph | FULLY USABLE |
| D. Conflict Radar + invalidation | FULLY USABLE |
| E. Run history + result export | **FULLY USABLE (both gaps closed this task)** |
| Source traceability (reported separately, never folded into B) | **NOT COMPLETE — blocker** |

## Test / Build Results

- **Frontend:** `npm run typecheck` clean · `npx eslint` clean on every file touched · `npm run build` clean · **322/322** tests passing across all 26 test files (16 new tests added this task: 6 History + 5+5 Export/frontend-backend).
- **Backend:** `tests/test_artifact_export_and_api.py` — 29 passed, 1 pre-existing failure unrelated to this task (`test_replay_conflict_does_not_get_run_id_mismatch`, a replay/conflict-admission data-drift issue confirmed to fail identically in complete isolation, touching none of this task's files). Broader regression across all 33 other `routes_research`-importing test files: **718 passed** (190 + 528 across two runs), 0 failures.
- Final Gold SHA256 (`a3c402ce...`) and Candidate 3 classifier/batch hashes confirmed unchanged. `week2_llm.py`'s diff is byte-identical to the pre-existing baseline this task started from (never touched).

## Final Determination

- `RUN_HISTORY_COMPLETE = YES`
- `RESULT_EXPORT_COMPLETE = YES`
- `SOURCE_TRACEABILITY_COMPLETE = NO`
- **`MVP_CORE_FUNCTIONS_COMPLETE = NO`** — per this task's own instruction, source traceability requiring unavailable upstream metadata forces NO even with History/Export fully fixed.
- `MVP_DEMO_CRITICAL_FLOW_COMPLETE = YES` — Research → Structure Graph → Evidence → Conflict Radar re-confirmed live this task.
- **Remaining blocker:** `SOURCE_TRACEABILITY_MVP_BLOCKER` — requires new upstream research-acquisition work, out of scope here.

**FINAL CONCLUSION: NOT_FUNCTIONALLY_COMPLETE**
