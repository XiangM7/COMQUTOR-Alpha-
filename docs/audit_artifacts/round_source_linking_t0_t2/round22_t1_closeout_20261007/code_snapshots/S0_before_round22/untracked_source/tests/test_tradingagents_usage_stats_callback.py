"""T4 request-level statistics offline prep: verify
comqutor_alpha.runners.diagnostics.TradingAgentsUsageStatsCallback correctly
counts success/retry/failure/missing-usage scenarios by calling the REAL
callback's own methods directly with FIXED, LangChain-shaped objects
(LLMResult/AIMessage/a real UUID run_id) -- the exact same objects LangChain
itself would pass at this boundary -- rather than building a separate
test-only statistics system. No network call, no Provider, no LangGraph
execution is involved; only the callback class and the aggregation function
beside it are exercised.

Mirrors the existing standalone-callback-method convention already used by
test_tradingagents_diagnostic_instrumentation.py::
test_diagnostic_callback_standalone_chain_and_retry_events_log_cleanly for
the sibling TradingAgentsDiagnosticCallback.
"""

from __future__ import annotations

import uuid

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from comqutor_alpha.runners.diagnostics import (
    TradingAgentsUsageStatsCallback,
    summarize_usage_records,
)

_METADATA = {"ls_provider": "anthropic", "ls_model_name": "claude-sonnet-4-6"}


def _chat_start(callback, run_id):
    callback.on_chat_model_start(
        {"lc": 1, "kwargs": {}},
        [[]],
        run_id=run_id,
        metadata=_METADATA,
    )


def _result_with_usage_metadata(text="ok", input_tokens=100, output_tokens=40):
    total = input_tokens + output_tokens
    message = AIMessage(
        content=text,
        usage_metadata={"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": total},
    )
    return LLMResult(generations=[[ChatGeneration(message=message)]])


def _result_without_usage(text="ok"):
    return LLMResult(generations=[[ChatGeneration(message=AIMessage(content=text))]])


def test_successful_call_with_real_usage_is_recorded_with_correct_fields():
    callback = TradingAgentsUsageStatsCallback(run_id="run-1", agent_label="NVDA:2026-09-30")
    call_id = uuid.uuid4()

    _chat_start(callback, call_id)
    callback.on_llm_end(_result_with_usage_metadata(input_tokens=100, output_tokens=40), run_id=call_id)

    assert len(callback.records) == 1
    record = callback.records[0]
    assert record["provider_call_id"] == str(call_id)
    assert record["run_id"] == "run-1"
    assert record["provider"] == "anthropic"
    assert record["model"] == "claude-sonnet-4-6"
    assert record["success"] is True
    assert record["retry_count"] == 0
    assert record["token_usage"] == {"input_tokens": 100, "output_tokens": 40, "total_tokens": 140}
    assert record["started_at"] < record["completed_at"] or record["started_at"] <= record["completed_at"]
    assert record["latency_ms"] >= 0
    # no confirmed pricing table entry exists for any provider/model yet.
    assert record["cost_usd"] is None
    assert record["cost_basis"] == "no_pricing_table_entry_for_provider_model"
    # the pending entry is fully consumed -- no leak across calls.
    assert callback._pending == {}


def test_deepseek_call_reported_as_openai_by_langchain_still_resolves_a_real_cost():
    """Round 5 (2026-10-04), T4 cost-metering gap: LangChain's own
    ``ls_provider`` metadata genuinely reports "openai" for a DeepSeek call
    made through an OpenAI-compatible client class -- confirmed directly
    against the real NVDA Fresh Run 034a0a60-430e-41f8-8321-03a11389707a's
    own tradingagents_llm_usage_summary.json, which recorded every one of
    its 20 calls under "openai:deepseek-v4-flash" with total_cost_usd=null.
    comqutor_alpha.llm.cost_basis now disambiguates by the unambiguous
    MODEL name (deepseek-v4-flash is never billed by any other vendor in
    this table) rather than trusting the misleading client-class label --
    this must resolve a real cost, not stay silently null."""
    callback = TradingAgentsUsageStatsCallback(run_id="run-1")
    call_id = uuid.uuid4()

    callback.on_chat_model_start(
        {"lc": 1, "kwargs": {}},
        [[]],
        run_id=call_id,
        metadata={"ls_provider": "openai", "ls_model_name": "deepseek-v4-flash"},
    )
    callback.on_llm_end(_result_with_usage_metadata(input_tokens=1_000_000, output_tokens=1_000_000), run_id=call_id)

    record = callback.records[0]
    assert record["provider"] == "openai"  # the raw, originally-reported label is never rewritten
    assert record["model"] == "deepseek-v4-flash"
    assert record["cost_usd"] == 0.75  # (1M * $0.15 + 1M * $0.60) / 1M, the off-peak floor rate
    assert record["cost_basis"] == (
        "pricing_table:deepseek:deepseek-v4-flash:model_name_overrode_reported_provider_openai:"
        "off_peak_floor_estimate_see_usd_ceiling_for_peak_rate"
    )


