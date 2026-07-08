"""Guarded wrapper for running the original TradingAgents research pipeline."""

from __future__ import annotations

from pathlib import Path


def _require_payload_value(payload, key):
    value = payload.get(key)
    if value in (None, "", []):
        raise RuntimeError(f"Missing required payload field for real TradingAgents run: {key}")
    return value


def run_original_tradingagents_research(payload, output_root="outputs/runs"):
    """Run original TradingAgents only when explicitly requested.

    Tests should inject a fake runner or use ``offline_raw_agent_outputs``.
    A real run may call LLM/data providers and therefore requires the caller to
    opt in with ``allow_real_tradingagents_run=True`` and provide config.
    """
    payload = payload or {}

    if payload.get("final_state") is not None:
        from comqutor_alpha.adapters.tradingagents_output_writer import (
            save_comqutor_run_outputs,
        )

        return save_comqutor_run_outputs(
            final_state=payload.get("final_state"),
            ticker=_require_payload_value(payload, "ticker"),
            config=payload.get("config") or {},
            selected_analysts=payload.get("selected_analysts") or [],
            analysis_date=payload.get("analysis_date"),
            output_root=output_root,
        )

    if payload.get("allow_real_tradingagents_run") is not True:
        raise RuntimeError(
            "Real TradingAgents execution is disabled by default. Use "
            "offline_raw_agent_outputs for local tests, inject a fake runner, or set "
            "allow_real_tradingagents_run=True with a configured environment."
        )

    ticker = _require_payload_value(payload, "ticker")
    analysis_date = _require_payload_value(payload, "analysis_date")
    selected_analysts = payload.get("selected_analysts") or ["market", "news", "fundamentals", "sentiment"]
    config = payload.get("config")
    if not isinstance(config, dict):
        raise RuntimeError(
            "Real TradingAgents execution requires payload['config'] with provider/model/API "
            "configuration. The API wrapper does not read or modify .env."
        )

    try:
        from comqutor_alpha.adapters.tradingagents_output_writer import (
            save_comqutor_run_outputs,
        )
        from tradingagents.graph.trading_graph import TradingAgentsGraph
    except Exception as exc:
        raise RuntimeError(f"Unable to import TradingAgents graph entrypoint: {exc}") from exc

    graph = TradingAgentsGraph(selected_analysts, config=config, debug=False)
    final_state, _processed_signal = graph.propagate(str(ticker), str(analysis_date))
    run_dir = save_comqutor_run_outputs(
        final_state=final_state,
        ticker=ticker,
        config=config,
        selected_analysts=selected_analysts,
        analysis_date=analysis_date,
        output_root=Path(output_root),
    )
    return run_dir
