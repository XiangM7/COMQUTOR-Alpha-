"""W7: streaming TradingAgents runner tests.

Everything here uses a fake graph (the ``graph_factory`` test seam) -- no
real Provider, LLM, market-data, or network call ever happens. Covers: the
public sentiment -> internal social mapping, chunk-driven analyst/debate/
trader/risk progress, duplicate-chunk deduplication, final-state merging,
the official-writer persistence path, and relocation of the writer's run
directory onto the lifecycle's claimed run_id.
"""

from __future__ import annotations

import json

import pytest

from comqutor_alpha.research_progress import ResearchProgressReporter
from comqutor_alpha.runners.tradingagents_runner import (
    PUBLIC_TO_INTERNAL_ANALYSTS,
    map_public_analysts_to_internal,
    run_streaming_tradingagents_research,
)

PROFILE = "comqutor_anthropic_medium_sonnet46_v1"


# ---------------------------------------------------------------------------
# Public -> internal analyst mapping
# ---------------------------------------------------------------------------


def test_sentiment_maps_to_social_only_at_the_graph_boundary():
    public, internal = map_public_analysts_to_internal(["market", "sentiment", "news", "fundamentals"])
    assert public == ["market", "sentiment", "news", "fundamentals"]
    assert internal == ["market", "social", "news", "fundamentals"]


def test_mapping_keeps_canonical_order_and_dedupes():
    public, internal = map_public_analysts_to_internal(["news", "sentiment", "news", "market"])
    assert public == ["market", "sentiment", "news"]
    assert internal == ["market", "social", "news"]


def test_mapping_rejects_unknown_names_including_internal_social():
    with pytest.raises(RuntimeError, match="INVALID_ANALYST_SELECTION"):
        map_public_analysts_to_internal(["market", "social"])
    with pytest.raises(RuntimeError, match="INVALID_ANALYST_SELECTION"):
        map_public_analysts_to_internal(["quant_wizard"])


def test_mapping_requires_at_least_one_analyst():
    with pytest.raises(RuntimeError, match="INVALID_ANALYST_SELECTION"):
        map_public_analysts_to_internal([])


def test_public_vocabulary_never_contains_social():
    assert "social" not in PUBLIC_TO_INTERNAL_ANALYSTS


# ---------------------------------------------------------------------------
# Fake streaming graph
# ---------------------------------------------------------------------------


class _FakePropagator:
    def __init__(self):
        self.created_with = None

    def create_initial_state(self, ticker, trade_date, **kwargs):
        self.created_with = {"ticker": ticker, "trade_date": trade_date, **kwargs}
        return {"company_of_interest": ticker, "trade_date": trade_date}

    def get_graph_args(self):
        return {"stream_mode": "values", "config": {"recursion_limit": 100}}


class _FakeCompiledGraph:
    def __init__(self, chunks):
        self._chunks = chunks
        self.stream_calls = []

    def stream(self, init_state, **kwargs):
        self.stream_calls.append({"init_state": init_state, "kwargs": kwargs})
        yield from self._chunks


class _FakeGraph:
    def __init__(self, chunks):
        self.propagator = _FakePropagator()
        self.graph = _FakeCompiledGraph(chunks)

    def resolve_instrument_context(self, ticker):
        return f"instrument-context:{ticker}"


class _RecordingProgressRepo:
    def __init__(self):
        self.updates = []

    def initialize_research_progress(self, run_id, **kwargs):
        return True

    def update_research_progress(self, run_id, **kwargs):
        self.updates.append(kwargs)
        return True

    def mark_research_progress_completed(self, run_id, partial=False):
        return True

    def mark_research_progress_failed(self, run_id, progress_message=None):
        return True


def _full_chunks():
    """Cumulative stream_mode="values" snapshots for a 4-analyst run, with a
    deliberate duplicate chunk after the sentiment report appears."""
    base = {"company_of_interest": "NVDA", "messages": []}
    c1 = {**base, "market_report": "market findings"}
    c2 = {**c1, "sentiment_report": "sentiment findings"}
    c3 = {**c2, "news_report": "news findings"}
    c4 = {**c3, "fundamentals_report": "fundamentals findings"}
    c5 = {
        **c4,
        "investment_debate_state": {
            "bull_history": "bull",
            "bear_history": "bear",
            "judge_decision": "debate settled",
        },
        "investment_plan": "plan",
    }
    c6 = {**c5, "trader_investment_plan": "trader plan"}
    c7 = {
        **c6,
        "risk_debate_state": {"judge_decision": "risk settled", "aggressive_history": "a"},
        "final_trade_decision": "decision text",
    }
    return [c1, c2, c2, c3, c4, c5, c6, c7]


