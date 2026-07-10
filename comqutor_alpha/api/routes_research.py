"""Week 1A research entrypoint helpers and optional FastAPI routes."""

from __future__ import annotations

import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from comqutor_alpha.adapters.tradingagents_output_writer import (
    OUTPUT_VERSION,
    build_raw_agent_output_record,
)
from comqutor_alpha.storage.file_store import (
    load_json_record,
    load_json_record_if_exists,
    run_dir_for,
    save_json_record,
    validate_run_id_for_path,
)
from comqutor_alpha.structure_engine.structured_output_adapter import (
    ERROR_LOG_ARTIFACT_PATH,
    save_structured_agent_outputs,
)


logger = logging.getLogger(__name__)

TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")

# Validate and normalize a request ticker.
def validate_ticker(raw):
    """Normalize and validate a request ticker. Uppercase, then whitelist-check.

    Accepts 1-10 chars starting with a letter, using A-Z, 0-9, '.', '-'
    (covers tickers like NVDA, BRK.B, RDS-A). Raises ValueError('INVALID_TICKER: ...').
    """
    ticker = str(raw or "").strip().upper()
    if not ticker:
        raise ValueError("INVALID_TICKER: ticker is required")
    if not TICKER_PATTERN.fullmatch(ticker):
        raise ValueError(
            "INVALID_TICKER: ticker must be 1-10 chars from A-Z, 0-9, '.', '-' "
            "and start with a letter"
        )
    return ticker

# Get the current UTC timestamp as a string.
def _utc_timestamp():
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

# Normalize the request payload.
def _normalize_payload(payload):
    return payload if isinstance(payload, dict) else {}

# Create a standardized error response payload.
def _error_response(payload, error_code, message):
    payload = _normalize_payload(payload)
    return {
        "run_id": payload.get("run_id"),
        "ticker": payload.get("ticker"),
        "status": "failed",
        "error_code": error_code,
        "message": message,
    }


# Error codes for expected client/input rejections (bad ticker, bad run_id, disabled
# feature, etc.) rather than unexpected internal failures. These are logged at a
# lower level without a traceback so probing/malformed requests don't flood logs.
_EXPECTED_CLIENT_ERROR_CODES = frozenset(
    {
        "INVALID_RUN_ID",
        "INVALID_ARTIFACT_FILENAME",
        "INVALID_OFFLINE_OUTPUTS",
        "INVALID_TICKER",
        "REAL_RUN_DISABLED",
        "OFFLINE_DISABLED",
    }
)

# Map known exceptions to standardized error responses.
def _map_exception_to_error(payload, exc):
    message = str(exc)
    if isinstance(exc, ValueError):
        if message.startswith("INVALID_RUN_ID"):
            return _error_response(
                payload, 
                "INVALID_RUN_ID", 
                "Invalid run_id.",
            )
        if message.startswith("INVALID_ARTIFACT_FILENAME"):
            return _error_response(
                payload,
                "INVALID_ARTIFACT_FILENAME",
                "Invalid artifact filename.",
            )
        if message.startswith("INVALID_OFFLINE_OUTPUTS"):
            return _error_response(
                payload,
                "INVALID_OFFLINE_OUTPUTS",
                "Invalid offline_raw_agent_outputs.",
            )
        if message.startswith("INVALID_TICKER"):
            return _error_response(
                payload, 
                "INVALID_TICKER",
                "Invalid ticker.",
            )
    if isinstance(exc, FileNotFoundError) and "raw_agent_outputs.json" in message:
        return _error_response(
            payload, 
            "RAW_OUTPUT_NOT_FOUND", 
            "Raw agent outputs not found.",
        )
    if isinstance(exc, RuntimeError) and "Real TradingAgents execution is disabled" in message:
        return _error_response(
            payload,
            "REAL_RUN_DISABLED",
            "Real TradingAgents execution is disabled by default.",
        )
    if isinstance(exc, RuntimeError) and message.startswith("OFFLINE_DISABLED"):
        return _error_response(
            payload, 
            "OFFLINE_DISABLED", 
            "Offline outputs are disabled.",
        )
    return _error_response(
        payload, 
        "INTERNAL_ERROR", 
        "Research request failed.",
        )

