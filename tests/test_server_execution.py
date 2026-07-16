"""W5.1B: comqutor_alpha/server_execution.py unit tests.

Covers: real execution disabled by default, config building from server
env only (never from a client payload), the config allowlist, config
identity hashing (no secrets), analyst allowlist validation, and real
force_refresh gating.
"""

from __future__ import annotations

import copy

import pytest

from comqutor_alpha import server_execution


@pytest.fixture(autouse=True)
def _clean_real_execution_env(monkeypatch):
    for var in (
        "COMQUTOR_REAL_TRADINGAGENTS_ENABLED",
        "COMQUTOR_TA_LLM_PROVIDER",
        "COMQUTOR_TA_DEEP_THINK_MODEL",
        "COMQUTOR_TA_QUICK_THINK_MODEL",
        "COMQUTOR_TA_BACKEND_URL",
        "COMQUTOR_REAL_FORCE_REFRESH_ENABLED",
    ):
        monkeypatch.delenv(var, raising=False)


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
    assert ctx["error"] == "REAL_RUN_DISABLED"


# ---------------------------------------------------------------------------
# Config building: server env only, allowlist, deep copy
# ---------------------------------------------------------------------------


def test_enabled_with_default_config_is_valid(monkeypatch):
    # tradingagents.default_config.DEFAULT_CONFIG ships with a working
    # provider/model triplet out of the box (the same one the CLI's
    # interactive flow would use) -- enabling real execution with no
    # COMQUTOR_TA_* overrides at all is therefore a valid configuration,
    # not a missing one.
    monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "true")
    ctx = server_execution.build_server_execution_context()
    assert ctx["enabled"] is True
    assert ctx["error"] is None
    assert ctx["config"] is not None


def test_enabled_but_missing_config_is_config_invalid(monkeypatch):
    monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "true")
    import tradingagents.default_config as default_config_module

    blank_config = dict(default_config_module.DEFAULT_CONFIG)
    blank_config["llm_provider"] = ""
    blank_config["deep_think_llm"] = ""
    monkeypatch.setattr(default_config_module, "DEFAULT_CONFIG", blank_config)

    ctx = server_execution.build_server_execution_context()
    assert ctx["enabled"] is True
    assert ctx["config"] is None
    assert ctx["error"] == "REAL_RUN_CONFIG_INVALID"


def test_valid_config_from_server_env(monkeypatch):
    monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "true")
    monkeypatch.setenv("COMQUTOR_TA_LLM_PROVIDER", "openai")
    monkeypatch.setenv("COMQUTOR_TA_DEEP_THINK_MODEL", "gpt-5.4")
    monkeypatch.setenv("COMQUTOR_TA_QUICK_THINK_MODEL", "gpt-5.4-mini")

    ctx = server_execution.build_server_execution_context()
    assert ctx["enabled"] is True
    assert ctx["error"] is None
    assert ctx["config"]["llm_provider"] == "openai"
    assert ctx["config"]["deep_think_llm"] == "gpt-5.4"
    assert ctx["config"]["quick_think_llm"] == "gpt-5.4-mini"
    assert ctx["execution_identity"]["provider_identity"] == "openai"
    assert ctx["execution_identity"]["model_identity"] == "gpt-5.4:gpt-5.4-mini"