def test_successful_call_with_no_usage_metadata_is_honestly_missing():
    callback = TradingAgentsUsageStatsCallback(run_id="run-1")
    call_id = uuid.uuid4()

    _chat_start(callback, call_id)
    callback.on_llm_end(_result_without_usage(), run_id=call_id)

    record = callback.records[0]
    assert record["success"] is True
    assert record["token_usage"] == {"input_tokens": None, "output_tokens": None, "total_tokens": None}
    assert record["cost_usd"] is None


def test_retry_then_success_increments_retry_count_on_the_same_call():
    callback = TradingAgentsUsageStatsCallback(run_id="run-1")
    call_id = uuid.uuid4()

    _chat_start(callback, call_id)
    callback.on_retry(retry_state=None, run_id=call_id)
    callback.on_retry(retry_state=None, run_id=call_id)
    callback.on_llm_end(_result_with_usage_metadata(), run_id=call_id)

    record = callback.records[0]
    assert record["retry_count"] == 2
    assert record["success"] is True


def test_failed_call_is_recorded_with_error_details_and_no_fabricated_usage():
    callback = TradingAgentsUsageStatsCallback(run_id="run-1")
    call_id = uuid.uuid4()

    _chat_start(callback, call_id)
    callback.on_llm_error(RuntimeError("provider unavailable"), run_id=call_id)

    record = callback.records[0]
    assert record["success"] is False
    assert record["error_type"] == "RuntimeError"
    assert record["error_message"] == "provider unavailable"
    assert record["token_usage"] == {"input_tokens": None, "output_tokens": None, "total_tokens": None}
    assert record["cost_usd"] is None
    assert record["cost_basis"] == "call_failed_no_usage"


def test_unknown_run_id_on_end_or_error_is_ignored_not_raised():
    callback = TradingAgentsUsageStatsCallback(run_id="run-1")
    # No matching on_*_start was ever recorded for this run_id.
    callback.on_llm_end(_result_with_usage_metadata(), run_id=uuid.uuid4())
    callback.on_llm_error(RuntimeError("x"), run_id=uuid.uuid4())
    assert callback.records == []


def test_summarize_usage_records_counts_requests_retries_and_missing_usage():
    callback = TradingAgentsUsageStatsCallback(run_id="run-1")

    # call A: success, usage known, no retry
    call_a = uuid.uuid4()
    _chat_start(callback, call_a)
    callback.on_llm_end(_result_with_usage_metadata(input_tokens=50, output_tokens=10), run_id=call_a)

    # call B: success, missing usage, 1 retry
    call_b = uuid.uuid4()
    _chat_start(callback, call_b)
    callback.on_retry(retry_state=None, run_id=call_b)
    callback.on_llm_end(_result_without_usage(), run_id=call_b)

    # call C: failure, 1 retry
    call_c = uuid.uuid4()
    _chat_start(callback, call_c)
    callback.on_retry(retry_state=None, run_id=call_c)
    callback.on_llm_error(RuntimeError("boom"), run_id=call_c)

    summary = summarize_usage_records(callback.records)

    assert summary["logical_call_count"] == 3
    # requests: A=1, B=2 (1 retry), C=2 (1 retry) => 5
    assert summary["actual_request_count"] == 5
    assert summary["retry_count_total"] == 2
    assert summary["success_count"] == 2
    assert summary["failure_count"] == 1
    assert summary["calls_with_usage"] == 1
    assert summary["calls_missing_usage"] == 2
    assert summary["missing_usage_ratio"] == round(2 / 3, 6)
    assert summary["total_input_tokens"] == 50
    assert summary["total_output_tokens"] == 10
    assert summary["total_cost_usd"] is None


