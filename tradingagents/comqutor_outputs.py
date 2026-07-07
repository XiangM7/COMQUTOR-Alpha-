"""COMQUTOR structure-layer output writer for completed TradingAgents runs."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

OUTPUT_VERSION = "week1b.v1"

AGENT_OUTPUT_FIELDS = (
    ("technical_agent", "Market Analyst", "market_report", ("market_report",)),
    ("sentiment_agent", "Sentiment Analyst", "sentiment_report", ("sentiment_report",)),
    ("news_agent", "News Analyst", "news_report", ("news_report",)),
    (
        "fundamental_agent",
        "Fundamentals Analyst",
        "fundamentals_report",
        ("fundamentals_report",),
    ),
    (
        "bull_researcher",
        "Bull Researcher",
        "investment_debate_state.bull_history",
        ("investment_debate_state", "bull_history"),
    ),
    (
        "bear_researcher",
        "Bear Researcher",
        "investment_debate_state.bear_history",
        ("investment_debate_state", "bear_history"),
    ),
    ("research_manager", "Research Manager", "investment_plan", ("investment_plan",)),
    ("trader", "Trader", "trader_investment_plan", ("trader_investment_plan",)),
    (
        "aggressive_risk_analyst",
        "Aggressive Analyst",
        "risk_debate_state.aggressive_history",
        ("risk_debate_state", "aggressive_history"),
    ),
    (
        "conservative_risk_analyst",
        "Conservative Analyst",
        "risk_debate_state.conservative_history",
        ("risk_debate_state", "conservative_history"),
    ),
    (
        "neutral_risk_analyst",
        "Neutral Analyst",
        "risk_debate_state.neutral_history",
        ("risk_debate_state", "neutral_history"),
    ),
    ("portfolio_manager", "Portfolio Manager", "final_trade_decision", ("final_trade_decision",)),
)


def _utc_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _resolve_output_root(output_root: str | os.PathLike[str] | None) -> Path:
    if output_root is not None:
        return Path(output_root)

    env_output_root = os.environ.get("COMQUTOR_OUTPUT_DIR")
    if env_output_root:
        return Path(env_output_root)

    return Path.cwd() / "outputs" / "runs"


def _get_nested(mapping: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) == 0
    return False


def _to_string(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        return str(value)


def _normalize_selected_analysts(selected_analysts: Any) -> list[str]:
    if selected_analysts is None:
        return []
    if isinstance(selected_analysts, str):
        return [selected_analysts]
    return [getattr(item, "value", str(item)) for item in selected_analysts]


def _extract_agent_outputs(final_state: Mapping[str, Any]) -> list[dict[str, str]]:
    agent_outputs = []
    for agent, tradingagents_agent, source_field, path in AGENT_OUTPUT_FIELDS:
        value = _get_nested(final_state, path)
        if _is_empty(value):
            continue
        agent_outputs.append(
            {
                "agent": agent,
                "tradingagents_agent": tradingagents_agent,
                "source_field": source_field,
                "raw_output": _to_string(value),
            }
        )
    return agent_outputs


def _build_final_report(ticker: str, run_id: str, analysis_date: str | None, agent_outputs) -> str:
    lines = [
        "# COMQUTOR TradingAgents Final Report",
        "",
        f"Ticker: {ticker}",
        f"Run ID: {run_id}",
    ]
    if analysis_date:
        lines.append(f"Analysis Date: {analysis_date}")
    lines.append("")

    for item in agent_outputs:
        lines.extend([f"## {item['agent']}", "", item["raw_output"], ""])

    return "\n".join(lines).rstrip() + "\n"


def save_comqutor_run_outputs(
    final_state,
    ticker,
    config,
    selected_analysts,
    analysis_date=None,
    output_root=None,
):
    """Save COMQUTOR-standard raw outputs for a completed TradingAgents run."""
    run_id = str(uuid4())
    run_dir = _resolve_output_root(output_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    final_state = final_state or {}
    config = config or {}
    agent_outputs = _extract_agent_outputs(final_state)

    quick_model = config.get("quick_think_llm")
    deep_model = config.get("deep_think_llm")
    metadata = {
        "run_id": run_id,
        "ticker": str(ticker),
        "analysis_date": analysis_date,
        "created_at": _utc_timestamp(),
        "llm_provider": config.get("llm_provider"),
        "model": deep_model or quick_model,
        "quick_model": quick_model,
        "deep_model": deep_model,
        "selected_analysts": _normalize_selected_analysts(selected_analysts),
        "agents": [item["agent"] for item in agent_outputs],
        "source": "TradingAgents",
        "output_version": OUTPUT_VERSION,
    }

    raw_payload = {
        "run_id": run_id,
        "ticker": str(ticker),
        "agent_outputs": agent_outputs,
    }

    (run_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (run_dir / "raw_agent_outputs.json").write_text(
        json.dumps(raw_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (run_dir / "final_report.md").write_text(
        _build_final_report(str(ticker), run_id, analysis_date, agent_outputs),
        encoding="utf-8",
    )

    return run_dir
