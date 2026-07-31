"""Week 1A research entrypoint helpers and optional FastAPI routes."""

from __future__ import annotations

import contextlib
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from comqutor_alpha.adapters.tradingagents_output_writer import (
    OUTPUT_VERSION,
    build_raw_agent_output_record,
)
from comqutor_alpha.api.agent_output_reader import get_agent_outputs_response
from comqutor_alpha.conflict_engine.pipeline import run_week4_conflict_pipeline
from comqutor_alpha.data_sanity.pipeline import (
    DATA_SANITY_ARTIFACT_FILENAME,
    MARKET_DATA_SNAPSHOT_ARTIFACT_FILENAME,
    run_data_sanity_stage,
)
from comqutor_alpha.data_sanity.schema import (
    STATUS_NOT_AVAILABLE as DATA_SANITY_STATUS_NOT_AVAILABLE,
)
from comqutor_alpha.graph_engine.evidence_integrity import (
    EVIDENCE_INTEGRITY_SCHEMA_VERSION,
    build_alpha_evidence_integrity_payload,
)
from comqutor_alpha.graph_engine.graph_schema import (
    GraphSchemaContractError,
    primary_activation_version_for,
    validate_structure_graph_contract,
)
from comqutor_alpha.graph_engine.pipeline import (
    build_structure_graph_stage,
    score_and_assemble_structure_graph,
)
from comqutor_alpha.research_lifecycle import (
    RESEARCH_RUN_STATUSES,
    ResearchLifecycleError,
    decode_run_history_cursor,
    encode_run_history_cursor,
    submit_research_request,  # noqa: F401 -- re-exported; POST route now uses research_jobs.enqueue_research_request
)
from comqutor_alpha.storage.db.repository import (
    GraphPersistenceError,
    build_repository_from_env,
    build_write_repository_from_env,
)
from comqutor_alpha.storage.file_store import (
    append_jsonl_record,
    load_json_record,
    load_json_record_if_exists,
    run_dir_for,
    save_json_record,
    validate_run_id_for_path,
)
from comqutor_alpha.structure_engine.alpha_mapper import save_alpha_matches
from comqutor_alpha.structure_engine.structure_extractor import save_extracted_structures
from comqutor_alpha.structure_engine.structured_output_adapter import (
    ERROR_LOG_ARTIFACT_PATH,
    save_structured_agent_outputs,
)
from comqutor_alpha.structure_engine.week2_llm import (
    ERROR_LOG_ARTIFACT_PATH as WEEK2_LLM_ERROR_LOG_ARTIFACT_PATH,
    build_server_week2_llm_gateway,
)

logger = logging.getLogger(__name__)

PIPELINE_ERROR_LOG_ARTIFACT_PATH = "error_logs/week2_pipeline_errors.jsonl"
WEEK3_PIPELINE_ERROR_LOG_ARTIFACT_PATH = "error_logs/week3_pipeline_errors.jsonl"
# Overwritten (not appended) on every Week 3 attempt -- the authoritative
# "did the *latest* attempt succeed" signal. WEEK3_PIPELINE_ERROR_LOG_ARTIFACT_PATH
# stays a pure append-only audit trail of every failure that ever happened;
# it is intentionally never consulted for readiness, so a stale failure from
# an earlier attempt can never keep pinning a since-recovered run to
# partial/not_ready.
WEEK3_PIPELINE_STATUS_ARTIFACT_FILENAME = "week3_pipeline_status.json"
REQUIRED_COMPLETION_ARTIFACTS = (
    "raw_agent_outputs",
    "structured_agent_outputs",
    "alpha_matches",
    "extracted_structures",
)

# Validate and normalize a request ticker.
def validate_ticker(raw):
    """Validate and normalize through TradingAgents' Yahoo-symbol contract."""
    if not isinstance(raw, str) or not raw:
        raise ValueError("INVALID_TICKER: ticker is required")
    if raw != raw.strip() or any(char.isspace() or ord(char) < 32 for char in raw):
        raise ValueError("INVALID_TICKER: ticker contains whitespace or control characters")
    if ".." in raw:
        raise ValueError("INVALID_TICKER: ticker contains a path traversal segment")

    try:
        from tradingagents.dataflows.symbol_utils import is_yahoo_safe, normalize_symbol
        from tradingagents.dataflows.utils import safe_ticker_component

        safe_ticker_component(raw, max_len=32)
        ticker = normalize_symbol(raw)
        if not isinstance(ticker, str) or not is_yahoo_safe(ticker):
            raise ValueError("unsafe normalized ticker")
        safe_ticker_component(ticker, max_len=32)
    except (TypeError, ValueError) as exc:
        raise ValueError("INVALID_TICKER: ticker is not a safe Yahoo-style symbol") from exc
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
        "INVALID_ANALYST_SELECTION",
        "REAL_RUN_DISABLED",
        "OFFLINE_DISABLED",
        "RAW_OUTPUT_NOT_FOUND",
    }
)

# Map known exceptions to standardized error responses.
def _map_exception_to_error(payload, exc):
    message = str(exc)
    if isinstance(exc, GraphPersistenceError) and exc.reason_code == "AGENT_OUTPUTS_DB_WRITE_FAILED":
        return _error_response(
            payload,
            "AGENT_OUTPUTS_DB_WRITE_FAILED",
            "Structured agent outputs could not be persisted.",
        )
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
        if message.startswith("INVALID_ANALYST_SELECTION"):
            return _error_response(
                payload,
                "INVALID_ANALYST_SELECTION",
                "Invalid analyst selection.",
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
            "alpha_matches": False,
            "extracted_structures": False,
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

# Deterministic, no-LLM, no-network summary text for the canonical research
# response (W4.3). Exact wording is a frozen contract -- see
# docs/w4_3_gate_contract.md section 3. Never generates a trade
# recommendation (Buy/Sell/Hold, position sizing, price target).
def _build_research_summary(conflict_status, main_conflict, dominant_alphas):
    if conflict_status != "ready":
        return "Conflict analysis is not ready for this research run."
    if main_conflict is not None:
        return main_conflict.get("explanation")
    if dominant_alphas:
        return (
            "Dominant Alpha structures were identified, but no "
            "taxonomy-declared conflict was admitted for this research run."
        )
    return (
        "No dominant Alpha structure or admitted conflict was identified "
        "for this research run."
    )


# Read this run's persisted dominant_alphas/main_conflict/conflict_status
# straight from the database (W4.2's source of truth) -- never recomputed,
# never read from a local conflicts.json (none is ever written). Guarded so
# any storage failure degrades to "not_ready"/empty/null rather than
# propagating -- the same safe-degrade contract as the rest of this module.
def _load_week4_response_fields(run_id, output_root, graph_repository):
    dominant_alphas = []
    main_conflict = None
    conflict_status = "not_ready"
    try:
        repository = graph_repository or build_repository_from_env(output_root)
        graph_row = repository.get_graph(run_id)
        if graph_row is not None:
            graph_json = graph_row.get("graph_json")
            if isinstance(graph_json, dict) and isinstance(graph_json.get("dominant_alphas"), list):
                dominant_alphas = graph_json["dominant_alphas"]
        conflict_result = repository.get_week4_conflict_result(run_id)
        if conflict_result is not None:
            conflict_status = "ready"
            main_conflict = conflict_result.get("main_conflict")
    except GraphPersistenceError as exc:
        logger.warning(
            "week4 response enrichment failed (run_id=%s, reason_code=%s)", run_id, exc.reason_code
        )
    except Exception as exc:
        logger.warning(
            "week4 response enrichment failed unexpectedly (run_id=%s, exc_type=%s)",
            run_id,
            type(exc).__name__,
        )
    return dominant_alphas, main_conflict, conflict_status


_UNSAFE_DATA_SANITY_DETAIL_MARKERS = (
    "/users/", "/home/", "/private/", "postgresql://", "traceback",
    "api_key", "password", "secret", "bearer ", "cookie",
)


def _sanitize_data_sanity_detail_value(value):
    """Defense in depth against a corrupted/foreign data_sanity.json: even
    though this codebase's own warning builders never write a raw
    exception/path/credential into ``details``, the public API additionally
    strips any string value that looks like one before it can ever reach a
    caller."""
    if isinstance(value, str):
        lowered = value.lower()
        if any(marker in lowered for marker in _UNSAFE_DATA_SANITY_DETAIL_MARKERS):
            return None
        return value
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            safe_item = _sanitize_data_sanity_detail_value(item)
            if safe_item is not None:
                cleaned[key] = safe_item
        return cleaned
    if isinstance(value, list):
        return [item for item in (_sanitize_data_sanity_detail_value(v) for v in value) if item is not None]
    return value


def _public_data_sanity_warning(warning):
    """Only ever forwards the four safe fields -- never a provider
    exception, stack trace, full market_data_snapshot, or local file path.
    A malformed warning entry (from a corrupted/foreign artifact) is
    dropped rather than partially trusted."""
    if not isinstance(warning, dict):
        return None
    code = warning.get("code")
    severity = warning.get("severity")
    message = warning.get("message")
    details = warning.get("details")
    if not isinstance(code, str) or not isinstance(severity, str) or not isinstance(message, str):
        return None
    safe_details = _sanitize_data_sanity_detail_value(details) if isinstance(details, dict) else {}
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "details": safe_details,
    }


