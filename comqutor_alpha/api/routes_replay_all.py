"""POST /api/replay-all -- batch-reprocess every saved TradingAgents raw
output under ``outputs/runs/`` through the current COMQUTOR structure
pipeline.

Deliberately minimal, per this Sprint's explicit scope: no new job queue,
no database writes, no polling page. The whole batch runs synchronously to
completion inside one HTTP request and returns the full per-run result
list in the response body. A single process-wide ``threading.Lock``
prevents a second concurrent batch from starting while one is already in
flight (HTTP 409 instead of queuing or interleaving two batches).

Every actual replay is delegated unchanged to
``comqutor_alpha.replay.pipeline.run_structure_replay`` -- this module
never re-implements segmentation/matching/graph-building, never calls
TradingAgents or a Provider, and never writes to ``research_runs`` or any
other database table.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

from comqutor_alpha.replay.pipeline import (
    DEFAULT_REPLAY_OUTPUT_ROOT,
    DEFAULT_SOURCE_OUTPUT_ROOT,
    ReplaySourceIncompleteError,
    run_structure_replay,
)
from comqutor_alpha.storage.file_store import resolve_output_root, validate_run_id_for_path

logger = logging.getLogger(__name__)

# Process-wide, not per-app-instance: represents "is a replay-all batch
# currently running in this process", which is exactly what a simple
# in-process lock (as explicitly scoped for this task -- no new generic
# job queue) is meant to express.
_REPLAY_ALL_LOCK = threading.Lock()


def _discover_source_runs(source_output_root: str) -> list[tuple[str, str | None]]:
    """Every immediate subdirectory of ``source_output_root`` that is (a) a
    legal run_id and (b) has a ``raw_agent_outputs.json`` that actually
    parses as JSON. Never treats ``structured_agent_outputs.json`` as a
    substitute input -- a directory missing the raw artifact, or with one
    that fails to parse, is silently skipped here (not an error; the batch
    simply never attempts that run). Returns ``(run_id, ticker)`` pairs,
    sorted by run_id for deterministic ordering.
    """
    root = resolve_output_root(source_output_root)
    if not root.exists():
        return []
    discovered: list[tuple[str, str | None]] = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name):
        if not entry.is_dir():
            continue
        try:
            run_id = validate_run_id_for_path(entry.name)
        except ValueError:
            continue
        raw_path = entry / "raw_agent_outputs.json"
        if not raw_path.exists():
            continue
        try:
            raw_payload = json.loads(raw_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        ticker = raw_payload.get("ticker") if isinstance(raw_payload, dict) else None
        discovered.append((run_id, str(ticker) if ticker else None))
    return discovered


def replay_all_saved_outputs(
    *,
    source_output_root: str = DEFAULT_SOURCE_OUTPUT_ROOT,
    replay_output_root: str = DEFAULT_REPLAY_OUTPUT_ROOT,
) -> dict[str, Any]:
    """The actual batch logic -- importable/testable independent of FastAPI.

    Never raises for an individual run's failure: each source run is
    isolated in its own try/except, recorded as ``"failed"`` in ``results``,
    and the loop continues. A source run's own artifacts are never written
    to (``run_structure_replay`` only reads them) and this function never
    calls TradingAgents, an LLM provider, a market-data provider, or writes
    to any database table.
    """
    source_runs = _discover_source_runs(source_output_root)
    results: list[dict[str, Any]] = []
    completed_count = 0
    blocked_count = 0
    failed_count = 0

    for source_run_id, ticker in source_runs:
        try:
            result = run_structure_replay(
                source_run_id=source_run_id,
                source_output_root=source_output_root,
                replay_output_root=replay_output_root,
                persist=True,
                comparison=True,
            )
        except ReplaySourceIncompleteError:
            failed_count += 1
            results.append(
                {
                    "source_run_id": source_run_id,
                    "ticker": ticker,
                    "replay_run_id": None,
                    "status": "failed",
                    "output_dir": None,
                    "error_code": "REPLAY_SOURCE_INCOMPLETE",
                }
            )
            continue
        except Exception as exc:
            # Never leak a raw exception message (could embed a filesystem
            # path) -- only a stable reason code and the exception's type
            # name land in the server log; the batch continues regardless.
            logger.warning(
                "replay-all: run failed unexpectedly (source_run_id=%s, exc_type=%s)",
                source_run_id,
                type(exc).__name__,
            )
            failed_count += 1
            results.append(
                {
                    "source_run_id": source_run_id,
                    "ticker": ticker,
                    "replay_run_id": None,
                    "status": "failed",
                    "output_dir": None,
                    "error_code": "REPLAY_SERVICE_ERROR",
                }
            )
            continue

        if result.status == "completed":
            completed_count += 1
        elif result.status == "blocked":
            blocked_count += 1
        else:
            failed_count += 1

        results.append(
            {
                "source_run_id": source_run_id,
                "ticker": ticker,
                "replay_run_id": result.replay_run_id,
                "status": result.status,
                "output_dir": result.output_dir,
                "error_code": result.error,
            }
        )

    return {
        "status": "completed",
        "total_runs_found": len(source_runs),
        "completed_count": completed_count,
        "blocked_count": blocked_count,
        "failed_count": failed_count,
        "results": results,
        # Structurally guaranteed, not merely observed: run_structure_replay
        # never calls TradingAgents or a Provider, so this batch cannot have
        # made any such call regardless of how many runs it processed.
        "provider_calls": 0,
        "tradingagents_calls": 0,
    }


try:
    from fastapi import APIRouter, Request
    from fastapi.responses import JSONResponse

    router = APIRouter()

    @router.post("/api/replay-all")
    def post_replay_all(http_request: Request):
        # Mirrors every other route's _request_output_root pattern (see
        # routes_research.py) so a server configured with a custom
        # output_root/COMQUTOR_OUTPUT_DIR sees replay-all operate on the
        # same source directory -- and lets tests point both roots at an
        # isolated tmp_path via app.state instead of the real outputs/.
        source_output_root = getattr(http_request.app.state, "output_root", None) or DEFAULT_SOURCE_OUTPUT_ROOT
        replay_output_root = (
            getattr(http_request.app.state, "replay_output_root", None) or DEFAULT_REPLAY_OUTPUT_ROOT
        )

        acquired = _REPLAY_ALL_LOCK.acquire(blocking=False)
        if not acquired:
            return JSONResponse(
                content={
                    "status": "failed",
                    "error_code": "REPLAY_ALL_ALREADY_RUNNING",
                    "message": "A replay-all batch is already running. Wait for it to finish and try again.",
                },
                status_code=409,
            )
        try:
            result = replay_all_saved_outputs(
                source_output_root=source_output_root, replay_output_root=replay_output_root
            )
            return JSONResponse(content=result, status_code=200)
        finally:
            _REPLAY_ALL_LOCK.release()

except ImportError:
    router = None


__all__ = ["replay_all_saved_outputs", "router"]
