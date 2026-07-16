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
import os
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from comqutor_alpha.storage.file_store import validate_run_id_for_path

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
    # W5.1B: an allowlisted, non-secret hash of the server-side TradingAgents
    # config actually used for a real run (see server_execution.py). Folding
    # it into the fingerprint -- never persisted as its own column -- means
    # an operator changing the server's provider/model configuration
    # automatically invalidates completed-run reuse for real requests,
    # without needing a new schema column or migration. Empty string (never
    # None, to keep the identity dict's JSON-serializable shape stable) when
    # no server execution identity was supplied (offline requests, or real
    # requests before W5.1B wiring).
    config_identity_sha256 = str(identity_overrides.get("config_identity_sha256") or "")

    return {
        "ticker": ticker,
        "analysis_date": analysis_date,
        "selected_analysts": selected_analysts,
        "execution_mode": execution_mode,
        "offline_input_digest": offline_input_digest,
        "provider_identity": provider_identity,
        "model_identity": model_identity,
        "config_identity_sha256": config_identity_sha256,
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
    """Full semantic validation of an opaque history cursor -- not just
    "is this valid JSON shaped like a 2-tuple". Every failure mode (bad
    JSON, wrong shape, non-string elements, blank strings, a ``created_at``
    that is not a real ISO datetime, or a ``run_id`` that would not pass
    :func:`validate_run_id_for_path`) raises the exact same
    ``ResearchLifecycleError("INVALID_CURSOR")`` -- never a raw
    ``ValueError`` that a downstream repository call could otherwise
    accidentally swallow into an unrelated storage-error code.
    """
    try:
        decoded = json.loads(cursor)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ResearchLifecycleError("INVALID_CURSOR") from exc

    if not isinstance(decoded, list) or len(decoded) != 2:
        raise ResearchLifecycleError("INVALID_CURSOR")

    created_at_text, run_id = decoded
    if not isinstance(created_at_text, str) or not isinstance(run_id, str):
        raise ResearchLifecycleError("INVALID_CURSOR")
    if not created_at_text.strip() or not run_id.strip():
        raise ResearchLifecycleError("INVALID_CURSOR")

    try:
        datetime.fromisoformat(created_at_text)
    except ValueError as exc:
        raise ResearchLifecycleError("INVALID_CURSOR") from exc

    try:
        validate_run_id_for_path(run_id)
    except ValueError as exc:
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
    "OFFLINE_DISABLED": "Offline outputs are disabled.",
    "REAL_RUN_DISABLED": "Real TradingAgents execution is disabled by default.",
    "REAL_RUN_CONFIG_INVALID": "Real TradingAgents execution is not configured correctly.",
    "REAL_FORCE_REFRESH_DISABLED": "force_refresh is not enabled for real TradingAgents execution.",
    "INVALID_ANALYST_SELECTION": "selected_analysts contains an analyst not supported for real execution.",
}


def _is_production_env() -> bool:
    return os.environ.get("COMQUTOR_ENV", "").strip().lower() == "production"


def _gate_failure_response(run_id: Any, ticker: str, error_code: str) -> dict[str, Any]:
    """A safe, terminal response for a request rejected *before* any
    ``research_runs`` row is claimed -- no ``cache_disposition`` (nothing was
    ever claimed/reused), but ``run_status`` is still populated as
    ``"failed"`` for caller-shape compatibility with every other failure
    response this module returns."""
    return {
        "run_id": run_id,
        "ticker": ticker,
        "status": "failed",
        "error_code": error_code,
        "message": _safe_message(error_code, "Research request could not be processed."),
        "run_status": "failed",
    }


def _readonly_reuse_lookup(
    graph_repository: Any,
    *,
    run_id: str | None,
    request_fingerprint: str,
    force_refresh: bool,
) -> dict[str, Any] | None:
    """Read-only mirror of ``claim_research_run``'s reuse decision -- never
    inserts a row. Used to let an explicit run_id (or fingerprint) that
    already has a reusable/terminal row bypass the real-mode server gates
    below: reusing an existing result never executes anything new, so
    whether real execution is currently enabled/configured is irrelevant to
    it. Only requests that would actually need a *new* row go through the
    gates. Raises ``GraphPersistenceError("RUN_ID_CONFLICT")`` if an
    explicit run_id row exists for a different logical request, exactly like
    the write path would.
    """
    from comqutor_alpha.storage.db.repository import GraphPersistenceError

    if run_id is not None:
        existing = graph_repository.get_research_run_record(run_id)
        if existing is not None:
            if existing["request_fingerprint"] != request_fingerprint:
                raise GraphPersistenceError("RUN_ID_CONFLICT")
            if existing["status"] in ACTIVE_RESEARCH_RUN_STATUSES:
                return {"run_id": existing["run_id"], "disposition": DISPOSITION_REUSED_IN_FLIGHT, "record": existing}
            return {"run_id": existing["run_id"], "disposition": DISPOSITION_REUSED_COMPLETED, "record": existing}

    active = graph_repository.find_active_research_run(request_fingerprint)
    if active is not None:
        return {"run_id": active["run_id"], "disposition": DISPOSITION_REUSED_IN_FLIGHT, "record": active}

    if not force_refresh:
        completed = graph_repository.find_latest_completed_research_run(request_fingerprint)
        if completed is not None:
            return {"run_id": completed["run_id"], "disposition": DISPOSITION_REUSED_COMPLETED, "record": completed}

    return None


