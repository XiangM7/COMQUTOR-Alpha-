#!/usr/bin/env python3
"""T4 Phase A: create the two isolated local PostgreSQL databases (loopback only) and prove they are not the 8000 service's database.

  comqutor_alpha_t4_test         -- the T4 instance (port 8002): verification runs, then the NVDA Fresh Run
  comqutor_alpha_t4_pytest_test  -- the PostgreSQL integration tests (they create/truncate their own tables)

Credentials and server come from .env's COMQUTOR_TEST_DATABASE_URL (read in memory, never printed); only the database name changes.
The 8000 service's database is only read (row count of research_runs, in a READ ONLY transaction) before and after.

    python create_t4_databases.py --out 01_postgres/databases.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
T4_DATABASES = ("comqutor_alpha_t4_test", "comqutor_alpha_t4_pytest_test", "comqutor_alpha_t4_rehearsal_test")


def url_for(database: str) -> str:
    base = make_url(dotenv_values(REPO / ".env")["COMQUTOR_TEST_DATABASE_URL"])
    return base.set(database=database).render_as_string(hide_password=False)


def service_db_name() -> str:
    return make_url(dotenv_values(REPO / ".env")["COMQUTOR_TEST_DATABASE_URL"]).database


def research_run_count(database: str) -> int:
    engine = sa.create_engine(url_for(database))
    with engine.connect() as conn:
        conn.execute(sa.text("SET TRANSACTION READ ONLY"))
        return int(conn.execute(sa.text("select count(*) from research_runs")).scalar())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--print-url-for", choices=T4_DATABASES, help="print that T4 database's URL to stdout (for the launcher's own export)")
    args = ap.parse_args(argv)
    if args.print_url_for:
        print(url_for(args.print_url_for))
        return 0
    if not args.out:
        ap.error("--out is required")
    service_db = service_db_name()
    if service_db in T4_DATABASES:
        print("refusing: T4 database name equals the service database", file=sys.stderr)
        return 2
    before = research_run_count(service_db)
    admin = sa.create_engine(url_for("postgres"), isolation_level="AUTOCOMMIT")
    created, existing = [], []
    with admin.connect() as conn:
        present = set(conn.execute(sa.text("select datname from pg_database")).scalars())
        for name in T4_DATABASES:
            if name in present:
                existing.append(name)
            else:
                conn.execute(sa.text(f'CREATE DATABASE "{name}"'))
                created.append(name)
        listing = sorted(conn.execute(sa.text("select datname from pg_database where not datistemplate")).scalars())
        server = {"version": conn.execute(sa.text("show server_version")).scalar()}
    after = research_run_count(service_db)
    url = make_url(url_for(T4_DATABASES[0]))
    doc = {"taken_at": datetime.now(timezone.utc).isoformat(), "server": {"host": url.host, "port": url.port, **server},
           "service_8000_database": service_db, "t4_databases": list(T4_DATABASES), "created": created, "already_existed": existing,
           "databases_on_server": listing,
           "service_8000_research_runs_count": {"before": before, "after": after, "unchanged": before == after},
           "isolation": {name: name != service_db for name in T4_DATABASES}}
    Path(args.out).write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(doc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
