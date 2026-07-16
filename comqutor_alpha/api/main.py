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


def _resolve_cors_origins() -> list[str] | None:
    """``COMQUTOR_CORS_ORIGINS``: a comma-separated exact-origin allowlist.

    Unset -> ``None`` (no CORS middleware installed at all -- the safe
    default for a local/internal deployment). Blank entries are dropped,
    duplicates are removed, and a literal ``"*"`` is always rejected (never
    installed, even alongside other explicit origins) -- this phase always
    runs with ``allow_credentials=False``, but a wildcard origin is refused
    unconditionally rather than relying on that alone.
    """
    raw = os.environ.get("COMQUTOR_CORS_ORIGINS", "").strip()
    if not raw:
        return None
    origins: list[str] = []
    seen: set[str] = set()
    for item in raw.split(","):
        origin = item.strip()
        if not origin or origin == "*":
            continue
        if origin not in seen:
            seen.add(origin)
            origins.append(origin)
    return origins or None


try:
    from fastapi import FastAPI

    from comqutor_alpha.api.routes_alpha_library import router as alpha_library_router
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

    def create_app(*, output_root: str | None = None) -> FastAPI:
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            app.state.output_root = output_root
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

        for router in (alpha_library_router, research_router, system_router):
            if router is not None:
                app.include_router(router)

        cors_origins = _resolve_cors_origins()
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

    app = create_app()

except ImportError:
    app = None

    def create_app(*, output_root: str | None = None):
        raise RuntimeError(
            "The 'api' optional dependency group is not installed. "
            "Run: pip install \"tradingagents[api]\""
        )
