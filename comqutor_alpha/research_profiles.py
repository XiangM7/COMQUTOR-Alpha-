"""Fixed, versioned server-side Research Profiles.

A Research Profile is the *only* source of the TradingAgents model/provider/
research-depth configuration a real (non-offline) web-submitted run may use.
Ordinary users never choose (or even see) any of it: an HTTP request carries
only ticker/analysis_date/selected_analysts, and nothing a client sends can
override a profile field (the request model simply has no such fields, and
extra JSON keys are ignored by the API layer).

The profile is immutable and versioned: changing any result-affecting field
requires a new ``profile_id``, and the full non-secret profile identity is
folded into the request fingerprint (see ``research_lifecycle.
build_research_request_identity``) so a profile change can never cause an
old completed run to be wrongly reused.

There is a small, fixed registry of profiles (``_PROFILE_REGISTRY``), not an
open-ended selection: ``get_active_research_profile()`` returns the single
*default* profile every request with no explicit ``profile_id`` resolves to
(DeepSeek, as of ``comqutor_deepseek_default_v1``); ``get_research_profile
(profile_id)`` resolves any other registered profile (e.g. the Anthropic
profile) for callers that explicitly ask for it by id -- there is still no
HTTP-exposed ``profile_id`` field, so this is for internal/ops/test use, not
a public API surface.

Nothing here reads, stores, logs, or returns a credential. Each profile's
provider API key stays exclusively in the server process environment and is
read only by the provider SDK itself; ``server_execution.
is_provider_credential_present`` checks *presence* without ever exposing the
value.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any

## Research Profile
class ResearchProfileError(Exception):
    """Safe profile error: carries a stable reason code only."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True)
class ResearchProfile:
    """Immutable, versioned bundle of every server-controlled,
    result-affecting TradingAgents setting a real web run uses. All fields
    are non-secret by construction -- a credential must never be added
    here."""

    profile_id: str
    display_name: str
    llm_provider: str
    quick_think_llm: str
    deep_think_llm: str
    # None means "use TradingAgents' own provider-default endpoint
    # resolution" (DEFAULT_CONFIG's backend_url=None contract) -- for
    # Anthropic that is the official Anthropic API endpoint. Never sourced
    # from an HTTP request.
    backend_url: str | None
    output_language: str
    max_debate_rounds: int
    max_risk_discuss_rounds: int
    # None means "no override -- use TradingAgents' own provider default"
    # (DEFAULT_CONFIG's temperature=None contract), matching the Anthropic
    # profile's pre-existing (implicit) behavior.
    temperature: float | None = None
    # Non-tradingagents-config field: only meaningful when llm_provider ==
    # "deepseek" (validated below). Never written into DEFAULT_CONFIG/
    # PROFILE_CONFIG_KEYS -- tradingagents has no such key -- but carried on
    # the built config dict by server_execution.build_server_tradingagents_
    # config so comqutor_alpha.runners.tradingagents_runner can scope the
    # real DeepSeek request through comqutor_alpha.llm.deepseek_smoke's
    # thinking-mode injection at the one place a real request is made.
    deepseek_thinking: str | None = None


DEEPSEEK_DEFAULT_PROFILE_ID = "comqutor_deepseek_default_v1"
ANTHROPIC_PROFILE_ID = "comqutor_anthropic_medium_sonnet46_v1"

# The project-canonical cheapest DeepSeek model, confirmed against the real
# DeepSeek provider registry (tradingagents.llm_clients.model_catalog) to
# support both thinking and non-thinking modes -- see the Track A DeepSeek
# smoke profile sprint report for the full provider-registry audit trail.
_DEEPSEEK_DEFAULT_PROFILE = ResearchProfile(
    profile_id=DEEPSEEK_DEFAULT_PROFILE_ID,
    display_name="DeepSeek Default Research",
    llm_provider="deepseek",
    quick_think_llm="deepseek-v4-flash",
    deep_think_llm="deepseek-v4-flash",
    backend_url=None,
    output_language="English",
    max_debate_rounds=1,
    max_risk_discuss_rounds=1,
    temperature=0.0,
    deepseek_thinking="disabled",
)

