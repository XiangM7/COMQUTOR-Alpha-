"""John Requirement B root-cause instrumentation tests.

Covers the observability-only diagnostics added for
docs/audit_artifacts/v0_2_tradingagents_timeout_root_cause.json:
TradingAgentsDiagnosticCallback (comqutor_alpha/runners/diagnostics.py) and
its wiring into run_streaming_tradingagents_research's stream loop
(comqutor_alpha/runners/tradingagents_runner.py). No real Provider, LLM,
market-data, or network call ever happens here -- everything uses the same
fake-graph test seam as tests/test_tradingagents_progress_runner.py.
"""

from __future__ import annotations

import logging

import pytest

from comqutor_alpha.runners.diagnostics import TradingAgentsDiagnosticCallback
from comqutor_alpha.runners.tradingagents_runner import (
    run_streaming_tradingagents_research,
)

PROFILE = "comqutor_anthropic_medium_sonnet46_v1"


# ---------------------------------------------------------------------------
# Fake streaming graph (mirrors tests/test_tradingagents_progress_runner.py)
# ---------------------------------------------------------------------------


class _FakePropagator:
    def create_initial_state(self, ticker, trade_date, **kwargs):
        return {"company_of_interest": ticker, "trade_date": trade_date}

    def get_graph_args(self):
        return {"stream_mode": "values", "config": {"recursion_limit": 100}}


class _FakeCompiledGraph:
    def __init__(self, chunks=None, exc=None):
        self._chunks = chunks or []
        self._exc = exc
        self.stream_calls = []

    def stream(self, init_state, **kwargs):
        self.stream_calls.append({"init_state": init_state, "kwargs": kwargs})
        for chunk in self._chunks:
            yield chunk
        if self._exc is not None:
            raise self._exc


class _FakeGraph:
    def __init__(self, chunks=None, exc=None):
        self.propagator = _FakePropagator()
        self.graph = _FakeCompiledGraph(chunks, exc)

    def resolve_instrument_context(self, ticker, asset_type):
        return f"instrument-context:{ticker}:{asset_type}"


def _payload(run_id="diag-run"):
    return {
        "allow_real_tradingagents_run": True,
        "ticker": "QQQ",
        "analysis_date": "2026-09-14",
        "asset_type": "stock",
        "selected_analysts": ["market", "sentiment", "news", "fundamentals"],
        "config": {"llm_provider": "anthropic", "deep_think_llm": "x", "quick_think_llm": "x"},
        "profile_id": PROFILE,
        "run_id": run_id,
    }


def _full_chunks():
    base = {"company_of_interest": "QQQ", "messages": []}
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


# ---------------------------------------------------------------------------
# 1. Stage start/end recorded
# ---------------------------------------------------------------------------


def test_stream_loop_start_and_chunk_events_are_logged(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="comqutor_alpha.runners.tradingagents_runner")
    run_streaming_tradingagents_research(
        _payload(),
        output_root=str(tmp_path),
        graph_factory=lambda i, c: _FakeGraph(_full_chunks()),
    )
    messages = [r.message for r in caplog.records]
    assert any("stage=STREAM_LOOP_START" in m for m in messages)
    chunk_msgs = [m for m in messages if "stage=STREAM_CHUNK" in m]
    assert len(chunk_msgs) == 2
    assert "chunk_index=1" in chunk_msgs[0]
    assert "chunk_index=2" in chunk_msgs[1]
    assert "elapsed=" in chunk_msgs[0]


# ---------------------------------------------------------------------------
# 2 & 3 & 4. Exception stage, traceback, and chained cause recorded
# ---------------------------------------------------------------------------


def test_stream_failure_is_logged_with_traceback_and_chained_cause(tmp_path, caplog):
    caplog.set_level(logging.ERROR, logger="comqutor_alpha.runners.tradingagents_runner")
    original = ValueError("No OHLCV data available for QQQ.")
    wrapped = RuntimeError("wrapped failure")
    wrapped.__cause__ = original

    with pytest.raises(RuntimeError, match="wrapped failure"):
        run_streaming_tradingagents_research(
            _payload(),
            output_root=str(tmp_path),
            graph_factory=lambda i, c: _FakeGraph(chunks=[{"company_of_interest": "QQQ"}], exc=wrapped),
        )

    error_records = [r for r in caplog.records if "STREAM_LOOP_ERROR" in r.message]
    assert len(error_records) == 1
    record = error_records[0]
    assert "exc_type=RuntimeError" in record.message
    assert "chunks_received=1" in record.message
    assert "ValueError" in record.message  # chained_cause repr
    assert record.exc_info is not None  # traceback captured
    formatted = record.getMessage()
    assert "wrapped failure" in formatted


def test_stream_failure_with_no_chunks_reports_zero_chunks_received(tmp_path, caplog):
    caplog.set_level(logging.ERROR, logger="comqutor_alpha.runners.tradingagents_runner")
    with pytest.raises(ValueError, match="boom"):
        run_streaming_tradingagents_research(
            _payload(),
            output_root=str(tmp_path),
            graph_factory=lambda i, c: _FakeGraph(chunks=[], exc=ValueError("boom")),
        )
    error_records = [r for r in caplog.records if "STREAM_LOOP_ERROR" in r.message]
    assert len(error_records) == 1
    assert "chunks_received=0" in error_records[0].message


# ---------------------------------------------------------------------------
# 5. Timeout metadata -- not applicable at this layer (no timeout is imposed
#    by this instrumentation itself); elapsed time is recorded instead, which
#    is the metadata this layer can actually observe.
# ---------------------------------------------------------------------------


