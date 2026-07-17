"""W5.1B: comqutor_alpha/research_jobs.py (JobManager, background
submission) tests.

Fast, deterministic coverage of crash/timeout/queue-full/shutdown/
reconciliation logic uses an injected fake process double (see
``_FakeProcess``) rather than real OS process spawns -- the private
``process_factory``/``worker_entrypoint`` seams exist for exactly this.
One test (``test_real_multiprocessing_end_to_end_with_fake_worker``) uses a
*real* ``multiprocessing`` spawn-context process with a fake (non-
TradingAgents) module-level worker function, proving the actual process
architecture works end-to-end without ever touching a real LLM/provider/
network.
"""

from __future__ import annotations

import tempfile
import time
import uuid
from pathlib import Path

import pytest

import comqutor_alpha.research_jobs as research_jobs
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository


def _memory_repo():
    """Despite the name (kept for minimal diff against earlier call sites),
    this is a file-based SQLite repo, not ``sqlite:///:memory:``. In-memory
    SQLite is backed by a single ``StaticPool``-pinned connection shared
    across every checkout -- fine for sequential access, but not safe for
    the genuine concurrent access these tests exercise (the JobManager's
    background supervisor thread reading/writing the same repository
    concurrently with the main test thread's polling reads). A real file
    gets SQLAlchemy's normal pooled-connection behavior instead, exactly
    like the concurrency tests in test_research_runs_persistence.py already
    use (``_file_repo(tmp_path)``) for the same reason.
    """
    db_path = Path(tempfile.mkdtemp()) / f"{uuid.uuid4().hex}.db"
    engine = build_engine(f"sqlite:///{db_path}")
    apply_migrations(engine)
    return GraphPersistenceRepository(engine)


def _claim(repo, fingerprint, **overrides):
    kwargs = {
        "run_id": None,
        "request_fingerprint": fingerprint,
        "ticker": "NVDA",
        "analysis_date": "2026-06-30",
        "selected_analysts": ["market"],
        "execution_mode": "offline",
        "provider_identity": "x",
        "model_identity": "y",
        "pipeline_identity": {},
        "force_refresh": False,
    }
    kwargs.update(overrides)
    run_id = repo.claim_research_run(**kwargs)["run_id"]
    repo.initialize_research_progress(run_id, profile_id="offline_fixture_v1", total_units=12)
    return run_id


def _assert_failed_progress(repo, run_id):
    progress = repo.get_research_progress(run_id)
    assert progress["current_stage"] == "failed"
    assert progress["progress_percent"] < 100


class _FakeProcess:
    """Duck-typed multiprocessing.Process double: start()/is_alive()/
    exitcode/terminate()/join()/kill(). Lets tests control exactly when
    (and how) a "worker" finishes without spawning a real OS process."""

    def __init__(self, target, args):
        self.target = target
        self.args = args
        self._alive = False
        self.exitcode = None
        self.terminate_called = False
        self.kill_called = False

    def start(self):
        self._alive = True

    def is_alive(self):
        return self._alive

    def terminate(self):
        self.terminate_called = True
        self._alive = False
        if self.exitcode is None:
            self.exitcode = -15

    def kill(self):
        self.kill_called = True
        self._alive = False
        self.exitcode = -9

    def join(self, timeout=None):
        return None

    def finish(self, exitcode=0):
        self._alive = False
        self.exitcode = exitcode


class _FailingStartProcess(_FakeProcess):
    def start(self):
        raise OSError("could not fork/spawn")


def _make_manager(repo, *, factory=None, **overrides):
    kwargs = {
        "max_workers": 1,
        "queue_capacity": 2,
        "timeout_seconds": 1000,
        "shutdown_grace_seconds": 1,
        "process_factory": factory,
        "repository_factory": lambda: repo,
        "poll_interval": 0.01,
    }
    kwargs.update(overrides)
    return research_jobs.JobManager(**kwargs)


# ---------------------------------------------------------------------------
# resolve_job_manager_settings: bounded, safe-fail env parsing
# ---------------------------------------------------------------------------


