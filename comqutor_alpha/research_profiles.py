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

Nothing here reads, stores, logs, or returns a credential. The Anthropic
API key stays exclusively in the server process environment
(``ANTHROPIC_API_KEY``) and is read only by the provider SDK itself;
``server_execution.is_anthropic_credential_present`` checks *presence*
without ever exposing the value.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any


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


ACTIVE_PROFILE_ID = "comqutor_anthropic_medium_sonnet46_v1"

_ACTIVE_PROFILE = ResearchProfile(
    profile_id=ACTIVE_PROFILE_ID,
    display_name="COMQUTOR Anthropic Medium v1",
    llm_provider="anthropic",
    quick_think_llm="claude-sonnet-4-6",
    deep_think_llm="claude-sonnet-4-6",
    backend_url=None,
    output_language="English",
    max_debate_rounds=3,
    max_risk_discuss_rounds=3,
)

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
)


def get_active_research_profile() -> ResearchProfile:
    """The single fixed profile every real web-submitted run uses. Validated
    on every call so a future edit that breaks an invariant fails loudly at
    the readiness/submission gate instead of mid-run."""
    validate_research_profile(_ACTIVE_PROFILE)
    return _ACTIVE_PROFILE


def validate_research_profile(profile: ResearchProfile) -> None:
    """Raises ``ResearchProfileError("RESEARCH_PROFILE_INVALID")`` if any
    field violates the frozen profile contract."""
    if not str(profile.profile_id or "").strip():
        raise ResearchProfileError("RESEARCH_PROFILE_INVALID")
    if not str(profile.display_name or "").strip():
        raise ResearchProfileError("RESEARCH_PROFILE_INVALID")
    if str(profile.llm_provider or "").strip().lower() != "anthropic":
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


def build_profile_identity(profile: ResearchProfile | None = None) -> dict[str, Any]:
    """The full non-secret, result-affecting identity of a profile --
    ``profile_id`` plus every ``PROFILE_CONFIG_KEYS`` value. This whole dict
    is folded into the request fingerprint, so *any* profile field change
    (not just the id) invalidates stale completed-run reuse. Contains no
    credential, no filesystem path, no environment value."""
    profile = profile or get_active_research_profile()
    identity: dict[str, Any] = {"profile_id": profile.profile_id}
    for key in PROFILE_CONFIG_KEYS:
        identity[key] = getattr(profile, key)
    return identity


def compute_profile_identity_sha256(profile: ResearchProfile | None = None) -> str:
    canonical = json.dumps(
        build_profile_identity(profile), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def display_name_for_profile_id(profile_id: str | None) -> str | None:
    """Safe, human-readable profile name for API/UI display -- never an
    internal config hash. ``None`` for unknown/absent ids."""
    if profile_id == _ACTIVE_PROFILE.profile_id:
        return _ACTIVE_PROFILE.display_name
    return None


__all__ = [
    "ACTIVE_PROFILE_ID",
    "PROFILE_CONFIG_KEYS",
    "ResearchProfile",
    "ResearchProfileError",
    "get_active_research_profile",
    "validate_research_profile",
    "build_profile_tradingagents_config",
    "build_profile_identity",
    "compute_profile_identity_sha256",
    "display_name_for_profile_id",
]
