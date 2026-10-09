# Incident: NVDA Fresh Run wrote to production database `comqutor_alpha`

Date: 2026-10-02. Affected run: `034a0a60-430e-41f8-8321-03a11389707a` (NVDA,
submitted via `POST /api/research` as part of this round's authorized Plan B
Fresh Run). **No DELETE/UPDATE/DDL has been executed against the production
database. This document proposes a cleanup plan; it does not carry it out.**

## 1. What happened

The isolated-database launcher
(`docs/audit_artifacts/round_source_linking_t0_t2/run_nvda_fresh_run_isolated_db.sh`)
correctly resolved `COMQUTOR_DATABASE_URL` to the isolated test database
(`comqutor_alpha_test`, host `127.0.0.1`, port `5433`), verified the name
ends in `_test`, and printed "T4 isolated-DB check passed" -- all true, in
that script's own process. It then handed off via
`exec bash scripts/start_live_comqutor.sh`.

`start_live_comqutor.sh` re-sources `.env` (its own step 3, "load .env
safely") with `set -a` (auto-export). `.env` itself defines its own
`COMQUTOR_DATABASE_URL`, pointing at the **production** database
`comqutor_alpha` (same host/port, `127.0.0.1:5433` -- these two databases are
distinguished only by name, not by host or port). Sourcing `.env` silently
overwrote the already-exported isolation override. Step 4 of the same
script ("explicitly export the required live-research environment")
re-forces `COMQUTOR_REAL_TRADINGAGENTS_ENABLED`, `COMQUTOR_WEEK2_LLM_ENABLED`,
CORS origins, API host, and API port *after* the `.env` reload -- but never
`COMQUTOR_DATABASE_URL`, because this script was never written with an
externally-supplied database override in mind.

By the time `exec comqutor-api` ran, the real server process's
`COMQUTOR_DATABASE_URL` was the production value. Confirmed directly against
the live process: `ps eww <pid>` showed
`COMQUTOR_DATABASE_URL=postgresql+psycopg://comqutor:[REDACTED]@127.0.0.1:5433/comqutor_alpha`.

Both real write paths inherited this same wrong value, since both call
`comqutor_alpha.storage.db.repository.build_write_repository_from_env`,
which resolves `COMQUTOR_DATABASE_URL` from `os.environ` fresh, with no
caching, at the moment each is called:

- The **main API process**, synchronously inside `POST /api/research`'s
  `enqueue_research_request` -> `prepare_research_submission`
  (`comqutor_alpha/research_lifecycle.py:669-671`) -> `claim_research_run`
  -- this wrote the `research_runs` row.
- The **spawned background worker** (`multiprocessing` `spawn` context,
  `comqutor_alpha/research_jobs.py:128`, `_job_worker_entrypoint`), which
  inherited the same already-wrong environment from its parent process at
  spawn time -- this wrote `agent_outputs`, `alpha_matches`,
  `alpha_activations`, `alpha_conflicts`, `entity_alpha_exposures`,
  `structure_graphs`, and `research_run_progress`.

Both failures trace to the exact same single root cause: `COMQUTOR_DATABASE_URL`
was correct in one process, then silently clobbered one handoff later, before
either write path ever ran.

**The isolated test database `comqutor_alpha_test` itself never received any
row for this run** -- confirmed by a fresh connection, checked across every
table in that database (0 rows, both scoped to this `run_id` and in total
across every table in the schema).

## 2. Read-only audit of the production database

Full schema has exactly 9 tables (`schema_migrations` plus the 8 below);
confirmed by querying `information_schema.tables` directly rather than
assuming -- no other table in the schema carries a `run_id` column, so the
impact is exhaustively these 8 tables, not "these 8 plus possibly more":

| table | rows for this run_id |
|---|---|
| `research_runs` | 1 |
| `research_run_progress` | 1 |
| `agent_outputs` | 1040 |
| `alpha_matches` | 1040 |
| `alpha_activations` | 10 |
| `alpha_conflicts` | 8 |
| `entity_alpha_exposures` | 10 |
| `structure_graphs` | 1 |
| **Total** | **2111** |

**No foreign key constraints exist anywhere in this schema** (confirmed via
`information_schema.table_constraints`/`referential_constraints` -- zero
rows returned). `run_id` is a plain, unconstrained column everywhere except
`research_runs.run_id`, which is that table's own primary key. There is
therefore no database-enforced cascade relationship of any kind between
these tables, and no risk of an unintended cascade touching another run.

**No other run was touched or modified.** This run's own
`active_fingerprint` is already `NULL` (correctly cleared on completion);
zero other rows currently hold a non-null `active_fingerprint`, confirming
no collision or interaction with any in-flight or historical run. Production
holds 103 other, pre-existing `research_runs` rows, all untouched.

## 3. Backup

Full backup of all 2111 rows across the 8 tables, as JSON (one file per
table, byte-exact column values, `NULL`/JSON/timestamp types preserved),
written to:

```
docs/audit_artifacts/round_source_linking_t0_t2/incident_prod_db_writes_20261002/db_backup/
  manifest.json                   (run_id, per-table row count + sha256)
  research_runs.json
  research_run_progress.json
  agent_outputs.json
  alpha_matches.json
  alpha_activations.json
  alpha_conflicts.json
  entity_alpha_exposures.json
  structure_graphs.json
```

Also preserved in this same incident directory:
- `research_files/` -- a full copy of the real, unaffected file-based run
  artifacts (`outputs/runs/034a0a60-430e-41f8-8321-03a11389707a/`): source
  registry, raw/structured agent outputs, all 838 semantic call records,
  TradingAgents' own call log and usage summary, error logs.
- `execution_logs/server_stdout_redacted.log` -- the real server process's
  captured stdout for this run. Checked and confirmed free of any database
  password or API key before being written here (the server's own stdout
  never printed a raw DSN or key at all; verified by scanning for both the
  connection-string pattern and generic secret-token patterns, zero matches
  either way).
- `config_evidence/nvda_fresh_run_plan_b_frozen_config.md` -- the pre-run
  frozen configuration snapshot (code state, budgets, prompt versions,
  database target as *intended*).

**Restore validated**, not merely assumed: all 2111 rows from the JSON
backup were inserted into the isolated `comqutor_alpha_test` database,
every per-table count verified to match the backup's manifest exactly
(8/8 tables matched), then removed again, leaving `comqutor_alpha_test`
back in its original empty state. This proves the backup is complete and
genuinely restorable, independent of production.

## 4. Fix: enforce the database target at the actual write-connection point

A startup-script environment check (what the launcher already had) is
proven insufficient on its own -- it can be satisfied in one process and
silently invalidated one handoff later, exactly as happened here. The fix
moves enforcement to the one place every real write path actually funnels
through, in whichever process it runs in:

- **`comqutor_alpha/storage/db/engine.py`**: new function
  `enforce_required_database_name(database_url)`. Reads
  `COMQUTOR_REQUIRE_DATABASE_NAME` (a second, independent environment
  variable; unset by default, zero behavior change for every existing
  caller/deployment). When set, parses the database name out of
  `database_url` via SQLAlchemy's own URL parser and raises
  `DatabaseConfigurationError("DATABASE_TARGET_MISMATCH")` -- never the raw
  DSN or a credential -- on any mismatch.
- **`comqutor_alpha/storage/db/repository.py`**:
  `build_write_repository_from_env` now calls this check immediately after
  resolving the URL and **before** `build_engine` is ever invoked -- so no
  connection, query, or schema-migration attempt happens against the wrong
  target. `build_repository_from_env` (the read-only path) is deliberately
  left unaffected, matching the write-path-only scope this task was given.
- **`docs/audit_artifacts/round_source_linking_t0_t2/run_nvda_fresh_run_isolated_db.sh`**:
  now also exports `COMQUTOR_REQUIRE_DATABASE_NAME="$db_name"` alongside its
  existing `COMQUTOR_DATABASE_URL` override. Since `.env` never defines this
  variable, `start_live_comqutor.sh`'s own `.env` re-source cannot clobber
  it the way it clobbers `COMQUTOR_DATABASE_URL` -- it survives the exact
  handoff that caused this incident, and is independently re-checked inside
  the final process.

**Verified offline (no new Provider call, no real Postgres server
required for the negative case):**
- `tests/test_graph_persistence.py::TestRequiredDatabaseNameGuard` (6 new
  tests): guard absent -> no behavior change; guard present and matching
  (local SQLite, no network) -> succeeds and persists normally; guard
  present and mismatched, pointed at a TEST-NET-1 address (192.0.2.1,
  RFC 5737, guaranteed unroutable) -> refuses immediately with
  `DATABASE_TARGET_MISMATCH`, confirmed via a mocked `build_engine` that
  `build_engine` is **never called** (not merely "fails fast", but provably
  never attempts a connection); read-only repository path confirmed
  unaffected even under the same mismatch; direct unit coverage of the
  parsing/comparison logic itself. All 6 new tests pass; the full
  `test_graph_persistence.py` + `test_week4_persistence.py` +
  `test_research_jobs.py` + `test_env_overrides.py` suites (183 tests total)
  pass with no regressions.
- **Reproduced the real incident and proved the fix closes it**: ran
  `build_write_repository_from_env` with `COMQUTOR_REQUIRE_DATABASE_NAME=
  comqutor_alpha_test` and the real, actual production `COMQUTOR_DATABASE_URL`
  from `.env` (the exact value the live server process had) -- raised
  `DATABASE_TARGET_MISMATCH` immediately, before any connection. Then ran it
  again with the real, actual `COMQUTOR_TEST_DATABASE_URL` -- succeeded
  cleanly, built a real repository against `comqutor_alpha_test`, left zero
  stray rows behind.

## 5. Proposed cleanup plan (NOT executed -- awaiting your confirmation)

**Backup location** (already written and restore-validated, see Section 3):
`docs/audit_artifacts/round_source_linking_t0_t2/incident_prod_db_writes_20261002/db_backup/`

**Scope**: exactly `run_id = '034a0a60-430e-41f8-8321-03a11389707a'`, nothing else.

**Proposed deletion order** (not required by any FK/cascade constraint --
none exist -- chosen only for readability: business-data tables first, the
run's own anchor/status rows last):

1. `DELETE FROM agent_outputs WHERE run_id = '034a0a60-430e-41f8-8321-03a11389707a';` -- expect 1040
2. `DELETE FROM alpha_matches WHERE run_id = '034a0a60-430e-41f8-8321-03a11389707a';` -- expect 1040
3. `DELETE FROM alpha_activations WHERE run_id = '034a0a60-430e-41f8-8321-03a11389707a';` -- expect 10
4. `DELETE FROM alpha_conflicts WHERE run_id = '034a0a60-430e-41f8-8321-03a11389707a';` -- expect 8
5. `DELETE FROM entity_alpha_exposures WHERE run_id = '034a0a60-430e-41f8-8321-03a11389707a';` -- expect 10
6. `DELETE FROM structure_graphs WHERE run_id = '034a0a60-430e-41f8-8321-03a11389707a';` -- expect 1
7. `DELETE FROM research_run_progress WHERE run_id = '034a0a60-430e-41f8-8321-03a11389707a';` -- expect 1
8. `DELETE FROM research_runs WHERE run_id = '034a0a60-430e-41f8-8321-03a11389707a';` -- expect 1

**Transaction/rollback method**: all 8 statements inside one single
transaction (`BEGIN` ... `COMMIT`). Before `COMMIT`, re-query every table's
count for this `run_id` and confirm all 8 are exactly 0; if any is not
(meaning a concurrent write happened, which should be impossible since the
server is stopped and no other process references this run_id), `ROLLBACK`
the entire transaction instead of committing, leaving production completely
untouched, and report the discrepancy rather than forcing it through. Since
there are no triggers and no FKs, a rollback at any point is fully clean --
nothing partially applied can leak through.

**Post-check**: immediately after `COMMIT`, a fresh connection re-queries
all 8 tables for this `run_id` (must be 0 everywhere) and re-confirms the
other 103 pre-existing `research_runs` rows are unchanged in count.

This plan executes only on your explicit go-ahead -- this task's own
authorization covers investigation, backup, the isolation fix, and testing
only; it does not authorize any production DELETE/UPDATE/DDL.
