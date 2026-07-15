"""File-backed reader for Week 1-2 structured agent outputs (W4.3).

Reads exactly one artifact -- ``structured_agent_outputs.json`` -- and never
opens, stats, or otherwise references ``raw_agent_outputs.json``, even when
that file exists on disk. This is the sole enforcement point for the W4.3
spec-resolution decision recorded in ``docs/w4_3_gate_contract.md`` section
7: ``GET /api/research/{run_id}/agent-outputs`` is structured-only by
design, not by omission. Raw transcript authorization/redaction/audit is a
deferred, separate decision, out of scope for this endpoint.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from comqutor_alpha.storage.file_store import run_dir_for, validate_run_id_for_path

logger = logging.getLogger(__name__)

STRUCTURED_ARTIFACT_FILENAME = "structured_agent_outputs.json"

_ERROR_MESSAGES = {
    "INVALID_RUN_ID": "Invalid run_id.",
    "RUN_NOT_FOUND": "Run not found.",
    "AGENT_OUTPUTS_NOT_READY": "Structured agent outputs have not been generated for this run yet.",
    "AGENT_OUTPUTS_CORRUPTED": "Persisted structured agent outputs are missing required fields.",
    "AGENT_OUTPUTS_UNAVAILABLE": "Agent output storage is temporarily unavailable.",
}


class AgentOutputsReadError(Exception):
    """Safe read-path error: carries a stable reason code only. Never
    carries a raw exception message, a traceback, or a local path."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def _error_response(run_id: str | None, error_code: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "ticker": None,
        "status": "failed",
        "error_code": error_code,
        "message": _ERROR_MESSAGES[error_code],
    }


def _read_structured_payload(run_id: str, output_root: Any) -> dict[str, Any]:
    """Load and structurally validate ``structured_agent_outputs.json``.

    Never constructs a path to, checks for, or opens
    ``raw_agent_outputs.json`` -- structured-only by construction, not by a
    field filter applied after reading both files.
    """
    run_dir = run_dir_for(run_id, output_root)
    path = run_dir / STRUCTURED_ARTIFACT_FILENAME

    if not path.exists():
        raise AgentOutputsReadError("AGENT_OUTPUTS_NOT_READY")

    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AgentOutputsReadError("AGENT_OUTPUTS_CORRUPTED") from exc
    except OSError as exc:
        raise AgentOutputsReadError("AGENT_OUTPUTS_UNAVAILABLE") from exc

    if not isinstance(payload, dict):
        raise AgentOutputsReadError("AGENT_OUTPUTS_CORRUPTED")
    if payload.get("run_id") != run_id:
        raise AgentOutputsReadError("AGENT_OUTPUTS_CORRUPTED")
    ticker = payload.get("ticker")
    if not isinstance(ticker, str) or not ticker.strip():
        raise AgentOutputsReadError("AGENT_OUTPUTS_CORRUPTED")
    schema_version = payload.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version.strip():
        raise AgentOutputsReadError("AGENT_OUTPUTS_CORRUPTED")
    records = payload.get("records")
    if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
        raise AgentOutputsReadError("AGENT_OUTPUTS_CORRUPTED")

    return {"ticker": ticker, "schema_version": schema_version, "records": records}


def get_agent_outputs_response(run_id: Any, output_root: str = "outputs/runs") -> dict[str, Any]:
    """Build the full ``GET /api/research/{run_id}/agent-outputs`` response.

    Structured-only by design (see module docstring). Never invokes an LLM,
    TradingAgents, or a network call; never performs a database write, table
    creation, or migration; never returns a local filesystem path.
    """
    try:
        safe_run_id = validate_run_id_for_path(run_id)
    except ValueError:
        return _error_response(str(run_id) if run_id is not None else None, "INVALID_RUN_ID")

    run_dir = run_dir_for(safe_run_id, output_root)
    if not run_dir.exists():
        return _error_response(safe_run_id, "RUN_NOT_FOUND")

    try:
        parsed = _read_structured_payload(safe_run_id, output_root)
    except AgentOutputsReadError as exc:
        return _error_response(safe_run_id, exc.reason_code)
    except Exception as exc:
        logger.warning(
            "agent outputs read failed unexpectedly (run_id=%s, exc_type=%s)",
            safe_run_id,
            type(exc).__name__,
        )
        logger.debug(
            "agent outputs read failed unexpectedly (run_id=%s)", safe_run_id, exc_info=True
        )
        return _error_response(safe_run_id, "AGENT_OUTPUTS_UNAVAILABLE")

    structured_records = parsed["records"]
    return {
        "run_id": safe_run_id,
        "ticker": parsed["ticker"],
        "status": "ok",
        "schema_version": parsed["schema_version"],
        "structured_agent_outputs": structured_records,
        "count": len(structured_records),
    }


__all__ = ["get_agent_outputs_response", "AgentOutputsReadError", "STRUCTURED_ARTIFACT_FILENAME"]
