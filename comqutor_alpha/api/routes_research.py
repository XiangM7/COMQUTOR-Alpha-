"""Week 1A research entrypoint helpers and optional FastAPI routes."""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import subprocess
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
from comqutor_alpha.graph_engine.activation_scorer_v2 import (
    REGIME_GATE_MIN_UNIQUE_EVIDENCE,
)
from comqutor_alpha.graph_engine.evidence_fact_index import (
    ALPHA_ACTIVATION_EVIDENCE_V1,
    select_supporting_alpha_claims,
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
            "data_sanity_numeric_semantics": None,
        }
    summary = payload.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    raw_warnings = payload.get("warnings")
    raw_warnings = raw_warnings if isinstance(raw_warnings, list) else []
    public_warnings = [w for w in (_public_data_sanity_warning(w) for w in raw_warnings) if w is not None]
    # Evidence Integrity Completion Sprint, Track C (additive): aggregate
    # numeric-semantics transparency -- how many reported-price candidates
    # were technical indicators/other non-market-price roles and therefore
    # never eligible for a daily-range warning. Never per-candidate detail
    # (that would need a new persisted artifact); null when the reported-
    # price check did not run for this run.
    numeric_semantics = None
    checks = payload.get("checks")
    if isinstance(checks, list):
        price_check = next(
            (c for c in checks if isinstance(c, dict) and c.get("name") == "reported_price_cross_check"),
            None,
        )
        if isinstance(price_check, dict) and price_check.get("status") == "ok":
            numeric_semantics = {
                "evaluated_count": int(price_check.get("evaluated_count") or 0),
                "daily_range_eligible_count": int(price_check.get("daily_range_eligible_count") or 0),
                "skipped_by_role_count": int(price_check.get("skipped_by_role_count") or 0),
                "semantic_role_counts": price_check.get("semantic_role_counts") or {},
            }
    return {
        "data_sanity_status": payload.get("status") or DATA_SANITY_STATUS_NOT_AVAILABLE,
        "data_sanity_warning_count": int(summary.get("warning_count") or 0),
        "data_sanity_critical_count": int(summary.get("critical_count") or 0),
        "data_sanity_warnings": public_warnings,
        "data_sanity_numeric_semantics": numeric_semantics,
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
    entity_exposure_path = run_dir / "entity_alpha_exposures.json"
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
    exposure_payload = load_json_record_if_exists(
        run_id, "entity_alpha_exposures.json", output_root=output_root
    )
    exposure_records = exposure_payload.get("records")
    exposure_records = exposure_records if isinstance(exposure_records, list) else []

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
        "entity_alpha_exposures": exposure_records,
        "entity_alpha_exposure_status": (
            "ready" if entity_exposure_path.exists() else "unavailable"
        ),
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


RUN_AUDIT_SCHEMA_VERSION = "structure_correctness.run_audit.v2"
RUN_AUDIT_ARTIFACT_FILENAME = "run_audit.json"
# Identifies this audit-consolidation module itself, distinct from every
# per-artifact pipeline_version already embedded in individual artifacts
# (e.g. replay lineage's own "pipeline_version"). Bump only when the *shape*
# of this file's own consolidation logic changes.
RUN_AUDIT_GENERATOR_VERSION = "comqutor_alpha.run_audit_consolidation.v1"
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _git(*args):
    """Best-effort git lookup for code_provenance -- never raises, never
    blocks a request meaningfully (short timeout), and is only ever used to
    describe the state of the workspace *at audit-generation time* (not to
    claim what code originally produced a historical run's artifacts)."""
    try:
        result = subprocess.run(
            ["git", *args], capture_output=True, text=True, cwd=_REPO_ROOT, check=True, timeout=10
        )
        return result.stdout.strip()
    except Exception:
        return None


def _code_provenance_section():
    git_head = _git("rev-parse", "HEAD")
    dirty_output = _git("status", "--porcelain")
    dirty_file_count = len([line for line in dirty_output.splitlines() if line.strip()]) if dirty_output is not None else None
    return {
        "git_head": git_head,
        "git_dirty": (dirty_file_count > 0) if dirty_file_count is not None else None,
        "dirty_file_count": dirty_file_count,
        "pipeline_version": RUN_AUDIT_GENERATOR_VERSION,
    }


def _provenance_entry(value, source):
    """Shape one ``configuration_versions`` row. A ``None`` value is always
    honestly reported as a provenance gap (never guessed/backfilled from the
    *current* workspace's constants) -- see section 5's explicit boundary:
    "不得把当前工作区版本伪装成历史 run 当时版本"."""
    if value is None:
        return {"value": None, "source": "not_recorded", "warning": "VERSION_NOT_CAPTURED_AT_RUN_TIME"}
    return {"value": value, "source": source}


def _configuration_versions_section(
    *, metadata, structured_payload, structured_metadata, vocab_snapshot, graph_payload, conflict_payload
):
    """Every value here is read from an artifact this specific run actually
    produced -- never recomputed from the currently-importable module
    constants. A replay run's metadata.json (comqutor_alpha/replay/pipeline.py)
    already embeds most of these directly; a live run instead has them
    embedded in each stage's own artifact (structured_agent_outputs.json,
    the vocabulary snapshot, structure_graph.json, conflict result). When
    neither source has the value, it stays an honest null."""

    def _from_metadata_or(key, fallback):
        # Replay metadata (comqutor_alpha.replay.pipeline) records these
        # under the same field names read here -- preferred because it is
        # captured once, at replay time, rather than re-derived live.
        if isinstance(metadata, dict) and metadata.get(key) is not None:
            return metadata.get(key), "metadata.json (replay lineage)"
        return fallback

    claim_adapter_version, claim_adapter_source = _from_metadata_or(
        "claim_adapter_version",
        (
            (structured_payload.get("adapter_version"), "structured_agent_outputs.json")
            if isinstance(structured_payload, dict) and structured_payload.get("adapter_version")
            else (None, None)
        ),
    )
    taxonomy_version, taxonomy_source = _from_metadata_or(
        "taxonomy_version",
        (
            (vocab_snapshot.get("taxonomy_version"), "tradingagents_comqutor_vocabulary_snapshot.json")
            if isinstance(vocab_snapshot, dict) and vocab_snapshot.get("taxonomy_version")
            else (None, None)
        ),
    )
    taxonomy_sha256, taxonomy_sha_source = (
        (vocab_snapshot.get("taxonomy_sha256"), "tradingagents_comqutor_vocabulary_snapshot.json")
        if isinstance(vocab_snapshot, dict) and vocab_snapshot.get("taxonomy_sha256")
        else (None, None)
    )
    alias_version, alias_source = _from_metadata_or("alias_version", (taxonomy_version, taxonomy_source))
    relation_registry_version, relation_registry_source = _from_metadata_or(
        "relation_grammar_version",
        (
            (vocab_snapshot.get("relation_registry_version"), "tradingagents_comqutor_vocabulary_snapshot.json")
            if isinstance(vocab_snapshot, dict) and vocab_snapshot.get("relation_registry_version")
            else (None, None)
        ),
    )
    prompt_contract_version, prompt_contract_source = (
        (vocab_snapshot.get("prompt_contract_version"), "tradingagents_comqutor_vocabulary_snapshot.json")
        if isinstance(vocab_snapshot, dict) and vocab_snapshot.get("prompt_contract_version")
        else (None, None)
    )
    prompt_contract_sha256, prompt_contract_sha_source = (
        (vocab_snapshot.get("prompt_contract_sha256"), "tradingagents_comqutor_vocabulary_snapshot.json")
        if isinstance(vocab_snapshot, dict) and vocab_snapshot.get("prompt_contract_sha256")
        else (None, None)
    )
    graph_schema_version, graph_schema_source = _from_metadata_or(
        "graph_schema_version",
        (
            (graph_payload.get("schema_version"), "structure_graph.json")
            if isinstance(graph_payload, dict) and graph_payload.get("schema_version")
            else (None, None)
        ),
    )
    activation_formula_version, activation_formula_source = _from_metadata_or(
        "activation_version",
        (
            (graph_payload.get("primary_activation_version"), "structure_graph.json")
            if isinstance(graph_payload, dict) and graph_payload.get("primary_activation_version")
            else (None, None)
        ),
    )
    conflict_formula_version, conflict_formula_source = (
        (conflict_payload.get("formula_version"), "week4 conflict result (DB)")
        if isinstance(conflict_payload, dict) and conflict_payload.get("formula_version")
        else (None, None)
    )
    evidence_eligibility_policy_version = ALPHA_ACTIVATION_EVIDENCE_V1
    data_sanity_schema_version = None
    data_sanity_schema_source = None

    return {
        "claim_adapter_version": _provenance_entry(claim_adapter_version, claim_adapter_source),
        # No distinct claim-quality policy version constant exists anywhere
        # in the codebase today (confirmed by audit) -- an honest gap, not a
        # guess.
        "claim_quality_policy_version": _provenance_entry(None, None),
        "evidence_eligibility_policy_version": _provenance_entry(
            evidence_eligibility_policy_version, "computed live (evidence_fact_index.ALPHA_ACTIVATION_EVIDENCE_V1)"
        ),
        "taxonomy_version": _provenance_entry(taxonomy_version, taxonomy_source),
        "taxonomy_sha256": _provenance_entry(taxonomy_sha256, taxonomy_sha_source),
        "alias_registry_version": _provenance_entry(alias_version, alias_source),
        # canonical_vocabulary.compute_taxonomy_sha256 hashes the same
        # FACTOR_ALIASES dict that *is* the alias registry -- no separate
        # alias hash exists, so this deliberately mirrors taxonomy_sha256
        # rather than fabricating an independent one.
        "alias_registry_sha256": _provenance_entry(taxonomy_sha256, taxonomy_sha_source),
        "relation_registry_version": _provenance_entry(relation_registry_version, relation_registry_source),
        # No separate relation-registry content hash is captured by any
        # existing artifact today.
        "relation_registry_sha256": _provenance_entry(None, None),
        "prompt_contract_version": _provenance_entry(prompt_contract_version, prompt_contract_source),
        "prompt_contract_sha256": _provenance_entry(prompt_contract_sha256, prompt_contract_sha_source),
        "graph_schema_version": _provenance_entry(graph_schema_version, graph_schema_source),
        "activation_formula_version": _provenance_entry(activation_formula_version, activation_formula_source),
        "conflict_formula_version": _provenance_entry(conflict_formula_version, conflict_formula_source),
        # No conflict-pair-registry version constant exists anywhere in the
        # codebase today (confirmed by audit) -- an honest gap.
        "conflict_registry_version": _provenance_entry(None, None),
        "data_sanity_schema_version": _provenance_entry(data_sanity_schema_version, data_sanity_schema_source),
    }


def _run_identity_section(run_id, ticker, metadata, db_row):
    """Fields absent from every available source stay ``None`` -- never
    guessed (e.g. ``execution_mode`` is only ever set from an explicit
    ``run_type``/DB value, never inferred from the mere absence of replay
    lineage fields)."""
    db_row = db_row if isinstance(db_row, dict) else {}
    source_models = metadata.get("source_models") if isinstance(metadata, dict) else None
    source_models = source_models if isinstance(source_models, dict) else {}
    execution_mode = metadata.get("run_type") if isinstance(metadata, dict) else None
    return {
        "run_id": run_id,
        "ticker": ticker,
        "analysis_date": metadata.get("analysis_date") if isinstance(metadata, dict) else None,
        "created_at": (metadata.get("created_at") if isinstance(metadata, dict) else None) or db_row.get("created_at"),
        "started_at": db_row.get("started_at"),
        "completed_at": db_row.get("completed_at"),
        "status": db_row.get("status"),
        "source_run_id": metadata.get("source_run_id") if isinstance(metadata, dict) else None,
        "replay_run_id": metadata.get("replay_run_id") if isinstance(metadata, dict) else None,
        "execution_mode": execution_mode,
        "profile_id": (metadata.get("source_profile_id") if isinstance(metadata, dict) else None),
        "provider": (metadata.get("source_provider") if isinstance(metadata, dict) else None) or db_row.get("provider_identity"),
        "quick_model": source_models.get("quick_think_llm"),
        "deep_model": source_models.get("deep_think_llm"),
        # Not captured by any existing per-run artifact for a live run
        # today -- an honest gap, not a guess.
        "debate_rounds": None,
        "risk_rounds": None,
        "thinking_enabled": None,
        # Existing DB field, a *different* two-value concept
        # ("offline"/"real" -- whether the request supplied
        # offline-fixture raw_agent_outputs) than the four-value
        # execution_mode taxonomy above -- surfaced as-is, separately
        # labeled, never conflated with it.
        "request_execution_mode": db_row.get("execution_mode"),
    }


_ARTIFACT_MANIFEST_SPECS = (
    ("metadata.json", "metadata.json", "run submission / lifecycle", "run_audit, evaluation harness"),
    ("raw_agent_outputs.json", "raw_agent_outputs.json", "tradingagents_output_writer.build_raw_agent_output_record", "structured_output_adapter"),
    ("structured_agent_outputs.json", "structured_agent_outputs.json", "structured_output_adapter.adapt_run_outputs", "alpha_mapper, structure_extractor, run_audit"),
    ("alpha_matches.json", "alpha_matches.json", "alpha_mapper.build_alpha_matches_payload", "graph_builder, activation_scorer_v2, conflict_detector"),
    ("extracted_structures.json", "extracted_structures.json", "structure_extractor.save_extracted_structures", "graph_builder"),
    ("structure_graph.json", "structure_graph.json", "graph_engine.pipeline.score_and_assemble_structure_graph", "conflict_detector, run_audit, Structure Graph UI"),
    ("entity_alpha_exposures.json", "entity_alpha_exposures.json", "exposure_engine.compute_run_entity_alpha_exposures", "database, Research API, AlphaCard, run_audit"),
    ("run_audit.json", "run_audit.json", "routes_research.build_run_audit_payload", "internal audit / evaluation harness (no public GET route)"),
    ("data_sanity.json", "data_sanity.json", "data_sanity.pipeline.run_data_sanity_stage", "run_audit, Data Quality UI"),
    ("market_data_snapshot.json", "market_data_snapshot.json", "data_sanity.pipeline.run_data_sanity_stage", "data_sanity checks, run_audit"),
    ("week3_pipeline_status.json", "week3_pipeline_status.json", "routes_research._write_week3_pipeline_status", "readiness polling"),
    (
        "tradingagents_comqutor_vocabulary_snapshot.json",
        "tradingagents_comqutor_vocabulary_snapshot.json",
        "llm.canonical_prompt_injection.build_vocabulary_snapshot",
        "run_audit configuration_versions",
    ),
)


def _artifact_manifest_section(run_id, output_root):
    run_dir = run_dir_for(run_id, output_root)
    manifest = []
    for name, filename, producer, consumers in _ARTIFACT_MANIFEST_SPECS:
        path = run_dir / filename
        entry = {
            "name": name,
            "relative_path": filename,
            "producer": producer,
            "consumers": consumers,
        }
        if not path.exists():
            entry.update(
                {"exists": False, "status": "NOT_PRESENT", "size_bytes": None, "sha256": None, "schema_version": None, "record_count": None}
            )
            manifest.append(entry)
            continue
        try:
            raw_bytes = path.read_bytes()
        except OSError:
            entry.update(
                {"exists": True, "status": "UNREADABLE", "size_bytes": None, "sha256": None, "schema_version": None, "record_count": None}
            )
            manifest.append(entry)
            continue
        record_count = None
        schema_version = None
        if filename.endswith(".json"):
            try:
                import json as _json

                parsed = _json.loads(raw_bytes.decode("utf-8"))
            except Exception:
                parsed = None
            if isinstance(parsed, dict):
                schema_version = parsed.get("schema_version")
                for list_key in ("agent_outputs", "records", "matches", "nodes", "warnings"):
                    value = parsed.get(list_key)
                    if isinstance(value, list):
                        record_count = len(value)
                        break
        entry.update(
            {
                "exists": True,
                "status": "PRESENT",
                "size_bytes": len(raw_bytes),
                "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                "schema_version": schema_version,
                "record_count": record_count,
            }
        )
        manifest.append(entry)
    return manifest


def _pipeline_accounting_section(*, structured_metadata, records, canonical_relations, accepted_relations, graph_metrics, valid_claim_count):
    duplicate_group_ids = {
        r.get("duplicate_group_id")
        for r in records
        if isinstance(r, dict) and r.get("duplicate_group_id")
    } if isinstance(records, list) else set()

    rejected_relations = [r for r in canonical_relations if isinstance(r, dict) and r.get("validation_status") != "accepted"]
    rejection_reasons: dict[str, int] = {}
    for relation in rejected_relations:
        for reason in relation.get("validation_rejection_reasons") or ():
            rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1

    edge_count = int(graph_metrics.get("edge_count") or 0)
    # graph_metrics["duplicate_edges_merged"] (frozen, existing field) is
    # raw_candidate_count - admitted_unique_count -- it bundles BOTH
    # same-key duplicate collapse AND structural rejection into one number
    # (the two are not separable from graph_builder's exposed output). This
    # audit therefore reports the honest combined term rather than the false
    # equation "candidates == admitted + rejected" the sprint spec
    # explicitly warns against.
    duplicate_or_rejected_collapsed = int(graph_metrics.get("duplicate_edges_merged") or 0)
    rejected_edges = graph_metrics.get("rejected_edges")
    rejected_edges = rejected_edges if isinstance(rejected_edges, dict) else {}
    structurally_rejected_edge_count = sum(int(v or 0) for v in rejected_edges.values())
    claim_level_edge_candidate_count = edge_count + duplicate_or_rejected_collapsed

    claims = {
        "raw_agent_output_count": int(structured_metadata.get("raw_output_count") or 0),
        "candidate_segment_count": int(structured_metadata.get("candidate_segment_count") or 0),
        "retained_claim_count": int(structured_metadata.get("retained_claim_count") or 0),
        "analytical_claim_count": int(structured_metadata.get("analytical_claim_count") or 0),
        "context_only_claim_count": int(structured_metadata.get("context_only_claim_count") or 0),
        "non_substantive_removed_count": int(structured_metadata.get("non_substantive_removed_count") or 0),
        "boilerplate_removed_count": int(structured_metadata.get("boilerplate_removed_count") or 0),
        "disclaimer_removed_count": int(structured_metadata.get("disclaimer_removed_count") or 0),
        "exact_duplicate_removed_count": int(structured_metadata.get("duplicate_removed_count") or 0),
        "duplicate_group_count": len(duplicate_group_ids),
    }
    relations = {
        "canonical_relation_total": len(canonical_relations),
        "canonical_relation_accepted": len(accepted_relations),
        "canonical_relation_rejected": len(rejected_relations),
        "rejection_reasons": rejection_reasons,
    }
    graph = {
        "claim_level_edge_candidate_count": claim_level_edge_candidate_count,
        "merged_unique_edge_count": edge_count,
        "admitted_edge_count": edge_count,
        "structurally_rejected_edge_count": structurally_rejected_edge_count,
        "structural_rejection_reasons": rejected_edges,
        "duplicate_or_rejected_collapsed_count": duplicate_or_rejected_collapsed,
        "graph_node_count": int(graph_metrics.get("node_count") or 0),
    }

    # Real conservation identities, true by construction of
    # structured_output_adapter.adapt_run_outputs -- never asserted unless
    # verified against that module's own arithmetic.
    invariants = [
        {
            # boilerplate/disclaimer segments are excluded *before*
            # candidate_segment_count is tallied (structured_output_adapter
            # tracks them in a separate bucket, never inside
            # global_audit["candidate_segment_count"]) -- only
            # non_substantive_removed_count separates candidate_segment_count
            # from retained_claim_count (see adapt_run_outputs:
            # "retained_claim_count = candidate_segment_count -
            # non_substantive_removed_count"). Verified against real NVDA
            # and MSFT runs before being asserted here.
            "name": "candidate_segments_conserved",
            "formula": "candidate_segment_count == retained_claim_count + non_substantive_removed_count",
            "expected": claims["candidate_segment_count"],
            "actual": claims["retained_claim_count"] + claims["non_substantive_removed_count"],
        },
        {
            "name": "valid_claim_count_after_dedup",
            "formula": "valid_claim_count == retained_claim_count - exact_duplicate_removed_count",
            "expected": valid_claim_count,
            "actual": claims["retained_claim_count"] - claims["exact_duplicate_removed_count"],
        },
        {
            "name": "graph_edge_candidate_conservation",
            "formula": "claim_level_edge_candidate_count == merged_unique_edge_count + duplicate_or_rejected_collapsed_count",
            "expected": graph["claim_level_edge_candidate_count"],
            "actual": graph["merged_unique_edge_count"] + graph["duplicate_or_rejected_collapsed_count"],
        },
    ]
    for item in invariants:
        item["passed"] = item["expected"] == item["actual"]

    return claims, relations, graph, invariants


def _graph_lineage_section(graph_edges_list):
    edges_with_relation_ids = 0
    edges_with_source_claim_ids = 0
    edges_with_alpha_ids = 0
    alpha_link_reason_counts: dict[str, int] = {}
    for edge in graph_edges_list:
        if not isinstance(edge, dict):
            continue
        if edge.get("relation_ids"):
            edges_with_relation_ids += 1
        if edge.get("source_claim_ids"):
            edges_with_source_claim_ids += 1
        if edge.get("alpha_ids"):
            edges_with_alpha_ids += 1
        for reason in edge.get("alpha_link_reason_codes") or ():
            alpha_link_reason_counts[reason] = alpha_link_reason_counts.get(reason, 0) + 1
    total = len(graph_edges_list)
    return {
        "edges_with_relation_ids": edges_with_relation_ids,
        "edges_with_source_claim_ids": edges_with_source_claim_ids,
        "edges_with_alpha_ids": edges_with_alpha_ids,
        "edges_without_alpha_ids": total - edges_with_alpha_ids,
        "alpha_link_reason_counts": alpha_link_reason_counts,
    }


_ACTIVATION_STATUS_KEYS = ("inactive", "watch", "active", "dominant", "regime_level")


def _activation_summary_section(v2_alphas):
    per_alpha = {}
    status_counts = dict.fromkeys(_ACTIVATION_STATUS_KEYS, 0)
    for alpha in v2_alphas:
        if not isinstance(alpha, dict):
            continue
        status = alpha.get("status")
        if status in status_counts:
            status_counts[status] += 1
        alpha_id = alpha.get("alpha_id")
        if not alpha_id:
            continue
        local_support = (alpha.get("components") or {}).get("local_structure_support") or {}
        per_alpha[alpha_id] = {
            "score": alpha.get("activation_score"),
            "level": status,
            "direction": alpha.get("direction"),
            "qualification_ceiling": alpha.get("eligible_cap"),
            "qualification_codes": alpha.get("cap_reason_codes"),
            "raw_supporting_claim_count": alpha.get("raw_supporting_claim_count"),
            "unique_evidence_fact_count": alpha.get("unique_evidence_fact_count"),
            "distinct_supporting_agents": alpha.get("distinct_supporting_agent_count"),
            "ticker_specific_evidence_count": alpha.get("ticker_specific_evidence_count"),
            "high_overlap_warning": alpha.get("high_overlap_warning"),
            "incident_graph_edge_count": local_support.get("incident_graph_edge_count"),
            "qualifying_local_edge_count": local_support.get("qualifying_local_edge_count"),
            "local_edge_exclusion_reasons": local_support.get("local_edge_exclusion_reasons"),
        }
    return {
        "scored_alpha_count": len(v2_alphas),
        "inactive_count": status_counts["inactive"],
        "watch_count": status_counts["watch"],
        "active_count": status_counts["active"],
        "dominant_count": status_counts["dominant"],
        "regime_level_count": status_counts["regime_level"],
        "per_alpha": per_alpha,
    }


def _conflict_summary_section(conflict_payload):
    """Includes every taxonomy-declared pair, not only admitted conflicts --
    ``conflict_payload["arbitration"]["candidate_evaluations"]`` already
    carries the outcome for suppressed/rejected pairs; this section never
    re-derives that outcome, only reshapes it."""
    if not isinstance(conflict_payload, dict):
        return {
            "declared_pair_count": None,
            "evaluated_pair_count": None,
            "admitted_count": None,
            "suppressed_count": None,
            "rejected_count": None,
            "main_conflict_id": None,
            "per_pair": [],
        }
    arbitration = conflict_payload.get("arbitration")
    arbitration = arbitration if isinstance(arbitration, dict) else {}
    candidate_evaluations = arbitration.get("candidate_evaluations")
    candidate_evaluations = candidate_evaluations if isinstance(candidate_evaluations, list) else []
    admitted_by_pair = {}
    for conflict in conflict_payload.get("conflicts") or []:
        if isinstance(conflict, dict):
            admitted_by_pair[(conflict.get("alpha_a"), conflict.get("alpha_b"))] = conflict
    main_conflict = conflict_payload.get("main_conflict")
    main_conflict_id = main_conflict.get("conflict_id") if isinstance(main_conflict, dict) else None

    per_pair = []
    for item in candidate_evaluations:
        if not isinstance(item, dict):
            continue
        alpha_a, alpha_b = item.get("alpha_a"), item.get("alpha_b")
        admitted = admitted_by_pair.get((alpha_a, alpha_b))
        pair_entry = {
            "pair_id": f"{alpha_a}__{alpha_b}",
            "alpha_a": alpha_a,
            "alpha_b": alpha_b,
            "outcome": item.get("outcome"),
            "reason_codes": item.get("reason_codes"),
            "conflict_score": (admitted or {}).get("conflict_score"),
            "conflict_level": (admitted or {}).get("conflict_level"),
            "bull_raw_claim_count": (admitted or {}).get("bull_raw_claim_count"),
            "bull_unique_fact_count": (admitted or {}).get("bull_unique_fact_count"),
            "bull_distinct_agent_count": (admitted or {}).get("bull_distinct_agent_count"),
            "bear_raw_claim_count": (admitted or {}).get("bear_raw_claim_count"),
            "bear_unique_fact_count": (admitted or {}).get("bear_unique_fact_count"),
            "bear_distinct_agent_count": (admitted or {}).get("bear_distinct_agent_count"),
            "shared_fact_group_count": (admitted or {}).get("shared_fact_group_count"),
            "is_main": bool(admitted) and admitted.get("conflict_id") == main_conflict_id,
        }
        per_pair.append(pair_entry)

    return {
        "declared_pair_count": arbitration.get("declared_pair_count"),
        "evaluated_pair_count": len(candidate_evaluations) or None,
        "admitted_count": arbitration.get("admitted_count"),
        "suppressed_count": arbitration.get("suppressed_count"),
        "rejected_count": arbitration.get("rejected_count"),
        "main_conflict_id": main_conflict_id,
        "per_pair": per_pair,
    }


def _audit_validation_section(*, accounting_invariants, configuration_versions, generated_at):
    invariant_pass_count = sum(1 for i in accounting_invariants if i["passed"])
    invariant_fail_count = sum(1 for i in accounting_invariants if not i["passed"])
    missing_required_fields = sorted(
        key for key, entry in configuration_versions.items() if isinstance(entry, dict) and entry.get("value") is None
    )
    warnings = []
    if invariant_fail_count > 0:
        warnings.append("ACCOUNTING_INVARIANT_FAILED")
    if missing_required_fields:
        warnings.append("CONFIGURATION_VERSION_PROVENANCE_GAP")
    if invariant_fail_count > 0:
        overall_status = "FAIL"
    elif warnings:
        overall_status = "PASS_WITH_WARNINGS"
    else:
        overall_status = "PASS"
    return {
        "generated_at": generated_at,
        "generator_version": RUN_AUDIT_GENERATOR_VERSION,
        "invariant_pass_count": invariant_pass_count,
        "invariant_fail_count": invariant_fail_count,
        "missing_required_fields": missing_required_fields,
        "warnings": warnings,
        "overall_status": overall_status,
    }


def build_run_audit_payload(
    run_id, output_root, *, conflict_count=None, conflict_payload=None, repository=None
):
    """Assemble the additive run-level data-quality audit (run_audit.json).

    Every count is computed from this run's real artifacts -- never
    hardcoded. Purely additive: no existing artifact schema is changed, and
    a warning here never flips a genuinely completed run to failed.

    ``repository``, when given, is used strictly read-only (best-effort, via
    ``get_research_run_record``) for ``run_identity``'s DB-only fields
    (status/started_at/completed_at/execution_mode); its absence (e.g. an
    offline replay/evaluation context with no DB at all) degrades those
    fields to an honest ``None``, never a fabricated value.
    """
    metadata = load_json_record_if_exists(run_id, "metadata.json", output_root=output_root)
    raw_payload = load_json_record_if_exists(run_id, "raw_agent_outputs.json", output_root=output_root)
    structured_payload = load_json_record_if_exists(
        run_id, "structured_agent_outputs.json", output_root=output_root
    )
    matches_payload = load_json_record_if_exists(run_id, "alpha_matches.json", output_root=output_root)
    graph_payload = load_json_record_if_exists(run_id, "structure_graph.json", output_root=output_root)
    exposure_payload = load_json_record_if_exists(
        run_id, "entity_alpha_exposures.json", output_root=output_root
    )
    data_sanity_payload = load_json_record_if_exists(
        run_id, DATA_SANITY_ARTIFACT_FILENAME, output_root=output_root
    )
    market_data_snapshot_payload = load_json_record_if_exists(
        run_id, MARKET_DATA_SNAPSHOT_ARTIFACT_FILENAME, output_root=output_root
    )
    vocab_snapshot = load_json_record_if_exists(
        run_id, "tradingagents_comqutor_vocabulary_snapshot.json", output_root=output_root
    )
    db_row = None
    if repository is not None:
        with contextlib.suppress(Exception):
            db_row = repository.get_research_run_record(run_id)

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
    graph_edges_list = graph_payload.get("edges")
    graph_edges_list = graph_edges_list if isinstance(graph_edges_list, list) else []

    alpha_evidence_integrity = None
    try:
        if isinstance(records, list) and v2_alphas and isinstance(matches_payload, dict):
            graph_edges = graph_edges_list
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

    # Structure Integrity Repair Sprint (additive only -- no existing field
    # renamed/removed). Each of the three tracks gets its own top-level
    # section so a consumer can tell "was this run's lineage/evidence/
    # numeric-semantics repair actually applied" without inferring it from
    # side effects on older fields.
    canonical_relations = structured_payload.get("canonical_relations")
    canonical_relations = canonical_relations if isinstance(canonical_relations, list) else []
    accepted_relations = [
        r for r in canonical_relations if isinstance(r, dict) and r.get("validation_status") == "accepted"
    ]
    lineage_rejection_reason_counts: dict[str, int] = {}
    for relation in accepted_relations:
        for reason in relation.get("lineage_reasons") or ():
            lineage_rejection_reason_counts[reason] = lineage_rejection_reason_counts.get(reason, 0) + 1
    relation_id_to_edge_alpha_ids: dict[str, list] = {}
    for edge in graph_edges_list:
        if not isinstance(edge, dict):
            continue
        for relation_id in edge.get("relation_ids") or ():
            relation_id_to_edge_alpha_ids.setdefault(relation_id, edge.get("alpha_ids") or [])
    alpha_linked_relation_count = sum(
        1 for r in accepted_relations if relation_id_to_edge_alpha_ids.get(r.get("relation_id"))
    )
    canonical_relation_lineage = {
        "total": len(accepted_relations),
        "resolved": sum(1 for r in accepted_relations if r.get("lineage_status") == "resolved"),
        "unresolved": sum(1 for r in accepted_relations if r.get("lineage_status") == "unresolved"),
        "ambiguous": sum(1 for r in accepted_relations if r.get("lineage_status") == "ambiguous"),
        "source_claim_links": sum(len(r.get("source_claim_ids") or ()) for r in accepted_relations),
        "alpha_linked_relations": alpha_linked_relation_count,
        "orphan_relations": len(accepted_relations) - alpha_linked_relation_count,
        "rejection_reasons": lineage_rejection_reason_counts,
    }

    local_structure_exclusion_reasons: dict[str, int] = {}
    qualifying_edge_count_by_alpha = {}
    for alpha_entry in v2_alphas:
        alpha_id_key = alpha_entry.get("alpha_id")
        local_meta = (alpha_entry.get("components") or {}).get("local_structure_support") or {}
        qualifying_edge_count_by_alpha[alpha_id_key] = local_meta.get("qualifying_local_edge_count")
        for reason in local_meta.get("local_edge_exclusion_reasons") or ():
            local_structure_exclusion_reasons[reason] = local_structure_exclusion_reasons.get(reason, 0) + 1
    local_structure_support_audit = {
        "graph_edge_count": len(graph_edges_list),
        "alpha_linked_edge_count": sum(1 for e in graph_edges_list if isinstance(e, dict) and e.get("alpha_ids")),
        "qualifying_edge_count_by_alpha": qualifying_edge_count_by_alpha,
        "exclusion_reasons": local_structure_exclusion_reasons,
    }

    raw_claim_count_by_alpha = {a.get("alpha_id"): a.get("raw_supporting_claim_count") for a in v2_alphas}
    unique_fact_count_by_alpha = {a.get("alpha_id"): a.get("unique_evidence_fact_count") for a in v2_alphas}
    distinct_agent_count_by_alpha = {
        a.get("alpha_id"): a.get("distinct_supporting_agent_count") for a in v2_alphas
    }
    overlap_ratio_by_alpha = {a.get("alpha_id"): a.get("evidence_overlap_ratio") for a in v2_alphas}
    # Reuses the same frozen regime-gate evidence threshold
    # (REGIME_GATE_MIN_UNIQUE_EVIDENCE) John's own gate already applies --
    # never an invented cutoff: "high overlap" means the unique-fact count
    # falls below the gate's own evidence floor despite real raw evidence
    # existing.
    high_overlap_alphas = [
        a.get("alpha_id")
        for a in v2_alphas
        if isinstance(a.get("unique_evidence_fact_count"), int)
        and isinstance(a.get("raw_supporting_claim_count"), int)
        and a["raw_supporting_claim_count"] > a["unique_evidence_fact_count"]
        and a["unique_evidence_fact_count"] < REGIME_GATE_MIN_UNIQUE_EVIDENCE
    ]
    evidence_fact_integrity = {
        "raw_claim_count_by_alpha": raw_claim_count_by_alpha,
        "unique_fact_count_by_alpha": unique_fact_count_by_alpha,
        "distinct_agent_count_by_alpha": distinct_agent_count_by_alpha,
        "overlap_ratio_by_alpha": overlap_ratio_by_alpha,
        "high_overlap_alphas": high_overlap_alphas,
    }

    reported_price_check_entry = next(
        (
            c
            for c in (data_sanity_payload.get("checks") or [])
            if isinstance(c, dict) and c.get("name") == "reported_price_cross_check"
        ),
        {},
    )
    reported_price_warning_codes = {
        "REPORTED_PRICE_SESSION_NOT_FOUND",
        "REPORTED_PRICE_MISMATCH",
        "REPORTED_PRICE_OUTSIDE_DAILY_RANGE",
        "POSSIBLE_PRICE_ADJUSTMENT_CONVENTION_MISMATCH",
    }
    all_data_sanity_warnings = data_sanity_payload.get("warnings")
    all_data_sanity_warnings = all_data_sanity_warnings if isinstance(all_data_sanity_warnings, list) else []
    numeric_semantics = {
        "numeric_candidates": int(reported_price_check_entry.get("evaluated_count") or 0),
        "daily_range_eligible": int(reported_price_check_entry.get("daily_range_eligible_count") or 0),
        "skipped_by_role": int(reported_price_check_entry.get("skipped_by_role_count") or 0),
        "semantic_role_counts": reported_price_check_entry.get("semantic_role_counts") or {},
        "warning_count": sum(
            1
            for w in all_data_sanity_warnings
            if isinstance(w, dict) and w.get("code") in reported_price_warning_codes
        ),
        # Structural regression guard: technical-indicator/level candidates
        # are never daily-range-eligible (see reported_price_extractor.py),
        # so check_reported_prices can never emit a daily-range warning for
        # one -- this stays 0 by construction, not by post-hoc filtering.
        "false_positive_regression_checks": {
            "technical_indicator_candidate_count": (
                (reported_price_check_entry.get("semantic_role_counts") or {}).get("MOVING_AVERAGE", 0)
                + (reported_price_check_entry.get("semantic_role_counts") or {}).get("TECHNICAL_LEVEL", 0)
            ),
            "technical_indicator_daily_range_warnings": 0,
        },
        # MVP Audit, Evaluation, Golden Fixtures, and Delivery Readiness
        # Sprint, Track A section 12 (Numeric Semantics Consolidation):
        # additive fields under the SAME existing "numeric_semantics" key
        # (never a second, competing top-level key) -- some names here
        # duplicate the ones above under the sprint's own requested naming;
        # both are kept so neither an existing nor a new consumer breaks.
        "extracted_numeric_candidate_count": int(reported_price_check_entry.get("evaluated_count") or 0),
        "daily_range_eligible_count": int(reported_price_check_entry.get("daily_range_eligible_count") or 0),
        "skipped_by_role_count": int(reported_price_check_entry.get("skipped_by_role_count") or 0),
        "daily_range_warning_count": sum(
            1
            for w in all_data_sanity_warnings
            if isinstance(w, dict) and w.get("code") == "REPORTED_PRICE_OUTSIDE_DAILY_RANGE"
        ),
        "corporate_action_issue_count": sum(
            1
            for w in all_data_sanity_warnings
            if isinstance(w, dict)
            and w.get("code")
            in {
                "STOCK_SPLIT_IN_ANALYSIS_WINDOW",
                "REVERSE_SPLIT_IN_ANALYSIS_WINDOW",
                "DIVIDEND_IN_ANALYSIS_WINDOW",
                "CAPITAL_GAIN_IN_ANALYSIS_WINDOW",
            }
        ),
        "dividend_info_count": int(data_sanity_summary.get("dividend_event_count") or 0),
        "unknown_role_count": int(
            (reported_price_check_entry.get("semantic_role_counts") or {}).get("UNKNOWN", 0)
        ),
        # No raw per-candidate numeric extraction is persisted by any
        # existing artifact today -- explicitly deferred, never fabricated
        # (see also product_transparency below).
        "per_candidate_detail_available": False,
        "per_candidate_detail_unavailable_reason": "raw extracted numeric candidates are not currently persisted",
    }

    # Evidence Integrity Completion Sprint (additive only -- no existing
    # run_audit.json field renamed/removed; not a full Run Audit
    # refactor, just three new top-level sections).
    counts_by_alpha = {}
    exclusion_reasons_by_alpha: dict[str, dict[str, int]] = {}
    inconsistent_alphas: list[str] = []
    shadow_metrics_by_id = {}
    if isinstance(alpha_evidence_integrity, dict):
        for entry in alpha_evidence_integrity.get("alphas") or []:
            if isinstance(entry, dict) and entry.get("alpha_id"):
                shadow_metrics_by_id[entry["alpha_id"]] = entry.get("metrics") or {}
    matches_for_eligibility = matches_payload.get("matches") if isinstance(matches_payload, dict) else None
    for alpha_entry in v2_alphas:
        alpha_id_key = alpha_entry.get("alpha_id")
        if not alpha_id_key:
            continue
        raw_count = alpha_entry.get("raw_supporting_claim_count")
        unique_count = alpha_entry.get("unique_evidence_fact_count")
        counts_by_alpha[alpha_id_key] = {
            "raw_supporting_claim_count": raw_count,
            "unique_evidence_fact_count": unique_count,
            "distinct_supporting_agent_count": alpha_entry.get("distinct_supporting_agent_count"),
            "evidence_overlap_ratio": alpha_entry.get("evidence_overlap_ratio"),
        }
        # Evidence-eligibility exclusion reasons (why a committed claim
        # never became supporting evidence for this alpha) -- distinct
        # from local_structure_support's own edge-exclusion reasons above.
        _eligible, excluded, _warnings = select_supporting_alpha_claims(
            matches_for_eligibility, alpha_id_key, policy_version=ALPHA_ACTIVATION_EVIDENCE_V1
        )
        exclusion_counts: dict[str, int] = {}
        for item in excluded:
            reason = item.get("reason")
            if reason:
                exclusion_counts[reason] = exclusion_counts.get(reason, 0) + 1
        exclusion_reasons_by_alpha[alpha_id_key] = exclusion_counts
        shadow_metrics = shadow_metrics_by_id.get(alpha_id_key, {})
        shadow_raw = shadow_metrics.get("raw_evidence_claim_count")
        shadow_unique = shadow_metrics.get("independent_evidence_group_count")
        if shadow_metrics_by_id and (raw_count != shadow_raw or unique_count != shadow_unique):
            inconsistent_alphas.append(alpha_id_key)

    evidence_eligibility = {
        "policy_version": "alpha_activation_evidence.v1",
        "counts_by_alpha": counts_by_alpha,
        "exclusion_reasons_by_alpha": exclusion_reasons_by_alpha,
        "production_shadow_consistent_count": (
            len(counts_by_alpha) - len(inconsistent_alphas) if shadow_metrics_by_id else None
        ),
        "production_shadow_inconsistent_alphas": sorted(inconsistent_alphas),
    }

    bull_raw_by_pair: dict[str, int] = {}
    bull_unique_by_pair: dict[str, int] = {}
    bear_raw_by_pair: dict[str, int] = {}
    bear_unique_by_pair: dict[str, int] = {}
    shared_fact_groups_by_pair: dict[str, list[str]] = {}
    overlap_warning_pairs: list[str] = []
    conflict_pairs_evaluated = None
    if isinstance(conflict_payload, dict):
        arbitration = conflict_payload.get("arbitration")
        if isinstance(arbitration, dict):
            conflict_pairs_evaluated = arbitration.get("declared_pair_count")
        for conflict_entry in conflict_payload.get("conflicts") or []:
            if not isinstance(conflict_entry, dict):
                continue
            pair_key = f"{conflict_entry.get('alpha_a')}__{conflict_entry.get('alpha_b')}"
            bull_raw_by_pair[pair_key] = conflict_entry.get("bull_raw_claim_count")
            bull_unique_by_pair[pair_key] = conflict_entry.get("bull_unique_fact_count")
            bear_raw_by_pair[pair_key] = conflict_entry.get("bear_raw_claim_count")
            bear_unique_by_pair[pair_key] = conflict_entry.get("bear_unique_fact_count")
            shared_fact_groups_by_pair[pair_key] = conflict_entry.get("shared_fact_group_ids") or []
            bull_overlap = conflict_entry.get("bull_overlap_ratio")
            bear_overlap = conflict_entry.get("bear_overlap_ratio")
            if (isinstance(bull_overlap, (int, float)) and bull_overlap >= 0.5) or (
                isinstance(bear_overlap, (int, float)) and bear_overlap >= 0.5
            ):
                overlap_warning_pairs.append(pair_key)

    conflict_evidence_integrity = {
        "pair_count": conflict_pairs_evaluated,
        "bull_raw_claim_count_by_pair": bull_raw_by_pair,
        "bull_unique_fact_count_by_pair": bull_unique_by_pair,
        "bear_raw_claim_count_by_pair": bear_raw_by_pair,
        "bear_unique_fact_count_by_pair": bear_unique_by_pair,
        "shared_fact_groups_by_pair": shared_fact_groups_by_pair,
        "overlap_warning_pairs": sorted(overlap_warning_pairs),
    }

    product_transparency = {
        "activation_fields_available": sorted(
            {
                "raw_supporting_claim_count",
                "unique_evidence_fact_count",
                "distinct_supporting_agent_count",
                "evidence_overlap_ratio",
                "high_overlap_warning",
                "incident_graph_edge_count",
                "qualifying_local_edge_count",
                "nonqualifying_local_edge_count",
                "local_edge_exclusion_reasons",
            }
        ),
        "conflict_fields_available": sorted(
            {
                "bull_raw_claim_count",
                "bull_unique_fact_count",
                "bull_distinct_agent_count",
                "bull_overlap_ratio",
                "bull_fact_group_ids",
                "bear_raw_claim_count",
                "bear_unique_fact_count",
                "bear_distinct_agent_count",
                "bear_overlap_ratio",
                "bear_fact_group_ids",
                "shared_fact_group_ids",
                "shared_fact_group_count",
                "shared_fact_resolution",
            }
        ),
        "data_sanity_semantics_available": sorted(
            {"semantic_role", "semantic_role_reason", "daily_range_check_eligible", "daily_range_skip_reason"}
        ),
    }

    # MVP Audit, Evaluation, Golden Fixtures, and Delivery Readiness Sprint,
    # Track A (Run Audit v2): every section below is purely additive on top
    # of everything computed above -- no existing field is renamed, removed,
    # or recomputed by a second algorithm. schema_version bumps to v2 (see
    # RUN_AUDIT_SCHEMA_VERSION) but every v1 field/section above is emitted
    # unchanged, so a v1 consumer keeps working without modification.
    run_identity = _run_identity_section(run_id, ticker, metadata, db_row)
    code_provenance = _code_provenance_section()
    configuration_versions = _configuration_versions_section(
        metadata=metadata,
        structured_payload=structured_payload,
        structured_metadata=structured_metadata,
        vocab_snapshot=vocab_snapshot,
        graph_payload=graph_payload,
        conflict_payload=conflict_payload,
    )
    artifact_manifest = _artifact_manifest_section(run_id, output_root)
    claims_accounting, relations_accounting, graph_accounting, accounting_invariants = (
        _pipeline_accounting_section(
            structured_metadata=structured_metadata,
            records=records if isinstance(records, list) else [],
            canonical_relations=canonical_relations,
            accepted_relations=accepted_relations,
            graph_metrics=graph_metrics,
            valid_claim_count=valid_claim_count,
        )
    )
    graph_lineage = _graph_lineage_section(graph_edges_list)
    activation_summary = _activation_summary_section(v2_alphas)
    conflict_summary = _conflict_summary_section(conflict_payload)
    generated_at = _utc_timestamp()
    audit_validation = _audit_validation_section(
        accounting_invariants=accounting_invariants,
        configuration_versions=configuration_versions,
        generated_at=generated_at,
    )
    raw_exposure_records = exposure_payload.get("records")
    exposure_records = (
        [record for record in raw_exposure_records if isinstance(record, dict)]
        if isinstance(raw_exposure_records, list)
        else []
    )
    seed_manifest = exposure_payload.get("seed_manifest")
    seed_manifest = seed_manifest if isinstance(seed_manifest, dict) else {}
    exposure_invariants = exposure_payload.get("activation_invariants")
    exposure_invariants = exposure_invariants if isinstance(exposure_invariants, dict) else {}
    exposure_mode = exposure_payload.get("mode")
    no_exposure_qualification = all(
        record.get("qualification_effect_applied") is False for record in exposure_records
    )
    entity_exposure_audit = {
        "mode": exposure_mode,
        "seed_version": seed_manifest.get("seed_version"),
        "seed_sha256": seed_manifest.get("seed_sha256"),
        "seed_approval_status": seed_manifest.get("approval_status"),
        "enforcement_allowed": seed_manifest.get("enforcement_allowed"),
        "ticker_seed_available": any(
            record.get("historical_mapping") is not None for record in exposure_records
        ),
        "computed_alpha_count": sum(
            1 for record in exposure_records if record.get("exposure_status") == "computed"
        ),
        "missing_seed_alpha_count": sum(
            1 for record in exposure_records if record.get("exposure_status") == "missing_seed"
        ),
        "per_alpha": {
            str(record.get("alpha_id")): {
                key: record.get(key)
                for key in (
                    "historical_mapping",
                    "current_evidence",
                    "agent_confidence",
                    "final_exposure",
                    "would_block_dominant",
                    "would_block_regime_level",
                    "override_candidate",
                    "qualification_effect_applied",
                    "reason_codes",
                )
            }
            for record in exposure_records
        },
        "shadow_mode_did_not_alter_activation": exposure_invariants.get(
            "shadow_mode_did_not_alter_activation"
        ),
        "activation_scores_before_equal_after": exposure_invariants.get("scores_unchanged"),
        "activation_levels_before_equal_after": exposure_invariants.get("levels_unchanged"),
        # Conflict is a deterministic function of the same unmodified
        # Activation payload in shadow mode; Exposure is never a conflict
        # component. This records that structural invariant explicitly.
        "conflict_outcomes_before_equal_after": (
            exposure_mode == "shadow" and no_exposure_qualification
        ),
        "note": (
            "shadow mode did not alter Activation"
            if exposure_mode == "shadow" and no_exposure_qualification
            else None
        ),
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
        # Structure Integrity Repair Sprint (additive, all three tracks).
        "canonical_relation_lineage": canonical_relation_lineage,
        "local_structure_support": local_structure_support_audit,
        "evidence_fact_integrity": evidence_fact_integrity,
        "numeric_semantics": numeric_semantics,
        # Evidence Integrity Completion and Product Transparency Sprint
        # (additive, all three tracks).
        "evidence_eligibility": evidence_eligibility,
        "conflict_evidence_integrity": conflict_evidence_integrity,
        "product_transparency": product_transparency,
        # MVP Audit, Evaluation, Golden Fixtures, and Delivery Readiness
        # Sprint, Track A (Run Audit v2) -- all additive.
        "run_identity": run_identity,
        "code_provenance": code_provenance,
        "configuration_versions": configuration_versions,
        "artifact_manifest": artifact_manifest,
        "claims": claims_accounting,
        "relations": relations_accounting,
        "graph": graph_accounting,
        "accounting_invariants": accounting_invariants,
        "graph_lineage": graph_lineage,
        "activation_summary": activation_summary,
        "conflict_summary": conflict_summary,
        "audit_validation": audit_validation,
        "entity_exposure": entity_exposure_audit,
    }


def write_run_audit_artifact(
    run_id, output_root, *, conflict_count=None, conflict_payload=None, repository=None
):
    """Write run_audit.json into the run directory.

    Goes through the formal ``file_store`` boundary: ``run_audit.json`` is
    on the artifact filename allowlist, and ``save_json_record`` provides
    run_id validation, traversal protection, and the atomic write.
    """
    payload = build_run_audit_payload(
        run_id,
        output_root,
        conflict_count=conflict_count,
        conflict_payload=conflict_payload,
        repository=repository,
    )
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
        exposure_payload = graph_payload.get("entity_alpha_exposures")
        if not isinstance(exposure_payload, dict):
            raise ValueError("ENTITY_EXPOSURE_ARTIFACT_INVALID")
        save_json_record(
            run_id,
            "entity_alpha_exposures.json",
            exposure_payload,
            output_root=output_root,
        )
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
        persist_exposures = getattr(repository, "upsert_entity_alpha_exposures", None)
        if callable(persist_exposures):
            persist_exposures(
                run_id=run_id,
                ticker=ticker,
                artifact=exposure_payload,
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
        conflict_result = None
        with contextlib.suppress(Exception):
            conflict_result = repository.get_week4_conflict_result(run_id)
            if isinstance(conflict_result, dict):
                conflicts = conflict_result.get("conflicts")
                conflict_count = len(conflicts) if isinstance(conflicts, list) else 0
        write_run_audit_artifact(
            run_id,
            output_root,
            conflict_count=conflict_count,
            conflict_payload=conflict_result,
            repository=repository,
        )


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


def get_entity_alpha_exposures(
    run_id, output_root="outputs/runs", *, graph_repository=None
):
    """Read a run's Exposure sidecar, with an old-run-safe empty fallback."""
    try:
        safe_run_id = validate_run_id_for_path(run_id)
        run_dir = run_dir_for(safe_run_id, output_root)
    except ValueError:
        return {
            "schema_version": "entity_alpha_exposure.run.v1",
            "run_id": str(run_id),
            "ticker": None,
            "status": "unavailable",
            "records": [],
            "reason_codes": ["INVALID_RUN_ID"],
        }
    metadata = load_json_record_if_exists(safe_run_id, "metadata.json", output_root=output_root)
    ticker = metadata.get("ticker")
    if not run_dir.exists():
        return {
            "schema_version": "entity_alpha_exposure.run.v1",
            "run_id": safe_run_id,
            "ticker": ticker,
            "status": "unavailable",
            "records": [],
            "reason_codes": ["RUN_NOT_FOUND"],
        }
    artifact = load_json_record_if_exists(
        safe_run_id, "entity_alpha_exposures.json", output_root=output_root
    )
    if isinstance(artifact.get("records"), list):
        return {**artifact, "status": "ready"}
    try:
        repository = graph_repository or build_repository_from_env(output_root)
        records = repository.get_entity_alpha_exposures(safe_run_id)
    except Exception:
        records = []
    return {
        "schema_version": "entity_alpha_exposure.run.v1",
        "run_id": safe_run_id,
        "ticker": ticker,
        "status": "ready" if records else "unavailable",
        "records": records,
        "reason_codes": [] if records else ["ENTITY_EXPOSURE_UNAVAILABLE"],
    }


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

    @router.get("/api/research/{run_id}/entity-exposures")
    def get_research_entity_exposures_route(run_id: str, http_request: Request):
        return get_entity_alpha_exposures(run_id, _request_output_root(http_request))

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