# Additive Data Sanity Cross-Check v1 fields for the canonical Research
# response. A run with no data_sanity.json (historical, predates this
# feature) reports "not_available" -- never guessed or backfilled.
def _public_data_sanity_fields(run_id, output_root):
    payload = load_json_record_if_exists(run_id, DATA_SANITY_ARTIFACT_FILENAME, output_root=output_root)
    if not payload:
        return {
            "data_sanity_status": DATA_SANITY_STATUS_NOT_AVAILABLE,
            "data_sanity_warning_count": 0,
            "data_sanity_critical_count": 0,
            "data_sanity_warnings": [],
        }
    summary = payload.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    raw_warnings = payload.get("warnings")
    raw_warnings = raw_warnings if isinstance(raw_warnings, list) else []
    public_warnings = [w for w in (_public_data_sanity_warning(w) for w in raw_warnings) if w is not None]
    return {
        "data_sanity_status": payload.get("status") or DATA_SANITY_STATUS_NOT_AVAILABLE,
        "data_sanity_warning_count": int(summary.get("warning_count") or 0),
        "data_sanity_critical_count": int(summary.get("critical_count") or 0),
        "data_sanity_warnings": public_warnings,
    }


# Build a research response payload summarizing the run status and artifacts.
def build_research_response(run_id, output_root="outputs/runs", *, graph_repository=None):
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
    week2_llm_error_log_path = run_dir / WEEK2_LLM_ERROR_LOG_ARTIFACT_PATH
    pipeline_error_log_path = run_dir / PIPELINE_ERROR_LOG_ARTIFACT_PATH
    # Week 3: same filesystem-only pattern as above. "Ready" means the graph
    # artifact was written AND the most recent Week 3 attempt for this run
    # recorded success -- both conditions hold for every real run (this
    # pipeline always attempts Week 3 once Week 1-2 succeed, and always ends
    # every attempt by recording its own outcome), so this is a reliable,
    # DB-free signal that GET .../graph will actually have something to
    # return. The status marker is overwritten (never appended) each
    # attempt, so a successful retry always supersedes an earlier failure;
    # the separate WEEK3_PIPELINE_ERROR_LOG_ARTIFACT_PATH remains a pure
    # append-only audit trail and is deliberately not consulted here.
    structure_graph_path = run_dir / "structure_graph.json"
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
        "week2_llm_error_logs": week2_llm_error_log_path.exists(),
        "week2_pipeline_error_logs": pipeline_error_log_path.exists(),
    }
    complete = all(artifacts[name] for name in REQUIRED_COMPLETION_ARTIFACTS)
    has_any = any(artifacts[name] for name in REQUIRED_COMPLETION_ARTIFACTS)

    week3_status = load_json_record_if_exists(
        run_id, WEEK3_PIPELINE_STATUS_ARTIFACT_FILENAME, output_root=output_root
    )
    structure_graph_ready = structure_graph_path.exists() and week3_status.get("outcome") == "success"

    # W4.3: Week 4 fields are read straight from the database (its source of
    # truth) only when Week 3 actually succeeded -- a Week 3 failure means
    # Week 4 was never even attempted (see _run_week3_graph_pipeline), so
    # there is nothing to query and conflict_status stays "not_ready".
    dominant_alphas, main_conflict, conflict_status = (
        _load_week4_response_fields(run_id, output_root, graph_repository)
        if structure_graph_ready
        else ([], None, "not_ready")
    )

    # "completed" now requires Week 3 (graph build + activation scoring +
    # persistence) *and* Week 4 (conflict detection + persistence) to have
    # actually succeeded, not just Week 1-2. A Week 3 failure, or a Week 3
    # success followed by a Week 4 failure, both degrade status to "partial"
    # (reusing the existing partial/degraded vocabulary) rather than
    # silently reporting completed with a broken/missing graph or conflict
    # result. A Week 4 run that legitimately found zero admitted conflicts
    # is NOT a Week 4 failure -- conflict_status is "ready" either way, so
    # it never blocks "completed" on its own.
    if complete and structure_graph_ready and conflict_status == "ready":
        status = "completed"
    elif complete or has_any:
        status = "partial"
    else:
        status = "failed"

    summary = _build_research_summary(conflict_status, main_conflict, dominant_alphas)

    return {
        "run_id": run_id,
        "ticker": ticker,
        "status": status,
        "artifacts": artifacts,
        "agent_output_count": _count_raw_outputs(raw_payload),
        "structured_output_count": _count_structured_outputs(structured_payload),
        # Stable, additive Week 3 status contract. "ready" means GET
        # .../graph can return the persisted graph for this run_id right
        # now; "not_ready" covers every degraded/failed Week 3 case (never
        # attempted, construction/scoring/persistence failure) uniformly --
        # callers needing the specific reason should query GET .../graph,
        # which has its own richer, still-safe error_code contract.
        "structure_graph_status": "ready" if structure_graph_ready else "not_ready",
        # W4.3 additive fields (see docs/w4_3_gate_contract.md section 3).
        # dominant_alphas comes straight from the persisted Structure Graph,
        # never recomputed/re-sorted here.
        "dominant_alphas": dominant_alphas,
        "main_conflict": main_conflict,
        "conflict_status": conflict_status,
        "summary": summary,
        # Data Sanity Cross-Check v1 additive fields -- an independent
        # cross-validation warning, never a change to claims/Activation/
        # Graph/Conflict, and never blocks "completed".
        **_public_data_sanity_fields(run_id, output_root),
    }

# Run a research request with the given payload, optionally using a custom runner.
def _log_pipeline_error(
    run_id,
    output_root,
    stage,
    error_code="WEEK2_ARTIFACT_GENERATION_FAILED",
):
    append_jsonl_record(
        run_id,
        PIPELINE_ERROR_LOG_ARTIFACT_PATH,
        {
            "run_id": run_id,
            "stage": stage,
            "error_code": error_code,
            "created_at": _utc_timestamp(),
        },
        output_root=output_root,
    )


def _write_week3_pipeline_status(run_id, output_root, *, outcome, stage=None):
    """Overwrite this run's Week 3 status marker with the latest attempt's
    outcome. Never appended -- a later successful attempt always supersedes
    an earlier failure, which is what lets ``build_research_response``
    recover to "completed"/"ready" after a retry without ever consulting
    (or needing to clean up) the append-only failure log."""
    save_json_record(
        run_id,
        WEEK3_PIPELINE_STATUS_ARTIFACT_FILENAME,
        {
            "run_id": run_id,
            "outcome": outcome,
            "stage": stage,
            "updated_at": _utc_timestamp(),
        },
        output_root=output_root,
    )


def _log_week3_pipeline_error(run_id, output_root, stage):
    # Safe audit fields only (run_id/stage/stable error_code/timestamp) --
    # never the triggering exception's text, type, or traceback. This is the
    # only thing recorded for a Week 3 stage failure; nothing about a Week 3
    # failure is ever passed to `logging` at all, so there is no leakage
    # surface to guard there.
    append_jsonl_record(
        run_id,
        WEEK3_PIPELINE_ERROR_LOG_ARTIFACT_PATH,
        {
            "run_id": run_id,
            "stage": stage,
            "error_code": "WEEK3_GRAPH_GENERATION_FAILED",
            "created_at": _utc_timestamp(),
        },
        output_root=output_root,
    )
    logger.warning("week3 pipeline stage failed (run_id=%s, stage=%s)", run_id, stage)
    _write_week3_pipeline_status(run_id, output_root, outcome="failed", stage=stage)


