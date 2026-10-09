"""Tests for the configurable sampling temperature (#178/#168).

Temperature is a cross-provider knob: when set it must reach the underlying
chat client; when unset the provider keeps its own default.
"""

import importlib

import pytest

from tradingagents.llm_clients.factory import create_llm_client


@pytest.mark.unit
class TestTemperatureForwarding:
    @pytest.mark.parametrize(
        "provider,model",
        [
            ("openai", "gpt-4.1"),
            ("anthropic", "claude-sonnet-4-6"),
            ("google", "gemini-2.5-flash"),
            ("deepseek", "deepseek-chat"),
        ],
    )
    def test_temperature_reaches_client_when_set(self, provider, model):
        llm = create_llm_client(
            provider=provider, model=model, temperature=0.0, api_key="placeholder"
        ).get_llm()
        assert llm.temperature == 0.0

    def test_temperature_omitted_leaves_provider_default(self):
        # Not passing temperature must not force it to a value.
        llm = create_llm_client(
            provider="openai", model="gpt-4.1", api_key="placeholder"
        ).get_llm()
        # langchain's default is unset/None, not 0.0
        assert llm.temperature is None


@pytest.mark.unit
class TestTemperatureEnvOverlay:
    def test_env_sets_temperature(self, monkeypatch):
        import tradingagents.default_config as dc
        monkeypatch.setenv("TRADINGAGENTS_TEMPERATURE", "0.2")
        importlib.reload(dc)
        # Stored on config (string from env is fine; consumed via float()).
        assert dc.DEFAULT_CONFIG["temperature"] in ("0.2", 0.2)
        assert float(dc.DEFAULT_CONFIG["temperature"]) == 0.2
        monkeypatch.delenv("TRADINGAGENTS_TEMPERATURE", raising=False)
        importlib.reload(dc)

    def test_default_temperature_is_none(self, monkeypatch):
        import tradingagents.default_config as dc
        monkeypatch.delenv("TRADINGAGENTS_TEMPERATURE", raising=False)
        importlib.reload(dc)
        assert dc.DEFAULT_CONFIG["temperature"] is None


@pytest.mark.unit
class TestProviderKwargsTemperature:
    """_get_provider_kwargs float-coerces and forwards temperature, or omits it."""

    def _kwargs_for(self, temperature):
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        # Call the method without constructing the full graph.
        graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
        graph.config = {"llm_provider": "openai", "temperature": temperature}
        return TradingAgentsGraph._get_provider_kwargs(graph)

    def test_float_string_coerced(self):
        assert self._kwargs_for("0.3")["temperature"] == 0.3

    def test_float_passthrough(self):
        assert self._kwargs_for(0.0)["temperature"] == 0.0

    def test_none_omitted(self):
        assert "temperature" not in self._kwargs_for(None)

    def test_empty_string_omitted(self):
        assert "temperature" not in self._kwargs_for("")


@pytest.mark.unit
class TestProviderKwargsMaxTokens:
    """_get_provider_kwargs int-coerces and forwards max_tokens, or omits it.

    Added 2026-09-30 (T3/T4 joint-verification execution-path task): the
    Research Agent layer previously had no enforceable per-call output-token
    cap at all -- this is the minimum necessary limit added for that gap,
    mirroring the existing, already-tested temperature-forwarding pattern
    directly above.
    """

    def _kwargs_for(self, max_tokens):
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
        graph.config = {"llm_provider": "openai", "max_tokens": max_tokens}
        return TradingAgentsGraph._get_provider_kwargs(graph)

    def test_int_passthrough(self):
        assert self._kwargs_for(4000)["max_tokens"] == 4000

    def test_string_coerced(self):
        assert self._kwargs_for("4000")["max_tokens"] == 4000

    def test_none_omitted(self):
        assert "max_tokens" not in self._kwargs_for(None)

    def test_empty_string_omitted(self):
        assert "max_tokens" not in self._kwargs_for("")


@pytest.mark.unit
class TestMaxTokensReachesClient:
    @pytest.mark.parametrize(("provider", "model"), [("openai", "gpt-5.5"), ("anthropic", "claude-sonnet-4-6")])
    def test_max_tokens_reaches_client_when_set(self, provider, model):
        llm = create_llm_client(
            provider=provider, model=model, max_tokens=4000, api_key="placeholder"
        ).get_llm()
        assert llm.max_tokens == 4000

    def test_max_tokens_omitted_leaves_provider_default(self):
        llm = create_llm_client(provider="openai", model="gpt-5.5", api_key="placeholder").get_llm()
        assert llm.max_tokens is None


@pytest.mark.unit
class TestProviderKwargsMaxRetries:
    """Mirrors TestProviderKwargsMaxTokens for the sibling max_retries forward."""

    def _kwargs_for(self, max_retries):
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
        graph.config = {"llm_provider": "openai", "max_retries": max_retries}
        return TradingAgentsGraph._get_provider_kwargs(graph)

    def test_int_passthrough(self):
        assert self._kwargs_for(2)["max_retries"] == 2

    def test_string_coerced(self):
        assert self._kwargs_for("2")["max_retries"] == 2

    def test_none_omitted(self):
        assert "max_retries" not in self._kwargs_for(None)

    def test_empty_string_omitted(self):
        assert "max_retries" not in self._kwargs_for("")


@pytest.mark.unit
class TestMaxRetriesReachesClient:
    @pytest.mark.parametrize(("provider", "model"), [("openai", "gpt-5.5"), ("anthropic", "claude-sonnet-4-6")])
    def test_max_retries_reaches_client_when_set(self, provider, model):
        llm = create_llm_client(
            provider=provider, model=model, max_retries=5, api_key="placeholder"
        ).get_llm()
        assert llm.max_retries == 5
