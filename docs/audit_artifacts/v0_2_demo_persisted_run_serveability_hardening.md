# COMQUTOR Alpha — Demo Persisted-Run Serveability Hardening

**Product Demo Hardening — Phase 2A.** Objective: make the NVDA/QQQ/SNDK persisted demo runs reliably servable through the existing COMQUTOR API/UI without rerunning TradingAgents or Provider semantics, closing the Phase-1 P0 findings before any presentation/UI polish. This phase does not reopen Gold v0.2 acceptance and does not modify the Phase-1 audit.

## Headline Result

**No data was ever missing from the authoritative database.** Investigation found that NVDA, QQQ, and SNDK were already `FULLY_LIVE_SERVABLE` before any Phase-2A code was written — the Phase-1 finding was a measurement artifact: the ad-hoc checks used to produce it resolved to a different, stale database than the one these runs (and the currently-running API server) actually use. **No rehydration/write mechanism was built**, because none was needed; building one for data that was never missing would have added unnecessary write-path risk for a nonexistent problem. Instead, a small, read-only verification script was added so this exact class of false alarm cannot recur silently.

## Root Cause

**`RUNS_ORIGINATED_IN_DIFFERENT_DB`** (relative to whatever database context Phase-1's ad-hoc checks resolved to). Evidence:

- `comqutor_alpha/storage/db/engine.py::resolve_database_url()` falls back to a local SQLite file (`outputs/runs/_comqutor_alpha_graph.db`) whenever `COMQUTOR_DATABASE_URL` is unset in the process environment.
- That SQLite file's mtime is **2026-08-19 11:49** — it has not been written to since. All three candidate run directories were created *after* that date (NVDA 09-03, SNDK 09-04, QQQ 09-11), so none of their data could ever have reached it.
- `.env` at the repo root **does** set a non-empty `COMQUTOR_DATABASE_URL` (confirmed length 108 chars, scheme prefix `postgresql+psyc...`; the full DSN and credentials were never printed or logged).
- `scripts/start_live_comqutor.sh` — the one sanctioned launcher for live COMQUTOR research per its own header — sources `.env` with `set -a` before starting `comqutor-api`, so a server started through it inherits the Postgres DSN.
- The `comqutor-api` server already running in this environment reports via `GET /ready`: `database: ready`, `real_execution: configured`, `live_semantic_pipeline: ready` — consistent with having been started through the correct launcher.
- A direct, read-only query against the Postgres DSN from `.env` (`127.0.0.1:5433/comqutor_alpha`, container `comqutor-alpha--postgres-1`, confirmed running) found **complete rows for all three run_ids** across `research_runs`, `research_run_progress`, `structure_graphs`, `alpha_conflicts` (6 rows each — the six canonical taxonomy conflict pairs), `agent_outputs`, `alpha_activations` (10 rows each — the 10-Alpha MVP taxonomy), `alpha_matches`, and `entity_alpha_exposures` (10 rows each). `research_runs.status='completed'` with real, non-null `completed_at` timestamps matching the corresponding `run_audit.json` file artifacts to the second.

**Certainty**: HIGH that the runs' authoritative data lives correctly in Postgres (directly proven). MEDIUM on the precise mechanism of Phase-1's own check environment (not directly observed/logged at the time — inferred from the SQLite file's stale mtime). Explicitly **not** concluded: `ORIGINAL_PERSISTENCE_DEFECT` (persistence succeeded correctly), `POST_RUN_DB_DELETION` (no evidence of deletion — rows are present and consistent), `CURRENT_DB_RESET_OR_REPLACED` for the authoritative Postgres DB (never reset).

## Active Database Identity (Safe)

`postgresql+psycopg://127.0.0.1:5433/comqutor_alpha` — resolved via the project's own `resolve_database_url()`, no credentials inspected or printed anywhere in this investigation.

## Per-Run Before State

| Run | File State | Postgres DB State | Classification |
|---|---|---|---|
| NVDA `57d7b4c4-...` | complete | complete (1/1/1/6/733/10/733/10 rows across the 8 relevant tables) | FULLY_LIVE_SERVABLE (already) |
| QQQ `f239a53f-...` | complete | complete (1/1/1/6/826/10/826/10 rows) | FULLY_LIVE_SERVABLE (already) — contradicts the Phase-1 finding, which queried a different database |
| SNDK `e8e0f398-...` | complete | complete (1/1/1/6/918/10/918/10 rows) | FULLY_LIVE_SERVABLE (already) |

## Existing Restore/Reindex Mechanism Search

Searched for: replay, rehydrate, reindex, backfill, import-run, persist-graph, persist-conflict, restore-run, artifact-migration, DB-rebuild. **No dedicated rehydrate/reindex/backfill mechanism exists.** `POST /api/replay-all` exists but creates *new* replay run_ids by reprocessing `raw_agent_outputs.json` through the current pipeline — it does not (and was correctly not used to) restore the original accepted demo run_ids' own DB rows. This search is moot in practice: the empirical investigation above found nothing needed restoring.

## Mechanism Used

**VERIFICATION_ONLY.** No persistence write/rehydration was performed or needed. A new read-only diagnostic script, `scripts/verify_persisted_run_serveability.py`, was added to make this exact verification repeatable and environment-safe going forward, so a future bare `comqutor-api` invocation (started without `.env` loaded) cannot silently reproduce this false alarm undetected.

**What the script does**: loads `.env` the same safe way `scripts/start_live_comqutor.sh` does, then calls the exact existing, unmodified production read functions (`get_research_run_status` / `build_research_response` / `get_persisted_structure_graph` / `get_persisted_conflicts` from `comqutor_alpha.api.routes_research`) against a single, explicitly-resolved, read-only repository (`build_repository_from_env`) — the same resolution the API server itself uses. It classifies each run as `FULLY_LIVE_SERVABLE` / `FILE_COMPLETE_DB_INCOMPLETE` / `DB_PRESENT_BUT_INCONSISTENT` / `FILE_INCOMPLETE` / `OTHER`, and reports the resolved database identity with credentials always redacted. Zero writes, zero Provider calls, zero TradingAgents calls, zero semantic recomputation.

## Code Files Added

- `scripts/verify_persisted_run_serveability.py` (SHA256 `03650c06baf5f437c64bac0affffa1f6c5652a978e34e93ce488a5d82f96bf0b`)

No production route file (`routes_research.py` or any other) was modified — the "no silent file fallback inside user-facing GET routes" constraint is satisfied trivially, since those routes were not touched at all.

## Tests Added

`tests/test_persisted_run_serveability.py` (SHA256 `143c9c08b15325c475c7e4e41a33457ae82dffa574695923e1ab2ad414368729`) — 13 tests, all passing:

- Classification logic: fully-ready → `FULLY_LIVE_SERVABLE`; optional artifacts being `False` (error logs, `final_report`) does not block it; missing DB row + file artifacts present → `FILE_COMPLETE_DB_INCOMPLETE`; DB row present but partial → `DB_PRESENT_BUT_INCONSISTENT`; malformed/missing response → `OTHER`; no DB row and no artifacts → `OTHER` (never fabricates success).
- Safe database identity: a Postgres DSN never leaks user/password; a SQLite DSN is handled safely; a malformed DSN reports `unknown` rather than raising.
- Integration (synthetic fixture, in-memory SQLite, `offline_raw_agent_outputs`, zero Provider/TradingAgents calls, following the pre-existing `test_graph_api.py`/`test_research_runs_api.py` convention): end-to-end `verify_run()` against a synthetic completed run returns `FULLY_LIVE_SERVABLE`; two successive calls are idempotent and produce identical output (no writes occur at all); an unknown run_id does not crash and is never misreported as servable.

**Broader regression check**: `pytest tests/test_persisted_run_serveability.py tests/test_research_runs_api.py tests/test_research_jobs.py tests/test_graph_api.py tests/test_graph_persistence.py` → **144 passed, 0 failed, 0 new regressions.**

## Zero-Provider Proof

0 Provider calls, 0 TradingAgents calls, 0 fresh ticker runs, 0 semantic recomputation this phase. All verification used read-only DB queries and read-only production GET-route functions against already-persisted data. The new test's only pipeline execution is a synthetic, offline fixture using a throwaway run_id in an in-memory SQLite database — it never touches the real NVDA/QQQ/SNDK run_ids, their files, or the real Postgres database.

## Per-Run After API State

| Run | status | graph | conflicts | dominant Alphas | main conflict | classification |
|---|---|---|---|---|---|---|
| NVDA | completed | ready | ready | `A301` | A101 vs A304 | **FULLY_LIVE_SERVABLE** |
| QQQ | completed | ready | ready | *(none)* | A301 vs A304 | **FULLY_LIVE_SERVABLE** |
| SNDK | completed | ready | ready | `A201` | *(none admitted)* | **FULLY_LIVE_SERVABLE** |

All three match their previously-established accepted structural story exactly. For QQQ: the no-dominant-Alpha state is preserved verbatim, and A001 is **not** exposed as detected — this is serving validation only, reading already-adjudicated persisted data, not a Gold reevaluation. For SNDK: the zero-admitted-conflict state renders as a legitimate result via the existing API contract, not a broken/not-ready state.

## P0 Closure

- **P0-1: CLOSED.** QQQ is reliably live-servable via the existing, unmodified API/UI contract, confirmed via both direct HTTP GET calls against the running server and the new verification script, with zero semantic recomputation.
- **P0-2: CLOSED.** NVDA, QQQ, and SNDK are all independently verified `FULLY_LIVE_SERVABLE`.

## Remaining Risks

1. A future `comqutor-api` server started without `.env` loaded (or without `COMQUTOR_DATABASE_URL` otherwise exported) will silently resolve to the stale SQLite fallback and reproduce the exact appearance of the Phase-1 finding — not because data is missing, but because the wrong database is being queried. Operators should always start the server via `scripts/start_live_comqutor.sh` (or otherwise export `COMQUTOR_DATABASE_URL`) for any demo-serving session, and can run `python scripts/verify_persisted_run_serveability.py <run_id> ...` beforehand as a pre-demo gate (non-zero exit if any run isn't fully servable).
2. Whether other, non-candidate historical runs depend on the same Postgres container being up was not exhaustively audited — if it is stopped, all three demo runs would revert to appearing not-ready, for the same underlying reason, not because their data changed.
3. The verification script re-resolves the database URL independently (via `resolve_database_url()`) rather than reading a public attribute off the repository instance (which does not exist) — correct today, but the two resolution paths must be kept in sync if ever refactored.

## Not-Authorized Actions Confirmed Avoided

No Alpha taxonomy change. No Alpha mapping semantics change. No evidence stance semantics change. No activation threshold change. No conflict semantics/admissibility change. No TradingAgents rerun. No Provider call. No fresh ticker research. No Gold v0.2 acceptance artifact modified. No file fallback invented inside any user-facing GET route (`routes_research.py` was not modified at all).

## Next Recommended Step

**Product Demo Hardening — Phase 2B: Structured top-level result summary** — render the Alpha list, dominant Alpha (or an explicit no-dominant state), and main conflict (or an explicit no-conflict state) directly on `ResearchRunPage.tsx`, per the Phase-1 recommended first implementation slice. **Not implemented in this phase.**

---

**Gold v0.2 closure changed: no. Phase-1 audit changed: no. Alpha/activation/conflict semantics changed: no. Production route files changed: 0. Provider calls: 0. TradingAgents calls: 0. Fresh ticker runs: 0. All three candidate runs verified live-servable using only already-persisted authoritative data. Commits: 0. Pushes: 0. Destructive git operations: 0.**

**PRODUCT DEMO HARDENING — PHASE 2A ONLY. P0-1 CLOSED. P0-2 CLOSED. GOLD v0.2 NOT REOPENED. NO RESEARCH RERUN.**
