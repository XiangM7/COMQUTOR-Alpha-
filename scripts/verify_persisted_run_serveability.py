#!/usr/bin/env python3
"""Verify that already-persisted research runs are servable via the current
production read API, without any Provider/TradingAgents calls and without any
semantic recomputation.

This is a read-only operator/demo-preparation diagnostic. It calls the exact
same production functions the live HTTP routes call
(``comqutor_alpha.api.routes_research.get_research_run_status`` /
``build_research_response`` / ``get_persisted_structure_graph`` /
``get_persisted_conflicts``), against a single explicitly-resolved,
read-only repository (``build_repository_from_env``) -- the same database
resolution the API server itself uses. It performs zero writes and inserts
zero rows.

Background: a Phase-1 product-demo-readiness audit reported that a specific
persisted run appeared "not ready" via ad-hoc checks. Phase-2A investigation
found the run's data was fully and correctly persisted in the project's
configured database (Postgres, per ``.env``'s ``COMQUTOR_DATABASE_URL``) --
the ad-hoc checks had instead resolved to the local SQLite fallback (used
only when no ``COMQUTOR_DATABASE_URL`` is present in the process
environment), which predates and never contained that run. This script
exists so that verifying serveability for a given run_id -- e.g. before a
stakeholder demo -- is a single, repeatable, environment-safe command rather
than an ad-hoc check that can silently target the wrong database.

Usage:
    python scripts/verify_persisted_run_serveability.py RUN_ID [RUN_ID ...]

Exit code 0 if every requested run is FULLY_LIVE_SERVABLE, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_dotenv_safely() -> None:
    """Load .env into the process environment, same as scripts/start_live_comqutor.sh.

    Never overrides a variable already exported in the calling shell.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)


def _safe_database_identity(database_url: str) -> str:
    """Return a credential-free description of a DSN: scheme + host/db only."""
    if "://" not in database_url:
        return "unknown"
    scheme, rest = database_url.split("://", 1)
    if scheme.startswith("sqlite"):
        # sqlite:///path -- the path itself carries no credentials.
        return f"{scheme}:///{rest.lstrip('/')}"
    after_at = rest.split("@", 1)[1] if "@" in rest else rest
    return f"{scheme}://{after_at}"


# One of: FULLY_LIVE_SERVABLE, FILE_COMPLETE_DB_INCOMPLETE,
# DB_PRESENT_BUT_INCONSISTENT, FILE_INCOMPLETE, OTHER
#
# Required-artifact completeness is intentionally NOT re-derived here from
# the `artifacts` dict -- some artifacts (e.g. error logs, final_report) are
# legitimately optional and False on a fully successful run. The production
# status-derivation logic in build_research_response already applies the
# authoritative fail-closed completeness check (ticker_consistency,
# artifact_completeness, graph/conflict readiness) to produce `status`; this
# function only classifies based on that existing, authoritative output.
def classify_run_serveability(status_response: dict, main_response: dict) -> str:
    db_row_found = not (
        status_response.get("status") == "failed"
        and status_response.get("error_code") == "RUN_STATUS_NOT_FOUND"
    )

    if not isinstance(main_response, dict) or "status" not in main_response:
        return "OTHER"

    if not db_row_found:
        # No DB row for /status, but build_research_response still returned a
        # shape -- treat "artifacts present at all" as evidence of file
        # completeness (it cannot itself fabricate DB-only fields).
        artifacts = main_response.get("artifacts") or {}
        if artifacts:
            return "FILE_COMPLETE_DB_INCOMPLETE"
        return "OTHER"

    fully_ready = (
        main_response.get("status") == "completed"
        and main_response.get("structure_graph_status") == "ready"
        and main_response.get("conflict_status") == "ready"
    )
    if fully_ready:
        return "FULLY_LIVE_SERVABLE"

    if main_response.get("status") == "partial":
        return "DB_PRESENT_BUT_INCONSISTENT"

    return "OTHER"


def verify_run(run_id: str, repository, output_root: str = "outputs/runs") -> dict:
    from comqutor_alpha.api.routes_research import (
        build_research_response,
        get_persisted_conflicts,
        get_persisted_structure_graph,
        get_research_run_status,
    )

    status_response = get_research_run_status(run_id, graph_repository=repository)
    main_response = build_research_response(run_id, output_root=output_root, graph_repository=repository)
    graph_response = get_persisted_structure_graph(run_id, output_root=output_root, graph_repository=repository)
    conflicts_response = get_persisted_conflicts(run_id, output_root=output_root, graph_repository=repository)

    classification = classify_run_serveability(status_response, main_response)

    dominant_alpha_ids = None
    main_conflict_pair = None
    if isinstance(main_response, dict):
        dominant = main_response.get("dominant_alphas")
        if isinstance(dominant, list):
            dominant_alpha_ids = [a.get("alpha_id") for a in dominant if isinstance(a, dict)]
        main_conflict = main_response.get("main_conflict")
        if isinstance(main_conflict, dict):
            main_conflict_pair = {"alpha_a": main_conflict.get("alpha_a"), "alpha_b": main_conflict.get("alpha_b")}

    return {
        "run_id": run_id,
        "classification": classification,
        "ticker": main_response.get("ticker") if isinstance(main_response, dict) else None,
        "status_response_status": status_response.get("status"),
        "main_response_status": main_response.get("status") if isinstance(main_response, dict) else None,
        "structure_graph_status": main_response.get("structure_graph_status") if isinstance(main_response, dict) else None,
        "conflict_status": main_response.get("conflict_status") if isinstance(main_response, dict) else None,
        "graph_route_status": graph_response.get("status") if isinstance(graph_response, dict) else None,
        "conflicts_route_status": conflicts_response.get("status") if isinstance(conflicts_response, dict) else None,
        "dominant_alpha_ids": dominant_alpha_ids,
        "main_conflict_pair": main_conflict_pair,
        "fully_live_servable": classification == "FULLY_LIVE_SERVABLE",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_ids", nargs="+", help="One or more persisted run_ids to verify.")
    parser.add_argument(
        "--output-root",
        default="outputs/runs",
        help="Directory containing run artifact subdirectories (default: outputs/runs).",
    )
    args = parser.parse_args(argv)

    _load_dotenv_safely()

    from comqutor_alpha.storage.db.engine import resolve_database_url
    from comqutor_alpha.storage.db.repository import build_repository_from_env

    try:
        database_identity = _safe_database_identity(resolve_database_url())
        repository = build_repository_from_env()
    except Exception as exc:  # noqa: BLE001 -- surfaced as a stable, safe report field only
        print(json.dumps({"error": "REPOSITORY_UNAVAILABLE", "reason": type(exc).__name__}, indent=2))
        return 1

    results = [verify_run(run_id, repository, output_root=args.output_root) for run_id in args.run_ids]
    all_servable = all(r["fully_live_servable"] for r in results)

    report = {
        "database_identity": database_identity,
        "provider_calls": 0,
        "tradingagents_calls": 0,
        "semantic_recomputation": False,
        "results": results,
        "all_fully_live_servable": all_servable,
    }
    print(json.dumps(report, indent=2))
    return 0 if all_servable else 1


if __name__ == "__main__":
    raise SystemExit(main())
