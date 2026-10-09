#!/usr/bin/env python3
"""T4 round 32: a read-only demo copy of the T4 instance's data, for the final-code instance (start_r32_instance.sh demo).

1. comqutor_alpha_t4_test (the database the two Fresh runs live in) is dumped with pg_dump inside the PostgreSQL container
   (a read-only snapshot of the source) and restored into the empty comqutor_alpha_t4_r32_demo_test.
2. outputs/t4_runs is copied to outputs/t4_r32_demo_runs; every file hash of the copy must equal the original.
3. Row counts of every table in source and copy are compared; the source's counts are taken before and after (unchanged).

The credentials are read from .env in memory and passed to the container through its environment, never printed.

    python prepare_demo_copy.py --out 07_demo/demo_copy.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.engine import make_url

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
CONTAINER = "comqutor-alpha--postgres-1"
SOURCE_DB, DEMO_DB = "comqutor_alpha_t4_test", "comqutor_alpha_t4_r32_demo_test"
SOURCE_ROOT, DEMO_ROOT = REPO / "outputs" / "t4_runs", REPO / "outputs" / "t4_r32_demo_runs"


def url_for(db: str) -> str:
    return subprocess.run([sys.executable, str(HERE / "create_r32_databases.py"), "--print-url-for", db], capture_output=True, text=True,
                          check=True).stdout.strip()


def counts(db: str) -> dict[str, int]:
    engine = sa.create_engine(url_for(db))
    with engine.connect() as conn:
        conn.execute(sa.text("SET TRANSACTION READ ONLY"))
        tables = sorted(conn.execute(sa.text("select tablename from pg_tables where schemaname='public'")).scalars())
        return {t: int(conn.execute(sa.text(f'select count(*) from "{t}"')).scalar()) for t in tables}


def tree(directory: Path) -> dict[str, str]:
    return {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(directory.rglob("*")) if p.is_file()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if DEMO_ROOT.exists():
        print(f"refusing: {DEMO_ROOT} exists", file=sys.stderr)
        return 2
    if counts(DEMO_DB):
        print("refusing: the demo database is not empty", file=sys.stderr)
        return 2
    source_before = counts(SOURCE_DB)
    url = make_url(url_for(SOURCE_DB))
    env = {**os.environ, "PGPASSWORD": url.password or ""}
    dump = subprocess.run(["docker", "exec", "-e", "PGPASSWORD", CONTAINER, "pg_dump", "-U", url.username, "-d", SOURCE_DB, "--no-owner", "--no-privileges"],
                          capture_output=True, env=env, check=True).stdout
    restore = subprocess.run(["docker", "exec", "-i", "-e", "PGPASSWORD", CONTAINER, "psql", "-q", "-v", "ON_ERROR_STOP=1", "-U", url.username, "-d", DEMO_DB],
                             input=dump, capture_output=True, env=env)
    source_after = counts(SOURCE_DB)
    demo = counts(DEMO_DB)
    original = tree(SOURCE_ROOT)
    shutil.copytree(SOURCE_ROOT, DEMO_ROOT)
    copy = tree(DEMO_ROOT)
    doc = {"taken_at": datetime.now(UTC).isoformat(), "source_database": SOURCE_DB, "demo_database": DEMO_DB,
           "dump_bytes": len(dump), "dump_sha256": hashlib.sha256(dump).hexdigest(), "restore_exit_code": restore.returncode,
           "restore_stderr_tail": restore.stderr.decode(errors="replace")[-500:],
           "source_counts_before": source_before, "source_counts_after": source_after, "source_unchanged": source_before == source_after,
           "demo_counts": demo, "demo_equals_source": demo == source_before,
           "output_root_copy": {"from": str(SOURCE_ROOT.relative_to(REPO)), "to": str(DEMO_ROOT.relative_to(REPO)), "files": len(copy),
                                "byte_identical": copy == original, "original_unchanged": tree(SOURCE_ROOT) == original}}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: doc[k] for k in ("restore_exit_code", "source_unchanged", "demo_equals_source", "output_root_copy")}))
    return 0 if restore.returncode == 0 and doc["demo_equals_source"] and doc["output_root_copy"]["byte_identical"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
