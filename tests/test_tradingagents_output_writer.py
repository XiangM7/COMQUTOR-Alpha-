import json
from pathlib import Path

import pytest

from comqutor_alpha.adapters.tradingagents_output_writer import (
    MAX_RAW_OUTPUT_CHARS,
    OUTPUT_VERSION,
    TRUNCATION_MARKER,
    _to_string,
    build_raw_agent_output_record,
    save_comqutor_run_outputs,
)


def _final_state():
    return {
        "market_report": "Market report text.",
        "sentiment_report": "Sentiment report text.",
        "news_report": "News report text.",
        "fundamentals_report": "Fundamentals report text.",
        "investment_debate_state": {
            "bull_history": "Bull history text.",
            "bear_history": "Bear history text.",
            "judge_decision": "Research manager fallback text.",
        },
        "investment_plan": "Research manager primary plan.",
        "trader_investment_plan": "Trader plan text.",
        "risk_debate_state": {
            "aggressive_history": "Aggressive risk text.",
            "conservative_history": "Conservative risk text.",
            "neutral_history": "Neutral risk text.",
            "judge_decision": "Portfolio manager fallback text.",
        },
        "final_trade_decision": "Portfolio manager final decision.",
    }


def _load_run(run_dir):
    run_dir = Path(run_dir)
    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    raw = json.loads((run_dir / "raw_agent_outputs.json").read_text(encoding="utf-8"))
    return metadata, raw


def _record(raw, agent):
    return next(item for item in raw["agent_outputs"] if item["agent"] == agent)


def test_extracts_expected_outputs_from_final_state(tmp_path):
    run_dir = save_comqutor_run_outputs(
        final_state=_final_state(),
        ticker="NVDA",
        config={"llm_provider": "openai"},
        selected_analysts=["market", "news"],
        analysis_date="2026-06-30",
        output_root=tmp_path,
    )
    metadata, raw = _load_run(run_dir)

    assert raw["schema_version"] == OUTPUT_VERSION
    assert len(raw["agent_outputs"]) == 12
    assert metadata["agents"] == [
        "market_agent",
        "sentiment_agent",
        "news_agent",
        "fundamental_agent",
        "bull_researcher",
        "bear_researcher",
        "research_manager",
        "trader",
        "aggressive_risk_analyst",
        "conservative_risk_analyst",
        "neutral_risk_analyst",
        "portfolio_manager",
    ]

    record = _record(raw, "market_agent")
    for field in (
        "agent_output_id",
        "run_id",
        "ticker",
        "agent",
        "tradingagents_agent",
        "source_field",
        "source_path",
        "source_candidates",
        "raw_output",
        "content_length",
        "original_content_length",
        "truncated",
        "created_at",
    ):
        assert field in record
    assert record["agent_output_id"] == f"{metadata['run_id']}:market_agent:market_report"
    assert record["source_path"] == "market_report"
    assert record["truncated"] is False


def test_research_manager_fallback(tmp_path):
    final_state = _final_state()
    final_state.pop("investment_plan")

    run_dir = save_comqutor_run_outputs(final_state, "NVDA", output_root=tmp_path)
    _metadata, raw = _load_run(run_dir)
    record = _record(raw, "research_manager")

    assert record["source_path"] == "investment_debate_state.judge_decision"
    assert record["raw_output"] == "Research manager fallback text."


def test_portfolio_manager_fallback(tmp_path):
    final_state = _final_state()
    final_state.pop("final_trade_decision")

    run_dir = save_comqutor_run_outputs(final_state, "NVDA", output_root=tmp_path)
    _metadata, raw = _load_run(run_dir)
    record = _record(raw, "portfolio_manager")

    assert record["source_path"] == "risk_debate_state.judge_decision"
    assert record["raw_output"] == "Portfolio manager fallback text."


def test_primary_path_wins_when_fallback_also_exists(tmp_path):
    run_dir = save_comqutor_run_outputs(_final_state(), "NVDA", output_root=tmp_path)
    _metadata, raw = _load_run(run_dir)
    record = _record(raw, "research_manager")

    assert record["source_path"] == "investment_plan"
    assert "investment_debate_state.judge_decision" in record["source_candidates"]
    assert record["raw_output"] == "Research manager primary plan."


