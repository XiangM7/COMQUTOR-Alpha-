"""W7: PostgreSQL integration profile for migration 0005 and the
research_run_progress repository primitives.

Follows the same PostgreSQL Verification Gate contract as
tests/test_w5_1b_postgres_integration.py: an unset
``COMQUTOR_TEST_DATABASE_URL`` is the only normal skip; any other
misconfiguration is a hard ``pytest.fail``. Cleans up only the rows this
module's own unique run_id prefix created.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError

from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations, applied_migration_versions
from comqutor_alpha.storage.db.repository import (
    GraphPersistenceError,
    GraphPersistenceRepository,
)
from comqutor_alpha.storage.db.schema import research_run_progress, research_runs

pytestmark = pytest.mark.integration

PROFILE = "comqutor_anthropic_medium_sonnet46_v1"
ANALYSTS = ["fundamentals", "market", "news", "sentiment"]


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
        "prefix": f"w7_pg_{uuid.uuid4().hex}",
        "run_ids": set(),
    }
    yield context

    run_ids = context["run_ids"]
    if run_ids:
        with engine.begin() as conn:
            conn.execute(
                sa.delete(research_run_progress).where(research_run_progress.c.run_id.in_(run_ids))
            )
            conn.execute(sa.delete(research_runs).where(research_runs.c.run_id.in_(run_ids)))
    engine.dispose()


def _run_id(context, suffix):
    run_id = f"{context['prefix']}_{suffix}"
    context["run_ids"].add(run_id)
    return run_id


def _claim(context, suffix, *, execution_mode="real", analysts=None):
    repo = context["repo"]
    run_id = _run_id(context, suffix)
    repo.claim_research_run(
        run_id=run_id,
        request_fingerprint=f"fp_{run_id}",
        ticker="NVDA",
        analysis_date="2026-07-16",
        selected_analysts=analysts if analysts is not None else ANALYSTS,
        execution_mode=execution_mode,
        provider_identity="anthropic",
        model_identity="claude-sonnet-4-6:claude-sonnet-4-6",
        pipeline_identity={},
    )
    return run_id


def test_migration_0005_applied(postgres_context):
    assert "0005_create_research_run_progress" in applied_migration_versions(
        postgres_context["engine"]
    )
    # Re-applying is a safe no-op.
    assert apply_migrations(postgres_context["engine"]) == []


def test_progress_round_trip_and_monotonicity(postgres_context):
    repo = postgres_context["repo"]
    run_id = _run_id(postgres_context, "roundtrip")
    assert repo.initialize_research_progress(run_id, profile_id=PROFILE, total_units=15) is True
    assert repo.initialize_research_progress(run_id, profile_id=PROFILE, total_units=15) is False

    assert repo.update_research_progress(
        run_id, progress_percent=43, current_stage="news_analysis", completed_units=4,
        progress_message="Running the News Analyst.",
    )
    # Regression attempt: rejected as a no-op.
    assert (
        repo.update_research_progress(
            run_id, progress_percent=20, current_stage="market_analysis", completed_units=1
        )
        is False
    )
    row = repo.get_research_progress(run_id)
    assert row["progress_percent"] == 43
    assert row["current_stage"] == "news_analysis"
    assert row["completed_units"] == 4
    assert row["total_units"] == 15
    assert row["profile_id"] == PROFILE


def test_progress_check_constraints_enforced_by_postgres(postgres_context):
    engine = postgres_context["engine"]
    run_id = _run_id(postgres_context, "constraint")
    with pytest.raises(SQLAlchemyError):
        with engine.begin() as conn:
            conn.execute(
                sa.insert(research_run_progress).values(
                    run_id=run_id,
                    profile_id=PROFILE,
                    progress_percent=150,
                    current_stage="queued",
                    completed_units=0,
                    total_units=15,
                    updated_at=datetime.now(UTC),
                )
            )


def test_invalid_numeric_rejected_before_sql(postgres_context):
    repo = postgres_context["repo"]
    run_id = _run_id(postgres_context, "invalid")
    repo.initialize_research_progress(run_id, profile_id=PROFILE, total_units=15)
    for bad_percent in (True, 50.5, "50", -1, 101):
        with pytest.raises(GraphPersistenceError):
            repo.update_research_progress(
                run_id, progress_percent=bad_percent, current_stage="queued", completed_units=0
            )


def test_terminal_behaviors(postgres_context):
    repo = postgres_context["repo"]
    done = _run_id(postgres_context, "done")
    failed = _run_id(postgres_context, "failed")
    repo.initialize_research_progress(done, profile_id=PROFILE, total_units=15)
    repo.initialize_research_progress(failed, profile_id=PROFILE, total_units=15)
    repo.update_research_progress(
        failed, progress_percent=64, current_stage="trading_plan", completed_units=6
    )

    assert repo.mark_research_progress_completed(done)
    row = repo.get_research_progress(done)
    assert (row["progress_percent"], row["current_stage"]) == (100, "completed")
    assert row["completed_units"] == row["total_units"]

    assert repo.mark_research_progress_failed(failed, progress_message="Safe message.")
    row = repo.get_research_progress(failed)
    assert (row["progress_percent"], row["current_stage"]) == (64, "failed")


def test_eta_duration_history_matching(postgres_context):
    repo = postgres_context["repo"]
    engine = postgres_context["engine"]

    for index, duration in enumerate((100, 150, 200)):
        run_id = _claim(postgres_context, f"hist{index}")
        repo.mark_research_run_running(run_id)
        repo.mark_research_run_terminal(run_id, status="completed")
        end = datetime.now(UTC)
        with engine.begin() as conn:
            conn.execute(
                sa.update(research_runs)
                .where(research_runs.c.run_id == run_id)
                .values(started_at=end - timedelta(seconds=duration), completed_at=end)
            )
        repo.initialize_research_progress(run_id, profile_id=PROFILE, total_units=15)
        repo.mark_research_progress_completed(run_id)

    # A different profile and a different analyst selection never mix in.
    other_profile = _claim(postgres_context, "otherprofile")
    repo.mark_research_run_running(other_profile)
    repo.mark_research_run_terminal(other_profile, status="completed")
    end = datetime.now(UTC)
    with engine.begin() as conn:
        conn.execute(
            sa.update(research_runs)
            .where(research_runs.c.run_id == other_profile)
            .values(started_at=end - timedelta(seconds=999), completed_at=end)
        )
    repo.initialize_research_progress(other_profile, profile_id="other_profile_v9", total_units=15)
    repo.mark_research_progress_completed(other_profile)

    durations = repo.list_real_completed_run_durations(
        profile_id=PROFILE, selected_analysts=ANALYSTS
    )
    matching = [d for d in durations if 99 <= d <= 201]
    assert len(matching) >= 3
    assert all(d < 990 for d in durations)