def test_summarize_usage_records_handles_empty_input():
    summary = summarize_usage_records([])
    assert summary["logical_call_count"] == 0
    assert summary["missing_usage_ratio"] is None
    assert summary["total_cost_usd"] is None


# ---------------------------------------------------------------------------
# Real entry point, real callback-mounting path (2026-09-30, third follow-up
# round, task section 三): everything above calls the callback's own methods
# directly. This section instead drives the REAL
# run_streaming_tradingagents_research entry point
# (comqutor_alpha/runners/tradingagents_runner.py) with the exact same
# graph_factory test seam tests/test_tradingagents_diagnostic_instrumentation.py
# already uses, and only injects fixed responses at the external-model
# boundary (inside the fake compiled graph's own .stream(), by calling
# whatever callbacks that real entry point actually attached to
# config["callbacks"] -- never by constructing/calling a callback directly).
# This proves the callback that ends up on disk is the SAME one the real
# wiring in tradingagents_runner.py attaches, not a parallel test double.
# ---------------------------------------------------------------------------

import json  # noqa: E402
from pathlib import Path  # noqa: E402

from comqutor_alpha.runners.diagnostics import TradingAgentsDiagnosticCallback  # noqa: E402
from comqutor_alpha.runners.tradingagents_runner import (  # noqa: E402
    run_streaming_tradingagents_research,
)


class _RealEntryPointFakePropagator:
    def create_initial_state(self, ticker, trade_date, **kwargs):
        return {"company_of_interest": ticker, "trade_date": trade_date}

    def get_graph_args(self):
        return {"stream_mode": "values", "config": {"recursion_limit": 100}}


class _CallbackInvokingFakeCompiledGraph:
    """Simulates one successful LLM call and one retry-then-failed LLM call
    by invoking whatever real callbacks the entry point attached -- the
    fixed responses are injected here, at the external-model boundary, never
    inside the callback class itself."""

    def __init__(self, chunks):
        self._chunks = chunks
        self.stream_calls = []
        self.invoked_callback_types: list[type] = []

    def stream(self, init_state, **kwargs):
        self.stream_calls.append({"init_state": init_state, "kwargs": kwargs})
        callbacks = kwargs.get("config", {}).get("callbacks", [])
        self.invoked_callback_types = [type(cb) for cb in callbacks]

        success_call_id = uuid.uuid4()
        for cb in callbacks:
            cb.on_chat_model_start(
                {"lc": 1, "kwargs": {}},
                [[]],
                run_id=success_call_id,
                metadata={"ls_provider": "openai", "ls_model_name": "gpt-5.5"},
            )
        success_result = LLMResult(
            generations=[[
                ChatGeneration(
                    message=AIMessage(
                        content="ok",
                        usage_metadata={"input_tokens": 50, "output_tokens": 10, "total_tokens": 60},
                    )
                )
            ]]
        )
        for cb in callbacks:
            cb.on_llm_end(success_result, run_id=success_call_id)

        failed_call_id = uuid.uuid4()
        for cb in callbacks:
            cb.on_chat_model_start(
                {"lc": 1, "kwargs": {}},
                [[]],
                run_id=failed_call_id,
                metadata={"ls_provider": "openai", "ls_model_name": "gpt-5.4-mini"},
            )
        for cb in callbacks:
            cb.on_retry(retry_state=None, run_id=failed_call_id)
        for cb in callbacks:
            cb.on_llm_error(RuntimeError("simulated provider failure"), run_id=failed_call_id)

        yield from self._chunks


class _RealEntryPointFakeGraph:
    def __init__(self, chunks):
        self.propagator = _RealEntryPointFakePropagator()
        self.graph = _CallbackInvokingFakeCompiledGraph(chunks)

    def resolve_instrument_context(self, ticker, asset_type):
        return f"instrument-context:{ticker}:{asset_type}"


