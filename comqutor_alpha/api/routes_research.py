"""Week 1A research entrypoint helpers and optional FastAPI routes."""

from __future__ import annotations

import contextlib
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
from comqutor_alpha.api.agent_output_reader import get_agent_outputs_response
from comqutor_alpha.conflict_engine.pipeline import run_week4_conflict_pipeline
from comqutor_alpha.graph_engine.graph_schema import GRAPH_SCHEMA_VERSION
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

TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
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
        "RAW_OUTPUT_NOT_FOUND",
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
        logger.debug(
            "week4 response enrichment failed unexpectedly (run_id=%s)", run_id, exc_info=True
        )
    return dominant_alphas, main_conflict, conflict_status


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
    }

# Run a research request with the given payload, optionally using a custom runner.
def _log_pipeline_error(run_id, output_root, stage):
    append_jsonl_record(
        run_id,
        PIPELINE_ERROR_LOG_ARTIFACT_PATH,
        {
            "run_id": run_id,
            "stage": stage,
            "error_code": "WEEK2_ARTIFACT_GENERATION_FAILED",
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


def _run_week1_week2_artifact_pipeline(run_dir, llm_gateway=None):
    run_dir = Path(run_dir).expanduser().resolve()
    run_id = validate_run_id_for_path(run_dir.name)
    output_root = run_dir.parent

    try:
        save_structured_agent_outputs(run_dir, llm_gateway=llm_gateway)
    except Exception:
        _log_pipeline_error(run_id, output_root, "structured_agent_outputs")
        return

    for stage, writer in (
        ("alpha_matches", save_alpha_matches),
        ("extracted_structures", save_extracted_structures),
    ):
        try:
            writer(run_id, output_root=output_root, llm_gateway=llm_gateway)
        except Exception:
            _log_pipeline_error(run_id, output_root, stage)


def _run_week3_graph_pipeline(run_dir, *, graph_repository=None):
    """Build, persist (file + DB), and score the Week 3 Structure Graph.

    Only runs after Week 1-2 artifacts exist; any failure at any step is
    caught, logged with a stable safe reason code, and never propagates --
    a Week 3 failure must never take down or alter the Week 1-2 response.
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
    except Exception:
        _log_week3_pipeline_error(run_id, output_root, "structure_graph_inputs")
        return

    try:
        graph = build_structure_graph_stage(alpha_matches_payload, extracted_structures_payload)
    except Exception:
        _log_week3_pipeline_error(run_id, output_root, "structure_graph_construction")
        return

    try:
        graph_payload = score_and_assemble_structure_graph(
            graph,
            alpha_matches_payload,
            extracted_structures_payload,
            run_timestamp=run_timestamp,
        )
    except Exception:
        _log_week3_pipeline_error(run_id, output_root, "activation_scoring")
        return

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
    with contextlib.suppress(Exception):
        run_week4_conflict_pipeline(
            run_id=run_id,
            ticker=ticker,
            graph_payload=graph_payload,
            alpha_matches_payload=alpha_matches_payload,
            repository=repository,
            output_root=output_root,
        )


def run_research_request(
    payload,
    runner=None,
    output_root="outputs/runs",
    *,
    week2_llm_gateway=None,
    graph_repository=None,
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
        else:
            from comqutor_alpha.runners.tradingagents_runner import (
                run_original_tradingagents_research,
            )

            run_dir = Path(run_original_tradingagents_research(payload, output_root=output_root))
            run_id = validate_run_id_for_path(run_dir.name)

        raw_path = run_dir / "raw_agent_outputs.json"
        if not raw_path.exists():
            raise FileNotFoundError("raw_agent_outputs.json not found")
        if week2_llm_gateway is None:
            week2_llm_gateway = build_server_week2_llm_gateway(run_id, run_dir.parent)
        _run_week1_week2_artifact_pipeline(run_dir, week2_llm_gateway)
        # Week 3 graph build/score/persist is a side effect of a successful
        # POST; its own status is reported only via GET .../graph so the
        # frozen Week 1-2 response contract above never changes shape.
        _run_week3_graph_pipeline(run_dir, graph_repository=graph_repository)
        return build_research_response(run_id, output_root=output_root, graph_repository=graph_repository)
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


def _graph_error_response(run_id, ticker, error_code):
    return {
        "run_id": run_id,
        "ticker": ticker,
        "status": "failed",
        "error_code": error_code,
        "message": _GRAPH_ERROR_MESSAGES[error_code],
    }


# Retrieve the exact persisted Structure Graph for a run_id. Pure read path:
# validated run_id -> cheap filesystem existence check -> one DB SELECT. Never
# invokes TradingAgents/LLM, never rebuilds the graph, never mutates storage.
def get_persisted_structure_graph(run_id, output_root="outputs/runs", *, graph_repository=None):
    try:
        safe_run_id = validate_run_id_for_path(run_id)
    except ValueError:
        return _graph_error_response(str(run_id), None, "INVALID_RUN_ID")

    run_dir = run_dir_for(safe_run_id, output_root)
    if not run_dir.exists():
        return _graph_error_response(safe_run_id, None, "RUN_NOT_FOUND")

    try:
        repository = graph_repository or build_repository_from_env(output_root)
        row = repository.get_graph(safe_run_id)
    except GraphPersistenceError as exc:
        logger.warning(
            "graph retrieval failed (run_id=%s, reason_code=%s)", safe_run_id, exc.reason_code
        )
        return _graph_error_response(safe_run_id, None, "GRAPH_UNAVAILABLE")
    except Exception as exc:
        # Anything else (engine construction, filesystem, driver import) must
        # still degrade safely rather than leak a traceback/DSN to the
        # caller -- and, unlike the client response, the *server log* must
        # stay safe by default too: a raw driver/SQLAlchemy exception's text
        # routinely embeds the DSN, host, or username. The default (WARNING)
        # log line below carries only run_id + the exception's type name.
        # The full traceback is only ever emitted at DEBUG (see the
        # `logger.debug` call), which is off unless an operator has
        # explicitly configured their logging handler for it -- a
        # deliberate, local action, never the production default.
        logger.warning(
            "graph retrieval failed unexpectedly (run_id=%s, exc_type=%s)",
            safe_run_id,
            type(exc).__name__,
        )
        logger.debug(
            "graph retrieval failed unexpectedly (run_id=%s)", safe_run_id, exc_info=True
        )
        return _graph_error_response(safe_run_id, None, "GRAPH_UNAVAILABLE")

    if row is None:
        return _graph_error_response(safe_run_id, None, "GRAPH_NOT_READY")

    graph_json = row.get("graph_json")
    required_keys = {"schema_version", "nodes", "edges", "activation", "dominant_alphas"}
    if not isinstance(graph_json, dict) or not required_keys.issubset(graph_json):
        logger.warning("persisted graph is corrupted (run_id=%s)", safe_run_id)
        return _graph_error_response(safe_run_id, row.get("ticker"), "GRAPH_CORRUPTED")
    if graph_json.get("schema_version") != GRAPH_SCHEMA_VERSION:
        logger.warning(
            "persisted graph schema mismatch (run_id=%s, found=%s)",
            safe_run_id,
            graph_json.get("schema_version"),
        )
        return _graph_error_response(safe_run_id, row.get("ticker"), "GRAPH_SCHEMA_MISMATCH")

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
        "activation": graph_json.get("activation", {}),
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
        logger.debug(
            "conflicts retrieval failed unexpectedly (run_id=%s)", safe_run_id, exc_info=True
        )
        return _conflicts_error_response(safe_run_id, "CONFLICTS_UNAVAILABLE")

    if result is None:
        return _conflicts_error_response(safe_run_id, "CONFLICTS_NOT_READY")

    # Equal to the W4.2 deterministic reconstruction, with exactly one
    # additive top-level field (status="ok") -- every other key/value comes
    # straight from `result`, unmodified.
    return {**result, "status": "ok"}


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


# Retrieve one run's lifecycle status. Pure read path: validated run_id ->
# one DB SELECT against research_runs only. Never reads raw/structured
# agent output files, never reads a graph file, never invokes an LLM or the
# network, never performs a migration or a write.
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
        logger.debug(
            "run status retrieval failed unexpectedly (run_id=%s)", safe_run_id, exc_info=True
        )
        return _run_status_error_response(safe_run_id, "RUN_STATUS_UNAVAILABLE")

    if record is None:
        return _run_status_error_response(safe_run_id, "RUN_STATUS_NOT_FOUND")
    if not _RUN_STATUS_REQUIRED_FIELDS.issubset(record) or record.get("status") not in RESEARCH_RUN_STATUSES:
        logger.warning("persisted run status is corrupted (run_id=%s)", safe_run_id)
        return _run_status_error_response(safe_run_id, "RUN_STATUS_CORRUPTED")

    return _public_run_record_fields(record)


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
        logger.debug("run history retrieval failed unexpectedly", exc_info=True)
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
    # OFFLINE_DISABLED, INVALID_ANALYST_SELECTION, CACHED_RUN_UNAVAILABLE,
    # INTERNAL_ERROR) is a safe, generic 500 -- never guessed at per-code.
    _RESEARCH_SUBMISSION_ERROR_HTTP_STATUS = {
        "RUN_ID_CONFLICT": 409,
        "INVALID_FORCE_REFRESH": 409,
        "REAL_FORCE_REFRESH_DISABLED": 403,
        "REAL_RUN_DISABLED": 503,
        "REAL_RUN_CONFIG_INVALID": 503,
        "RESEARCH_QUEUE_FULL": 503,
        "JOB_MANAGER_UNAVAILABLE": 503,
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
        output_root = _request_output_root(http_request)
        return get_agent_outputs_response(run_id, output_root if output_root is not None else "outputs/runs")

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
