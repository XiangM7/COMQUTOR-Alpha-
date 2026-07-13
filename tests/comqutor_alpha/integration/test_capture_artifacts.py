from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from comqutor_alpha.config import ComqutorConfig, ConfigurationError, normalize_ticker
from comqutor_alpha.integration.state_capture import StateCaptureError, capture_analyst_reports
from comqutor_alpha.integration.tradingagents_runner import (
    TradingAgentsRunner,
    UpstreamContractError,
)
from comqutor_alpha.scripts.run_comqutor_research import capture_run
from comqutor_alpha.storage.artifact_store import ArtifactStore, ArtifactStoreError

FIXTURE = Path(__file__).parents[1] / "fixtures/upstream_state_minimal.json"
RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


class FakeGraph:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def propagate(self, company_name, trade_date, asset_type="stock"):
        self.calls.append((company_name, trade_date, asset_type))
        return self.result


def _fixture_return():
    return tuple(json.loads(FIXTURE.read_text())["return_value"])


@pytest.mark.integration
def test_fake_graph_end_to_end_generates_immutable_artifacts(tmp_path: Path) -> None:
    graph = FakeGraph(_fixture_return())
    config = ComqutorConfig(output_dir=tmp_path / "runs")
    output = capture_run(
        runner=TradingAgentsRunner(graph),
        store=ArtifactStore(config.output_dir),
        config=config,
        ticker="nvda",
        analysis_date="2026-01-15",
        run_id=RUN_ID,
        created_at=NOW,
    )

    assert graph.calls == [("NVDA", "2026-01-15", "stock")]
    assert sorted(path.name for path in output.iterdir()) == [
        "metadata.json",
        "raw_agent_outputs.json",
        "upstream_decision.json",
    ]
    metadata = json.loads((output / "metadata.json").read_text())
    reports = json.loads((output / "raw_agent_outputs.json").read_text())
    decision = json.loads((output / "upstream_decision.json").read_text())
    assert metadata["run_id"] == str(RUN_ID)
    assert metadata["ticker"] == "NVDA"
    assert len(metadata["config_fingerprint"]) == 64
    assert [report["agent"] for report in reports] == [
        "market",
        "sentiment",
        "news",
        "fundamentals",
    ]
    assert decision["comparison_only"] is True
    assert not list(config.output_dir.glob(".tmp-*"))

    with pytest.raises(ArtifactStoreError, match="run already exists") as duplicate:
        capture_run(
            runner=TradingAgentsRunner(graph),
            store=ArtifactStore(config.output_dir),
            config=config,
            ticker="NVDA",
            analysis_date="2026-01-15",
            run_id=RUN_ID,
            created_at=NOW,
        )
    assert duplicate.value.error_code == "duplicate_run_id"


@pytest.mark.contract
@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda state: state.pop("news_report"), "missing_report"),
        (lambda state: state.__setitem__("market_report", ""), "empty_report"),
        (lambda state: state.__setitem__("sentiment_report", []), "invalid_report_type"),
    ],
)
def test_state_capture_has_typed_errors(mutation, code) -> None:
    state = dict(_fixture_return()[0])
    mutation(state)
    with pytest.raises(StateCaptureError) as caught:
        capture_analyst_reports(
            state,
            run_id=RUN_ID,
            ticker="NVDA",
            analysis_date="2026-01-15",
            captured_at=NOW,
        )
    assert caught.value.error_code == code


@pytest.mark.contract
def test_runner_rejects_non_pair_and_non_mapping() -> None:
    with pytest.raises(UpstreamContractError) as non_pair:
        TradingAgentsRunner(FakeGraph({})).run("NVDA", "2026-01-15")
    assert non_pair.value.error_code == "invalid_propagate_return"

    with pytest.raises(UpstreamContractError) as non_mapping:
        TradingAgentsRunner(FakeGraph(([], "decision"))).run("NVDA", "2026-01-15")
    assert non_mapping.value.error_code == "invalid_final_state"


@pytest.mark.contract
@pytest.mark.parametrize("ticker", ["../NVDA", "A/B", "A\\B", "..", "", "A" * 21])
def test_ticker_path_traversal_is_rejected(ticker: str) -> None:
    with pytest.raises(ConfigurationError):
        normalize_ticker(ticker)


@pytest.mark.contract
def test_artifact_store_rejects_noncanonical_run_id(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    with pytest.raises(ArtifactStoreError) as caught:
        store.run_path("../../etc/passwd")
    assert caught.value.error_code == "invalid_run_id"
