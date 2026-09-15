"""Observability-only diagnostics for the TradingAgents pre-semantic path.

Added for John Requirement B's root-cause instrumentation task
(docs/audit_artifacts/v0_2_tradingagents_timeout_root_cause.json): two
independently-authorized live QQQ runs failed at an identical ~903-second
mark before ``run_streaming_tradingagents_research``'s own stream loop ever
observed a single LangGraph chunk, and the resulting generic
``exc_type=ValueError`` log line carried no traceback. This module adds a
passive LangChain callback handler that logs chain/tool/LLM start-end-error
events with elapsed time and name only, so the *next* run (diagnostic or
otherwise) shows exactly which node/tool/LLM call was in flight and for how
long, and preserves the real traceback on failure.

Every method here only logs and returns ``None`` (the ``BaseCallbackHandler``
default) -- it never raises on its own, never inspects prompt/tool content
(only counts and names, so no request/response bodies or credentials are
ever logged), and never alters what LangChain/LangGraph does with the event.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

logger = logging.getLogger(__name__)


def _event_name(serialized: dict[str, Any] | None, kwargs: dict[str, Any]) -> str:
    if isinstance(serialized, dict):
        name = serialized.get("name") or serialized.get("id")
        if isinstance(name, list):
            name = name[-1] if name else None
        if name:
            return str(name)
    name = kwargs.get("name")
    return str(name) if name else "unknown"


class TradingAgentsDiagnosticCallback(BaseCallbackHandler):
    """Logs chain/tool/LLM start, end, and error events with elapsed time.

    ``run_label`` is a non-secret identifier (ticker/date) used only to
    correlate log lines from one research run.
    """

    def __init__(self, run_label: str) -> None:
        self._run_label = run_label
        self._start_monotonic = time.monotonic()

    def _elapsed(self) -> float:
        return round(time.monotonic() - self._start_monotonic, 3)

    def on_chain_start(self, serialized, inputs, **kwargs):  # noqa: D102
        logger.info(
            "tradingagents_diagnostic stage=CHAIN_START run=%s name=%s elapsed=%.3fs",
            self._run_label, _event_name(serialized, kwargs), self._elapsed(),
        )

    def on_chain_end(self, outputs, **kwargs):  # noqa: D102
        logger.info(
            "tradingagents_diagnostic stage=CHAIN_END run=%s elapsed=%.3fs",
            self._run_label, self._elapsed(),
        )

    def on_chain_error(self, error, **kwargs):  # noqa: D102
        logger.error(
            "tradingagents_diagnostic stage=CHAIN_ERROR run=%s elapsed=%.3fs exc_type=%s exc_message=%s",
            self._run_label, self._elapsed(), type(error).__name__, str(error),
            exc_info=error,
        )

    def on_tool_start(self, serialized, input_str, **kwargs):  # noqa: D102
        logger.info(
            "tradingagents_diagnostic stage=TOOL_START run=%s name=%s elapsed=%.3fs input_len=%d",
            self._run_label, _event_name(serialized, kwargs), self._elapsed(), len(input_str or ""),
        )

    def on_tool_end(self, output, **kwargs):  # noqa: D102
        logger.info(
            "tradingagents_diagnostic stage=TOOL_END run=%s elapsed=%.3fs",
            self._run_label, self._elapsed(),
        )

    def on_tool_error(self, error, **kwargs):  # noqa: D102
        logger.error(
            "tradingagents_diagnostic stage=TOOL_ERROR run=%s elapsed=%.3fs exc_type=%s exc_message=%s",
            self._run_label, self._elapsed(), type(error).__name__, str(error),
            exc_info=error,
        )

    def on_llm_start(self, serialized, prompts, **kwargs):  # noqa: D102
        logger.info(
            "tradingagents_diagnostic stage=LLM_START run=%s name=%s elapsed=%.3fs prompt_count=%d",
            self._run_label, _event_name(serialized, kwargs), self._elapsed(), len(prompts or []),
        )

    def on_chat_model_start(self, serialized, messages, **kwargs):  # noqa: D102
        logger.info(
            "tradingagents_diagnostic stage=LLM_START run=%s name=%s elapsed=%.3fs message_batches=%d",
            self._run_label, _event_name(serialized, kwargs), self._elapsed(), len(messages or []),
        )

    def on_llm_end(self, response, **kwargs):  # noqa: D102
        logger.info(
            "tradingagents_diagnostic stage=LLM_END run=%s elapsed=%.3fs",
            self._run_label, self._elapsed(),
        )

    def on_llm_error(self, error, **kwargs):  # noqa: D102
        logger.error(
            "tradingagents_diagnostic stage=LLM_ERROR run=%s elapsed=%.3fs exc_type=%s exc_message=%s",
            self._run_label, self._elapsed(), type(error).__name__, str(error),
            exc_info=error,
        )

    def on_retry(self, retry_state, **kwargs):  # noqa: D102
        logger.warning(
            "tradingagents_diagnostic stage=RETRY run=%s elapsed=%.3fs",
            self._run_label, self._elapsed(),
        )
