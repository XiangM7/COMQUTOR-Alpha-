"""W7: research_run_progress persistence, monotonicity, reporter math,
ETA history rules, status-API enrichment, and worker/lifecycle failure
mirroring -- all against SQLite (the offline default). PostgreSQL coverage
of the same table lives in tests/test_research_progress_postgres_integration.py.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from comqutor_alpha import research_progress
from comqutor_alpha.api.routes_research import get_research_run_status
from comqutor_alpha.research_progress import (
    ResearchProgressReporter,
    analyst_progress_percent,
    canonical_public_analysts,
    compute_total_units,
)
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import (
    GraphPersistenceError,
    GraphPersistenceRepository,
)
from comqutor_alpha.storage.db.schema import research_runs

PROFILE = "comqutor_anthropic_medium_sonnet46_v1"
ANALYSTS = ["fundamentals", "market", "news", "sentiment"]  # canonical sorted storage order


def _memory_repo() -> GraphPersistenceRepository:
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    return GraphPersistenceRepository(engine)


def _claim(repo, run_id, *, fingerprint=None, execution_mode="real", analysts=None):
    return repo.claim_research_run(
        run_id=run_id,
        request_fingerprint=fingerprint or f"fp_{run_id}",
        ticker="NVDA",
        analysis_date="2026-07-16",
        selected_analysts=analysts if analysts is not None else ANALYSTS,
        execution_mode=execution_mode,
        provider_identity="anthropic",
        model_identity="claude-sonnet-4-6:claude-sonnet-4-6",
        pipeline_identity={},
    )


def _set_run_window(repo, run_id, *, started, completed):
    with repo._engine.begin() as conn:  # noqa: SLF001 -- test-only direct timestamp control
        conn.execute(
            sa.update(research_runs)
            .where(research_runs.c.run_id == run_id)
            .values(started_at=started, completed_at=completed)
        )


def _completed_real_run(repo, run_id, *, duration_seconds, profile_id=PROFILE, analysts=None):
    _claim(repo, run_id, analysts=analysts)
    repo.mark_research_run_running(run_id)
    repo.mark_research_run_terminal(run_id, status="completed")
    end = datetime.now(UTC)
    _set_run_window(repo, run_id, started=end - timedelta(seconds=duration_seconds), completed=end)
    repo.initialize_research_progress(
        run_id, profile_id=profile_id, total_units=compute_total_units(analysts or ANALYSTS)
    )
    repo.mark_research_progress_completed(run_id)


# ---------------------------------------------------------------------------
# Migration 0005 (SQLite) + constraints
# ---------------------------------------------------------------------------


def test_migration_0005_applies_and_is_idempotent():
    engine = build_engine("sqlite:///:memory:")
    applied = apply_migrations(engine)
    assert "0005_create_research_run_progress" in applied
    assert apply_migrations(engine) == []  # re-run is a safe no-op
    with engine.connect() as conn:
        tables = sa.inspect(conn).get_table_names()
    assert "research_run_progress" in tables


def test_initialize_is_idempotent_and_never_resets_progress():
    repo = _memory_repo()
    assert repo.initialize_research_progress("run-a", profile_id=PROFILE, total_units=15) is True
    assert repo.update_research_progress(
        "run-a", progress_percent=50, current_stage="fundamentals_analysis", completed_units=4
    )
    # Second initialize is a no-op -- the advanced state survives.
    assert repo.initialize_research_progress("run-a", profile_id=PROFILE, total_units=15) is False
    row = repo.get_research_progress("run-a")
    assert row["progress_percent"] == 50
    assert row["current_stage"] == "fundamentals_analysis"
    assert row["total_units"] == 15


def test_progress_is_monotonic_never_regresses():
    repo = _memory_repo()
    repo.initialize_research_progress("run-a", profile_id=PROFILE, total_units=15)
    assert repo.update_research_progress(
        "run-a", progress_percent=72, current_stage="raw_outputs_saved", completed_units=5
    )
    # 72 -> 48 must be impossible.
    assert (
        repo.update_research_progress(
            "run-a", progress_percent=48, current_stage="news_analysis", completed_units=3
        )
        is False
    )
    row = repo.get_research_progress("run-a")
    assert row["progress_percent"] == 72
    assert row["current_stage"] == "raw_outputs_saved"


def test_repeated_identical_update_is_idempotent():
    repo = _memory_repo()
    repo.initialize_research_progress("run-a", profile_id=PROFILE, total_units=15)
    for _ in range(3):
        assert repo.update_research_progress(
            "run-a", progress_percent=30, current_stage="sentiment_analysis", completed_units=2
        )
    row = repo.get_research_progress("run-a")
    assert row["progress_percent"] == 30
    assert row["completed_units"] == 2


@pytest.mark.parametrize(
    "kwargs",
    [
        {"progress_percent": 101, "current_stage": "queued", "completed_units": 0},
        {"progress_percent": -1, "current_stage": "queued", "completed_units": 0},
        {"progress_percent": 50.5, "current_stage": "queued", "completed_units": 0},
        {"progress_percent": float("nan"), "current_stage": "queued", "completed_units": 0},
        {"progress_percent": float("inf"), "current_stage": "queued", "completed_units": 0},
        {"progress_percent": "50", "current_stage": "queued", "completed_units": 0},
        {"progress_percent": True, "current_stage": "queued", "completed_units": 0},
        {"progress_percent": 50, "current_stage": "queued", "completed_units": -1},
        {"progress_percent": 50, "current_stage": "queued", "completed_units": "3"},
        {"progress_percent": 50, "current_stage": "", "completed_units": 0},
        {"progress_percent": 50, "current_stage": "x" * 65, "completed_units": 0},
    ],
)
def test_invalid_progress_values_are_rejected(kwargs):
    repo = _memory_repo()
    repo.initialize_research_progress("run-a", profile_id=PROFILE, total_units=15)
    with pytest.raises(GraphPersistenceError) as exc_info:
        repo.update_research_progress("run-a", **kwargs)
    assert exc_info.value.reason_code == "RESEARCH_PROGRESS_INVALID"


def test_completed_units_can_never_exceed_total_units():
    repo = _memory_repo()
    repo.initialize_research_progress("run-a", profile_id=PROFILE, total_units=5)
    assert (
        repo.update_research_progress(
            "run-a", progress_percent=50, current_stage="news_analysis", completed_units=6
        )
        is False
    )
    assert repo.get_research_progress("run-a")["completed_units"] == 0


def test_initialize_rejects_nonpositive_total_units():
    repo = _memory_repo()
    with pytest.raises(GraphPersistenceError):
        repo.initialize_research_progress("run-a", profile_id=PROFILE, total_units=0)
    with pytest.raises(GraphPersistenceError):
        repo.initialize_research_progress("run-a", profile_id=PROFILE, total_units=True)
    with pytest.raises(GraphPersistenceError):
        repo.initialize_research_progress("run-a", profile_id="", total_units=15)


def test_terminal_completed_and_partial_reach_100_with_distinct_stages():
    repo = _memory_repo()
    repo.initialize_research_progress("run-a", profile_id=PROFILE, total_units=15)
    repo.initialize_research_progress("run-b", profile_id=PROFILE, total_units=15)
    assert repo.mark_research_progress_completed("run-a")
    assert repo.mark_research_progress_completed("run-b", partial=True)
    row_a = repo.get_research_progress("run-a")
    row_b = repo.get_research_progress("run-b")
    assert (row_a["progress_percent"], row_a["current_stage"]) == (100, "completed")
    assert row_a["completed_units"] == row_a["total_units"]
    assert (row_b["progress_percent"], row_b["current_stage"]) == (100, "completed_partial")


def test_terminal_failed_preserves_last_real_percent():
    repo = _memory_repo()
    repo.initialize_research_progress("run-a", profile_id=PROFILE, total_units=15)
    repo.update_research_progress(
        "run-a", progress_percent=64, current_stage="trading_plan", completed_units=6
    )
    assert repo.mark_research_progress_failed("run-a", progress_message="Safe message.")
    row = repo.get_research_progress("run-a")
    assert row["current_stage"] == "failed"
    assert row["progress_percent"] == 64  # never faked to 100
    assert row["progress_message"] == "Safe message."


def test_run_isolation():
    repo = _memory_repo()
    repo.initialize_research_progress("run-a", profile_id=PROFILE, total_units=15)
    repo.initialize_research_progress("run-b", profile_id=PROFILE, total_units=13)
    repo.update_research_progress(
        "run-a", progress_percent=50, current_stage="fundamentals_analysis", completed_units=4
    )
    row_b = repo.get_research_progress("run-b")
    assert row_b["progress_percent"] == 8
    assert row_b["total_units"] == 13


# ---------------------------------------------------------------------------
# Stage/percent contract + reporter math
# ---------------------------------------------------------------------------


def test_canonical_analyst_order_and_dedupe():
    assert canonical_public_analysts(["sentiment", "market", "sentiment", "news"]) == [
        "market",
        "sentiment",
        "news",
    ]


def test_total_units_scale_with_selection():
    assert compute_total_units(["market", "sentiment", "news", "fundamentals"]) == 15
    assert compute_total_units(["market", "news"]) == 13


def test_analyst_window_split_four_and_two():
    assert [analyst_progress_percent(k, 4) for k in range(5)] == [10, 20, 30, 40, 50]
    assert [analyst_progress_percent(k, 2) for k in range(3)] == [10, 30, 50]
    assert [analyst_progress_percent(k, 1) for k in range(2)] == [10, 50]


class _RecordingRepo:
    def __init__(self):
        self.updates = []
        self.initialized = []
        self.terminal = []

    def initialize_research_progress(self, run_id, **kwargs):
        self.initialized.append((run_id, kwargs))
        return True

    def update_research_progress(self, run_id, **kwargs):
        self.updates.append(kwargs)
        return True

    def mark_research_progress_completed(self, run_id, partial=False):
        self.terminal.append("completed_partial" if partial else "completed")
        return True

    def mark_research_progress_failed(self, run_id, progress_message=None):
        self.terminal.append(("failed", progress_message))
        return True


def test_reporter_analyst_and_stage_flow():
    repo = _RecordingRepo()
    reporter = ResearchProgressReporter(
        repo, "run-a", profile_id=PROFILE, selected_analysts=["market", "sentiment"]
    )
    reporter.initialize()
    reporter.record_stage("initializing")
    reporter.record_analyst_completed("market")
    reporter.record_analyst_completed("market")  # duplicate: no double advance
    reporter.record_analyst_completed("sentiment")
    reporter.record_stage("research_debate")
    reporter.record_stage("research_debate")  # duplicate stage: no-op
    reporter.record_terminal("completed")

    percents = [(u["current_stage"], u["progress_percent"], u["completed_units"]) for u in repo.updates]
    assert percents == [
        ("initializing", 10, 0),
        ("market_analysis", 30, 1),
        ("sentiment_analysis", 50, 2),
        ("research_debate", 58, 3),
    ]
    assert repo.terminal == ["completed"]


def test_reporter_ignores_unselected_analyst_and_unknown_stage():
    repo = _RecordingRepo()
    reporter = ResearchProgressReporter(
        repo, "run-a", profile_id=PROFILE, selected_analysts=["market"]
    )
    reporter.record_analyst_completed("news")  # not selected
    reporter.record_stage("made_up_stage")
    assert repo.updates == []


def test_reporter_swallows_repository_failures():
    class _ExplodingRepo:
        def initialize_research_progress(self, *args, **kwargs):
            raise RuntimeError("db down")

        def update_research_progress(self, *args, **kwargs):
            raise RuntimeError("db down")

        def mark_research_progress_failed(self, *args, **kwargs):
            raise RuntimeError("db down")

    reporter = ResearchProgressReporter(
        _ExplodingRepo(), "run-a", profile_id=PROFILE, selected_analysts=ANALYSTS
    )
    reporter.initialize()
    reporter.record_stage("initializing")
    reporter.record_terminal("failed", message="x")  # must not raise


# ---------------------------------------------------------------------------
# ETA history rules
# ---------------------------------------------------------------------------


def test_eta_estimating_below_three_samples():
    repo = _memory_repo()
    _completed_real_run(repo, "hist-1", duration_seconds=120)
    _completed_real_run(repo, "hist-2", duration_seconds=180)

    _claim(repo, "live-1")
    repo.initialize_research_progress("live-1", profile_id=PROFILE, total_units=15)
    status = get_research_run_status("live-1", graph_repository=repo)
    assert status["eta_status"] == "estimating"
    assert status["eta_sample_count"] == 2
    assert status["estimated_remaining_seconds_min"] is None
    assert status["estimated_remaining_seconds_max"] is None


def test_eta_available_with_three_matching_samples():
    repo = _memory_repo()
    for index, duration in enumerate((120, 180, 240)):
        _completed_real_run(repo, f"hist-{index}", duration_seconds=duration)

    _claim(repo, "live-1")
    repo.mark_research_run_running("live-1")
    repo.initialize_research_progress("live-1", profile_id=PROFILE, total_units=15)
    status = get_research_run_status("live-1", graph_repository=repo)
    assert status["eta_status"] == "available"
    assert status["eta_sample_count"] == 3
    assert status["estimated_remaining_seconds_min"] is not None
    assert status["estimated_remaining_seconds_max"] is not None
    assert 0 <= status["estimated_remaining_seconds_min"] <= status["estimated_remaining_seconds_max"]


def test_eta_ignores_other_profiles_and_selections_and_non_completed():
    repo = _memory_repo()
    _completed_real_run(repo, "hist-other-profile", duration_seconds=100, profile_id="different_profile_v9")
    _completed_real_run(repo, "hist-other-analysts", duration_seconds=100, analysts=["market", "news"])
    # A partial real run never qualifies.
    _claim(repo, "hist-partial")
    repo.mark_research_run_running("hist-partial")
    repo.mark_research_run_terminal("hist-partial", status="partial")
    end = datetime.now(UTC)
    _set_run_window(repo, "hist-partial", started=end - timedelta(seconds=100), completed=end)
    repo.initialize_research_progress("hist-partial", profile_id=PROFILE, total_units=15)
    repo.mark_research_progress_completed("hist-partial", partial=True)
    # A failed real run never qualifies.
    _claim(repo, "hist-failed")
    repo.mark_research_run_running("hist-failed")
    repo.mark_research_run_terminal("hist-failed", status="failed", error_code="INTERNAL_ERROR")
    # An offline completed run never qualifies (execution_mode filter).
    _claim(repo, "hist-offline", execution_mode="offline")
    repo.mark_research_run_running("hist-offline")
    repo.mark_research_run_terminal("hist-offline", status="completed")
    end = datetime.now(UTC)
    _set_run_window(repo, "hist-offline", started=end - timedelta(seconds=100), completed=end)
    repo.initialize_research_progress("hist-offline", profile_id=PROFILE, total_units=15)
    repo.mark_research_progress_completed("hist-offline")

    durations = repo.list_real_completed_run_durations(
        profile_id=PROFILE, selected_analysts=ANALYSTS
    )
    assert durations == []


def test_eta_remaining_clamped_at_zero_when_overdue():
    repo = _memory_repo()
    for index in range(3):
        _completed_real_run(repo, f"hist-{index}", duration_seconds=10)

    _claim(repo, "live-1")
    repo.mark_research_run_running("live-1")
    # Force an elapsed time far beyond every historical duration.
    with repo._engine.begin() as conn:  # noqa: SLF001
        conn.execute(
            sa.update(research_runs)
            .where(research_runs.c.run_id == "live-1")
            .values(started_at=datetime.now(UTC) - timedelta(seconds=3600))
        )
    repo.initialize_research_progress("live-1", profile_id=PROFILE, total_units=15)
    status = get_research_run_status("live-1", graph_repository=repo)
    assert status["eta_status"] == "available"
    assert status["estimated_remaining_seconds_min"] == 0
    assert status["estimated_remaining_seconds_max"] == 0


# ---------------------------------------------------------------------------
# Status API enrichment shape
# ---------------------------------------------------------------------------


def test_status_response_carries_progress_fields_and_display_name():
    repo = _memory_repo()
    _claim(repo, "live-1")
    repo.mark_research_run_running("live-1")
    repo.initialize_research_progress("live-1", profile_id=PROFILE, total_units=15)
    repo.update_research_progress(
        "live-1", progress_percent=43, current_stage="news_analysis", completed_units=4,
        progress_message="Running the News Analyst.",
    )
    status = get_research_run_status("live-1", graph_repository=repo)
    assert status["profile_id"] == PROFILE
    assert status["profile_display_name"] == "COMQUTOR Anthropic Medium v1"
    assert status["progress_percent"] == 43
    assert status["current_stage"] == "news_analysis"
    assert status["completed_units"] == 4
    assert status["total_units"] == 15
    assert status["progress_message"] == "Running the News Analyst."
    assert isinstance(status["elapsed_seconds"], int)
    assert status["eta_status"] in ("estimating", "available")
    # Never a fingerprint, credential, or config hash.
    serialized = str(status)
    for forbidden in ("request_fingerprint", "active_fingerprint", "config_identity", "sha256"):
        assert forbidden not in serialized


def test_status_response_without_progress_row_degrades_safely():
    repo = _memory_repo()
    _claim(repo, "legacy-1")
    status = get_research_run_status("legacy-1", graph_repository=repo)
    assert status["progress_percent"] is None
    assert status["current_stage"] is None
    assert status["eta_status"] == "estimating"
    assert status["eta_sample_count"] == 0


def test_status_response_terminal_eta_states():
    repo = _memory_repo()
    _completed_real_run(repo, "done-1", duration_seconds=60)
    status = get_research_run_status("done-1", graph_repository=repo)
    assert status["eta_status"] == "complete"
    assert status["progress_percent"] == 100

    _claim(repo, "failed-1")
    repo.mark_research_run_running("failed-1")
    repo.mark_research_run_terminal("failed-1", status="failed", error_code="INTERNAL_ERROR")
    status = get_research_run_status("failed-1", graph_repository=repo)
    assert status["eta_status"] == "unavailable"


# ---------------------------------------------------------------------------
# Worker/lifecycle failure consistency
# ---------------------------------------------------------------------------


def test_job_manager_failure_marks_progress_failed():
    from comqutor_alpha.research_jobs import JobManager

    repo = _memory_repo()
    _claim(repo, "run-a")
    repo.initialize_research_progress("run-a", profile_id=PROFILE, total_units=15)
    manager = JobManager(
        max_workers=1,
        queue_capacity=1,
        timeout_seconds=60,
        shutdown_grace_seconds=1,
        repository_factory=lambda: repo,
    )
    manager._mark_failed_if_active(  # noqa: SLF001 -- unit-testing the shared failure path
        "run-a", "RESEARCH_TIMEOUT", "The research run exceeded the configured execution time."
    )
    record = repo.get_research_run_record("run-a")
    assert record["status"] == "failed"
    progress = repo.get_research_progress("run-a")
    assert progress["current_stage"] == "failed"
    assert progress["progress_percent"] == 8  # preserved, never faked


def test_startup_reconciliation_marks_progress_failed():
    from comqutor_alpha.research_jobs import reconcile_orphaned_runs_on_startup

    repo = _memory_repo()
    _claim(repo, "orphan-1")
    repo.mark_research_run_running("orphan-1")
    repo.initialize_research_progress("orphan-1", profile_id=PROFILE, total_units=15)
    repo.update_research_progress(
        "orphan-1", progress_percent=40, current_stage="news_analysis", completed_units=3
    )

    reconciled = reconcile_orphaned_runs_on_startup(repo)
    assert reconciled == ["orphan-1"]
    progress = repo.get_research_progress("orphan-1")
    assert progress["current_stage"] == "failed"
    assert progress["progress_percent"] == 40
    assert "server restart" in progress["progress_message"].lower()
