"""W5.1B: liveness (``/health``) and readiness (``/ready``) endpoints.

``/health`` is pure liveness -- it never touches the database, the
filesystem, a provider, or the network. It only proves the process is alive
and able to answer HTTP requests.

``/ready`` checks the things an operator actually needs before routing
traffic here: the database is reachable and migrated (0001-0004, read-only
-- this endpoint never applies a migration or writes a row), and the
background job manager is initialized and currently accepting jobs. It also
reports (never gates overall readiness on, when merely *disabled*) whether
real TradingAgents execution is configured. Every error path is a stable,
safe status string -- never a DSN, a config value, an API key, a traceback,
or a filesystem path.
"""

from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError

from comqutor_alpha import server_execution
from comqutor_alpha.storage.db.engine import (
    DatabaseConfigurationError,
    build_engine,
    resolve_database_url,
    sqlite_file_path,
)
from comqutor_alpha.storage.db.schema import schema_migrations

logger = logging.getLogger(__name__)

_REQUIRED_MIGRATIONS = frozenset(
    {
        "0001_create_week3_alpha_matches_and_structure_graphs",
        "0002_create_week4_alpha_activations_and_alpha_conflicts",
        "0003_create_research_runs",
        "0004_create_agent_outputs",
        "0005_create_research_run_progress",
    }
)

# Safe, stable reason labels for a misconfigured real-execution capability.
# Never an env var value, a config dict, or an exception message.
_REAL_EXECUTION_REASONS = {
    "REAL_RUN_CONFIG_INVALID": "profile_invalid",
    "REAL_RUN_CREDENTIAL_MISSING": "credential_missing",
}


def health_response() -> dict[str, Any]:
    return {"status": "ok"}


def _database_ready(output_root: str | None) -> bool:
    """Read-only: a single ``SELECT 1`` plus a read of ``schema_migrations``.
    Never applies a migration, never creates a local SQLite file that does
    not already exist (mirrors ``GraphPersistenceRepository``'s own guard).
    """
    try:
        database_url = resolve_database_url(output_root)
    except DatabaseConfigurationError:
        return False

    guard = sqlite_file_path(database_url)
    if guard is not None and not guard.exists():
        return False

    try:
        engine = build_engine(database_url, create_if_missing=False)
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
            applied = set(conn.execute(sa.select(schema_migrations.c.version)).scalars().all())
    except SQLAlchemyError:
        return False
    return _REQUIRED_MIGRATIONS.issubset(applied)


def _real_execution_status() -> tuple[str, str | None]:
    """``("disabled"|"configured"|"misconfigured", safe_reason_or_None)``.

    ``disabled`` is decided *before* any profile or credential check, so a
    deliberately-disabled server is always reported as disabled -- never
    misreported as a credential problem. When enabled, the fixed Research
    Profile must build and its provider's own API key (whichever provider
    that profile actually names -- DeepSeek by default) must be *present*
    (presence only -- the value is never validated, read into memory beyond
    the boolean check, logged, or returned). Never leaks the config dict,
    provider identity, or any env var value."""
    ctx = server_execution.build_server_execution_context()
    if not ctx["enabled"]:
        return "disabled", None
    if ctx["error"] is not None:
        return "misconfigured", _REAL_EXECUTION_REASONS.get(ctx["error"], "profile_invalid")
    return "configured", None


def _active_profile_fields() -> dict[str, Any] | None:
    """Safe, non-secret snapshot of the profile a real request would
    resolve to right now -- never a credential, never a config value beyond
    what the profile itself already exposes via ``build_profile_identity``.
    ``None`` if the profile itself fails to build (reported instead via
    ``real_execution``/``real_execution_reason``)."""
    try:
        from comqutor_alpha.research_profiles import get_active_research_profile

        profile = get_active_research_profile()
    except Exception:
        return None
    return {
        "profile_id": profile.profile_id,
        "profile_display_name": profile.display_name,
        "provider": profile.llm_provider,
        "quick_model": profile.quick_think_llm,
        "deep_model": profile.deep_think_llm,
        "thinking": profile.deepseek_thinking,
        "max_debate_rounds": profile.max_debate_rounds,
        "max_risk_discuss_rounds": profile.max_risk_discuss_rounds,
    }


def readiness_response(*, job_manager: Any, output_root: str | None = None) -> tuple[dict[str, Any], bool]:
    """Returns ``(body, overall_ready)``. Overall readiness requires the
    database (migrated through 0005) *and* job manager to both be usable; a
    merely *disabled* (not misconfigured) real-execution capability never
    blocks overall readiness -- only an enabled-but-invalid configuration
    (broken profile, or missing credential for the active profile's
    provider) does.
    """
    database_ready = _database_ready(output_root)
    job_manager_ready = job_manager is not None and bool(job_manager.is_accepting())
    real_execution_status, real_execution_reason = _real_execution_status()

    overall_ready = database_ready and job_manager_ready and real_execution_status != "misconfigured"

    body = {
        "status": "ready" if overall_ready else "not_ready",
        "database": "ready" if database_ready else "unavailable",
        "job_manager": "ready" if job_manager_ready else "unavailable",
        "real_execution": real_execution_status,
        "real_execution_reason": real_execution_reason,
        # Always the real, current default profile -- never a stale/
        # hardcoded provider label. None only if the profile itself fails
        # to build (see real_execution_reason for why).
        "profile": _active_profile_fields(),
    }
    return body, overall_ready


try:
    from fastapi import APIRouter, Request
    from fastapi.responses import JSONResponse

    router = APIRouter()

    @router.get("/health")
    def get_health() -> dict[str, Any]:
        return health_response()

    @router.get("/ready")
    def get_ready(request: Request) -> JSONResponse:
        job_manager = getattr(request.app.state, "job_manager", None)
        output_root = getattr(request.app.state, "output_root", None)
        body, ok = readiness_response(job_manager=job_manager, output_root=output_root)
        return JSONResponse(content=body, status_code=200 if ok else 503)

except ImportError:
    router = None


__all__ = [
    "health_response",
    "readiness_response",
    "router",
]
