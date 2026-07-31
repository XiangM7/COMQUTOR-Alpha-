"""DeepSeek non-thinking smoke profile (Track A).

A deliberately cheap, throwaway profile used only to validate that the
full pipeline (raw reports -> claims -> factors -> alphas -> relation
candidates -> graph -> activation -> conflicts -> API/UI) still works
end to end. It is completely separate from ``research_profiles.py``'s
``ACTIVE_PROFILE_ID`` -- the formal, Anthropic-only, web-submitted
research profile -- and can never be selected by an HTTP request.

Everything here lives in ``comqutor_alpha/`` on purpose: ``tradingagents/``
must never be edited for this task. DeepSeek's real "thinking" toggle is
``extra_body={"thinking": {"type": "enabled" | "disabled"}}`` on the
OpenAI-compatible chat-completions request (api-docs.deepseek.com/guides/
thinking_mode/, applies to both deepseek-v4-flash and deepseek-v4-pro).
tradingagents' ``OpenAIClient.get_llm()`` only forwards a fixed whitelist
of kwargs (``_PASSTHROUGH_KWARGS``) and does not include ``extra_body``,
so there is no way to plumb the toggle through the existing config-dict
contract without an edit there. Instead, this module defines two small
``DeepSeekChatOpenAI`` subclasses (one per thinking mode) and swaps the
provider registry's ``chat_class`` entry to one of them for the scope of
a single smoke run via ``deepseek_thinking_scope`` -- a real extension of
the client, going through the same ``_get_request_payload`` seam
``DeepSeekChatOpenAI``/``MinimaxChatOpenAI`` already use, not a string
hack. The swap is scoped (try/finally) and touches only the ``deepseek``
registry entry, so no other provider is ever affected and no run outside
the ``with`` block sees a different class.
"""

from __future__ import annotations

import copy
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

DEEPSEEK_THINKING_ENV_VAR = "TRADINGAGENTS_DEEPSEEK_THINKING"
_VALID_THINKING_MODES = ("enabled", "disabled")

# Canonical *public* analyst wire values used throughout comqutor_alpha
# (see runners.tradingagents_runner.PUBLIC_TO_INTERNAL_ANALYSTS) --
# "sentiment" is the public name for what TradingAgentsGraph internally
# calls "social".
_ALL_PUBLIC_ANALYSTS = ("market", "sentiment", "news", "fundamentals")


