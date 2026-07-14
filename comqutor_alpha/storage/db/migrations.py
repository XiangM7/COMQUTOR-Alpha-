"""Explicit, idempotent migration runner for Week 3 tables.

Not Alembic: migrations are plain (version_id, tables) entries in
``schema.MIGRATIONS``, applied through SQLAlchemy Core DDL (dialect-portable
across PostgreSQL and SQLite) and recorded in a ``schema_migrations`` table.
Re-applying is always safe -- ``CREATE TABLE IF NOT EXISTS`` semantics via
``checkfirst`` plus a version guard so a given migration's "applied" row is
only ever inserted once.
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from comqutor_alpha.storage.db.schema import MIGRATIONS, schema_migrations


def applied_migration_versions(engine: Engine) -> set[str]:
    schema_migrations.create(engine, checkfirst=True)
    with engine.connect() as conn:
        rows = conn.execute(sa.select(schema_migrations.c.version))
        return {row[0] for row in rows}


def apply_migrations(engine: Engine) -> list[str]:
    """Apply any not-yet-applied migration, in order. Returns newly applied versions."""
    already_applied = applied_migration_versions(engine)
    newly_applied: list[str] = []
    for version, tables in MIGRATIONS:
        if version in already_applied:
            continue
        for table in tables:
            table.create(engine, checkfirst=True)
        with engine.begin() as conn:
            conn.execute(
                sa.insert(schema_migrations).values(version=version, applied_at=datetime.now(UTC))
            )
        newly_applied.append(version)
    return newly_applied
