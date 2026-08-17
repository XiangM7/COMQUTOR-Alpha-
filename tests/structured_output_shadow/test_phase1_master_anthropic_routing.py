from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from comqutor_alpha.llm_runtime.cache import build_llm_cache_key
from comqutor_alpha.llm_runtime.canonical_json import sha256_text
from comqutor_alpha.research_profiles import (
    ANTHROPIC_PROFILE_ID,
    DEEPSEEK_DEFAULT_PROFILE_ID,
    get_active_research_profile,
    get_research_profile,
)
from comqutor_alpha.structure_engine.structured_output_shadow_provider import (
    SHADOW_WEEK2_ERROR_LOG_ARTIFACT_PATH,
    STRUCTURED_CLAIM_SHADOW_MAX_RETRIES,
    STRUCTURED_CLAIM_SHADOW_TIMEOUT_SECONDS,
    build_phase1_master_provider_gateway,
    profile_id_for_semantic_task,
)

master = importlib.import_module("scripts.run_phase1_master")


def test_only_structured_claim_shadow_routes_to_anthropic():
    assert profile_id_for_semantic_task("structured_claim_shadow") == ANTHROPIC_PROFILE_ID
    for task in ("structured_adapter", "alpha_classifier", "structure_extractor"):
        assert profile_id_for_semantic_task(task) == DEEPSEEK_DEFAULT_PROFILE_ID
    with pytest.raises(ValueError, match="PHASE1_MASTER_SEMANTIC_TASK_UNKNOWN"):
        profile_id_for_semantic_task("user-controlled-provider")


def test_live_default_and_existing_week2_profile_remain_deepseek():
    default = get_active_research_profile()
    assert default.profile_id == DEEPSEEK_DEFAULT_PROFILE_ID
    assert default.llm_provider == "deepseek"
    assert default.quick_think_llm == "deepseek-v4-flash"


def test_anthropic_profile_and_credential_env_resolution(monkeypatch, tmp_path):
    profile = get_research_profile(ANTHROPIC_PROFILE_ID)
    monkeypatch.setattr(master, "REPO_ROOT", tmp_path)
    (tmp_path / ".env").write_text("placeholder=true\n", encoding="utf-8")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-test-key")
    result = master.run_provider_configuration_precheck(profile)
    assert result["passed"] is True
    assert result["credential_env_name"] == "ANTHROPIC_API_KEY"
    assert result["key_present"] is True
    assert result["key_length"] == len("fake-test-key")
    assert result["sanitized_base_url_hostname"] == "api.anthropic.com"


def test_master_gateway_uses_fixed_anthropic_policy(monkeypatch, tmp_path):
    profile = get_research_profile(ANTHROPIC_PROFILE_ID)
    captured = {}

    def fake_factory(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(get_llm=lambda: SimpleNamespace(invoke=lambda _prompt: None))

    monkeypatch.setattr("tradingagents.llm_clients.create_llm_client", fake_factory)
    gateway, info = build_phase1_master_provider_gateway(
        profile=profile,
        run_id="anthropic-eval",
        output_root=tmp_path,
        logical_call_limit=12,
    )
    assert captured["provider"] == "anthropic"
    assert captured["model"] == "claude-sonnet-4-6"
    assert captured["timeout"] == STRUCTURED_CLAIM_SHADOW_TIMEOUT_SECONDS == 180.0
    assert captured["max_retries"] == 0
    assert gateway.max_retries == STRUCTURED_CLAIM_SHADOW_MAX_RETRIES == 1
    assert gateway.error_log_artifact_path == SHADOW_WEEK2_ERROR_LOG_ARTIFACT_PATH
    assert info.max_provider_attempts == 24


def test_final_recanary_can_narrow_gateway_to_zero_retries(monkeypatch, tmp_path):
    profile = get_research_profile(ANTHROPIC_PROFILE_ID)
    monkeypatch.setattr(
        "tradingagents.llm_clients.create_llm_client",
        lambda **_kwargs: SimpleNamespace(
            get_llm=lambda: SimpleNamespace(invoke=lambda _prompt: None)
        ),
    )
    gateway, info = build_phase1_master_provider_gateway(
        profile=profile,
        run_id="final-v4-1-recanary",
        output_root=tmp_path,
        logical_call_limit=4,
        max_retries=0,
    )
    assert gateway.max_retries == 0
    assert gateway.max_calls == 4
    assert info.max_retries == 0
    assert info.max_provider_attempts == 4


def test_provider_and_model_prevent_cross_provider_cache_hits():
    common = {
        "task": "structured_claim_shadow",
        "prompt_version": "structured_adapter.claim_extraction_shadow.v1",
        "prompt_sha256": "c60f1526fd927e4593ab5913bc3c653cd2a05f6d24dc5fdf3e258a3e62128d1e",
        "input_schema_version": "comqutor.structured_claim_shadow_request.v1",
        "output_schema_version": "comqutor.structured_claim_shadow.v1",
        "input_sha256": sha256_text("same report"),
    }
    deepseek_key = build_llm_cache_key(
        **common, provider="deepseek", model="deepseek-v4-flash"
    )
    anthropic_key = build_llm_cache_key(
        **common, provider="anthropic", model="claude-sonnet-4-6"
    )
    assert deepseek_key != anthropic_key


@pytest.mark.parametrize(
    ("status_code", "reason"),
    [
        (401, "BLOCKED_ANTHROPIC_CREDENTIAL_INVALID"),
        (403, "BLOCKED_ANTHROPIC_CREDENTIAL_INVALID"),
        (404, "BLOCKED_ANTHROPIC_PROFILE_MODEL_INVALID"),
        (500, "BLOCKED_ANTHROPIC_PROVIDER_UNAVAILABLE"),
    ],
)
def test_anthropic_qualification_failure_classification(status_code, reason):
    error = type("ProviderError", (Exception,), {"status_code": status_code})()
    assert master._anthropic_qualification_blocker(error) == reason
