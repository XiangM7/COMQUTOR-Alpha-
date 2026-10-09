#!/usr/bin/env python3
"""T4 round 32: create this round's isolated local PostgreSQL databases (loopback only) and prove none of them is a service
database. Credentials and server come from .env's COMQUTOR_TEST_DATABASE_URL (read in memory, never printed); only the
database name changes. The 8000 service's database and the 8002 T4 database are only read (row counts, READ ONLY).

  comqutor_alpha_t4_r32_pytest_test  -- the PostgreSQL integration tests on the final code
  comqutor_alpha_t4_r32_verify_test  -- the chain check: empty-database migration, production write path, restart, reopen, export
  comqutor_alpha_t4_r32_demo_test    -- a restored copy of comqutor_alpha_t4_test, served read-only by the final code for the demo

    python create_r32_databases.py --out 03_postgres/databases.json
    python create_r32_databases.py --print-url-for comqutor_alpha_t4_r32_verify_test
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
R32_DATABASES = ("comqutor_alpha_t4_r32_pytest_test", "comqutor_alpha_t4_r32_verify_test", "comqutor_alpha_t4_r32_demo_test")
PROTECTED = ("comqutor_alpha_test", "comqutor_alpha_t4_test")  # 8000 service, 8002 T4 instance (the two Fresh runs)


def url_for(database: str) -> str:
    base = make_url(dotenv_values(REPO / ".env")["COMQUTOR_TEST_DATABASE_URL"])
    return base.set(database=database).render_as_string(hide_password=False)


def run_count(database: str) -> int | None:
    try:
        engine = sa.create_engine(url_for(database))
        with engine.connect() as conn:
            conn.execute(sa.text("SET TRANSACTION READ ONLY"))
            return int(conn.execute(sa.text("select count(*) from research_runs")).scalar())
    except Exception:
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--print-url-for", choices=R32_DATABASES + ("comqutor_alpha_t4_test",))
    args = ap.parse_args(argv)
    if args.print_url_for:
        print(url_for(args.print_url_for))
        return 0
    if not args.out:
        ap.error("--out is required")
    if set(R32_DATABASES) & set(PROTECTED):
        print("refusing: a round-32 database name equals a service database", file=sys.stderr)
        return 2
    before = {name: run_count(name) for name in PROTECTED}
    admin = sa.create_engine(url_for("postgres"), isolation_level="AUTOCOMMIT")
    created, existing = [], []
    with admin.connect() as conn:
        present = set(conn.execute(sa.text("select datname from pg_database")).scalars())
        for name in R32_DATABASES:
            if name in present:
                existing.append(name)
            else:
                conn.execute(sa.text(f'CREATE DATABASE "{name}"'))
                created.append(name)
        server = conn.execute(sa.text("show server_version")).scalar()
        listing = sorted(conn.execute(sa.text("select datname from pg_database where not datistemplate")).scalars())
    after = {name: run_count(name) for name in PROTECTED}
    url = make_url(url_for(R32_DATABASES[0]))
    doc = {"taken_at": datetime.now(UTC).isoformat(), "server": {"host": url.host, "port": url.port, "version": server, "dialect": "postgresql"},
           "round32_databases": list(R32_DATABASES), "created": created, "already_existed": existing, "databases_on_server": listing,
           "protected_research_runs_count": {"before": before, "after": after, "unchanged": before == after}}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(doc))
    return 0 if not existing else 1


if __name__ == "__main__":
    raise SystemExit(main())
