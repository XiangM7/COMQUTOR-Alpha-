"""PostgreSQL integration profile for W4.2 persistence."""

from __future__ import annotations

import os
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceError, GraphPersistenceRepository
from comqutor_alpha.storage.db.schema import (
    alpha_activations,
    alpha_conflicts,
    schema_migrations,
)
from tests.test_week4_persistence import _week4_payloads

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def postgres_context():
    url = os.environ.get("COMQUTOR_TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("COMQUTOR_TEST_DATABASE_URL not configured")
    if not url.startswith(("postgresql://", "postgresql+psycopg://")):
        pytest.skip("COMQUTOR_TEST_DATABASE_URL must use PostgreSQL")

    try:
        engine = build_engine(url)
    except ImportError:
        pytest.skip("PostgreSQL driver is unavailable")
    try:
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
    except SQLAlchemyError:
        engine.dispose()
        pytest.skip("configured PostgreSQL database is unreachable")
    apply_migrations(engine)

    context = {
        "engine": engine,
        "repo": GraphPersistenceRepository(engine),
        "prefix": f"w42_pg_{uuid.uuid4().hex}",
        "run_ids": set(),
    }
    yield context

    run_ids = context["run_ids"]
    if run_ids:
        with engine.begin() as conn:
            conn.execute(sa.delete(alpha_conflicts).where(alpha_conflicts.c.run_id.in_(run_ids)))
            conn.execute(
                sa.delete(alpha_activations).where(alpha_activations.c.run_id.in_(run_ids))
            )
    engine.dispose()


def _run_id(context, suffix):
    run_id = f"{context['prefix']}_{suffix}"
    context["run_ids"].add(run_id)
    return run_id


def _persist(context, suffix, *, ticker="NVDA", score=90.0):
    run_id = _run_id(context, suffix)
    activation, conflict = _week4_payloads(run_id, ticker, score=score)
    context["repo"].persist_week4_results(
        run_id=run_id,
        ticker=ticker,
        activation_payload=activation,
        conflict_payload=conflict,
    )
    return run_id, activation, conflict


def test_migration_0002_and_tables_exist(postgres_context):
    engine = postgres_context["engine"]
    inspector = sa.inspect(engine)
    assert {"alpha_activations", "alpha_conflicts"}.issubset(inspector.get_table_names())
    with engine.connect() as conn:
        count = conn.scalar(
            sa.select(sa.func.count())
            .select_from(schema_migrations)
            .where(
                schema_migrations.c.version
                == "0002_create_week4_alpha_activations_and_alpha_conflicts"
            )
        )
    assert count == 1


def test_week4_json_columns_are_real_jsonb(postgres_context):
    inspector = sa.inspect(postgres_context["engine"])
    activation_types = {column["name"]: column["type"] for column in inspector.get_columns("alpha_activations")}
    conflict_types = {column["name"]: column["type"] for column in inspector.get_columns("alpha_conflicts")}
    assert isinstance(activation_types["activation_json"], JSONB)
    for name in ("reason_codes", "evidence_audit", "candidate_json", "conflict_json"):
        assert isinstance(conflict_types[name], JSONB)


def test_activation_unique_constraint_is_enforced(postgres_context):
    engine = postgres_context["engine"]
    run_id = _run_id(postgres_context, "unique_activation")
    values = {
        "run_id": run_id,
        "ticker": "NVDA",
        "alpha_id": "A101",
        "alpha_name": "AI Expansion",
        "activation_score": 50.0,
        "status": "watch",
        "direction": "positive",
        "formula_version": "week3.activation.mvp_v1",
        "activation_rank": 0,
        "activation_json": {},
    }
    with engine.begin() as conn:
        conn.execute(sa.insert(alpha_activations).values(**values))
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(sa.insert(alpha_activations).values(**values))


def test_conflict_unique_constraint_is_enforced(postgres_context):
    engine = postgres_context["engine"]
    run_id = _run_id(postgres_context, "unique_conflict")
    values = {
        "run_id": run_id,
        "ticker": "NVDA",
        "alpha_a": "A101",
        "alpha_b": "A304",
        "outcome": "rejected",
        "reason_codes": ["TEST"],
        "evidence_audit": {},
        "candidate_json": {},
        "schema_version": "week4.alpha_conflicts.v1",
        "formula_version": "week4.conflict_score.mvp_v1",
    }
    with engine.begin() as conn:
        conn.execute(sa.insert(alpha_conflicts).values(**values))
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(sa.insert(alpha_conflicts).values(**values))


def test_round_trip_all_outcomes_and_main_reconstruction(postgres_context):
    run_id, activation, conflict = _persist(postgres_context, "round_trip")
    repo = postgres_context["repo"]
    assert len(repo.get_alpha_activations(run_id)) == len(activation["alphas"])
    assert {row["outcome"] for row in repo.get_alpha_conflicts(run_id)} == {
        "admitted",
        "suppressed",
        "rejected",
    }
    assert repo.get_week4_conflict_result(run_id) == conflict
    assert repo.get_week4_conflict_result(run_id)["main_conflict"] == conflict["conflicts"][0]


def test_retry_replace_semantics(postgres_context):
    run_id, _, _ = _persist(postgres_context, "retry", score=90)
    repo = postgres_context["repo"]
    activation, conflict = _week4_payloads(run_id, "NVDA", score=70)
    repo.persist_week4_results(
        run_id=run_id,
        ticker="NVDA",
        activation_payload=activation,
        conflict_payload=conflict,
    )
    assert len(repo.get_alpha_activations(run_id)) == 7
    assert len(repo.get_alpha_conflicts(run_id)) == 6
    assert repo.get_alpha_activations(run_id)[2]["activation_score"] == 70


@pytest.mark.parametrize("same_ticker", [False, True])
def test_run_isolation_including_same_ticker(postgres_context, same_ticker):
    suffix = "same_ticker" if same_ticker else "different_ticker"
    run_a, _, _ = _persist(postgres_context, f"{suffix}_a", ticker="NVDA", score=90)
    run_b, _, _ = _persist(
        postgres_context,
        f"{suffix}_b",
        ticker="NVDA" if same_ticker else "QQQ",
        score=60,
    )
    repo = postgres_context["repo"]
    run_b_before = repo.get_week4_conflict_result(run_b)
    activation, conflict = _week4_payloads(run_a, "NVDA", score=70)
    repo.persist_week4_results(
        run_id=run_a,
        ticker="NVDA",
        activation_payload=activation,
        conflict_payload=conflict,
    )
    assert repo.get_week4_conflict_result(run_b) == run_b_before


def test_transaction_rollback_preserves_prior_state(postgres_context):
    run_id, _, _ = _persist(postgres_context, "rollback", score=90)
    engine = postgres_context["engine"]
    repo = postgres_context["repo"]
    activations_before = repo.get_alpha_activations(run_id)
    conflicts_before = repo.get_alpha_conflicts(run_id)
    activation, conflict = _week4_payloads(run_id, "NVDA", score=70)

    def fail_conflict_insert(_conn, _cursor, statement, _parameters, _context, _executemany):
        if "insert into alpha_conflicts" in statement.lower():
            raise sa.exc.OperationalError(statement, {}, RuntimeError("forced"))

    sa.event.listen(engine, "before_cursor_execute", fail_conflict_insert)
    try:
        with pytest.raises(GraphPersistenceError) as exc_info:
            repo.persist_week4_results(
                run_id=run_id,
                ticker="NVDA",
                activation_payload=activation,
                conflict_payload=conflict,
            )
        assert exc_info.value.reason_code == "DB_WRITE_FAILED"
    finally:
        sa.event.remove(engine, "before_cursor_execute", fail_conflict_insert)

    assert repo.get_alpha_activations(run_id) == activations_before
    assert repo.get_alpha_conflicts(run_id) == conflicts_before
