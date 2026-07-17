"""W5.1B/W7: Server-controlled TradingAgents execution configuration.

Real (non-offline) research runs must be fully controlled by the *server*
process environment -- never by an HTTP request. This module is the only
place that:

1. Decides whether real TradingAgents execution is enabled at all
   (``COMQUTOR_REAL_TRADINGAGENTS_ENABLED``).
2. Builds the actual TradingAgents ``config`` dict a real run will use, by
   applying the fixed, versioned server Research Profile (see
   ``comqutor_alpha.research_profiles``) on top of the existing, unmodified
   ``tradingagents.default_config.DEFAULT_CONFIG``. No HTTP field and no
   per-request input can influence this config.
3. Derives a safe, non-secret execution identity (provider/model labels,
   the profile id, and the full non-secret profile identity) that feeds
   into the request fingerprint so a profile/model change invalidates stale
   completed-run reuse automatically -- without ever storing the config
   itself in ``research_runs``, a log line, or an HTTP response.
4. Checks that the Anthropic credential is *present* in the server process
   environment before a real run may start -- presence only; the value is
   never read into a config dict, never logged, never returned.

Nothing here reads an API key *value*, a database URL, or any other secret
-- provider SDKs keep reading their own credentials from the standard
process environment exactly as they do today; this module never copies
those variables into the config dict it builds.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

from comqutor_alpha.research_profiles import (
    ResearchProfileError,
    build_profile_identity,
    build_profile_tradingagents_config,
    compute_profile_identity_sha256,
    get_active_research_profile,
)

logger = logging.getLogger(__name__)

# Name of the environment variable holding the Anthropic credential. Only
# its *presence* is ever checked here -- the value itself is read exclusively
# by the provider SDK inside TradingAgents.
ANTHROPIC_API_KEY_ENV = "ANTHROPIC_API_KEY"

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


def resolve_asset_type(ticker: str) -> str:
    """Resolve one canonical ticker through TradingAgents' CLI classifier."""
    try:
        from cli.utils import detect_asset_type

        return detect_asset_type(ticker).value
    except Exception as exc:
        raise ServerExecutionConfigError("INVALID_TICKER") from exc


def validate_real_selected_analysts(
    selected_analysts: list[str],
    *,
    asset_type: str = "stock",
) -> None:
    """Raises ``ServerExecutionConfigError("INVALID_ANALYST_SELECTION")`` if
    any requested analyst falls outside the formal real-mode set or the CLI's
    analyst set for the resolved asset type."""
    if not selected_analysts or not set(selected_analysts).issubset(REAL_RUN_ALLOWED_ANALYSTS):
        raise ServerExecutionConfigError("INVALID_ANALYST_SELECTION")

    try:
        from cli.models import AnalystType, AssetType
        from cli.utils import filter_analysts_for_asset_type

        public_to_cli = {
            "market": AnalystType.MARKET,
            "sentiment": AnalystType.SOCIAL,
            "news": AnalystType.NEWS,
            "fundamentals": AnalystType.FUNDAMENTALS,
        }
        selected_cli = [public_to_cli[name] for name in selected_analysts]
        allowed_cli = filter_analysts_for_asset_type(selected_cli, AssetType(asset_type))
    except (KeyError, ValueError) as exc:
        raise ServerExecutionConfigError("INVALID_ANALYST_SELECTION") from exc
    if len(allowed_cli) != len(selected_cli):
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


def is_anthropic_credential_present() -> bool:
    """Presence-only check of ``ANTHROPIC_API_KEY`` in the server process
    environment. The value is never returned, stored, logged, hashed, or
    copied anywhere -- only whether a non-blank value exists."""
    return bool(os.environ.get(ANTHROPIC_API_KEY_ENV, "").strip())


def build_server_tradingagents_config() -> dict[str, Any]:
    """The TradingAgents config for a real run: the fixed server Research
    Profile applied on top of the unmodified ``DEFAULT_CONFIG`` (see
    ``research_profiles.build_profile_tradingagents_config``). Never reads
    an HTTP payload and never reads a credential.

    Raises ``ServerExecutionConfigError("REAL_RUN_CONFIG_INVALID")`` for
    *any* construction failure -- including a native TradingAgents
    config-import error (whose message could echo a ``TRADINGAGENTS_*`` env
    var value) -- so callers only ever see one stable reason code. Only the
    exception's type name is ever logged, at any log level.
    """
    try:
        return build_profile_tradingagents_config(get_active_research_profile())
    except (ResearchProfileError, ServerExecutionConfigError) as exc:
        logger.warning(
            "server-side TradingAgents config construction failed (exc_type=%s)",
            type(exc).__name__,
        )
        raise ServerExecutionConfigError("REAL_RUN_CONFIG_INVALID") from exc
    except Exception as exc:
        # Never the raw exception message/repr/traceback -- at *any* log
        # level, including DEBUG. Only the exception's type name, ever.
        logger.warning(
            "server-side TradingAgents config construction failed (exc_type=%s)",
            type(exc).__name__,
        )
        logger.debug(
            "server-side TradingAgents config construction failed (exc_type=%s)",
            type(exc).__name__,
        )
        raise ServerExecutionConfigError("REAL_RUN_CONFIG_INVALID") from exc