# Create an offline research run with provided payload and save outputs.
def _create_offline_run(payload, output_root):
    payload = _normalize_payload(payload)
    run_id = str(payload.get("run_id") or uuid4())
    ticker = validate_ticker(payload.get("ticker"))
    run_dir = run_dir_for(run_id, output_root)
    run_dir.mkdir(parents=True, exist_ok=False)

    raw_outputs = payload.get("offline_raw_agent_outputs")
    if raw_outputs is None:
        raw_outputs = []
    if not isinstance(raw_outputs, list):
        raise ValueError("INVALID_OFFLINE_OUTPUTS: offline_raw_agent_outputs must be a list")
    if len(raw_outputs) > 20:
        raise ValueError("INVALID_OFFLINE_OUTPUTS: too many offline_raw_agent_outputs")

    created_at = _utc_timestamp()
    agent_outputs = []
    for index, raw_record in enumerate(raw_outputs):
        if not isinstance(raw_record, dict):
            raise ValueError("INVALID_OFFLINE_OUTPUTS: each offline output must be a mapping")
        agent = str(raw_record.get("agent") or "offline_agent")
        tradingagents_agent = str(raw_record.get("tradingagents_agent") or agent)
        source_field = str(raw_record.get("source_field") or "offline_raw_agent_outputs")
        agent_outputs.append(
            build_raw_agent_output_record(
                run_id=run_id,
                ticker=ticker,
                agent=agent,
                tradingagents_agent=tradingagents_agent,
                source_field=source_field,
                source_path=source_field,
                source_candidates=[source_field],
                raw_value=raw_record.get("raw_output"),
                created_at=created_at,
                record_suffix=str(index),
            )
        )

    metadata = {
        "run_id": run_id,
        "ticker": ticker,
        "analysis_date": payload.get("analysis_date"),
        "created_at": created_at,
        "selected_analysts": payload.get("selected_analysts", []),
        "source": "COMQUTOR Week 1A offline research entrypoint",
        "output_version": "week1a.api.v1",
        "artifacts": {
            "metadata": True,
            "raw_agent_outputs": True,
            "structured_agent_outputs": False,
            "final_report": False,
        },
    }
    raw_payload = {
        "schema_version": OUTPUT_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "agent_outputs": agent_outputs,
    }
    save_json_record(run_id, "metadata.json", metadata, output_root=output_root)
    save_json_record(run_id, "raw_agent_outputs.json", raw_payload, output_root=output_root)
    return run_id, run_dir

# Count the number of raw agent outputs in the payload.
def _count_raw_outputs(raw_payload):
    outputs = raw_payload.get("agent_outputs", [])
    return len(outputs) if isinstance(outputs, list) else 0

# Count the number of structured outputs in the payload.
def _count_structured_outputs(structured_payload):
    records = structured_payload.get("records", [])
    return len(records) if isinstance(records, list) else 0

# Build a research response payload summarizing the run status and artifacts.
def build_research_response(run_id, output_root="outputs/runs"):
    run_dir = run_dir_for(run_id, output_root)
    metadata_path = run_dir / "metadata.json"
    raw_path = run_dir / "raw_agent_outputs.json"
    structured_path = run_dir / "structured_agent_outputs.json"
    final_report_path = run_dir / "final_report.md"
    # Week 2 artifacts. Presence is reported as booleans only; the paths
    # themselves never leave this function.
    alpha_matches_path = run_dir / "alpha_matches.json"
    extracted_structures_path = run_dir / "extracted_structures.json"
    error_log_path = run_dir / ERROR_LOG_ARTIFACT_PATH
    metadata = load_json_record_if_exists(run_id, "metadata.json", output_root=output_root)
    raw_payload = load_json_record_if_exists(
        run_id,
        "raw_agent_outputs.json",
        output_root=output_root,
    )
    structured_payload = load_json_record_if_exists(
        run_id,
        "structured_agent_outputs.json",
        output_root=output_root,
    )
    ticker = metadata.get("ticker") or raw_payload.get("ticker") or structured_payload.get("ticker")
    artifacts = {
        "metadata": metadata_path.exists(),
        "raw_agent_outputs": raw_path.exists(),
        "structured_agent_outputs": structured_path.exists(),
        "final_report": final_report_path.exists(),
        "alpha_matches": alpha_matches_path.exists(),
        "extracted_structures": extracted_structures_path.exists(),
        "structured_output_error_logs": error_log_path.exists(),
    }

    return {
        "run_id": run_id,
        "ticker": ticker,
        "status": "completed" if raw_path.exists() and structured_path.exists() else "partial",
        "artifacts": artifacts,
        "agent_output_count": _count_raw_outputs(raw_payload),
        "structured_output_count": _count_structured_outputs(structured_payload),
    }

