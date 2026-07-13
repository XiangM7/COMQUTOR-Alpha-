from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
import yaml

from comqutor_alpha.alpha_library import load_taxonomy
from comqutor_alpha.application.research_pipeline import ResearchPipeline
from comqutor_alpha.config import ComqutorConfig
from comqutor_alpha.integration.tradingagents_runner import TradingAgentsRunner
from comqutor_alpha.storage.artifact_store import ArtifactStore
from comqutor_alpha.structure_engine.activation_scorer import ActivationScorer
from comqutor_alpha.structure_engine.alpha_mapper import AlphaMapper
from comqutor_alpha.structure_engine.conflict_detector import ConflictDetector
from comqutor_alpha.structure_engine.graph_builder import GraphBuilder
from comqutor_alpha.structure_engine.structure_extractor import StructureExtractor
from comqutor_alpha.structure_engine.structure_schema import AgentType, RunStatus
from comqutor_alpha.structure_engine.structured_output_adapter import StructuredOutputAdapter

CASES = Path(__file__).parents[1] / "golden_cases/research_cases_v1.yaml"
RUN_IDS = {
    "NVDA": UUID("11111111-1111-4111-8111-111111111111"),
    "QQQ": UUID("22222222-2222-4222-8222-222222222222"),
    "MSFT": UUID("33333333-3333-4333-8333-333333333333"),
}
NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


class FakeGraph:
    def __init__(self, reports):
        self.reports = reports

    def propagate(self, ticker, trade_date, asset_type="stock"):
        del trade_date, asset_type
        state = {
            "market_report": self.reports["market"],
            "sentiment_report": self.reports["sentiment"],
            "news_report": self.reports["news"],
            "fundamentals_report": self.reports["fundamentals"],
            "final_trade_decision": f"comparison-only for {ticker}",
        }
        return state, "comparison-only processed decision"


class FixtureClaimExtractor:
    method = "golden_fixture_extractor"

    def extract(self, report):
        sentences = [sentence.strip() + "." for sentence in report.report_text.split(".") if sentence.strip()]
        claims = []
        for sentence in sentences:
            lowered = sentence.casefold()
            negative = any(
                term in lowered
                for term in ("downside risk", "recession risk", "credit spreads are widening")
            )
            claims.append(
                {
                    "claim": f"Structural observation: {sentence}",
                    "evidence": sentence,
                    "entities": [report.ticker],
                    "factors": [],
                    "direction": "negative" if negative else "positive",
                    "confidence": 0.9 if report.agent in {AgentType.NEWS, AgentType.MARKET} else 0.8,
                    "source_type": "analyst",
                    "source_refs": [f"fixture:{report.agent.value}"],
                }
            )
        return {"claims": claims}


class FixtureRelationExtractor:
    def extract(self, claim):
        suffix = str(claim.claim_id)
        return {
            "nodes": [
                {"label": f"evidence {suffix}", "node_type": "factor"},
                {"label": f"outcome {suffix}", "node_type": "factor"},
            ],
            "edges": [
                {
                    "source": f"evidence {suffix}",
                    "target": f"outcome {suffix}",
                    "edge_type": "causal",
                    "weight": claim.confidence,
                }
            ],
        }


def _pipeline(tmp_path, case):
    taxonomy = load_taxonomy()
    config = ComqutorConfig(output_dir=tmp_path / "runs")
    return ResearchPipeline(
        runner=TradingAgentsRunner(FakeGraph(case["reports"])),
        adapter=StructuredOutputAdapter(FixtureClaimExtractor()),
        mapper=AlphaMapper(taxonomy),
        extractor=StructureExtractor(FixtureRelationExtractor()),
        graph_builder=GraphBuilder(),
        activation_scorer=ActivationScorer(),
        conflict_detector=ConflictDetector(),
        taxonomy=taxonomy,
        artifact_store=ArtifactStore(config.output_dir),
        config=config,
        clock=lambda: NOW,
    )


def _cases():
    return yaml.safe_load(CASES.read_text(encoding="utf-8"))["cases"]