def _safe_message(error_code: str, fallback: str) -> str:
    return _SAFE_ERROR_MESSAGES.get(error_code, fallback)


def _build_terminal_reuse_response(
    run_id: str,
    record: Mapping[str, Any],
    ticker: str,
    *,
    output_root: Any,
    graph_repository: Any,
) -> dict[str, Any] | None:
    """Project a terminal (completed/partial/failed) ``research_runs`` row
    into a safe reuse response. The row is the sole source of truth for a
    terminal run's outcome -- never re-derived from, or overridden by,
    leftover filesystem artifacts, and never re-executed.

    For ``completed``, the canonical result is still rebuilt via
    ``build_research_response`` (the only way to get the full Week 1-4
    payload), but only after confirming the rebuilt status actually agrees
    with the database -- returns ``None`` (caller reports
    ``CACHED_RUN_UNAVAILABLE``) if the artifacts backing a "completed"
    database row are no longer readable/consistent.

    For ``partial``/``failed``, the response is built *exclusively* from
    the database row: no artifact read, no executor call, no chance of a
    stale/misleading artifact upgrading a partial/failed run to
    completed/partial. ``stage``/``error_code``/``error_message`` come
    straight from the row. Never exposes ``request_fingerprint``,
    ``active_fingerprint``, ``provider_identity``/``model_identity``,
    ``pipeline_identity``, or any local path.
    """
    from comqutor_alpha.api.routes_research import build_research_response

    status = record.get("status")
    if status == "completed":
        response = build_research_response(run_id, output_root=output_root, graph_repository=graph_repository)
        if response.get("status") != "completed":
            return None
        response["run_status"] = "completed"
        response["cache_disposition"] = DISPOSITION_REUSED_COMPLETED
        return response

    # partial or failed: DB-only, never calls the executor, never reads a
    # local artifact.
    stage = record.get("stage") or (STAGE_PARTIAL if status == "partial" else STAGE_FAILED)
    response: dict[str, Any] = {
        "run_id": run_id,
        "ticker": record.get("ticker", ticker),
        "status": status,
        "run_status": status,
        "stage": stage,
        "cache_disposition": DISPOSITION_REUSED_COMPLETED,
    }
    if status == "failed":
        error_code = str(record.get("error_code") or "INTERNAL_ERROR")
        response["error_code"] = error_code
        response["message"] = record.get("error_message") or _safe_message(
            error_code, "Research request failed."
        )
    return response


def _reuse_response_from_claim(
    claim: Mapping[str, Any],
    ticker: str,
    output_root: Any,
    graph_repository: Any,
) -> dict[str, Any] | None:
    """``{"response": ...}`` if ``claim``'s disposition is a reuse
    (in-flight or terminal), else ``None`` (disposition is
    created/force_refreshed -- caller must actually execute it)."""
    disposition = claim["disposition"]
    record = claim["record"]
    run_id = claim["run_id"]

    if disposition == DISPOSITION_REUSED_IN_FLIGHT:
        return {
            "response": {
                "run_id": run_id,
                "ticker": record.get("ticker", ticker),
                "status": "running" if record.get("status") == "running" else "queued",
                "run_status": record.get("status"),
                "stage": record.get("stage") or STAGE_RESEARCH_PIPELINE,
                "cache_disposition": DISPOSITION_REUSED_IN_FLIGHT,
            }
        }

    if disposition == DISPOSITION_REUSED_COMPLETED:
        # Reached either via fingerprint-based completed-cache lookup (record
        # is always "completed" there) or via an explicit run_id that already
        # points at *any* terminal attempt of the identical logical request
        # (record may be "completed", "partial", or "failed" there). Either
        # way, the research_runs row is the sole source of truth for a
        # terminal run's status -- it is never revived, never re-executed,
        # and a partial/failed row is never "upgraded" by reading a
        # leftover/misleading artifact off disk.
        reuse_response = _build_terminal_reuse_response(
            run_id, record, ticker, output_root=output_root, graph_repository=graph_repository
        )
        if reuse_response is None:
            # The database says completed, but the file-backed canonical
            # artifacts this run depended on are no longer readable/consistent
            # (e.g. output_root was cleared). Never silently re-run the
            # (potentially costly) pipeline to paper over that -- fail
            # closed with a stable, safe code instead.
            logger.warning("cached completed run unavailable (run_id=%s)", run_id)
            return {
                "response": {
                    "run_id": run_id,
                    "ticker": ticker,
                    "status": "failed",
                    "error_code": "CACHED_RUN_UNAVAILABLE",
                    "message": _safe_message("CACHED_RUN_UNAVAILABLE", "Cached result unavailable."),
                }
            }
        return {"response": reuse_response}

    return None


