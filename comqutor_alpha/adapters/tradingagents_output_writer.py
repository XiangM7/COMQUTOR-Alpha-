"""Hardened Week 1A writer for TradingAgents final_state outputs."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from comqutor_alpha.storage.file_store import (
    atomic_write_text,
    run_dir_for,
    save_json_record,
    validate_artifact_filename,
)


OUTPUT_VERSION = "week1a.raw_agent_outputs.v1"
MAX_RAW_OUTPUT_CHARS = 50000
TRUNCATION_MARKER = "\n\n[TRUNCATED: original output exceeded 50000 characters]"
SAFE_CONFIG_KEYS = {"llm_provider", "quick_think_llm", "deep_think_llm"}


@dataclass(frozen=True)
class AgentOutputField:
    agent: str
    tradingagents_agent: str
    source_field: str
    primary_path: tuple[str, ...]
    fallback_paths: tuple[tuple[str, ...], ...] = ()


AGENT_OUTPUT_FIELDS: tuple[AgentOutputField, ...] = (
    AgentOutputField("market_agent", "Market Analyst", "market_report", ("market_report",)),
    AgentOutputField(
        "sentiment_agent",
        "Sentiment Analyst",
        "sentiment_report",
        ("sentiment_report",),
    ),
    AgentOutputField("news_agent", "News Analyst", "news_report", ("news_report",)),
    AgentOutputField(
        "fundamental_agent",
        "Fundamentals Analyst",
        "fundamentals_report",
        ("fundamentals_report",),
    ),
    AgentOutputField(
        "bull_researcher",
        "Bull Researcher",
        "investment_debate_state.bull_history",
        ("investment_debate_state", "bull_history"),
    ),
    AgentOutputField(
        "bear_researcher",
        "Bear Researcher",
        "investment_debate_state.bear_history",
        ("investment_debate_state", "bear_history"),
    ),
    AgentOutputField(
        "research_manager",
        "Research Manager",
        "investment_plan",
        ("investment_plan",),
        (("investment_debate_state", "judge_decision"),),
    ),
    AgentOutputField(
        "trader",
        "Trader",
        "trader_investment_plan",
        ("trader_investment_plan",),
    ),
    AgentOutputField(
        "aggressive_risk_analyst",
        "Aggressive Analyst",
        "risk_debate_state.aggressive_history",
        ("risk_debate_state", "aggressive_history"),
    ),
    AgentOutputField(
        "conservative_risk_analyst",
        "Conservative Analyst",
        "risk_debate_state.conservative_history",
        ("risk_debate_state", "conservative_history"),
    ),
    AgentOutputField(
        "neutral_risk_analyst",
        "Neutral Analyst",
        "risk_debate_state.neutral_history",
        ("risk_debate_state", "neutral_history"),
    ),
    AgentOutputField(
        "portfolio_manager",
        "Portfolio Manager",
        "final_trade_decision",
        ("final_trade_decision",),
        (("risk_debate_state", "judge_decision"),),
    ),
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


def _path_label(path: tuple[str, ...]) -> str:
    return ".".join(path)


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
    except (TypeError, ValueError, RecursionError):
        return str(value)


def _truncate_raw_output(raw_output: str) -> tuple[str, int, int, bool]:
    original_length = len(raw_output)
    if original_length <= MAX_RAW_OUTPUT_CHARS:
        return raw_output, original_length, original_length, False

    keep_chars = max(MAX_RAW_OUTPUT_CHARS - len(TRUNCATION_MARKER), 0)
    truncated_output = raw_output[:keep_chars] + TRUNCATION_MARKER
    return truncated_output, len(truncated_output), original_length, True


def _normalize_selected_analysts(selected_analysts: Any) -> list[str]:
    if selected_analysts is None:
        return []
    if isinstance(selected_analysts, str):
        values = [selected_analysts]
    else:
        try:
            iterator = iter(selected_analysts)
        except TypeError:
            values = [selected_analysts]
        else:
            values = list(iterator)

    normalized = []
    for item in values:
        text = str(getattr(item, "value", item)).strip()[:100]
        if text:
            normalized.append(text)
    return normalized


def _safe_config_value(config: Any, key: str) -> str | None:
    if key not in SAFE_CONFIG_KEYS or not isinstance(config, Mapping):
        return None
    value = config.get(key)
    if value is None:
        return None
    return str(value)


def _select_source(final_state: Mapping[str, Any], field: AgentOutputField) -> tuple[Any, str | None]:
    candidates = (field.primary_path, *field.fallback_paths)
    for source_path in candidates:
        value = _get_nested(final_state, source_path)
        if not _is_empty(value):
            return value, _path_label(source_path)
    return None, None


def _extract_agent_outputs(
    final_state: Mapping[str, Any],
    run_id: str,
    ticker: str,
    created_at: str,
) -> list[dict[str, Any]]:
    agent_outputs = []
    for field in AGENT_OUTPUT_FIELDS:
        value, source_path = _select_source(final_state, field)
        if source_path is None:
            continue

        raw_output = _to_string(value)
        raw_output, content_length, original_content_length, truncated = _truncate_raw_output(raw_output)
        agent_outputs.append(
            {
                "agent_output_id": f"{run_id}:{field.agent}:{field.source_field}",
                "run_id": run_id,
                "ticker": ticker,
                "agent": field.agent,
                "tradingagents_agent": field.tradingagents_agent,
                "source_field": field.source_field,
                "source_path": source_path,
                "source_candidates": [
                    _path_label(path) for path in (field.primary_path, *field.fallback_paths)
                ],
                "raw_output": raw_output,
                "content_length": content_length,
                "original_content_length": original_content_length,
                "truncated": truncated,
                "created_at": created_at,
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


def _validate_final_state(final_state: Any, allow_empty_final_state: bool) -> Mapping[str, Any]:
    if final_state is None:
        raise ValueError("INVALID_FINAL_STATE: final_state is required")
    if not isinstance(final_state, Mapping):
        raise ValueError("INVALID_FINAL_STATE: final_state must be a mapping")
    if not final_state and not allow_empty_final_state:
        raise ValueError(
            "INVALID_FINAL_STATE: final_state is empty; pass allow_empty_final_state=True "
            "to write an empty capture"
        )
    return final_state


def save_comqutor_run_outputs(
    final_state,
    ticker,
    config=None,
    selected_analysts=None,
    analysis_date=None,
    output_root=None,
    allow_empty_final_state=False,
    write_final_report=False,
):
    """Save COMQUTOR-standard raw outputs for a completed TradingAgents run."""
    final_state = _validate_final_state(final_state, allow_empty_final_state)
    run_id = str(uuid4())
    output_root = _resolve_output_root(output_root)
    run_dir = run_dir_for(run_id, output_root)
    run_dir.mkdir(parents=True, exist_ok=False)

    ticker = str(ticker)
    created_at = _utc_timestamp()
    agent_outputs = _extract_agent_outputs(final_state, run_id, ticker, created_at)
    warnings = [] if agent_outputs else ["NO_AGENT_OUTPUTS_EXTRACTED"]

    artifacts = {
        "metadata": True,
        "raw_agent_outputs": True,
        "final_report": bool(write_final_report),
    }
    metadata = {
        "run_id": run_id,
        "ticker": ticker,
        "analysis_date": analysis_date,
        "created_at": created_at,
        "selected_analysts": _normalize_selected_analysts(selected_analysts),
        "agents": [item["agent"] for item in agent_outputs],
        "source": "TradingAgents",
        "output_version": OUTPUT_VERSION,
        "llm_provider": _safe_config_value(config, "llm_provider"),
        "quick_model": _safe_config_value(config, "quick_think_llm"),
        "deep_model": _safe_config_value(config, "deep_think_llm"),
        "artifacts": artifacts,
    }
    if warnings:
        metadata["warnings"] = warnings

    raw_payload = {
        "schema_version": OUTPUT_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "agent_outputs": agent_outputs,
    }

    save_json_record(run_id, "metadata.json", metadata, output_root=output_root)
    save_json_record(run_id, "raw_agent_outputs.json", raw_payload, output_root=output_root)

    if write_final_report:
        final_report_filename = validate_artifact_filename("final_report.md")
        atomic_write_text(
            run_dir / final_report_filename,
            _build_final_report(ticker, run_id, analysis_date, agent_outputs),
            encoding="utf-8",
        )

    return run_dir
