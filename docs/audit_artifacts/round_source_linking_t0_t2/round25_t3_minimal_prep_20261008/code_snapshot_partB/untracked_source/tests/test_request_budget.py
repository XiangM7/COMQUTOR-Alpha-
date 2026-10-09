"""Tests for comqutor_alpha.runners.request_budget: the REAL, enforced
request-count cap for the TradingAgents Research Agent LLM layer.

Every test drives the real wrapping mechanism against a real ChatOpenAI
subclass (network never touched -- _generate is overridden to return a
fixed response, the same "fixed Provider response through the real call
wrapper" convention already used elsewhere this round) through both the
direct .invoke() shape and the .bind_tools().invoke() shape every real
TradingAgents analyst actually uses. Zero network, zero paid calls.
"""

from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI

from comqutor_alpha.runners.request_budget import (
    RequestBudgetGuard,
    ResearchAgentBudgetExceeded,
    wrap_chat_model_with_budget_guard,
)


class _FixedResponseChatOpenAI(ChatOpenAI):
    fixed_responses: list = []  # class-level default; each instance gets its own via __init__ override
    _call_count: int = 0

    def __init__(self, *args, fixed_responses=None, **kwargs):
        super().__init__(*args, **kwargs)
        object.__setattr__(self, "_fixed_responses", list(fixed_responses or ["ok"]))
        object.__setattr__(self, "_call_count", 0)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        idx = min(self._call_count, len(self._fixed_responses) - 1)
        object.__setattr__(self, "_call_count", self._call_count + 1)
        item = self._fixed_responses[idx]
        if isinstance(item, Exception):
            raise item
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=item))])


def _model(fixed_responses):
    return _FixedResponseChatOpenAI(model="gpt-5.5", api_key="placeholder", fixed_responses=fixed_responses)


def test_guard_allows_calls_up_to_the_limit_then_blocks():
    guard = RequestBudgetGuard(max_actual_requests=2)
    model = wrap_chat_model_with_budget_guard(_model(["r1", "r2", "r3"]), guard, max_retries=0)

    assert model.invoke("hi").content == "r1"
    assert model.invoke("hi").content == "r2"
    with pytest.raises(ResearchAgentBudgetExceeded):
        model.invoke("hi")
    assert guard.actual_requests_made == 2
    assert guard.remaining() == 0


def test_guard_blocks_before_the_real_call_not_after():
    """The 3rd call must never reach _generate at all once the budget is spent."""
    guard = RequestBudgetGuard(max_actual_requests=1)
    model = wrap_chat_model_with_budget_guard(_model(["r1", "r2"]), guard, max_retries=0)

    model.invoke("hi")
    with pytest.raises(ResearchAgentBudgetExceeded):
        model.invoke("hi")
    # _generate was only ever actually reached once.
    assert model._call_count == 1


def test_guard_enforced_through_bind_tools_the_real_analyst_call_shape():
    guard = RequestBudgetGuard(max_actual_requests=1)
    model = wrap_chat_model_with_budget_guard(_model(["r1", "r2"]), guard, max_retries=0)

    bound = model.bind_tools([])
    assert bound.invoke("hi").content == "r1"
    with pytest.raises(ResearchAgentBudgetExceeded):
        bound.invoke("hi")


def test_guard_enforced_through_a_real_prompt_pipe_chain():
    from langchain_core.prompts import ChatPromptTemplate

    guard = RequestBudgetGuard(max_actual_requests=1)
    model = wrap_chat_model_with_budget_guard(_model(["r1", "r2"]), guard, max_retries=0)
    chain = ChatPromptTemplate.from_messages([("human", "{x}")]) | model.bind_tools([])

    assert chain.invoke({"x": "hi"}).content == "r1"
    with pytest.raises(ResearchAgentBudgetExceeded):
        chain.invoke({"x": "hi"})


def test_wrapper_retries_count_against_the_same_guard():
    """A transient failure is retried at the wrapper's own level -- each
    attempt (including retries) consumes the shared guard's budget, closing
    the 'SDK-internal retry is invisible' gap rather than just disclosing it."""
    guard = RequestBudgetGuard(max_actual_requests=5)
    model = wrap_chat_model_with_budget_guard(
        _model([RuntimeError("transient"), RuntimeError("transient"), "success"]),
        guard,
        max_retries=2,
    )
    result = model.invoke("hi")
    assert result.content == "success"
    # 2 failed attempts + 1 successful attempt = 3 real requests, all counted.
    assert guard.actual_requests_made == 3