def _report_progress_stage(progress_reporter, stage):
    """Best-effort progress advance -- a reporter's own persistence errors
    are already swallowed inside it, but this guard also keeps a defective
    injected reporter from ever failing the pipeline."""
    if progress_reporter is None:
        return
    try:
        progress_reporter.record_stage(stage)
    except Exception as exc:
        logger.warning(
            "progress stage report failed (stage=%s, exc_type=%s)", stage, type(exc).__name__
        )


def _run_week1_week2_artifact_pipeline(
    run_dir,
    llm_gateway=None,
    *,
    graph_repository=None,
    progress_reporter=None,
):
    run_dir = Path(run_dir).expanduser().resolve()
    run_id = validate_run_id_for_path(run_dir.name)
    output_root = run_dir.parent

    try:
        save_structured_agent_outputs(run_dir, llm_gateway=llm_gateway)
    except Exception:
        _log_pipeline_error(run_id, output_root, "structured_agent_outputs")
        return
    _report_progress_stage(progress_reporter, "structured_claims")

    try:
        structured_payload = load_json_record(
            run_id, "structured_agent_outputs.json", output_root=output_root
        )
        repository = graph_repository or build_write_repository_from_env(output_root)
        repository.persist_agent_outputs(
            run_id=run_id,
            ticker=structured_payload.get("ticker"),
            structured_payload=structured_payload,
        )
    except Exception as exc:
        _log_pipeline_error(
            run_id,
            output_root,
            "agent_outputs_persistence",
            "AGENT_OUTPUTS_DB_WRITE_FAILED",
        )
        logger.warning(
            "structured agent output persistence failed "
            "(run_id=%s, stage=%s, reason_code=%s, exc_type=%s)",
            run_id,
            "agent_outputs_persistence",
            "AGENT_OUTPUTS_DB_WRITE_FAILED",
            type(exc).__name__,
        )
        raise GraphPersistenceError("AGENT_OUTPUTS_DB_WRITE_FAILED") from exc

    for stage, writer in (
        ("alpha_matches", save_alpha_matches),
        ("extracted_structures", save_extracted_structures),
    ):
        try:
            writer(run_id, output_root=output_root, llm_gateway=llm_gateway)
        except Exception:
            _log_pipeline_error(run_id, output_root, stage)
        else:
            if stage == "alpha_matches":
                _report_progress_stage(progress_reporter, "alpha_mapping")


RUN_AUDIT_SCHEMA_VERSION = "structure_correctness.run_audit.v1"
RUN_AUDIT_ARTIFACT_FILENAME = "run_audit.json"


def build_run_audit_payload(run_id, output_root, *, conflict_count=None):
    """Assemble the additive run-level data-quality audit (run_audit.json).

    Every count is computed from this run's real artifacts -- never
    hardcoded. Purely additive: no existing artifact schema is changed, and
    a warning here never flips a genuinely completed run to failed.
    """
    metadata = load_json_record_if_exists(run_id, "metadata.json", output_root=output_root)
    raw_payload = load_json_record_if_exists(run_id, "raw_agent_outputs.json", output_root=output_root)
    structured_payload = load_json_record_if_exists(
        run_id, "structured_agent_outputs.json", output_root=output_root
    )
    matches_payload = load_json_record_if_exists(run_id, "alpha_matches.json", output_root=output_root)
    graph_payload = load_json_record_if_exists(run_id, "structure_graph.json", output_root=output_root)
    data_sanity_payload = load_json_record_if_exists(
        run_id, DATA_SANITY_ARTIFACT_FILENAME, output_root=output_root
    )
    market_data_snapshot_payload = load_json_record_if_exists(
        run_id, MARKET_DATA_SNAPSHOT_ARTIFACT_FILENAME, output_root=output_root
    )

    raw_outputs = raw_payload.get("agent_outputs")
    raw_agent_output_count = len(raw_outputs) if isinstance(raw_outputs, list) else 0

    records = structured_payload.get("records")
    valid_claim_count = len(records) if isinstance(records, list) else 0
    structured_metadata = structured_payload.get("metadata")
    structured_metadata = structured_metadata if isinstance(structured_metadata, dict) else {}
    raw_claim_count = int(structured_metadata.get("raw_claim_count") or valid_claim_count)
    boilerplate_removed_count = int(structured_metadata.get("boilerplate_removed_count") or 0)
    disclaimer_removed_count = int(structured_metadata.get("disclaimer_removed_count") or 0)
    duplicate_removed_count = int(structured_metadata.get("duplicate_removed_count") or 0)

    # Unified Claim Admissibility and Context-Only Routing Sprint: additive
    # claim-quality counters, read back from structured_agent_outputs.json's
    # own metadata (computed once by the adapter's shared quality gate --
    # never re-derived here).
    analytical_claim_count = int(structured_metadata.get("analytical_claim_count") or 0)
    context_only_claim_count = int(structured_metadata.get("context_only_claim_count") or 0)
    non_substantive_removed_count = int(structured_metadata.get("non_substantive_removed_count") or 0)
    llm_claims_proposed_count = int(structured_metadata.get("llm_claims_proposed_count") or 0)
    llm_claims_removed_count = int(structured_metadata.get("llm_claims_removed_count") or 0)
    deterministic_claims_removed_count = int(
        structured_metadata.get("deterministic_claims_removed_count") or 0
    )
    llm_quality_fallback_count = int(structured_metadata.get("llm_quality_fallback_count") or 0)
    quality_reason_counts = structured_metadata.get("quality_reason_counts")
    quality_reason_counts = quality_reason_counts if isinstance(quality_reason_counts, dict) else {}

    matches = matches_payload.get("matches")
    matches = matches if isinstance(matches, list) else []
    matched_alpha_count = sum(1 for m in matches if isinstance(m, dict) and m.get("match_status") == "matched")
    ambiguous_alpha_count = sum(
        1 for m in matches if isinstance(m, dict) and m.get("match_status") == "ambiguous"
    )
    no_match_count = sum(1 for m in matches if isinstance(m, dict) and m.get("match_status") == "no_match")

    graph_metrics = graph_payload.get("graph_metrics")
    graph_metrics = graph_metrics if isinstance(graph_metrics, dict) else {}
    graph_node_count = int(graph_metrics.get("node_count") or 0)
    graph_edge_count = int(graph_metrics.get("edge_count") or 0)
    rejected_edges = graph_metrics.get("rejected_edges")
    rejected_edge_count = (
        sum(int(v or 0) for v in rejected_edges.values()) if isinstance(rejected_edges, dict) else 0
    )

    activation = graph_payload.get("activation")
    alphas = activation.get("alphas") if isinstance(activation, dict) else None
    alphas = alphas if isinstance(alphas, list) else []
    dominant_alpha_count = sum(1 for a in alphas if isinstance(a, dict) and a.get("status") == "dominant")
    regime_level_alpha_count = sum(
        1 for a in alphas if isinstance(a, dict) and a.get("status") == "regime_level"
    )
    high_activation_count = sum(
        1
        for a in alphas
        if isinstance(a, dict)
        and isinstance(a.get("activation_score"), (int, float))
        and a["activation_score"] >= 85
    )

    # Versioned-activation audit counters (Activation v2 sprint). Computed
    # from the persisted graph's activation_versions when present; a
    # v1-only historical graph reports zeros for the v2-specific counters.
    def _alphas_for_version(version_key):
        versions = graph_payload.get("activation_versions")
        if not isinstance(versions, dict):
            return []
        block = versions.get(version_key)
        entries = block.get("alphas") if isinstance(block, dict) else None
        return [a for a in entries if isinstance(a, dict)] if isinstance(entries, list) else []

    primary_activation_version = (
        primary_activation_version_for(graph_payload) if isinstance(graph_payload, dict) else None
    )
    v1_alphas = _alphas_for_version("v1")
    v2_alphas = _alphas_for_version("v2")
    activation_v1_regime_level_count = sum(
        1 for a in v1_alphas if a.get("status") == "regime_level"
    )
    activation_v2_regime_level_count = sum(
        1 for a in v2_alphas if a.get("status") == "regime_level"
    )
    # "Capped" means the score was actually reduced (cap_was_binding), not
    # merely that some cap's condition was eligible/applicable -- an
    # eligible ceiling above the uncapped score changed nothing.
    activation_v2_capped_alpha_count = sum(
        1 for a in v2_alphas if a.get("cap_was_binding") is True
    )
    activation_v2_regime_gate_failure_count = sum(
        1 for a in v2_alphas if a.get("regime_gate_failures")
    )

    # Data Sanity Cross-Check v1 (additive, independent sidecar). A run that
    # predates this feature or had it disabled simply has no data_sanity.json
    # -- reported as "not_available" here too, never guessed/backfilled.
    data_sanity_summary = data_sanity_payload.get("summary")
    data_sanity_summary = data_sanity_summary if isinstance(data_sanity_summary, dict) else {}
    data_sanity_status = data_sanity_payload.get("status") or DATA_SANITY_STATUS_NOT_AVAILABLE
    data_sanity_warning_count = int(data_sanity_summary.get("warning_count") or 0)
    data_sanity_critical_count = int(data_sanity_summary.get("critical_count") or 0)
    reported_price_check_count = int(data_sanity_summary.get("reported_price_check_count") or 0)
    market_data_rows = market_data_snapshot_payload.get("rows")
    market_data_row_count = len(market_data_rows) if isinstance(market_data_rows, list) else 0

    warnings = []
    expected_agents = metadata.get("agents")
    if isinstance(expected_agents, list) and expected_agents and raw_agent_output_count < len(expected_agents):
        warnings.append("MISSING_EXPECTED_AGENT_OUTPUTS")
    if boilerplate_removed_count > 0:
        warnings.append("BOILERPLATE_REMOVED")
    if duplicate_removed_count > 0:
        warnings.append("DUPLICATES_REMOVED")
    if graph_node_count > 0 and graph_edge_count == 0:
        warnings.append("INSUFFICIENT_STRUCTURAL_RELATIONS")
    if graph_edge_count == 0:
        warnings.append("NO_GRAPH_EDGES")
    if high_activation_count > 0 and graph_edge_count == 0:
        warnings.append("HIGH_ACTIVATION_WITHOUT_GRAPH_SUPPORT")

    ticker = metadata.get("ticker") or structured_payload.get("ticker") or graph_payload.get("ticker")

    # Regime Evidence Integrity Shadow Layer (Product Findings Closure and
    # Regime Evidence Integrity Sprint, Track B): an additive, internal-only
    # diagnostic block -- never surfaced through any public Research API or
    # Agent Findings projector (this function's own output, run_audit.json,
    # has no GET route). Computed from exactly the artifacts already loaded
    # above; never a second read, never a database write, never a change to
    # John's production Activation score/status/regime gate
    # (activation_scorer_v2.py is not imported here and is never called by
    # this block). A defect in this shadow analysis must never take down
    # the rest of this already-valuable audit payload.
    alpha_evidence_integrity = None
    try:
        if isinstance(records, list) and v2_alphas and isinstance(matches_payload, dict):
            graph_edges = graph_payload.get("edges")
            graph_edges = graph_edges if isinstance(graph_edges, list) else []
            alpha_evidence_integrity = build_alpha_evidence_integrity_payload(
                run_id=run_id,
                ticker=str(ticker or ""),
                alpha_matches_payload=matches_payload,
                activation_v2_alphas=v2_alphas,
                graph_edges=graph_edges,
                structured_records=records,
            )
    except Exception as exc:
        logger.warning(
            "evidence integrity shadow analysis failed "
            "(run_id=%s, stage=%s, exc_type=%s)",
            run_id,
            "alpha_evidence_integrity",
            type(exc).__name__,
        )
        alpha_evidence_integrity = {
            "schema_version": EVIDENCE_INTEGRITY_SCHEMA_VERSION,
            "run_id": run_id,
            "ticker": ticker,
            "status": "unavailable",
        }

    return {
        "schema_version": RUN_AUDIT_SCHEMA_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "raw_agent_output_count": raw_agent_output_count,
        "raw_claim_count": raw_claim_count,
        "boilerplate_removed_count": boilerplate_removed_count,
        "disclaimer_removed_count": disclaimer_removed_count,
        "duplicate_removed_count": duplicate_removed_count,
        "valid_claim_count": valid_claim_count,
        "matched_alpha_count": matched_alpha_count,
        "ambiguous_alpha_count": ambiguous_alpha_count,
        "no_match_count": no_match_count,
        "graph_node_count": graph_node_count,
        "graph_edge_count": graph_edge_count,
        "rejected_edge_count": rejected_edge_count,
        "dominant_alpha_count": dominant_alpha_count,
        "regime_level_alpha_count": regime_level_alpha_count,
        "conflict_count": int(conflict_count or 0),
        "primary_activation_version": primary_activation_version,
        "activation_v1_regime_level_count": activation_v1_regime_level_count,
        "activation_v2_regime_level_count": activation_v2_regime_level_count,
        "activation_v2_capped_alpha_count": activation_v2_capped_alpha_count,
        "activation_v2_regime_gate_failure_count": activation_v2_regime_gate_failure_count,
        "data_sanity_status": data_sanity_status,
        "data_sanity_warning_count": data_sanity_warning_count,
        "data_sanity_critical_count": data_sanity_critical_count,
        "market_data_row_count": market_data_row_count,
        "reported_price_check_count": reported_price_check_count,
        # Unified Claim Admissibility and Context-Only Routing Sprint:
        # additive claim-quality audit counters (see
        # structured_output_adapter.adapt_run_outputs's own metadata).
        "analytical_claim_count": analytical_claim_count,
        "context_only_claim_count": context_only_claim_count,
        "non_substantive_removed_count": non_substantive_removed_count,
        "llm_claims_proposed_count": llm_claims_proposed_count,
        "llm_claims_removed_count": llm_claims_removed_count,
        "deterministic_claims_removed_count": deterministic_claims_removed_count,
        "llm_quality_fallback_count": llm_quality_fallback_count,
        "quality_reason_counts": quality_reason_counts,
        "warnings": warnings,
        # Regime Evidence Integrity Shadow Layer (Track B): additive,
        # internal-only. None when the graph/activation v2 artifacts are not
        # yet available for this run (e.g. Week 3 has not completed).
        "alpha_evidence_integrity": alpha_evidence_integrity,
    }


