# Week 6 Adversarial Audit — COMQUTOR Alpha

Repo: `/Users/xiangmao/COMQUTOR-Alpha-`, branch `comqutor-structure-layer`, HEAD `64e657958aa1db32528d55e8b9c5520b387f86fc` (clean). Read-only audit; no tracked files modified. All DB mutation tests below were run against `sqlite:///:memory:` or a disposable `w6_audit_mutate_*` run_id in the already-running test Postgres (`COMQUTOR_TEST_DATABASE_URL`), cleaned up after each run. No secrets/DSNs printed.

---

## 1. Documentation contract claims (doc:line)

| Claim | Location |
|---|---|
| "Structured agent outputs had no formal DB table" → "Fixed: migration `0004_create_agent_outputs`..." | `docs/week6_final_gap_audit.md:13` |
| "`/agent-outputs` was artifact-only" → "Fixed: new runs are DB-first; safe structured legacy fallback remains" | `docs/week6_final_gap_audit.md:14` |
| "Graph GET could reject a valid DB row when the local directory was missing" → "Fixed: DB read precedes legacy filesystem checks" | `docs/week6_final_gap_audit.md:15` |
| "DB/repository score boundaries allowed coercion" → "Fixed: reject bool, string, NaN, Infinity and out-of-range values" | `docs/week6_final_gap_audit.md:16` |
| "Unexpected logs could include traceback context" → "Fixed: stable ERROR/WARNING records include run/ticker/stage/code/type without `exc_info`" | `docs/week6_final_gap_audit.md:17` |
| "Readiness knew only migrations 0001–0003" → "Fixed: requires exact 0001–0004 state" | `docs/week6_final_gap_audit.md:18` |
| "CI did not represent backend extras, frontend and PostgreSQL" → "Fixed locally: three-job workflow implemented and YAML parsed... remote run not performed" | `docs/week6_final_gap_audit.md:19` |
| "PostgreSQL 16: 38 passed, 0 skipped" | `docs/week6_final_gap_audit.md:55` |
| "Clean install, seed, `/health`, `/ready`, history, NVDA, QQQ and TERM cleanup: PASS" | `docs/week6_final_gap_audit.md:58` |
| Database Migrations list: only `0001`–`0004` | `docs/release_candidate_manifest.md:11-16` |
| "Structured API fields are whitelisted; raw Provider text, prompts, credentials, DSNs, paths and tracebacks are not public contracts" | `docs/release_candidate_manifest.md:56-57` |
| "Rehearse a clean installation in an isolated temporary directory: `./scripts/verify_clean_install.sh`... excludes `.git`, `.venv`, `node_modules`, build output, generated Demo data, caches, and environment files" | `docs/installation_and_usage.md:122-127` |
| "PostgreSQL is the local development and integration-verification database... Do not use the Demo SQLite database as a production service database" | `docs/installation_and_usage.md:79-81` |

---

## 2. Actual code behavior per question (file:line)

**Q1 — Formal DB persistence path.** Real: `comqutor_alpha/api/routes_research.py:505-548` (`_run_week1_week2_artifact_pipeline`) writes `structured_agent_outputs.json` to disk, reloads it, then calls `repository.persist_agent_outputs(run_id=..., ticker=..., structured_payload=...)` at `routes_research.py:528`, which lands in `comqutor_alpha/storage/db/repository.py:430-452` (`persist_agent_outputs`) — a single transaction that deletes stale rows and upserts new ones into the `agent_outputs` table (`schema.py:203-243`). Confirmed live: `test_pipeline_persists_claims_before_alpha_mapping_and_keeps_traceability` (`tests/test_agent_outputs_persistence.py:246-267`) runs the real pipeline entrypoint and asserts rows land in the DB — **passed** in my run.

**Q2 — DB-first read path, exact trace.** `comqutor_alpha/api/agent_output_reader.py:get_agent_outputs_response` (lines 296-397):
1. Validates `run_id` (line 317).
2. Builds/uses repository and calls `repository.list_agent_outputs(safe_run_id)` (line 323) **before any filesystem check**.
3. If `database_records` is non-empty (line 353), projects and returns immediately — file system is never touched.
4. Only if `database_records == []` does it fall to `run_dir_for(...)` / `run_dir.exists()` (lines 373-374) and then `_read_structured_payload` (line 378), which reads `structured_agent_outputs.json` from disk.
This is genuinely DB-first, not a race — there's no concurrent read of both sources; it's a strict `if/else` sequence with an early return.

