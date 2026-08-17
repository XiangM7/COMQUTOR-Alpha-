# Fresh Live Run Pipeline Failure Audit — `5ffe121a-68fd-473b-82b5-c9465332d8a2`

**Branch:** `comqutor-structure-layer` **HEAD:** `b5837e80a4550fc35165d0013a8ef0f27ccb4c8f` (unchanged throughout — read-only audit) **Worktree:** large legitimate uncommitted work preserved, untouched **Commit:** none **Push:** none **Subagents:** 0 **Provider calls:** 0

**Run ID:** `5ffe121a-68fd-473b-82b5-c9465332d8a2` **Ticker:** NVDA **Created:** `2026-08-14T17:08:21Z` (17:08:36Z audit-generated) — completed roughly 10 minutes before this audit began. This is a genuinely fresh run, not historical.

## Executive summary

**All three data failures share one confirmed root cause: the live backend server process has not been restarted since before the code it is currently serving was finished being written.** The on-disk artifact for this run is complete and correct for A3, B4, and B5 — proving the *computation* layer works. The browser's failures happen further downstream, primarily because the process actually answering the frontend's requests (`127.0.0.1:8001`) started on **2026-08-11 15:52:59** and has been running for **2 days 18+ hours** without a restart, while at least eight backend source files directly on the A3/B4/B5 request path were edited **after** that — on 2026-08-12 and 2026-08-13. Python does not hot-reload; this server is provably executing stale in-memory code for every one of those modules. A secondary, separately-confirmed issue is that this diagnosis could not directly inspect the live Postgres database the server actually uses (`postgresql+psycopg://…@127.0.0.1:5433/…`, a Docker container) — credentials were not available and were not attempted to be extracted — so the DB layer is marked `DB_COMPARISON_NOT_AVAILABLE` for direct row-content verification, though strong circumstantial evidence (below) is consistent with the same staleness explanation. The Alpha-card layout bug is unrelated and purely a CSS `auto-fill` + missing-wrap-safety issue, independently confirmed by direct source read.

## 1. Nine required A2 artifacts — all present, valid, and populated

Read `outputs/runs/5ffe121a-68fd-473b-82b5-c9465332d8a2/artifact_manifest.json` (written by this run itself): `artifact_completeness: "pass"`, `required_artifact_count: 9`, `present_required_artifact_count: 9`, `missing_required_artifacts: []`.

| Artifact | Size | Valid JSON | Schema version | Notes |
|---|---|---|---|---|
| `metadata.json` | 831 B | yes | — | run_id/ticker match |
| `raw_agent_outputs.json` | 108,114 B | yes | `week1a.raw_agent_outputs.v1` | 12 agent outputs |
| `structured_agent_outputs.json` | 1,371,262 B | yes | `week1a.structured_agent_outputs.v2` | 743 records |
| `evidence_facts.json` | 29,560 B | yes | `evidence_facts.export.v1` | — |
| `alpha_matches.json` | 6,702,041 B | yes | `week2.alpha_matches.v2` | 743 matches, 3,715 candidate scores |
| `structure_graph.json` | 369,438 B | yes | `week3.structure_graph.v2` | — |
| `alpha_activations.json` | 288,323 B | yes | `alpha_activations.export.v1` | 10 alphas, each carries `classification_version: "b4.alpha_level.v1"` |
| `conflicts.json` | 951,735 B | yes | `conflicts.export.v1` | `source_schema_version: "week4.alpha_conflicts.v1"`, 2 admitted, 1 candidate |
| `run_audit.json` | 115,662 B | yes | `structure_correctness.run_audit.v2` | `ticker_consistency: "pass"`, `overall_status: "PASS_WITH_WARNINGS"` |

Plus additive artifacts, all present and valid: `unclassified_findings.json` (A3, `unclassified_findings.v1`, 921,861 B), `entity_alpha_exposures.json`, `evidence_stance_audit.json`, `summary.json`, `structured_adapter_authority_routing.json`. `conflict_results.json` correctly shows `"status": "missing", "compatibility_alias_of": "conflicts.json"` — the legacy filename, not a real gap.

