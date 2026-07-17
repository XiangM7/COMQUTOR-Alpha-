"""W5.1B: Background research job architecture.

The synchronous ``research_lifecycle.submit_research_request`` stays exactly
as it was for direct Python callers (see its docstring). This module adds
the *background* equivalent used by the async HTTP POST route: claim a run
exactly the same way, then hand the actual (potentially slow, potentially
real-provider) execution off to a bounded pool of ``multiprocessing`` worker
processes -- never the request thread, never a plain (unkillable) Python
thread.

Process isolation, not threads, because a real TradingAgents run must be
forcibly terminable (timeout, shutdown) without corrupting interpreter
state shared with the request-serving process. The ``spawn`` start method
is used explicitly (not ``fork``) so a worker never inherits an open
database connection, a partially-initialized FastAPI app, or any other
parent-process file descriptor -- see requirement #13 in the task spec.

Nothing in this module talks to a real LLM, a real data provider, or real
TradingAgents directly; it only supervises whatever ``execute_claimed_
research_run`` (research_lifecycle.py) is configured to call, exactly like
the synchronous path.
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from comqutor_alpha.research_lifecycle import mark_research_run_failed_consistently
from comqutor_alpha.storage.db.repository import build_write_repository_from_env

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bounded, safe-fail environment configuration
# ---------------------------------------------------------------------------

DEFAULT_MAX_WORKERS = 1
DEFAULT_QUEUE_CAPACITY = 8
DEFAULT_TIMEOUT_SECONDS = 1800
DEFAULT_SHUTDOWN_GRACE_SECONDS = 10

_MAX_WORKERS_BOUNDS = (1, 4)
_QUEUE_CAPACITY_BOUNDS = (0, 100)
_TIMEOUT_SECONDS_BOUNDS = (30, 14400)
_SHUTDOWN_GRACE_SECONDS_BOUNDS = (0, 60)


class JobManagerConfigError(Exception):
    """Safe job-manager configuration error: a stable reason code only."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def _parse_bounded_int(env_var: str, default: int, bounds: tuple[int, int]) -> int:
    """Never silently accepts an out-of-range or malformed value -- a typo'd
    or dangerously large operator override must fail loudly (raise) rather
    than quietly running with an unbounded/unsafe worker count, queue
    capacity, or timeout."""
    minimum, maximum = bounds
    raw = os.environ.get(env_var, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise JobManagerConfigError(f"INVALID_{env_var}") from exc
    if not (minimum <= value <= maximum):
        raise JobManagerConfigError(f"INVALID_{env_var}")
    return value


def resolve_job_manager_settings() -> dict[str, int]:
    """Raises ``JobManagerConfigError`` if any env override is malformed or
    out of its safe range (see the ``_BOUNDS`` constants above)."""
    return {
        "max_workers": _parse_bounded_int("COMQUTOR_JOB_MAX_WORKERS", DEFAULT_MAX_WORKERS, _MAX_WORKERS_BOUNDS),
        "queue_capacity": _parse_bounded_int(
            "COMQUTOR_JOB_QUEUE_CAPACITY", DEFAULT_QUEUE_CAPACITY, _QUEUE_CAPACITY_BOUNDS
        ),
        "timeout_seconds": _parse_bounded_int(
            "COMQUTOR_JOB_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS, _TIMEOUT_SECONDS_BOUNDS
        ),
        "shutdown_grace_seconds": _parse_bounded_int(
            "COMQUTOR_JOB_SHUTDOWN_GRACE_SECONDS", DEFAULT_SHUTDOWN_GRACE_SECONDS, _SHUTDOWN_GRACE_SECONDS_BOUNDS
        ),
    }


# ---------------------------------------------------------------------------
# Child-process entrypoint (module-level, picklable -- multiprocessing
# "spawn" requires this; a bound method or closure cannot be pickled).
# ---------------------------------------------------------------------------


def _job_worker_entrypoint(
    run_id: str,
    execution_payload: dict[str, Any],
    output_root: str,
    disposition: str,
    ticker: str,
) -> None:
    """Runs in the child process. Receives only plain, picklable data (a
    run_id string, a plain dict payload, plain strings) -- never an
    Engine/Connection/Repository object from the parent. Rebuilds its own
    write repository from the server environment, then drives the run
    through the exact same ``execute_claimed_research_run`` the synchronous
    path uses, so terminal-state writes (completed/partial/failed) go
    through one single, already-tested code path regardless of which
    process calls it.

    Raises (crashing the process with a non-zero exit code) if the
    repository itself cannot be built -- the parent supervisor's exitcode
    check then marks the run failed (``RESEARCH_WORKER_CRASHED``) exactly
    as it would for any other worker crash.
    """
    from comqutor_alpha.research_lifecycle import execute_claimed_research_run

    repository = build_write_repository_from_env(output_root)
    execute_claimed_research_run(
        run_id,
        execution_payload,
        output_root=output_root,
        graph_repository=repository,
        disposition=disposition,
        ticker=ticker,
    )


@dataclass
class _Job:
    run_id: str
    execution_payload: dict[str, Any]
    disposition: str
    ticker: str
    output_root: str


@dataclass
class _ActiveJob:
    job: _Job
    process: Any
    started_at: float = field(default_factory=time.monotonic)


@dataclass
class _StartingJob:
    """A job that has left ``_pending`` but has not yet been registered in
    ``_active`` -- i.e. its process object may not exist yet, or exists but
    ``process.start()`` has not returned. Registered in ``_starting`` under
    the lock *before* ``process.start()`` is ever called, so a job is always
    a member of exactly one of pending/starting/active/terminal -- there is
    no window where ``shutdown()`` can observe neither. Only the supervisor
    thread itself ever calls ``.start()``/``.terminate()`` on ``process``
    (see ``_start_pending``) -- concurrently poking a ``multiprocessing.
    Process`` whose ``.start()`` call is still in flight from a different
    thread is not safe, so ``shutdown()`` never touches this object's
    process directly; it only waits for the supervisor thread to resolve
    it (bounded by joining that thread)."""

    job: _Job
    process: Any = None


class JobManager:
    """Bounded local-process supervisor for background research runs.

    Importing this module (or constructing a ``JobManager``) never starts a
    worker or a supervisor thread -- only :meth:`start` does. Safe to
    construct at module scope / in tests without any background activity
    beginning.
    """

    def __init__(
        self,
        *,
        max_workers: int,
        queue_capacity: int,
        timeout_seconds: int,
        shutdown_grace_seconds: int,
        output_root: str | None = "outputs/runs",
        mp_context: Any = None,
        process_factory: Callable[..., Any] | None = None,
        worker_entrypoint: Callable[..., None] | None = None,
        repository_factory: Callable[[], Any] | None = None,
        poll_interval: float = 0.05,
    ) -> None:
        self._max_workers = max_workers
        self._queue_capacity = queue_capacity
        self._timeout_seconds = timeout_seconds
        self._shutdown_grace_seconds = shutdown_grace_seconds
        self._output_root = output_root
        self._mp_context = mp_context or multiprocessing.get_context("spawn")
        # Test seam: a fake process factory lets tests exercise crash/
        # timeout/start-failure handling deterministically and fast, without
        # spawning a real OS process for every scenario. Production always
        # uses the real spawn-context Process.
        self._process_factory = process_factory or self._mp_context.Process
        self._worker_entrypoint = worker_entrypoint or _job_worker_entrypoint
        self._repository_factory = repository_factory or (lambda: build_write_repository_from_env(self._output_root))
        self._poll_interval = poll_interval

        self._lock = threading.RLock()
        self._pending: deque[_Job] = deque()
        # Jobs that have left _pending but are not yet registered in
        # _active -- see _StartingJob's docstring. Every job is always a
        # member of exactly one of _pending/_starting/_active (or has
        # already been resolved to a terminal DB status and removed from
        # all three) -- there is no unmanaged in-between state.
        self._starting: dict[str, _StartingJob] = {}
        self._active: dict[str, _ActiveJob] = {}
        self._accepting = False
        self._stopped = threading.Event()
        self._wake = threading.Event()
        self._supervisor_thread: threading.Thread | None = None
        self._repository: Any = None
        # One-way latch: once shutdown() has run (even if concurrent calls
        # race to enter it), this JobManager instance is permanently done --
        # start() must never resurrect it (see start()/shutdown()).
        self._ever_shutdown = False

    # -- properties -----------------------------------------------------

    @property
    def max_workers(self) -> int:
        return self._max_workers

    @property
    def queue_capacity(self) -> int:
        return self._queue_capacity

    def is_accepting(self) -> bool:
        with self._lock:
            return self._accepting and not self._stopped.is_set()

    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    def starting_count(self) -> int:
        with self._lock:
            return len(self._starting)

    def active_count(self) -> int:
        with self._lock:
            return len(self._active)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "max_workers": self._max_workers,
                "queue_capacity": self._queue_capacity,
                "active": len(self._active),
                "starting": len(self._starting),
                "pending": len(self._pending),
                "accepting": self._accepting and not self._stopped.is_set(),
            }

    def _get_repository(self) -> Any:
        if self._repository is None:
            self._repository = self._repository_factory()
        return self._repository

    # -- lifecycle --------------------------------------------------------

    def start(self) -> None:
        """Begins accepting jobs and starts the supervisor thread. Never
        called at import time -- only by the API lifespan startup hook.

        Raises ``JobManagerConfigError("JOB_MANAGER_ALREADY_SHUT_DOWN")`` if
        ``shutdown()`` has already run on this instance -- a JobManager is
        one-shot for the lifetime of one API process run; it must never
        silently ``self._stopped.clear()`` and resurrect a supervisor loop
        that has already torn down every worker and released every
        ``active_fingerprint``. Build a fresh ``JobManager`` instead (the
        normal API lifespan already does exactly one ``start()``/one
        ``shutdown()`` per process).
        """
        with self._lock:
            if self._ever_shutdown:
                raise JobManagerConfigError("JOB_MANAGER_ALREADY_SHUT_DOWN")
            self._accepting = True
        self._stopped.clear()
        self._supervisor_thread = threading.Thread(
            target=self._supervise_loop, name="comqutor-job-supervisor", daemon=True
        )
        self._supervisor_thread.start()

    def submit(
        self,
        run_id: str,
        execution_payload: Mapping[str, Any],
        *,
        disposition: str,
        ticker: str,
        output_root: str | None = None,
    ) -> bool:
        """Enqueues an already-claimed run for background execution.

        Returns ``False`` (never raises) if the manager is not currently
        accepting jobs, or if the system is already at total capacity
        (``max_workers + queue_capacity`` -- i.e. every worker slot busy and
        the waiting queue full) -- callers must then fail the
        already-claimed row (``RESEARCH_QUEUE_FULL``/
        ``JOB_MANAGER_UNAVAILABLE``) and release its ``active_fingerprint``
        themselves (see ``enqueue_research_request`` below); this method
        never touches the database.

        ``queue_capacity=0`` means "no *waiting* room" -- it does not mean
        "never run anything": a request still starts immediately whenever a
        worker slot is free. Capacity is therefore checked against
        ``active + pending`` combined, not ``pending`` alone.
        """
        job = _Job(
            run_id=run_id,
            execution_payload=dict(execution_payload),
            disposition=disposition,
            ticker=ticker,
            output_root=output_root or self._output_root,
        )
        with self._lock:
            if not self._accepting or self._stopped.is_set():
                return False
            total_capacity = self._max_workers + self._queue_capacity
            in_flight = len(self._active) + len(self._starting) + len(self._pending)
            if in_flight >= total_capacity:
                return False
            self._pending.append(job)
        self._wake.set()
        return True

    def shutdown(self) -> None:
        """Stops accepting new jobs, waits up to ``shutdown_grace_seconds``
        for in-flight jobs to finish naturally, then forcibly terminates
        anything still running and fails every remaining active/pending/
        starting job with ``SERVER_SHUTDOWN`` -- never leaves a zombie
        process or a row permanently stuck holding ``active_fingerprint``.

        Idempotent and a one-way latch: the *first* call does the full
        teardown described above; every subsequent call (this instance has
        already been shut down) returns immediately without touching
        anything -- never re-terminates a process, never re-marks a
        terminal row, never raises. ``start()`` on this same instance after
        this point always raises ``JobManagerConfigError`` rather than
        silently resurrecting a supervisor loop (see ``start()``).

        ``self._stopped`` is set *early* (before waiting out the grace
        period) so a concurrently in-flight ``_start_pending`` call --
        specifically one whose ``process.start()`` is still blocked when
        shutdown begins -- observes it the moment ``.start()`` returns (see
        ``_start_pending``) and self-terminates/self-marks-failed rather
        than ever registering the job as active after shutdown began. This
        closes the escape window entirely: from the instant a job leaves
        ``_pending``, it is tracked in ``_starting`` until the supervisor
        thread itself resolves it to either ``_active`` or a terminal DB
        write -- there is no point at which ``shutdown()`` can observe a
        job in neither collection while its process is still running.

        Critically, this method does **not** return until the supervisor
        thread has actually exited: joining it uses no timeout at all
        (an unbounded, polling ``while is_alive(): join(0.5)`` loop rather
        than one fixed ``join(timeout=...)`` call whose expiry was
        previously treated as "close enough"). A supervisor thread blocked
        inside a job's ``process.start()`` call keeps this method waiting
        for exactly as long as that call takes to return -- there is no
        point at which ``shutdown()`` gives up and returns while
        ``_starting``/the supervisor thread might still be live, which is
        what previously let a `queued`/`running` row and its worker process
        outlive a completed-looking ``shutdown()`` call.
        """
        with self._lock:
            if self._ever_shutdown:
                return
            self._ever_shutdown = True
            self._accepting = False
        self._stopped.set()
        self._wake.set()

        deadline = time.monotonic() + self._shutdown_grace_seconds
        while time.monotonic() < deadline:
            self._reap_finished()
            with self._lock:
                quiescent = not self._active and not self._starting
            if quiescent:
                break
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))

        with self._lock:
            remaining_active = list(self._active.items())
            self._active.clear()
            remaining_pending = list(self._pending)
            self._pending.clear()
            # remaining_starting deliberately NOT cleared/touched here --
            # only the supervisor thread may call .start()/.terminate() on
            # a process whose .start() it itself issued and may still be in
            # flight (see _StartingJob's docstring). The unbounded join
            # below is what guarantees these get fully resolved before this
            # method returns.

        for run_id, active_job in remaining_active:
            self._terminate_process(active_job.process)
            self._mark_failed_if_active(run_id, "SERVER_SHUTDOWN", "Server is shutting down.")
        for job in remaining_pending:
            self._mark_failed_if_active(job.run_id, "SERVER_SHUTDOWN", "Server is shutting down.")

        self._wake.set()

        # Unbounded wait for the supervisor thread to actually exit. No
        # fixed timeout is ever "accepted" as good enough -- _supervise_loop
        # only exits its `while not self._stopped.is_set()` loop after
        # _start_pending() returns, and _start_pending() never returns
        # mid-job: it always either resolves a popped job to _active or to
        # a terminal DB write (see its post-start()/except-Exception
        # handling) before its own `while True:` loop can advance again.
        # Polling in short join() slices (rather than one blocking
        # join()) keeps this responsive/interruptible without ever treating
        # "still running" as a reason to give up and return.
        if self._supervisor_thread is not None:
            while self._supervisor_thread.is_alive():
                self._supervisor_thread.join(timeout=0.5)

        # Final sweep: the supervisor thread has, by now, fully exited --
        # which (per _supervise_loop/_start_pending, see above) guarantees
        # _starting is already empty and every job it was tracking has been
        # resolved to either _active (if it raced shutdown and lost -- see
        # _start_pending's post-start() handling, which self-terminates and
        # self-marks-failed in that case, but may not have updated this
        # manager's _active dict before the process was already stopped) or
        # a terminal DB write. This sweep exists only to reap whatever the
        # supervisor thread deposited into _active in that exact race
        # window; it is a harmless no-op otherwise.
        self._reap_finished()
        with self._lock:
            leftover_active = list(self._active.items())
            self._active.clear()
        for run_id, active_job in leftover_active:
            self._terminate_process(active_job.process)
            self._mark_failed_if_active(run_id, "SERVER_SHUTDOWN", "Server is shutting down.")

    # -- supervisor loop --------------------------------------------------

    def _supervise_loop(self) -> None:
        while not self._stopped.is_set():
            self._reap_finished()
            self._reap_timeouts()
            self._start_pending()
            self._wake.wait(self._poll_interval)
            self._wake.clear()

    def _reap_finished(self) -> None:
        with self._lock:
            items = list(self._active.items())
        for run_id, active_job in items:
            process = active_job.process
            if process.is_alive():
                continue
            with self._lock:
                self._active.pop(run_id, None)
            exitcode = process.exitcode
            if exitcode != 0:
                # Worker crashed (unhandled exception, killed by an external
                # signal, etc.) before writing its own terminal state.
                # Conditional -- a no-op if the worker actually did finish
                # writing completed/partial/failed just before dying.
                self._mark_failed_if_active(
                    run_id, "RESEARCH_WORKER_CRASHED", f"Worker process exited with code {exitcode}."
                )
            else:
                # exitcode == 0 does NOT guarantee the worker's own terminal
                # DB write (inside execute_claimed_research_run) actually
                # landed -- e.g. a transient DB hiccup at the very end is
                # suppressed there (_suppress_lifecycle_errors) precisely so
                # the pipeline's real outcome is still returned/logged
                # rather than crashing the worker, but that means a clean
                # exit is never sufficient evidence the row reached a
                # terminal status. This conditional update
                # (WHERE status IN (queued, running)) is a safe no-op if the
                # worker's write already landed, and a safe failure
                # (fingerprint released) if it did not -- never a blind
                # SELECT-then-overwrite, never a permanently stuck
                # queued/running row.
                self._mark_failed_if_active(
                    run_id,
                    "RESEARCH_WORKER_RESULT_NOT_PERSISTED",
                    "Worker exited without persisting a terminal research status.",
                )

    def _reap_timeouts(self) -> None:
        now = time.monotonic()
        with self._lock:
            items = list(self._active.items())
        for run_id, active_job in items:
            if now - active_job.started_at < self._timeout_seconds:
                continue
            with self._lock:
                # Re-check under the lock: the worker may have finished
                # (and been reaped) between the snapshot above and here.
                if run_id not in self._active:
                    continue
                self._active.pop(run_id, None)
            self._terminate_process(active_job.process)
            # Conditional update: if the worker actually finished writing a
            # terminal state in the race window right before termination,
            # this is a safe no-op (WHERE status IN (queued, running)).
            self._mark_failed_if_active(
                run_id, "RESEARCH_TIMEOUT", "Research run exceeded the configured timeout."
            )

    def _start_pending(self) -> None:
        while True:
            with self._lock:
                if not self._accepting or self._stopped.is_set():
                    return
                if len(self._active) + len(self._starting) >= self._max_workers or not self._pending:
                    return
                job = self._pending.popleft()
                # Registered as "starting" immediately, still under the
                # lock, before process construction/`.start()` is ever
                # attempted -- from this instant the job is always
                # findable (in _starting) even though it is not active yet,
                # closing the pending-popped-but-nowhere-tracked window
                # that previously let shutdown() race past it.
                entry = _StartingJob(job=job)
                self._starting[job.run_id] = entry

            try:
                process = self._process_factory(
                    target=self._worker_entrypoint,
                    args=(job.run_id, job.execution_payload, job.output_root, job.disposition, job.ticker),
                )
                with self._lock:
                    # Attach the process handle to the still-tracked entry
                    # (if shutdown() has not already removed it -- it never
                    # does concurrently, per the docstring above, but this
                    # stays defensive/idempotent either way) so it is
                    # visible for diagnostics even before .start() returns.
                    if job.run_id in self._starting:
                        self._starting[job.run_id].process = process
                process.start()
            except Exception:
                with self._lock:
                    self._starting.pop(job.run_id, None)
                    stopped = self._stopped.is_set()
                if stopped:
                    self._mark_failed_if_active(job.run_id, "SERVER_SHUTDOWN", "Server is shutting down.")
                else:
                    logger.warning("worker process failed to start (run_id=%s)", job.run_id)
                    self._mark_failed_if_active(
                        job.run_id, "RESEARCH_WORKER_START_FAILED", "Worker process failed to start."
                    )
                continue

            with self._lock:
                self._starting.pop(job.run_id, None)
                stopped = self._stopped.is_set()
                if not stopped:
                    self._active[job.run_id] = _ActiveJob(job=job, process=process, started_at=time.monotonic())
            if stopped:
                # shutdown() began (and, per its own contract, is waiting
                # for this thread to resolve every starting job) while this
                # process.start() call was still in flight -- the process
                # did start, so it must be terminated now rather than ever
                # registered as active/left running unmanaged.
                self._terminate_process(process)
                self._mark_failed_if_active(job.run_id, "SERVER_SHUTDOWN", "Server is shutting down.")

    @staticmethod
    def _terminate_process(process: Any) -> None:
        if not process.is_alive():
            return
        process.terminate()
        process.join(timeout=5)
        if process.is_alive():
            kill = getattr(process, "kill", None)
            if kill is not None:
                kill()
            process.join(timeout=5)

    def _mark_failed_if_active(self, run_id: str, error_code: str, error_message: str) -> None:
        try:
            mark_research_run_failed_consistently(
                self._get_repository(),
                run_id,
                error_code=error_code,
                error_message=error_message,
            )
        except Exception:
            logger.warning(
                "failed to record job-manager outcome (run_id=%s, error_code=%s)", run_id, error_code
            )