def _real_entry_point_payload(run_id="usage-stats-real-entry"):
    return {
        "allow_real_tradingagents_run": True,
        "ticker": "NVDA",
        "analysis_date": "2026-09-30",
        "asset_type": "stock",
        "selected_analysts": ["market", "sentiment", "news", "fundamentals"],
        "config": {"llm_provider": "openai", "deep_think_llm": "gpt-5.5", "quick_think_llm": "gpt-5.4-mini"},
        "run_id": run_id,
    }


def _full_chunks():
    base = {"company_of_interest": "NVDA", "messages": []}
    c1 = {**base, "market_report": "m"}
    c2 = {
        **c1,
        "sentiment_report": "s",
        "news_report": "n",
        "fundamentals_report": "f",
        "investment_debate_state": {"judge_decision": "settled"},
        "trader_investment_plan": "t",
        "risk_debate_state": {"judge_decision": "settled"},
        "final_trade_decision": "decision",
    }
    return [c1, c2]


def test_real_entry_point_attaches_and_exercises_the_real_usage_stats_callback(tmp_path):
    fake_graph = _RealEntryPointFakeGraph(_full_chunks())

    run_dir = run_streaming_tradingagents_research(
        _real_entry_point_payload(),
        output_root=str(tmp_path),
        graph_factory=lambda i, c: fake_graph,
    )

    # 1. The callback actually invoked at the real entry point is the real
    # production class, attached by tradingagents_runner.py's own wiring --
    # not a parallel object this test constructed itself.
    assert TradingAgentsDiagnosticCallback in fake_graph.graph.invoked_callback_types
    assert TradingAgentsUsageStatsCallback in fake_graph.graph.invoked_callback_types

    # 2. Real artifacts were flushed to the real, final run directory.
    calls_path = Path(run_dir) / "tradingagents_llm_calls.jsonl"
    summary_path = Path(run_dir) / "tradingagents_llm_usage_summary.json"
    assert calls_path.exists()
    assert summary_path.exists()

    records = [json.loads(line) for line in calls_path.read_text().splitlines() if line]
    # 3. Exactly 2 records -- one per simulated LLM call. Never double-counted
    # across log layers: the sibling TradingAgentsDiagnosticCallback writes
    # only to Python logging (verified separately in
    # test_tradingagents_diagnostic_instrumentation.py), never to this same
    # JSONL file, so this count reflects only TradingAgentsUsageStatsCallback's
    # own records.
    assert len(records) == 2

    success_record = next(r for r in records if r["success"] is True)
    failed_record = next(r for r in records if r["success"] is False)

    assert success_record["provider"] == "openai"
    assert success_record["model"] == "gpt-5.5"
    assert success_record["retry_count"] == 0
    assert success_record["token_usage"] == {"input_tokens": 50, "output_tokens": 10, "total_tokens": 60}

    assert failed_record["model"] == "gpt-5.4-mini"
    assert failed_record["retry_count"] == 1
    assert failed_record["error_type"] == "RuntimeError"
    # Missing usage stays explicitly unknown (None), never fabricated as 0 --
    # this is the honest behavior this test exists to confirm at the real
    # entry point, not just inside the callback's own unit tests above.
    assert failed_record["token_usage"] == {"input_tokens": None, "output_tokens": None, "total_tokens": None}

    summary = json.loads(summary_path.read_text())
    assert summary["logical_call_count"] == 2
    # 4. Logical calls vs actual requests vs retries correspond correctly:
    # success call = 1 request (0 retries); failed call = 2 requests (1
    # initial + 1 retry) -- total 3, never conflated with logical_call_count.
    assert summary["actual_request_count"] == 3
    assert summary["retry_count_total"] == 1
    assert summary["success_count"] == 1
    assert summary["failure_count"] == 1
    assert summary["missing_usage_ratio"] == 0.5

    # 5. Explicit statistical-boundary disclosure this test itself proves is
    # real, not just documented: this callback's retry_count reflects ONLY
    # LangChain's own on_retry signal (simulated once above). A Provider
    # SDK's internal HTTP-level retry below that boundary is invisible to
    # this mechanism and is never fabricated as 0 -- it is simply not
    # observable here, exactly as TradingAgentsUsageStatsCallback's own
    # docstring states.