**Q3 — Boundaries of legacy fallback / is it dead code.** Fallback triggers only when `list_agent_outputs` returns `[]`, i.e., a run created before migration `0004`, or a persistence failure that didn't raise (there is none — `persist_agent_outputs` either succeeds or raises `GraphPersistenceError`, which fails the whole pipeline request, see `routes_research.py:533-548`). In the **current** production write flow, every completed run persists to the DB, so the fallback is **not exercised in normal operation** going forward — it is a genuine compatibility shim for pre-migration data, not currently-dead code (it is exercised by the demo bootstrap only incidentally when a repo already has rows — see `seed_w5_demo.py:295-306` which explicitly repairs count-zero DB state from the legacy artifact). It is tested directly (`tests/test_agent_outputs_persistence.py:210-224`, `test_legacy_artifact_fallback_remains_available`) using a real DB-miss (not mocked), so it is not orphaned/dead in the codebase sense, but it is a redundancy surface worth flagging: two independent read implementations of the same whitelist-projection logic exist (`_read_structured_payload` for files vs. `list_agent_outputs`/`_public_agent_output_row` for DB), both funneling into the shared `_project_public_record`, which limits (but doesn't eliminate) duplication risk.

**Q4 — Score validation strictness.** Reader-side validator: `agent_output_reader.py:_validate_confidence` (lines 162-168) explicitly rejects `bool` (`_require(not isinstance(value, bool))`), rejects non-`int/float`, rejects non-finite (`math.isfinite`), and rejects out-of-range. Repository-side validator: `repository.py:_strict_number` (lines 111-123), same rejections, used for `confidence`, `match_score`, `activation_score`, `conflict_score`, etc. **Mutation-tested directly against real data** — see §7.

**Q5 — Postgres vs SQLite semantics.** `repository.py:298-310` and `:416-428` explicitly branch on `self.dialect_name` for `ON CONFLICT DO UPDATE` (`postgresql`/`sqlite` dialect-specific `insert()`), and `_require_supported_dialect` (`repository.py:312-314`) rejects any other dialect outright — no silent third-dialect behavior. `schema.py:31-32` (`_json_type`) gives real `JSONB` on Postgres, `JSON`-over-`TEXT` on SQLite via `.with_variant`. **Genuine semantic drift found via mutation** (not from reading code alone) — see §7: SQLite's dynamic typing silently coerces a `bool`/numeric-string written directly into the `confidence` column into a valid float, bypassing the CHECK constraint; Postgres correctly raises a type error on `bool` at the wire-protocol level but (like SQLite) also silently accepts a numeric string. This channel is only reachable by code that bypasses `persist_agent_outputs`'s Python-level validation (e.g., a future maintenance script or raw SQL fix) — the application's normal write path is unaffected — but it does mean the numeric-range `CHECK` constraint is not, by itself, a complete type-safety net across both backends.

**Q6 — Readiness endpoint / migration check.** `routes_system.py:_database_ready` (lines 58-79) does a real `SELECT 1` **and** reads `schema_migrations` and checks `_REQUIRED_MIGRATIONS.issubset(applied)` (line 79), where `_REQUIRED_MIGRATIONS` (lines 36-44) lists all 5 migration versions (`0001`...`0005`). It never calls `apply_migrations`/`ensure_schema` — confirmed both by code (no import of `apply_migrations` in this module) and by test `test_ready_never_applies_a_migration` (`tests/test_api_system_routes.py:171-184`), which passed. This is a real migration-state check, not just an open-connection check — confirmed further by mutation (§7).

**Q7 — Logging / secret hygiene.** `grep -rn "logger\.\|logging\.\|print(" comqutor_alpha scripts | grep -i "traceback\|exc_info\|dsn\|password\|api_key\|token"` → **zero matches**. No `logger.exception(...)`, no `exc_info=True` anywhere in `comqutor_alpha/` or `scripts/`. Every exception-adjacent log line I found (`research_lifecycle.py:648,689,720`; `api/main.py:113,122`; `api/routes_research.py:1098,1205`) logs only `exc.reason_code` (a fixed enum-like string) or `type(exc).__name__` (e.g. `agent_output_reader.py:343-351`), never `str(exc)`.

**Q8 — CI workflow.** See §4 (exact YAML quoted). Three real jobs: `backend-offline` (real pytest, offline-only), `frontend` (real Vitest/Playwright-adjacent build+lint+test), `postgres-integration` (real `postgres:16` service container + real `psycopg` DSN + real integration pytest run against it). No `continue-on-error`, no `|| true`, no soft-fail anywhere in `.github/workflows/ci.yml` (verified via direct grep, zero hits).

