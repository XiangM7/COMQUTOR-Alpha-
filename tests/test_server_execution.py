"""W5.1B/W7: comqutor_alpha/server_execution.py unit tests.

Covers: real execution disabled by default, the fixed-profile config path
(never from a client payload, never from a per-request env override), the
Anthropic credential *presence* gate (value never read/logged/returned),
execution-identity hashing (no secrets), analyst allowlist validation, and
real force_refresh gating.
"""

from __future__ import annotations

import copy

import pytest

from comqutor_alpha import research_profiles, server_execution


@pytest.fixture(autouse=True)
def _clean_real_execution_env(monkeypatch):
    for var in (
        "COMQUTOR_REAL_TRADINGAGENTS_ENABLED",
        "COMQUTOR_REAL_FORCE_REFRESH_ENABLED",
    ):
        monkeypatch.delenv(var, raising=False)
    # conftest's autouse fixture guarantees ANTHROPIC_API_KEY is set to a
    # placeholder; tests exercising the missing-credential path delete it
    # explicitly themselves.


# ---------------------------------------------------------------------------
# Enabled/disabled defaults
# ---------------------------------------------------------------------------


def test_real_execution_disabled_by_default():
    assert server_execution.is_real_tradingagents_enabled() is False


def test_real_force_refresh_disabled_by_default():
    assert server_execution.is_real_force_refresh_enabled() is False


def test_real_execution_enabled_requires_exact_true_value(monkeypatch):
    monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "yes-please")
    assert server_execution.is_real_tradingagents_enabled() is False


@pytest.mark.parametrize("value", ["true", "True", "1", "yes", "on"])
def test_real_execution_enabled_recognizes_true_values(monkeypatch, value):
    monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", value)
    assert server_execution.is_real_tradingagents_enabled() is True


def test_build_server_execution_context_disabled_by_default():
    ctx = server_execution.build_server_execution_context()
    assert ctx["enabled"] is False
    assert ctx["config"] is None
    assert ctx["execution_identity"] is None
    assert ctx["profile_id"] is None
    assert ctx["error"] == "REAL_RUN_DISABLED"


def test_disabled_never_reports_a_credential_error(monkeypatch):
    # Deliberately disabled AND no credential present: the error must stay
    # REAL_RUN_DISABLED -- never misreported as a missing-key problem.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ctx = server_execution.build_server_execution_context()
    assert ctx["error"] == "REAL_RUN_DISABLED"


# ---------------------------------------------------------------------------
# Fixed-profile config building: server-only, deep copy, no env override
# ---------------------------------------------------------------------------


def test_enabled_context_uses_fixed_profile_config(monkeypatch):
    monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "true")
    ctx = server_execution.build_server_execution_context()
    assert ctx["enabled"] is True
    assert ctx["error"] is None
    assert ctx["config"]["llm_provider"] == "anthropic"
    assert ctx["config"]["deep_think_llm"] == "claude-sonnet-4-6"
    assert ctx["config"]["quick_think_llm"] == "claude-sonnet-4-6"
    assert ctx["config"]["output_language"] == "English"
    assert ctx["config"]["max_debate_rounds"] == 3
    assert ctx["config"]["max_risk_discuss_rounds"] == 3
    assert ctx["profile_id"] == research_profiles.ACTIVE_PROFILE_ID
    assert ctx["execution_identity"]["provider_identity"] == "anthropic"
    assert ctx["execution_identity"]["model_identity"] == "claude-sonnet-4-6:claude-sonnet-4-6"
    assert ctx["execution_identity"]["profile_id"] == research_profiles.ACTIVE_PROFILE_ID


def test_backend_url_uses_provider_default_endpoint_resolution():
    # backend_url=None is TradingAgents' own "use the provider's official
    # endpoint" contract -- never sourced from an HTTP request or a
    # per-request env override.
    config = server_execution.build_server_tradingagents_config()
    assert config["backend_url"] is None


def test_config_is_deep_copy_and_never_mutates_default_config():
    from tradingagents.default_config import DEFAULT_CONFIG

    before = copy.deepcopy(DEFAULT_CONFIG)
    config = server_execution.build_server_tradingagents_config()
    config["llm_provider"] = "mutated-should-not-leak-back"
    config["data_vendors"]["core_stock_apis"] = "mutated-nested-should-not-leak-back"

    assert before == DEFAULT_CONFIG
    assert DEFAULT_CONFIG["llm_provider"] != "mutated-should-not-leak-back"


