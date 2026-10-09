"""Selectable Week 2 execution profiles (2026-10-08, T3 closeout).

A profile is an explicit, named product execution configuration for the
three semantic tasks the T3 verification measured
(``content_support_verification``, ``alpha_classifier``,
``evidence_stance_classifier``). It is selected per process with
``COMQUTOR_WEEK2_LLM_PROFILE=<name>``; unset (every existing deployment and
the running service) keeps today's environment-driven behavior exactly.

A profile never changes the provider, model, prompt templates, candidate
scope, output caps or any judgment rule -- only timeouts, retries, batch
size, concurrency and the request/response audit. While one is selected, its
values replace the overlapping environment settings
(``COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS`` for these three tasks,
``COMQUTOR_WEEK2_LLM_MAX_RETRIES``, ``COMQUTOR_WEEK2_LLM_ENABLE_REQUEST_AUDIT``,
``COMQUTOR_WEEK2_CONTENT_SUPPORT_BATCH_SIZE``, ``COMQUTOR_WEEK2_LLM_CONCURRENCY``,
``COMQUTOR_WEEK2_STANCE_CONCURRENCY``). An unknown name is a configuration
error, never a silent fall-back to defaults.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

PROFILE_ENV_VAR = "COMQUTOR_WEEK2_LLM_PROFILE"


@dataclass(frozen=True)
class Week2ExecutionProfile:
    name: str
    # client read timeout AND application-level timeout, per task
    task_timeout_seconds: Mapping[str, float]
    # application retries (the gateway's own retry loop); SDK retries are always 0 in build_server_week2_llm_gateway
    max_retries: int
    request_response_audit: bool
    content_support_batch_size: int
    alpha_classifier_concurrency: int
    evidence_stance_concurrency: int
    basis: str


# The configuration execution t3joint-20261008T170322Z-bd99811e ran with (its signed plan's
# "config"): content support one claim per request, 120 s; Alpha one claim per request, 45 s,
# concurrency 4; stance in the production 10-item batches, 120 s, concurrency 4; both retry
# layers 0; audit on. 120 s is a chosen bound, not a measured success guarantee: in that
# execution content support took up to 82.5 s and stance up to 15.9 s on 3 small batches.
T3_VERIFIED_20261008 = Week2ExecutionProfile(
    name="t3_verified_20261008",
    task_timeout_seconds=MappingProxyType(
        {
            "content_support_verification": 120.0,
            "alpha_classifier": 45.0,
            "evidence_stance_classifier": 120.0,
        }
    ),
    max_retries=0,
    request_response_audit=True,
    content_support_batch_size=1,
    alpha_classifier_concurrency=4,
    evidence_stance_concurrency=4,
    basis="T3 execution t3joint-20261008T170322Z-bd99811e, signed plan config",
)

PROFILES: Mapping[str, Week2ExecutionProfile] = MappingProxyType({T3_VERIFIED_20261008.name: T3_VERIFIED_20261008})


class UnknownWeek2ExecutionProfile(ValueError):
    pass


def resolve_week2_execution_profile() -> Week2ExecutionProfile | None:
    """The profile named by ``COMQUTOR_WEEK2_LLM_PROFILE``, ``None`` when unset;
    raises ``UnknownWeek2ExecutionProfile`` for a name that is not registered."""
    name = (os.environ.get(PROFILE_ENV_VAR) or "").strip()
    if not name:
        return None
    profile = PROFILES.get(name)
    if profile is None:
        raise UnknownWeek2ExecutionProfile(name)
    return profile


__all__ = [
    "PROFILE_ENV_VAR",
    "PROFILES",
    "T3_VERIFIED_20261008",
    "UnknownWeek2ExecutionProfile",
    "Week2ExecutionProfile",
    "resolve_week2_execution_profile",
]