def build_execution_identity(config: dict[str, Any]) -> dict[str, Any]:
    """Safe, non-secret identity for the fingerprint: provider/model labels,
    the fixed profile's id, and the *full* non-secret profile identity
    (models, rounds, language, endpoint mode). Folding the whole profile
    identity in -- never just a hash of part of it -- means any
    result-affecting profile change invalidates stale completed-run reuse
    for real requests, without a new database column. Contains no
    credential, no filesystem path, no environment value."""
    profile = get_active_research_profile()
    provider = str(config.get("llm_provider") or "").strip()
    deep_model = str(config.get("deep_think_llm") or "").strip()
    quick_model = str(config.get("quick_think_llm") or "").strip()
    return {
        "provider_identity": provider,
        "model_identity": f"{deep_model}:{quick_model}",
        "config_identity_sha256": compute_profile_identity_sha256(profile),
        "profile_id": profile.profile_id,
        "profile_identity": build_profile_identity(profile),
    }


def build_server_execution_context() -> dict[str, Any]:
    """Single entrypoint: resolves whether/how a real run may proceed.

    Returns a dict with:
      - ``enabled``: whether ``COMQUTOR_REAL_TRADINGAGENTS_ENABLED`` is true.
      - ``config``: the server-side TradingAgents config (``None`` unless
        enabled and valid).
      - ``execution_identity``: ``{provider_identity, model_identity,
        config_identity_sha256, profile_id, profile_identity}`` (``None``
        unless enabled and valid).
      - ``profile_id``: the fixed profile's id (``None`` unless enabled and
        the profile itself is valid).
      - ``error``: ``None``, ``"REAL_RUN_DISABLED"``,
        ``"REAL_RUN_CONFIG_INVALID"``, or ``"REAL_RUN_CREDENTIAL_MISSING"``.

    Never raises -- every failure mode is reported through ``error``. When
    real execution is merely *disabled*, the credential is never even
    checked, so a disabled server is always reported as disabled -- never
    misreported as a credential problem.
    """
    if not is_real_tradingagents_enabled():
        return {
            "enabled": False,
            "config": None,
            "execution_identity": None,
            "profile_id": None,
            "error": "REAL_RUN_DISABLED",
        }

    try:
        config = build_server_tradingagents_config()
        execution_identity = build_execution_identity(config)
    except ServerExecutionConfigError as exc:
        return {
            "enabled": True,
            "config": None,
            "execution_identity": None,
            "profile_id": None,
            "error": exc.reason_code,
        }
    except Exception as exc:
        logger.warning(
            "server execution context construction failed (exc_type=%s)", type(exc).__name__
        )
        logger.debug(
            "server execution context construction failed (exc_type=%s)", type(exc).__name__
        )
        return {
            "enabled": True,
            "config": None,
            "execution_identity": None,
            "profile_id": None,
            "error": "REAL_RUN_CONFIG_INVALID",
        }

    profile_id = str(execution_identity.get("profile_id") or "")

    if not is_anthropic_credential_present():
        # Enabled with a valid profile but no credential in the server
        # environment: a real run could never start, so this must fail
        # closed *before* any research_runs row is ever claimed. The
        # identity is still returned so fingerprints stay stable -- a
        # credential is never part of the fingerprint.
        return {
            "enabled": True,
            "config": None,
            "execution_identity": execution_identity,
            "profile_id": profile_id,
            "error": "REAL_RUN_CREDENTIAL_MISSING",
        }

    return {
        "enabled": True,
        "config": config,
        "execution_identity": execution_identity,
        "profile_id": profile_id,
        "error": None,
    }


__all__ = [
    "ANTHROPIC_API_KEY_ENV",
    "REAL_RUN_ALLOWED_ANALYSTS",
    "ServerExecutionConfigError",
    "is_real_tradingagents_enabled",
    "is_real_force_refresh_enabled",
    "is_anthropic_credential_present",
    "resolve_asset_type",
    "validate_real_selected_analysts",
    "resolve_real_analysis_date",
    "build_server_tradingagents_config",
    "build_execution_identity",
    "build_server_execution_context",
]