def write_run_audit_artifact(run_id, output_root, *, conflict_count=None):
    """Write run_audit.json into the run directory.

    Goes through the formal ``file_store`` boundary: ``run_audit.json`` is
    on the artifact filename allowlist, and ``save_json_record`` provides
    run_id validation, traversal protection, and the atomic write.
    """
    payload = build_run_audit_payload(run_id, output_root, conflict_count=conflict_count)
    save_json_record(run_id, RUN_AUDIT_ARTIFACT_FILENAME, payload, output_root=output_root)
    return payload


def _run_week3_graph_pipeline(run_dir, *, graph_repository=None, progress_reporter=None):
    """Build, persist (file + DB), and score the Week 3 Structure Graph.

    Only runs after Week 1-2 artifacts exist; any failure at any step is
    caught, logged with a stable safe reason code, and never propagates --
    a Week 3 failure must never take down or alter the Week 1-2 response.
    Progress stages are reported strictly *after* their real step succeeds,
    so a Graph/Conflict failure can never show a fabricated 100%.
    """
    run_dir = Path(run_dir).expanduser().resolve()
    run_id = validate_run_id_for_path(run_dir.name)
    output_root = run_dir.parent

    try:
        alpha_matches_payload = load_json_record(run_id, "alpha_matches.json", output_root=output_root)
        extracted_structures_payload = load_json_record(
            run_id, "extracted_structures.json", output_root=output_root
        )
        metadata = load_json_record_if_exists(run_id, "metadata.json", output_root=output_root)
        run_timestamp = metadata.get("analysis_date") or metadata.get("created_at")
        # Structured records feed Activation v2's semantic dedupe
        # (duplicate_group_id) and ticker-specificity (entities). Optional:
        # a missing artifact degrades to the scorer's own text-based
        # fallbacks, never a failure.
        structured_payload = load_json_record_if_exists(
            run_id, "structured_agent_outputs.json", output_root=output_root
        )
        structured_records = structured_payload.get("records")
        if not isinstance(structured_records, list):
            structured_records = []
    except Exception:
        _log_week3_pipeline_error(run_id, output_root, "structure_graph_inputs")
        return

    try:
        graph = build_structure_graph_stage(alpha_matches_payload, extracted_structures_payload)
    except Exception:
        _log_week3_pipeline_error(run_id, output_root, "structure_graph_construction")
        return
    _report_progress_stage(progress_reporter, "structure_graph")

    try:
        graph_payload = score_and_assemble_structure_graph(
            graph,
            alpha_matches_payload,
            extracted_structures_payload,
            run_timestamp=run_timestamp,
            structured_records=structured_records,
        )
    except Exception:
        _log_week3_pipeline_error(run_id, output_root, "activation_scoring")
        return
    _report_progress_stage(progress_reporter, "activation_scoring")

    try:
        save_json_record(run_id, "structure_graph.json", graph_payload, output_root=output_root)
    except Exception:
        _log_week3_pipeline_error(run_id, output_root, "structure_graph_artifact_write")
        return

    ticker = graph_payload.get("ticker") or metadata.get("ticker")
    try:
        # build_write_repository_from_env (not the read-only
        # build_repository_from_env) is deliberate: only this write pipeline
        # may provision the local SQLite file/directory or apply schema
        # migrations. GET .../graph must never do either.
        repository = graph_repository or build_write_repository_from_env(output_root)
        repository.persist_run(
            run_id=run_id,
            ticker=ticker,
            alpha_matches_payload=alpha_matches_payload,
            graph_payload=graph_payload,
        )
    except Exception:
        _log_week3_pipeline_error(run_id, output_root, "structure_graph_persistence")
        return

    # Best-effort marker only: Week 1-2 succeeded and the graph is fully
    # built/scored/persisted at this point, so a failure writing this last
    # bookkeeping file must not be surfaced as a request failure -- worst
    # case, a stale/missing marker just under-reports readiness until the
    # next successful attempt overwrites it.
    with contextlib.suppress(Exception):
        _write_week3_pipeline_status(run_id, output_root, outcome="success")

    # Week 4 (W4.3): only ever reached after Week 3's graph has actually
    # been built, scored, and persisted above -- reuses the exact same
    # repository handle (no second repository abstraction, no duplicate
    # connection) and the exact same graph_payload["activation"] this
    # request just computed (no recomputation). Never allowed to affect the
    # Week 1-3 outcome already established above: run_week4_conflict_pipeline
    # itself never raises, and this call is additionally wrapped so a defect
    # in the Week 4 seam can never take down an already-successful Week 3
    # response.
    week4_succeeded = False
    with contextlib.suppress(Exception):
        week4_succeeded = bool(
            run_week4_conflict_pipeline(
                run_id=run_id,
                ticker=ticker,
                graph_payload=graph_payload,
                alpha_matches_payload=alpha_matches_payload,
                repository=repository,
                output_root=output_root,
            )
        )
    if week4_succeeded:
        # Both progress milestones require the Week 4 detector AND its
        # database persistence to have genuinely succeeded -- a conflict
        # failure keeps progress pinned below 96 rather than faking it.
        _report_progress_stage(progress_reporter, "conflict_analysis")
        _report_progress_stage(progress_reporter, "result_persistence")

    # Additive data-quality audit artifact. Best-effort like the status
    # marker above: an audit write failure never affects the run outcome,
    # and an audit warning never turns a genuinely completed run into a
    # failed one.
    with contextlib.suppress(Exception):
        conflict_count = None
        with contextlib.suppress(Exception):
            conflict_result = repository.get_week4_conflict_result(run_id)
            if isinstance(conflict_result, dict):
                conflicts = conflict_result.get("conflicts")
                conflict_count = len(conflicts) if isinstance(conflicts, list) else 0
        write_run_audit_artifact(run_id, output_root, conflict_count=conflict_count)