def test_backend_url_override_applied(monkeypatch):
    monkeypatch.setenv("COMQUTOR_TA_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("COMQUTOR_TA_DEEP_THINK_MODEL", "local-deep")
    monkeypatch.setenv("COMQUTOR_TA_QUICK_THINK_MODEL", "local-quick")
    monkeypatch.setenv("COMQUTOR_TA_BACKEND_URL", "http://localhost:11434/v1")

    config = server_execution.build_server_tradingagents_config()
    assert config["backend_url"] == "http://localhost:11434/v1"


def test_config_is_deep_copy_and_never_mutates_default_config(monkeypatch):
    from tradingagents.default_config import DEFAULT_CONFIG

    before = copy.deepcopy(DEFAULT_CONFIG)
    monkeypatch.setenv("COMQUTOR_TA_LLM_PROVIDER", "openai")
    monkeypatch.setenv("COMQUTOR_TA_DEEP_THINK_MODEL", "gpt-5.4")
    monkeypatch.setenv("COMQUTOR_TA_QUICK_THINK_MODEL", "gpt-5.4-mini")

    config = server_execution.build_server_tradingagents_config()
    config["llm_provider"] = "mutated-should-not-leak-back"
    config["data_vendors"]["core_stock_apis"] = "mutated-nested-should-not-leak-back"

    assert before == DEFAULT_CONFIG
    assert DEFAULT_CONFIG["llm_provider"] != "mutated-should-not-leak-back"


def test_only_allowlisted_config_keys_are_ever_overridden(monkeypatch):
    monkeypatch.setenv("COMQUTOR_TA_LLM_PROVIDER", "openai")
    monkeypatch.setenv("COMQUTOR_TA_DEEP_THINK_MODEL", "gpt-5.4")
    monkeypatch.setenv("COMQUTOR_TA_QUICK_THINK_MODEL", "gpt-5.4-mini")

    from tradingagents.default_config import DEFAULT_CONFIG

    config = server_execution.build_server_tradingagents_config()
    for key, value in config.items():
        if key in server_execution.REAL_RUN_ALLOWLISTED_CONFIG_KEYS:
            continue
        assert value == DEFAULT_CONFIG[key]


# ---------------------------------------------------------------------------
# Config identity: no secrets, no local paths, changes with config
# ---------------------------------------------------------------------------


def test_config_identity_contains_no_secret_or_path_markers(monkeypatch):
    # The full config dict legitimately contains local paths
    # (project_dir/results_dir/data_cache_dir/memory_log_path) --
    # TradingAgentsGraph needs them, and the config itself never leaves the
    # server process. What must never leak a secret or a local path is the
    # *identity* (config_identity_sha256 + provider/model labels) that flows
    # into the fingerprint and could, in principle, be logged/inspected.
    monkeypatch.setenv("COMQUTOR_TA_LLM_PROVIDER", "openai")
    monkeypatch.setenv("COMQUTOR_TA_DEEP_THINK_MODEL", "gpt-5.4")
    monkeypatch.setenv("COMQUTOR_TA_QUICK_THINK_MODEL", "gpt-5.4-mini")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-super-secret-value")

    config = server_execution.build_server_tradingagents_config()
    identity = server_execution.build_execution_identity(config)
    serialized = str(identity)
    for forbidden in ("sk-super-secret-value", "/Users/", "password", "api_key"):
        assert forbidden not in serialized
    assert len(identity["config_identity_sha256"]) == 64
    int(identity["config_identity_sha256"], 16)


def test_config_identity_payload_excludes_local_paths():
    payload_keys = set(server_execution.REAL_RUN_ALLOWLISTED_CONFIG_KEYS)
    for path_key in ("project_dir", "results_dir", "data_cache_dir", "memory_log_path"):
        assert path_key not in payload_keys


def test_provider_or_model_change_changes_config_identity(monkeypatch):
    monkeypatch.setenv("COMQUTOR_TA_LLM_PROVIDER", "openai")
    monkeypatch.setenv("COMQUTOR_TA_DEEP_THINK_MODEL", "gpt-5.4")
    monkeypatch.setenv("COMQUTOR_TA_QUICK_THINK_MODEL", "gpt-5.4-mini")
    config_a = server_execution.build_server_tradingagents_config()
    identity_a = server_execution.build_execution_identity(config_a)

    monkeypatch.setenv("COMQUTOR_TA_DEEP_THINK_MODEL", "gpt-5.5")
    config_b = server_execution.build_server_tradingagents_config()
    identity_b = server_execution.build_execution_identity(config_b)

    assert identity_a["config_identity_sha256"] != identity_b["config_identity_sha256"]
    assert identity_a["model_identity"] != identity_b["model_identity"]


def test_identical_config_produces_identical_identity(monkeypatch):
    monkeypatch.setenv("COMQUTOR_TA_LLM_PROVIDER", "openai")
    monkeypatch.setenv("COMQUTOR_TA_DEEP_THINK_MODEL", "gpt-5.4")
    monkeypatch.setenv("COMQUTOR_TA_QUICK_THINK_MODEL", "gpt-5.4-mini")
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