def _payload(run_id=None, analysts=None):
    payload = {
        "allow_real_tradingagents_run": True,
        "ticker": "NVDA",
        "analysis_date": "2026-07-16",
        "selected_analysts": analysts or ["market", "sentiment", "news", "fundamentals"],
        "config": {"llm_provider": "anthropic", "deep_think_llm": "claude-sonnet-4-6", "quick_think_llm": "claude-sonnet-4-6"},
        "profile_id": PROFILE,
    }
    if run_id is not None:
        payload["run_id"] = run_id
    return payload


def _run(tmp_path, payload, chunks, repo=None):
    graph = _FakeGraph(chunks)
    reporter = None
    if repo is not None:
        reporter = ResearchProgressReporter(
            repo, payload.get("run_id", "run-x"), profile_id=PROFILE,
            selected_analysts=payload["selected_analysts"],
        )
    run_dir = run_streaming_tradingagents_research(
        payload,
        output_root=str(tmp_path),
        progress_reporter=reporter,
        graph_factory=lambda internal, config: graph,
    )
    return run_dir, graph


# ---------------------------------------------------------------------------
# Streaming progress
# ---------------------------------------------------------------------------


def test_four_analysts_advance_stepwise_then_debate_trader_risk(tmp_path):
    repo = _RecordingProgressRepo()
    _run(tmp_path, _payload(run_id="claimed-run-1"), _full_chunks(), repo)

    flow = [(u["current_stage"], u["progress_percent"]) for u in repo.updates]
    assert flow == [
        ("market_analysis", 20),
        ("sentiment_analysis", 30),
        ("news_analysis", 40),
        ("fundamentals_analysis", 50),
        ("research_debate", 58),
        ("trading_plan", 64),
        ("risk_review", 70),
    ]


def test_duplicate_chunks_never_advance_twice(tmp_path):
    repo = _RecordingProgressRepo()
    chunks = _full_chunks()
    # Repeat every chunk twice.
    doubled = [chunk for chunk in chunks for _ in range(2)]
    _run(tmp_path, _payload(run_id="claimed-run-2"), doubled, repo)
    stages = [u["current_stage"] for u in repo.updates]
    assert len(stages) == len(set(stages)) == 7


def test_two_analyst_selection_splits_the_window(tmp_path):
    repo = _RecordingProgressRepo()
    base = {"company_of_interest": "NVDA"}
    c1 = {**base, "market_report": "m"}
    c2 = {**c1, "sentiment_report": "s"}
    c3 = {
        **c2,
        "investment_debate_state": {"judge_decision": "settled"},
        "trader_investment_plan": "t",
        "risk_debate_state": {"judge_decision": "settled"},
        "final_trade_decision": "d",
    }
    _run(tmp_path, _payload(run_id="claimed-run-3", analysts=["market", "sentiment"]), [c1, c2, c3], repo)
    flow = [(u["current_stage"], u["progress_percent"]) for u in repo.updates]
    assert flow[:2] == [("market_analysis", 30), ("sentiment_analysis", 50)]


def test_single_analyst_selection(tmp_path):
    repo = _RecordingProgressRepo()
    base = {"company_of_interest": "NVDA"}
    c1 = {**base, "news_report": "n"}
    c2 = {
        **c1,
        "investment_debate_state": {"judge_decision": "settled"},
        "trader_investment_plan": "t",
        "risk_debate_state": {"judge_decision": "settled"},
        "final_trade_decision": "d",
    }
    _run(tmp_path, _payload(run_id="claimed-run-4", analysts=["news"]), [c1, c2], repo)
    assert (repo.updates[0]["current_stage"], repo.updates[0]["progress_percent"]) == (
        "news_analysis",
        50,
    )


