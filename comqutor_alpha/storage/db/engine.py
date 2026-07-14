"""Database engine construction.

Reads ``COMQUTOR_DATABASE_URL`` from the server process environment only --
never from an HTTP request payload or client-supplied configuration. When
unset, falls back to a local SQLite file so default execution stays fully
offline (no external service required for tests or local development) --
*except* in production, where a silent SQLite fallback would mean the
"real" persistence layer quietly never runs. See ``resolve_database_url``.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

from comqutor_alpha.storage.file_store import resolve_output_root

DEFAULT_SQLITE_FILENAME = "_comqutor_alpha_graph.db"


class DatabaseConfigurationError(Exception):
    """Safe database-configuration error: carries a stable reason code only.

    Never carries a DSN, file path, or raw exception text.
    """

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def _is_production() -> bool:
    return os.environ.get("COMQUTOR_ENV", "").strip().lower() == "production"


def resolve_database_url(output_root: str | None = None) -> str:
    """Resolve the DSN to use: server env var, else a local SQLite fallback.

    Pure computation -- performs no filesystem mutation (no directory
    creation). Callers that intend to actually connect/write use
    :func:`build_engine`'s ``create_if_missing`` to control whether the
    local SQLite directory gets created; a read-only caller can resolve the
    same URL without provisioning anything.

    The SQLite fallback file is deliberately named with a ``.`` (not a valid
    ``run_id`` character), placed alongside the run directories so it is
    never mistaken for -- or collides with -- an actual run.

    In production (``COMQUTOR_ENV=production``), there is no SQLite
    fallback: a missing ``COMQUTOR_DATABASE_URL`` raises
    ``DatabaseConfigurationError`` rather than silently persisting to a
    local file that would never be backed up, shared across instances, or
    inspected as "the real database". Development and tests are unaffected.
    """
    env_url = os.environ.get("COMQUTOR_DATABASE_URL", "").strip()
    if env_url:
        return env_url
    if _is_production():
        raise DatabaseConfigurationError("PRODUCTION_DATABASE_URL_REQUIRED")
    root = resolve_output_root(output_root)
    return f"sqlite:///{root / DEFAULT_SQLITE_FILENAME}"


def _is_sqlite_memory_url(url: str) -> bool:
    return url.startswith("sqlite://") and (":memory:" in url or url.rstrip("/") == "sqlite:/")


def sqlite_file_path(database_url: str) -> Path | None:
    """Return the local file path for a file-based (non-memory) SQLite DSN.

    Returns ``None`` for every other DSN (Postgres, in-memory SQLite), which
    have no such "auto-creates a file on connect" footgun to guard against.
    """
    if not database_url.startswith("sqlite:///") or _is_sqlite_memory_url(database_url):
        return None
    return Path(database_url.removeprefix("sqlite:///"))


def build_engine(database_url: str, *, create_if_missing: bool = True) -> Engine:
    """Build a SQLAlchemy engine for the given DSN.

    In-memory SQLite needs a single pinned connection (``StaticPool``) or
    every checkout would silently see a fresh, empty database -- a classic
    footgun for tests using ``sqlite:///:memory:``.

    ``create_if_missing=False`` (used by the read-only repository path) skips
    creating the parent directory for a local SQLite file -- engine
    construction itself never touches the filesystem in that mode; the
    caller is still responsible for not *connecting* to a file that does not
    exist yet (see ``GraphPersistenceRepository``'s own guard).
    """
    if _is_sqlite_memory_url(database_url):
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    if database_url.startswith("sqlite:///"):
        if create_if_missing:
            path = Path(database_url.removeprefix("sqlite:///"))
            path.parent.mkdir(parents=True, exist_ok=True)
        return create_engine(database_url, connect_args={"check_same_thread": False})
    return create_engine(database_url)


def build_engine_from_env(output_root: str | None = None, *, create_if_missing: bool = True) -> Engine:
    return build_engine(resolve_database_url(output_root), create_if_missing=create_if_missing)