def test_default_settings(monkeypatch):
    for var in (
        "COMQUTOR_JOB_MAX_WORKERS",
        "COMQUTOR_JOB_QUEUE_CAPACITY",
        "COMQUTOR_JOB_TIMEOUT_SECONDS",
        "COMQUTOR_JOB_SHUTDOWN_GRACE_SECONDS",
    ):
        monkeypatch.delenv(var, raising=False)
    settings = research_jobs.resolve_job_manager_settings()
    assert settings == {
        "max_workers": 1,
        "queue_capacity": 8,
        "timeout_seconds": 1800,
        "shutdown_grace_seconds": 10,
    }


@pytest.mark.parametrize(
    ("env_var", "value"),
    [
        ("COMQUTOR_JOB_MAX_WORKERS", "0"),
        ("COMQUTOR_JOB_MAX_WORKERS", "5"),
        ("COMQUTOR_JOB_MAX_WORKERS", "not-a-number"),
        ("COMQUTOR_JOB_QUEUE_CAPACITY", "-1"),
        ("COMQUTOR_JOB_QUEUE_CAPACITY", "101"),
        ("COMQUTOR_JOB_TIMEOUT_SECONDS", "29"),
        ("COMQUTOR_JOB_TIMEOUT_SECONDS", "14401"),
        ("COMQUTOR_JOB_SHUTDOWN_GRACE_SECONDS", "-1"),
        ("COMQUTOR_JOB_SHUTDOWN_GRACE_SECONDS", "61"),
    ],
)
def test_out_of_range_or_malformed_settings_fail_safely(monkeypatch, env_var, value):
    monkeypatch.setenv(env_var, value)
    with pytest.raises(research_jobs.JobManagerConfigError):
        research_jobs.resolve_job_manager_settings()


