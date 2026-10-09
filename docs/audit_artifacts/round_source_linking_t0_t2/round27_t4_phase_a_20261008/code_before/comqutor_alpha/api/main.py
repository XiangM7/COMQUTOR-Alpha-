"""Optional FastAPI app for COMQUTOR Week 1-5 API routes.

``create_app()`` builds a fresh FastAPI application with all routers,
a FastAPI ``lifespan`` context (background job manager startup/
reconciliation/shutdown -- see ``comqutor_alpha.research_jobs``), and
optional CORS middleware (see ``_resolve_cors_origins``). Importing this
module -- or even calling ``create_app()`` -- never starts uvicorn, a
background worker process, or startup reconciliation: those only run when
an ASGI server (or a ``TestClient`` used as a context manager) actually
drives the app's ``lifespan``.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class ApiConfigurationError(Exception):
    """Safe API-configuration error: a stable reason code only. Defined
    independently of the FastAPI import below (it carries no dependency on
    FastAPI itself) so it is always importable/catchable regardless of
    whether the ``api`` optional dependency group is installed."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def _resolve_cors_origins() -> list[str] | None:
    """``COMQUTOR_CORS_ORIGINS``: a comma-separated exact-origin allowlist.

    Fail-closed, not "sanitize and continue": unset (or entirely blank/
    whitespace) means "no CORS middleware at all" (returns ``None``) -- the
    safe default for a local/internal deployment. Once the variable is
    non-blank, however, the *entire* value must be valid: every
    comma-separated token, after stripping whitespace, must be non-empty
    and must not be the literal ``"*"``. A single illegal token (a blank
    entry from a leading/trailing/double comma, or a wildcard anywhere --
    alone or mixed with real origins) raises
    ``ApiConfigurationError("INVALID_CORS_ORIGINS")`` for the *whole*
    configuration -- it never silently drops just the bad token(s) and
    proceeds with whatever remains. Legal origins are deduplicated,
    preserving first-occurrence order.
    """
    raw = os.environ.get("COMQUTOR_CORS_ORIGINS", "")
    if not raw.strip():
        return None
    origins: list[str] = []
    seen: set[str] = set()
    for item in raw.split(","):
        origin = item.strip()
        if not origin or origin == "*":
            raise ApiConfigurationError("INVALID_CORS_ORIGINS")
        if origin not in seen:
            seen.add(origin)
            origins.append(origin)
    return origins


# Set by the module-level ``app = create_app()`` call below when
# construction fails due to an ``ApiConfigurationError`` (as opposed to
# FastAPI simply not being installed) -- lets ``server.py``'s entrypoint
# tell the two "app is None" cases apart and print the right safe message.
app_configuration_error: ApiConfigurationError | None = None

try:
    from fastapi import FastAPI

    from comqutor_alpha.api.routes_alpha_library import router as alpha_library_router
    from comqutor_alpha.api.routes_replay_all import router as replay_all_router
    from comqutor_alpha.api.routes_research import router as research_router
    from comqutor_alpha.api.routes_system import router as system_router
    from comqutor_alpha.research_jobs import (
        JobManagerConfigError,
        build_job_manager_from_env,
        reconcile_orphaned_runs_on_startup,
    )
    from comqutor_alpha.storage.db.repository import (
        GraphPersistenceError,
        build_write_repository_from_env,
    )

    def create_app(*, output_root: str | None = None, replay_output_root: str | None = None) -> FastAPI:
        # Resolved -- and validated -- before anything else. An invalid
        # COMQUTOR_CORS_ORIGINS must never produce a partially-built app
        # (routers registered, lifespan wired, but CORS silently skipped or
        # half-applied); create_app() raises ApiConfigurationError and
        # returns nothing at all.
        cors_origins = _resolve_cors_origins()

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            app.state.output_root = output_root
            # Consumed only by POST /api/replay-all (routes_replay_all.py);
            # None means "use comqutor_alpha.replay.pipeline's own default
            # (outputs/replays)" -- no other route reads this.
            app.state.replay_output_root = replay_output_root
            app.state.job_manager = None

            # Startup reconciliation: local single-instance semantics --
            # any queued/running row surviving from a previous process is
            # marked failed (SERVER_RESTARTED) rather than resumed (which
            # could silently re-trigger a paid real-execution call). Never
            # applies a migration itself -- assumes 0001-0003 already exist
            # (the same assumption every other write-path repository call
            # makes); a repository construction failure here degrades to
            # "reconciliation skipped", not a startup crash.
            try:
                repository = build_write_repository_from_env(output_root)
                reconciled = reconcile_orphaned_runs_on_startup(repository)
                if reconciled:
                    logger.warning("startup reconciliation marked %d orphaned run(s) failed", len(reconciled))
            except GraphPersistenceError as exc:
                logger.warning("startup reconciliation skipped (reason_code=%s)", exc.reason_code)
            except Exception as exc:
                logger.warning("startup reconciliation failed unexpectedly (exc_type=%s)", type(exc).__name__)

            try:
                job_manager = build_job_manager_from_env(output_root)
                job_manager.start()
                app.state.job_manager = job_manager
            except JobManagerConfigError as exc:
                logger.warning("job manager unavailable at startup (reason_code=%s)", exc.reason_code)

            yield

            if app.state.job_manager is not None:
                app.state.job_manager.shutdown()

        app = FastAPI(title="COMQUTOR Alpha API", lifespan=lifespan)

        for router in (alpha_library_router, research_router, system_router, replay_all_router):
            if router is not None:
                app.include_router(router)

        if cors_origins:
            from fastapi.middleware.cors import CORSMiddleware

            app.add_middleware(
                CORSMiddleware,
                allow_origins=cors_origins,
                allow_credentials=False,
                allow_methods=["GET", "POST", "OPTIONS"],
                allow_headers=["Content-Type"],
            )

        return app

    try:
        app = create_app()
    except ApiConfigurationError as exc:
        app = None
        app_configuration_error = exc

except ImportError:
    app = None

    def create_app(*, output_root: str | None = None):
        raise RuntimeError(
            "The 'api' optional dependency group is not installed. "
            "Run: pip install \"tradingagents[api]\""
        )
