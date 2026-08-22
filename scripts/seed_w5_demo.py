#!/usr/bin/env python3
"""Seed the isolated W5 demo cache from approved deterministic fixtures."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.engine import make_url

from comqutor_alpha.api.agent_output_reader import get_agent_outputs_response
from comqutor_alpha.api.routes_research import (
    get_persisted_conflicts,
    get_persisted_structure_graph,
    get_research_run,
    get_research_run_history,
    run_research_request,
)
from comqutor_alpha.research_lifecycle import (
    build_research_request_fingerprint,
    build_research_request_identity,
)
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from comqutor_alpha.storage.file_store import (
    load_json_record,
    run_dir_for,
    save_json_record,
)
from scripts.deterministic_echo_llm import build_deterministic_echo_gateway

_fixtures = importlib.import_module(
    "scripts.w5_demo_fixtures" if __package__ else "w5_demo_fixtures"
)
DEMO_ANALYSIS_DATE = _fixtures.DEMO_ANALYSIS_DATE
DEMO_SELECTED_ANALYSTS = _fixtures.DEMO_SELECTED_ANALYSTS
approved_demo_outputs = _fixtures.approved_demo_outputs

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEMO_ROOT = (REPO_ROOT / ".demo" / "w5").resolve()
DEFAULT_OUTPUT_ROOT = DEFAULT_DEMO_ROOT / "outputs" / "runs"
DEFAULT_DATABASE_PATH = DEFAULT_DEMO_ROOT / "comqutor_demo.db"
DEFAULT_DATABASE_URL = f"sqlite:///{DEFAULT_DATABASE_PATH}"

DEMO_RUN_IDS = {
    "NVDA": "w5_demo_nvda_20260630",
    "QQQ": "w5_demo_qqq_20260630",
}


class DemoSeedError(Exception):
    """Stable local-demo setup error without raw fixture or credential content."""


@dataclass(frozen=True)
class DemoTargets:
    output_root: Path
    database_url: str
    database_path: Path | None


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def resolve_demo_targets(
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    database_url: str = DEFAULT_DATABASE_URL,
    *,
    allow_unsafe_target: bool = False,
    environment: Mapping[str, str] | None = None,
) -> DemoTargets:
    """Validate targets before any directory, file, or database is touched."""
    env = environment if environment is not None else os.environ
    resolved_output = Path(output_root).expanduser().resolve()
    production = str(env.get("COMQUTOR_ENV", "")).strip().lower() == "production"

    try:
        parsed_url = make_url(str(database_url))
    except Exception as exc:
        raise DemoSeedError("INVALID_DEMO_DATABASE_URL") from exc

    backend = parsed_url.get_backend_name()
    database_path: Path | None = None
    normalized_url = str(database_url)
    if backend == "sqlite":
        raw_database = parsed_url.database
        if not raw_database or raw_database == ":memory:":
            raise DemoSeedError("DEMO_DATABASE_MUST_BE_FILE_BACKED")
        database_path = Path(raw_database).expanduser()
        if not database_path.is_absolute():
            database_path = (Path.cwd() / database_path).resolve()
        else:
            database_path = database_path.resolve()
        normalized_url = parsed_url.set(database=str(database_path)).render_as_string(
            hide_password=False
        )

    unsafe = (
        production
        or not _is_within(resolved_output, DEFAULT_DEMO_ROOT)
        or backend != "sqlite"
        or database_path is None
        or not _is_within(database_path, DEFAULT_DEMO_ROOT)
    )
    if unsafe and not allow_unsafe_target:
        raise DemoSeedError("UNSAFE_DEMO_TARGET_REQUIRES_CONFIRMATION")

    return DemoTargets(
        output_root=resolved_output,
        database_url=normalized_url,
        database_path=database_path,
    )


@contextmanager
def _offline_only_environment() -> Iterator[None]:
    overrides = {
        "COMQUTOR_ENV": "",
        "COMQUTOR_REAL_TRADINGAGENTS_ENABLED": "false",
        "COMQUTOR_WEEK2_LLM_ENABLED": "false",
    }
    previous = {key: os.environ.get(key) for key in overrides}
    os.environ.update(overrides)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _browser_request(ticker: str) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "analysis_date": DEMO_ANALYSIS_DATE,
        "selected_analysts": list(DEMO_SELECTED_ANALYSTS),
    }


def _build_repository(targets: DemoTargets) -> GraphPersistenceRepository:
    engine = build_engine(targets.database_url, create_if_missing=True)
    apply_migrations(engine)
    return GraphPersistenceRepository(engine, database_url=targets.database_url)


def _record_demo_metadata(run_id: str, output_root: Path) -> None:
    metadata = load_json_record(run_id, "metadata.json", output_root=output_root)
    metadata.update(
        {
            "demo_fixture": True,
            "source": "approved_offline_golden_fixture",
            "live_provider_used": False,
        }
    )
    save_json_record(run_id, "metadata.json", metadata, output_root=output_root)


def _claim_completed_browser_cache(
    repository: GraphPersistenceRepository,
    *,
    ticker: str,
    run_id: str,
) -> None:
    request = _browser_request(ticker)
    identity = build_research_request_identity(request)
    fingerprint = build_research_request_fingerprint(identity)
    claim = repository.claim_research_run(
        run_id=run_id,
        request_fingerprint=fingerprint,
        ticker=identity["ticker"],
        analysis_date=identity["analysis_date"],
        selected_analysts=identity["selected_analysts"],
        execution_mode=identity["execution_mode"],
        provider_identity=identity["provider_identity"],
        model_identity=identity["model_identity"],
        pipeline_identity=identity["pipeline_identity"],
    )
    if claim["disposition"] == "reused_completed":
        if claim["run_id"] != run_id or claim["record"]["status"] != "completed":
            raise DemoSeedError("INVALID_EXISTING_DEMO_CACHE")
        return
    if claim["disposition"] != "created":
        raise DemoSeedError("DEMO_CACHE_CLAIM_NOT_CREATED")
    repository.mark_research_run_running(run_id)
    repository.mark_research_run_terminal(run_id, status="completed")


def verify_demo_case(
    repository: GraphPersistenceRepository,
    output_root: Path,
    ticker: str,
) -> dict[str, Any]:
    ticker = ticker.upper()
    run_id = DEMO_RUN_IDS[ticker]
    record = repository.get_research_run_record(run_id)
    if record is None or record.get("status") != "completed":
        raise DemoSeedError(f"{ticker}_DEMO_RUN_NOT_COMPLETED")

    metadata = load_json_record(run_id, "metadata.json", output_root=output_root)
    expected_metadata = {
        "demo_fixture": True,
        "source": "approved_offline_golden_fixture",
        "live_provider_used": False,
    }
    if any(metadata.get(key) != value for key, value in expected_metadata.items()):
        raise DemoSeedError(f"{ticker}_DEMO_METADATA_INVALID")

    response = get_research_run(run_id, output_root=output_root, graph_repository=repository)
    graph = get_persisted_structure_graph(
        run_id, output_root=output_root, graph_repository=repository
    )
    conflicts = get_persisted_conflicts(
        run_id, output_root=output_root, graph_repository=repository
    )
    agent_outputs = get_agent_outputs_response(
        run_id, output_root=output_root, graph_repository=repository
    )
    history = get_research_run_history(
        ticker=ticker, output_root=output_root, graph_repository=repository
    )

    if response.get("status") != "completed":
        raise DemoSeedError(f"{ticker}_CANONICAL_RESPONSE_NOT_COMPLETED")
    if response.get("structure_graph_status") != "ready" or graph.get("status") != "ok":
        raise DemoSeedError(f"{ticker}_GRAPH_NOT_READY")
    if response.get("conflict_status") != "ready" or conflicts.get("status") != "ok":
        raise DemoSeedError(f"{ticker}_CONFLICTS_NOT_READY")
    if agent_outputs.get("status") != "ok" or not agent_outputs.get(
        "structured_agent_outputs"
    ):
        raise DemoSeedError(f"{ticker}_AGENT_OUTPUTS_NOT_READY")
    if repository.count_agent_outputs(run_id) != agent_outputs.get("count"):
        raise DemoSeedError(f"{ticker}_AGENT_OUTPUTS_DB_INCOMPLETE")
    if history.get("status") != "ok":
        raise DemoSeedError(f"{ticker}_HISTORY_NOT_READY")
    matching_history = [item for item in history["items"] if item.get("run_id") == run_id]
    if len(matching_history) != 1:
        raise DemoSeedError(f"{ticker}_HISTORY_NOT_IDEMPOTENT")

    conflict_ids = [item["conflict_id"] for item in conflicts["conflicts"]]
    main_conflict = conflicts.get("main_conflict")
    if main_conflict is not None and (
        not conflicts["conflicts"] or main_conflict != conflicts["conflicts"][0]
    ):
        raise DemoSeedError(f"{ticker}_MAIN_CONFLICT_NOT_ARBITRATED")
    if ticker == "NVDA":
        if not main_conflict:
            raise DemoSeedError("NVDA_MAIN_CONFLICT_NOT_ARBITRATED")
        if main_conflict.get("conflict_id") != "A101__A304":
            raise DemoSeedError("NVDA_MAIN_CONFLICT_INVALID")
        if (
            main_conflict.get("bull_alpha_id") != "A101"
            or main_conflict.get("bear_alpha_id") != "A304"
            or not main_conflict["bull_structure"].get("claim_ids")
            or not main_conflict["bull_structure"].get("evidence")
            or not main_conflict["bear_structure"].get("claim_ids")
            or not main_conflict["bear_structure"].get("evidence")
        ):
            raise DemoSeedError("NVDA_CONFLICT_TRACEABILITY_INVALID")
    else:
        # Under the primary Activation v2 formula the deliberately thin QQQ
        # fixture (one A501 claim from one agent) legitimately admits zero
        # conflicts. Both approved pairs must still have been *arbitrated*
        # (evaluated by the detector), never silently skipped.
        evaluated_pairs = {
            (item.get("alpha_a"), item.get("alpha_b"))
            for item in conflicts.get("arbitration", {}).get("candidate_evaluations", [])
        }
        if not {("A001", "A501"), ("A003", "A501")}.issubset(evaluated_pairs):
            raise DemoSeedError("QQQ_APPROVED_CONFLICTS_MISSING")

    return {
        "ticker": ticker,
        "run_id": run_id,
        "status": response["status"],
        "structure_graph_status": response["structure_graph_status"],
        "conflict_status": response["conflict_status"],
        "main_conflict": main_conflict["conflict_id"] if main_conflict else None,
        "conflicts": conflict_ids,
        "structured_agent_output_count": agent_outputs["count"],
        "history_count": len(matching_history),
    }


def seed_demo_case(
    repository: GraphPersistenceRepository,
    output_root: Path,
    ticker: str,
) -> dict[str, Any]:
    ticker = ticker.upper()
    run_id = DEMO_RUN_IDS[ticker]
    existing_record = repository.get_research_run_record(run_id)
    if existing_record is not None:
        try:
            if repository.count_agent_outputs(run_id) == 0:
                structured_payload = load_json_record(
                    run_id, "structured_agent_outputs.json", output_root=output_root
                )
                repository.persist_agent_outputs(
                    run_id=run_id,
                    ticker=ticker,
                    structured_payload=structured_payload,
                )
            return verify_demo_case(repository, output_root, ticker)
        except (DemoSeedError, FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
            raise DemoSeedError(f"{ticker}_EXISTING_DEMO_RUN_INVALID") from exc

    run_dir = run_dir_for(run_id, output_root)
    if run_dir.exists():
        shutil.rmtree(run_dir)

    payload = {
        **_browser_request(ticker),
        "run_id": run_id,
        "offline_raw_agent_outputs": approved_demo_outputs(ticker),
    }
    # Pure-LLM Alpha semantic authority: matched_alpha is now exclusively an
    # LLM decision, so the demo (which must stay live_provider_used=False,
    # see expected_metadata above) needs a real, zero-Provider-call Alpha
    # classifier to keep producing a genuine, evidence-differentiated demo
    # dataset -- the same deterministic-echo double the pipeline sanity
    # tests use, never a real Provider call.
    gateway = build_deterministic_echo_gateway(f"w5-demo-seed-{ticker.lower()}", output_root)
    with _offline_only_environment():
        pipeline_response = run_research_request(
            payload,
            output_root=output_root,
            graph_repository=repository,
            week2_llm_gateway=gateway,
        )
    if (
        pipeline_response.get("status") != "completed"
        or pipeline_response.get("structure_graph_status") != "ready"
        or pipeline_response.get("conflict_status") != "ready"
    ):
        raise DemoSeedError(f"{ticker}_WEEK1_TO_4_PIPELINE_FAILED")

    _record_demo_metadata(run_id, output_root)
    _claim_completed_browser_cache(repository, ticker=ticker, run_id=run_id)
    return verify_demo_case(repository, output_root, ticker)


def seed_w5_demo(targets: DemoTargets) -> list[dict[str, Any]]:
    targets.output_root.mkdir(parents=True, exist_ok=True)
    repository = _build_repository(targets)
    return [
        seed_demo_case(repository, targets.output_root, ticker)
        for ticker in DEMO_RUN_IDS
    ]


def verify_w5_demo(targets: DemoTargets) -> list[dict[str, Any]]:
    repository = _build_repository(targets)
    return [
        verify_demo_case(repository, targets.output_root, ticker)
        for ticker in DEMO_RUN_IDS
    ]


def _parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--database-url", default=DEFAULT_DATABASE_URL)
    parser.add_argument(
        "--allow-unsafe-target",
        action="store_true",
        help="Explicitly permit a target outside .demo/w5, PostgreSQL, or production mode.",
    )
    return parser


def main() -> int:
    args = _parser("Seed isolated W5 NVDA and QQQ demo runs.").parse_args()
    try:
        targets = resolve_demo_targets(
            args.output_root,
            args.database_url,
            allow_unsafe_target=args.allow_unsafe_target,
        )
        results = seed_w5_demo(targets)
    except DemoSeedError as exc:
        print(f"W5_DEMO_SEED_FAILED: {exc}")
        return 1

    print("W5_DEMO_SEED_OK")
    for result in results:
        print(
            f"{result['ticker']}: run_id={result['run_id']} "
            f"main_conflict={result['main_conflict']}"
        )
    print("live_provider_used=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
