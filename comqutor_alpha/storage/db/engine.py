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
    ``COMQUTOR_REQUIRE_DATABASE_DIALECT`` (e.g. ``postgresql``) makes the
    same refusal explicit for any environment, and also refuses a URL of a
    different backend.
    """
    env_url = os.environ.get("COMQUTOR_DATABASE_URL", "").strip()
    required_dialect = os.environ.get("COMQUTOR_REQUIRE_DATABASE_DIALECT", "").strip().lower()
    if required_dialect:
        # 2026-10-08 (T4): a launcher that must run on one database backend
        # (the T4 PostgreSQL verification and Fresh Run instance) sets this;
        # a missing URL or a URL of another backend is then an explicit
        # error, never the local SQLite fallback below. Unset: unchanged.
        if not env_url:
            raise DatabaseConfigurationError("REQUIRED_DATABASE_URL_MISSING")
        if describe_database(env_url)["dialect"] != required_dialect:
            raise DatabaseConfigurationError("DATABASE_DIALECT_MISMATCH")
        return env_url
    if env_url:
        return env_url
    if _is_production():
        raise DatabaseConfigurationError("PRODUCTION_DATABASE_URL_REQUIRED")
    root = resolve_output_root(output_root)
    return f"sqlite:///{root / DEFAULT_SQLITE_FILENAME}"


def describe_database(database_url: str) -> dict[str, str | None]:
    """Backend name (``postgresql``, ``sqlite``, ...) and database name of a
    DSN, parsed with SQLAlchemy's URL parser -- never the user, password,
    host or the DSN itself. Unparseable: both ``None``."""
    from sqlalchemy.engine import make_url

    try:
        url = make_url(database_url)
    except Exception:
        return {"dialect": None, "database": None}
    database = url.database
    if url.get_backend_name() == "sqlite" and database:
        database = Path(database).name
    return {"dialect": url.get_backend_name(), "database": database}


def enforce_required_database_name(database_url: str) -> None:
    """Refuse to proceed if ``COMQUTOR_REQUIRE_DATABASE_NAME`` is set and
    ``database_url`` does not resolve to that exact database name.

    2026-10-02 incident fix: an isolated-database launcher
    (``run_nvda_fresh_run_isolated_db.sh``) exported an overridden
    ``COMQUTOR_DATABASE_URL`` in its own process and verified it resolved to
    a ``_test``-suffixed database -- but the *next* script in its own exec
    chain (``scripts/start_live_comqutor.sh``) re-sourced ``.env`` afterward
    (to pick up credentials/other config), which silently overwrote that
    override back to ``.env``'s own production ``COMQUTOR_DATABASE_URL``
    before the API process ever started. The launcher's check had already
    passed, in a different process, before the variable it was protecting
    was clobbered -- so a real research run wrote 1040+ rows into the
    production database instead of the isolated test one. A startup-script
    env-var check is therefore not sufficient on its own: it can verify the
    environment at one point in one process and still be silently bypassed
    one handoff later.

    This function is the fix: it is called at the actual write-connection
    construction point (``build_write_repository_from_env``), inside the
    final process, immediately before anything connects -- so it sees
    whatever ``COMQUTOR_DATABASE_URL`` the process *actually* ends up with,
    not what an earlier script merely intended. ``COMQUTOR_REQUIRE_DATABASE_
    NAME`` is a second, independent environment variable that a launcher
    sets alongside its ``COMQUTOR_DATABASE_URL`` override; since ``.env``
    never defines this variable, re-sourcing ``.env`` cannot clobber it the
    way it clobbers ``COMQUTOR_DATABASE_URL`` itself -- it survives the
    exact handoff that caused the incident.

    Unset (the default, every existing caller/deployment): a complete no-op,
    zero behavior change. Set: parses the database name out of
    ``database_url`` (via SQLAlchemy's own URL parser, not manual string
    splitting) and raises ``DatabaseConfigurationError(
    "DATABASE_TARGET_MISMATCH")`` -- never the raw DSN or a credential -- if
    it does not match exactly. Raised before :func:`build_engine` is ever
    called, so no connection, query, or schema-creation attempt is made
    against the wrong target.
    """
    required = os.environ.get("COMQUTOR_REQUIRE_DATABASE_NAME", "").strip()
    if not required:
        return
    from sqlalchemy.engine import make_url

    try:
        actual = make_url(database_url).database
    except Exception as exc:
        raise DatabaseConfigurationError("DATABASE_TARGET_MISMATCH") from exc
    if actual != required:
        raise DatabaseConfigurationError("DATABASE_TARGET_MISMATCH")


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
