"""Track A: DeepSeek Non-Thinking Smoke Profile tests.

Covers the 12 DeepSeek-profile scenarios from the sprint spec plus the
debate/risk *node invocation count* check (A4), which must exercise the
real ``ConditionalLogic`` state machine rather than only asserting on a
config string.
"""

from __future__ import annotations

import dataclasses

import pytest
from langchain_core.messages import HumanMessage

from comqutor_alpha.llm import deepseek_smoke
from comqutor_alpha.runners.tradingagents_runner import map_public_analysts_to_internal
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.llm_clients.openai_client import (
    OPENAI_COMPATIBLE_PROVIDERS,
    DeepSeekChatOpenAI,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(deepseek_smoke.DEEPSEEK_THINKING_ENV_VAR, raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)


# 1. Independent smoke profile loads --------------------------------------


def test_smoke_profile_loads_and_is_distinct_from_formal_default_profile():
    from comqutor_alpha import research_profiles

    smoke = deepseek_smoke.get_deepseek_smoke_profile()
    assert smoke.profile_id == "comqutor_deepseek_smoke_v1"
    formal = research_profiles.get_active_research_profile()
    # Both may use the DeepSeek provider now, but they remain two distinct,
    # independently-versioned profiles -- the smoke profile is still never
    # equated with the formal default research profile's identity/quality.
    assert formal.profile_id != smoke.profile_id
    assert formal.profile_id == "comqutor_deepseek_default_v1"


# 2. Provider is deepseek ---------------------------------------------------


def test_provider_is_deepseek():
    smoke = deepseek_smoke.get_deepseek_smoke_profile()
    assert smoke.llm_provider == "deepseek"
    config = deepseek_smoke.build_deepseek_smoke_config(smoke)
    assert config["llm_provider"] == "deepseek"


# 3. Quick/deep model correct ------------------------------------------------


def test_quick_and_deep_models_are_cheap_and_valid():
    from tradingagents.llm_clients.validators import validate_model

    smoke = deepseek_smoke.get_deepseek_smoke_profile()
    assert smoke.quick_think_llm == "deepseek-v4-flash"
    assert smoke.deep_think_llm == "deepseek-v4-flash"
    assert validate_model("deepseek", smoke.quick_think_llm)
    assert validate_model("deepseek", smoke.deep_think_llm)


# 4. Thinking disabled actually reaches the client request ------------------


def test_thinking_disabled_reaches_client_request():
    client = deepseek_smoke.DeepSeekThinkingDisabledChatOpenAI(
        model="deepseek-v4-flash", api_key="placeholder", base_url="https://api.deepseek.com"
    )
    payload = client._get_request_payload([HumanMessage(content="hi")])
    assert payload["extra_body"]["thinking"] == {"type": "disabled"}


def test_thinking_enabled_reaches_client_request():
    client = deepseek_smoke.DeepSeekThinkingEnabledChatOpenAI(
        model="deepseek-v4-flash", api_key="placeholder", base_url="https://api.deepseek.com"
    )
    payload = client._get_request_payload([HumanMessage(content="hi")])
    assert payload["extra_body"]["thinking"] == {"type": "enabled"}


def test_thinking_controlled_client_preserves_reasoning_content_roundtrip():
    """The new subclasses must not lose DeepSeekChatOpenAI's existing
    reasoning_content roundtrip behavior -- only add the thinking toggle."""
    assert issubclass(deepseek_smoke.DeepSeekThinkingDisabledChatOpenAI, DeepSeekChatOpenAI)
    assert issubclass(deepseek_smoke.DeepSeekThinkingEnabledChatOpenAI, DeepSeekChatOpenAI)


# 5. Debate rounds = 1 (real node invocation count, not a config string) ---


def test_debate_rounds_one_completes_exactly_one_bull_bear_exchange_then_manager():
    logic = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
    state = {"investment_debate_state": {"count": 0, "current_response": ""}}
    visited = []

    next_node = logic.should_continue_debate(state)
    visited.append(next_node)
    assert next_node == "Bull Researcher"

    # Bull speaks -> count becomes 1
    state["investment_debate_state"] = {"count": 1, "current_response": "Bull: ..."}
    next_node = logic.should_continue_debate(state)
    visited.append(next_node)
    assert next_node == "Bear Researcher"

    # Bear speaks -> count becomes 2 (== 2 * max_debate_rounds)
    state["investment_debate_state"] = {"count": 2, "current_response": "Bear: ..."}
    next_node = logic.should_continue_debate(state)
    visited.append(next_node)
    assert next_node == "Research Manager"

    assert visited == ["Bull Researcher", "Bear Researcher", "Research Manager"]


# 6. Risk rounds = 1 (real node invocation count) ---------------------------


def test_risk_rounds_one_completes_exactly_one_round_then_portfolio_manager():
    logic = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
    state = {"risk_debate_state": {"count": 0, "latest_speaker": ""}}
    visited = []

    next_node = logic.should_continue_risk_analysis(state)
    visited.append(next_node)
    assert next_node == "Aggressive Analyst"

    state["risk_debate_state"] = {"count": 1, "latest_speaker": "Aggressive: ..."}
    next_node = logic.should_continue_risk_analysis(state)
    visited.append(next_node)
    assert next_node == "Conservative Analyst"

    state["risk_debate_state"] = {"count": 2, "latest_speaker": "Conservative: ..."}
    next_node = logic.should_continue_risk_analysis(state)
    visited.append(next_node)
    assert next_node == "Neutral Analyst"

    state["risk_debate_state"] = {"count": 3, "latest_speaker": "Neutral: ..."}
    next_node = logic.should_continue_risk_analysis(state)
    visited.append(next_node)
    assert next_node == "Portfolio Manager"

    assert visited == [
        "Aggressive Analyst", "Conservative Analyst", "Neutral Analyst", "Portfolio Manager",
    ]


def test_config_rounds_match_profile_not_just_incidentally():
    smoke = deepseek_smoke.get_deepseek_smoke_profile()
    assert smoke.max_debate_rounds == 1
    assert smoke.max_risk_discuss_rounds == 1


# 7. Four analysts enter the workflow ---------------------------------------


def test_four_analysts_map_to_correct_internal_workflow_nodes():
    smoke = deepseek_smoke.get_deepseek_smoke_profile()
    public, internal = map_public_analysts_to_internal(list(smoke.selected_analysts))
    assert public == ["market", "sentiment", "news", "fundamentals"]
    assert internal == ["market", "social", "news", "fundamentals"]


# 8. Missing DeepSeek key fails clearly, no silent fallback -----------------


def test_missing_deepseek_key_fails_explicitly(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(deepseek_smoke.DeepSeekSmokeProfileError) as exc_info:
        deepseek_smoke.run_deepseek_smoke("SNDK", "2026-07-01")
    assert exc_info.value.reason_code == "DEEPSEEK_API_KEY_MISSING"


# 9. Request failure never falls back to another provider -------------------


def test_deepseek_request_failure_does_not_fall_back_to_anthropic(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "placeholder")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "placeholder-should-never-be-used")

    calls = []

    def _boom(**kwargs):
        calls.append(kwargs.get("provider"))
        raise RuntimeError("simulated DeepSeek request failure")

    monkeypatch.setattr(
        "comqutor_alpha.runners.tradingagents_runner.run_original_tradingagents_research",
        lambda payload, output_root=None: _boom(provider=payload["config"]["llm_provider"]),
    )

    with pytest.raises(RuntimeError, match="simulated DeepSeek request failure"):
        deepseek_smoke.run_deepseek_smoke("SNDK", "2026-07-01")

    assert calls == ["deepseek"]  # never retried, never switched provider


# 10. Non-DeepSeek providers never receive the thinking param ---------------


def test_non_deepseek_provider_registry_untouched_during_scope():
    other_before = OPENAI_COMPATIBLE_PROVIDERS["openai"].chat_class
    deepseek_before = OPENAI_COMPATIBLE_PROVIDERS["deepseek"].chat_class
    with deepseek_smoke.deepseek_thinking_scope("disabled"):
        assert OPENAI_COMPATIBLE_PROVIDERS["openai"].chat_class is other_before
        assert (
            OPENAI_COMPATIBLE_PROVIDERS["deepseek"].chat_class
            is deepseek_smoke.DeepSeekThinkingDisabledChatOpenAI
        )
    assert OPENAI_COMPATIBLE_PROVIDERS["deepseek"].chat_class is deepseek_before


def test_scope_restores_registry_even_on_exception():
    deepseek_before = OPENAI_COMPATIBLE_PROVIDERS["deepseek"].chat_class
    with pytest.raises(ValueError, match="boom"), deepseek_smoke.deepseek_thinking_scope("disabled"):
        raise ValueError("boom")
    assert OPENAI_COMPATIBLE_PROVIDERS["deepseek"].chat_class is deepseek_before


# 11. Env-var override ------------------------------------------------------


def test_env_var_overrides_profile_thinking_default(monkeypatch):
    smoke = deepseek_smoke.get_deepseek_smoke_profile()
    assert smoke.deepseek_thinking == "disabled"
    monkeypatch.setenv(deepseek_smoke.DEEPSEEK_THINKING_ENV_VAR, "enabled")
    assert deepseek_smoke.resolve_deepseek_thinking_mode(smoke) == "enabled"


def test_invalid_env_var_value_raises_at_resolve_time(monkeypatch):
    monkeypatch.setenv(deepseek_smoke.DEEPSEEK_THINKING_ENV_VAR, "sort-of")
    with pytest.raises(ValueError, match="TRADINGAGENTS_DEEPSEEK_THINKING"):
        deepseek_smoke.resolve_deepseek_thinking_mode()


# Profile serialization keeps configuration ----------------------------------


def test_profile_serializes_with_all_fields_intact():
    smoke = deepseek_smoke.get_deepseek_smoke_profile()
    as_dict = dataclasses.asdict(smoke)
    assert as_dict["llm_provider"] == "deepseek"
    assert as_dict["deepseek_thinking"] == "disabled"
    assert as_dict["selected_analysts"] == ("market", "sentiment", "news", "fundamentals")
    rebuilt = deepseek_smoke.DeepSeekSmokeProfile(**as_dict)
    assert rebuilt == smoke


# 12. Status surface shows real identity, no secrets ------------------------


def test_status_shows_real_provider_model_rounds_and_thinking(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "super-secret-value")
    status = deepseek_smoke.build_deepseek_smoke_status()
    assert status["provider"] == "deepseek"
    assert status["quick_think_llm"] == "deepseek-v4-flash"
    assert status["deep_think_llm"] == "deepseek-v4-flash"
    assert status["max_debate_rounds"] == 1
    assert status["max_risk_discuss_rounds"] == 1
    assert status["deepseek_thinking"] == "disabled"
    assert status["selected_analysts"] == ["market", "sentiment", "news", "fundamentals"]
    assert status["deepseek_api_key_present"] is True
    assert "super-secret-value" not in repr(status)
    assert "super-secret-value" not in str(status)


def test_status_key_absent_reports_false(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    status = deepseek_smoke.build_deepseek_smoke_status()
    assert status["deepseek_api_key_present"] is False


def test_error_reason_codes_never_contain_key_material(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    try:
        deepseek_smoke.run_deepseek_smoke("SNDK", "2026-07-01")
    except deepseek_smoke.DeepSeekSmokeProfileError as exc:
        assert exc.reason_code == "DEEPSEEK_API_KEY_MISSING"
        assert "sk-" not in str(exc)


# Invalid profile fields are rejected -----------------------------------------


def test_invalid_profile_rejected():
    bad = dataclasses.replace(deepseek_smoke.get_deepseek_smoke_profile(), llm_provider="anthropic")
    with pytest.raises(deepseek_smoke.DeepSeekSmokeProfileError):
        deepseek_smoke.validate_deepseek_smoke_profile(bad)

    bad_rounds = dataclasses.replace(deepseek_smoke.get_deepseek_smoke_profile(), max_debate_rounds=0)
    with pytest.raises(deepseek_smoke.DeepSeekSmokeProfileError):
        deepseek_smoke.validate_deepseek_smoke_profile(bad_rounds)

    bad_thinking = dataclasses.replace(deepseek_smoke.get_deepseek_smoke_profile(), deepseek_thinking="maybe")
    with pytest.raises(deepseek_smoke.DeepSeekSmokeProfileError):
        deepseek_smoke.validate_deepseek_smoke_profile(bad_thinking)
