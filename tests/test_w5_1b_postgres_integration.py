"""PostgreSQL integration profile for W5.1A race recovery and W5.1B
background-runtime repository primitives.

Follows the same PostgreSQL Verification Gate contract as
tests/test_research_runs_postgres_integration.py: an unset
``COMQUTOR_TEST_DATABASE_URL`` is the only normal skip; any other
misconfiguration is a hard ``pytest.fail``. Cleans up only the rows this
module's own unique run_id prefix created.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from comqutor_alpha.research_jobs import reconcile_orphaned_runs_on_startup
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from comqutor_alpha.storage.db.schema import MIGRATIONS, research_runs

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def postgres_context():
    import os

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
        "prefix": f"w51b_pg_{uuid.uuid4().hex}",
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


# ---------------------------------------------------------------------------
# W5.1A race recovery against real PostgreSQL
# ---------------------------------------------------------------------------


def test_race_recovery_winner_completes_before_loser_retry_on_postgres(postgres_context):
    repo = postgres_context["repo"]
    fingerprint = f"fp_{postgres_context['prefix']}_race"
    winner_holder = {}

    original_insert = repo._insert_new_run  # noqa: SLF001
    state = {"raised": False}

    def racy_insert(conn, values):
        if not state["raised"]:
            state["raised"] = True
            raise IntegrityError("INSERT ...", {}, Exception("duplicate key value violates unique constraint"))
        return original_insert(conn, values)

    repo._insert_new_run = racy_insert  # noqa: SLF001

    def on_race(attempt, request_fingerprint):
        winner = repo.claim_research_run(**_claim_kwargs(postgres_context, "race-winner", fingerprint=request_fingerprint))
        repo.mark_research_run_running(winner["run_id"])
        repo.mark_research_run_terminal(winner["run_id"], status="completed")
        winner_holder["run_id"] = winner["run_id"]

    repo._on_claim_race = on_race  # noqa: SLF001

    try:
        loser = repo.claim_research_run(**_claim_kwargs(postgres_context, "race-loser", fingerprint=fingerprint))
    finally:
        del repo._insert_new_run  # noqa: SLF001
        del repo._on_claim_race  # noqa: SLF001

    assert loser["disposition"] == "reused_completed"
    assert loser["run_id"] == winner_holder["run_id"]


def test_no_duplicate_active_fingerprint_under_concurrency_on_postgres(postgres_context):
    import threading

    repo = postgres_context["repo"]
    fingerprint = f"fp_{postgres_context['prefix']}_concurrent"
    barrier = threading.Barrier(4)
    results = []
    lock = threading.Lock()

    def worker(i):
        barrier.wait()
        result = repo.claim_research_run(**_claim_kwargs(postgres_context, f"concurrent-{i}", fingerprint=fingerprint))
        with lock:
            results.append(result)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
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

    with postgres_context["engine"].connect() as conn:
        active_rows = conn.execute(
            sa.select(sa.func.count())
            .select_from(research_runs)
            .where(research_runs.c.active_fingerprint == fingerprint)
        ).scalar()
    assert active_rows == 1

    winner_run_id = next(r["run_id"] for r in results if r["disposition"] == "created")
    repo.mark_research_run_terminal(winner_run_id, status="failed", error_code="TEST_CLEANUP", error_message="test cleanup")


# ---------------------------------------------------------------------------
# mark_research_run_failed_if_active: conditional UPDATE, terminal rows
# never overwritten
# ---------------------------------------------------------------------------


def test_mark_failed_if_active_conditional_update_on_postgres(postgres_context):
    repo = postgres_context["repo"]
    claim = repo.claim_research_run(**_claim_kwargs(postgres_context, "mark-failed-active"))
    updated = repo.mark_research_run_failed_if_active(
        claim["run_id"], error_code="RESEARCH_TIMEOUT", error_message="timed out"
    )
    assert updated is True
    record = repo.get_research_run_record(claim["run_id"])
    assert record["status"] == "failed"
    assert record["error_code"] == "RESEARCH_TIMEOUT"
    assert record["active_fingerprint"] is None


def test_mark_failed_if_active_is_a_noop_on_already_terminal_row_on_postgres(postgres_context):
    repo = postgres_context["repo"]
    claim = repo.claim_research_run(**_claim_kwargs(postgres_context, "mark-failed-terminal"))
    repo.mark_research_run_running(claim["run_id"])
    repo.mark_research_run_terminal(claim["run_id"], status="completed")
    before = repo.get_research_run_record(claim["run_id"])

    updated = repo.mark_research_run_failed_if_active(
        claim["run_id"], error_code="RESEARCH_TIMEOUT", error_message="should not apply"
    )
    assert updated is False
    after = repo.get_research_run_record(claim["run_id"])
    assert before == after  # terminal row never overwritten


@pytest.mark.parametrize("terminal_status", ["completed", "partial", "failed"])
def test_terminal_rows_not_overwritten_by_failed_if_active_on_postgres(postgres_context, terminal_status):
    repo = postgres_context["repo"]
    claim = repo.claim_research_run(**_claim_kwargs(postgres_context, f"terminal-{terminal_status}"))
    repo.mark_research_run_running(claim["run_id"])
    repo.mark_research_run_terminal(claim["run_id"], status=terminal_status)
    before = repo.get_research_run_record(claim["run_id"])

    repo.mark_research_run_failed_if_active(claim["run_id"], error_code="SERVER_SHUTDOWN", error_message="x")
    after = repo.get_research_run_record(claim["run_id"])
    assert before == after


# ---------------------------------------------------------------------------
# Restart reconciliation against real PostgreSQL
# ---------------------------------------------------------------------------


def test_restart_reconciliation_on_postgres(postgres_context):
    repo = postgres_context["repo"]
    queued_claim = repo.claim_research_run(**_claim_kwargs(postgres_context, "orphan-queued"))
    running_claim = repo.claim_research_run(**_claim_kwargs(postgres_context, "orphan-running"))
    repo.mark_research_run_running(running_claim["run_id"])

    completed_claim = repo.claim_research_run(**_claim_kwargs(postgres_context, "not-orphan-completed"))
    repo.mark_research_run_running(completed_claim["run_id"])
    repo.mark_research_run_terminal(completed_claim["run_id"], status="completed")
    before_completed = repo.get_research_run_record(completed_claim["run_id"])

    reconciled = reconcile_orphaned_runs_on_startup(repo)

    assert queued_claim["run_id"] in reconciled
    assert running_claim["run_id"] in reconciled
    assert completed_claim["run_id"] not in reconciled

    for run_id in (queued_claim["run_id"], running_claim["run_id"]):
        record = repo.get_research_run_record(run_id)
        assert record["status"] == "failed"
        assert record["error_code"] == "SERVER_RESTARTED"
        assert record["active_fingerprint"] is None

    after_completed = repo.get_research_run_record(completed_claim["run_id"])
    assert before_completed == after_completed


# ---------------------------------------------------------------------------
# No migration 0004
# ---------------------------------------------------------------------------


def test_no_migration_0004_exists(postgres_context):
    assert [version for version, _tables in MIGRATIONS] == [
        "0001_create_week3_alpha_matches_and_structure_graphs",
        "0002_create_week4_alpha_activations_and_alpha_conflicts",
        "0003_create_research_runs",
    ]


def test_no_migration_0004_applied_on_postgres(postgres_context):
    from comqutor_alpha.storage.db.schema import schema_migrations

    with postgres_context["engine"].connect() as conn:
        versions = set(conn.execute(sa.select(schema_migrations.c.version)).scalars().all())
    assert not any(v.startswith("0004") for v in versions)


def test_no_agent_outputs_table_on_postgres(postgres_context):
    inspector = sa.inspect(postgres_context["engine"])
    assert "agent_outputs" not in inspector.get_table_names()