def test_in_range_settings_accepted(monkeypatch):
    monkeypatch.setenv("COMQUTOR_JOB_MAX_WORKERS", "4")
    monkeypatch.setenv("COMQUTOR_JOB_QUEUE_CAPACITY", "0")
    monkeypatch.setenv("COMQUTOR_JOB_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("COMQUTOR_JOB_SHUTDOWN_GRACE_SECONDS", "60")
    settings = research_jobs.resolve_job_manager_settings()
    assert settings == {
        "max_workers": 4,
        "queue_capacity": 0,
        "timeout_seconds": 30,
        "shutdown_grace_seconds": 60,
    }


# ---------------------------------------------------------------------------
# Import / construction never starts background activity
# ---------------------------------------------------------------------------


def test_import_does_not_start_a_worker():
    # research_jobs is already imported at module scope above; reaching
    # here with no thread/process side effects already proves it. Belt and
    # suspenders: constructing a manager must not start anything either.
    repo = _memory_repo()
    jm = _make_manager(repo, factory=lambda target, args: _FakeProcess(target, args))
    assert jm.is_accepting() is False
    assert jm.active_count() == 0
    assert jm.pending_count() == 0


# ---------------------------------------------------------------------------
# Bounded worker count / bounded queue
# ---------------------------------------------------------------------------


def test_bounded_worker_count_does_not_exceed_max_workers():
    repo = _memory_repo()
    processes = []

    def factory(target, args):
        p = _FakeProcess(target, args)
        processes.append(p)
        return p

    jm = _make_manager(repo, factory=factory, max_workers=2, queue_capacity=5)
    jm.start()
    try:
        run_ids = [_claim(repo, f"fp-bound-{i}") for i in range(4)]
        for run_id in run_ids:
            assert jm.submit(run_id, {}, disposition="created", ticker="NVDA")
        time.sleep(0.1)
        assert jm.active_count() == 2
        assert jm.pending_count() == 2
    finally:
        jm.shutdown()


def test_bounded_queue_rejects_beyond_total_capacity():
    repo = _memory_repo()

    def factory(target, args):
        return _FakeProcess(target, args)

    jm = _make_manager(repo, factory=factory, max_workers=1, queue_capacity=1)
    # Do not start the supervisor thread, so nothing is promoted from
    # pending -> active during this test -- isolates pure capacity counting.
    run_a = _claim(repo, "fp-cap-a")
    run_b = _claim(repo, "fp-cap-b")
    run_c = _claim(repo, "fp-cap-c")
    with jm._lock:  # noqa: SLF001 -- test-only direct state manipulation
        jm._accepting = True
    assert jm.submit(run_a, {}, disposition="created", ticker="NVDA") is True
    assert jm.submit(run_b, {}, disposition="created", ticker="NVDA") is True
    assert jm.submit(run_c, {}, disposition="created", ticker="NVDA") is False


def test_queue_capacity_zero_still_runs_immediately_when_worker_free():
    repo = _memory_repo()

    def factory(target, args):
        return _FakeProcess(target, args)

    jm = _make_manager(repo, factory=factory, max_workers=1, queue_capacity=0)
    jm.start()
    try:
        run_id = _claim(repo, "fp-zero-cap")
        assert jm.submit(run_id, {}, disposition="created", ticker="NVDA") is True
        time.sleep(0.1)
        assert jm.active_count() == 1
    finally:
        jm.shutdown()


# ---------------------------------------------------------------------------
# Queue full marks failed + frees active_fingerprint
# ---------------------------------------------------------------------------


def test_queue_full_marks_run_failed_and_frees_active_fingerprint():
    repo = _memory_repo()

    def factory(target, args):
        return _FakeProcess(target, args)

    jm = _make_manager(repo, factory=factory, max_workers=1, queue_capacity=0)
    with jm._lock:  # noqa: SLF001
        jm._accepting = True
    run_id = _claim(repo, "fp-queue-full")

    result = research_jobs.enqueue_research_request(
        {"ticker": "NVDA", "offline_raw_agent_outputs": [{"agent": "x", "raw_output": "y"}]},
        graph_repository=repo,
        job_manager=jm,
    )
    # This call claims its own new run (different fingerprint); to
    # directly exercise "queue full", saturate the manager first via the
    # low-level submit(), then confirm enqueue_research_request's own
    # queue-full handling for its own claimed row.
    assert result["cache_disposition"] in ("created", "reused_completed", "force_refreshed")

    # Now directly test the mark-failed-on-queue-full contract using the
    # pre-claimed row above and a manager whose submit() always refuses.
    jm.submit(run_id, {}, disposition="created", ticker="NVDA")  # occupies the only slot in pending
    another_run_id = _claim(repo, "fp-queue-full-2")
    accepted = jm.submit(another_run_id, {}, disposition="created", ticker="NVDA")
    assert accepted is False

    record_before = repo.get_research_run_record(another_run_id)
    assert record_before["status"] == "queued"
    repo.mark_research_run_failed_if_active(
        another_run_id, error_code="RESEARCH_QUEUE_FULL", error_message="The research job queue is full."
    )
    record_after = repo.get_research_run_record(another_run_id)
    assert record_after["status"] == "failed"
    assert record_after["error_code"] == "RESEARCH_QUEUE_FULL"
    assert record_after["active_fingerprint"] is None


def test_enqueue_research_request_queue_full_end_to_end():
    repo = _memory_repo()

    class _AlwaysFullManager:
        def is_accepting(self):
            return True

        def submit(self, *_args, **_kwargs):
            return False

    result = research_jobs.enqueue_research_request(
        {"ticker": "NVDA", "offline_raw_agent_outputs": [{"agent": "x", "raw_output": "z1"}]},
        graph_repository=repo,
        job_manager=_AlwaysFullManager(),
    )
    assert result["error_code"] == "RESEARCH_QUEUE_FULL"
    assert result["run_status"] == "failed"
    record = repo.get_research_run_record(result["run_id"])
    assert record["status"] == "failed"
    assert record["error_code"] == "RESEARCH_QUEUE_FULL"
    assert record["active_fingerprint"] is None
    _assert_failed_progress(repo, result["run_id"])


def test_enqueue_research_request_job_manager_unavailable():
    repo = _memory_repo()
    result = research_jobs.enqueue_research_request(
        {"ticker": "NVDA", "offline_raw_agent_outputs": [{"agent": "x", "raw_output": "z2"}]},
        graph_repository=repo,
        job_manager=None,
    )
    assert result["error_code"] == "JOB_MANAGER_UNAVAILABLE"
    record = repo.get_research_run_record(result["run_id"])
    assert record["status"] == "failed"
    assert record["active_fingerprint"] is None
    _assert_failed_progress(repo, result["run_id"])


# ---------------------------------------------------------------------------
# Reuse dispositions never enqueue
# ---------------------------------------------------------------------------


def test_completed_reuse_does_not_enqueue(tmp_path):
    # Uses the real synchronous submit_research_request to genuinely
    # complete a run (real artifacts on disk) rather than forcing "completed"
    # directly on the row -- a forced-but-artifact-less "completed" row
    # would (correctly, per the W5.1A fix) come back CACHED_RUN_UNAVAILABLE
    # instead of reused_completed, which is not what this test wants to
    # exercise.
    from comqutor_alpha.research_lifecycle import submit_research_request

    repo = _memory_repo()

    class _CountingManager:
        def __init__(self):
            self.submitted = 0

        def is_accepting(self):
            return True

        def submit(self, *_args, **_kwargs):
            self.submitted += 1
            return True

    manager = _CountingManager()
    payload = {"ticker": "NVDA", "offline_raw_agent_outputs": [{"agent": "x", "raw_output": "reuse-1"}]}
    first = submit_research_request(payload, output_root=tmp_path, graph_repository=repo)
    assert first["cache_disposition"] == "created"
    assert first["run_status"] == "completed"

    second = research_jobs.enqueue_research_request(
        payload, output_root=tmp_path, graph_repository=repo, job_manager=manager
    )
    assert second["cache_disposition"] == "reused_completed"
    assert manager.submitted == 0  # never enqueued -- served synchronously from the DB row


def test_active_reuse_does_not_enqueue():
    repo = _memory_repo()

    class _CountingManager:
        def __init__(self):
            self.submitted = 0

        def is_accepting(self):
            return True

        def submit(self, *_args, **_kwargs):
            self.submitted += 1
            return True

    manager = _CountingManager()
    payload = {"ticker": "NVDA", "offline_raw_agent_outputs": [{"agent": "x", "raw_output": "reuse-2"}]}
    first = research_jobs.enqueue_research_request(payload, graph_repository=repo, job_manager=manager)
    assert first["cache_disposition"] == "created"

    second = research_jobs.enqueue_research_request(payload, graph_repository=repo, job_manager=manager)
    assert second["cache_disposition"] == "reused_in_flight"
    assert manager.submitted == 1  # only the first (created) request ever hit submit()


# ---------------------------------------------------------------------------
# Worker start failure
# ---------------------------------------------------------------------------


def test_worker_start_failure_marks_run_failed():
    repo = _memory_repo()

    def factory(target, args):
        return _FailingStartProcess(target, args)

    jm = _make_manager(repo, factory=factory)
    jm.start()
    try:
        run_id = _claim(repo, "fp-start-fail")
        assert jm.submit(run_id, {}, disposition="created", ticker="NVDA") is True
        for _ in range(200):
            record = repo.get_research_run_record(run_id)
            if record["status"] == "failed":
                break
            time.sleep(0.02)
        assert record["status"] == "failed"
        assert record["error_code"] == "RESEARCH_WORKER_START_FAILED"
        assert record["active_fingerprint"] is None
        _assert_failed_progress(repo, run_id)
    finally:
        jm.shutdown()


# ---------------------------------------------------------------------------
# Worker crash
# ---------------------------------------------------------------------------


def test_worker_crash_marks_run_failed():
    repo = _memory_repo()
    processes = []

    def factory(target, args):
        p = _FakeProcess(target, args)
        processes.append(p)
        return p

    jm = _make_manager(repo, factory=factory)
    jm.start()
    try:
        run_id = _claim(repo, "fp-crash")
        assert jm.submit(run_id, {}, disposition="created", ticker="NVDA")
        for _ in range(50):
            if processes:
                break
            time.sleep(0.01)
        processes[0].finish(exitcode=1)
        for _ in range(200):
            record = repo.get_research_run_record(run_id)
            if record["status"] == "failed":
                break
            time.sleep(0.02)
        assert record["status"] == "failed"
        assert record["error_code"] == "RESEARCH_WORKER_CRASHED"
        assert record["active_fingerprint"] is None
        _assert_failed_progress(repo, run_id)
    finally:
        jm.shutdown()


def test_worker_normal_completion_is_not_overwritten_by_supervisor():
    repo = _memory_repo()
    processes = []

    def factory(target, args):
        p = _FakeProcess(target, args)
        processes.append(p)
        return p

    jm = _make_manager(repo, factory=factory)
    jm.start()
    try:
        run_id = _claim(repo, "fp-normal-complete")
        assert jm.submit(run_id, {}, disposition="created", ticker="NVDA")
        for _ in range(50):
            if processes:
                break
            time.sleep(0.01)
        # Simulate the worker itself having already written "completed"
        # (as execute_claimed_research_run would, in-process) before exiting
        # cleanly.
        repo.mark_research_run_running(run_id)
        repo.mark_research_run_terminal(run_id, status="completed")
        processes[0].finish(exitcode=0)
        time.sleep(0.15)
        record = repo.get_research_run_record(run_id)
        assert record["status"] == "completed"  # never overwritten
    finally:
        jm.shutdown()


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


def test_timeout_terminates_worker_and_clears_active_fingerprint():
    repo = _memory_repo()
    processes = []

    def factory(target, args):
        p = _FakeProcess(target, args)
        processes.append(p)
        return p

    jm = _make_manager(repo, factory=factory, timeout_seconds=0)
    jm.start()
    try:
        run_id = _claim(repo, "fp-timeout")
        assert jm.submit(run_id, {}, disposition="created", ticker="NVDA")
        for _ in range(200):
            record = repo.get_research_run_record(run_id)
            if record["status"] == "failed":
                break
            time.sleep(0.02)
        assert record["status"] == "failed"
        assert record["error_code"] == "RESEARCH_TIMEOUT"
        assert record["active_fingerprint"] is None
        assert processes[0].terminate_called is True
        _assert_failed_progress(repo, run_id)
    finally:
        jm.shutdown()


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------


def test_shutdown_rejects_new_jobs():
    repo = _memory_repo()

    def factory(target, args):
        return _FakeProcess(target, args)

    jm = _make_manager(repo, factory=factory)
    jm.start()
    jm.shutdown()
    run_id = _claim(repo, "fp-shutdown-reject")
    assert jm.submit(run_id, {}, disposition="created", ticker="NVDA") is False


def test_shutdown_terminates_active_process_and_fails_it():
    repo = _memory_repo()
    processes = []

    def factory(target, args):
        p = _FakeProcess(target, args)
        processes.append(p)
        return p

    jm = _make_manager(repo, factory=factory, timeout_seconds=1000, shutdown_grace_seconds=0)
    jm.start()
    run_id = _claim(repo, "fp-shutdown-active")
    assert jm.submit(run_id, {}, disposition="created", ticker="NVDA")
    for _ in range(50):
        if processes:
            break
        time.sleep(0.01)
    jm.shutdown()

    record = repo.get_research_run_record(run_id)
    assert record["status"] == "failed"
    assert record["error_code"] == "SERVER_SHUTDOWN"
    assert record["active_fingerprint"] is None
    assert processes[0].is_alive() is False
    _assert_failed_progress(repo, run_id)


def test_shutdown_fails_pending_jobs_too():
    repo = _memory_repo()

    def factory(target, args):
        return _FakeProcess(target, args)

    jm = _make_manager(repo, factory=factory, max_workers=1, queue_capacity=1)
    with jm._lock:  # noqa: SLF001
        jm._accepting = True
    active_run = _claim(repo, "fp-shutdown-pending-active")
    pending_run = _claim(repo, "fp-shutdown-pending-pending")
    assert jm.submit(active_run, {}, disposition="created", ticker="NVDA")
    assert jm.submit(pending_run, {}, disposition="created", ticker="NVDA")
    # Neither was ever promoted (supervisor thread never started), so both
    # sit as "pending" from the manager's point of view.
    jm.shutdown()

    for run_id in (active_run, pending_run):
        record = repo.get_research_run_record(run_id)
        assert record["status"] == "failed"
        assert record["error_code"] == "SERVER_SHUTDOWN"
        _assert_failed_progress(repo, run_id)


def test_no_zombie_process_after_shutdown():
    repo = _memory_repo()
    processes = []

    def factory(target, args):
        p = _FakeProcess(target, args)
        processes.append(p)
        return p

    jm = _make_manager(repo, factory=factory, shutdown_grace_seconds=0)
    jm.start()
    run_id = _claim(repo, "fp-no-zombie")
    jm.submit(run_id, {}, disposition="created", ticker="NVDA")
    for _ in range(50):
        if processes:
            break
        time.sleep(0.01)
    jm.shutdown()
    assert all(not p.is_alive() for p in processes)


# ---------------------------------------------------------------------------
# Startup reconciliation
# ---------------------------------------------------------------------------


def test_reconcile_orphaned_queued_run():
    repo = _memory_repo()
    run_id = _claim(repo, "fp-orphan-queued")
    reconciled = research_jobs.reconcile_orphaned_runs_on_startup(repo)
    assert run_id in reconciled
    record = repo.get_research_run_record(run_id)
    assert record["status"] == "failed"
    assert record["error_code"] == "SERVER_RESTARTED"
    assert record["active_fingerprint"] is None
    _assert_failed_progress(repo, run_id)


def test_reconcile_orphaned_running_run():
    repo = _memory_repo()
    run_id = _claim(repo, "fp-orphan-running")
    repo.mark_research_run_running(run_id)
    reconciled = research_jobs.reconcile_orphaned_runs_on_startup(repo)
    assert run_id in reconciled
    record = repo.get_research_run_record(run_id)
    assert record["status"] == "failed"
    assert record["error_code"] == "SERVER_RESTARTED"
    _assert_failed_progress(repo, run_id)


@pytest.mark.parametrize("terminal_status", ["completed", "partial", "failed"])
def test_reconcile_does_not_touch_terminal_runs(terminal_status):
    repo = _memory_repo()
    run_id = _claim(repo, f"fp-orphan-{terminal_status}")
    repo.mark_research_run_running(run_id)
    repo.mark_research_run_terminal(run_id, status=terminal_status)
    before = repo.get_research_run_record(run_id)

    reconciled = research_jobs.reconcile_orphaned_runs_on_startup(repo)
    assert run_id not in reconciled
    after = repo.get_research_run_record(run_id)
    assert before == after


# ---------------------------------------------------------------------------
# Real multiprocessing end-to-end (fake worker, no real TradingAgents)
# ---------------------------------------------------------------------------


def _fake_real_worker_entrypoint(run_id, execution_payload, output_root, disposition, ticker):
    """Module-level, picklable -- required for a genuine spawn-context
    Process. Proves the real process-supervision architecture without ever
    invoking TradingAgents/an LLM/a network call."""
    from comqutor_alpha.research_lifecycle import execute_claimed_research_run
    from comqutor_alpha.storage.db.repository import build_write_repository_from_env

    repository = build_write_repository_from_env(output_root)

    def _fake_executor(_payload, **_kwargs):
        return {"run_id": run_id, "ticker": ticker, "status": "completed"}

    execute_claimed_research_run(
        run_id,
        execution_payload,
        output_root=output_root,
        graph_repository=repository,
        disposition=disposition,
        ticker=ticker,
        executor=_fake_executor,
    )


def test_real_multiprocessing_end_to_end_with_fake_worker(tmp_path):
    from comqutor_alpha.storage.db.repository import build_write_repository_from_env

    output_root = str(tmp_path)
    repo = build_write_repository_from_env(output_root)
    run_id = _claim(repo, "fp-real-mp-e2e")

    jm = research_jobs.JobManager(
        max_workers=1,
        queue_capacity=2,
        timeout_seconds=60,
        shutdown_grace_seconds=10,
        output_root=output_root,
        worker_entrypoint=_fake_real_worker_entrypoint,
        poll_interval=0.05,
    )
    jm.start()
    try:
        assert jm.submit(run_id, {"ticker": "NVDA"}, disposition="created", ticker="NVDA", output_root=output_root)
        record = None
        for _ in range(200):
            record = repo.get_research_run_record(run_id)
            if record["status"] == "completed":
                break
            time.sleep(0.1)
        assert record["status"] == "completed"
    finally:
        jm.shutdown()
    assert jm.active_count() == 0
