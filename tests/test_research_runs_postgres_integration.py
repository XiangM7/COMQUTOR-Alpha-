"""PostgreSQL integration profile for W5.1A research_runs persistence.

Follows the same PostgreSQL Verification Gate contract as
tests/test_week4_postgres_persistence.py: an unset
``COMQUTOR_TEST_DATABASE_URL`` is the only normal skip; any other
misconfiguration (non-PostgreSQL scheme, missing driver, unreachable
database) is a hard ``pytest.fail``. Cleans up only the rows this module's
own unique run_id prefix created -- never a full-table delete/truncate.
"""

from __future__ import annotations

import os
import threading
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError

from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceError, GraphPersistenceRepository
from comqutor_alpha.storage.db.schema import research_runs, schema_migrations

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def postgres_context():
    url = os.environ.get("COMQUTOR_TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("COMQUTOR_TEST_DATABASE_URL not configured")
    if not url.startswith(("postgresql://", "postgresql+psycopg://")):
        pytest.fail("COMQUTOR_TEST_DATABASE_URL is not a PostgreSQL DSN")

    try:
        engine = build_engine(url)
    except ImportError:
        pytest.fail("PostgreSQL verification was configured but the driver is unavailable")
    try:
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
    except SQLAlchemyError:
        engine.dispose()
        pytest.fail("PostgreSQL verification was configured but the database is unreachable")
    apply_migrations(engine)

    context = {
        "engine": engine,
        "repo": GraphPersistenceRepository(engine),
        "prefix": f"w51a_pg_{uuid.uuid4().hex}",
        "run_ids": set(),
    }
    yield context

    run_ids = context["run_ids"]
    if run_ids:
        with engine.begin() as conn:
            conn.execute(sa.delete(research_runs).where(research_runs.c.run_id.in_(run_ids)))
    engine.dispose()


def _run_id(context, suffix):
    run_id = f"{context['prefix']}_{suffix}"
    context["run_ids"].add(run_id)
    return run_id


def _claim_kwargs(context, suffix, *, fingerprint=None, **overrides):
    kwargs = {
        "run_id": _run_id(context, suffix),
        "request_fingerprint": fingerprint or f"fp_{context['prefix']}_{suffix}",
        "ticker": "NVDA",
        "analysis_date": "2026-06-30",
        "selected_analysts": ["fundamentals", "market", "news", "sentiment"],
        "execution_mode": "offline",
        "provider_identity": "server_unconfigured",
        "model_identity": "server_unconfigured",
        "pipeline_identity": {"graph_schema_version": "week3.structure_graph.v1"},
        "force_refresh": False,
    }
    kwargs.update(overrides)
    return kwargs


def test_migration_0003_and_research_runs_table_exist(postgres_context):
    engine = postgres_context["engine"]
    inspector = sa.inspect(engine)
    assert "research_runs" in inspector.get_table_names()
    with engine.connect() as conn:
        count = conn.scalar(
            sa.select(sa.func.count())
            .select_from(schema_migrations)
            .where(schema_migrations.c.version == "0003_create_research_runs")
        )
    assert count == 1


def test_migration_reapply_is_idempotent(postgres_context):
    engine = postgres_context["engine"]
    applied = apply_migrations(engine)
    assert applied == []
    with engine.connect() as conn:
        count = conn.scalar(
            sa.select(sa.func.count())
            .select_from(schema_migrations)
            .where(schema_migrations.c.version == "0003_create_research_runs")
        )
    assert count == 1


def test_row_round_trip_with_real_jsonb(postgres_context):
    repo = postgres_context["repo"]
    claim = repo.claim_research_run(
        **_claim_kwargs(
            postgres_context,
            "roundtrip",
            selected_analysts=["news", "market"],
            pipeline_identity={"a": 1, "nested": {"b": True}},
        )
    )
    record = repo.get_research_run_record(claim["run_id"])
    assert record["selected_analysts"] == ["news", "market"]
    assert record["pipeline_identity"] == {"a": 1, "nested": {"b": True}}

    engine = postgres_context["engine"]
    with engine.connect() as conn:
        data_type = conn.execute(
            sa.text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'research_runs' AND column_name = 'pipeline_identity'"
            )
        ).scalar()
    assert data_type == "jsonb"


