"""W5.1B: Server-controlled TradingAgents execution configuration.

Real (non-offline) research runs must be fully controlled by the *server*
process environment -- never by an HTTP request. This module is the only
place that:

1. Decides whether real TradingAgents execution is enabled at all
   (``COMQUTOR_REAL_TRADINGAGENTS_ENABLED``).
2. Builds the actual TradingAgents ``config`` dict a real run will use, by
   deep-copying the existing, unmodified ``tradingagents.default_config.
   DEFAULT_CONFIG`` and overriding only a small, explicit allowlist of
   non-secret keys that already exist in that default config.
3. Derives a safe, non-secret execution identity (provider/model labels
   plus a config hash) that feeds into the request fingerprint so a change
   to the server's model configuration invalidates stale completed-run
   reuse automatically -- without ever storing the config itself in
   ``research_runs``, a log line, or an HTTP response.

Nothing here reads an API key, a database URL, or any other secret --
provider SDKs keep reading their own credentials from the standard process
environment exactly as they do today; this module never touches those
variables and never copies them into the config dict it builds.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any

# Every key here must already exist in tradingagents.default_config.DEFAULT_CONFIG
# -- this module never invents a config key TradingAgentsGraph does not
# already read. Deliberately small: only the knobs a server operator needs
# to point a real run at a specific provider/model/endpoint. No vendor
# credentials, no filesystem paths, no debate/round tuning here.
REAL_RUN_ALLOWLISTED_CONFIG_KEYS: tuple[str, ...] = (
    "llm_provider",
    "deep_think_llm",
    "quick_think_llm",
    "backend_url",
)

_ENV_TO_CONFIG_KEY: dict[str, str] = {
    "COMQUTOR_TA_LLM_PROVIDER": "llm_provider",
    "COMQUTOR_TA_DEEP_THINK_MODEL": "deep_think_llm",
    "COMQUTOR_TA_QUICK_THINK_MODEL": "quick_think_llm",
    "COMQUTOR_TA_BACKEND_URL": "backend_url",
}

_BOOL_TRUE = frozenset({"true", "1", "yes", "on"})

# The real-mode analyst allowlist (W5.1B requirement #13). Matches
# research_lifecycle.DEFAULT_SELECTED_ANALYSTS's member set exactly (kept
# as an independent, explicit tuple here -- this module must not import
# research_lifecycle, to avoid a circular import back into it).
REAL_RUN_ALLOWED_ANALYSTS: frozenset[str] = frozenset({"market", "news", "fundamentals", "sentiment"})


class ServerExecutionConfigError(Exception):
    """Safe server-execution configuration error: a stable reason code only."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def _parse_bool_env(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name, "")
    if not raw.strip():
        return default
    # Fail-closed, not fail-loud: an unrecognized value (typo, stray
    # whitespace-only truthiness, etc.) must never accidentally enable real
    # execution or real force_refresh. Only an exact recognized "true" value
    # flips the default; everything else stays at the safe default.
    return raw.strip().lower() in _BOOL_TRUE


def is_real_tradingagents_enabled() -> bool:
    return _parse_bool_env("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", default=False)


def is_real_force_refresh_enabled() -> bool:
    return _parse_bool_env("COMQUTOR_REAL_FORCE_REFRESH_ENABLED", default=False)


def validate_real_selected_analysts(selected_analysts: list[str]) -> None:
    """Raises ``ServerExecutionConfigError("INVALID_ANALYST_SELECTION")`` if
    any requested analyst falls outside the formal real-mode set."""
    if not set(selected_analysts).issubset(REAL_RUN_ALLOWED_ANALYSTS):
        raise ServerExecutionConfigError("INVALID_ANALYST_SELECTION")


def resolve_real_analysis_date(analysis_date: str | None) -> str:
    """Server-UTC "today" (``YYYY-MM-DD``) when a real request omits
    ``analysis_date``. Resolved exactly once per request by the caller
    (before fingerprinting) so the same resolved value flows into both the
    fingerprint and the actual execution payload -- never resolved twice
    with a chance of drifting across a UTC midnight boundary.
    """
    text = str(analysis_date or "").strip()
    if text:
        return text
    return datetime.now(UTC).date().isoformat()


