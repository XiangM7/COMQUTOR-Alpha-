"""Call the existing TradingAgents graph without modifying upstream nodes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from comqutor_alpha.config import (
    normalize_analysis_date,
    normalize_asset_type,
    normalize_ticker,
)


class TradingGraph(Protocol):
    def propagate(
        self,
        company_name: str,
        trade_date: str,
        asset_type: str = "stock",
    ) -> tuple[Mapping[str, Any], Any]: ...


class UpstreamContractError(RuntimeError):
    """The real or fake upstream graph violated the verified seam."""

    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True, slots=True)
class UpstreamRun:
    final_state: Mapping[str, Any]
    processed_decision: Any


class TradingAgentsRunner:
    """Small injectable wrapper around ``TradingAgentsGraph.propagate``."""

    def __init__(self, graph: TradingGraph):
        self._graph = graph

    def run(
        self,
        ticker: str,
        analysis_date: str | date,
        asset_type: str = "stock",
    ) -> UpstreamRun:
        normalized_ticker = normalize_ticker(ticker)
        normalized_date = normalize_analysis_date(analysis_date)
        normalized_asset_type = normalize_asset_type(asset_type)
        result = self._graph.propagate(
            normalized_ticker,
            normalized_date.isoformat(),
            normalized_asset_type,
        )
        if not isinstance(result, tuple) or len(result) != 2:
            raise UpstreamContractError(
                "invalid_propagate_return",
                "TradingAgentsGraph.propagate() must return (final_state, processed_decision)",
            )
        final_state, processed_decision = result
        if not isinstance(final_state, Mapping):
            raise UpstreamContractError(
                "invalid_final_state",
                "TradingAgentsGraph final_state must be a mapping",
            )
        return UpstreamRun(final_state=final_state, processed_decision=processed_decision)


def build_real_runner(config: Mapping[str, Any] | None = None) -> TradingAgentsRunner:
    """Build the real graph lazily so importing COMQUTOR never requires a key."""
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph_config = DEFAULT_CONFIG.copy()
    if config:
        graph_config.update(config)
    return TradingAgentsRunner(TradingAgentsGraph(config=graph_config))