def test_wrapper_exhausts_retries_and_raises_the_real_last_exception():
    guard = RequestBudgetGuard(max_actual_requests=5)
    model = wrap_chat_model_with_budget_guard(
        _model([RuntimeError("fail-1"), RuntimeError("fail-2")]), guard, max_retries=1
    )
    with pytest.raises(RuntimeError, match="fail-2"):
        model.invoke("hi")
    assert guard.actual_requests_made == 2


def test_retries_exceeding_the_overall_budget_stop_with_budget_exceeded_not_a_fake_success():
    """A retry that would exceed the OVERALL budget raises
    ResearchAgentBudgetExceeded, never silently downgraded to "retries
    exhausted, giving up gracefully" -- the two failure modes stay distinct."""
    guard = RequestBudgetGuard(max_actual_requests=1)
    model = wrap_chat_model_with_budget_guard(
        _model([RuntimeError("fail-1"), "would-have-succeeded"]), guard, max_retries=3
    )
    with pytest.raises(ResearchAgentBudgetExceeded):
        model.invoke("hi")
    assert guard.actual_requests_made == 1  # only the first (failed) attempt was ever reserved


def test_wrapping_preserves_existing_fields_never_a_copy():
    model = _model(["r1"])
    model.max_tokens = 123
    guard = RequestBudgetGuard(max_actual_requests=5)
    wrapped = wrap_chat_model_with_budget_guard(model, guard)
    assert wrapped is model  # in-place, not a new instance
    assert wrapped.max_tokens == 123


def test_callback_based_enforcement_would_not_actually_work():
    """Documents, as a real executable test (not just a comment), the exact
    empirical finding that motivated this module's design: an exception
    raised inside a LangChain callback is swallowed, and the real call
    proceeds anyway -- proving a callback-only 'budget enforcement' would be
    a fake guarantee, which is why wrap_chat_model_with_budget_guard exists
    instead of, e.g., a TradingAgentsUsageStatsCallback-style hook."""
    from langchain_core.callbacks import BaseCallbackHandler

    class _RaisingCallback(BaseCallbackHandler):
        def on_chat_model_start(self, *a, **k):
            raise ResearchAgentBudgetExceeded("this must NOT stop the call")

    model = _model(["it ran anyway"])
    result = model.invoke("hi", config={"callbacks": [_RaisingCallback()]})
    assert result.content == "it ran anyway"


# ---------------------------------------------------------------------------
# Real entry point: run_streaming_tradingagents_research actually wires the
# guard onto graph.deep_thinking_llm/quick_thinking_llm, actually raises
# uncaught (never swallowed), and actually attempts a partial save.
# ---------------------------------------------------------------------------


def _payload(max_actual_requests=None, max_retries=None, run_id="budget-run"):
    payload = {
        "allow_real_tradingagents_run": True,
        "ticker": "NVDA",
        "analysis_date": "2026-09-30",
        "asset_type": "stock",
        "selected_analysts": ["market", "sentiment", "news", "fundamentals"],
        "config": {"llm_provider": "openai", "deep_think_llm": "gpt-5.5", "quick_think_llm": "gpt-5.4-mini"},
        "run_id": run_id,
    }
    if max_actual_requests is not None:
        payload["research_agent_max_actual_requests"] = max_actual_requests
    if max_retries is not None:
        payload["research_agent_max_retries"] = max_retries
    return payload


class _LLMCallingFakePropagator:
    def create_initial_state(self, ticker, trade_date, **kwargs):
        return {"company_of_interest": ticker, "trade_date": trade_date}

    def get_graph_args(self):
        return {"stream_mode": "values", "config": {"recursion_limit": 100}}


class _LLMCallingFakeCompiledGraph:
    """Simulates real analyst nodes calling graph.deep_thinking_llm/
    quick_thinking_llm mid-stream -- the exact attributes
    run_streaming_tradingagents_research wraps in place."""

    def __init__(self, owner_graph, chunks_between_calls):
        self._owner = owner_graph
        self._chunks_between_calls = chunks_between_calls
        self.stream_calls = []

    def stream(self, init_state, **kwargs):
        self.stream_calls.append({"init_state": init_state, "kwargs": kwargs})
        base = {"company_of_interest": "NVDA", "messages": []}
        for i, extra in enumerate(self._chunks_between_calls):
            self._owner.deep_thinking_llm.invoke("simulated analyst prompt")
            yield {**base, **extra}


class _LLMCallingFakeGraph:
    def __init__(self, deep_llm, quick_llm, chunks_between_calls):
        self.propagator = _LLMCallingFakePropagator()
        self.deep_thinking_llm = deep_llm
        self.quick_thinking_llm = quick_llm
        self.graph = _LLMCallingFakeCompiledGraph(self, chunks_between_calls)

    def resolve_instrument_context(self, ticker, asset_type):
        return f"instrument-context:{ticker}:{asset_type}"