# Run a research request with the given payload, optionally using a custom runner.
def run_research_request(payload, runner=None, output_root="outputs/runs"):
    payload = _normalize_payload(payload)
    try:
        payload = {**payload, "ticker": validate_ticker(payload.get("ticker"))}
        if runner is not None:
            run_dir = Path(runner(payload, output_root=output_root))
            run_id = validate_run_id_for_path(run_dir.name)
        elif payload.get("offline_raw_agent_outputs") is not None:
            if os.environ.get("COMQUTOR_ENV", "").strip().lower() == "production":
                raise RuntimeError(
                    "OFFLINE_DISABLED: offline_raw_agent_outputs is not allowed in production"
                )
            run_id, run_dir = _create_offline_run(payload, output_root)
        else:
            from comqutor_alpha.runners.tradingagents_runner import (
                run_original_tradingagents_research,
            )

            run_dir = Path(run_original_tradingagents_research(payload, output_root=output_root))
            run_id = validate_run_id_for_path(run_dir.name)

        raw_path = run_dir / "raw_agent_outputs.json"
        if not raw_path.exists():
            raise FileNotFoundError("raw_agent_outputs.json not found")
        save_structured_agent_outputs(run_dir)
        return build_research_response(run_id, output_root=output_root)
    except Exception as exc:
        error_response = _map_exception_to_error(payload, exc)
        if error_response["error_code"] in _EXPECTED_CLIENT_ERROR_CODES:
            logger.warning(
                "research request rejected (ticker=%s, run_id=%s, error_code=%s)",
                payload.get("ticker"),
                payload.get("run_id"),
                error_response["error_code"],
            )
        else:
            logger.exception(
                "research request failed (ticker=%s, run_id=%s)",
                payload.get("ticker"),
                payload.get("run_id"),
            )
        return error_response

# Retrieve the research run status and artifacts for a given run_id.
def get_research_run(run_id, output_root="outputs/runs"):
    try:
        run_dir = run_dir_for(run_id, output_root)
    except ValueError:
        return {
            "run_id": str(run_id),
            "ticker": None,
            "status": "failed",
            "error_code": "INVALID_RUN_ID",
            "message": "Invalid run_id.",
        }
    if not run_dir.exists():
        return {
            "run_id": str(run_id),
            "ticker": None,
            "status": "failed",
            "error_code": "RUN_NOT_FOUND",
            "message": "Run not found.",
        }
    return build_research_response(str(run_id), output_root=output_root)

# Retrieve the research response for a given run_id, loading from the stored JSON record.
def get_research_response(run_id, output_root="outputs/runs"):
    return load_json_record(run_id, "research_response.json", output_root=output_root)


try:
    from fastapi import APIRouter
    from pydantic import BaseModel

    # Support both Pydantic v2 (field_validator) and v1 (validator) without
    # pinning a new dependency version.
    try:
        from pydantic import field_validator

        def _ticker_field_validator(func):
            return field_validator("ticker")(classmethod(func))

    except ImportError:  # Pydantic v1
        from pydantic import validator

        def _ticker_field_validator(func):
            return validator("ticker", allow_reuse=True)(classmethod(func))

    def _model_to_payload(model):
        # Pydantic v2 uses model_dump(); v1 only has dict().
        dump = getattr(model, "model_dump", None)
        return dump(exclude_none=True) if dump is not None else model.dict(exclude_none=True)
    
    class ResearchRequest(BaseModel):
        ticker: str
        analysis_date: str | None = None
        selected_analysts: list[str] | None = None
        offline_raw_agent_outputs: list[dict] | None = None
        run_id: str | None = None
        # NOTE: allow_real_tradingagents_run and config are intentionally NOT exposed here.
        # Real runs are server-controlled; clients cannot trigger paid LLM/data calls via HTTP.

        @_ticker_field_validator
        def _validate_ticker(cls, value):
            return validate_ticker(value)

    router = APIRouter()

    @router.post("/api/research")
    def post_research(request: ResearchRequest):
        return run_research_request(_model_to_payload(request))

    @router.get("/api/research/{run_id}")
    def get_research_run_route(run_id: str):
        return get_research_run(run_id)

except ImportError:
    router = None