def build_job_manager_from_env(output_root: str | None = "outputs/runs") -> JobManager:
    """Raises ``JobManagerConfigError`` if any ``COMQUTOR_JOB_*`` override is
    malformed/out-of-range -- callers (the API lifespan startup hook) must
    treat that as "job manager unavailable" (readiness 503), never silently
    fall back to a dangerous default."""
    settings = resolve_job_manager_settings()
    return JobManager(
        max_workers=settings["max_workers"],
        queue_capacity=settings["queue_capacity"],
        timeout_seconds=settings["timeout_seconds"],
        shutdown_grace_seconds=settings["shutdown_grace_seconds"],
        output_root=output_root,
    )


# ---------------------------------------------------------------------------
# Startup reconciliation
# ---------------------------------------------------------------------------


def reconcile_orphaned_runs_on_startup(graph_repository: Any) -> list[str]:
    """Local single-instance semantics: a ``queued``/``running`` row left
    over from a previous server process (crash, ``kill -9``, host reboot)
    can never be safely resumed in place -- resuming could silently re-run
    (and re-bill) a real TradingAgents call the operator never asked for
    again. Every such orphan is marked ``failed`` (``SERVER_RESTARTED``) and
    its ``active_fingerprint`` released, so a fresh, identical request is
    free to be claimed again. Never re-executes anything itself. Returns
    the list of run_ids reconciled.
    """
    orphans = graph_repository.list_active_research_run_records()
    reconciled = []
    restart_message = "The research run was interrupted by a server restart."
    for row in orphans:
        try:
            updated = mark_research_run_failed_consistently(
                graph_repository,
                row["run_id"],
                error_code="SERVER_RESTARTED",
                error_message=restart_message,
            )
        except Exception:
            logger.warning(
                "startup reconciliation could not update run (run_id=%s)", row["run_id"]
            )
        else:
            if updated:
                reconciled.append(row["run_id"])
    return reconciled