def test_metadata_does_not_include_secret_config_values(tmp_path):
    run_dir = save_comqutor_run_outputs(
        _final_state(),
        "NVDA",
        config={
            "llm_provider": "openai",
            "quick_think_llm": "quick-model",
            "deep_think_llm": "deep-model",
            "OPENAI_API_KEY": "SHOULD_NOT_APPEAR",
            "api_key": "SHOULD_NOT_APPEAR",
            "secret_token": "SHOULD_NOT_APPEAR",
            "password": "SHOULD_NOT_APPEAR",
            "backend_url": "SHOULD_NOT_APPEAR",
        },
        output_root=tmp_path,
    )
    metadata, _raw = _load_run(run_dir)
    serialized = json.dumps(metadata, ensure_ascii=False)

    assert metadata["llm_provider"] == "openai"
    assert metadata["quick_model"] == "quick-model"
    assert metadata["deep_model"] == "deep-model"
    assert "SHOULD_NOT_APPEAR" not in serialized


def test_oversized_raw_output_is_truncated(tmp_path):
    final_state = {"market_report": "x" * (MAX_RAW_OUTPUT_CHARS + 100)}

    run_dir = save_comqutor_run_outputs(final_state, "NVDA", output_root=tmp_path)
    _metadata, raw = _load_run(run_dir)
    record = _record(raw, "market_agent")

    assert record["truncated"] is True
    assert record["original_content_length"] == MAX_RAW_OUTPUT_CHARS + 100
    assert record["content_length"] == MAX_RAW_OUTPUT_CHARS
    assert record["raw_output"].endswith(TRUNCATION_MARKER)


def test_build_raw_agent_output_record_truncates_large_raw_value():
    record = build_raw_agent_output_record(
        run_id="run_1",
        ticker="NVDA",
        agent="market_agent",
        tradingagents_agent="Market Analyst",
        source_field="market_report",
        source_path="market_report",
        source_candidates=["market_report"],
        raw_value="x" * (MAX_RAW_OUTPUT_CHARS + 1),
        created_at="2026-07-08T00:00:00Z",
        record_suffix="0",
    )

    assert record["agent_output_id"] == "run_1:market_agent:market_report:0"
    assert record["truncated"] is True
    assert record["content_length"] == MAX_RAW_OUTPUT_CHARS
    assert record["original_content_length"] == MAX_RAW_OUTPUT_CHARS + 1


def test_final_report_is_not_written_by_default(tmp_path):
    run_dir = save_comqutor_run_outputs(_final_state(), "NVDA", output_root=tmp_path)
    metadata, _raw = _load_run(run_dir)

    assert metadata["artifacts"]["final_report"] is False
    assert not (Path(run_dir) / "final_report.md").exists()


def test_final_report_is_written_only_when_opted_in(tmp_path):
    run_dir = save_comqutor_run_outputs(
        _final_state(),
        "NVDA",
        output_root=tmp_path,
        write_final_report=True,
    )
    metadata, _raw = _load_run(run_dir)

    assert metadata["artifacts"]["final_report"] is True
    assert (Path(run_dir) / "final_report.md").exists()


def test_invalid_final_state_none_raises_value_error(tmp_path):
    with pytest.raises(ValueError, match="INVALID_FINAL_STATE"):
        save_comqutor_run_outputs(None, "NVDA", output_root=tmp_path)


def test_empty_final_state_requires_explicit_opt_in_and_writes_warning(tmp_path):
    with pytest.raises(ValueError, match="final_state is empty"):
        save_comqutor_run_outputs({}, "NVDA", output_root=tmp_path)

    run_dir = save_comqutor_run_outputs(
        {},
        "NVDA",
        output_root=tmp_path,
        allow_empty_final_state=True,
    )
    metadata, raw = _load_run(run_dir)

    assert metadata["warnings"] == ["NO_AGENT_OUTPUTS_EXTRACTED"]
    assert raw["agent_outputs"] == []


def test_to_string_handles_common_values_and_circular_reference():
    class NeedsDefaultString:
        def __str__(self):
            return "needs-default-string"

    circular = []
    circular.append(circular)

    assert _to_string("plain text") == "plain text"
    assert _to_string({"text": "英伟达"}) == '{"text": "英伟达"}'
    assert "needs-default-string" in _to_string({"obj": NeedsDefaultString()})
    assert _to_string(circular) == "[[...]]"
