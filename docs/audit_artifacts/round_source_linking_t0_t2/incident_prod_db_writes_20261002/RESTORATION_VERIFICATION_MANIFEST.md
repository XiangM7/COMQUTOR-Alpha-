# Restoration verification manifest

**This document exists specifically to prevent a false impression: the
original NVDA Fresh Run (`034a0a60-430e-41f8-8321-03a11389707a`) did NOT run
against an isolated database throughout. It wrote its database state to the
production database `comqutor_alpha`. The data now present in
`comqutor_alpha_test` is a restored copy of a backup taken from that
production write, not a re-execution and not evidence that the original run
used the isolated database.**

## Facts, explicit

1. **The original research actually wrote to the production database.**
   Confirmed via `ps eww` on the live process (its real
   `COMQUTOR_DATABASE_URL` resolved to `comqutor_alpha`, not
   `comqutor_alpha_test`) and via direct query against `comqutor_alpha`
   itself (2111 rows found there, matching this run's `run_id` exactly).
   See `INCIDENT_REPORT_AND_CLEANUP_PLAN.md` in this same directory for the
   full root-cause trace.
2. **The data now in `comqutor_alpha_test` comes from backup restoration,
   not from the original run writing there, and not from any new
   execution.** No Provider call, no TradingAgents run, and no Week2 LLM
   call was made to produce this data. It is a row-for-row restore of the
   JSON backup taken from the production database before that production
   data was deleted.
3. **Restoration time**: `2026-10-02T18:14:29Z` (UTC, verification
   performed; the restore transaction itself immediately preceded this).
4. **Source backup**: `db_backup/manifest.json`, sha256
   `85d850b9a3488a81b7ad9ea9960986a4f9d0e0d09e602ddebb11a59339a17273`. That
   manifest's own per-table sha256 hashes (recorded at backup time, and
   reconfirmed byte-identical against production immediately before the
   production delete) are the authoritative record of exactly what was
   restored -- see `db_backup/manifest.json` directly.
5. **Pre-restore collision check**: `comqutor_alpha_test` was queried for
   this `run_id` across all 8 tables immediately before restoring -- 0 rows
   existed. The restore was a clean insert, never an overwrite of anything
   pre-existing.
6. **Restore counts**: all 8 tables matched the backup manifest's row counts
   exactly (`agent_outputs`=1040, `alpha_matches`=1040,
   `alpha_activations`=10, `alpha_conflicts`=8,
   `entity_alpha_exposures`=10, `structure_graphs`=1,
   `research_run_progress`=1, `research_runs`=1; total 2111), committed in
   one transaction.

## Verification results (real API and export entry point, new process)

Verified via FastAPI's `TestClient` driving the real, unmodified
`comqutor_alpha.api.main.create_app()` application and its real route
functions (`get_research_run`, `get_run_export_bundle`,
`get_persisted_structure_graph`, `get_persisted_conflicts`) -- not a
reimplementation, and not an in-memory object read -- with
`COMQUTOR_DATABASE_URL` pointed at `comqutor_alpha_test` (the now-restored
database). A live, persistent background server was not used for this check
(declined by this environment's own safety controls against starting a new
long-running process); `TestClient` exercises the identical application and
route code in-process instead, which is the available equivalent here.

- `GET /api/research/034a0a60-430e-41f8-8321-03a11389707a`: HTTP 200.
  `status=completed`, `ticker=NVDA`, `structured_output_count=1040`,
  `structure_graph_status=ready`, `conflict_status=ready`,
  `dominant_alphas=[]`, `artifacts.alpha_matches=true`,
  `artifacts.extracted_structures=true` -- identical to the original run's
  own response before the production rows were ever touched.
- `GET /api/research/034a0a60-430e-41f8-8321-03a11389707a/export`: HTTP 200,
  `content-type: application/zip`, 802,186 bytes, sha256
  `424f22da55e838e7fa4d5aecbd715fe4174eb1beaba969b7ac3d574f1327e4fc`
  (saved as `restored_db_export_verification.zip` in this directory). Real
  export bundle, 15 artifact files (`alpha_matches.json`,
  `structure_graph.json`, `conflicts.json`, `evidence_stance_audit.json`,
  `unclassified_findings.json`, `source_registry.json`, etc.), produced
  straight from the real artifact manifest -- `EXPORT_NOT_READY` would have
  been returned had the finalizer's own artifact manifest been missing or
  incomplete, and it was not.
- `GET /api/research/034a0a60-430e-41f8-8321-03a11389707a/graph`: HTTP 200,
  real structure graph with nodes/edges/graph_metrics/graph_coherence.
- `GET /api/research/034a0a60-430e-41f8-8321-03a11389707a/conflicts`: HTTP
  200, confirms 8 declared candidate pairs, 0 admitted, 8 rejected, no main
  conflict -- consistent with the original run's own "no official conflict"
  finding (never forced or altered by the restoration).

File/DB/API/Export consistency is confirmed: the real, unaffected
file-based artifacts under `outputs/runs/034a0a60-430e-41f8-8321-03a11389707a/`
(never touched by the production-database incident) and the restored
database agree with each other through the real API and export code paths.
