"""Shared pytest fixtures that prevent CI hangs when API keys are absent."""

import os
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# .env-leak environment isolation (Gate 0, Activation v2 sprint; extended
# 2026-09-26 for the Data Sanity network leak below).
#
# ``import tradingagents`` runs load_dotenv() as an import side effect, which
# injects COMQUTOR_DATABASE_URL / COMQUTOR_TEST_DATABASE_URL / COMQUTOR_ENV /
# COMQUTOR_DATA_SANITY_ENABLED from a developer's local .env into the test
# process -- silently defeating ``env -u ...`` shell isolation and pointing
# "offline" tests at a real database, or (COMQUTOR_DATA_SANITY_ENABLED=true
# in .env) making comqutor_alpha.data_sanity.pipeline.is_data_sanity_enabled()
# return True inside every test that calls comqutor_alpha.api.routes_research
# .run_research_request -- which unconditionally runs run_data_sanity_stage,
# which then genuinely calls YFinanceMarketDataProvider.get_history_rows and
# makes a REAL HTTPS request to Yahoo Finance (confirmed reproduced: see
# tests/structured_output_shadow/conftest.py). Force load_dotenv's side
# effect to happen exactly once, right now, and then restore these four
# variables to their pre-import (shell-provided) state: a value the shell
# explicitly exported survives; a value injected only by .env is removed.
# Because tradingagents is now cached in sys.modules, no later import can
# re-inject them mid-suite.
# ---------------------------------------------------------------------------

_DOTENV_LEAK_ISOLATION_VARS = (
    "COMQUTOR_DATABASE_URL",
    "COMQUTOR_TEST_DATABASE_URL",
    "COMQUTOR_ENV",
    "COMQUTOR_DATA_SANITY_ENABLED",
)
_SHELL_PROVIDED_DOTENV_LEAK_ENV = {
    name: os.environ[name] for name in _DOTENV_LEAK_ISOLATION_VARS if name in os.environ
}

import tradingagents  # noqa: E402,F401  -- deliberate: trigger load_dotenv now

for _name in _DOTENV_LEAK_ISOLATION_VARS:
    if _name in _SHELL_PROVIDED_DOTENV_LEAK_ENV:
        os.environ[_name] = _SHELL_PROVIDED_DOTENV_LEAK_ENV[_name]
    else:
        os.environ.pop(_name, None)


@pytest.fixture(autouse=True)
def _isolate_database_env(request, monkeypatch):
    """Non-integration tests must never see a database environment variable,
    and no test ever sees a .env-leaked Data Sanity enable flag.

    Integration tests keep COMQUTOR_TEST_DATABASE_URL (which they are
    required to read explicitly) but still never see COMQUTOR_DATABASE_URL,
    COMQUTOR_ENV, or COMQUTOR_DATA_SANITY_ENABLED.
    """
    monkeypatch.delenv("COMQUTOR_DATABASE_URL", raising=False)
    monkeypatch.delenv("COMQUTOR_ENV", raising=False)
    monkeypatch.delenv("COMQUTOR_DATA_SANITY_ENABLED", raising=False)
    if request.node.get_closest_marker("integration") is None:
        monkeypatch.delenv("COMQUTOR_TEST_DATABASE_URL", raising=False)


def pytest_configure(config):
    for marker in ("unit", "integration", "smoke"):
        config.addinivalue_line("markers", f"{marker}: {marker}-level tests")


_API_KEY_ENV_VARS = (
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "ANTHROPIC_API_KEY",
    "XAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "DASHSCOPE_API_KEY",
    "DASHSCOPE_CN_API_KEY",
    "ZHIPU_API_KEY",
    "ZHIPU_CN_API_KEY",
    "MINIMAX_API_KEY",
    "MINIMAX_CN_API_KEY",
    "OPENROUTER_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "ALPHA_VANTAGE_API_KEY",
)


@pytest.fixture(autouse=True)
def _dummy_api_keys(monkeypatch):
    for env_var in _API_KEY_ENV_VARS:
        # `or` not a .get default: an env var present but empty (e.g. a key left
        # blank in a .env copied from .env.example) must still get the placeholder.
        monkeypatch.setenv(env_var, os.environ.get(env_var) or "placeholder")


@pytest.fixture(autouse=True)
def _isolate_config():
    """Reset the global dataflows config before and after each test.

    ``set_config`` merges (it never clears keys absent from the override), so a
    test that sets e.g. ``tool_vendors`` would otherwise leak into later tests
    and make routing behavior order-dependent. Replace the global outright so
    every test starts from a clean DEFAULT_CONFIG.
    """
    import copy

    import tradingagents.dataflows.config as config_module
    import tradingagents.default_config as default_config

    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)
    yield
    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)


@pytest.fixture()
def mock_llm_client():
    client = MagicMock()
    client.get_llm.return_value = MagicMock()
    with patch(
        "tradingagents.llm_clients.factory.create_llm_client",
        return_value=client,
    ):
        yield client
