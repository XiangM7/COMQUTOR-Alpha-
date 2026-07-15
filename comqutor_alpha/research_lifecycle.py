"""W5.1A: Research Run Lifecycle, Request Fingerprint, and Submission
Orchestration.

This module is the run-control layer sitting in front of the existing,
unmodified Week 1-4 research pipeline (``routes_research.run_research_request``).
It answers three questions a raw pipeline call never could on its own:

1. Is this exact logical request already running somewhere (in-flight
   duplicate suppression)?
2. Has this exact logical request already completed (completed-run reuse)?
3. If neither, claim a new ``queued`` row, run the pipeline, and record the
   terminal outcome (``completed``/``partial``/``failed``).

Nothing here calls a real LLM, a real data provider, or real TradingAgents.
Nothing here starts a background task, thread pool, or queue -- submission
is still synchronous; this module only adds bookkeeping and de-duplication
around the existing synchronous call.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping, Sequence
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lifecycle state machine
# ---------------------------------------------------------------------------

RESEARCH_RUN_STATUSES = frozenset({"queued", "running", "completed", "partial", "failed"})
TERMINAL_RESEARCH_RUN_STATUSES = frozenset({"completed", "partial", "failed"})
ACTIVE_RESEARCH_RUN_STATUSES = frozenset({"queued", "running"})

# Allowed (from_status -> {to_status, ...}) transitions. Anything not listed
# here -- including every transition *out of* a terminal status -- is
# forbidden. A failed retry must claim a brand new run_id; no terminal row
# is ever revived in place.
_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "failed"}),
    "running": frozenset({"completed", "partial", "failed"}),
    "completed": frozenset(),
    "partial": frozenset(),
    "failed": frozenset(),
}


def is_allowed_transition(from_status: str, to_status: str) -> bool:
    return to_status in _ALLOWED_TRANSITIONS.get(from_status, frozenset())


# Stable, non-sensitive stage labels. Never a raw exception message, a stack
# frame, or anything provider/path specific.
STAGE_ACCEPTED = "accepted"
STAGE_RESEARCH_PIPELINE = "research_pipeline"
STAGE_COMPLETED = "completed"
STAGE_PARTIAL = "partial"
STAGE_FAILED = "failed"

# Cache-disposition values returned to callers of submit_research_request.
DISPOSITION_CREATED = "created"
DISPOSITION_REUSED_COMPLETED = "reused_completed"
DISPOSITION_REUSED_IN_FLIGHT = "reused_in_flight"
DISPOSITION_FORCE_REFRESHED = "force_refreshed"

# Matches tradingagents_runner.py's inline real-run default analyst set.
# Duplicated here (not importable as a named constant -- tradingagents_runner.py
# is out of scope for this task) rather than reverse-engineered from the
# HTTP payload, so a request that omits selected_analysts fingerprints
# identically to one that explicitly names this exact set.
DEFAULT_SELECTED_ANALYSTS: tuple[str, ...] = ("market", "news", "fundamentals", "sentiment")

# Used for provider_identity/model_identity when no real, server-controlled
# execution identity has been configured yet (W5.1B scope). Never derived
# from client payload.
SERVER_UNCONFIGURED_IDENTITY = "server_unconfigured"


class ResearchLifecycleError(Exception):
    """Safe orchestration-layer error: carries a stable reason code only.
    Never carries a raw exception message, traceback, DSN, path, or raw
    payload content."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


# ---------------------------------------------------------------------------
# Canonicalization helpers
# ---------------------------------------------------------------------------


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_selected_analysts(raw: Any) -> list[str]:
    if not raw:
        raw = DEFAULT_SELECTED_ANALYSTS
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raw = DEFAULT_SELECTED_ANALYSTS
    cleaned = {str(item).strip() for item in raw if str(item or "").strip()}
    return sorted(cleaned)


