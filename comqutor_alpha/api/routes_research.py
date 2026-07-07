"""Week 1A research entrypoint helpers and optional FastAPI routes."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from comqutor_alpha.storage.file_store import load_json_record
from comqutor_alpha.structure_engine.structured_output_adapter import save_structured_agent_outputs


def _utc_timestamp():
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json_if_exists(path):
    path = Path(path)
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _normalize_payload(payload):
    return payload if isinstance(payload, dict) else {}


def _create_offline_run(payload, output_root):
    payload = _normalize_payload(payload)
    run_id = str(payload.get("run_id") or uuid4())
    ticker = str(payload.get("ticker") or "unknown").upper()
    run_dir = Path(output_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    raw_outputs = payload.get("offline_raw_agent_outputs") or []
    metadata = {
        "run_id": run_id,
        "ticker": ticker,
        "analysis_date": payload.get("analysis_date"),
        "created_at": _utc_timestamp(),
        "selected_analysts": payload.get("selected_analysts", []),
        "source": "COMQUTOR Week 1A offline research entrypoint",
        "output_version": "week1a.api.v1",
    }
    raw_payload = {
        "run_id": run_id,
        "ticker": ticker,
        "agent_outputs": raw_outputs,
    }
    _write_json(run_dir / "metadata.json", metadata)
    _write_json(run_dir / "raw_agent_outputs.json", raw_payload)
    return run_dir


def _count_raw_outputs(raw_payload):
    outputs = raw_payload.get("agent_outputs", [])
    return len(outputs) if isinstance(outputs, list) else 0


def _count_structured_outputs(structured_payload):
    records = structured_payload.get("records", [])
    return len(records) if isinstance(records, list) else 0


def build_research_response(run_dir):
    run_dir = Path(run_dir)
    metadata_path = run_dir / "metadata.json"
    raw_path = run_dir / "raw_agent_outputs.json"
    structured_path = run_dir / "structured_agent_outputs.json"
    metadata = _read_json_if_exists(metadata_path)
    raw_payload = _read_json_if_exists(raw_path)
    structured_payload = _read_json_if_exists(structured_path)
    run_id = metadata.get("run_id") or raw_payload.get("run_id") or run_dir.name
    ticker = metadata.get("ticker") or raw_payload.get("ticker") or structured_payload.get("ticker")

    return {
        "run_id": run_id,
        "ticker": ticker,
        "status": "completed" if raw_path.exists() and structured_path.exists() else "partial",
        "run_dir": str(run_dir),
        "metadata_path": str(metadata_path) if metadata_path.exists() else None,
        "raw_agent_outputs_path": str(raw_path) if raw_path.exists() else None,
        "structured_agent_outputs_path": str(structured_path) if structured_path.exists() else None,
        "agent_output_count": _count_raw_outputs(raw_payload),
        "structured_output_count": _count_structured_outputs(structured_payload),
    }


def run_research_request(payload, runner=None, output_root="outputs/runs"):
    payload = _normalize_payload(payload)
    try:
        if runner is not None:
            run_dir = Path(runner(payload, output_root=output_root))
        elif payload.get("offline_raw_agent_outputs") is not None:
            run_dir = _create_offline_run(payload, output_root)
        else:
            from comqutor_alpha.runners.tradingagents_runner import (
                run_original_tradingagents_research,
            )

            run_dir = Path(run_original_tradingagents_research(payload, output_root=output_root))

        raw_path = run_dir / "raw_agent_outputs.json"
        if not raw_path.exists():
            raise FileNotFoundError(f"raw_agent_outputs.json not found in {run_dir}")
        save_structured_agent_outputs(run_dir)
        return build_research_response(run_dir)
    except Exception as exc:
        return {
            "run_id": payload.get("run_id"),
            "ticker": payload.get("ticker"),
            "status": "failed",
            "error": str(exc),
        }


def get_research_run(run_id, output_root="outputs/runs"):
    run_dir = Path(output_root) / str(run_id)
    if not run_dir.exists():
        return {
            "run_id": str(run_id),
            "ticker": None,
            "status": "failed",
            "error": f"Run directory not found: {run_dir}",
        }
    return build_research_response(run_dir)


def get_research_response(run_id, output_root="outputs/runs"):
    return load_json_record(run_id, "research_response.json", output_root=output_root)


try:
    from fastapi import APIRouter

    router = APIRouter()

    @router.post("/api/research")
    def post_research(payload: dict):
        return run_research_request(payload)

    @router.get("/api/research/{run_id}")
    def get_research_run_route(run_id: str):
        return get_research_run(run_id)

except ImportError:
    router = None
