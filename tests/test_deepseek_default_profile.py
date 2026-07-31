"""Make DeepSeek the Default Research Profile -- dedicated coverage.

Complements the updated assertions in test_research_profiles.py,
test_server_execution.py, test_api_system_routes.py, and test_w5_1b_api.py
(all updated in this same sprint). This file focuses on:

- the real thinking-disabled wiring reaching TradingAgentsGraph
  construction for the *actual* real-execution runner entrypoints
  (not just the DeepSeek smoke-profile path from a prior sprint),
- the four real-mode analysts staying intact,
- no automatic Anthropic fallback anywhere in the resolution chain,
- readiness/metadata showing the real, current default profile.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from comqutor_alpha import research_profiles, server_execution
from comqutor_alpha.llm.deepseek_smoke import (
    DeepSeekThinkingDisabledChatOpenAI,
    DeepSeekThinkingEnabledChatOpenAI,
)
from comqutor_alpha.runners import tradingagents_runner as runner
from tradingagents.llm_clients.openai_client import OPENAI_COMPATIBLE_PROVIDERS

# ---------------------------------------------------------------------------
# Default profile resolution
# ---------------------------------------------------------------------------


class TestDefaultProfileIsDeepSeek:
    def test_active_profile_id_is_the_new_deepseek_default(self):
        assert research_profiles.ACTIVE_PROFILE_ID == "comqutor_deepseek_default_v1"

    def test_default_profile_full_shape(self):
        profile = research_profiles.get_active_research_profile()
        assert profile.llm_provider == "deepseek"
        assert profile.quick_think_llm == "deepseek-v4-flash"
        assert profile.deep_think_llm == "deepseek-v4-flash"
        assert profile.deepseek_thinking == "disabled"
        assert profile.max_debate_rounds == 1
        assert profile.max_risk_discuss_rounds == 1
        assert profile.temperature == 0.0

    def test_no_profile_id_resolves_to_deepseek_default(self):
        assert research_profiles.get_research_profile(None).profile_id == "comqutor_deepseek_default_v1"
        assert research_profiles.get_research_profile("").profile_id == "comqutor_deepseek_default_v1"


# ---------------------------------------------------------------------------
# Four analysts preserved
# ---------------------------------------------------------------------------


def test_four_real_mode_analysts_are_all_still_allowed():
    assert frozenset(
        {"market", "news", "fundamentals", "sentiment"}
    ) == server_execution.REAL_RUN_ALLOWED_ANALYSTS


def test_real_analyst_validation_accepts_all_four_together():
    server_execution.validate_real_selected_analysts(["market", "sentiment", "news", "fundamentals"])  # no raise


# ---------------------------------------------------------------------------
# Thinking really disabled -- proven at the real execution entrypoints,
# not only the smoke-profile path.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_thinking_env(monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_DEEPSEEK_THINKING", raising=False)


class _RecordingGraph:
    """Stand-in for TradingAgentsGraph: records which DeepSeek chat_class
    was active in the provider registry at construction time (the only
    moment that matters -- see _deepseek_thinking_scope_for_config's
    docstring) without ever touching a real provider."""

    captured_chat_class: type | None = None

    def __init__(self, *args, **kwargs):
        _RecordingGraph.captured_chat_class = OPENAI_COMPATIBLE_PROVIDERS["deepseek"].chat_class

    def propagate(self, ticker, analysis_date, asset_type="stock"):
        return {"final_trade_decision": "HOLD"}, None


class TestRealRunnerThinkingWiring:
    def test_original_runner_constructs_graph_with_thinking_disabled(self, monkeypatch, tmp_path):
        import tradingagents.graph.trading_graph as trading_graph_module

        monkeypatch.setattr(trading_graph_module, "TradingAgentsGraph", _RecordingGraph)
        monkeypatch.setattr(
            "comqutor_alpha.adapters.tradingagents_output_writer.save_comqutor_run_outputs",
            lambda **kwargs: tmp_path / "fake-run",
        )
        config = research_profiles.build_profile_tradingagents_config()
        config["deepseek_thinking"] = "disabled"

        payload = {
            "allow_real_tradingagents_run": True,
            "ticker": "NVDA",
            "analysis_date": "2026-07-30",
            "config": config,
        }
        runner.run_original_tradingagents_research(payload, output_root=str(tmp_path))

        assert _RecordingGraph.captured_chat_class is DeepSeekThinkingDisabledChatOpenAI

    def test_original_runner_constructs_graph_with_thinking_enabled_when_configured(self, monkeypatch, tmp_path):
        import tradingagents.graph.trading_graph as trading_graph_module

        monkeypatch.setattr(trading_graph_module, "TradingAgentsGraph", _RecordingGraph)
        monkeypatch.setattr(
            "comqutor_alpha.adapters.tradingagents_output_writer.save_comqutor_run_outputs",
            lambda **kwargs: tmp_path / "fake-run",
        )
        config = research_profiles.build_profile_tradingagents_config()
        config["deepseek_thinking"] = "enabled"

        payload = {
            "allow_real_tradingagents_run": True,
            "ticker": "NVDA",
            "analysis_date": "2026-07-30",
            "config": config,
        }
        runner.run_original_tradingagents_research(payload, output_root=str(tmp_path))

        assert _RecordingGraph.captured_chat_class is DeepSeekThinkingEnabledChatOpenAI

    def test_non_deepseek_provider_never_touches_the_deepseek_registry_entry(self, monkeypatch, tmp_path):
        import tradingagents.graph.trading_graph as trading_graph_module

        monkeypatch.setattr(trading_graph_module, "TradingAgentsGraph", _RecordingGraph)
        monkeypatch.setattr(
            "comqutor_alpha.adapters.tradingagents_output_writer.save_comqutor_run_outputs",
            lambda **kwargs: tmp_path / "fake-run",
        )
        anthropic_profile = research_profiles.get_research_profile(research_profiles.ANTHROPIC_PROFILE_ID)
        config = research_profiles.build_profile_tradingagents_config(anthropic_profile)
        before = OPENAI_COMPATIBLE_PROVIDERS["deepseek"].chat_class

        payload = {
            "allow_real_tradingagents_run": True,
            "ticker": "NVDA",
            "analysis_date": "2026-07-30",
            "config": config,
        }
        runner.run_original_tradingagents_research(payload, output_root=str(tmp_path))

        assert _RecordingGraph.captured_chat_class is before  # untouched

    def test_streaming_graph_factory_also_gets_thinking_disabled(self):
        config = research_profiles.build_profile_tradingagents_config()
        config["deepseek_thinking"] = "disabled"
        with runner._deepseek_thinking_scope_for_config(config):
            assert OPENAI_COMPATIBLE_PROVIDERS["deepseek"].chat_class is DeepSeekThinkingDisabledChatOpenAI

    def test_bad_env_override_fails_the_run_loudly(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRADINGAGENTS_DEEPSEEK_THINKING", "sort-of-disabled")
        config = research_profiles.build_profile_tradingagents_config()
        config["deepseek_thinking"] = "disabled"
        payload = {
            "allow_real_tradingagents_run": True,
            "ticker": "NVDA",
            "analysis_date": "2026-07-30",
            "config": config,
        }
        with pytest.raises(ValueError, match="TRADINGAGENTS_DEEPSEEK_THINKING"):
            runner.run_original_tradingagents_research(payload, output_root=str(tmp_path))

    def test_disabled_extra_body_actually_reaches_the_request_payload(self):
        """End-to-end proof (no network): the class selected during the
        scope really injects extra_body={"thinking": {"type": "disabled"}}
        on the outgoing request, exactly like the Track A smoke profile."""
        client = DeepSeekThinkingDisabledChatOpenAI(
            model="deepseek-v4-flash", api_key="placeholder", base_url="https://api.deepseek.com"
        )
        payload = client._get_request_payload([HumanMessage(content="hi")])
        assert payload["extra_body"]["thinking"] == {"type": "disabled"}


# ---------------------------------------------------------------------------
# No automatic Anthropic fallback anywhere
# ---------------------------------------------------------------------------


class TestNoAutomaticAnthropicFallback:
    def test_missing_deepseek_key_never_silently_switches_provider(self, monkeypatch):
        monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "true")
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        # ANTHROPIC_API_KEY is present (autouse fixture) -- must not matter.
        ctx = server_execution.build_server_execution_context()
        assert ctx["error"] == "REAL_RUN_CREDENTIAL_MISSING"
        assert ctx["config"] is None
        # The resolved profile is still DeepSeek -- no fallback identity swap.
        assert ctx["execution_identity"]["provider_identity"] == "deepseek"

    def test_deepseek_request_failure_has_no_fallback_code_path(self, monkeypatch, tmp_path):
        """There is no alternate-provider branch anywhere in the real
        runner: a DeepSeek graph-construction failure propagates unchanged,
        it never triggers a retry against a different provider."""
        import tradingagents.graph.trading_graph as trading_graph_module

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated DeepSeek failure")

        monkeypatch.setattr(trading_graph_module, "TradingAgentsGraph", _boom)
        config = research_profiles.build_profile_tradingagents_config()
        config["deepseek_thinking"] = "disabled"
        payload = {
            "allow_real_tradingagents_run": True,
            "ticker": "NVDA",
            "analysis_date": "2026-07-30",
            "config": config,
        }
        with pytest.raises(RuntimeError, match="simulated DeepSeek failure"):
            runner.run_original_tradingagents_research(payload, output_root=str(tmp_path))
        assert config["llm_provider"] == "deepseek"  # never mutated to anthropic


# ---------------------------------------------------------------------------
# Readiness / metadata show the real profile
# ---------------------------------------------------------------------------


class TestReadinessShowsRealProfile:
    def test_readiness_profile_block_matches_the_real_default(self):
        from comqutor_alpha.api.routes_system import readiness_response

        body, _ok = readiness_response(job_manager=None)
        assert body["profile"]["profile_id"] == "comqutor_deepseek_default_v1"
        assert body["profile"]["profile_display_name"] == "DeepSeek Default Research"
        assert body["profile"]["provider"] == "deepseek"
        assert body["profile"]["quick_model"] == "deepseek-v4-flash"
        assert body["profile"]["deep_model"] == "deepseek-v4-flash"
        assert body["profile"]["thinking"] == "disabled"
        assert body["profile"]["max_debate_rounds"] == 1
        assert body["profile"]["max_risk_discuss_rounds"] == 1

    def test_readiness_never_mentions_anthropic_or_smoke_profile(self):
        from comqutor_alpha.api.routes_system import readiness_response

        body, _ok = readiness_response(job_manager=None)
        serialized = str(body)
        assert "anthropic" not in serialized.lower()
        assert "smoke" not in serialized.lower()
