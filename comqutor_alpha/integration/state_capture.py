"""Capture only the four analyst reports from a TradingAgents final state."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from comqutor_alpha.config import normalize_analysis_date, normalize_ticker
from comqutor_alpha.structure_engine.structure_schema import (
    AgentType,
    RawAnalystReport,
    RawAnalystReportBundle,
)

REPORT_FIELDS: tuple[tuple[str, str], ...] = (
    ("market", "market_report"),
    ("sentiment", "sentiment_report"),
    ("news", "news_report"),
    ("fundamentals", "fundamentals_report"),
)


class StateCaptureError(RuntimeError):
    def __init__(self, error_code: str, field: str, message: str):
        super().__init__(message)
        self.error_code = error_code
        self.field = field


CapturedAnalystReport = RawAnalystReport


def capture_analyst_reports(
    final_state: Mapping[str, Any],
    *,
    run_id: UUID,
    ticker: str,
    analysis_date: str | date,
    captured_at: datetime | None = None,
) -> tuple[CapturedAnalystReport, ...]:
    normalized_ticker = normalize_ticker(ticker)
    normalized_date = normalize_analysis_date(analysis_date)
    timestamp = captured_at or datetime.now(UTC)
    if timestamp.tzinfo is None:
        raise StateCaptureError(
            "naive_capture_time", "captured_at", "captured_at must be timezone-aware"
        )

    reports: list[CapturedAnalystReport] = []
    for agent, field in REPORT_FIELDS:
        if field not in final_state:
            raise StateCaptureError("missing_report", field, f"missing upstream field: {field}")
        text = final_state[field]
        if not isinstance(text, str):
            raise StateCaptureError("invalid_report_type", field, f"{field} must be a string")
        text = text.strip()
        if not text:
            raise StateCaptureError("empty_report", field, f"{field} must not be empty")
        reports.append(
            CapturedAnalystReport(
                run_id=run_id,
                ticker=normalized_ticker,
                analysis_date=normalized_date,
                agent=AgentType(agent),
                report_text=text,
                captured_at=timestamp,
                source_field=field,
            )
        )
    return tuple(reports)


def capture_report_bundle(
    final_state: Mapping[str, Any],
    *,
    run_id: UUID,
    ticker: str,
    analysis_date: str | date,
    captured_at: datetime | None = None,
) -> tuple[RawAnalystReportBundle, tuple[StateCaptureError, ...]]:
    """Fail-soft bundle capture used by the application pipeline."""
    normalized_ticker = normalize_ticker(ticker)
    normalized_date = normalize_analysis_date(analysis_date)
    timestamp = captured_at or datetime.now(UTC)
    if timestamp.tzinfo is None:
        raise StateCaptureError(
            "naive_capture_time", "captured_at", "captured_at must be timezone-aware"
        )
    reports: dict[AgentType, RawAnalystReport] = {}
    missing: list[AgentType] = []
    errors: list[StateCaptureError] = []
    for agent_value, field in REPORT_FIELDS:
        agent = AgentType(agent_value)
        raw = final_state.get(field)
        if field not in final_state:
            error = StateCaptureError("missing_report", field, f"missing upstream field: {field}")
        elif not isinstance(raw, str):
            error = StateCaptureError("invalid_report_type", field, f"{field} must be a string")
        elif not raw.strip():
            error = StateCaptureError("empty_report", field, f"{field} must not be empty")
        else:
            reports[agent] = RawAnalystReport(
                run_id=run_id,
                ticker=normalized_ticker,
                analysis_date=normalized_date,
                agent=agent,
                report_text=raw.strip(),
                captured_at=timestamp,
                source_field=field,
            )
            continue
        missing.append(agent)
        errors.append(error)
    bundle = RawAnalystReportBundle(
        run_id=run_id,
        ticker=normalized_ticker,
        analysis_date=normalized_date,
        reports=reports,
        missing_agents=missing,
    )
    return bundle, tuple(errors)