def run_research_request(
    payload,
    runner=None,
    output_root="outputs/runs",
    *,
    week2_llm_gateway=None,
    graph_repository=None,
    progress_reporter=None,
):
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
        elif payload.get("allow_real_tradingagents_run") is True and payload.get("final_state") is None:
            # W7: the API's real-execution path streams the TradingAgents
            # graph so genuinely-completed agent milestones advance real
            # progress. allow_real_tradingagents_run is set exclusively by
            # the server-side submission gate (research_lifecycle) -- an
            # HTTP request cannot carry it (see ResearchRequest below).
            from comqutor_alpha.runners.tradingagents_runner import (
                run_streaming_tradingagents_research,
            )

            run_dir = Path(
                run_streaming_tradingagents_research(
                    payload, output_root=output_root, progress_reporter=progress_reporter
                )
            )
            run_id = validate_run_id_for_path(run_dir.name)
        else:
            from comqutor_alpha.runners.tradingagents_runner import (
                run_original_tradingagents_research,
            )

            run_dir = Path(run_original_tradingagents_research(payload, output_root=output_root))
            run_id = validate_run_id_for_path(run_dir.name)

        payload = {**payload, "run_id": run_id}
        raw_path = run_dir / "raw_agent_outputs.json"
        if not raw_path.exists():
            raise FileNotFoundError("raw_agent_outputs.json not found")
        _report_progress_stage(progress_reporter, "raw_outputs_saved")
        if week2_llm_gateway is None:
            week2_llm_gateway = build_server_week2_llm_gateway(run_id, run_dir.parent)
        _run_week1_week2_artifact_pipeline(
            run_dir,
            week2_llm_gateway,
            graph_repository=graph_repository,
            progress_reporter=progress_reporter,
        )
        # Data Sanity Cross-Check v1: an independent sidecar stage, run after
        # structured claims exist (so reported-price cross-checks have
        # something to check) and before Graph/Activation (so a Data Sanity
        # defect or a yfinance failure can never affect Alpha Mapping, the
        # Structure Graph, Activation, or Conflict detection, and never
        # changes this request's completion status). run_data_sanity_stage
        # never raises, but this call is additionally wrapped so a defect in
        # the wiring itself can never take down an already-successful
        # Week 1-2 response.
        with contextlib.suppress(Exception):
            run_data_sanity_stage(run_id, output_root)
        # Week 3 graph build/score/persist is a side effect of a successful
        # POST; its own status is reported only via GET .../graph so the
        # frozen Week 1-2 response contract above never changes shape.
        _run_week3_graph_pipeline(
            run_dir, graph_repository=graph_repository, progress_reporter=progress_reporter
        )
        response = build_research_response(
            run_id, output_root=output_root, graph_repository=graph_repository
        )
        return response
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
            logger.error(
                "research request failed "
                "(ticker=%s, run_id=%s, stage=%s, reason_code=%s, exc_type=%s)",
                payload.get("ticker"),
                payload.get("run_id"),
                "research_pipeline",
                error_response["error_code"],
                type(exc).__name__,
            )
        return error_response

# Retrieve the research run status and artifacts for a given run_id.
def get_research_run(run_id, output_root="outputs/runs", *, graph_repository=None):
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
    return build_research_response(str(run_id), output_root=output_root, graph_repository=graph_repository)

# Retrieve the research response for a given run_id, loading from the stored JSON record.
def get_research_response(run_id, output_root="outputs/runs"):
    return load_json_record(run_id, "research_response.json", output_root=output_root)


_GRAPH_ERROR_MESSAGES = {
    "INVALID_RUN_ID": "Invalid run_id.",
    "RUN_NOT_FOUND": "Run not found.",
    "GRAPH_NOT_READY": "Structure graph has not been generated for this run yet.",
    "GRAPH_UNAVAILABLE": "Graph storage is temporarily unavailable.",
    "GRAPH_CORRUPTED": "Persisted graph is missing required fields.",
    "GRAPH_SCHEMA_MISMATCH": "Persisted graph schema is not supported by this server.",
}

# Maps a GraphPersistenceError.reason_code (from either the repository's own
# write/read-time contract check or this module's own re-validation below)
# to the public-facing graph error code. An unknown reason_code is treated
# as a transient/infra failure (GRAPH_UNAVAILABLE), never as corruption --
# only the contract-specific reason codes below indicate corrupted data or
# an unsupported schema version.
_GRAPH_PERSISTENCE_REASON_TO_ERROR_CODE = {
    "DB_DATA_CORRUPTED": "GRAPH_CORRUPTED",
    "GRAPH_SCHEMA_INVALID": "GRAPH_CORRUPTED",
    "GRAPH_SCHEMA_PRIMARY_MISMATCH": "GRAPH_CORRUPTED",
    "GRAPH_SCHEMA_MISMATCH": "GRAPH_SCHEMA_MISMATCH",
}


def _graph_error_response(run_id, ticker, error_code):
    return {
        "run_id": run_id,
        "ticker": ticker,
        "status": "failed",
        "error_code": error_code,
        "message": _GRAPH_ERROR_MESSAGES[error_code],
    }