def build_server_tradingagents_config() -> dict[str, Any]:
    """Deep-copies ``DEFAULT_CONFIG`` and overrides only the allowlisted
    keys from server environment variables. Never mutates ``DEFAULT_CONFIG``
    itself. Raises ``ServerExecutionConfigError("REAL_RUN_CONFIG_INVALID")``
    if the provider/model triplet required to actually run TradingAgents is
    missing or blank.
    """
    from tradingagents.default_config import DEFAULT_CONFIG

    config = copy.deepcopy(DEFAULT_CONFIG)

    for env_var, config_key in _ENV_TO_CONFIG_KEY.items():
        if config_key not in config:
            # Defensive only: every entry in _ENV_TO_CONFIG_KEY is chosen to
            # match an existing DEFAULT_CONFIG key; this never triggers in
            # practice and never invents a new key if it somehow did.
            continue
        value = os.environ.get(env_var, "").strip()
        if value:
            config[config_key] = value

    required = ("llm_provider", "deep_think_llm", "quick_think_llm")
    if not all(str(config.get(key) or "").strip() for key in required):
        raise ServerExecutionConfigError("REAL_RUN_CONFIG_INVALID")

    return config


def _config_identity_payload(config: dict[str, Any]) -> dict[str, Any]:
    """Only the allowlisted, non-secret, result-affecting subset -- never
    the full config dict (which could otherwise carry local filesystem
    paths such as ``project_dir``/``results_dir``/``data_cache_dir``)."""
    return {key: config.get(key) for key in REAL_RUN_ALLOWLISTED_CONFIG_KEYS}


def compute_config_identity_sha256(config: dict[str, Any]) -> str:
    payload = _config_identity_payload(config)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_execution_identity(config: dict[str, Any]) -> dict[str, str]:
    """Safe, non-secret identity derived from an allowlisted config subset.

    ``config_identity_sha256`` is folded into the request fingerprint (see
    research_lifecycle.build_research_request_identity's
    ``server_execution_identity`` parameter) so a server-side model/provider
    change automatically invalidates stale completed-run reuse for real
    requests, without a new database column.
    """
    provider = str(config.get("llm_provider") or "").strip()
    deep_model = str(config.get("deep_think_llm") or "").strip()
    quick_model = str(config.get("quick_think_llm") or "").strip()
    return {
        "provider_identity": provider,
        "model_identity": f"{deep_model}:{quick_model}",
        "config_identity_sha256": compute_config_identity_sha256(config),
    }


def build_server_execution_context() -> dict[str, Any]:
    """Single entrypoint: resolves whether/how a real run may proceed.

    Returns a dict with:
      - ``enabled``: whether ``COMQUTOR_REAL_TRADINGAGENTS_ENABLED`` is true.
      - ``config``: the server-side TradingAgents config (``None`` unless
        enabled and valid).
      - ``execution_identity``: ``{provider_identity, model_identity,
        config_identity_sha256}`` (``None`` unless enabled and valid).
      - ``error``: ``None``, ``"REAL_RUN_DISABLED"``, or
        ``"REAL_RUN_CONFIG_INVALID"``.

    Never raises -- every failure mode is reported through ``error``.
    """
    if not is_real_tradingagents_enabled():
        return {"enabled": False, "config": None, "execution_identity": None, "error": "REAL_RUN_DISABLED"}

    try:
        config = build_server_tradingagents_config()
    except ServerExecutionConfigError as exc:
        return {"enabled": True, "config": None, "execution_identity": None, "error": exc.reason_code}

    return {
        "enabled": True,
        "config": config,
        "execution_identity": build_execution_identity(config),
        "error": None,
    }


__all__ = [
    "REAL_RUN_ALLOWLISTED_CONFIG_KEYS",
    "REAL_RUN_ALLOWED_ANALYSTS",
    "ServerExecutionConfigError",
    "is_real_tradingagents_enabled",
    "is_real_force_refresh_enabled",
    "validate_real_selected_analysts",
    "resolve_real_analysis_date",
    "build_server_tradingagents_config",
    "compute_config_identity_sha256",
    "build_execution_identity",
    "build_server_execution_context",
]