def test_active_fingerprint_unique_constraint_is_real_pg_constraint(postgres_context):
    repo = postgres_context["repo"]
    fingerprint = f"fp_{postgres_context['prefix']}_unique_pg"
    repo.claim_research_run(**_claim_kwargs(postgres_context, "unique1", fingerprint=fingerprint))

    engine = postgres_context["engine"]
    indexes = sa.inspect(engine).get_indexes("research_runs")
    unique_on_active_fingerprint = any(
        "active_fingerprint" in idx["column_names"] and idx.get("unique")
        for idx in indexes
    ) or any(
        "active_fingerprint" in (uc.get("column_names") or [])
        for uc in sa.inspect(engine).get_unique_constraints("research_runs")
    )
    assert unique_on_active_fingerprint


def test_lifecycle_transitions_against_real_postgres(postgres_context):
    repo = postgres_context["repo"]
    claim = repo.claim_research_run(**_claim_kwargs(postgres_context, "lifecycle"))
    running = repo.mark_research_run_running(claim["run_id"])
    assert running["status"] == "running"
    assert running["started_at"] is not None

    completed = repo.mark_research_run_terminal(claim["run_id"], status="completed")
    assert completed["status"] == "completed"
    assert completed["active_fingerprint"] is None

    with pytest.raises(GraphPersistenceError) as exc_info:
        repo.mark_research_run_running(claim["run_id"])
    assert exc_info.value.reason_code == "RESEARCH_RUN_TRANSITION_INVALID"


def test_completed_reuse_against_real_postgres(postgres_context):
    repo = postgres_context["repo"]
    fingerprint = f"fp_{postgres_context['prefix']}_reuse"
    claim = repo.claim_research_run(**_claim_kwargs(postgres_context, "reuse1", fingerprint=fingerprint))
    repo.mark_research_run_running(claim["run_id"])
    repo.mark_research_run_terminal(claim["run_id"], status="completed")

    reuse = repo.claim_research_run(**_claim_kwargs(postgres_context, "reuse2", fingerprint=fingerprint))
    assert reuse["disposition"] == "reused_completed"
    assert reuse["run_id"] == claim["run_id"]


def test_terminal_frees_fingerprint_for_new_run_on_postgres(postgres_context):
    repo = postgres_context["repo"]
    fingerprint = f"fp_{postgres_context['prefix']}_retry"
    claim = repo.claim_research_run(**_claim_kwargs(postgres_context, "retry1", fingerprint=fingerprint))
    repo.mark_research_run_running(claim["run_id"])
    repo.mark_research_run_terminal(claim["run_id"], status="failed", error_code="X", error_message="boom")

    retry = repo.claim_research_run(**_claim_kwargs(postgres_context, "retry2", fingerprint=fingerprint))
    assert retry["disposition"] == "created"
    assert retry["run_id"] != claim["run_id"]


def test_concurrent_claims_against_real_postgres_produce_one_created(postgres_context):
    """Multiple threads, each with its own connection via the shared engine's
    pool, race to claim the identical fingerprint against real PostgreSQL.
    Exactly one must win; the rest must observe reused_in_flight -- never an
    internal error."""
    repo = postgres_context["repo"]
    fingerprint = f"fp_{postgres_context['prefix']}_concurrent"
    # Pre-register the run_id this claim *might* create for cleanup -- the
    # repository itself generates the run_id when none is given, so instead
    # track whichever run_id(s) actually appear afterward via the fingerprint.
    barrier = threading.Barrier(4)
    results = []
    lock = threading.Lock()

    def worker():
        barrier.wait()
        result = repo.claim_research_run(
            run_id=None,
            request_fingerprint=fingerprint,
            ticker="NVDA",
            analysis_date="2026-06-30",
            selected_analysts=["market"],
            execution_mode="offline",
            provider_identity="server_unconfigured",
            model_identity="server_unconfigured",
            pipeline_identity={},
            force_refresh=False,
        )
        with lock:
            results.append(result)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    for result in results:
        postgres_context["run_ids"].add(result["run_id"])

    dispositions = [r["disposition"] for r in results]
    assert dispositions.count("created") == 1
    assert dispositions.count("reused_in_flight") == 3
    assert len({r["run_id"] for r in results}) == 1

    # Clean up: bring the winning row to a terminal state so it does not
    # linger as an active_fingerprint-holding row across module fixture
    # teardown (teardown only deletes by run_id, which is sufficient, but
    # transitioning first keeps this test self-contained and honest about
    # lifecycle semantics).
    winner_run_id = next(r["run_id"] for r in results if r["disposition"] == "created")
    repo.mark_research_run_terminal(winner_run_id, status="failed", error_code="TEST_CLEANUP", error_message="test cleanup")