@pytest.mark.golden
@pytest.mark.parametrize("ticker", ["NVDA", "QQQ"])
def test_reviewed_nvda_and_qqq_golden_conflicts_end_to_end(tmp_path: Path, ticker: str) -> None:
    case = next(item for item in _cases() if item["ticker"] == ticker)
    result = _pipeline(tmp_path, case).run(
        ticker=ticker,
        analysis_date="2026-01-15",
        run_id=RUN_IDS[ticker],
    )
    assert result.status == RunStatus.COMPLETE
    assert result.main_conflict is not None
    expected_bulls = set(case.get("expected_bull_any", [case.get("expected_bull")]))
    assert result.main_conflict.bull_structure.split()[0] in expected_bulls
    assert result.main_conflict.bear_structure.split()[0] == case["expected_bear"]
    assert result.main_conflict.bull_evidence
    assert result.main_conflict.bear_evidence
    assert result.evidence_coverage == 1.0
    assert not re.search(r"\b(?:BUY|SELL|HOLD)\b", result.summary, flags=re.IGNORECASE)

    run_dir = tmp_path / "runs" / str(RUN_IDS[ticker])
    expected_artifacts = {
        "metadata.json",
        "raw_agent_outputs.json",
        "upstream_decision.json",
        "structured_agent_outputs.json",
        "alpha_matches.json",
        "structure_edges.json",
        "structure_graph.json",
        "alpha_activations.json",
        "alpha_conflicts.json",
        "research_result.json",
    }
    assert {path.name for path in run_dir.iterdir()} == expected_artifacts
    saved = json.loads((run_dir / "research_result.json").read_text())
    assert saved["run_id"] == str(RUN_IDS[ticker])


@pytest.mark.golden
def test_msft_golden_exposes_taxonomy_blocker_without_fabricating_conflict(tmp_path: Path) -> None:
    case = next(item for item in _cases() if item["ticker"] == "MSFT")
    result = _pipeline(tmp_path, case).run(
        ticker="MSFT",
        analysis_date="2026-01-15",
        run_id=RUN_IDS["MSFT"],
    )
    assert any(item.alpha_id == "A102" for item in result.dominant_alphas)
    assert any(item.alpha_id == "A304" for item in result.dominant_alphas)
    assert all({item.alpha_a, item.alpha_b} != {"A102", "A304"} for item in result.conflicts)
    assert result.main_conflict is not None
    assert not (
        result.main_conflict.bull_structure.startswith("A102")
        and result.main_conflict.bear_structure.startswith("A304")
    )
    assert case["blocked_reason"].startswith("Taxonomy does not declare A102/A304")


@pytest.mark.integration
def test_partial_agent_failure_is_degraded_and_preserves_successful_artifacts(tmp_path: Path) -> None:
    case = next(item for item in _cases() if item["ticker"] == "NVDA")
    case = {**case, "reports": {**case["reports"], "news": ""}}
    result = _pipeline(tmp_path, case).run(
        ticker="NVDA",
        analysis_date="2026-01-15",
        run_id=UUID("44444444-4444-4444-8444-444444444444"),
    )
    assert result.status == RunStatus.DEGRADED
    assert any(reason.startswith("capture:empty_report") for reason in result.degraded_reasons)
    assert result.evidence_coverage == 1.0


@pytest.mark.integration
def test_upstream_failure_returns_failed_result_and_artifacts(tmp_path: Path) -> None:
    class BrokenGraph:
        def propagate(self, *args, **kwargs):
            raise TimeoutError("upstream unavailable")

    taxonomy = load_taxonomy()
    config = ComqutorConfig(output_dir=tmp_path / "runs")
    pipeline = ResearchPipeline(
        runner=TradingAgentsRunner(BrokenGraph()),
        adapter=StructuredOutputAdapter(FixtureClaimExtractor()),
        mapper=AlphaMapper(taxonomy),
        extractor=StructureExtractor(FixtureRelationExtractor()),
        graph_builder=GraphBuilder(),
        activation_scorer=ActivationScorer(),
        conflict_detector=ConflictDetector(),
        taxonomy=taxonomy,
        artifact_store=ArtifactStore(config.output_dir),
        config=config,
        clock=lambda: NOW,
    )
    run_id = UUID("55555555-5555-4555-8555-555555555555")
    result = pipeline.run(ticker="NVDA", analysis_date="2026-01-15", run_id=run_id)
    assert result.status == RunStatus.FAILED
    assert result.errors[0].stage == "upstream"
    assert (tmp_path / "runs" / str(run_id) / "research_result.json").exists()