class DeepSeekSmokeProfileError(Exception):
    """Safe smoke-profile error: carries a stable reason code only."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True)
class DeepSeekSmokeProfile:
    """Immutable, versioned smoke-test profile. Never used by the formal
    web research profile gate (see ``research_profiles.py``) and never
    result-equivalent to it -- this exists only to validate pipeline
    plumbing cheaply, not research quality."""

    profile_id: str
    display_name: str
    llm_provider: str
    quick_think_llm: str
    deep_think_llm: str
    backend_url: str | None
    output_language: str
    max_debate_rounds: int
    max_risk_discuss_rounds: int
    temperature: float | None
    selected_analysts: tuple[str, ...]
    deepseek_thinking: str


SMOKE_PROFILE_ID = "comqutor_deepseek_smoke_v1"

# deepseek-v4-flash is DeepSeek's cheapest current model and (per
# tradingagents.llm_clients.model_catalog) explicitly serves both thinking
# and non-thinking modes, so one model covers both quick and deep tiers.
_SMOKE_PROFILE = DeepSeekSmokeProfile(
    profile_id=SMOKE_PROFILE_ID,
    display_name="COMQUTOR DeepSeek Non-Thinking Smoke v1",
    llm_provider="deepseek",
    quick_think_llm="deepseek-v4-flash",
    deep_think_llm="deepseek-v4-flash",
    backend_url=None,
    output_language="English",
    max_debate_rounds=1,
    max_risk_discuss_rounds=1,
    # 0 is in DeepSeek's documented 0-2 range and is honored in
    # non-thinking mode (thinking mode ignores temperature entirely but
    # does not error on it); this profile only ever runs non-thinking.
    temperature=0.0,
    selected_analysts=_ALL_PUBLIC_ANALYSTS,
    deepseek_thinking="disabled",
)

# The only TradingAgents DEFAULT_CONFIG keys this profile is allowed to
# override -- every entry already exists in DEFAULT_CONFIG (never a new
# tradingagents-side key; "deepseek_thinking" deliberately is NOT one of
# these, since DEFAULT_CONFIG has no such key and this module must not
# add one to tradingagents/).
SMOKE_PROFILE_CONFIG_KEYS: tuple[str, ...] = (
    "llm_provider",
    "quick_think_llm",
    "deep_think_llm",
    "backend_url",
    "output_language",
    "max_debate_rounds",
    "max_risk_discuss_rounds",
    "temperature",
)


def get_deepseek_smoke_profile() -> DeepSeekSmokeProfile:
    validate_deepseek_smoke_profile(_SMOKE_PROFILE)
    return _SMOKE_PROFILE


def validate_deepseek_smoke_profile(profile: DeepSeekSmokeProfile) -> None:
    """Raises ``DeepSeekSmokeProfileError("SMOKE_PROFILE_INVALID")`` for any
    violation of the frozen smoke-profile contract."""
    if not str(profile.profile_id or "").strip():
        raise DeepSeekSmokeProfileError("SMOKE_PROFILE_INVALID")
    if not str(profile.display_name or "").strip():
        raise DeepSeekSmokeProfileError("SMOKE_PROFILE_INVALID")
    if str(profile.llm_provider or "").strip().lower() != "deepseek":
        raise DeepSeekSmokeProfileError("SMOKE_PROFILE_INVALID")
    for model in (profile.quick_think_llm, profile.deep_think_llm):
        if not str(model or "").strip():
            raise DeepSeekSmokeProfileError("SMOKE_PROFILE_INVALID")
    if not str(profile.output_language or "").strip():
        raise DeepSeekSmokeProfileError("SMOKE_PROFILE_INVALID")
    for rounds in (profile.max_debate_rounds, profile.max_risk_discuss_rounds):
        if isinstance(rounds, bool) or not isinstance(rounds, int) or not (1 <= rounds <= 10):
            raise DeepSeekSmokeProfileError("SMOKE_PROFILE_INVALID")
    if profile.backend_url is not None and not str(profile.backend_url).strip():
        raise DeepSeekSmokeProfileError("SMOKE_PROFILE_INVALID")
    if profile.temperature is not None:
        if isinstance(profile.temperature, bool) or not isinstance(profile.temperature, (int, float)):
            raise DeepSeekSmokeProfileError("SMOKE_PROFILE_INVALID")
        if not (0.0 <= float(profile.temperature) <= 2.0):
            raise DeepSeekSmokeProfileError("SMOKE_PROFILE_INVALID")
    analysts = tuple(profile.selected_analysts or ())
    if not analysts or len(set(analysts)) != len(analysts):
        raise DeepSeekSmokeProfileError("SMOKE_PROFILE_INVALID")
    if not set(analysts).issubset(set(_ALL_PUBLIC_ANALYSTS)):
        raise DeepSeekSmokeProfileError("SMOKE_PROFILE_INVALID")
    if profile.deepseek_thinking not in _VALID_THINKING_MODES:
        raise DeepSeekSmokeProfileError("SMOKE_PROFILE_INVALID")


def build_deepseek_smoke_config(profile: DeepSeekSmokeProfile | None = None) -> dict[str, Any]:
    """Deep-copies TradingAgents' unmodified ``DEFAULT_CONFIG`` and applies
    exactly ``SMOKE_PROFILE_CONFIG_KEYS`` on top. Mirrors
    ``research_profiles.build_profile_tradingagents_config`` but for the
    DeepSeek smoke profile -- kept as a separate function so the formal
    research-profile code path is never touched by this task."""
    profile = profile or get_deepseek_smoke_profile()
    validate_deepseek_smoke_profile(profile)
    try:
        from tradingagents.default_config import DEFAULT_CONFIG

        config = copy.deepcopy(DEFAULT_CONFIG)
    except DeepSeekSmokeProfileError:
        raise
    except Exception as exc:
        raise DeepSeekSmokeProfileError("SMOKE_PROFILE_INVALID") from exc

    for key in SMOKE_PROFILE_CONFIG_KEYS:
        if key not in config:
            raise DeepSeekSmokeProfileError("SMOKE_PROFILE_INVALID")
        config[key] = getattr(profile, key)
    return config


def resolve_deepseek_thinking_value(default: str | None) -> str:
    """Resolve the effective thinking mode from an explicit default value
    plus the ``TRADINGAGENTS_DEEPSEEK_THINKING`` env override -- the shared,
    caller-agnostic core of thinking-mode resolution. Used both by the
    smoke profile (via ``resolve_deepseek_thinking_mode`` below) and by
    ``comqutor_alpha.runners.tradingagents_runner`` for the real default
    DeepSeek research profile, so the two never drift into two different
    resolution rules.

    Raises ``ValueError`` immediately for any effective value other than
    "enabled" or "disabled" -- this must fail loudly at startup/submission
    time, never silently fall back to a default (mirrors
    ``default_config._coerce``'s eager-failure style for env-var
    overrides)."""
    raw = os.environ.get(DEEPSEEK_THINKING_ENV_VAR)
    mode = default if raw is None or raw == "" else raw.strip().lower()
    if mode not in _VALID_THINKING_MODES:
        raise ValueError(
            f"Invalid {DEEPSEEK_THINKING_ENV_VAR}={mode!r}; "
            f"must be one of {_VALID_THINKING_MODES}"
        )
    return mode


def resolve_deepseek_thinking_mode(profile: DeepSeekSmokeProfile | None = None) -> str:
    """Resolve the effective thinking mode for the DeepSeek *smoke* profile:
    ``TRADINGAGENTS_DEEPSEEK_THINKING`` env var overrides the profile's own
    ``deepseek_thinking`` field. See ``resolve_deepseek_thinking_value`` for
    the shared resolution rule and its exact failure contract."""
    profile = profile or get_deepseek_smoke_profile()
    return resolve_deepseek_thinking_value(profile.deepseek_thinking)


# ---------------------------------------------------------------------------
# Thinking-mode request injection (extends DeepSeekChatOpenAI; never edits it)
# ---------------------------------------------------------------------------

def _inject_thinking(payload: dict[str, Any], mode: str) -> dict[str, Any]:
    extra_body = dict(payload.get("extra_body") or {})
    extra_body["thinking"] = {"type": mode}
    payload["extra_body"] = extra_body
    return payload


def _make_thinking_chat_class(mode: str):
    from tradingagents.llm_clients.openai_client import DeepSeekChatOpenAI

    class _DeepSeekThinkingControlled(DeepSeekChatOpenAI):
        def _get_request_payload(self, input_, *, stop=None, **kwargs):
            payload = super()._get_request_payload(input_, stop=stop, **kwargs)
            return _inject_thinking(payload, mode)

    _DeepSeekThinkingControlled.__name__ = f"DeepSeekThinking{mode.capitalize()}ChatOpenAI"
    _DeepSeekThinkingControlled.__qualname__ = _DeepSeekThinkingControlled.__name__
    return _DeepSeekThinkingControlled


# Built once per mode (not per-call) so tests and the scope manager share
# stable, importable classes rather than a fresh type on every invocation.
DeepSeekThinkingEnabledChatOpenAI = _make_thinking_chat_class("enabled")
DeepSeekThinkingDisabledChatOpenAI = _make_thinking_chat_class("disabled")

_THINKING_CHAT_CLASSES = {
    "enabled": DeepSeekThinkingEnabledChatOpenAI,
    "disabled": DeepSeekThinkingDisabledChatOpenAI,
}


@contextmanager
def deepseek_thinking_scope(mode: str) -> Iterator[None]:
    """Scope the ``deepseek`` provider-registry entry to a thinking-mode-
    controlled chat class for the duration of the ``with`` block, then
    restore the original entry. Only the ``deepseek`` entry is ever
    touched -- every other provider's registry entry, and any concurrent
    ``deepseek`` client already constructed before entry, is unaffected."""
    if mode not in _VALID_THINKING_MODES:
        raise ValueError(f"Invalid thinking mode {mode!r}; must be one of {_VALID_THINKING_MODES}")

    from tradingagents.llm_clients import openai_client as _openai_client_module

    registry = _openai_client_module.OPENAI_COMPATIBLE_PROVIDERS
    original_spec = registry["deepseek"]
    registry["deepseek"] = replace(original_spec, chat_class=_THINKING_CHAT_CLASSES[mode])
    try:
        yield
    finally:
        registry["deepseek"] = original_spec


# ---------------------------------------------------------------------------
# Status / readiness surface (no secrets)
# ---------------------------------------------------------------------------

def build_deepseek_smoke_status(profile: DeepSeekSmokeProfile | None = None) -> dict[str, Any]:
    """Non-secret status dict describing the real, resolved smoke-profile
    identity: provider, models, rounds, analysts, and thinking mode. Never
    includes the API key value -- only whether one is present."""
    profile = profile or get_deepseek_smoke_profile()
    validate_deepseek_smoke_profile(profile)
    from tradingagents.llm_clients.api_key_env import get_api_key_env

    api_key_env = get_api_key_env(profile.llm_provider) or ""
    return {
        "profile_id": profile.profile_id,
        "display_name": profile.display_name,
        "provider": profile.llm_provider,
        "quick_think_llm": profile.quick_think_llm,
        "deep_think_llm": profile.deep_think_llm,
        "base_url_source": "profile_override" if profile.backend_url else "provider_default",
        "max_debate_rounds": profile.max_debate_rounds,
        "max_risk_discuss_rounds": profile.max_risk_discuss_rounds,
        "selected_analysts": list(profile.selected_analysts),
        "temperature": profile.temperature,
        "deepseek_thinking": resolve_deepseek_thinking_mode(profile),
        "deepseek_api_key_present": bool(os.environ.get(api_key_env, "").strip()) if api_key_env else False,
    }


# ---------------------------------------------------------------------------
# Real (opt-in) smoke run entrypoint
# ---------------------------------------------------------------------------

def run_deepseek_smoke(
    ticker: str,
    analysis_date: str,
    *,
    output_root: str | Path = "outputs/runs",
    profile: DeepSeekSmokeProfile | None = None,
) -> Path:
    """Execute one real DeepSeek smoke run through the exact same
    production entrypoint (``run_original_tradingagents_research``) real
    web runs use, so it exercises the identical downstream pipeline. No
    try/except swallows a failure here and there is no alternate-provider
    code path anywhere in this function -- any DeepSeek failure (missing
    key, bad model, request error, unsupported thinking param) propagates
    to the caller unchanged. Requires explicit opt-in from the caller;
    never invoked by tests or by any offline/replay code path."""
    profile = profile or get_deepseek_smoke_profile()
    validate_deepseek_smoke_profile(profile)
    mode = resolve_deepseek_thinking_mode(profile)  # raises ValueError before any side effect

    from tradingagents.llm_clients.api_key_env import get_api_key_env

    api_key_env = get_api_key_env(profile.llm_provider)
    if api_key_env and not os.environ.get(api_key_env, "").strip():
        raise DeepSeekSmokeProfileError("DEEPSEEK_API_KEY_MISSING")

    config = build_deepseek_smoke_config(profile)
    payload = {
        "allow_real_tradingagents_run": True,
        "ticker": ticker,
        "analysis_date": analysis_date,
        "selected_analysts": list(profile.selected_analysts),
        "asset_type": "stock",
        "config": config,
    }

    from comqutor_alpha.runners.tradingagents_runner import run_original_tradingagents_research

    with deepseek_thinking_scope(mode):
        return run_original_tradingagents_research(payload, output_root=output_root)


__all__ = [
    "DEEPSEEK_THINKING_ENV_VAR",
    "SMOKE_PROFILE_ID",
    "SMOKE_PROFILE_CONFIG_KEYS",
    "DeepSeekSmokeProfile",
    "DeepSeekSmokeProfileError",
    "get_deepseek_smoke_profile",
    "validate_deepseek_smoke_profile",
    "build_deepseek_smoke_config",
    "resolve_deepseek_thinking_value",
    "resolve_deepseek_thinking_mode",
    "DeepSeekThinkingEnabledChatOpenAI",
    "DeepSeekThinkingDisabledChatOpenAI",
    "deepseek_thinking_scope",
    "build_deepseek_smoke_status",
    "run_deepseek_smoke",
]