_ANTHROPIC_PROFILE = ResearchProfile(
    profile_id=ANTHROPIC_PROFILE_ID,
    display_name="COMQUTOR Anthropic Medium v1",
    llm_provider="anthropic",
    quick_think_llm="claude-sonnet-4-6",
    deep_think_llm="claude-sonnet-4-6",
    backend_url=None,
    output_language="English",
    max_debate_rounds=3,
    max_risk_discuss_rounds=3,
    temperature=None,
    deepseek_thinking=None,
)

# The default every request with no explicit profile_id resolves to.
ACTIVE_PROFILE_ID = DEEPSEEK_DEFAULT_PROFILE_ID

# Fixed, small registry -- not an open-ended selection. Every profile here
# must pass validate_research_profile(); adding a profile means adding a
# new, reviewed entry, never accepting one from a request.
_PROFILE_REGISTRY: dict[str, ResearchProfile] = {
    DEEPSEEK_DEFAULT_PROFILE_ID: _DEEPSEEK_DEFAULT_PROFILE,
    ANTHROPIC_PROFILE_ID: _ANTHROPIC_PROFILE,
}

# Providers a registered profile may declare. Not an arbitrary-provider
# allowance -- every profile in _PROFILE_REGISTRY is reviewed/fixed, this
# only bounds which providers *those* profiles may name.
_VALID_PROFILE_PROVIDERS = frozenset({"deepseek", "anthropic"})
_VALID_DEEPSEEK_THINKING_VALUES = frozenset({"enabled", "disabled"})

# The only config keys a profile is allowed to override on top of
# TradingAgents' DEFAULT_CONFIG. Every key must already exist in
# DEFAULT_CONFIG -- a profile never invents a config key TradingAgentsGraph
# does not already read, and never touches filesystem paths, vendor
# settings, or provider credentials.
PROFILE_CONFIG_KEYS: tuple[str, ...] = (
    "llm_provider",
    "quick_think_llm",
    "deep_think_llm",
    "backend_url",
    "output_language",
    "max_debate_rounds",
    "max_risk_discuss_rounds",
    "temperature",
)


def get_active_research_profile() -> ResearchProfile:
    """The default profile every real web-submitted run uses when no
    explicit profile_id is resolved (DeepSeek, comqutor_deepseek_default_v1).
    Validated on every call so a future edit that breaks an invariant fails
    loudly at the readiness/submission gate instead of mid-run."""
    validate_research_profile(_DEEPSEEK_DEFAULT_PROFILE)
    return _DEEPSEEK_DEFAULT_PROFILE


def get_research_profile(profile_id: str | None = None) -> ResearchProfile:
    """Resolve one profile from the fixed registry. ``None``/empty resolves
    to the default (DeepSeek) -- the same profile ``get_active_research_
    profile()`` returns. A non-empty, unregistered id raises
    ``ResearchProfileError("RESEARCH_PROFILE_UNKNOWN")``: there is no
    free-form profile selection, only the fixed, versioned registry."""
    if not profile_id:
        return get_active_research_profile()
    profile = _PROFILE_REGISTRY.get(profile_id)
    if profile is None:
        raise ResearchProfileError("RESEARCH_PROFILE_UNKNOWN")
    validate_research_profile(profile)
    return profile


def validate_research_profile(profile: ResearchProfile) -> None:
    """Raises ``ResearchProfileError("RESEARCH_PROFILE_INVALID")`` if any
    field violates the frozen profile contract."""
    if not str(profile.profile_id or "").strip():
        raise ResearchProfileError("RESEARCH_PROFILE_INVALID")
    if not str(profile.display_name or "").strip():
        raise ResearchProfileError("RESEARCH_PROFILE_INVALID")
    provider = str(profile.llm_provider or "").strip().lower()
    if provider not in _VALID_PROFILE_PROVIDERS:
        raise ResearchProfileError("RESEARCH_PROFILE_INVALID")
    for model in (profile.quick_think_llm, profile.deep_think_llm):
        if not str(model or "").strip():
            raise ResearchProfileError("RESEARCH_PROFILE_INVALID")
    if not str(profile.output_language or "").strip():
        raise ResearchProfileError("RESEARCH_PROFILE_INVALID")
    for rounds in (profile.max_debate_rounds, profile.max_risk_discuss_rounds):
        if isinstance(rounds, bool) or not isinstance(rounds, int) or not (1 <= rounds <= 10):
            raise ResearchProfileError("RESEARCH_PROFILE_INVALID")
    if profile.backend_url is not None and not str(profile.backend_url).strip():
        raise ResearchProfileError("RESEARCH_PROFILE_INVALID")
    if profile.temperature is not None:
        if isinstance(profile.temperature, bool) or not isinstance(profile.temperature, (int, float)):
            raise ResearchProfileError("RESEARCH_PROFILE_INVALID")
        if not (0.0 <= float(profile.temperature) <= 2.0):
            raise ResearchProfileError("RESEARCH_PROFILE_INVALID")
    if provider == "deepseek":
        if profile.deepseek_thinking not in _VALID_DEEPSEEK_THINKING_VALUES:
            raise ResearchProfileError("RESEARCH_PROFILE_INVALID")
    elif profile.deepseek_thinking is not None:
        # A non-DeepSeek profile must never carry a DeepSeek-specific field.
        raise ResearchProfileError("RESEARCH_PROFILE_INVALID")