def prepare_research_submission(
    payload: Mapping[str, Any] | None,
    *,
    output_root: Any = "outputs/runs",
    graph_repository: Any = None,
    server_execution_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate, gate, fingerprint, and claim/reuse-lookup one research
    request. Never runs the pipeline itself -- that is
    ``execute_claimed_research_run``'s job, called by the synchronous
    ``submit_research_request`` below or by
    ``research_jobs.enqueue_research_request`` for the background path. This
    split exists so both paths share exactly one fingerprint/claim/
    real-mode-gate implementation.

    Returns exactly one of:

    - ``{"response": <dict>}``: a terminal response the caller should return
      as-is -- a validation/gate failure, or any reuse (in-flight, or any
      terminal explicit-run_id/fingerprint row).
    - ``{"claim": ..., "execution_payload": ..., "graph_repository": ...,
      "ticker": ...}``: disposition is ``created``/``force_refreshed`` -- a
      fresh ``queued`` row now exists and must actually be executed.

    Real-mode server gates (real execution enabled/configured,
    ``force_refresh`` enabled for real execution, the real-mode analyst
    allowlist -- see ``server_execution.py``) are enforced *before* ever
    calling ``claim_research_run`` -- but only when this request would
    actually need to create a new run. An explicit run_id or fingerprint
    that already resolves to a reusable/terminal row is served from that row
    via a read-only lookup regardless of current gate state (serving an
    existing result never executes anything new), and a gate failure with
    no existing row to reuse never creates a ``queued`` row at all.
    """
    from comqutor_alpha import server_execution
    from comqutor_alpha.api.routes_research import (
        _map_exception_to_error,
        _normalize_payload,
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
        return {"response": _map_exception_to_error(payload, exc)}

    offline_raw_agent_outputs = payload.get("offline_raw_agent_outputs")
    execution_mode = "offline" if offline_raw_agent_outputs is not None else "real"

    if execution_mode == "offline" and _is_production_env():
        # Rejected before any repository construction is even attempted --
        # never a queued row, never a repository connection for a request
        # this server will never execute.
        return {"response": _gate_failure_response(explicit_run_id, ticker, "OFFLINE_DISABLED")}

    working_payload = dict(payload)
    real_config: dict[str, Any] | None = None
    resolved_server_execution_identity = server_execution_identity
    real_gate_error: str | None = None

    if execution_mode == "real":
        # Resolved exactly once, here -- the same resolved value flows into
        # both the fingerprint (via working_payload) and, further below, the
        # execution_payload actually handed to the executor.
        working_payload["analysis_date"] = server_execution.resolve_real_analysis_date(
            payload.get("analysis_date")
        )
        if server_execution_identity is None:
            ctx = server_execution.build_server_execution_context()
            resolved_server_execution_identity = ctx["execution_identity"]
            if ctx["error"] is not None:
                real_gate_error = ctx["error"]
            elif force_refresh and not server_execution.is_real_force_refresh_enabled():
                real_gate_error = "REAL_FORCE_REFRESH_DISABLED"
            else:
                normalized_analysts = _normalize_selected_analysts(payload.get("selected_analysts"))
                try:
                    server_execution.validate_real_selected_analysts(normalized_analysts)
                except server_execution.ServerExecutionConfigError as exc:
                    real_gate_error = exc.reason_code
                else:
                    real_config = ctx["config"]

    if graph_repository is None:
        try:
            graph_repository = build_write_repository_from_env(output_root)
        except GraphPersistenceError as exc:
            logger.warning("research repository unavailable (reason_code=%s)", exc.reason_code)
            return {
                "response": {
                    "run_id": explicit_run_id,
                    "ticker": ticker,
                    "status": "failed",
                    "error_code": "INTERNAL_ERROR",
                    "message": _safe_message("INTERNAL_ERROR", "Research request failed."),
                }
            }
        except Exception as exc:
            logger.warning(
                "research repository unavailable unexpectedly (exc_type=%s)", type(exc).__name__
            )
            return {
                "response": {
                    "run_id": explicit_run_id,
                    "ticker": ticker,
                    "status": "failed",
                    "error_code": "INTERNAL_ERROR",
                    "message": _safe_message("INTERNAL_ERROR", "Research request failed."),
                }
            }

    try:
        identity = build_research_request_identity(
            working_payload, server_execution_identity=resolved_server_execution_identity
        )
        fingerprint = build_research_request_fingerprint(identity)
    except ValueError as exc:
        return {"response": _map_exception_to_error(payload, exc)}

    if real_gate_error is not None:
        try:
            reuse = _readonly_reuse_lookup(
                graph_repository,
                run_id=explicit_run_id,
                request_fingerprint=fingerprint,
                force_refresh=force_refresh,
            )
        except GraphPersistenceError as exc:
            logger.warning("research run claim failed (reason_code=%s)", exc.reason_code)
            error_code = exc.reason_code if exc.reason_code in _SAFE_ERROR_MESSAGES else "INTERNAL_ERROR"
            return {
                "response": {
                    "run_id": explicit_run_id,
                    "ticker": ticker,
                    "status": "failed",
                    "error_code": error_code,
                    "message": _safe_message(error_code, "Research request could not be processed."),
                }
            }
        if reuse is not None:
            reused = _reuse_response_from_claim(reuse, ticker, output_root, graph_repository)
            if reused is not None:
                return reused
        return {"response": _gate_failure_response(explicit_run_id, ticker, real_gate_error)}

    try:
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
            "response": {
                "run_id": explicit_run_id,
                "ticker": ticker,
                "status": "failed",
                "error_code": error_code,
                "message": _safe_message(error_code, "Research request could not be processed."),
            }
        }
    except ValueError as exc:
        return {"response": _map_exception_to_error(payload, exc)}

    reused = _reuse_response_from_claim(claim, ticker, output_root, graph_repository)
    if reused is not None:
        return reused

    # disposition in {created, force_refreshed}: a fresh `queued` row was
    # just claimed. Never executed here -- caller's job.
    run_id = claim["run_id"]
    execution_payload = {
        **working_payload,
        "run_id": run_id,
        "ticker": identity["ticker"],
        "selected_analysts": identity["selected_analysts"],
    }
    if execution_mode == "real" and real_config is not None:
        # Never sourced from the client payload -- ResearchRequest cannot
        # carry either of these fields (see routes_research.ResearchRequest).
        execution_payload["allow_real_tradingagents_run"] = True
        execution_payload["config"] = real_config

    return {
        "claim": claim,
        "execution_payload": execution_payload,
        "graph_repository": graph_repository,
        "ticker": ticker,
    }


def execute_claimed_research_run(
    run_id: str,
    execution_payload: Mapping[str, Any],
    *,
    output_root: Any,
    graph_repository: Any,
    disposition: str,
    ticker: str,
    executor: Any = None,
) -> dict[str, Any]:
    """Runs the pipeline for an already-``queued`` run and records the
    terminal outcome. Shared by the synchronous ``submit_research_request``
    path (same process) and the background worker process
    (``research_jobs.py`` -- a fresh ``graph_repository`` rebuilt from server
    env in the child process, never the parent's engine/connection object).

    ``executor`` defaults to the existing, unmodified
    ``routes_research.run_research_request`` -- this function never
    reimplements Week 1-4 pipeline logic, it only records the outcome the
    executor reports.
    """
    from comqutor_alpha.api.routes_research import run_research_request

    executor = executor or run_research_request

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


def submit_research_request(
    payload: Mapping[str, Any] | None,
    *,
    output_root: Any = "outputs/runs",
    graph_repository: Any = None,
    executor: Any = None,
    server_execution_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Claim/execute/reuse a research request through the run lifecycle --
    synchronous, in-process. Preserved unchanged as a direct Python
    entrypoint (no background job submission, no queueing) for backward
    compatibility; ``research_jobs.enqueue_research_request`` is the
    background-submission equivalent used by the async HTTP POST route.
    Internally just ``prepare_research_submission`` followed by
    ``execute_claimed_research_run`` when a fresh run was actually claimed.
    """
    prepared = prepare_research_submission(
        payload,
        output_root=output_root,
        graph_repository=graph_repository,
        server_execution_identity=server_execution_identity,
    )
    if "response" in prepared:
        return prepared["response"]

    claim = prepared["claim"]
    return execute_claimed_research_run(
        claim["run_id"],
        prepared["execution_payload"],
        output_root=output_root,
        graph_repository=prepared["graph_repository"],
        executor=executor,
        disposition=claim["disposition"],
        ticker=prepared["ticker"],
    )


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
    "prepare_research_submission",
    "execute_claimed_research_run",
    "submit_research_request",
]