# ---------------------------------------------------------------------------
# Background submission (the async-HTTP-POST equivalent of
# research_lifecycle.submit_research_request)
# ---------------------------------------------------------------------------


def enqueue_research_request(
    payload: Mapping[str, Any] | None,
    *,
    output_root: str | None = "outputs/runs",
    graph_repository: Any = None,
    job_manager: JobManager | None,
) -> dict[str, Any]:
    """Claim (exactly like ``submit_research_request``), then hand off
    execution to ``job_manager`` instead of running it inline. Never
    duplicates the fingerprint/claim/real-mode-gate logic -- delegates
    entirely to ``research_lifecycle.prepare_research_submission``.

    Any reuse disposition (in-flight, or any terminal row) is returned
    immediately, exactly as the synchronous path would -- never enqueued.
    Only a freshly claimed (``created``/``force_refreshed``) row is ever
    submitted to the job manager.
    """
    from comqutor_alpha.research_lifecycle import prepare_research_submission

    prepared = prepare_research_submission(
        payload, output_root=output_root, graph_repository=graph_repository
    )
    if "response" in prepared:
        return prepared["response"]

    claim = prepared["claim"]
    run_id = claim["run_id"]
    disposition = claim["disposition"]
    ticker = prepared["ticker"]
    repository = prepared["graph_repository"]

    # Create the progress row the moment the run is claimed, so the very
    # first status poll after a 202 already has real telemetry (queued/8%).
    # Best-effort: a telemetry failure never blocks the submission itself.
    try:
        from comqutor_alpha.research_progress import ResearchProgressReporter

        ResearchProgressReporter(
            repository,
            run_id,
            profile_id=str(prepared.get("profile_id") or ""),
            selected_analysts=prepared["execution_payload"].get("selected_analysts"),
        ).initialize()
    except Exception as exc:
        logger.warning(
            "research progress initialization failed (run_id=%s, exc_type=%s)",
            run_id,
            type(exc).__name__,
        )

    if job_manager is None or not job_manager.is_accepting():
        mark_research_run_failed_consistently(
            repository,
            run_id,
            error_code="JOB_MANAGER_UNAVAILABLE",
            error_message="Background job manager is not available.",
        )
        return {
            "run_id": run_id,
            "ticker": ticker,
            "status": "failed",
            "error_code": "JOB_MANAGER_UNAVAILABLE",
            "message": "Background job manager is not available.",
            "run_status": "failed",
            "cache_disposition": disposition,
        }

    accepted = job_manager.submit(
        run_id, prepared["execution_payload"], disposition=disposition, ticker=ticker, output_root=output_root
    )
    if not accepted:
        # Queue is at capacity (or the manager stopped accepting between the
        # is_accepting() check above and this call) -- the row must never
        # be left dangling as "queued forever" holding active_fingerprint.
        mark_research_run_failed_consistently(
            repository,
            run_id,
            error_code="RESEARCH_QUEUE_FULL",
            error_message="The research job queue is full.",
        )
        return {
            "run_id": run_id,
            "ticker": ticker,
            "status": "failed",
            "error_code": "RESEARCH_QUEUE_FULL",
            "message": "The research job queue is full.",
            "run_status": "failed",
            "cache_disposition": disposition,
        }

    return {
        "run_id": run_id,
        "ticker": ticker,
        "status": "queued",
        "run_status": "queued",
        "stage": "accepted",
        "cache_disposition": disposition,
    }


__all__ = [
    "DEFAULT_MAX_WORKERS",
    "DEFAULT_QUEUE_CAPACITY",
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_SHUTDOWN_GRACE_SECONDS",
    "JobManagerConfigError",
    "resolve_job_manager_settings",
    "JobManager",
    "build_job_manager_from_env",
    "reconcile_orphaned_runs_on_startup",
    "enqueue_research_request",
]