def test_stream_uses_values_mode_and_merges_final_state(tmp_path):
    run_dir, graph = _run(tmp_path, _payload(run_id="claimed-run-5"), _full_chunks())
    assert graph.graph.stream_calls[0]["kwargs"]["stream_mode"] == "values"
    raw = json.loads((run_dir / "raw_agent_outputs.json").read_text())
    agents = {record["agent"] for record in raw["agent_outputs"]}
    # The merged final state carried every report + debate + trader + risk
    # sections, so the official writer extracted all of them.
    assert {
        "market_agent",
        "sentiment_agent",
        "news_agent",
        "fundamental_agent",
        "trader",
        "portfolio_manager",
    }.issubset(agents)


def test_internal_analysts_passed_to_graph_factory(tmp_path):
    captured = {}

    def factory(internal, config):
        captured["internal"] = internal
        captured["config"] = config
        return _FakeGraph(_full_chunks())

    run_streaming_tradingagents_research(
        _payload(run_id="claimed-run-6"),
        output_root=str(tmp_path),
        graph_factory=factory,
    )
    assert captured["internal"] == ["market", "social", "news", "fundamentals"]
    # metadata keeps the *public* vocabulary -- social never leaks outward.
    metadata = json.loads((tmp_path / "claimed-run-6" / "metadata.json").read_text())
    assert metadata["selected_analysts"] == ["market", "sentiment", "news", "fundamentals"]
    assert "social" not in metadata["selected_analysts"]


# ---------------------------------------------------------------------------
# Claimed-run_id relocation through the official writer
# ---------------------------------------------------------------------------


def test_outputs_land_under_the_claimed_run_id(tmp_path):
    run_dir, _graph = _run(tmp_path, _payload(run_id="claimed-run-7"), _full_chunks())
    assert run_dir.name == "claimed-run-7"
    assert (tmp_path / "claimed-run-7" / "raw_agent_outputs.json").exists()
    # The writer's temporary uuid directory is gone.
    assert [p.name for p in tmp_path.iterdir()] == ["claimed-run-7"]

    metadata = json.loads((run_dir / "metadata.json").read_text())
    raw = json.loads((run_dir / "raw_agent_outputs.json").read_text())
    assert metadata["run_id"] == "claimed-run-7"
    assert raw["run_id"] == "claimed-run-7"
    for record in raw["agent_outputs"]:
        assert record["run_id"] == "claimed-run-7"
        assert record["agent_output_id"].startswith("claimed-run-7:")


def test_without_claimed_run_id_the_writer_directory_is_kept(tmp_path):
    run_dir, _graph = _run(tmp_path, _payload(run_id=None), _full_chunks())
    assert run_dir.exists()
    raw = json.loads((run_dir / "raw_agent_outputs.json").read_text())
    assert raw["run_id"] == run_dir.name


# ---------------------------------------------------------------------------
# Guard rails
# ---------------------------------------------------------------------------


def test_streaming_requires_server_opt_in(tmp_path):
    payload = _payload()
    payload.pop("allow_real_tradingagents_run")
    with pytest.raises(RuntimeError, match="disabled by default"):
        run_streaming_tradingagents_research(payload, output_root=str(tmp_path))


def test_streaming_requires_server_config(tmp_path):
    payload = _payload()
    payload["config"] = None
    with pytest.raises(RuntimeError, match="config"):
        run_streaming_tradingagents_research(
            payload, output_root=str(tmp_path), graph_factory=lambda i, c: _FakeGraph([])
        )


def test_empty_stream_fails_rather_than_writing_an_empty_run(tmp_path):
    with pytest.raises(RuntimeError, match="no state"):
        run_streaming_tradingagents_research(
            _payload(run_id="claimed-run-8"),
            output_root=str(tmp_path),
            graph_factory=lambda i, c: _FakeGraph([]),
        )
    assert not (tmp_path / "claimed-run-8").exists()


def test_progress_failures_never_fail_the_run(tmp_path):
    class _ExplodingRepo:
        def initialize_research_progress(self, *a, **k):
            raise RuntimeError("db down")

        def update_research_progress(self, *a, **k):
            raise RuntimeError("db down")

    reporter = ResearchProgressReporter(
        _ExplodingRepo(), "claimed-run-9", profile_id=PROFILE,
        selected_analysts=["market", "sentiment", "news", "fundamentals"],
    )
    run_dir = run_streaming_tradingagents_research(
        _payload(run_id="claimed-run-9"),
        output_root=str(tmp_path),
        progress_reporter=reporter,
        graph_factory=lambda i, c: _FakeGraph(_full_chunks()),
    )
    assert run_dir.name == "claimed-run-9"