## Build TradingAgents Config from Profile
def build_profile_tradingagents_config(profile: ResearchProfile | None = None) -> dict[str, Any]:
    """Deep-copies TradingAgents' unmodified ``DEFAULT_CONFIG`` and applies
    exactly the profile's ``PROFILE_CONFIG_KEYS`` on top. Never reads an
    HTTP payload, never reads a credential, never mutates DEFAULT_CONFIG.

    Raises ``ResearchProfileError("RESEARCH_PROFILE_INVALID")`` for any
    failure -- including a native TradingAgents config-import error -- so a
    caller only ever sees one stable reason code, never a raw exception
    message that could echo an environment variable.
    """
    profile = profile or get_active_research_profile()
    validate_research_profile(profile)
    try:
        from tradingagents.default_config import DEFAULT_CONFIG

        config = copy.deepcopy(DEFAULT_CONFIG)
    except ResearchProfileError:
        raise
    except Exception as exc:
        raise ResearchProfileError("RESEARCH_PROFILE_INVALID") from exc

    for key in PROFILE_CONFIG_KEYS:
        if key not in config:
            # Defensive only: every PROFILE_CONFIG_KEYS entry matches an
            # existing DEFAULT_CONFIG key; never invents a new key.
            raise ResearchProfileError("RESEARCH_PROFILE_INVALID")
        config[key] = getattr(profile, key)
    return config

## Build Profile Identity
def build_profile_identity(profile: ResearchProfile | None = None) -> dict[str, Any]:
    """The full non-secret, result-affecting identity of a profile --
    ``profile_id`` plus every ``PROFILE_CONFIG_KEYS`` value plus
    ``deepseek_thinking`` (result-affecting for DeepSeek profiles, but not a
    tradingagents config key, so it is folded in explicitly here rather than
    via ``PROFILE_CONFIG_KEYS``). This whole dict is folded into the request
    fingerprint, so *any* profile field change (not just the id) invalidates
    stale completed-run reuse. Contains no credential, no filesystem path,
    no environment value."""
    profile = profile or get_active_research_profile()
    identity: dict[str, Any] = {"profile_id": profile.profile_id}
    for key in PROFILE_CONFIG_KEYS:
        identity[key] = getattr(profile, key)
    identity["deepseek_thinking"] = profile.deepseek_thinking
    return identity


def compute_profile_identity_sha256(profile: ResearchProfile | None = None) -> str:
    canonical = json.dumps(
        build_profile_identity(profile), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def display_name_for_profile_id(profile_id: str | None) -> str | None:
    """Safe, human-readable profile name for API/UI display -- never an
    internal config hash. ``None`` for unknown/absent ids. Looks up the full
    fixed registry (not just the current default), so a historical run
    recorded under a previously-active or explicitly-selected profile still
    displays its correct name."""
    if not profile_id:
        return None
    profile = _PROFILE_REGISTRY.get(profile_id)
    return profile.display_name if profile is not None else None


__all__ = [
    "ACTIVE_PROFILE_ID",
    "DEEPSEEK_DEFAULT_PROFILE_ID",
    "ANTHROPIC_PROFILE_ID",
    "PROFILE_CONFIG_KEYS",
    "ResearchProfile",
    "ResearchProfileError",
    "get_active_research_profile",
    "get_research_profile",
    "validate_research_profile",
    "build_profile_tradingagents_config",
    "build_profile_identity",
    "compute_profile_identity_sha256",
    "display_name_for_profile_id",
]
