"""Deterministic per-ticker saved-run selection for A4 (task section 7).

Never creates a new TradingAgents run, never calls a Provider. Selection
is purely a function of what already exists: file-system state
(``outputs/runs/<run_id>/metadata.json`` + artifact presence) and,
separately, database state (``research_runs`` row, when a repository is
supplied) -- reported independently, never assumed to agree. Read-only
throughout: never writes ``artifact_manifest.json`` (or anything else)
into a source run's own directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from comqutor_alpha.api.artifact_export import REQUIRED_ARTIFACT_FILENAMES
from comqutor_alpha.storage.file_store import resolve_output_root

STATUS_SELECTED = "selected"
STATUS_RUN_ARTIFACT_NOT_AVAILABLE = "RUN_ARTIFACT_NOT_AVAILABLE"

# The only two files run_structure_replay actually requires (see
# comqutor_alpha.replay.pipeline.run_structure_replay's own
# ReplaySourceIncompleteError guard). A2's full 9-artifact
# REQUIRED_ARTIFACT_FILENAMES is checked and reported separately, purely
# informational -- many legitimately replayable saved runs predate the A2
# finalizer and will never have all 9 on disk.
REPLAY_HARD_REQUIREMENTS = ("metadata.json", "raw_agent_outputs.json")


def _read_metadata(run_dir: Path) -> dict[str, Any] | None:
    path = run_dir / "metadata.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _file_artifact_completeness(run_dir: Path) -> tuple[str, list[str]]:
    missing = [name for name in REQUIRED_ARTIFACT_FILENAMES if not (run_dir / name).exists()]
    return ("pass" if not missing else "fail"), missing


def _replay_eligible(run_dir: Path) -> bool:
    return all((run_dir / name).exists() for name in REPLAY_HARD_REQUIREMENTS)


def discover_candidate_runs(ticker: str, output_root: str | Path | None = None) -> list[dict[str, Any]]:
    """Every saved run directory under ``output_root`` whose metadata.json
    ticker matches (case-insensitive). Pure file-system scan, sorted by
    ``run_id`` for a stable base iteration order -- final selection
    ordering is applied separately in :func:`select_run_for_ticker`."""
    root = resolve_output_root(output_root)
    ticker_upper = str(ticker).upper()
    candidates: list[dict[str, Any]] = []
    if not root.exists():
        return candidates
    for run_dir in sorted(root.iterdir()):
        if not run_dir.is_dir():
            continue
        metadata = _read_metadata(run_dir)
        if metadata is None:
            continue
        if str(metadata.get("ticker") or "").upper() != ticker_upper:
            continue
        file_completeness, missing = _file_artifact_completeness(run_dir)
        candidates.append(
            {
                "run_id": run_dir.name,
                "ticker": metadata.get("ticker"),
                "analysis_date": metadata.get("analysis_date"),
                "created_at": metadata.get("created_at"),
                "file_artifact_completeness": file_completeness,
                "file_artifact_missing": missing,
                "replay_eligible": _replay_eligible(run_dir),
            }
        )
    return candidates


def _selection_sort_key(candidate: dict[str, Any]) -> tuple:
    # Deterministic: latest analysis_date, then latest created_at, then
    # run_id as the final tie-breaker -- never directory/OS/DB incidental
    # ordering.
    return (
        str(candidate.get("analysis_date") or ""),
        str(candidate.get("created_at") or ""),
        str(candidate.get("run_id") or ""),
    )


def select_run_for_ticker(
    ticker: str, output_root: str | Path | None = None, *, repository: Any = None
) -> dict[str, Any]:
    """Deterministically selects one saved run to regression-test for
    ``ticker``.

    Preference order: among replay-eligible candidates (metadata.json +
    raw_agent_outputs.json present), prefer ones whose file artifact
    completeness (A2's 9-required-artifact contract, checked read-only)
    passes; within that pool, latest analysis_date, then latest
    created_at, then run_id as the final deterministic tie-breaker. A
    replay-ineligible candidate is never selected even if it is the only
    one available for this ticker -- reported as
    ``RUN_ARTIFACT_NOT_AVAILABLE`` instead of a Provider re-run.

    Database state is reported independently via ``database_record_status``
    and never influences selection -- a saved run legitimately predates
    the current database, or the database file legitimately predates the
    run (see task section 7's explicit FILE_ARTIFACT_STATUS/
    DATABASE_RECORD_STATUS split).
    """
    candidates = discover_candidate_runs(ticker, output_root)
    eligible = [c for c in candidates if c["replay_eligible"]]
    if not eligible:
        return {
            "ticker": str(ticker).upper(),
            "run_selection_status": STATUS_RUN_ARTIFACT_NOT_AVAILABLE,
            "run_id": None,
            "analysis_date": None,
            "created_at": None,
            "file_artifact_completeness": None,
            "file_artifact_missing": [],
            "database_record_status": "not_applicable",
            "candidates_considered": len(candidates),
            "replay_eligible_candidates": 0,
            "selected_from_complete_pool": False,
        }

    complete = [c for c in eligible if c["file_artifact_completeness"] == "pass"]
    pool = complete or eligible
    selected = sorted(pool, key=_selection_sort_key, reverse=True)[0]

    database_record_status = "not_checked"
    if repository is not None:
        db_record = None
        try:
            db_record = repository.get_research_run_record(selected["run_id"])
        except Exception:
            database_record_status = "DATABASE_READ_FAILED"
        else:
            database_record_status = f"found:{db_record.get('status')}" if db_record else "not_found"

    return {
        "ticker": str(ticker).upper(),
        "run_selection_status": STATUS_SELECTED,
        "run_id": selected["run_id"],
        "analysis_date": selected["analysis_date"],
        "created_at": selected["created_at"],
        "file_artifact_completeness": selected["file_artifact_completeness"],
        "file_artifact_missing": selected["file_artifact_missing"],
        "database_record_status": database_record_status,
        "candidates_considered": len(candidates),
        "replay_eligible_candidates": len(eligible),
        "selected_from_complete_pool": bool(complete),
    }


__all__ = [
    "STATUS_SELECTED",
    "STATUS_RUN_ARTIFACT_NOT_AVAILABLE",
    "REPLAY_HARD_REQUIREMENTS",
    "discover_candidate_runs",
    "select_run_for_ticker",
]
