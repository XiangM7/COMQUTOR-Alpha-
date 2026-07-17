"""W5.1B Final Correctness Patch tests.

Covers the five confirmed gaps closed by this patch (found in commit
a727cf18b557707e82a09cae6f6976bbb710d455 / "w5v2"):

A. A pending -> starting -> active escape race in ``JobManager`` between
   ``shutdown()`` and ``_start_pending()``'s ``process.start()`` call.
B. Blind trust that a worker's ``exitcode == 0`` means its terminal DB
   write actually landed.
C. ``GET /api/research/{run_id}/agent-outputs`` silently substituting a
   literal ``"outputs/runs"`` for ``output_root=None``, bypassing
   ``COMQUTOR_OUTPUT_DIR``.
D. ``build_server_execution_context()`` only handling
   ``ServerExecutionConfigError``, not the plain ``ValueError``/``TypeError``
   TradingAgents' own ``TRADINGAGENTS_*`` env-var parsing can raise at
   ``tradingagents.default_config`` import time.
E. CORS silently dropping blank tokens and ``"*"`` instead of rejecting the
   whole configuration.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

import pytest

import comqutor_alpha.research_jobs as research_jobs
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceError, GraphPersistenceRepository

REPO_ROOT = Path(__file__).resolve().parents[1]


def _file_repo(tmp_path=None):
    """File-based SQLite (never ``:memory:``/StaticPool) -- required for
    genuine concurrent access between the supervisor thread and the test's
    own thread(s); see test_research_jobs.py's ``_memory_repo`` docstring
    for why in-memory SQLite is unsafe here."""
    root = Path(tmp_path) if tmp_path is not None else Path(tempfile.mkdtemp())
    db_path = root / f"{uuid.uuid4().hex}.db"
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
    return repo.claim_research_run(**kwargs)["run_id"]


# ---------------------------------------------------------------------------
# Fake process doubles
# ---------------------------------------------------------------------------


class _FakeProcess:
    def __init__(self, target, args):
        self.target = target
        self.args = args
        self._alive = False
        self.exitcode = None

    def start(self):
        self._alive = True

    def is_alive(self):
        return self._alive

    def terminate(self):
        self._alive = False
        if self.exitcode is None:
            self.exitcode = -15

    def kill(self):
        self._alive = False
        self.exitcode = -9

    def join(self, timeout=None):
        return None

    def finish(self, exitcode=0):
        self._alive = False
        self.exitcode = exitcode


class _InstantCleanExitProcess:
    """``start()`` returns immediately with the process already "exited"
    (``is_alive() == False``, ``exitcode == 0``) -- simulates a worker that
    ran and exited cleanly before the supervisor even checks it once."""

    def __init__(self, target, args):
        self.target = target
        self.args = args
        self.exitcode = 0

    def start(self):
        return None

    def is_alive(self):
        return False

    def terminate(self):
        return None

    def kill(self):
        return None

    def join(self, timeout=None):
        return None


class _FailingStartProcess(_FakeProcess):
    def start(self):
        raise OSError("could not fork/spawn")


class _BlockingStartProcess:
    """``start()`` blocks on ``start_gate`` until the test releases it --
    used to deterministically land inside the pending-popped-but-not-yet-
    active window that Fix 1 closes."""

    def __init__(self, target, args, *, start_gate, started_signal):
        self.target = target
        self.args = args
        self._start_gate = start_gate
        self._started_signal = started_signal
        self._alive = False
        self.exitcode = None

    def start(self):
        self._started_signal.set()
        self._start_gate.wait(timeout=10.0)
        self._alive = True

    def is_alive(self):
        return self._alive

    def terminate(self):
        self._alive = False
        self.exitcode = -15

    def kill(self):
        self._alive = False
        self.exitcode = -9

    def join(self, timeout=None):
        return None


def _make_manager(repo, *, factory, **overrides):
    kwargs = {
        "max_workers": 1,
        "queue_capacity": 4,
        "timeout_seconds": 1000,
        "shutdown_grace_seconds": 2,
        "process_factory": factory,
        "repository_factory": lambda: repo,
        "poll_interval": 0.01,
    }
    kwargs.update(overrides)
    return research_jobs.JobManager(**kwargs)


# ===========================================================================
# A. Shutdown / start-pending race (Fix 1)
# ===========================================================================


def test_shutdown_during_blocking_start_terminates_process_and_marks_failed(tmp_path):
    """Proves the exact gap this patch closes: with the *previous*
    implementation, ``shutdown()`` would return once its fixed
    ``supervisor_thread.join(timeout=max(1.0, shutdown_grace_seconds))``
    expired -- here that bound is ``max(1.0, 2) == 2.0`` seconds -- even
    though the supervisor thread was still blocked inside
    ``process.start()`` and ``_starting`` was still non-empty. This test
    holds the block open well past that old timeout and asserts
    ``shutdown()`` is *still* running (not returned, thread still alive,
    ``starting_count() == 1``, nothing yet marked failed) before ever
    releasing the gate -- something the previous implementation could not
    have passed.
    """
    repo = _file_repo(tmp_path)
    start_gate = threading.Event()
    started_signal = threading.Event()
    processes = []
    old_join_timeout = max(1.0, 2)  # shutdown_grace_seconds=2 from _make_manager

    def factory(target, args):
        p = _BlockingStartProcess(target, args, start_gate=start_gate, started_signal=started_signal)
        processes.append(p)
        return p

    jm = _make_manager(repo, factory=factory)
    jm.start()
    run_id = _claim(repo, "fp-blocking-start")
    assert jm.submit(run_id, {}, disposition="created", ticker="NVDA")

    # Wait until the supervisor thread is actually inside process.start().
    assert started_signal.wait(timeout=5.0)
    assert jm.starting_count() == 1
    assert jm.active_count() == 0

    shutdown_thread = threading.Thread(target=jm.shutdown)
    shutdown_thread.start()
    time.sleep(0.2)  # let shutdown() begin (accepting=False, stopped set)
    assert jm.is_accepting() is False

    # Wait well past the OLD fixed join timeout while still holding the
    # gate closed -- shutdown() must NOT have returned by now.
    time.sleep(old_join_timeout + 1.0)
    assert shutdown_thread.is_alive() is True
    assert jm.starting_count() == 1
    assert jm.is_accepting() is False
    still_pending_record = repo.get_research_run_record(run_id)
    assert still_pending_record["status"] == "queued"  # not yet touched

    # Now release the blocked start() call.
    start_gate.set()
    shutdown_thread.join(timeout=10.0)
    assert not shutdown_thread.is_alive()

    assert jm.pending_count() == 0
    assert jm.starting_count() == 0
    assert jm.active_count() == 0
    assert processes[0].is_alive() is False

    record = repo.get_research_run_record(run_id)
    assert record["status"] == "failed"
    assert record["error_code"] == "SERVER_SHUTDOWN"
    assert record["active_fingerprint"] is None
    assert jm.is_accepting() is False
    # F. supervisor thread reference state: never alive after shutdown.
    supervisor_thread = jm._supervisor_thread  # noqa: SLF001 -- test-only inspection
    assert supervisor_thread is None or supervisor_thread.is_alive() is False


def test_shutdown_before_any_start_fails_pending_job(tmp_path):
    repo = _file_repo(tmp_path)

    def factory(target, args):
        return _FakeProcess(target, args)

    # Supervisor thread never started -- job stays in "pending" forever
    # until shutdown() itself handles it.
    jm = _make_manager(repo, factory=factory)
    with jm._lock:  # noqa: SLF001 -- test-only direct state manipulation
        jm._accepting = True
    run_id = _claim(repo, "fp-shutdown-before-start")
    assert jm.submit(run_id, {}, disposition="created", ticker="NVDA")
    assert jm.pending_count() == 1

    jm.shutdown()

    assert jm.pending_count() == 0
    record = repo.get_research_run_record(run_id)
    assert record["status"] == "failed"
    assert record["error_code"] == "SERVER_SHUTDOWN"
    assert record["active_fingerprint"] is None


def test_shutdown_after_start_success_before_registration_is_covered_by_active_path(tmp_path):
    """A job whose process.start() already succeeded and was registered as
    active by the time shutdown() runs is handled by the normal active-job
    termination path -- confirms that path still releases the fingerprint
    and terminates the process (regression guard for the refactor)."""
    repo = _file_repo(tmp_path)
    processes = []

    def factory(target, args):
        p = _FakeProcess(target, args)
        processes.append(p)
        return p

    jm = _make_manager(repo, factory=factory)
    jm.start()
    run_id = _claim(repo, "fp-shutdown-after-active")
    assert jm.submit(run_id, {}, disposition="created", ticker="NVDA")
    for _ in range(200):
        if jm.active_count() == 1:
            break
        time.sleep(0.02)
    assert jm.active_count() == 1

    jm.shutdown()

    record = repo.get_research_run_record(run_id)
    assert record["status"] == "failed"
    assert record["error_code"] == "SERVER_SHUTDOWN"
    assert record["active_fingerprint"] is None
    assert processes[0].is_alive() is False


def test_start_failure_without_shutdown_marks_worker_start_failed(tmp_path):
    repo = _file_repo(tmp_path)

    def factory(target, args):
        return _FailingStartProcess(target, args)

    jm = _make_manager(repo, factory=factory)
    jm.start()
    try:
        run_id = _claim(repo, "fp-start-fail-no-shutdown")
        assert jm.submit(run_id, {}, disposition="created", ticker="NVDA")
        record = None
        for _ in range(200):
            record = repo.get_research_run_record(run_id)
            if record["status"] == "failed":
                break
            time.sleep(0.02)
        assert record["status"] == "failed"
        assert record["error_code"] == "RESEARCH_WORKER_START_FAILED"
        assert record["active_fingerprint"] is None
    finally:
        jm.shutdown()


def test_repeated_shutdown_is_idempotent_and_does_not_raise(tmp_path):
    repo = _file_repo(tmp_path)

    def factory(target, args):
        return _FakeProcess(target, args)

    jm = _make_manager(repo, factory=factory)
    jm.start()
    run_id = _claim(repo, "fp-repeated-shutdown")
    jm.submit(run_id, {}, disposition="created", ticker="NVDA")

    jm.shutdown()
    jm.shutdown()  # must not raise, hang, or double-fail differently
    jm.shutdown()

    assert jm.is_accepting() is False
    record = repo.get_research_run_record(run_id)
    assert record["status"] == "failed"
    assert record["error_code"] == "SERVER_SHUTDOWN"


def test_no_new_process_escapes_after_shutdown_begins(tmp_path):
    """A job submitted (accepted into pending) right as shutdown begins
    must never actually spawn a running process afterward."""
    repo = _file_repo(tmp_path)
    started_processes = []

    def factory(target, args):
        p = _FakeProcess(target, args)
        started_processes.append(p)
        return p

    jm = _make_manager(repo, factory=factory, poll_interval=0.001)
    jm.start()
    jm.shutdown()

    run_id = _claim(repo, "fp-no-escape-after-shutdown")
    accepted = jm.submit(run_id, {}, disposition="created", ticker="NVDA")
    assert accepted is False
    time.sleep(0.05)
    assert jm.active_count() == 0
    assert jm.pending_count() == 0


def test_shutdown_during_start_that_then_raises_marks_server_shutdown(tmp_path):
    """process.start() itself raises (not merely blocks) while shutdown is
    in progress -- must still be attributed to SERVER_SHUTDOWN, never
    RESEARCH_WORKER_START_FAILED (which would misleadingly suggest a normal
    operational failure rather than a deliberate shutdown)."""

    class _BlockingThenRaisingStartProcess:
        def __init__(self, target, args, *, start_gate, started_signal):
            self.target = target
            self.args = args
            self._start_gate = start_gate
            self._started_signal = started_signal
            self._alive = False
            self.exitcode = None

        def start(self):
            self._started_signal.set()
            self._start_gate.wait(timeout=10.0)
            raise OSError("could not fork/spawn (simulated, during shutdown)")

        def is_alive(self):
            return self._alive

        def terminate(self):
            self._alive = False

        def kill(self):
            self._alive = False

        def join(self, timeout=None):
            return None

    repo = _file_repo(tmp_path)
    start_gate = threading.Event()
    started_signal = threading.Event()

    def factory(target, args):
        return _BlockingThenRaisingStartProcess(target, args, start_gate=start_gate, started_signal=started_signal)

    jm = _make_manager(repo, factory=factory)
    jm.start()
    run_id = _claim(repo, "fp-blocking-start-then-raise")
    assert jm.submit(run_id, {}, disposition="created", ticker="NVDA")

    assert started_signal.wait(timeout=5.0)
    assert jm.starting_count() == 1

    shutdown_thread = threading.Thread(target=jm.shutdown)
    shutdown_thread.start()
    time.sleep(0.2)
    assert jm.is_accepting() is False

    start_gate.set()
    shutdown_thread.join(timeout=10.0)
    assert not shutdown_thread.is_alive()
    assert jm.starting_count() == 0

    record = repo.get_research_run_record(run_id)
    assert record is not None
    assert record["status"] == "failed"
    assert record["error_code"] == "SERVER_SHUTDOWN"
    assert record["error_code"] != "RESEARCH_WORKER_START_FAILED"
    assert record["active_fingerprint"] is None


def test_shutdown_then_restart_is_rejected(tmp_path):
    repo = _file_repo(tmp_path)

    def factory(target, args):
        return _FakeProcess(target, args)

    jm = _make_manager(repo, factory=factory)
    jm.start()
    jm.shutdown()
    assert jm.is_accepting() is False

    with pytest.raises(research_jobs.JobManagerConfigError) as exc_info:
        jm.start()
    assert exc_info.value.reason_code == "JOB_MANAGER_ALREADY_SHUT_DOWN"

    # start() must not have partially resurrected anything before raising.
    assert jm.is_accepting() is False
    assert jm._stopped.is_set() is True  # noqa: SLF001 -- test-only inspection
    supervisor_thread = jm._supervisor_thread  # noqa: SLF001
    assert supervisor_thread is None or supervisor_thread.is_alive() is False


def test_shutdown_after_start_failure_supervisor_thread_state(tmp_path):
    """Belt-and-suspenders check of the supervisor-thread-reference
    invariant on a plain (non-blocking) shutdown path, not just the
    blocking-start scenario above."""
    repo = _file_repo(tmp_path)

    def factory(target, args):
        return _FakeProcess(target, args)

    jm = _make_manager(repo, factory=factory)
    jm.start()
    supervisor_thread = jm._supervisor_thread  # noqa: SLF001
    assert supervisor_thread is not None
    assert supervisor_thread.is_alive() is True

    jm.shutdown()

    assert supervisor_thread.is_alive() is False


# ===========================================================================
# B. Worker clean-exit terminal reconciliation (Fix 2)
# ===========================================================================


def _run_clean_exit_scenario(tmp_path, *, prearrange):
    repo = _file_repo(tmp_path)
    run_id = _claim(repo, f"fp-clean-exit-{prearrange.__name__}")
    prearrange(repo, run_id)

    jm = _make_manager(repo, factory=lambda target, args: _InstantCleanExitProcess(target, args))
    jm.start()
    try:
        assert jm.submit(run_id, {}, disposition="created", ticker="NVDA")
        # Give the supervisor a few ticks to reap the instantly-finished
        # process.
        for _ in range(100):
            if jm.active_count() == 0:
                break
            time.sleep(0.02)
        time.sleep(0.1)  # let _reap_finished's mark_failed_if_active land
    finally:
        jm.shutdown()
    return repo.get_research_run_record(run_id)


def test_clean_exit_does_not_overwrite_completed_row(tmp_path):
    def prearrange(repo, run_id):
        repo.mark_research_run_running(run_id)
        repo.mark_research_run_terminal(run_id, status="completed")

    record = _run_clean_exit_scenario(tmp_path, prearrange=prearrange)
    assert record["status"] == "completed"
    assert record["error_code"] is None


def test_clean_exit_does_not_overwrite_partial_row(tmp_path):
    def prearrange(repo, run_id):
        repo.mark_research_run_running(run_id)
        repo.mark_research_run_terminal(run_id, status="partial")

    record = _run_clean_exit_scenario(tmp_path, prearrange=prearrange)
    assert record["status"] == "partial"


def test_clean_exit_does_not_overwrite_failed_row(tmp_path):
    def prearrange(repo, run_id):
        repo.mark_research_run_running(run_id)
        repo.mark_research_run_terminal(
            run_id, status="failed", error_code="INVALID_TICKER", error_message="Invalid ticker."
        )

    record = _run_clean_exit_scenario(tmp_path, prearrange=prearrange)
    assert record["status"] == "failed"
    assert record["error_code"] == "INVALID_TICKER"  # original error preserved, not overwritten
    assert record["error_message"] == "Invalid ticker."


def test_clean_exit_with_row_still_running_is_marked_failed(tmp_path):
    def prearrange(repo, run_id):
        repo.mark_research_run_running(run_id)
        # Never write a terminal status -- simulates the worker's terminal
        # DB write having silently failed (suppressed).

    record = _run_clean_exit_scenario(tmp_path, prearrange=prearrange)
    assert record["status"] == "failed"
    assert record["error_code"] == "RESEARCH_WORKER_RESULT_NOT_PERSISTED"
    assert record["active_fingerprint"] is None
    assert "Traceback" not in (record["error_message"] or "")


def test_clean_exit_with_row_still_queued_is_marked_failed(tmp_path):
    def prearrange(repo, run_id):
        return None  # never even transitioned to running

    record = _run_clean_exit_scenario(tmp_path, prearrange=prearrange)
    assert record["status"] == "failed"
    assert record["error_code"] == "RESEARCH_WORKER_RESULT_NOT_PERSISTED"
    assert record["active_fingerprint"] is None


def test_simulated_terminal_write_failure_is_reconciled_on_clean_exit(tmp_path):
    """End-to-end version of the "running" scenario above: actually drives
    the row through execute_claimed_research_run with an injected
    mark_research_run_terminal failure (exactly what
    _suppress_lifecycle_errors would swallow in production), proving the
    supervisor's clean-exit reconciliation is what ultimately recovers it
    -- not any change to execute_claimed_research_run itself."""
    from comqutor_alpha.research_lifecycle import execute_claimed_research_run

    repo = _file_repo(tmp_path)
    run_id = _claim(repo, "fp-simulated-terminal-write-failure")

    class _FailingTerminalRepo:
        def __getattr__(self, name):
            return getattr(repo, name)

        def mark_research_run_terminal(self, *_args, **_kwargs):
            raise GraphPersistenceError("DB_WRITE_FAILED")

    def fake_executor(_payload, **_kwargs):
        return {"run_id": run_id, "ticker": "NVDA", "status": "completed"}

    # Stands in for what the child worker process does -- its own terminal
    # write fails and is suppressed (execute_claimed_research_run's
    # documented behavior), so it "exits" (returns, here) as if nothing
    # went wrong.
    execute_claimed_research_run(
        run_id,
        {},
        output_root=str(tmp_path),
        graph_repository=_FailingTerminalRepo(),
        disposition="created",
        ticker="NVDA",
        executor=fake_executor,
    )
    mid_record = repo.get_research_run_record(run_id)
    assert mid_record["status"] == "running"  # the worker's write never landed

    jm = _make_manager(repo, factory=lambda target, args: _InstantCleanExitProcess(target, args))
    jm.start()
    try:
        # The row is already claimed/running; register it directly as
        # "active" the way the real _start_pending would have, to exercise
        # exactly the supervisor's _reap_finished reconciliation without
        # re-running the whole claim/submit dance.
        job = research_jobs._Job(
            run_id=run_id, execution_payload={}, disposition="created", ticker="NVDA", output_root=str(tmp_path)
        )
        process = _InstantCleanExitProcess(target=None, args=())
        with jm._lock:  # noqa: SLF001
            jm._active[run_id] = research_jobs._ActiveJob(job=job, process=process)
        for _ in range(100):
            if jm.active_count() == 0:
                break
            time.sleep(0.02)
        time.sleep(0.1)
    finally:
        jm.shutdown()

    final_record = repo.get_research_run_record(run_id)
    assert final_record["status"] == "failed"
    assert final_record["error_code"] == "RESEARCH_WORKER_RESULT_NOT_PERSISTED"
    assert final_record["active_fingerprint"] is None


# ===========================================================================
# C. Output-root consistency (Fix 3)
# ===========================================================================


def test_agent_outputs_endpoint_honors_comqutor_output_dir(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from comqutor_alpha.api.main import create_app

    custom_root = tmp_path / "custom_output_dir"
    custom_root.mkdir()
    default_root = tmp_path / "outputs" / "runs"

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COMQUTOR_OUTPUT_DIR", str(custom_root))
    for var in ("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "COMQUTOR_CORS_ORIGINS"):
        monkeypatch.delenv(var, raising=False)

    run_id = "custom_output_dir_run"
    run_dir = custom_root / run_id
    run_dir.mkdir()
    (run_dir / "structured_agent_outputs.json").write_text(
        json.dumps(
            {
                "schema_version": "week1a.structured_agent_outputs.v2",
                "run_id": run_id,
                "ticker": "NVDA",
                "records": [],
            }
        ),
        encoding="utf-8",
    )

    # create_app(output_root=None) -- the app must resolve output_root via
    # COMQUTOR_OUTPUT_DIR, not silently fall back to "./outputs/runs".
    app = create_app(output_root=None)
    with TestClient(app) as client:
        response = client.get(f"/api/research/{run_id}/agent-outputs")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["run_id"] == run_id
    assert not default_root.exists()  # nothing was created/read under the default path
    serialized = json.dumps(body)
    assert str(custom_root) not in serialized
    assert str(tmp_path) not in serialized


def test_explicit_output_root_takes_precedence_over_comqutor_output_dir(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from comqutor_alpha.api.main import create_app

    env_root = tmp_path / "env_output_dir"
    explicit_root = tmp_path / "explicit_output_dir"
    env_root.mkdir()
    explicit_root.mkdir()
    monkeypatch.setenv("COMQUTOR_OUTPUT_DIR", str(env_root))

    run_id = "explicit_precedence_run"
    run_dir = explicit_root / run_id
    run_dir.mkdir()
    (run_dir / "structured_agent_outputs.json").write_text(
        json.dumps(
            {
                "schema_version": "week1a.structured_agent_outputs.v2",
                "run_id": run_id,
                "ticker": "NVDA",
                "records": [],
            }
        ),
        encoding="utf-8",
    )

    app = create_app(output_root=str(explicit_root))
    with TestClient(app) as client:
        response = client.get(f"/api/research/{run_id}/agent-outputs")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    # The env-configured directory was never touched for this run.
    assert not (env_root / run_id).exists()


def test_default_fallback_used_when_neither_explicit_nor_env_set(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from comqutor_alpha.api.main import create_app

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("COMQUTOR_OUTPUT_DIR", raising=False)

    app = create_app(output_root=None)
    with TestClient(app) as client:
        response = client.get("/api/research/totally-unknown-run/agent-outputs")

    assert response.status_code == 200
    assert response.json()["error_code"] == "RUN_NOT_FOUND"


def test_status_and_history_and_graph_and_conflicts_all_use_same_output_root(tmp_path, monkeypatch):
    """All read routes must resolve output_root the same way the POST/job
    manager path does -- a run created via POST must be visible to every
    GET route without any of them substituting a different default."""
    from fastapi.testclient import TestClient

    from comqutor_alpha.api.main import create_app

    monkeypatch.setenv("COMQUTOR_OUTPUT_DIR", str(tmp_path / "should_not_be_used"))
    app = create_app(output_root=str(tmp_path))
    with TestClient(app) as client:
        response = client.post(
            "/api/research",
            json={
                "ticker": "NVDA",
                "analysis_date": "2026-06-30",
                "offline_raw_agent_outputs": [{"agent": "news_agent", "raw_output": "consistency check"}],
            },
        )
        run_id = response.json()["run_id"]
        deadline = time.monotonic() + 10
        status_body = None
        while time.monotonic() < deadline:
            status_body = client.get(f"/api/research/{run_id}/status").json()
            if status_body["status"] in ("completed", "partial", "failed"):
                break
            time.sleep(0.05)
        assert status_body["status"] == "completed"

        agent_outputs = client.get(f"/api/research/{run_id}/agent-outputs").json()
        assert agent_outputs.get("error_code") != "RUN_NOT_FOUND"
        history = client.get("/api/research").json()
        assert any(item["run_id"] == run_id for item in history["items"])


# ===========================================================================
# D. Server config exception boundary (Fix 4)
# ===========================================================================


def test_value_error_from_config_builder_is_wrapped(monkeypatch):
    # Uses unittest.mock.patch as a context manager (reverted synchronously
    # on __exit__, inside this test's own body) rather than
    # monkeypatch.setattr on the *global* copy.deepcopy -- an autouse
    # fixture elsewhere in this suite (conftest.py's _isolate_config) also
    # calls copy.deepcopy during its own teardown, and depending on fixture
    # teardown order that can run before monkeypatch reverts a
    # function-scoped patch of a stdlib-wide function, corrupting an
    # unrelated fixture's teardown. Scoping the patch to a plain `with`
    # block sidesteps that ordering question entirely.
    from unittest.mock import patch

    from comqutor_alpha import server_execution

    monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "true")

    def raising_deepcopy(_value):
        raise ValueError("simulated native TradingAgents config error")

    with patch("copy.deepcopy", raising_deepcopy), pytest.raises(server_execution.ServerExecutionConfigError) as exc_info:
        server_execution.build_server_tradingagents_config()
    assert exc_info.value.reason_code == "REAL_RUN_CONFIG_INVALID"


def test_build_server_execution_context_maps_arbitrary_exception_safely(monkeypatch):
    from comqutor_alpha import server_execution

    monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "true")

    def raising_config_builder():
        raise TypeError("unexpected native TradingAgents type error")

    monkeypatch.setattr(server_execution, "build_server_tradingagents_config", raising_config_builder)
    ctx = server_execution.build_server_execution_context()
    assert ctx == {
        "enabled": True,
        "config": None,
        "execution_identity": None,
        "profile_id": None,
        "error": "REAL_RUN_CONFIG_INVALID",
    }


def test_readiness_response_503_on_native_config_exception(monkeypatch):
    from comqutor_alpha import server_execution
    from comqutor_alpha.api.routes_system import readiness_response

    monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "true")

    def raising_config_builder():
        raise ValueError("simulated native error")

    monkeypatch.setattr(server_execution, "build_server_tradingagents_config", raising_config_builder)

    class _FakeJobManager:
        def is_accepting(self):
            return True

    body, ok = readiness_response(job_manager=_FakeJobManager(), output_root=str(Path(tempfile.mkdtemp())))
    assert ok is False
    assert body["real_execution"] == "misconfigured"
    assert "ValueError" not in json.dumps(body)
    assert "Traceback" not in json.dumps(body)


def test_post_returns_503_before_claim_on_native_config_exception(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from comqutor_alpha import server_execution
    from comqutor_alpha.api.main import create_app
    from comqutor_alpha.storage.db.repository import build_write_repository_from_env

    monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "true")

    def raising_config_builder():
        raise ValueError("simulated native error")

    monkeypatch.setattr(server_execution, "build_server_tradingagents_config", raising_config_builder)

    app = create_app(output_root=str(tmp_path))
    with TestClient(app) as client:
        response = client.post("/api/research", json={"ticker": "NVDA"})

    assert response.status_code == 503
    body = response.json()
    assert body["error_code"] == "REAL_RUN_CONFIG_INVALID"
    serialized = json.dumps(body)
    assert "ValueError" not in serialized
    assert "Traceback" not in serialized

    repo = build_write_repository_from_env(str(tmp_path))
    assert repo.list_research_run_records(limit=50) == []


def test_fresh_subprocess_native_env_error_maps_to_real_run_config_invalid():
    """Genuinely fresh Python process (not just monkeypatching within this
    interpreter): tradingagents.default_config's own TRADINGAGENTS_* env-var
    parsing runs exactly once, at first import, so this is the only way to
    exercise a real import-time failure rather than one manufactured after
    the fact."""
    script = (
        "import json\n"
        "import comqutor_alpha.server_execution as se\n"
        "ctx = se.build_server_execution_context()\n"
        "print(json.dumps({\n"
        "    'enabled': ctx['enabled'],\n"
        "    'error': ctx['error'],\n"
        "    'config_is_none': ctx['config'] is None,\n"
        "    'execution_identity_is_none': ctx['execution_identity'] is None,\n"
        "}))\n"
    )
    env = dict(os.environ)
    env["COMQUTOR_REAL_TRADINGAGENTS_ENABLED"] = "true"
    env["TRADINGAGENTS_MAX_DEBATE_ROUNDS"] = "not-an-integer"

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr
    assert "not-an-integer" not in result.stdout
    assert "not-an-integer" not in result.stderr

    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["enabled"] is True
    assert payload["error"] == "REAL_RUN_CONFIG_INVALID"
    assert payload["config_is_none"] is True
    assert payload["execution_identity_is_none"] is True


# ===========================================================================
# D2. Server config DEBUG non-leakage (this patch's Fix 2)
# ===========================================================================


def test_debug_log_does_not_leak_exception_content_from_config_builder(monkeypatch, caplog):
    import logging as logging_module
    from unittest.mock import patch

    from comqutor_alpha import server_execution

    monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "true")
    secret_marker = "super-secret-config-marker"

    def raising_deepcopy(_value):
        raise ValueError(
            f"Invalid value for TRADINGAGENTS_MAX_DEBATE_ROUNDS: invalid literal for int() "
            f"with base 10: '{secret_marker}'"
        )

    caplog.set_level(logging_module.DEBUG, logger="comqutor_alpha.server_execution")
    with (
        patch("copy.deepcopy", raising_deepcopy),
        pytest.raises(server_execution.ServerExecutionConfigError),
    ):
        server_execution.build_server_tradingagents_config()

    # The triggering ValueError is wrapped into ResearchProfileError before
    # this module logs it -- only that bare wrapper type name may appear.
    assert "ResearchProfileError" in caplog.text
    assert secret_marker not in caplog.text
    assert "TRADINGAGENTS_MAX_DEBATE_ROUNDS" not in caplog.text
    assert "Traceback" not in caplog.text
    assert 'File "' not in caplog.text
    assert "invalid literal for int" not in caplog.text


def test_debug_log_does_not_leak_exception_content_from_execution_context(monkeypatch, caplog):
    import logging as logging_module

    from comqutor_alpha import server_execution

    monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "true")
    secret_marker = "second-secret-marker"

    def raising_config_builder():
        raise RuntimeError(f"native config failure mentioning {secret_marker}")

    monkeypatch.setattr(server_execution, "build_server_tradingagents_config", raising_config_builder)

    caplog.set_level(logging_module.DEBUG, logger="comqutor_alpha.server_execution")
    ctx = server_execution.build_server_execution_context()

    assert ctx["error"] == "REAL_RUN_CONFIG_INVALID"
    assert ctx["config"] is None
    assert secret_marker not in caplog.text
    assert "Traceback" not in caplog.text
    assert 'File "' not in caplog.text
    assert "RuntimeError" in caplog.text


def test_fresh_subprocess_debug_logging_does_not_leak_env_or_traceback():
    """Same fresh-process rationale as the test above, but this time the
    subprocess explicitly enables DEBUG logging (``logging.basicConfig
    (level=logging.DEBUG)``) before calling
    ``build_server_execution_context()`` -- proving the non-leakage holds
    even when an operator has turned on the most verbose logging level this
    module supports, not just at the WARNING default."""
    script = (
        "import json\n"
        "import logging\n"
        "logging.basicConfig(level=logging.DEBUG)\n"
        "import comqutor_alpha.server_execution as se\n"
        "ctx = se.build_server_execution_context()\n"
        "print(json.dumps({'error': ctx['error'], 'config_is_none': ctx['config'] is None}))\n"
    )
    env = dict(os.environ)
    env["COMQUTOR_REAL_TRADINGAGENTS_ENABLED"] = "true"
    env["TRADINGAGENTS_MAX_DEBATE_ROUNDS"] = "debug-secret-marker"

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0
    combined_output = result.stdout + result.stderr
    assert "debug-secret-marker" not in combined_output
    assert "TRADINGAGENTS_MAX_DEBATE_ROUNDS" not in combined_output
    assert "Traceback" not in combined_output
    # A bare exception type name is explicitly allowed to appear -- the
    # import-time ValueError is wrapped into ResearchProfileError first.
    assert "ResearchProfileError" in combined_output

    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["error"] == "REAL_RUN_CONFIG_INVALID"
    assert payload["config_is_none"] is True


def test_keyboard_interrupt_is_not_swallowed_by_config_builder_boundary(monkeypatch):
    from unittest.mock import patch

    from comqutor_alpha import server_execution

    monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "true")

    def raising_deepcopy(_value):
        raise KeyboardInterrupt()

    with patch("copy.deepcopy", raising_deepcopy), pytest.raises(KeyboardInterrupt):
        server_execution.build_server_tradingagents_config()


def test_system_exit_is_not_swallowed_by_execution_context_boundary(monkeypatch):
    from comqutor_alpha import server_execution

    monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "true")

    def raising_config_builder():
        raise SystemExit(1)

    monkeypatch.setattr(server_execution, "build_server_tradingagents_config", raising_config_builder)
    with pytest.raises(SystemExit):
        server_execution.build_server_execution_context()


# ===========================================================================
# E. Strict CORS validation (Fix 5)
# ===========================================================================


def test_cors_unset_is_none(monkeypatch):
    from comqutor_alpha.api.main import _resolve_cors_origins

    monkeypatch.delenv("COMQUTOR_CORS_ORIGINS", raising=False)
    assert _resolve_cors_origins() is None


def test_cors_blank_value_is_none(monkeypatch):
    from comqutor_alpha.api.main import _resolve_cors_origins

    monkeypatch.setenv("COMQUTOR_CORS_ORIGINS", "   ")
    assert _resolve_cors_origins() is None


def test_cors_single_legal_origin(monkeypatch):
    from comqutor_alpha.api.main import _resolve_cors_origins

    monkeypatch.setenv("COMQUTOR_CORS_ORIGINS", "http://a.example.com")
    assert _resolve_cors_origins() == ["http://a.example.com"]


def test_cors_multiple_legal_origins_in_order(monkeypatch):
    from comqutor_alpha.api.main import _resolve_cors_origins

    monkeypatch.setenv("COMQUTOR_CORS_ORIGINS", "http://a.example.com,http://b.example.com")
    assert _resolve_cors_origins() == ["http://a.example.com", "http://b.example.com"]


def test_cors_duplicate_origin_deduplicated(monkeypatch):
    from comqutor_alpha.api.main import _resolve_cors_origins

    monkeypatch.setenv(
        "COMQUTOR_CORS_ORIGINS", "http://a.example.com,http://b.example.com,http://a.example.com"
    )
    assert _resolve_cors_origins() == ["http://a.example.com", "http://b.example.com"]


@pytest.mark.parametrize(
    "value",
    [
        "http://a.example.com,",
        ",http://a.example.com",
        "http://a.example.com,,http://b.example.com",
        "*",
        "http://a.example.com,*,http://b.example.com",
    ],
)
def test_cors_illegal_configurations_are_rejected(monkeypatch, value):
    from comqutor_alpha.api.main import ApiConfigurationError, _resolve_cors_origins

    monkeypatch.setenv("COMQUTOR_CORS_ORIGINS", value)
    with pytest.raises(ApiConfigurationError) as exc_info:
        _resolve_cors_origins()
    assert exc_info.value.reason_code == "INVALID_CORS_ORIGINS"


def test_create_app_does_not_build_partial_app_on_invalid_cors(tmp_path, monkeypatch):
    from comqutor_alpha.api.main import ApiConfigurationError, create_app

    monkeypatch.setenv("COMQUTOR_CORS_ORIGINS", "http://a.example.com,*")
    with pytest.raises(ApiConfigurationError):
        create_app(output_root=str(tmp_path))


def test_server_main_exits_safely_without_traceback_on_invalid_cors(monkeypatch):
    import importlib
    import types

    import comqutor_alpha.api.main as main_module
    import comqutor_alpha.api.server as server_module

    monkeypatch.setitem(sys.modules, "uvicorn", types.ModuleType("uvicorn"))
    monkeypatch.setenv("COMQUTOR_CORS_ORIGINS", "http://a.example.com,,http://b.example.com")
    importlib.reload(main_module)
    try:
        with pytest.raises(SystemExit) as exc_info:
            server_module.main()
        message = str(exc_info.value)
        assert message == "COMQUTOR_CORS_ORIGINS is invalid."
        assert "Traceback" not in message
        assert "http://a.example.com" not in message
    finally:
        monkeypatch.delenv("COMQUTOR_CORS_ORIGINS", raising=False)
        importlib.reload(main_module)
