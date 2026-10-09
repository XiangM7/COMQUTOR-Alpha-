"""Explicit, idempotent migration runner for Week 3 tables.

Not Alembic: migrations are plain (version_id, tables) entries in
``schema.MIGRATIONS``, applied through SQLAlchemy Core DDL (dialect-portable
across PostgreSQL and SQLite) and recorded in a ``schema_migrations`` table.
Re-applying is always safe -- ``CREATE TABLE IF NOT EXISTS`` semantics via
``checkfirst`` plus a version guard so a given migration's "applied" row is
only ever inserted once.

``schema.COLUMN_MIGRATIONS`` (COMQUTOR Alpha T1 next-round task, 2026-09-28)
is a second, distinct migration kind: ``table.create(checkfirst=True)`` is a
no-op against an ALREADY-EXISTING table, so it can never add a new column to
one -- every migration before this one only ever created whole new tables.
:func:`apply_column_migrations` instead issues a real, dialect-portable
``ALTER TABLE ... ADD COLUMN`` for each column genuinely missing from the
live table (checked via ``sa.inspect``, never assumed), tracked in the SAME
``schema_migrations`` table under its own version id so re-applying is
exactly as safe as the table-creation migrations above.
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from comqutor_alpha.storage.db.schema import COLUMN_MIGRATIONS, MIGRATIONS, schema_migrations


def applied_migration_versions(engine: Engine) -> set[str]:
    schema_migrations.create(engine, checkfirst=True)
    with engine.connect() as conn:
        rows = conn.execute(sa.select(schema_migrations.c.version))
        return {row[0] for row in rows}


def _add_columns_if_missing(engine: Engine, table: sa.Table, columns: tuple[sa.Column, ...]) -> None:
    inspector = sa.inspect(engine)
    existing = {col["name"] for col in inspector.get_columns(table.name)}
    with engine.begin() as conn:
        for column in columns:
            if column.name in existing:
                continue
            column_type = column.type.compile(dialect=engine.dialect)
            nullable_clause = "" if column.nullable else " NOT NULL"
            conn.execute(
                sa.DDL(f'ALTER TABLE {table.name} ADD COLUMN "{column.name}" {column_type}{nullable_clause}')
            )


def apply_column_migrations(engine: Engine) -> list[str]:
    """Apply any not-yet-applied entry in ``schema.COLUMN_MIGRATIONS``, in
    order. Returns newly applied versions. Every column added this way must
    already be declared nullable in ``schema.py`` (checked implicitly: a
    NOT NULL addition to a table with existing rows would fail on a real
    database with no default, which is exactly the safety net a genuinely
    additive migration should have)."""
    already_applied = applied_migration_versions(engine)
    newly_applied: list[str] = []
    for version, table, columns in COLUMN_MIGRATIONS:
        if version in already_applied:
            continue
        _add_columns_if_missing(engine, table, columns)
        with engine.begin() as conn:
            conn.execute(
                sa.insert(schema_migrations).values(version=version, applied_at=datetime.now(UTC))
            )
        newly_applied.append(version)
    return newly_applied


def apply_migrations(engine: Engine) -> list[str]:
    """Apply any not-yet-applied migration, in order (table-creation
    migrations first, then additive-column migrations). Returns newly
    applied versions from both."""
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
    newly_applied.extend(apply_column_migrations(engine))
    return newly_applied
