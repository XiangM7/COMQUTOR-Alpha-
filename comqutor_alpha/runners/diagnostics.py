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
import threading
import time
from datetime import datetime, timezone
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

from comqutor_alpha.llm.cost_basis import estimate_cost_usd

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


def _extract_llm_result_usage(response: Any) -> dict[str, int | None]:
    """Extract real token counts from a LangChain ``LLMResult``.

    Mirrors ``comqutor_alpha.structure_engine.week2_llm._response_token_usage``'s
    own "never estimate, mark unknown" rule, adapted to the ``LLMResult``
    shape (``llm_output`` usage dict, or a generation's ``message.usage_metadata``)
    rather than duplicating that function's single-message-response contract.
    Returns ``None`` for any field the Provider genuinely never reported --
    never a fabricated ``0``.
    """

    def _count(mapping: Any, *names: str) -> int | None:
        if not isinstance(mapping, dict):
            return None
        for name in names:
            value = mapping.get(name)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                return value
        return None

    llm_output = getattr(response, "llm_output", None) or {}
    usage = llm_output.get("token_usage") or llm_output.get("usage")
    input_tokens = _count(usage, "prompt_tokens", "input_tokens")
    output_tokens = _count(usage, "completion_tokens", "output_tokens")
    total_tokens = _count(usage, "total_tokens")

    if input_tokens is None and output_tokens is None and total_tokens is None:
        for batch in getattr(response, "generations", None) or []:
            for generation in batch:
                usage_metadata = getattr(getattr(generation, "message", None), "usage_metadata", None)
                if isinstance(usage_metadata, dict):
                    input_tokens = input_tokens if input_tokens is not None else _count(usage_metadata, "input_tokens")
                    output_tokens = output_tokens if output_tokens is not None else _count(usage_metadata, "output_tokens")
                    total_tokens = total_tokens if total_tokens is not None else _count(usage_metadata, "total_tokens")

    if total_tokens is None and isinstance(input_tokens, int) and isinstance(output_tokens, int):
        total_tokens = input_tokens + output_tokens

    return {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": total_tokens}


def _extract_provider_model(metadata: dict[str, Any] | None, serialized: dict[str, Any] | None) -> tuple[str, str]:
    """Identify provider/model from LangChain's own call metadata, never a guess.

    ``ls_provider``/``ls_model_name`` are populated automatically by
    ``langchain_core.language_models.chat_models.BaseChatModel`` for every
    chat-model invocation (confirmed against the installed langchain_core
    this round) -- this reads that existing mechanism rather than adding
    per-provider-client parsing. Falls back to ``serialized["kwargs"]``'s
    own ``model``/``model_name`` field, and only then to ``"unknown"``.
    """
    metadata = metadata or {}
    provider = metadata.get("ls_provider")
    model = metadata.get("ls_model_name")
    if not model and isinstance(serialized, dict):
        kwargs = serialized.get("kwargs") or {}
        model = kwargs.get("model") or kwargs.get("model_name")
    return str(provider or "unknown"), str(model or "unknown")


class TradingAgentsUsageStatsCallback(BaseCallbackHandler):
    """Real request-level usage/cost stats for the TradingAgents LLM boundary.

    Added alongside (never in place of) ``TradingAgentsDiagnosticCallback``
    above, on the same real production call path
    (``comqutor_alpha/runners/tradingagents_runner.py``). Where that class
    logs elapsed-time text lines for incident diagnosis, this class records
    structured, machine-readable fields for T4 request-level statistics:
    ``provider_call_id`` (LangChain's own per-invocation ``run_id`` -- the
    only request-correlation identifier this boundary exposes), provider/model
    (from LangChain's own call metadata, never guessed), wall-clock
    start/end, success/failure, a best-effort ``retry_count`` (incremented
    only when LangChain's own ``on_retry`` fires -- a Provider client's
    internal HTTP-level retries below that are not separately observable at
    this boundary, and this class never claims otherwise), the Provider's
    own returned token usage (never estimated), and cost (via
    ``comqutor_alpha.llm.cost_basis`` -- honestly "no pricing table
    entry" for every provider/model until a real price is confirmed and
    added there).

    Every method here only records and returns ``None`` -- it never raises
    on its own and never alters what LangChain/LangGraph does with the
    event, matching this module's own stated invariant.
    """

    def __init__(self, run_id: str, agent_label: str = "") -> None:
        self._run_id = run_id
        self._agent_label = agent_label
        self._pending: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self.records: list[dict[str, Any]] = []

    def _start(self, serialized, messages_or_prompts, *, run_id, metadata=None, **kwargs):
        provider, model = _extract_provider_model(metadata, serialized)
        with self._lock:
            self._pending[str(run_id)] = {
                "provider_call_id": str(run_id),
                "run_id": self._run_id,
                "agent_label": self._agent_label,
                "provider": provider,
                "model": model,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "_started_monotonic": time.monotonic(),
                "retry_count": 0,
            }

    def on_chat_model_start(self, serialized, messages, *, run_id, metadata=None, **kwargs):  # noqa: D102
        self._start(serialized, messages, run_id=run_id, metadata=metadata, **kwargs)

    def on_llm_start(self, serialized, prompts, *, run_id, metadata=None, **kwargs):  # noqa: D102
        self._start(serialized, prompts, run_id=run_id, metadata=metadata, **kwargs)

    def on_retry(self, retry_state, *, run_id, **kwargs):  # noqa: D102
        with self._lock:
            pending = self._pending.get(str(run_id))
            if pending is not None:
                pending["retry_count"] += 1

    def on_llm_end(self, response, *, run_id, **kwargs):  # noqa: D102
        with self._lock:
            pending = self._pending.pop(str(run_id), None)
        if pending is None:
            return
        token_usage = _extract_llm_result_usage(response)
        cost = estimate_cost_usd(
            pending["provider"], pending["model"], token_usage.get("input_tokens"), token_usage.get("output_tokens")
        )
        record = {k: v for k, v in pending.items() if not k.startswith("_")}
        record.update(
            completed_at=datetime.now(timezone.utc).isoformat(),
            latency_ms=round((time.monotonic() - pending["_started_monotonic"]) * 1000, 1),
            success=True,
            token_usage=token_usage,
            cost_usd=cost.usd,
            cost_basis=cost.basis,
            error_type=None,
            error_message=None,
        )
        with self._lock:
            self.records.append(record)

    def on_llm_error(self, error, *, run_id, **kwargs):  # noqa: D102
        with self._lock:
            pending = self._pending.pop(str(run_id), None)
        if pending is None:
            return
        record = {k: v for k, v in pending.items() if not k.startswith("_")}
        record.update(
            completed_at=datetime.now(timezone.utc).isoformat(),
            latency_ms=round((time.monotonic() - pending["_started_monotonic"]) * 1000, 1),
            success=False,
            token_usage={"input_tokens": None, "output_tokens": None, "total_tokens": None},
            cost_usd=None,
            cost_basis="call_failed_no_usage",
            error_type=type(error).__name__,
            error_message=str(error),
        )
        with self._lock:
            self.records.append(record)


TRADINGAGENTS_USAGE_STATS_SCHEMA_VERSION = "comqutor.tradingagents_usage_stats.v1"


def summarize_usage_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate ``TradingAgentsUsageStatsCallback.records`` into request-level counts.

    A sibling of ``comqutor_alpha.llm.usage_stats.compute_usage_stats``
    for this callback's own simpler per-record shape (``success`` bool
    rather than a ``provider_status`` enum, no cache field at this
    boundary) -- kept separate rather than forced into that function's
    ``SemanticCallRecord`` contract, which would silently miscount fields
    this shape does not have.
    """
    logical_call_count = len(records)
    actual_request_count = 0
    retry_count_total = 0
    calls_with_usage = 0
    calls_missing_usage = 0
    total_input_tokens = 0
    total_output_tokens = 0
    total_tokens_known = 0
    success_count = 0
    failure_count = 0
    cost_total: float | None = None
    cost_seen = False
    cost_basis_notes: dict[str, int] = {}
    per_provider_model: dict[str, dict[str, int]] = {}

    for record in records:
        retry_count = record.get("retry_count") or 0
        retry_count_total += retry_count
        actual_request_count += 1 + retry_count  # every record here reached the Provider at least once

        if record.get("success"):
            success_count += 1
        else:
            failure_count += 1

        token_usage = record.get("token_usage") or {}
        total_tokens = token_usage.get("total_tokens")
        input_tokens = token_usage.get("input_tokens")
        output_tokens = token_usage.get("output_tokens")
        has_usage = isinstance(total_tokens, int) or (isinstance(input_tokens, int) and isinstance(output_tokens, int))
        if has_usage:
            calls_with_usage += 1
            if isinstance(input_tokens, int):
                total_input_tokens += input_tokens
            if isinstance(output_tokens, int):
                total_output_tokens += output_tokens
            total_tokens_known += total_tokens if isinstance(total_tokens, int) else (input_tokens + output_tokens)
        else:
            calls_missing_usage += 1

        basis = record.get("cost_basis") or "unknown"
        cost_basis_notes[basis] = cost_basis_notes.get(basis, 0) + 1
        cost_usd = record.get("cost_usd")
        if isinstance(cost_usd, (int, float)):
            cost_total = (cost_total or 0.0) + cost_usd
            cost_seen = True

        key = f"{record.get('provider')}:{record.get('model')}"
        bucket = per_provider_model.setdefault(
            key, {"logical_call_count": 0, "calls_with_usage": 0, "calls_missing_usage": 0}
        )
        bucket["logical_call_count"] += 1
        bucket["calls_with_usage" if has_usage else "calls_missing_usage"] += 1

    return {
        "schema_version": TRADINGAGENTS_USAGE_STATS_SCHEMA_VERSION,
        "logical_call_count": logical_call_count,
        "actual_request_count": actual_request_count,
        "retry_count_total": retry_count_total,
        "success_count": success_count,
        "failure_count": failure_count,
        "calls_with_usage": calls_with_usage,
        "calls_missing_usage": calls_missing_usage,
        "missing_usage_ratio": round(calls_missing_usage / logical_call_count, 6) if logical_call_count else None,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_tokens_known": total_tokens_known,
        "total_cost_usd": round(cost_total, 6) if cost_seen else None,
        "cost_basis_notes": cost_basis_notes,
        "per_provider_model": per_provider_model,
    }
