"""Initial COMQUTOR runner: upstream capture and immutable raw artifacts."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from comqutor_alpha.config import ComqutorConfig, normalize_analysis_date, normalize_ticker
from comqutor_alpha.integration.state_capture import capture_analyst_reports
from comqutor_alpha.integration.tradingagents_runner import TradingAgentsRunner, build_real_runner
from comqutor_alpha.storage.artifact_store import ArtifactStore


def _upstream_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        check=False,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def capture_run(
    *,
    runner: TradingAgentsRunner,
    store: ArtifactStore,
    config: ComqutorConfig,
    ticker: str,
    analysis_date: str,
    asset_type: str = "stock",
    run_id: UUID | None = None,
    created_at: datetime | None = None,
) -> Path:
    current_run_id = run_id or uuid4()
    timestamp = created_at or datetime.now(UTC)
    normalized_ticker = normalize_ticker(ticker)
    normalized_date = normalize_analysis_date(analysis_date)
    upstream = runner.run(normalized_ticker, normalized_date, asset_type)
    reports = capture_analyst_reports(
        upstream.final_state,
        run_id=current_run_id,
        ticker=normalized_ticker,
        analysis_date=normalized_date,
        captured_at=timestamp,
    )
    metadata = {
        "run_id": str(current_run_id),
        "ticker": normalized_ticker,
        "analysis_date": normalized_date.isoformat(),
        "asset_type": asset_type,
        "created_at": timestamp.isoformat(),
        "upstream_commit": _upstream_commit(),
        "config_fingerprint": config.fingerprint(),
        "provider": config.llm_provider,
        "models": {
            "quick": config.quick_model,
            "deep": config.deep_model,
            "adapter": config.adapter_model,
        },
        "status": "captured",
    }
    upstream_decision = {
        "comparison_only": True,
        "processed_decision": upstream.processed_decision,
        "final_trade_decision": upstream.final_state.get("final_trade_decision"),
    }
    return store.write_initial_run(
        run_id=current_run_id,
        metadata=metadata,
        raw_reports=[report.model_dump(mode="json") for report in reports],
        upstream_decision=upstream_decision,
    )


class _FixtureGraph:
    def __init__(self, return_value: Sequence[Any]):
        self.return_value = tuple(return_value)

    def propagate(
        self,
        company_name: str,
        trade_date: str,
        asset_type: str = "stock",
    ) -> tuple[Mapping[str, Any], Any]:
        del company_name, trade_date, asset_type
        return self.return_value  # type: ignore[return-value]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--analysis-date", required=True)
    parser.add_argument("--asset-type", default="stock", choices=("stock", "crypto"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/runs"))
    parser.add_argument("--fixture", type=Path, help="Offline upstream return fixture")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = ComqutorConfig(output_dir=args.output_dir)
    if args.fixture:
        fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
        runner = TradingAgentsRunner(_FixtureGraph(fixture["return_value"]))
    else:
        runner = build_real_runner()
    output = capture_run(
        runner=runner,
        store=ArtifactStore(config.output_dir),
        config=config,
        ticker=args.ticker,
        analysis_date=args.analysis_date,
        asset_type=args.asset_type,
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