def test_elapsed_time_is_recorded_on_both_chunks_and_errors(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="comqutor_alpha.runners.tradingagents_runner")
    run_streaming_tradingagents_research(
        _payload(),
        output_root=str(tmp_path),
        graph_factory=lambda i, c: _FakeGraph(_full_chunks()),
    )
    chunk_msgs = [r.message for r in caplog.records if "STREAM_CHUNK" in r.message]
    for msg in chunk_msgs:
        assert "elapsed=" in msg


# ---------------------------------------------------------------------------
# 6. No credential leakage
# ---------------------------------------------------------------------------


def test_diagnostic_callback_never_logs_prompt_or_tool_content(caplog):
    caplog.set_level(logging.INFO, logger="comqutor_alpha.runners.diagnostics")
    callback = TradingAgentsDiagnosticCallback(run_label="QQQ:2026-09-14")
    secret_input = "API_KEY=sk-super-secret-value-should-never-appear"
    callback.on_tool_start({"name": "get_stockstats_indicators_report"}, secret_input)
    callback.on_llm_start({"name": "chat-model"}, [secret_input, secret_input])
    callback.on_tool_end("some tool output containing sk-super-secret-value-should-never-appear")
    callback.on_llm_end(None)

    all_text = "\n".join(r.message for r in caplog.records)
    assert "sk-super-secret-value-should-never-appear" not in all_text
    assert "API_KEY" not in all_text
    # Only counts/names/timings are logged.
    assert "input_len=" in all_text
    assert "prompt_count=2" in all_text


def test_diagnostic_callback_error_logging_never_leaks_env_values(caplog, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-should-not-leak")
    caplog.set_level(logging.ERROR, logger="comqutor_alpha.runners.diagnostics")
    callback = TradingAgentsDiagnosticCallback(run_label="QQQ:2026-09-14")
    callback.on_tool_error(ValueError("plain failure, no secret embedded"))
    all_text = "\n".join(r.message for r in caplog.records)
    assert "sk-should-not-leak" not in all_text


# ---------------------------------------------------------------------------
# 7 & 8. Successful / failure execution semantics unchanged
# ---------------------------------------------------------------------------


def test_successful_run_output_unchanged_by_instrumentation(tmp_path):
    import json

    run_dir = run_streaming_tradingagents_research(
        _payload(run_id="semantics-run"),
        output_root=str(tmp_path),
        graph_factory=lambda i, c: _FakeGraph(_full_chunks()),
    )
    raw = json.loads((run_dir / "raw_agent_outputs.json").read_text())
    agents = {record["agent"] for record in raw["agent_outputs"]}
    assert {"market_agent", "sentiment_agent", "news_agent", "fundamental_agent"}.issubset(agents)


def test_failure_exception_type_and_message_unchanged_by_instrumentation(tmp_path):
    original = ValueError("No OHLCV rows on or before 2026-09-14 for QQQ.")
    with pytest.raises(ValueError, match="No OHLCV rows on or before"):
        run_streaming_tradingagents_research(
            _payload(),
            output_root=str(tmp_path),
            graph_factory=lambda i, c: _FakeGraph(chunks=[], exc=original),
        )


# ---------------------------------------------------------------------------
# 9. Instrumentation itself does not swallow exceptions
# ---------------------------------------------------------------------------


def test_instrumentation_reraises_the_exact_same_exception_instance(tmp_path):
    original = ValueError("distinguishable-marker-exception")
    caught = {}

    def factory(i, c):
        return _FakeGraph(chunks=[], exc=original)

    try:
        run_streaming_tradingagents_research(
            _payload(), output_root=str(tmp_path), graph_factory=factory
        )
    except ValueError as exc:
        caught["exc"] = exc

    assert caught["exc"] is original


# ---------------------------------------------------------------------------
# 10. Instrumentation does not alter return values
# ---------------------------------------------------------------------------


def test_run_dir_return_value_unaffected_by_instrumentation(tmp_path):
    run_dir = run_streaming_tradingagents_research(
        _payload(run_id="return-value-run"),
        output_root=str(tmp_path),
        graph_factory=lambda i, c: _FakeGraph(_full_chunks()),
    )
    assert run_dir.name == "return-value-run"
    assert run_dir.exists()


# ---------------------------------------------------------------------------
# Callback wiring itself never breaks the existing no-callbacks test seam.
# ---------------------------------------------------------------------------


def test_diagnostic_callback_is_attached_to_stream_config(tmp_path):
    graph = _FakeGraph(_full_chunks())
    run_streaming_tradingagents_research(
        _payload(),
        output_root=str(tmp_path),
        graph_factory=lambda i, c: graph,
    )
    stream_kwargs = graph.graph.stream_calls[0]["kwargs"]
    callbacks = stream_kwargs["config"]["callbacks"]
    assert len(callbacks) == 1
    assert isinstance(callbacks[0], TradingAgentsDiagnosticCallback)


def test_diagnostic_callback_standalone_chain_and_retry_events_log_cleanly(caplog):
    caplog.set_level(logging.INFO, logger="comqutor_alpha.runners.diagnostics")
    callback = TradingAgentsDiagnosticCallback(run_label="QQQ:2026-09-14")
    callback.on_chain_start({"name": "market_analyst"}, {})
    callback.on_chain_end({})
    callback.on_retry(None)
    messages = [r.message for r in caplog.records]
    assert any("stage=CHAIN_START" in m and "name=market_analyst" in m for m in messages)
    assert any("stage=CHAIN_END" in m for m in messages)
    assert any("stage=RETRY" in m for m in messages)