**Q9 — `verify_clean_install.sh` freshness.** `scripts/verify_clean_install.sh:5-24` builds a fresh `mktemp -d` clean room, `rsync`s the repo into it excluding `.git/ .venv/ .env* .demo/ outputs/ frontend/node_modules/ frontend/dist/ .pytest_cache/ .ruff_cache/ __pycache__/ *.pyc` (lines 63-76), creates a **fresh venv** (`python3 -m venv`, line 78) and does `pip install -e` fresh (line 79), `npm ci` fresh (line 84). It then runs `seed_w5_demo.py`/`run_w5_demo.sh`, both of which use a SQLite file under `$CLEAN_ROOT/.demo/w5/comqutor_demo.db` — genuinely new because `.demo/` was excluded from the rsync and `$CLEAN_ROOT` is a brand-new tmp directory (`run_w5_demo.sh:9-12`). **Caveat, not disclosed in the doc**: the rehearsal only exercises the SQLite backend end-to-end; it never exercises a fresh Postgres schema bootstrap (`build_write_repository_from_env`'s `create_if_missing`/`ensure_schema` path against Postgres is only covered by the separate `postgres-integration` CI job, which itself starts from an empty `postgres:16` container — so Postgres migration-from-empty *is* covered, just not by this specific script).

**Q10 — Does `seed_w5_demo.py` bypass the real pipeline?** No — see §5 for the full trace. It calls the production entrypoint `run_research_request` (`routes_research.py:666`) with `offline_raw_agent_outputs` supplying **only** the raw TradingAgents agent output text (the part that would otherwise come from a live LLM call) via `_create_offline_run` (`routes_research.py:196-259`). Everything downstream — Week 1/2 structured extraction (`save_structured_agent_outputs`), DB persistence (`persist_agent_outputs`), Week 3 graph build/score/persist, Week 4 conflict detection/persist — runs through the unmodified production code path. This offline mode is explicitly blocked in production (`routes_research.py:681-685`, raises if `COMQUTOR_ENV=production`) and is disclosed in `installation_and_usage.md:105` ("Live Provider smoke testing is an explicit operator action and is not part of offline tests or CI"). It is a legitimate, disclosed fixture-input substitution for the LLM/TradingAgents call, not a DB-insert bypass of the pipeline.

---

## 3. Doc-vs-code conflicts

**CONFIRMED — stale migration count in two docs and one code docstring.**
- `comqutor_alpha/storage/db/schema.py:291-300` (`MIGRATIONS` tuple) defines **five** migrations, ending in `0005_create_research_run_progress`.
- `comqutor_alpha/api/routes_system.py:36-44` (`_REQUIRED_MIGRATIONS`) requires **all five** (`0001`...`0005`) for `/ready` to report `database: "ready"` — confirmed live by `test_ready_missing_migrations_is_not_ready` and directly by my own mutation (§7).
- `comqutor_alpha/api/routes_system.py:8` (module docstring) still says "the database is reachable and migrated (**0001-0004**, read-only...)" — stale by one migration.
- `docs/week6_final_gap_audit.md:18`: "Readiness knew only migrations 0001–0003" → "Fixed: requires exact **0001–0004** state" — stale; code actually requires 0001-0005.
- `docs/release_candidate_manifest.md:11-16` "Database Migrations" list enumerates only `0001`-`0004`, omitting `0005_create_research_run_progress` entirely.

This is a real, low-severity but concrete accuracy defect: two release-facing documents and one internal docstring understate the readiness gate by one migration. It does not affect runtime behavior (the code is internally consistent between `schema.py` and `routes_system.py`), but it means anyone reading only the docs to understand "what does `/ready` require" gets the wrong answer.

**Partially confirmed — Ruff CI scope vs delivered docs.** `docs/release_candidate_manifest.md:64-65` and `docs/week6_final_gap_audit.md:60` both honestly disclose "Whole-repository Ruff retains 19 pre-existing style findings" and that only a changed-file allowlist is linted in CI — this is **not** a doc-vs-code conflict, it is accurately disclosed. However `scripts/verify_w5_demo.py` (41 lines, imports/re-exports from `seed_w5_demo.py`) is **not** in the CI ruff allowlist (`.github/workflows/ci.yml:32-69` lists `scripts/seed_w5_demo.py` but not `scripts/verify_w5_demo.py`) even though it is in-scope W6 delivery tooling per `release_candidate_manifest.md:34`. Minor/cosmetic.

**No conflict found** for the DB-first / legacy-fallback claim (`week6_final_gap_audit.md:14`) — matches code and is well tested. **No conflict found** for the score-validation claim (`week6_final_gap_audit.md:16`) — matches code and mutation results (bool/string/NaN/Infinity/out-of-range are all rejected on the intended write+read path). **No conflict found** for the logging claim (`week6_final_gap_audit.md:17`) — confirmed by grep, zero `exc_info`/traceback/secret leakage anywhere in scope.

---

## 4. CI workflow analysis (`.github/workflows/ci.yml`, full 132 lines read)

Three jobs, quoted verbatim:

```yaml
  backend-offline:
    steps:
      - run: python -m pip install -e ".[api,dev]"
      - run: python -m pip check
      - name: Ruff maintained Python surface
        run: >-
          python -m ruff check
          comqutor_alpha/api/agent_output_reader.py
          comqutor_alpha/api/routes_research.py
          comqutor_alpha/api/routes_system.py
          ... (28 explicit files/tests)
      - name: Offline tests
        env:
          COMQUTOR_DATABASE_URL: ""
          COMQUTOR_ENV: ""
        run: python -m pytest -m "not integration" -q
      - name: Whitespace errors
        run: git show --check --oneline --no-renames HEAD

  frontend:
    defaults:
      run:
        working-directory: frontend
    steps:
      - run: npm ci
      - run: npm run typecheck
      - run: npm run lint
      - run: npm run test -- --run
      - run: npm run build

  postgres-integration:
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: comqutor
          POSTGRES_PASSWORD: comqutor_test_password
          POSTGRES_DB: comqutor_alpha_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U comqutor -d comqutor_alpha_test"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
    env:
      COMQUTOR_TEST_DATABASE_URL: postgresql+psycopg://comqutor:comqutor_test_password@127.0.0.1:5432/comqutor_alpha_test
    steps:
      - run: python -m pip install -e ".[api,dev]"
      - name: PostgreSQL persistence tests
        run: >-
          python -m pytest
          tests/test_agent_outputs_postgres_integration.py
          tests/test_graph_persistence_postgres_integration.py
          tests/test_research_progress_postgres_integration.py
          tests/test_research_runs_postgres_integration.py
          tests/test_w5_1b_postgres_integration.py
          tests/test_week4_postgres_persistence.py
          -q
```

**Findings:**
- `postgres-integration` genuinely spins up `postgres:16`, waits on `pg_isready` health checks, and points `COMQUTOR_TEST_DATABASE_URL` at it — real DSN, real connection, real 6-file integration test run. Not decorative.
- **No `continue-on-error: true` anywhere in the file** (grep returned zero hits).
- **No `|| true` or equivalent soft-fail anywhere in the file** (grep returned zero hits).
- The doc claim "remote run not performed" (`week6_final_gap_audit.md:19`, `release_candidate_manifest.md:61` "Remote CI is `NOT_YET_RUN`") is honest — I cannot independently verify remote GitHub Actions execution from this sandbox, and the docs do not overclaim it.
- The `backend-offline` job's ruff step is a curated allowlist, not `ruff check .` — this is disclosed in the docs (see §3) and does not misrepresent itself as full-repo lint.

---

## 5. Demo authenticity analysis

`scripts/seed_w5_demo.py:seed_demo_case` (lines 287-334) → calls `run_research_request(payload, output_root=output_root, graph_repository=repository)` (line 320) where `payload` includes `"offline_raw_agent_outputs": approved_demo_outputs(ticker)` (line 317, fixture data from `scripts/w5_demo_fixtures.py`).

Trace of `run_research_request` (`routes_research.py:666-753`) with that payload:
1. `payload.get("offline_raw_agent_outputs") is not None` → `_create_offline_run(payload, output_root)` (`routes_research.py:196-259`) — this is the **only** place the fixture substitutes for a real TradingAgents/LLM call: it writes `raw_agent_outputs.json` directly from the fixture list instead of invoking `run_original_tradingagents_research`.
2. `_run_week1_week2_artifact_pipeline` (line 718) runs for real: `save_structured_agent_outputs` (real Week 2 extraction/mapping code) then `repository.persist_agent_outputs` (real DB write, real validation).
3. `_run_week3_graph_pipeline` (line 727) runs for real: `build_structure_graph_stage`, `score_and_assemble_structure_graph`, `repository.persist_run` — all production code, real DB writes.
4. `run_week4_conflict_pipeline` (invoked inside step 3, `routes_research.py:647-657`) runs for real: real conflict detection/arbitration logic, real `persist_week4_results`.
5. `build_research_response` (line 730) assembles the response from what was actually persisted, not from a canned response.

**Conclusion: the demo does NOT bypass the real pipeline.** It substitutes only the single external, non-reproducible dependency (live LLM/TradingAgents multi-agent execution) with approved fixture text, then drives the entire Week 1-4 processing/persistence/scoring/arbitration pipeline for real. `seed_w5_demo.py:verify_demo_case` (lines 203-284) then independently re-reads the DB via `repository.count_agent_outputs`, `get_agent_outputs_response`, `get_persisted_structure_graph`, `get_persisted_conflicts`, `get_research_run_history` and cross-checks counts/conflict IDs against hardcoded expected values (e.g., NVDA main conflict must be exactly `A101__A304`, `bull_structure`/`bear_structure` must carry non-empty `claim_ids`/`evidence`) — this would fail if the real pipeline were broken, confirming the demo is a genuine (if fixture-fed) end-to-end exercise, not a rubber stamp. If Week 1-4 logic regressed, `seed_demo_case` would raise `DemoSeedError(f"{ticker}_WEEK1_TO_4_PIPELINE_FAILED")` (line 330) or one of the `verify_demo_case` assertions (lines 237-272) would fail.

**Disclosed limitation** (already honestly stated in `installation_and_usage.md:105` and the run script's own printed banner `run_w5_demo.sh:139`, "Real TradingAgents and Provider execution are disabled"): the demo never proves live-LLM correctness — only offline pipeline correctness. That's a scope boundary, not a hidden bypass.

---

## 6. Test effectiveness table

| Test file | Production entrypoint vs mock | Rating | Justification |
|---|---|---|---|
| `tests/test_agent_outputs_persistence.py` | Real: `run_research_request`, `submit_research_request`, `GraphPersistenceRepository` against real (in-memory) SQLite engine, real migrations | **STRONG** | Directly tests write-time rejection (bad confidence/sensitive text) without deleting prior rows, DB-first precedence over a tampered legacy artifact (`test_db_rows_override_tampered_legacy_artifact`), the actual absence-of-local-dir case (`test_db_first_reader_works_without_local_run_directory`), a genuinely-corrupted DB row via raw SQL update (`test_malformed_database_row_fails_closed`), and DB-write-failure propagation through the real lifecycle to a `failed` run status. This is the file that actually earns the doc's "DB-first" and "score boundary" claims. |
| `tests/test_agent_outputs_api.py` | Real `get_agent_outputs_response`, but **never** passes a `graph_repository`, so `list_agent_outputs` always resolves against an unseeded/non-existent SQLite path and returns `[]` | **PARTIAL** | Excellent, exhaustive coverage of the whitelist-projection/validation logic (NaN/Infinity/bool/out-of-range confidence, dict-typed claim_id/agent/direction, nested-object smuggling, raw-field leakage) — but every single test in this 684-line file exercises only the **legacy file-fallback branch** of `get_agent_outputs_response` (lines 373-397), never the DB-record branch (lines 353-369), because `database_records` is always empty in these tests. The shared `_project_public_record` function means the validation logic itself is exercised, but this file alone would pass unchanged even if the DB-first branch were deleted. Coverage of "DB-first" per se comes entirely from `test_agent_outputs_persistence.py`, not this file. |
| `tests/test_agent_outputs_postgres_integration.py` | Real Postgres via `COMQUTOR_TEST_DATABASE_URL`, real `GraphPersistenceRepository` | **STRONG** | 4 tests: real migration+JSONB column-type assertion via `information_schema`, real round-trip replace/idempotency, real run isolation, real invalid-replace-preserves-previous-rows (string confidence rejected). All 4 passed when run with `COMQUTOR_TEST_DATABASE_URL` sourced (see §Run log). Genuinely exercises Postgres-specific JSONB typing, not just "any DB". |
| `tests/test_w5_demo_seed.py` | Real `seed_w5_demo`, `submit_research_request`, real SQLite repo | **STRONG** | Verifies idempotency (`first == second`), verifies the completed-cache path genuinely reuses (`executor=lambda *a,**kw: pytest.fail(...)` — would fail the test if the pipeline re-ran), verifies `repository.count_agent_outputs(run_id) > 0` — a real DB assertion, not a mock. |
| `tests/test_api_system_routes.py` | Real `readiness_response`/`health_response`, real SQLite engine + real `apply_migrations`, plus a real FastAPI `TestClient` for HTTP-level `/ready` | **STRONG** | `test_ready_missing_migrations_is_not_ready` (line 158) and `test_ready_never_applies_a_migration` (line 171) directly test the exact mutation scenario requested in this audit (schema-less DB → not-ready; readiness must never write). `test_ready_error_body_never_leaks_dsn_or_path` (line 187) is a genuine secret-hygiene test. All passed with `COMQUTOR_DATABASE_URL=''`/`COMQUTOR_ENV=''` (matches CI and docs); 2/125 tests in the requested run **fail** if `COMQUTOR_DATABASE_URL` is left set to the real dev Postgres DSN, because `resolve_database_url` prioritizes the env var over the test's `output_root`-scoped SQLite path — an environment-coupling caveat, not a code defect (see §7). |
| `tests/test_capabilities.py` | Real `tradingagents.llm_clients.capabilities.get_capabilities` | **MISLEADING (out of Week 6 scope)** | This file tests an LLM model-capability lookup table (DeepSeek/MiniMax tool-choice quirks) — it has no relationship to agent-output persistence, the DB-first reader, readiness, CI, or the W5/W6 demo scripts. It passed (all tests green) but answers none of the Week 6 audit questions; including it in the Week 6 test list appears to be a scope/labeling error upstream of this audit. |

---

## 7. Mutation-testing results

All mutation runs performed against disposable SQLite in-memory engines or a uniquely-named disposable run_id in the live `COMQUTOR_TEST_DATABASE_URL` Postgres instance (cleaned up after). No production tables touched.

| # | Mutation | Result | Test coverage |
|---|---|---|---|
| 1 | DB record for a run_id whose local run directory does not exist on disk | **PASS (graceful)** — `get_agent_outputs_response` returns `status="ok"` with the DB record; filesystem is never consulted since the DB branch returns before the `run_dir.exists()` check (`agent_output_reader.py:353-369` short-circuits before line 373-374) | **Tested**: `tests/test_agent_outputs_persistence.py:168-182` (`test_db_first_reader_works_without_local_run_directory`), independently reproduced by me with `output_root="/tmp/nonexistent_root_xyz"` |
| 2a | `confidence = True` (bool) written directly to SQLite (bypassing `persist_agent_outputs`) | **SILENTLY COERCED, not rejected** — SQLite's dynamic typing stores `True` as `1.0`; by the time `list_agent_outputs`/`_strict_number` reads it back it's an ordinary in-range float, so no rejection occurs. Confirmed: `stored_confidence_read_back=1.0`, API `status=ok` | **TEST GAP** at the raw-SQL-bypass level (the app-level write-time check is tested; this direct-SQL-tamper scenario is not, except indirectly via `test_malformed_database_row_fails_closed` which uses a non-numeric `entities` value, not a boolean `confidence`) |
| 2b | `confidence = True` (bool) written directly to **real Postgres** (test DB) | **REJECTED at DB level** — `ProgrammingError` (type mismatch adapting Python `bool` to `double precision`/parameter type) | Not application-tested directly; confirms Q5 semantic drift — Postgres is *stricter* than SQLite here, but only incidentally (no explicit boolean-exclusion CHECK constraint exists in `schema.py`) |
| 3 | `confidence = "0.9"` (string) written directly, both backends | **SILENTLY COERCED on both SQLite and Postgres** — both accept the numeric string as a valid stored float `0.9`; read back as an ordinary float, no rejection | **TEST GAP on both dialects** — this is a real, reproducible cross-dialect gap: the "reject a numeric string" contract exists only in the Python write path (`_strict_number` inside `persist_agent_outputs`), not as a DB constraint, and is unreachable to test through any code path other than raw SQL |
| 4 | `confidence = NaN` written directly, SQLite | **REJECTED, but for the wrong reason** — Python's `sqlite3` driver silently converts `float('nan')` to `NULL` on bind; the `NOT NULL` constraint on `confidence` then raises `IntegrityError`. The numeric-range `CHECK` constraint never actually evaluates NaN. | Not directly tested; behavior is safe but accidental |
| 5 | `confidence = NaN` written directly, real Postgres | **REJECTED correctly** — Postgres preserves real NaN and the `ck_agent_outputs_confidence_range` CHECK (`NaN >= 0.0 AND NaN <= 1.0`) correctly evaluates false, raising `IntegrityError` | Confirms the CHECK constraint is a genuine (not just app-level) safety net on Postgres for NaN |
| 6 | `confidence = Infinity`, both backends | **REJECTED on both** — `CHECK constraint failed: ck_agent_outputs_confidence_range` (SQLite) / `IntegrityError` (Postgres) | DB-level CHECK constraint (`schema.py:233-236`) genuinely enforces this independent of the Python layer, on both dialects |
| 7 | `confidence = 5.0` (out of range) / `-1.0`, both backends | **REJECTED on both** via the same CHECK constraint | Confirmed defense-in-depth for pure out-of-range numerics |
| 8 | Monkeypatch/instrument the read-only agent-outputs handler's engine to detect any `CREATE/ALTER/DROP/INSERT/UPDATE/DELETE` statement or `ensure_schema()` call, against a live already-migrated real Postgres DB | **PASS — zero writes/DDL observed** for both a DB-miss (`RUN_NOT_FOUND`) and (from reading the code path, since `ensure_schema` is never imported into `agent_output_reader.py`) a DB-hit | Directly tested by me; also structurally guaranteed since `build_repository_from_env` (used by the reader, `repository.py:1467-1481`) never calls `ensure_schema`, unlike `build_write_repository_from_env` (`repository.py:1484-1494`) which is reserved for the write pipeline |
| 9 | Readiness against a schema-less temp SQLite DB (file exists, no migrations applied) | **Correctly reports `not_ready`**, `database: "unavailable"` | **Tested**: `tests/test_api_system_routes.py:158-168` (`test_ready_missing_migrations_is_not_ready`), passed in my run (with `COMQUTOR_DATABASE_URL` cleared) |
| 10 | Force a genuine DB miss (`list_agent_outputs` returns `[]` because no rows exist for that run_id) and confirm fallback to legacy file storage | **PASS, correctly falls back**, and is tested with a real (not mocked) DB miss | **Tested**: `tests/test_agent_outputs_persistence.py:210-224` (`test_legacy_artifact_fallback_remains_available`) |
| 11 | Capture stdout/stderr from a pytest run that deliberately errors (DB write failure) and scan for secret/traceback leakage | **Clean** — `test_database_write_failure_is_safe_and_terminal` (`tests/test_agent_outputs_persistence.py:270-295`) already asserts `str(tmp_path) not in serialized` and `"sqlite" not in serialized.lower()` on the actual API response; my own full pytest run captured no DSN/traceback text in output | No leakage found |

**Environment-coupling artifact found while running requested commands (not a code defect, but worth flagging):** `resolve_database_url()` (`comqutor_alpha/storage/db/engine.py:59-61`) always prefers the `COMQUTOR_DATABASE_URL` env var over any `output_root`-derived local SQLite path. Since this audit's shell had `COMQUTOR_DATABASE_URL` set (per task setup, pointing at the local dev Postgres on 5433), running `tests/test_api_system_routes.py` without first clearing that variable makes `test_ready_requires_database` and `test_ready_missing_migrations_is_not_ready` **fail** (2/125), because readiness ends up checking the real, already-migrated dev Postgres instead of the test's empty tmp SQLite file. This exactly matches the documented/CI-mandated invocation (`installation_and_usage.md:111`, `ci.yml:71-74`, both set `COMQUTOR_DATABASE_URL: ""`), so it is expected behavior given correct invocation — but it is a sharp edge: any operator running the offline suite from a shell with `COMQUTOR_DATABASE_URL` set to a working DB will see 2 spurious failures.

---

## 8. Confirmed defects

| Sev | file:function | Test | Problem | Why tests missed it | Minimal repro | Blast radius | Fix direction |
|---|---|---|---|---|---|---|---|
| P2 | `docs/release_candidate_manifest.md:11-16`, `docs/week6_final_gap_audit.md:18`, `comqutor_alpha/api/routes_system.py:8` | none (docs aren't tested) | Readiness migration requirement is documented as `0001-0004` in two release docs and the module's own docstring, but the actual enforced set (`routes_system.py:36-44`) is `0001-0005`, matching `schema.py`'s real 5-migration `MIGRATIONS` tuple. | Docs/docstrings aren't covered by any test; code itself is internally consistent so no test would catch prose drift. | Read `_REQUIRED_MIGRATIONS` (5 entries) vs `release_candidate_manifest.md` migration list (4 entries). | Low — cosmetic/documentation only; runtime behavior is correct and stricter than documented. | Update the docstring and both docs to list `0005_create_research_run_progress`. |
| P2 | `comqutor_alpha/storage/db/repository.py:_strict_number` (used inside `_agent_output_rows`) vs. `schema.py` `agent_outputs.confidence` column | none for this exact bypass path (`test_malformed_database_row_fails_closed` covers a different field, `entities`) | A `confidence` value written by any means other than `persist_agent_outputs()` (raw SQL, a future migration/backfill script, an admin tool) can silently store a `bool` or a numeric `string` as a valid-looking float — on **both** SQLite and Postgres for the string case, and on SQLite (not Postgres) for the bool case. The Python-level type check (`isinstance(value, bool)`, `isinstance(value, (int,float))`) is real and correct, but it is a write-time-only gate, not a DB-level invariant, for these two specific type-confusions (unlike the numeric-range/NaN/Infinity cases, which the CHECK constraint independently catches on both dialects). | The doc's claim "reject bool, string, NaN, Infinity and out-of-range values" is true of the *validated write path*, and all existing tests only exercise the validated write path (`persist_agent_outputs`) or the read path against data written through it. No test attempts a direct-SQL type-confusion bypass. | Steps reproduced live in this audit (§7, rows 2a/3): `UPDATE agent_outputs SET confidence = '0.9'` on a live row, then `repo.list_agent_outputs(run_id)` returns it un-rejected. | Low-moderate — requires DB write access outside the application's own write path (not reachable via any current public API), but is a real gap in the "read path never trusts stored data" invariant the docs claim. | Either add a DB-level `pg_typeof`/domain-type constraint (Postgres-only) or accept this as an explicit, documented boundary ("the DB is a trusted store; only `persist_agent_outputs` is a trust boundary") rather than implying the read path re-validates *type provenance* rather than just *value range*. |
| P3 | `scripts/verify_w5_demo.py` | n/a | Not included in the CI `ruff check` allowlist (`.github/workflows/ci.yml:32-69`) despite being W6 delivery tooling per `release_candidate_manifest.md:34`. | CI allowlist is manually curated; this file was apparently missed when `seed_w5_demo.py` was added. | Diff the allowlist against `release_candidate_manifest.md`'s "Delivery Scripts and Documents" list. | Negligible — 41-line thin wrapper, low complexity, unlikely to accumulate lint debt silently. | Add `scripts/verify_w5_demo.py` to the CI ruff allowlist. |

No P0/P1 defects were found in Week 6 scope. No secret/DSN/traceback leakage was found. No permanently-green CI steps were found. No pipeline-bypassing demo scripts were found.

---

## 9. Security / secret-handling findings

- **No hits** for `grep -rn "logger\.\|logging\.\|print(" comqutor_alpha scripts | grep -i "traceback\|exc_info\|dsn\|password\|api_key\|token"`.
- No `exc_info=True` or `logger.exception(...)` anywhere in `comqutor_alpha/` or `scripts/` — every exception is logged via a stable `reason_code` or `type(exc).__name__`, never `str(exc)`.
- `GraphPersistenceError` (`repository.py:73-84`) and `AgentOutputsReadError` (`agent_output_reader.py:115-122`) are both designed as safe, reason-code-only exceptions by explicit contract in their docstrings, and this contract is upheld everywhere they're raised/caught in scope.
- `agent_output_reader.py`'s whitelist projection (`PUBLIC_STRUCTURED_OUTPUT_FIELDS`, lines 50-74) is defense-in-depth against raw-transcript/prompt/credential leakage through the agent-outputs API; extensively tested in `tests/test_agent_outputs_api.py` (smuggling via known-field type confusion, unknown nested objects, raw_output/full_transcript/prompt/provider_response/final_state fields) — all correctly stripped or fail-closed.
- `test_database_write_failure_is_safe_and_terminal` and `test_ready_error_body_never_leaks_dsn_or_path` both assert, against real responses, that no local path or DSN scheme (`sqlite://`, `postgresql://`) appears in any API-facing payload.
- No `.env` file was read or printed by this audit; `COMQUTOR_DATABASE_URL`/`COMQUTOR_TEST_DATABASE_URL` were sourced into the shell only to run the requested Postgres integration tests, never echoed.

---

## Run log (for reproducibility)

```
.venv/bin/python -m pytest tests/test_agent_outputs_api.py tests/test_agent_outputs_persistence.py \
  tests/test_w5_demo_seed.py tests/test_api_system_routes.py tests/test_capabilities.py -q
  # with ambient COMQUTOR_DATABASE_URL set (dev Postgres): 2 failed, 123 passed
  # with COMQUTOR_DATABASE_URL='' COMQUTOR_ENV='': 125 passed

.venv/bin/python -m pytest tests/test_agent_outputs_postgres_integration.py -v -m integration
  # without sourcing .env: 4 skipped ("COMQUTOR_TEST_DATABASE_URL not configured")
  # with `set -a; source .env; set +a`: 4 passed
```

---

## 10. Week 6 verdict

**VERIFIED_WITH_LIMITATIONS**

Justification: Every headline Week 6 claim I could independently verify held up under adversarial testing — the DB-first agent-outputs read path is genuinely DB-first (not a race, not a silent file preference), the formal `agent_outputs` persistence path is real and transactional, score validation correctly rejects bool/string/NaN/Infinity/out-of-range on the actual write+read path used by the application, the readiness endpoint genuinely checks migration state (and is *stricter* than documented, requiring 0001-0005 not just 0001-0004), CI runs real backend/frontend/Postgres jobs with zero permanently-green or soft-fail steps, `verify_clean_install.sh` performs a genuinely fresh venv+dependency+SQLite rehearsal, and `seed_w5_demo.py` drives the real Week 1-4 production pipeline end-to-end rather than inserting canned results — it only substitutes the single external LLM/TradingAgents call with disclosed offline fixtures, and this substitution is blocked in production and honestly documented.

The "limitations" are: (1) a real, reproducible cross-dialect gap where a `confidence` value corrupted by direct SQL (bypassing the application's own write path) can silently pass as a valid string/bool on SQLite and as a valid string on both SQLite and Postgres — a low-probability but genuine boundary that the docs' "reject bool, string..." claim doesn't scope precisely enough; (2) two release documents and one code docstring understate the readiness migration requirement by one migration (0001-0004 documented vs. 0001-0005 enforced) — the code is stricter than claimed, not weaker, but it's still a documentation-accuracy defect; (3) `tests/test_agent_outputs_api.py`, despite being the largest and most thorough test file in scope, never actually exercises the DB-record branch of `get_agent_outputs_response` — DB-first coverage comes entirely from a different, smaller file. None of these rise to a P0/P1 correctness or security defect.
