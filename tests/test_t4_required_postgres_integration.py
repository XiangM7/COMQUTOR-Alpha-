"""T4 Phase A (2026-10-08): the forced-PostgreSQL write path against a real, isolated PostgreSQL test database.

Same PostgreSQL Verification Gate contract as tests/test_research_runs_postgres_integration.py: an unset
``COMQUTOR_TEST_DATABASE_URL`` is the only normal skip (the T4 test runner treats any skip as a failure); a
non-PostgreSQL scheme or an unreachable database is a hard ``pytest.fail``. Writes nothing but the schema migrations
``build_write_repository_from_env`` itself applies (idempotent).
"""

from __future__ import annotations

import os

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url

from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.repository import GraphPersistenceError

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def test_database_url():
    url = os.environ.get("COMQUTOR_TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("COMQUTOR_TEST_DATABASE_URL not configured")
    if not url.startswith(("postgresql://", "postgresql+psycopg://")):
        pytest.fail("COMQUTOR_TEST_DATABASE_URL is not a PostgreSQL DSN")
    engine = build_engine(url)
    try:
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
    except sa.exc.SQLAlchemyError:
        pytest.fail("PostgreSQL verification was configured but the database is unreachable")
    finally:
        engine.dispose()
    return url


def test_required_postgresql_write_repository_connects_migrates_and_reports_backend(test_database_url, monkeypatch, tmp_path):
    from comqutor_alpha.run_environment import database_backend
    from comqutor_alpha.storage.db.repository import build_write_repository_from_env

    name = make_url(test_database_url).database
    monkeypatch.setenv("COMQUTOR_DATABASE_URL", test_database_url)
    monkeypatch.setenv("COMQUTOR_REQUIRE_DATABASE_DIALECT", "postgresql")
    monkeypatch.setenv("COMQUTOR_REQUIRE_DATABASE_NAME", name)
    repository = build_write_repository_from_env(str(tmp_path))
    try:
        assert repository.dialect_name == "postgresql"
        with repository._engine.connect() as conn:
            assert conn.execute(sa.text("select current_database()")).scalar() == name
            assert conn.execute(sa.text("select count(*) from schema_migrations")).scalar() > 0
    finally:
        repository._engine.dispose()
    assert database_backend(str(tmp_path)) == {"status": "known", "dialect": "postgresql", "database": name}
    assert not any(tmp_path.iterdir()), "the PostgreSQL path must not create a local SQLite file"


def test_required_postgresql_refuses_a_different_database_name_before_connecting(test_database_url, monkeypatch, tmp_path):
    from comqutor_alpha.storage.db.repository import build_write_repository_from_env

    monkeypatch.setenv("COMQUTOR_DATABASE_URL", test_database_url)
    monkeypatch.setenv("COMQUTOR_REQUIRE_DATABASE_DIALECT", "postgresql")
    monkeypatch.setenv("COMQUTOR_REQUIRE_DATABASE_NAME", "comqutor_alpha_some_other_test")
    # the write path wraps the engine's DatabaseConfigurationError in a reason-code-only GraphPersistenceError
    with pytest.raises(GraphPersistenceError) as exc:
        build_write_repository_from_env(str(tmp_path))
    assert exc.value.reason_code == "DATABASE_TARGET_MISMATCH"


def test_required_postgresql_refuses_a_missing_url_instead_of_a_sqlite_file(test_database_url, monkeypatch, tmp_path):
    from comqutor_alpha.storage.db.repository import build_write_repository_from_env

    monkeypatch.delenv("COMQUTOR_DATABASE_URL", raising=False)
    monkeypatch.setenv("COMQUTOR_REQUIRE_DATABASE_DIALECT", "postgresql")
    with pytest.raises(GraphPersistenceError) as exc:
        build_write_repository_from_env(str(tmp_path))
    assert exc.value.reason_code == "REQUIRED_DATABASE_URL_MISSING"
    assert not any(tmp_path.iterdir())