# Retrieve the exact persisted Structure Graph for a run_id. Pure read path:
# validated run_id -> one DB SELECT -> legacy not-found classification. Never
# invokes TradingAgents/LLM, never rebuilds the graph, never mutates storage.
def get_persisted_structure_graph(run_id, output_root="outputs/runs", *, graph_repository=None):
    try:
        safe_run_id = validate_run_id_for_path(run_id)
    except ValueError:
        return _graph_error_response(str(run_id), None, "INVALID_RUN_ID")

    try:
        repository = graph_repository or build_repository_from_env(output_root)
        row = repository.get_graph(safe_run_id)
    except GraphPersistenceError as exc:
        logger.warning(
            "graph retrieval failed (run_id=%s, reason_code=%s)", safe_run_id, exc.reason_code
        )
        error_code = _GRAPH_PERSISTENCE_REASON_TO_ERROR_CODE.get(exc.reason_code, "GRAPH_UNAVAILABLE")
        return _graph_error_response(safe_run_id, None, error_code)
    except Exception as exc:
        # Anything else (engine construction, filesystem, driver import) must
        # still degrade safely rather than leak a traceback/DSN to the
        # caller -- and, unlike the client response, the *server log* must
        # stay safe by default too: a raw driver/SQLAlchemy exception's text
        # routinely embeds the DSN, host, or username. The default (WARNING)
        # log line below carries only run_id + the exception's type name.
        logger.warning(
            "graph retrieval failed unexpectedly (run_id=%s, exc_type=%s)",
            safe_run_id,
            type(exc).__name__,
        )
        return _graph_error_response(safe_run_id, None, "GRAPH_UNAVAILABLE")

    if row is None:
        run_dir = run_dir_for(safe_run_id, output_root)
        error_code = "GRAPH_NOT_READY" if run_dir.exists() else "RUN_NOT_FOUND"
        return _graph_error_response(safe_run_id, None, error_code)

    graph_json = row.get("graph_json")
    # Single source of truth for graph-contract shape (graph_schema module):
    # explicit per-schema_version required keys, never a startswith/union
    # acceptance, never a guessed version. Re-validated here (in addition to
    # the write-time and repository-read-time checks) so a stub repository
    # (as used in tests) or any other caller that bypasses
    # GraphPersistenceRepository.get_graph is still covered.
    try:
        validate_structure_graph_contract(graph_json)
    except GraphSchemaContractError as exc:
        logger.warning(
            "persisted graph failed contract validation (run_id=%s, reason_code=%s, found=%s)",
            safe_run_id,
            exc.reason_code,
            graph_json.get("schema_version") if isinstance(graph_json, dict) else None,
        )
        error_code = _GRAPH_PERSISTENCE_REASON_TO_ERROR_CODE.get(exc.reason_code, "GRAPH_CORRUPTED")
        return _graph_error_response(safe_run_id, row.get("ticker"), error_code)

    # primary_activation_version is computed strictly per the payload's own
    # schema_version (week3.structure_graph.v1 -> activation.formula_version;
    # .v2 -> its own primary_activation_version field) -- never guessed,
    # never backfilled from one version onto the other.
    activation_block = graph_json.get("activation", {})
    primary_activation_version = primary_activation_version_for(graph_json)
    return {
        "run_id": safe_run_id,
        "ticker": graph_json.get("ticker"),
        "status": "ok",
        "schema_version": graph_json.get("schema_version"),
        "graph_builder_version": graph_json.get("graph_builder_version"),
        "activation_scorer_version": graph_json.get("activation_scorer_version"),
        "nodes": graph_json.get("nodes", []),
        "edges": graph_json.get("edges", []),
        "graph_metrics": graph_json.get("graph_metrics", {}),
        "graph_coherence": graph_json.get("graph_coherence", {}),
        "activation": activation_block,
        "activation_versions": graph_json.get("activation_versions", {}),
        "primary_activation_version": primary_activation_version,
        "dominant_alphas": graph_json.get("dominant_alphas", []),
        "provenance": graph_json.get("provenance", {}),
    }


_CONFLICTS_ERROR_MESSAGES = {
    "INVALID_RUN_ID": "Invalid run_id.",
    "CONFLICTS_NOT_READY": "Conflict analysis has not been generated for this research run yet.",
    "CONFLICTS_UNAVAILABLE": "Conflict storage is temporarily unavailable.",
    "CONFLICTS_CORRUPTED": "Persisted conflict result is missing required fields.",
}


def _conflicts_error_response(run_id, error_code):
    return {
        "run_id": run_id,
        "ticker": None,
        "status": "failed",
        "error_code": error_code,
        "message": _CONFLICTS_ERROR_MESSAGES[error_code],
    }


# Retrieve the exact persisted W4.2 conflict result for a run_id. Pure read
# path: validated run_id -> one DB reconstruction. Deliberately does NOT
# check whether the local run directory exists first -- unlike the graph and
# agent-outputs endpoints, the database is this endpoint's only source of
# truth, so a run whose local directory was deleted must still succeed here
# as long as the database row is intact. Never re-runs the W4.1 detector,
# never reads alpha_matches.json/structure_graph.json, never invokes
# TradingAgents/LLM/network, never performs a migration/DDL/write.
def get_persisted_conflicts(run_id, output_root="outputs/runs", *, graph_repository=None):
    try:
        safe_run_id = validate_run_id_for_path(run_id)
    except ValueError:
        return _conflicts_error_response(str(run_id), "INVALID_RUN_ID")

    try:
        repository = graph_repository or build_repository_from_env(output_root)
        result = repository.get_week4_conflict_result(safe_run_id)
    except GraphPersistenceError as exc:
        logger.warning(
            "conflicts retrieval failed (run_id=%s, reason_code=%s)", safe_run_id, exc.reason_code
        )
        error_code = "CONFLICTS_CORRUPTED" if exc.reason_code == "DB_DATA_CORRUPTED" else "CONFLICTS_UNAVAILABLE"
        return _conflicts_error_response(safe_run_id, error_code)
    except Exception as exc:
        logger.warning(
            "conflicts retrieval failed unexpectedly (run_id=%s, exc_type=%s)",
            safe_run_id,
            type(exc).__name__,
        )
        return _conflicts_error_response(safe_run_id, "CONFLICTS_UNAVAILABLE")

    if result is None:
        return _conflicts_error_response(safe_run_id, "CONFLICTS_NOT_READY")

    # Additive per-conflict bull_evidence/bear_evidence (claim_id, claim
    # text, agent, match score, relation), rebuilt deterministically from
    # the run's persisted alpha_matches rows and the conflict's own
    # bull/bear structures. Never invokes an LLM; a failure here degrades
    # to the unenriched (still valid) payload.
    with contextlib.suppress(Exception):
        _attach_conflict_evidence(result, repository, safe_run_id)

    # Equal to the W4.2 deterministic reconstruction, with additive fields
    # only (status="ok" plus the bull_evidence/bear_evidence lists above) --
    # every other key/value comes straight from `result`, unmodified.
    return {**result, "status": "ok"}


def _match_relation_from_row(match_row, alpha_id):
    candidates = match_row.get("candidate_scores") if isinstance(match_row, dict) else None
    if isinstance(candidates, list):
        for candidate in candidates:
            if isinstance(candidate, dict) and str(candidate.get("alpha_id")) == str(alpha_id):
                return str(candidate.get("relation") or "unknown")
    return "unknown"


def _conflict_side_evidence(structure, match_rows_by_claim, alpha_id):
    """Build one side's evidence list from the conflict's own structure
    (claim_ids/evidence/match_scores are parallel arrays) enriched with the
    per-claim agent and relation from persisted alpha_matches rows. The
    agent always comes from the claim's own match row -- never positionally
    guessed from the structure's deduplicated agents list."""
    claim_ids = structure.get("claim_ids") if isinstance(structure, dict) else None
    if not isinstance(claim_ids, list):
        return []
    evidence_texts = structure.get("evidence") if isinstance(structure.get("evidence"), list) else []
    match_scores = (
        structure.get("match_scores") if isinstance(structure.get("match_scores"), list) else []
    )
    items = []
    for index, claim_id in enumerate(claim_ids):
        claim_id = str(claim_id)
        match_row = match_rows_by_claim.get(claim_id, {})
        claim_text = str(match_row.get("claim_text") or "")
        if not claim_text and index < len(evidence_texts):
            claim_text = str(evidence_texts[index] or "")
        match_score = match_row.get("match_score")
        if match_score is None and index < len(match_scores):
            match_score = match_scores[index]
        items.append(
            {
                "claim_id": claim_id,
                "claim_text": claim_text,
                "agent": str(match_row.get("agent") or ""),
                "match_score": float(match_score or 0.0),
                "relation": _match_relation_from_row(match_row, alpha_id),
            }
        )
    return items


