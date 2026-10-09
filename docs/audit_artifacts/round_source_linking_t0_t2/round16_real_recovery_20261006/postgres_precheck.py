#!/usr/bin/env python3
"""Round 16 pre-send check: the derived-run save path and API reads on PostgreSQL, with fixed-response
(fake HTTP) test material only.

Safety design:
  * connects ONLY with the isolated TEST database credentials (COMQUTOR_TEST_DATABASE_URL from .env; its
    database name must end in _test and the host must be loopback). It never reads, connects to, or names the
    production URL's database.
  * the derived-run tests run against a freshly created SCRATCH database on that same server
    (comqutor_alpha_r16_precheck_test), not against comqutor_alpha_test: nothing it writes can appear in the
    database the UI/backend reads, and cleanup is a single DROP DATABASE.
  * read-only look at the real test database's schema_migrations, so the real run is known not to apply a
    surprise migration.
  * the pytest subprocess gets a fake DEEPSEEK_API_KEY; the tests only use httpx.MockTransport.
  * the scratch database is dropped in a finally block and its absence is verified.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))
SCRATCH_DB = "comqutor_alpha_r16_precheck_test"

result = {"started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "scratch_database": SCRATCH_DB, "steps": []}


def step(name, **info):
    result["steps"].append({"step": name, **info})
    print(f"[precheck] {name}: {json.dumps(info, default=str)[:400]}", flush=True)


def finish(code):
    result["exit_code"] = code
    (HERE / "postgres_precheck_result.json").write_text(json.dumps(result, indent=2, default=str))
    sys.exit(code)


test_url = dotenv_values(REPO / ".env").get("COMQUTOR_TEST_DATABASE_URL")
if not test_url:
    step("abort", reason="COMQUTOR_TEST_DATABASE_URL is not defined in .env")
    finish(1)
parsed = make_url(test_url)
if not (parsed.database or "").endswith("_test") or parsed.host not in ("127.0.0.1", "localhost", "::1"):
    step("abort", reason="the test URL is not an isolated loopback *_test database", database=parsed.database, host=parsed.host)
    finish(1)
step("isolated_target", server=f"{parsed.host}:{parsed.port}", test_database=parsed.database, scratch_database=SCRATCH_DB,
     production_database_touched=False)

admin = create_engine(test_url, isolation_level="AUTOCOMMIT")
scratch_url = parsed.set(database=SCRATCH_DB)
try:
    with admin.connect() as conn:
        step("server", version=conn.execute(text("select version()")).scalar().split(",")[0])
        from comqutor_alpha.storage.db.schema import COLUMN_MIGRATIONS, MIGRATIONS

        wanted = {version for version, _ in MIGRATIONS} | {version for version, _, _ in COLUMN_MIGRATIONS}
        applied = {row[0] for row in conn.execute(text("select version from schema_migrations"))}
        active = conn.execute(text("select count(*) from research_runs where status in ('queued','running')")).scalar()
        step("real_test_database_read_only", repo_migrations=len(wanted), applied=len(applied & wanted),
             unapplied_in_real_test_db=sorted(wanted - applied), active_runs_now=active)
        existing = conn.execute(text("select 1 from pg_database where datname = :n"), {"n": SCRATCH_DB}).scalar()
        if existing:
            step("abort", reason="scratch database already exists; refusing to reuse or drop something I did not create")
            finish(1)
        conn.execute(text(f'CREATE DATABASE "{SCRATCH_DB}"'))
        step("scratch_database_created")

    env = {**os.environ,
           "COMQUTOR_R16_PRECHECK_DATABASE_URL": scratch_url.render_as_string(hide_password=False),
           "DEEPSEEK_API_KEY": "precheck-not-a-real-key"}
    env.pop("COMQUTOR_DATABASE_URL", None)
    completed = subprocess.run(
        [str(REPO / ".venv/bin/python"), "-m", "pytest", "tests/test_classification_recovery_derived_run.py", "-q", "-p", "no:cacheprovider"],
        cwd=REPO, env=env, capture_output=True, text=True)
    tail = [line for line in completed.stdout.splitlines() if line.strip()][-6:]
    (HERE / "postgres_precheck_pytest_output.log").write_text(completed.stdout.replace(scratch_url.password or "\0", "REDACTED") + completed.stderr[-2000:])
    step("derived_run_tests_on_postgres", returncode=completed.returncode, summary=tail[-1] if tail else None)

    with create_engine(scratch_url).connect() as conn:
        counts = {t: conn.execute(text(f"select count(*) from {t}")).scalar()
                  for t in ("research_runs", "agent_outputs", "alpha_activations", "graph_snapshots") if
                  conn.execute(text("select to_regclass(:t)"), {"t": t}).scalar()}
    step("scratch_database_contents_after_tests", **counts)
    result["tests_passed"] = completed.returncode == 0
finally:
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        gone = not conn.execute(text("select 1 from pg_database where datname = :n"), {"n": SCRATCH_DB}).scalar()
        leftovers = [row[0] for row in conn.execute(text("select datname from pg_database where datname like '%r16_precheck%'"))]
    step("scratch_database_dropped", verified_absent=gone, leftover_precheck_databases=leftovers)

finish(0 if result.get("tests_passed") and gone else 1)