def test_real_entry_point_wraps_and_enforces_the_research_agent_budget(tmp_path):
    from comqutor_alpha.runners.tradingagents_runner import run_streaming_tradingagents_research

    deep_llm = _model(["r1", "r2", "r3"])
    quick_llm = _model(["r1", "r2", "r3"])
    # 3 chunks -> 3 real deep_thinking_llm.invoke() calls inside the fake
    # stream, but the budget only allows 2 -> the 3rd must raise, uncaught,
    # all the way out of run_streaming_tradingagents_research.
    chunks = [{"market_report": "m"}, {"sentiment_report": "s"}, {"news_report": "n"}]
    fake_graph = _LLMCallingFakeGraph(deep_llm, quick_llm, chunks)

    with pytest.raises(ResearchAgentBudgetExceeded):
        run_streaming_tradingagents_research(
            _payload(max_actual_requests=2),
            output_root=str(tmp_path),
            graph_factory=lambda i, c: fake_graph,
        )

    # Never swallowed by an upper layer into a "graceful" partial success --
    # the caller sees the real exception type.
    assert deep_llm._call_count == 2  # the 3rd call never reached _generate


def test_partial_state_is_saved_when_budget_is_exceeded_mid_run(tmp_path):
    from comqutor_alpha.runners.tradingagents_runner import run_streaming_tradingagents_research

    deep_llm = _model(["r1", "r2", "r3"])
    quick_llm = _model(["r1", "r2", "r3"])
    chunks = [{"market_report": "m"}, {"sentiment_report": "s"}, {"news_report": "n"}]
    fake_graph = _LLMCallingFakeGraph(deep_llm, quick_llm, chunks)

    with pytest.raises(ResearchAgentBudgetExceeded):
        run_streaming_tradingagents_research(
            _payload(max_actual_requests=1, run_id="partial-save-run"),
            output_root=str(tmp_path),
            graph_factory=lambda i, c: fake_graph,
        )

    # Real, already-produced chunks (market_report from before the stop)
    # were saved -- never discarded just because the run didn't finish.
    run_dir = tmp_path / "partial-save-run"
    assert run_dir.exists()
    assert (run_dir / "raw_agent_outputs.json").exists()
    metadata = json.loads((run_dir / "metadata.json").read_text())
    assert metadata["stopped_reason"] == "RESEARCH_AGENT_REQUEST_BUDGET_EXCEEDED"


def test_no_wrapping_at_all_when_budget_not_requested(tmp_path):
    """The default, unset case: zero behavior change for every existing
    caller that never sets research_agent_max_actual_requests."""
    from comqutor_alpha.runners.tradingagents_runner import run_streaming_tradingagents_research

    deep_llm = _model(["r1", "r2", "r3", "r4", "r5"])
    quick_llm = _model(["r1", "r2", "r3", "r4", "r5"])
    chunks = [{"market_report": "m"}, {"sentiment_report": "s"}, {"news_report": "n"}]
    fake_graph = _LLMCallingFakeGraph(deep_llm, quick_llm, chunks)

    run_dir = run_streaming_tradingagents_research(
        _payload(run_id="no-budget-run"),  # no max_actual_requests at all
        output_root=str(tmp_path),
        graph_factory=lambda i, c: fake_graph,
    )
    assert run_dir.exists()
    assert deep_llm._call_count == 3  # all 3 calls succeeded, unrestricted
    assert type(deep_llm).__name__ == "_FixedResponseChatOpenAI"  # never wrapped/class-swapped


# ---------------------------------------------------------------------------
# Transport-level verification (2026-09-30, sixth follow-up round): everything
# above uses a _generate()-override fixture, one layer above real transport.
# This section instead drives the REAL create_llm_client -> OpenAIClient ->
# ChatOpenAI -> real openai SDK -> real httpx client chain, with ONLY the
# httpx transport itself replaced by httpx.MockTransport (a real, first-class
# httpx testing extension point -- never a mock of .invoke()/._generate(),
# and never a check of environment-variable plumbing alone). This is the
# actual external request boundary: a real HTTP request object is built,
# serialized, and would leave the process if the transport were real.
# ---------------------------------------------------------------------------

import httpx  # noqa: E402

from tradingagents.llm_clients.factory import create_llm_client  # noqa: E402