def _normalize_analysis_date(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _taxonomy_identity() -> str:
    """SHA-256 of the frozen taxonomy file's own bytes -- never the content
    itself. This is a read of a static, version-controlled file (not a
    formal "seed"), used purely as a change-detection identity so a future
    taxonomy edit changes every fingerprint computed against it."""
    from comqutor_alpha.alpha_library.alpha_loader import TAXONOMY_PATH

    return hashlib.sha256(TAXONOMY_PATH.read_bytes()).hexdigest()


def _pipeline_identity() -> dict[str, str]:
    """Stable version identifiers for every stage of the Week 1-4 pipeline
    that a persisted/cached research result depends on. Reuses existing
    version constants -- never invents a new versioning scheme."""
    from comqutor_alpha.conflict_engine.conflict_schema import (
        CONFLICT_FORMULA_VERSION,
        CONFLICT_SCHEMA_VERSION,
    )
    from comqutor_alpha.graph_engine.graph_schema import (
        ACTIVATION_FORMULA_VERSION,
        ACTIVATION_SCORER_VERSION,
        GRAPH_BUILDER_VERSION,
        GRAPH_SCHEMA_VERSION,
    )
    from comqutor_alpha.structure_engine.structured_output_adapter import (
        ADAPTER_VERSION,
        SCHEMA_VERSION as STRUCTURED_OUTPUT_SCHEMA_VERSION,
    )

    return {
        "structured_output_schema_version": STRUCTURED_OUTPUT_SCHEMA_VERSION,
        "structured_output_adapter_version": ADAPTER_VERSION,
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        "graph_builder_version": GRAPH_BUILDER_VERSION,
        "activation_scorer_version": ACTIVATION_SCORER_VERSION,
        "activation_formula_version": ACTIVATION_FORMULA_VERSION,
        "conflict_schema_version": CONFLICT_SCHEMA_VERSION,
        "conflict_formula_version": CONFLICT_FORMULA_VERSION,
        "taxonomy_sha256": _taxonomy_identity(),
    }


# ---------------------------------------------------------------------------
# Request identity / fingerprint
# ---------------------------------------------------------------------------


def build_research_request_identity(
    payload: Mapping[str, Any] | None,
    *,
    server_execution_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Deterministic identity dict used to compute the request fingerprint.

    Deliberately excludes ``run_id``, ``force_refresh``, wall-clock time,
    randomness, secrets, and any raw provider config -- two HTTP requests
    that only differ in those fields must produce the exact same identity
    (and therefore the same fingerprint). Includes a digest of the full
    ``offline_raw_agent_outputs`` payload (not just ticker/date) so any
    content change changes the fingerprint, without ever storing that raw
    payload anywhere.
    """
    payload = payload if isinstance(payload, Mapping) else {}

    # Deferred import: routes_research.py imports submit_research_request
    # from this module at module load time, so importing routes_research
    # back at *this* module's top level would be circular. Ticker
    # validation is intentionally reused (not duplicated) -- by the time
    # this function actually runs, both modules are fully loaded.
    from comqutor_alpha.api.routes_research import validate_ticker

    ticker = validate_ticker(payload.get("ticker"))
    analysis_date = _normalize_analysis_date(payload.get("analysis_date"))
    selected_analysts = _normalize_selected_analysts(payload.get("selected_analysts"))

    offline_raw_agent_outputs = payload.get("offline_raw_agent_outputs")
    execution_mode = "offline" if offline_raw_agent_outputs is not None else "real"
    offline_input_digest = (
        _sha256_hex(_canonical_json(offline_raw_agent_outputs))
        if execution_mode == "offline"
        else None
    )

    identity_overrides = server_execution_identity if isinstance(server_execution_identity, Mapping) else {}
    provider_identity = str(identity_overrides.get("provider_identity") or SERVER_UNCONFIGURED_IDENTITY)
    model_identity = str(identity_overrides.get("model_identity") or SERVER_UNCONFIGURED_IDENTITY)

    return {
        "ticker": ticker,
        "analysis_date": analysis_date,
        "selected_analysts": selected_analysts,
        "execution_mode": execution_mode,
        "offline_input_digest": offline_input_digest,
        "provider_identity": provider_identity,
        "model_identity": model_identity,
        "pipeline_identity": _pipeline_identity(),
    }


def build_research_request_fingerprint(identity: Mapping[str, Any]) -> str:
    """Canonical-JSON + SHA-256 over the identity dict. Deterministic: the
    same identity always produces the same fingerprint, independent of key
    insertion order (``sort_keys=True``)."""
    return _sha256_hex(_canonical_json(identity))


# ---------------------------------------------------------------------------
# Run history cursor codec (opaque to callers; keyset, not offset-based)
# ---------------------------------------------------------------------------


def encode_run_history_cursor(created_at: Any, run_id: str) -> str:
    created_at_text = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)
    return _canonical_json([created_at_text, run_id])


def decode_run_history_cursor(cursor: str) -> tuple[str, str]:
    try:
        decoded = json.loads(cursor)
        created_at_text, run_id = decoded
        if not isinstance(created_at_text, str) or not isinstance(run_id, str):
            raise ValueError
        if not created_at_text or not run_id:
            raise ValueError
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ResearchLifecycleError("INVALID_CURSOR") from exc
    return created_at_text, run_id


# ---------------------------------------------------------------------------
# Submission orchestration
# ---------------------------------------------------------------------------

# Safe, stable error messages -- never a raw exception string.
_SAFE_ERROR_MESSAGES = {
    "INTERNAL_ERROR": "Research request failed.",
    "CACHED_RUN_UNAVAILABLE": "A completed result was expected but is no longer available.",
    "RUN_ID_CONFLICT": "run_id already exists for a different request.",
    "INVALID_FORCE_REFRESH": "force_refresh cannot be combined with an existing run_id.",
}


def _safe_message(error_code: str, fallback: str) -> str:
    return _SAFE_ERROR_MESSAGES.get(error_code, fallback)


def submit_research_request(
    payload: Mapping[str, Any] | None,
    *,
    output_root: Any = "outputs/runs",
    graph_repository: Any = None,
    executor: Any = None,
    server_execution_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Claim/execute/reuse a research request through the run lifecycle.

    ``executor`` defaults to the existing, unmodified
    ``routes_research.run_research_request`` -- this function never
    reimplements Week 1-4 pipeline logic, it only decides *whether* and
    *how* to call it, and records the outcome. ``graph_repository`` is used
    both for the research_runs bookkeeping calls and is threaded through
    unchanged into the executor, so both share one database handle. When not
    injected (the real HTTP route), a write-ready repository is constructed
    from server environment configuration -- the same construction path
    ``_run_week3_graph_pipeline`` already uses -- and any construction
    failure degrades to a safe ``INTERNAL_ERROR`` response rather than an
    unhandled exception reaching the HTTP layer.
    """
    from comqutor_alpha.api.routes_research import (
        _map_exception_to_error,
        _normalize_payload,
        build_research_response,
        run_research_request,
        validate_ticker,
    )
    from comqutor_alpha.storage.db.repository import (
        GraphPersistenceError,
        build_write_repository_from_env,
    )

    payload = _normalize_payload(payload)
    force_refresh = bool(payload.get("force_refresh") or False)
    explicit_run_id = payload.get("run_id")

    try:
        ticker = validate_ticker(payload.get("ticker"))
    except ValueError as exc:
        return _map_exception_to_error(payload, exc)

    if graph_repository is None:
        try:
            graph_repository = build_write_repository_from_env(output_root)
        except GraphPersistenceError as exc:
            logger.warning("research repository unavailable (reason_code=%s)", exc.reason_code)
            return {
                "run_id": explicit_run_id,
                "ticker": ticker,
                "status": "failed",
                "error_code": "INTERNAL_ERROR",
                "message": _safe_message("INTERNAL_ERROR", "Research request failed."),
            }
        except Exception as exc:
            logger.warning(
                "research repository unavailable unexpectedly (exc_type=%s)", type(exc).__name__
            )
            logger.debug("research repository unavailable unexpectedly", exc_info=True)
            return {
                "run_id": explicit_run_id,
                "ticker": ticker,
                "status": "failed",
                "error_code": "INTERNAL_ERROR",
                "message": _safe_message("INTERNAL_ERROR", "Research request failed."),
            }

    try:
        identity = build_research_request_identity(payload, server_execution_identity=server_execution_identity)
        fingerprint = build_research_request_fingerprint(identity)
        claim = graph_repository.claim_research_run(
            run_id=explicit_run_id,
            request_fingerprint=fingerprint,
            ticker=identity["ticker"],
            analysis_date=identity["analysis_date"],
            selected_analysts=identity["selected_analysts"],
            execution_mode=identity["execution_mode"],
            provider_identity=identity["provider_identity"],
            model_identity=identity["model_identity"],
            pipeline_identity=identity["pipeline_identity"],
            force_refresh=force_refresh,
        )
    except GraphPersistenceError as exc:
        logger.warning("research run claim failed (reason_code=%s)", exc.reason_code)
        error_code = exc.reason_code if exc.reason_code in _SAFE_ERROR_MESSAGES else "INTERNAL_ERROR"
        return {
            "run_id": explicit_run_id,
            "ticker": ticker,
            "status": "failed",
            "error_code": error_code,
            "message": _safe_message(error_code, "Research request could not be processed."),
        }
    except ValueError as exc:
        return _map_exception_to_error(payload, exc)

    run_id = claim["run_id"]
    disposition = claim["disposition"]
    record = claim["record"]

    if disposition == DISPOSITION_REUSED_IN_FLIGHT:
        return {
            "run_id": run_id,
            "ticker": record.get("ticker", ticker),
            "status": "running" if record.get("status") == "running" else "queued",
            "run_status": record.get("status"),
            "stage": record.get("stage") or STAGE_RESEARCH_PIPELINE,
            "cache_disposition": DISPOSITION_REUSED_IN_FLIGHT,
        }

    if disposition == DISPOSITION_REUSED_COMPLETED:
        # Reached either via fingerprint-based completed-cache lookup (record
        # is always "completed" there) or via an explicit run_id that already
        # points at *any* terminal attempt of the identical logical request
        # (record may be "completed", "partial", or "failed" there -- never
        # revived, never re-executed, just reported as-is). The
        # database-says-completed-but-artifacts-are-gone safety check only
        # applies when the record itself claims "completed"; a genuinely
        # partial/failed terminal record is reported honestly, not treated
        # as an availability failure.
        response = build_research_response(run_id, output_root=output_root, graph_repository=graph_repository)
        recorded_status = record.get("status")
        if recorded_status == "completed" and response.get("status") != "completed":
            # The database says completed, but the file-backed canonical
            # artifacts this run depended on are no longer readable/consistent
            # (e.g. output_root was cleared). Never silently re-run the
            # (potentially costly) pipeline to paper over that -- fail
            # closed with a stable, safe code instead.
            logger.warning("cached completed run unavailable (run_id=%s)", run_id)
            return {
                "run_id": run_id,
                "ticker": ticker,
                "status": "failed",
                "error_code": "CACHED_RUN_UNAVAILABLE",
                "message": _safe_message("CACHED_RUN_UNAVAILABLE", "Cached result unavailable."),
            }
        response["run_status"] = response.get("status")
        response["cache_disposition"] = DISPOSITION_REUSED_COMPLETED
        return response

    # disposition in {created, force_refreshed}: a fresh `queued` row was
    # just claimed. Execute the pipeline now.
    executor = executor or run_research_request
    execution_payload = {
        **payload,
        "run_id": run_id,
        "ticker": identity["ticker"],
        "selected_analysts": identity["selected_analysts"],
    }

    try:
        graph_repository.mark_research_run_running(run_id)
        result = executor(
            execution_payload,
            output_root=output_root,
            graph_repository=graph_repository,
        )
    except Exception as exc:
        logger.warning(
            "research run execution failed unexpectedly (run_id=%s, exc_type=%s)",
            run_id,
            type(exc).__name__,
        )
        logger.debug("research run execution failed unexpectedly (run_id=%s)", run_id, exc_info=True)
        with _suppress_lifecycle_errors():
            graph_repository.mark_research_run_terminal(
                run_id, status="failed", error_code="INTERNAL_ERROR", error_message=_safe_message("INTERNAL_ERROR", "Research request failed.")
            )
        return {
            "run_id": run_id,
            "ticker": ticker,
            "status": "failed",
            "error_code": "INTERNAL_ERROR",
            "message": _safe_message("INTERNAL_ERROR", "Research request failed."),
            "run_status": "failed",
            "cache_disposition": disposition,
        }

    result_status = result.get("status")
    if result_status in ("completed", "partial"):
        with _suppress_lifecycle_errors():
            graph_repository.mark_research_run_terminal(run_id, status=result_status)
    else:
        error_code = result.get("error_code") or "INTERNAL_ERROR"
        error_message = result.get("message") or _safe_message(error_code, "Research request failed.")
        with _suppress_lifecycle_errors():
            graph_repository.mark_research_run_terminal(
                run_id, status="failed", error_code=str(error_code), error_message=str(error_message)
            )

    result["run_status"] = result_status if result_status in ("completed", "partial") else "failed"
    result["cache_disposition"] = disposition
    return result


class _suppress_lifecycle_errors:
    """Best-effort terminal-state write: the pipeline outcome itself must
    still be returned to the caller even if the bookkeeping update fails
    (e.g. a transient DB hiccup) -- worst case, a stale queued/running row
    under-reports until manually reconciled, but the caller is never told
    "failed" for a run that actually succeeded, or vice versa."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc is not None:
            logger.warning(
                "research run terminal-state bookkeeping failed (exc_type=%s)", exc_type.__name__
            )
        return True


__all__ = [
    "RESEARCH_RUN_STATUSES",
    "TERMINAL_RESEARCH_RUN_STATUSES",
    "ACTIVE_RESEARCH_RUN_STATUSES",
    "is_allowed_transition",
    "STAGE_ACCEPTED",
    "STAGE_RESEARCH_PIPELINE",
    "STAGE_COMPLETED",
    "STAGE_PARTIAL",
    "STAGE_FAILED",
    "DISPOSITION_CREATED",
    "DISPOSITION_REUSED_COMPLETED",
    "DISPOSITION_REUSED_IN_FLIGHT",
    "DISPOSITION_FORCE_REFRESHED",
    "DEFAULT_SELECTED_ANALYSTS",
    "SERVER_UNCONFIGURED_IDENTITY",
    "ResearchLifecycleError",
    "build_research_request_identity",
    "build_research_request_fingerprint",
    "encode_run_history_cursor",
    "decode_run_history_cursor",
    "submit_research_request",
]