def _attach_conflict_evidence(result, repository, run_id):
    conflicts = result.get("conflicts")
    conflicts = conflicts if isinstance(conflicts, list) else []
    main_conflict = result.get("main_conflict")
    targets = list(conflicts)
    if isinstance(main_conflict, dict):
        targets.append(main_conflict)
    if not targets:
        return

    match_rows_by_claim = {}
    with contextlib.suppress(Exception):
        for row in repository.get_alpha_matches(run_id):
            if isinstance(row, dict) and row.get("claim_id"):
                match_rows_by_claim[str(row["claim_id"])] = row

    for conflict in targets:
        if not isinstance(conflict, dict):
            continue
        bull_structure = conflict.get("bull_structure")
        bear_structure = conflict.get("bear_structure")
        conflict["bull_evidence"] = _conflict_side_evidence(
            bull_structure, match_rows_by_claim, conflict.get("bull_alpha_id")
        )
        conflict["bear_evidence"] = _conflict_side_evidence(
            bear_structure, match_rows_by_claim, conflict.get("bear_alpha_id")
        )


def _isoformat(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


_RUN_STATUS_MESSAGES = {
    "queued": "Research run is queued.",
    "running": "Research run is in progress.",
    "completed": "Research run completed.",
    "partial": "Research run completed partially.",
}


def _public_run_record_fields(record):
    """Project a research_runs row onto the safe public field set shared by
    the status and history endpoints. Never includes request_fingerprint,
    active_fingerprint, provider/model identity, pipeline identity, or any
    offline payload content."""
    status = record.get("status")
    if status == "failed":
        error_code = record.get("error_code")
        message = record.get("error_message") or "Research run failed."
    else:
        error_code = None
        message = _RUN_STATUS_MESSAGES.get(status, "")
    return {
        "run_id": record.get("run_id"),
        "ticker": record.get("ticker"),
        "analysis_date": record.get("analysis_date"),
        "selected_analysts": record.get("selected_analysts") or [],
        "status": status,
        "stage": record.get("stage"),
        "error_code": error_code,
        "message": message,
        "created_at": _isoformat(record.get("created_at")),
        "started_at": _isoformat(record.get("started_at")),
        "completed_at": _isoformat(record.get("completed_at")),
        "updated_at": _isoformat(record.get("updated_at")),
    }


_RUN_STATUS_ERROR_MESSAGES = {
    "INVALID_RUN_ID": "Invalid run_id.",
    "RUN_STATUS_NOT_FOUND": "Run not found.",
    "RUN_STATUS_UNAVAILABLE": "Run status storage is temporarily unavailable.",
    "RUN_STATUS_CORRUPTED": "Persisted run status is missing required fields.",
}


def _run_status_error_response(run_id, error_code):
    return {
        "run_id": run_id,
        "status": "failed",
        "error_code": error_code,
        "message": _RUN_STATUS_ERROR_MESSAGES[error_code],
    }


_RUN_STATUS_REQUIRED_FIELDS = {"run_id", "ticker", "status", "created_at", "updated_at"}

# Minimum matching historical samples before an ETA range may be shown.
# Below this the status endpoint reports eta_status="estimating" and never
# fabricates a countdown.
ETA_MINIMUM_SAMPLE_COUNT = 3


def _as_utc_datetime(value):
    if not hasattr(value, "tzinfo"):
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _elapsed_seconds_for_record(record):
    """Whole seconds from research_runs.started_at to now (running) or to
    completed_at (terminal). None when started_at is missing (still queued)
    or timestamps are unusable -- never a guessed value."""
    started_at = _as_utc_datetime(record.get("started_at"))
    if started_at is None:
        return None
    if record.get("status") in ("completed", "partial", "failed"):
        end = _as_utc_datetime(record.get("completed_at"))
        if end is None:
            return None
    else:
        end = datetime.now(UTC)
    try:
        seconds = (end - started_at).total_seconds()
    except TypeError:
        return None
    return max(0, int(seconds))


def _percentile(sorted_values, fraction):
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = fraction * (len(sorted_values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def _build_progress_and_eta_fields(record, repository):
    """Additive progress/ETA fields for the run status response. Every
    value comes from persisted telemetry or arithmetic over persisted
    timestamps -- nothing here fabricates progress, and ETA ranges only
    appear once at least ETA_MINIMUM_SAMPLE_COUNT genuinely-completed real
    runs with the identical profile and analyst selection exist."""
    from comqutor_alpha.research_profiles import display_name_for_profile_id

    fields = {
        "profile_id": None,
        "profile_display_name": None,
        "progress_percent": None,
        "current_stage": None,
        "completed_units": None,
        "total_units": None,
        "progress_message": None,
        "elapsed_seconds": _elapsed_seconds_for_record(record),
        "eta_status": "unavailable",
        "estimated_remaining_seconds_min": None,
        "estimated_remaining_seconds_max": None,
        "eta_sample_count": 0,
    }

    progress = None
    try:
        progress = repository.get_research_progress(record["run_id"])
    except GraphPersistenceError as exc:
        logger.warning(
            "run progress retrieval failed (run_id=%s, reason_code=%s)",
            record.get("run_id"),
            exc.reason_code,
        )
    except Exception as exc:
        logger.warning(
            "run progress retrieval failed unexpectedly (run_id=%s, exc_type=%s)",
            record.get("run_id"),
            type(exc).__name__,
        )

    if progress is not None:
        fields["profile_id"] = progress.get("profile_id")
        fields["profile_display_name"] = display_name_for_profile_id(progress.get("profile_id"))
        fields["progress_percent"] = progress.get("progress_percent")
        fields["current_stage"] = progress.get("current_stage")
        fields["completed_units"] = progress.get("completed_units")
        fields["total_units"] = progress.get("total_units")
        fields["progress_message"] = progress.get("progress_message")

    status = record.get("status")
    if status in ("completed", "partial"):
        fields["eta_status"] = "complete"
        return fields
    if status == "failed":
        fields["eta_status"] = "unavailable"
        return fields

    # queued/running: ETA history is restricted to normally-completed real
    # runs with the identical profile_id and canonical analyst selection.
    fields["eta_status"] = "estimating"
    if progress is None or not progress.get("profile_id"):
        return fields
    durations = []
    try:
        durations = repository.list_real_completed_run_durations(
            profile_id=progress["profile_id"],
            selected_analysts=record.get("selected_analysts") or [],
        )
    except GraphPersistenceError as exc:
        logger.warning("eta history retrieval failed (reason_code=%s)", exc.reason_code)
    except Exception as exc:
        logger.warning("eta history retrieval failed unexpectedly (exc_type=%s)", type(exc).__name__)

    fields["eta_sample_count"] = len(durations)
    if len(durations) >= ETA_MINIMUM_SAMPLE_COUNT:
        ordered = sorted(durations)
        p25 = _percentile(ordered, 0.25)
        p75 = _percentile(ordered, 0.75)
        elapsed = fields["elapsed_seconds"] or 0
        # Estimated remaining time is clamped at zero -- an overdue run
        # shows "approximately 0" rather than a negative countdown.
        fields["eta_status"] = "available"
        fields["estimated_remaining_seconds_min"] = max(0, int(round(p25 - elapsed)))
        fields["estimated_remaining_seconds_max"] = max(0, int(round(p75 - elapsed)))
    return fields


# Retrieve one run's lifecycle status. Pure read path: validated run_id ->
# DB SELECTs against research_runs/research_run_progress only. Never reads
# raw/structured agent output files, never reads a graph file, never invokes
# an LLM or the network, never performs a migration or a write.
def get_research_run_status(run_id, output_root=None, *, graph_repository=None):
    try:
        safe_run_id = validate_run_id_for_path(run_id)
    except ValueError:
        return _run_status_error_response(str(run_id), "INVALID_RUN_ID")

    try:
        repository = graph_repository or build_repository_from_env(output_root)
        record = repository.get_research_run_record(safe_run_id)
    except GraphPersistenceError as exc:
        logger.warning(
            "run status retrieval failed (run_id=%s, reason_code=%s)", safe_run_id, exc.reason_code
        )
        return _run_status_error_response(safe_run_id, "RUN_STATUS_UNAVAILABLE")
    except Exception as exc:
        logger.warning(
            "run status retrieval failed unexpectedly (run_id=%s, exc_type=%s)",
            safe_run_id,
            type(exc).__name__,
        )
        return _run_status_error_response(safe_run_id, "RUN_STATUS_UNAVAILABLE")

    if record is None:
        return _run_status_error_response(safe_run_id, "RUN_STATUS_NOT_FOUND")
    if not _RUN_STATUS_REQUIRED_FIELDS.issubset(record) or record.get("status") not in RESEARCH_RUN_STATUSES:
        logger.warning("persisted run status is corrupted (run_id=%s)", safe_run_id)
        return _run_status_error_response(safe_run_id, "RUN_STATUS_CORRUPTED")

    response = _public_run_record_fields(record)
    response.update(_build_progress_and_eta_fields(record, repository))
    return response


_RUN_HISTORY_ERROR_MESSAGES = {
    "INVALID_CURSOR": "Invalid cursor.",
    "INVALID_STATUS_FILTER": "Invalid status filter.",
    "INVALID_TICKER": "Invalid ticker.",
    "RUN_HISTORY_UNAVAILABLE": "Run history storage is temporarily unavailable.",
}


def _run_history_error_response(error_code):
    return {
        "status": "failed",
        "error_code": error_code,
        "message": _RUN_HISTORY_ERROR_MESSAGES[error_code],
    }


# List research runs, newest first. Pure read path against research_runs
# only -- never walks the local run directory tree, never touches
# raw/structured artifacts, never migrates or writes. Source of truth is
# exclusively the database.
def get_research_run_history(
    *, limit=20, cursor=None, ticker=None, status=None, output_root=None, graph_repository=None
):
    try:
        safe_limit = int(limit) if limit is not None else 20
    except (TypeError, ValueError):
        safe_limit = 20
    safe_limit = max(1, min(100, safe_limit))

    safe_ticker = None
    if ticker is not None:
        try:
            safe_ticker = validate_ticker(ticker)
        except ValueError:
            return _run_history_error_response("INVALID_TICKER")

    if status is not None and status not in RESEARCH_RUN_STATUSES:
        return _run_history_error_response("INVALID_STATUS_FILTER")

    decoded_cursor = None
    if cursor is not None:
        try:
            decoded_cursor = decode_run_history_cursor(cursor)
        except ResearchLifecycleError:
            return _run_history_error_response("INVALID_CURSOR")

    try:
        repository = graph_repository or build_repository_from_env(output_root)
        records = repository.list_research_run_records(
            limit=safe_limit + 1, cursor=decoded_cursor, ticker=safe_ticker, status=status
        )
    except GraphPersistenceError as exc:
        logger.warning("run history retrieval failed (reason_code=%s)", exc.reason_code)
        return _run_history_error_response("RUN_HISTORY_UNAVAILABLE")
    except Exception as exc:
        logger.warning(
            "run history retrieval failed unexpectedly (exc_type=%s)", type(exc).__name__
        )
        return _run_history_error_response("RUN_HISTORY_UNAVAILABLE")

    has_more = len(records) > safe_limit
    page = records[:safe_limit]
    next_cursor = None
    if has_more and page:
        last = page[-1]
        next_cursor = encode_run_history_cursor(last["created_at"], last["run_id"])

    return {
        "status": "ok",
        "items": [_public_run_record_fields(record) for record in page],
        "next_cursor": next_cursor,
    }


try:
    from fastapi import APIRouter, Request
    from fastapi.responses import JSONResponse
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
        # force_refresh (W5.1A): a cache-operation switch only -- it bypasses
        # completed-run reuse, never active-run (in-flight) de-duplication,
        # and never changes the request fingerprint (see
        # research_lifecycle.build_research_request_identity).
        force_refresh: bool = False
        # NOTE: allow_real_tradingagents_run and config are intentionally NOT exposed here.
        # Real runs are server-controlled; clients cannot trigger paid LLM/data calls via HTTP.

        @_ticker_field_validator
        def _validate_ticker(cls, value):
            return validate_ticker(value)

    router = APIRouter()

    # Stable disposition/error_code -> HTTP status mapping for the async
    # POST route only (GET routes keep their existing "always 200, error
    # detail in body" contract). Every error_code not listed here (e.g.
    # OFFLINE_DISABLED, CACHED_RUN_UNAVAILABLE, INTERNAL_ERROR) is a safe,
    # generic 500 -- never guessed at per-code.
    _RESEARCH_SUBMISSION_ERROR_HTTP_STATUS = {
        "RUN_ID_CONFLICT": 409,
        "INVALID_FORCE_REFRESH": 409,
        "REAL_FORCE_REFRESH_DISABLED": 403,
        "REAL_RUN_DISABLED": 503,
        "REAL_RUN_CONFIG_INVALID": 503,
        "REAL_RUN_CREDENTIAL_MISSING": 503,
        "RESEARCH_QUEUE_FULL": 503,
        "JOB_MANAGER_UNAVAILABLE": 503,
        "INVALID_ANALYST_SELECTION": 400,
        "INVALID_TICKER": 400,
    }

    def _research_submission_http_status(result):
        error_code = result.get("error_code")
        if result.get("status") == "failed" and error_code:
            return _RESEARCH_SUBMISSION_ERROR_HTTP_STATUS.get(error_code, 500)
        if result.get("cache_disposition") == "reused_completed":
            # Canonical result already exists (completed/partial/failed
            # terminal reuse) -- served synchronously, HTTP 200.
            return 200
        # created / force_refreshed / reused_in_flight: accepted for
        # background processing (or already running) -- HTTP 202.
        return 202

    @router.post("/api/research")
    def post_research(request: ResearchRequest, http_request: Request):
        # POST is asynchronous (W5.1B): the pipeline never runs on this
        # request thread. enqueue_research_request claims/reuses exactly
        # like submit_research_request, then hands actual execution off to
        # the app-lifespan-managed background job manager.
        from comqutor_alpha.research_jobs import enqueue_research_request

        job_manager = getattr(http_request.app.state, "job_manager", None)
        output_root = getattr(http_request.app.state, "output_root", None)
        result = enqueue_research_request(
            _model_to_payload(request), output_root=output_root, job_manager=job_manager
        )
        return JSONResponse(content=result, status_code=_research_submission_http_status(result))

    def _request_output_root(http_request: Request):
        # Every read route resolves the *same* output_root/database the
        # background job manager and POST route were configured with (see
        # create_app's ``app.state.output_root``) -- never the function's
        # own literal "outputs/runs" default, which would silently diverge
        # from a server configured with a custom output_root/
        # COMQUTOR_OUTPUT_DIR and make a just-created run invisible to
        # status polling.
        return getattr(http_request.app.state, "output_root", None)

    @router.get("/api/research/{run_id}")
    def get_research_run_route(run_id: str, http_request: Request):
        return get_research_run(run_id, _request_output_root(http_request))

    @router.get("/api/research/{run_id}/graph")
    def get_research_graph_route(run_id: str, http_request: Request):
        return get_persisted_structure_graph(run_id, _request_output_root(http_request))

    @router.get("/api/research/{run_id}/conflicts")
    def get_research_conflicts_route(run_id: str, http_request: Request):
        return get_persisted_conflicts(run_id, _request_output_root(http_request))

    @router.get("/api/research/{run_id}/agent-outputs")
    def get_research_agent_outputs_route(run_id: str, http_request: Request):
        # Pass the app's output_root through unchanged -- including when it
        # is None. Substituting a literal "outputs/runs" here would bypass
        # resolve_output_root(None)'s COMQUTOR_OUTPUT_DIR check, silently
        # diverging this route from every other route/the job manager,
        # which all resolve the same output_root consistently.
        return get_agent_outputs_response(run_id, _request_output_root(http_request))

    @router.get("/api/research/{run_id}/status")
    def get_research_status_route(run_id: str, http_request: Request):
        return get_research_run_status(run_id, _request_output_root(http_request))

    # Registered as a distinct exact path ("/api/research", no trailing
    # segment) -- FastAPI/Starlette route matching is template-exact, so
    # this can never be shadowed by, or shadow, "/api/research/{run_id}"
    # regardless of declaration order (see
    # tests/test_research_runs_api.py::test_history_route_not_swallowed_by_run_id_route).
    @router.get("/api/research")
    def get_research_history_route(
        http_request: Request,
        limit: int = 20,
        cursor: str | None = None,
        ticker: str | None = None,
        status: str | None = None,
    ):
        return get_research_run_history(
            limit=limit, cursor=cursor, ticker=ticker, status=status, output_root=_request_output_root(http_request)
        )

except ImportError:
    router = None