@pytest.fixture(autouse=True)
def _openai_api_key_env(monkeypatch):
    # tradingagents.llm_clients.openai_client.OpenAIClient.get_llm() reads
    # the credential ONLY from OPENAI_API_KEY (never from an api_key kwarg
    # passed to create_llm_client) -- confirmed directly against the real
    # production code this round. Every test in this section needs it set.
    monkeypatch.setenv("OPENAI_API_KEY", "placeholder")


def _openai_responses_api_body(content="ok"):
    # tradingagents.llm_clients.openai_client.OPENAI_COMPATIBLE_PROVIDERS["openai"]
    # sets use_responses_api=True for the native OpenAI provider (confirmed
    # directly this round) -- the real production call hits /v1/responses,
    # NOT /v1/chat/completions, so the fixed body must match THAT shape or
    # it silently fails to parse (confirmed: a chat-completions-shaped body
    # raises TypeError deep inside langchain_openai's response parser).
    return {
        "id": "resp_fixed",
        "object": "response",
        "created_at": 0,
        "model": "gpt-5.5",
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "output": [
            {
                "type": "message",
                "id": "msg_fixed",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": content, "annotations": []}],
            }
        ],
        "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
    }


class _ScriptedTransportHandler:
    """Each call consumes the next scripted outcome; the last outcome
    repeats if more calls arrive than scripted. ``outcomes`` entries are
    either "success" or an int HTTP status code for a fixed error body."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        idx = min(len(self.requests) - 1, len(self.outcomes) - 1)
        outcome = self.outcomes[idx]
        if outcome == "success":
            return httpx.Response(200, json=_openai_responses_api_body())
        return httpx.Response(outcome, json={"error": {"message": "simulated transport failure", "type": "server_error"}})

    @property
    def call_count(self) -> int:
        return len(self.requests)


def _real_model_with_mock_transport(outcomes, *, client_max_retries=0):
    """Builds a REAL ChatOpenAI through the REAL create_llm_client factory --
    the exact same call TradingAgentsGraph._get_provider_kwargs/__init__
    makes -- with only the transport swapped for a scripted, fixed one.
    """
    handler = _ScriptedTransportHandler(outcomes)
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = create_llm_client(
        provider="openai",
        model="gpt-5.5",
        http_client=http_client,
        max_retries=client_max_retries,
    )
    return client.get_llm(), handler


def _real_tool_list():
    from langchain_core.tools import tool

    @tool
    def get_fixed_market_snapshot(ticker: str) -> str:
        """A real, minimal LangChain tool -- bind_tools only needs its
        schema; it is never actually invoked in these tests."""
        return f"snapshot for {ticker}"

    return [get_fixed_market_snapshot]


def _invoke_via_real_analyst_call_shape(model):
    """Reproduces the EXACT real call shape every TradingAgents analyst
    uses (tradingagents/agents/analysts/market_analyst.py etc.):
    ``chain = prompt | llm.bind_tools(tools); result = chain.invoke(state["messages"])``
    """
    from langchain_core.messages import HumanMessage
    from langchain_core.prompts import ChatPromptTemplate

    prompt = ChatPromptTemplate.from_messages([("placeholder", "{messages}")])
    chain = prompt | model.bind_tools(_real_tool_list())
    return chain.invoke({"messages": [HumanMessage(content="hi")]})


def test_transport_boundary_success_calls_reach_transport_exactly_once_each():
    model, handler = _real_model_with_mock_transport(["success", "success", "success"])
    guard = RequestBudgetGuard(max_actual_requests=3)
    wrap_chat_model_with_budget_guard(model, guard, max_retries=0)

    for _ in range(3):
        result = _invoke_via_real_analyst_call_shape(model)
        assert result.content == "ok"
    assert handler.call_count == 3
    assert guard.actual_requests_made == 3


def test_transport_boundary_blocked_request_never_reaches_transport():
    model, handler = _real_model_with_mock_transport(["success", "success", "success"])
    guard = RequestBudgetGuard(max_actual_requests=2)
    wrap_chat_model_with_budget_guard(model, guard, max_retries=0)

    _invoke_via_real_analyst_call_shape(model)
    _invoke_via_real_analyst_call_shape(model)
    with pytest.raises(ResearchAgentBudgetExceeded):
        _invoke_via_real_analyst_call_shape(model)

    # The critical assertion: the 3rd, blocked request never left the
    # wrapper -- the real httpx transport was never even asked to send it.
    assert handler.call_count == 2


def test_transport_boundary_retry_then_success_counts_both_real_transport_calls():
    """A 500 then a success -- the wrapper's own retry loop makes a SECOND
    real request; both are real transport calls, both counted."""
    model, handler = _real_model_with_mock_transport([500, "success"], client_max_retries=0)
    guard = RequestBudgetGuard(max_actual_requests=5)
    wrap_chat_model_with_budget_guard(model, guard, max_retries=1)

    result = _invoke_via_real_analyst_call_shape(model)
    assert result.content == "ok"
    assert handler.call_count == 2  # the failed attempt AND the retry both really hit transport
    assert guard.actual_requests_made == 2


def test_transport_boundary_budget_exhausted_mid_retry_never_sends_the_blocked_retry():
    """Budget=1, a scripted failure that WOULD normally retry (max_retries=3)
    -- the retry is blocked by the budget before it ever reaches transport,
    and the real failure (not a fabricated success) is what the caller sees
    reported as the stop, via ResearchAgentBudgetExceeded specifically."""
    model, handler = _real_model_with_mock_transport([500, "success"], client_max_retries=0)
    guard = RequestBudgetGuard(max_actual_requests=1)
    wrap_chat_model_with_budget_guard(model, guard, max_retries=3)

    with pytest.raises(ResearchAgentBudgetExceeded):
        _invoke_via_real_analyst_call_shape(model)

    # Only the FIRST (failed) attempt ever reached transport -- the retry
    # that would have succeeded never got the chance to.
    assert handler.call_count == 1
    assert guard.actual_requests_made == 1


def test_underlying_client_max_retries_must_be_zero_or_retries_are_invisible():
    """Negative control, run for real against the actual transport boundary:
    confirms WHY client_max_retries=0 is mandatory. With the SDK's own
    default max_retries left in place, a single wrapper-level .invoke()
    call silently makes multiple real transport requests underneath --
    invisible to any counter sitting above .invoke(), including this
    wrapper's own guard.reserve() (which only sees ONE logical attempt).
    This is exactly the "hidden retry" failure mode
    run_streaming_tradingagents_research now prevents by forcing
    config["max_retries"]=0 before constructing the real client whenever
    the budget guard is engaged (see that function's own comment)."""
    model, handler = _real_model_with_mock_transport([500], client_max_retries=2)  # NOT forced to 0
    guard = RequestBudgetGuard(max_actual_requests=10)
    wrap_chat_model_with_budget_guard(model, guard, max_retries=0)  # wrapper itself does no retries

    with pytest.raises(Exception):  # the real openai SDK's own exception, not ResearchAgentBudgetExceeded
        _invoke_via_real_analyst_call_shape(model)

    # 3 real transport calls (1 + 2 SDK-internal retries) for what the guard
    # only ever saw as a single reserve() -- the exact invisible-retry gap.
    assert handler.call_count == 3
    assert guard.actual_requests_made == 1


def test_run_streaming_tradingagents_research_forces_client_max_retries_to_zero_when_budget_engaged(tmp_path):
    """Proves the production fix: when research_agent_max_actual_requests is
    set, the REAL config passed to graph construction has max_retries
    forced to 0 -- regardless of what TRADINGAGENTS_MAX_RETRIES/config
    otherwise said -- so the real client is built with zero internal retry
    capacity from the start (mutating .max_retries after construction does
    NOT work -- confirmed separately against a real ChatOpenAI instance)."""
    from comqutor_alpha.runners.tradingagents_runner import run_streaming_tradingagents_research

    captured_configs = []

    class _CapturingFakeCompiledGraph:
        def __init__(self):
            self.stream_calls = []

        def stream(self, init_state, **kwargs):
            self.stream_calls.append(kwargs)
            yield {"company_of_interest": "NVDA", "market_report": "m"}

    class _CapturingFakeGraph:
        def __init__(self, config):
            captured_configs.append(config)
            self.propagator = _LLMCallingFakePropagator()
            # No real LLM calls happen in this test -- it only inspects what
            # config graph_factory itself was handed.
            self.deep_thinking_llm = _model(["r1"])
            self.quick_thinking_llm = _model(["r1"])
            self.graph = _CapturingFakeCompiledGraph()

        def resolve_instrument_context(self, ticker, asset_type):
            return "ctx"

    payload = _payload(max_actual_requests=5, max_retries=2, run_id="config-check-run")
    payload["config"]["max_retries"] = 99  # deliberately wrong, must be overridden to 0

    run_streaming_tradingagents_research(
        payload, output_root=str(tmp_path), graph_factory=lambda internal_analysts, cfg: _CapturingFakeGraph(cfg)
    )

    assert captured_configs[0]["max_retries"] == 0
    # the caller's own original payload["config"] dict is never mutated in
    # place -- a new dict is built for graph construction instead.
    assert payload["config"]["max_retries"] == 99