def test_only_profile_keys_are_ever_overridden():
    from tradingagents.default_config import DEFAULT_CONFIG

    config = server_execution.build_server_tradingagents_config()
    for key, value in config.items():
        if key in research_profiles.PROFILE_CONFIG_KEYS:
            continue
        assert value == DEFAULT_CONFIG[key]


# ---------------------------------------------------------------------------
# Anthropic credential presence gate (presence only -- never the value)
# ---------------------------------------------------------------------------


def test_credential_present_with_placeholder():
    assert server_execution.is_anthropic_credential_present() is True


def test_credential_missing_when_unset(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert server_execution.is_anthropic_credential_present() is False


def test_credential_blank_counts_as_missing(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")
    assert server_execution.is_anthropic_credential_present() is False


def test_enabled_without_credential_fails_closed_before_any_claim(monkeypatch):
    monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ctx = server_execution.build_server_execution_context()
    assert ctx["enabled"] is True
    assert ctx["config"] is None
    assert ctx["error"] == "REAL_RUN_CREDENTIAL_MISSING"
    # Fingerprint identity stays available (a credential is never part of
    # the fingerprint), so cached completed runs remain servable.
    assert ctx["execution_identity"] is not None


def test_credential_value_never_appears_in_context(monkeypatch):
    secret_value = "test-credential-marker-never-leaked"
    monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret_value)
    ctx = server_execution.build_server_execution_context()
    serialized = str(ctx)
    assert secret_value not in serialized


# ---------------------------------------------------------------------------
# Execution identity: no secrets, no local paths, changes with profile
# ---------------------------------------------------------------------------


def test_execution_identity_contains_no_secret_or_path_markers(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-super-secret-value")

    config = server_execution.build_server_tradingagents_config()
    identity = server_execution.build_execution_identity(config)
    serialized = str(identity)
    for forbidden in ("sk-super-secret-value", "/Users/", "password", "api_key"):
        assert forbidden not in serialized
    assert len(identity["config_identity_sha256"]) == 64
    int(identity["config_identity_sha256"], 16)


def test_execution_identity_carries_full_profile_identity():
    config = server_execution.build_server_tradingagents_config()
    identity = server_execution.build_execution_identity(config)
    assert identity["profile_id"] == research_profiles.ACTIVE_PROFILE_ID
    assert identity["profile_identity"] == research_profiles.build_profile_identity()
    for key in research_profiles.PROFILE_CONFIG_KEYS:
        assert key in identity["profile_identity"]


def test_profile_identity_excludes_local_paths():
    identity = research_profiles.build_profile_identity()
    for path_key in ("project_dir", "results_dir", "data_cache_dir", "memory_log_path"):
        assert path_key not in identity


def test_identical_profile_produces_identical_identity():
    config_a = server_execution.build_server_tradingagents_config()
    config_b = server_execution.build_server_tradingagents_config()
    assert server_execution.build_execution_identity(config_a) == server_execution.build_execution_identity(config_b)


# ---------------------------------------------------------------------------
# Real-mode analyst allowlist
# ---------------------------------------------------------------------------


def test_valid_real_analyst_selection_passes():
    server_execution.validate_real_selected_analysts(["market", "news"])  # no raise


def test_invalid_real_analyst_selection_rejected():
    with pytest.raises(server_execution.ServerExecutionConfigError) as exc_info:
        server_execution.validate_real_selected_analysts(["market", "not_a_real_analyst"])
    assert exc_info.value.reason_code == "INVALID_ANALYST_SELECTION"


def test_internal_social_is_not_a_valid_public_analyst():
    # "social" is TradingAgents' internal wire key for the public
    # "sentiment" analyst -- it must never be accepted from a client.
    with pytest.raises(server_execution.ServerExecutionConfigError):
        server_execution.validate_real_selected_analysts(["social"])


def test_empty_real_analyst_selection_passes():
    server_execution.validate_real_selected_analysts([])  # subset of empty set trivially holds


# ---------------------------------------------------------------------------
# Real analysis_date resolution
# ---------------------------------------------------------------------------


def test_resolve_real_analysis_date_passthrough_when_given():
    assert server_execution.resolve_real_analysis_date("2026-06-30") == "2026-06-30"


def test_resolve_real_analysis_date_resolves_server_utc_today_when_omitted():
    from datetime import UTC, datetime

    resolved = server_execution.resolve_real_analysis_date(None)
    assert resolved == datetime.now(UTC).date().isoformat()


def test_resolve_real_analysis_date_treats_blank_as_omitted():
    assert server_execution.resolve_real_analysis_date("   ") != "   "