**`alpha_matches.json` Evidence Stance:** `mapper_version: week2.alpha_mapper.v2`; every one of 3,715 candidate scores has `evidence_stance_version: "evidence_stance.deterministic.v1"` and `stance_method: null` — 100% deterministic fallback, zero LLM stance calls, zero fallback-reason entries (none needed; this is simply the LLM stance tier being off by default, matching PD-006's `NOT_APPROVED` status — expected, not a defect).

## 2. A3 — Unclassified Findings

**Runtime-computed:** yes. `run_audit.json`'s embedded `unclassified_findings` block: `status: "ready"`, `total_count: 735`, `display_count: 20`, `reason_counts: {duplicate_supporting_text: 11, generic_background: 12, low_confidence: 0, no_alpha_match: 683, no_ticker_specific_evidence: 48}`, `unresolved_reason_count: 0`.

**Artifact-present:** yes. `unclassified_findings.json` on disk, valid, `schema_version: "unclassified_findings.v1"` — matches the *current* on-disk `comqutor_alpha/api/unclassified_findings.py`'s `SCHEMA_VERSION` constant exactly (directly verified: both equal `'unclassified_findings.v1'`).

**Frontend condition (confirmed by source read):** `frontend/src/pages/ResearchRunPage.tsx:198-208` — `const status = response?.unclassified_findings_status; if (status !== "ready") { … "Unclassified finding audit is not available for this historical run." }`.

**API layer (confirmed by source read):** `comqutor_alpha/api/routes_research.py:606-637` computes `unclassified_findings_status` by re-reading `unclassified_findings.json` straight off disk on every request (`load_json_record_if_exists`, no DB, no caching) and comparing its `schema_version` field to the imported `UNCLASSIFIED_FINDINGS_SCHEMA_VERSION` constant. Both this exact 30-line block and the constant's import (`comqutor_alpha/api/unclassified_findings.py`) were **last modified 2026-08-13** — after the live server process started (2026-08-11 15:52:59, see §6). The stale, currently-running process's in-memory copy of `routes_research.py` predates these edits; it is plausible (not directly observable without a restart) that this response-field wiring did not exist yet, or existed in an earlier form, when that process's module was loaded — the served JSON response would then simply lack a `"ready"` value for `unclassified_findings_status`, and the frontend's `!== "ready"` check falls through to the "historical run" message even though the run is brand new.

**CONFIRMED:** artifact and runtime computation are complete and correct. **CONTRIBUTING FACTOR (not directly observable without a live request trace or restart):** the exact mechanism by which the live process's response diverges from what fresh code would produce.

## 3. B4 — Alpha-level classification

**Runtime-computed:** yes. Every one of the 10 alphas in `alpha_activations.json` carries the full B4 field set:

```json
"target_level": "candidate", "qualified_level": "candidate", "is_blocked": false,
"blocked_from": [], "blocked_reason_codes": [], "diagnostic_reason_codes": [],
"classification_version": "b4.alpha_level.v1"
```

**Frontend condition (confirmed by source read):** `frontend/src/components/AlphaCard.tsx:193-236` —

```tsx
{activation && activation.qualified_level != null && activation.target_level != null ? (
  … real B4 display …
) : activation ? (
  <dd>Legacy classification — this run predates the B4 alpha-level classifier</dd>
) : null}
```

This fires precisely when the `activation` object the frontend *received* has `qualified_level` or `target_level` null/undefined — which the on-disk artifact does not. The activation payload reaches the frontend via `structure_graph.json`'s `activation` block through `routes_research.py`'s graph-serving route (`comqutor_alpha/api/routes_research.py` around line 3120, part of the same file confirmed stale — see §6); `comqutor_alpha/graph_engine/alpha_level_classifier.py` (the module that computes `target_level`/`qualified_level`/`is_blocked` in the first place) was **last modified 2026-08-12 11:31:00** — also after the live server started.

**CONFIRMED:** artifact fully populated with real classification data. **CONTRIBUTING FACTOR (unverified mechanism):** same staleness pattern as A3 — the exact response object the stale process serves for this field was not directly observed (would require a live request trace or restart).

## 4. B5 — Conflict Radar

**Runtime-computed:** yes. `run_audit.json`'s `conflict_summary`: `declared_pair_count: 6, evaluated_pair_count: 6, admitted_count: 2, suppressed_count: 2, rejected_count: 2, main_conflict_id: "A301__A304"`, with full B2 admissibility detail (`bull_score: 70.0`, `bear_score: 70.1005`, `bull_ticker_specific_support_count: 3`, `reason_codes: []`, `status: "admitted"` for the main pair) and full B5 presentation detail per pair (`bull_evidence_count`, `bear_evidence_count`, `counter_evidence_count`, `missing_evidence_count`, `qualification_gap_count`).

**Artifact-present:** yes. `conflicts.json`'s `main_conflict.evidence_ui` is fully populated: `schema_version: "conflict_evidence_ui.v1"`, `bull_evidence` (6 items), `bear_evidence` (7 items), `counter_evidence` (1 item), `missing_evidence: []`, `qualification_gaps: []`, `invalidation_conditions` (both sides present with `approval_status: "not_defined"` — expected; no invalidation registry entries approved yet, not a defect).

**API layer (frontend-observed error, confirmed by source read):** `comqutor_alpha/api/routes_research.py:3136-3140` — `CONFLICTS_CORRUPTED: "Persisted conflict result is missing required fields."` This message is returned by `get_persisted_conflicts()` (line 3162) when `repository.get_week4_conflict_result(run_id)` raises `GraphPersistenceError` with `reason_code == "DB_DATA_CORRUPTED"`.

**Read-only re-execution (this audit, current on-disk code, against the local SQLite fallback):**

```
status: failed
error_code: CONFLICTS_NOT_READY
message: Conflict analysis has not been generated for this research run yet.
```

This differs from the user's observed `CONFLICTS_CORRUPTED` — see §5 for why: the fresh process I ran this in and the live server do **not** use the same database.

**Persisted conflict result reconstruction (`reconstruct_conflict_result`, `comqutor_alpha/storage/db/week4_persistence.py`, last modified 2026-08-12 12:26:39 — after server start) requires:** every `alpha_conflicts` row's `schema_version == CONFLICT_SCHEMA_VERSION` (`"week4.alpha_conflicts.v1"`) and `formula_version == CONFLICT_FORMULA_VERSION` (`"week4.conflict_score.mvp_v1"`) exactly, per-row rank/pair/admissibility-field consistency, and a matching `evidence_strength`/`components` cross-check against the same call's `alpha_activations` rows (`_validate_week4_snapshot`). Any drift between the code that wrote the row and the code that reads it back triggers `DB_DATA_CORRUPTED`.

**CONFIRMED:** artifact fully populated with correct B2 + B5 data. **CONFIRMED:** the exact `CONFLICTS_CORRUPTED` message the user saw originates from `routes_research.py`'s reconstruction-failure path. **UNVERIFIED (blocked by `DB_COMPARISON_NOT_AVAILABLE`, see §5):** the exact row content in the live Postgres database that caused reconstruction to fail there specifically, as opposed to the "zero rows" result this audit observed against the (different, unused) local SQLite fallback.

## 5. Artifact vs. database vs. API — three-layer comparison

**A. Artifact (`outputs/runs/5ffe121a-…/`):** verified directly, complete (§1-4).

**B. Database:** `DB_COMPARISON_NOT_AVAILABLE`. Reason: `.env`'s `COMQUTOR_DATABASE_URL` is `postgresql+psycopg://<redacted>@127.0.0.1:5433/<db>` (host/port confirmed safe to disclose; credentials were not read or printed). Port 5433 is confirmed (via `docker ps`, no connection attempted) to be the `comqutor-alpha--postgres-1` Docker container (`postgres:16-alpine`, created 2026-07-14) — this is almost certainly what the live server (PID 67878, which holds ~19 established TCP connections to `localhost:5433`, confirmed via `/etc/services`: `pyrrho` = port 5433) is actually persisting to. This audit has no database credentials and did not attempt to extract or guess any, per instructions.

As a substitute, this audit queried the **local SQLite fallback** (`outputs/runs/_comqutor_alpha_graph.db`, resolved by fresh code when `COMQUTOR_DATABASE_URL` is unset) directly with read-only SQL:

```
alpha_conflicts   WHERE run_id = '5ffe121a-…'  → 0 rows
alpha_activations WHERE run_id = '5ffe121a-…'  → 0 rows
research_runs     WHERE run_id = '5ffe121a-…'  → 0 rows
```

The SQLite file's own mtime is **2026-08-13 11:26:58** — a full day *before* this run was even created (2026-08-14 17:08:21) — confirming this file has not been written to since well before this run and is simply not the database the live server uses. This is expected once the credentialed Postgres path is understood; it is not itself a bug, but it does mean **this audit cannot directly confirm what row (if any) exists for this run_id in the real, live database** — only that the live server's DB-dependent B5 endpoint fails for it in production.

**C. API:**
- `ACTUAL API PAYLOAD VERIFIED`: none — the live server was not queried directly by this audit (a live HTTP call against the production-serving process was out of scope for a read-only diagnostic and would not have added information beyond what the user already reported).
- `API CODE PATH INSPECTED ONLY`: yes, extensively (§2-4), plus one **live, read-only Python re-execution** of `get_persisted_conflicts()` using **current on-disk code** against the (wrong, but only accessible) local SQLite database (§4) — included for contrast, not as a stand-in for the real API payload.

## 6. Stale process / stale build determination

| Process | Command | Started | Elapsed | Port | Notes |
|---|---|---|---|---|---|
| PID 67878 | `python -m comqutor_alpha.api.server` | **2026-08-11 15:52:59** | 2d 18h | **8001** | cwd = `/Users/xiangmao/COMQUTOR-Alpha-` — the real, correctly-targeted COMQUTOR backend |
| PID 691 | `uvicorn main:app --port 8000` | 2026-06-30 | 44d 20h | 8000 (IPv4) | cwd = `~/Library/…/.Trash/ame/backend` — an **unrelated, deleted project**, irrelevant to COMQUTOR |
| PID 86282 (`com.docke`) | Docker proxy | — | — | 8000 (IPv6), 5433, 8501, 6333 | `docker ps` confirms the 8000 mapping belongs to a separate `rag-research-assistant-backend-1` container; 5433 is `comqutor-alpha--postgres-1` |
| PID 68263 (node) | `vite --port 5175` | **2026-08-11 15:53:08** | 2d 18h | 5175 | frontend dev server |

`frontend/.env.local` correctly sets `VITE_COMQUTOR_API_BASE_URL=http://127.0.0.1:8001` — so the port-8000 squatters (an orphaned Trash-folder process and an unrelated Docker container) are **not** what the frontend talks to; they are a separate environmental hygiene issue, noted but not the cause of these three bugs.

**File mtimes vs. PID 67878's start time (`1786488779`, 2026-08-11 15:52:59):**

| File | Last modified | Modified after server start? |
|---|---|---|
| `comqutor_alpha/api/routes_research.py` | Aug 13 11:31:15 | **yes** |
| `comqutor_alpha/api/artifact_export.py` | Aug 13 11:31:34 | **yes** |
| `comqutor_alpha/api/unclassified_findings.py` | Aug 13 10:59:05 | **yes** |
| `comqutor_alpha/storage/db/week4_persistence.py` | Aug 12 12:26:39 | **yes** |
| `comqutor_alpha/conflict_engine/conflict_detector.py` | Aug 12 12:26:25 | **yes** |
| `comqutor_alpha/conflict_engine/conflict_evidence_ui.py` | Aug 12 12:36:02 | **yes** |
| `comqutor_alpha/conflict_engine/conflict_schema.py` | Aug 12 11:09:38 | **yes** |
| `comqutor_alpha/graph_engine/alpha_level_classifier.py` | Aug 12 11:31:00 | **yes** |
| `comqutor_alpha/storage/db/repository.py` | Jul 31 17:42:41 | no |
| `comqutor_alpha/conflict_engine/conflict_admissibility.py` | Aug 11 14:30:29 | no (predates start) |
| `comqutor_alpha/graph_engine/activation_scorer_v2.py` | Aug 4 16:32:00 | no |

`comqutor_alpha/api/server.py` confirms `uvicorn.run(app, host=host, port=port, reload=False)` — **no auto-reload**. Frontend files under `frontend/src/{pages,components,api}` were also all last modified Aug 12-13, after the Vite dev server (PID 68263) started Aug 11 15:53:08 — but Vite's dev server serves transformed source on demand (HMR), which is a fundamentally different staleness risk than a non-reloading Python process; this audit did not observe the browser directly and cannot confirm whether the open tab's HMR connection was healthy throughout, so frontend staleness is listed as **UNVERIFIED**, not confirmed, in contrast to the backend.

A `frontend/dist/` production build also exists, dated **Aug 13 11:13** — after all frontend source edits — so if anything is statically serving `dist/` (not observed either way by this audit), it would be current. Which of `dist/` vs. the Vite dev server (5175) the browser actually loaded was not directly observable without inspecting the live browser session, which was out of scope.

**CONFIRMED ROOT CAUSE:** PID 67878 (the correct, frontend-targeted COMQUTOR backend on port 8001) has been running for 2 days 18+ hours without restart, while `routes_research.py`, `artifact_export.py`, `unclassified_findings.py`, `week4_persistence.py`, `conflict_detector.py`, `conflict_evidence_ui.py`, `conflict_schema.py`, and `alpha_level_classifier.py` — every module directly on the A3/B4/B5 live-request path — were modified after that process started. Python does not hot-reload (`reload=False`, confirmed). This process is provably executing outdated in-memory code for all of these modules.

## 7. Alpha card layout — CSS root cause

`frontend/src/styles.css:400-403`:

```css
.alpha-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: var(--space-4);
}
```

**CONFIRMED ROOT CAUSE (direct source read, no execution needed to see the defect):**

1. **`auto-fill`, not `auto-fit`.** `auto-fill` creates as many 240px-minimum tracks as fit the container width regardless of how many cards actually exist, and distributes the leftover `1fr` space evenly across *all* those tracks — including empty ones. With only 1-3 Active/Dominant/Regime cards in a wide container, this reserves several phantom empty columns: existing cards render at a narrow, fixed ~240px instead of expanding, and the phantom tracks show up as blank space on the right. This is why even a single card stays narrow instead of filling its row.
2. For **Candidate** alphas (typically 7-9 items — most of the 10-alpha taxonomy lands here when few are active), the same 240px floor now gets filled with real cards across 4+ columns, but 240px is too narrow for this card's actual content (long Alpha IDs, reason-code lists, qualification-ceiling text, supporting-agent lists), causing visual crowding/overlap.
3. **No `min-width: 0`** on `.alpha-card-row` (`display: flex`, line 456-461): flex children default to `min-width: auto`, which prevents them from shrinking below their content's intrinsic width — this is what allows a long `dd` value to push past the card boundary instead of wrapping.
4. **No `overflow-wrap` / `word-break`** anywhere in the `.alpha-card*` rule block (lines 400-464): a long unbroken token (an ID, a reason code, a comma-joined agent list) has no fallback wrapping behavior at all.
5. **No explicit column-count cap.** There is nothing limiting the grid to the task's suggested "desktop max 2 columns."

No CSS was modified — diagnosis only, per instructions.

## 8. Test coverage gap

Ran (read-only, zero Provider/TradingAgents calls):

```
python -m pytest tests/test_a3_unclassified_findings_control.py tests/test_b4_activation_level_alignment.py tests/test_b5_conflict_radar_evidence_ui.py -q
→ 148 passed in 1.37s
```

All 148 tests pass. **Why they pass while the real fresh web run fails:**

| File | Tests | Calls `run_research_request`/`_run_week3_graph_pipeline`? | Calls `get_persisted_conflicts` (real API read)? |
|---|---|---|---|
| `test_a3_unclassified_findings_control.py` | 58 | **no** | no |
| `test_b4_activation_level_alignment.py` | 28 | **no** | no |
| `test_b5_conflict_radar_evidence_ui.py` | 33 | **no** | yes (2×, against its own fresh, isolated, freshly-migrated test DB) |

None of the three files exercises the real live-run entry point (`run_research_request` → `_run_week3_graph_pipeline`, `comqutor_alpha/api/routes_research.py`). Each instead calls the underlying builder/detector/classifier functions directly, or (B4/B5) spins up its own fresh, correctly-migrated SQLite engine per test. This is exactly why these tests cannot catch the class of bug found here: every pytest invocation is, by construction, a brand-new Python process running current code against a throwaway database — it can never be "stale" relative to itself, and it never touches the shared server/production database a real browser session depends on.

**Missing end-to-end coverage, confirmed absent:** a test that (1) calls `run_research_request` (or `_run_week3_graph_pipeline`) exactly as the live POST route does, (2) against a real, migrated database, (3) then calls the actual read-side functions used by the frontend (`get_persisted_conflicts`, the research-status/detail builder producing `unclassified_findings_status`, and the graph-serving route producing `qualified_level`/`target_level`) — end to end, in one continuous process, the way a browser session actually experiences it. This gap exists independent of the staleness bug — even a stale-free deployment has no automated check that write-then-read-back genuinely round-trips through the real database and real serialization layer.

## 9. Commands executed

```
git branch --show-current; git rev-parse HEAD; git status --short; git diff --stat
ls -la outputs/runs/5ffe121a-68fd-473b-82b5-c9465332d8a2
python3 -m json.tool (all 9 + 6 additive artifacts, individually)
grep/rg across frontend/src and comqutor_alpha/ for the exact reported fallback strings
sed -n (targeted reads of routes_research.py, artifact_export.py, week4_persistence.py, repository.py, conflict_engine/pipeline.py, AlphaCard.tsx, ConflictRadarPage.tsx, ResearchRunPage.tsx, styles.css)
python3 -c "..." get_persisted_conflicts(run_id) — read-only, current code, against local SQLite fallback
sqlite3 outputs/runs/_comqutor_alpha_graph.db "SELECT COUNT(*) FROM alpha_conflicts/alpha_activations/research_runs WHERE run_id = …" — read-only
ps -p 67878/691/68263 -o pid,ppid,lstart,etime,command; lsof -p 67878/691 -a -i; lsof -nP -iTCP:8000 -sTCP:LISTEN
curl -sS -i http://127.0.0.1:8000/ and .../api/research/{run_id}/status — read-only GET, confirmed unrelated 404 app
stat -f mtimes for 11 backend files + 5 frontend files, compared against process start epoch
grep -o "^COMQUTOR_DATABASE_URL=" .env; docker ps (names/images/ports only, no connection attempted)
grep -i "pyrrho|irdmi|vcom-tunnel" /etc/services
python -m pytest tests/test_a3_unclassified_findings_control.py tests/test_b4_activation_level_alignment.py tests/test_b5_conflict_radar_evidence_ui.py -q
```

No write, no code edit, no artifact regeneration, no reprocessing, no server restart, no database connection attempt, no Provider/LLM/TradingAgents call.

## 10. Conclusion table

| Problem | Runtime generated? | Artifact present? | DB preserved? | API returned? | Frontend recognized? | Root cause |
|---|---|---|---|---|---|---|
| A3 Unclassified | Yes | Yes | N/A (file-based, not DB-backed) | No (observed by user) | No | **CONFIRMED:** stale server process; response-field wiring (`routes_research.py`, `unclassified_findings.py`) postdates process start. Exact in-memory mechanism **CONTRIBUTING/unverified** without a live trace or restart. |
| B4 Classification | Yes | Yes | N/A (served from graph artifact, not DB) | No (observed by user) | No | **CONFIRMED:** stale server process; `alpha_level_classifier.py` and the graph-serving route postdate process start. Exact in-memory mechanism **CONTRIBUTING/unverified**. |
| B5 Conflict Radar | Yes | Yes | **UNVERIFIED** (real Postgres DB inaccessible without credentials; local SQLite fallback confirmed unused/0 rows/stale mtime) | No (`CONFLICTS_CORRUPTED`, observed by user) | No | **CONFIRMED:** the error path (`routes_research.py`, `week4_persistence.py`) postdates process start; **CONFIRMED** artifact/computation are correct; exact DB row content **UNVERIFIED** (`DB_COMPARISON_NOT_AVAILABLE`). |
| Alpha card layout | N/A | N/A | N/A | N/A | Yes (misrendered) | **CONFIRMED:** `auto-fill` (not `auto-fit`) grid + no `min-width:0` + no `overflow-wrap`/`word-break` + no column cap, all directly read from `frontend/src/styles.css:400-464`. Unrelated to the staleness issue. |

**CONFIRMED ROOT CAUSE (data failures):** the live backend server (port 8001) has been running since 2026-08-11 15:52:59 without restart while at least eight files on the A3/B4/B5 request path were edited afterward; Python does not hot-reload.

**CONTRIBUTING FACTORS:** an inaccessible-to-this-audit live Postgres database prevents direct row-level confirmation for B5; two entirely unrelated processes (a deleted-project zombie and a Docker container for a different app) squat on port 8000, though the frontend correctly avoids that port.

**UNVERIFIED POSSIBILITIES (explicitly not claimed as fact):** the precise byte-for-byte shape of the live server's in-memory `unclassified_findings_status`/activation/conflicts response objects for this specific request; the exact row content and failure point inside the live Postgres `alpha_conflicts` table; whether the browser's Vite HMR connection was healthy throughout the session or whether the tab needed a hard refresh; whether `frontend/dist/` (built Aug 13 11:13) or the Vite dev server was actually what the browser loaded.

## 11. Minimal fix files (diagnosis only — not implemented this task)

Restarting PID 67878 (and, if HMR is suspect, PID 68263) is very likely sufficient by itself to resolve all three data-layer symptoms, since every relevant module is already correct on disk — no code fix has been identified as necessary from this audit's evidence. If a restart does *not* fully resolve B5, the next investigation target is `comqutor_alpha/storage/db/week4_persistence.py`'s `build_conflict_rows`/`reconstruct_conflict_result` against the real Postgres schema (may need a schema/migration check via `comqutor_alpha/storage/db/migrations.py` with real DB credentials). For the layout bug: `frontend/src/styles.css:400-464` (`.alpha-card-grid`, `.alpha-card-row`).

## 12. Regression tests needed (not written this task)

1. One true end-to-end test: `run_research_request` (or `_run_week3_graph_pipeline`) against a real migrated DB, immediately followed by `get_persisted_conflicts`, the research-detail/status builder, and the graph route — in one continuous process, asserting `unclassified_findings_status == "ready"`, every alpha's `qualified_level`/`target_level` non-null, and `main_conflict.evidence_ui` present, for a run with real saved `raw_agent_outputs.json`.
2. A layout/visual regression test (or at minimum a CSS unit assertion) verifying `.alpha-card-grid` never renders fewer real cards than available columns as empty phantom tracks, and that long field values wrap rather than overflow.
3. A process-staleness smoke check for local dev (e.g., a documented `README_DEV.md` step or a startup banner comparing the running process's import time against `git log -1 --format=%cI` for its own source tree) — out of scope to design fully here, noted as a gap.

## 13. Provider / execution guarantees

```
PROVIDER_CALLS = 0
TRADINGAGENTS_CALLS = 0
SUBAGENTS = 0
```

Files changed by this task: **only this report** (`docs/audit_artifacts/live_run_5ffe121a_pipeline_failure_report.md`). No code, artifact, database, or CSS was modified. No run was reprocessed. No server was restarted.

```
COMMIT = none
PUSH = none
```
