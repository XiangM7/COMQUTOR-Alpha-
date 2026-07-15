"""Exposure Engine v1 -- pure computational core (W4.4).

Implements exactly the Development Plan's Exposure formula::

    exposure = historical_mapping * 0.50
               + current_evidence * 0.30
               + agent_confidence * 0.20

Pure, deterministic, dependency-free: no filesystem, no database, no
environment variable, no network, no randomness, no wall-clock read. This
module does not know about -- and must never invent -- the formal
``entity_alpha_exposure_seed.yaml`` that ``historical_mapping`` values will
eventually come from in production. Callers supply
``historical_mapping``/``current_evidence``/``agent_confidence`` explicitly;
this module only computes the formula against whatever it is given.

Not wired into the research pipeline, any HTTP API, or the database in this
phase -- no ``entity_alpha_exposures`` table, no exposure endpoint. See
``docs/week4_spec_freeze_audit.md`` 第13节 (``EXPOSURE_SEED_UNAVAILABLE``):
the Exposure *Product* Gate remains ``BLOCKED_BY_SEED`` until the seed is
provided and signed off. This module only proves the Exposure *Core*
formula itself is correct, symmetric across inputs, and safely rejects
malformed input -- it is not a claim that any particular ticker/Alpha
exposure value is real.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from comqutor_alpha.alpha_library.alpha_loader import EXPECTED_ALPHA_IDS

EXPOSURE_FORMULA_VERSION = "week4.exposure_score.mvp_v1"

# APPROVED formula weights (Development Plan): historical_mapping 50%,
# current_evidence 30%, agent_confidence 20%. Not a tunable/config value --
# a frozen constant, exactly like W4.1's CONFLICT_FORMULA_VERSION weights.
EXPOSURE_WEIGHTS = {
    "historical_mapping": 0.50,
    "current_evidence": 0.30,
    "agent_confidence": 0.20,
}


class ExposureInputError(Exception):
    """Safe input-contract violation: carries a stable reason code only.
    Never carries the raw offending value or payload."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def _require_unit_interval_number(value: Any, reason_code: str) -> float:
    """Finite number in [0.0, 1.0]. ``bool``/``str``/``None``/out-of-range
    are all rejected outright -- never coerced, never clamped. A caller
    that passes an out-of-range or wrongly-typed value has a bug; silently
    "fixing" it would hide that bug instead of surfacing it."""
    if isinstance(value, bool):
        raise ExposureInputError(reason_code)
    if not isinstance(value, (int, float)):
        raise ExposureInputError(reason_code)
    number = float(value)
    if not math.isfinite(number):
        raise ExposureInputError(reason_code)
    if not (0.0 <= number <= 1.0):
        raise ExposureInputError(reason_code)
    return number


def calculate_exposure(
    *,
    historical_mapping,
    current_evidence,
    agent_confidence,
) -> dict[str, Any]:
    """Compute one Alpha's exposure score for one entity/ticker.

    Pure function of its three inputs; raises :class:`ExposureInputError`
    (``INVALID_EXPOSURE_INPUT``) for any input that is not a finite number
    in ``[0.0, 1.0]``. ``exposure_score`` is exactly the sum of the three
    ``components[*]["contribution"]`` values -- no additional conflict
    penalty, ranking bonus, or ticker-specific correction is ever applied.
    """
    historical = _require_unit_interval_number(historical_mapping, "INVALID_EXPOSURE_INPUT")
    evidence = _require_unit_interval_number(current_evidence, "INVALID_EXPOSURE_INPUT")
    confidence = _require_unit_interval_number(agent_confidence, "INVALID_EXPOSURE_INPUT")

    historical_contribution = historical * EXPOSURE_WEIGHTS["historical_mapping"]
    evidence_contribution = evidence * EXPOSURE_WEIGHTS["current_evidence"]
    confidence_contribution = confidence * EXPOSURE_WEIGHTS["agent_confidence"]

    exposure_score = historical_contribution + evidence_contribution + confidence_contribution

    return {
        "formula_version": EXPOSURE_FORMULA_VERSION,
        "exposure_score": exposure_score,
        "components": {
            "historical_mapping": {
                "raw": historical,
                "weight": EXPOSURE_WEIGHTS["historical_mapping"],
                "contribution": historical_contribution,
            },
            "current_evidence": {
                "raw": evidence,
                "weight": EXPOSURE_WEIGHTS["current_evidence"],
                "contribution": evidence_contribution,
            },
            "agent_confidence": {
                "raw": confidence,
                "weight": EXPOSURE_WEIGHTS["agent_confidence"],
                "contribution": confidence_contribution,
            },
        },
    }


def _require_ticker(ticker: Any) -> str:
    if not isinstance(ticker, str) or not ticker.strip():
        raise ExposureInputError("INVALID_TICKER")
    return ticker


def _require_alpha_mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ExposureInputError("INVALID_EXPOSURE_INPUT")
    for key in value:
        if not isinstance(key, str) or not key.strip():
            raise ExposureInputError("INVALID_EXPOSURE_INPUT")
    return value


def compute_entity_alpha_exposures(
    *,
    ticker,
    historical_mapping,
    current_evidence,
    agent_confidence,
    taxonomy=None,
) -> dict[str, Any]:
    """Compute exposure scores for every Alpha declared by
    ``historical_mapping`` for one ticker.

    ``historical_mapping`` decides which Alphas this ticker outputs at all;
    ``current_evidence`` and ``agent_confidence`` must declare a value for
    exactly that same ``alpha_id`` set -- no missing component is ever
    defaulted to 0, and no Alpha absent from ``historical_mapping`` is ever
    auto-added just because it happens to appear in one of the other two
    mappings. Every ``alpha_id`` must belong to the valid Alpha ID universe.

    ``taxonomy=None`` (the default) validates against ``EXPECTED_ALPHA_IDS``
    -- the static MVP-10 identifier constant, imported without ever calling
    ``load_alpha_taxonomy()`` or otherwise touching
    ``alpha_taxonomy_v1.yaml``. An explicit ``taxonomy`` mapping is a
    testing seam only, never a hardcoded substitute weight table; it must
    be a ``Mapping`` with non-empty string keys, validated the same way
    ``historical_mapping``/``current_evidence``/``agent_confidence`` are.

    Pure function: no filesystem, database, network, or environment access
    of any kind -- not even to read the frozen Alpha taxonomy YAML. Does
    not read a formal exposure seed. Does not mutate any input mapping.
    Output ``exposures`` is always sorted by ``alpha_id``, so input
    iteration order never affects the result.
    """
    safe_ticker = _require_ticker(ticker)
    historical = _require_alpha_mapping(historical_mapping)
    evidence = _require_alpha_mapping(current_evidence)
    confidence = _require_alpha_mapping(agent_confidence)

    if taxonomy is None:
        valid_alpha_ids = set(EXPECTED_ALPHA_IDS)
    else:
        valid_alpha_ids = set(_require_alpha_mapping(taxonomy))

    alpha_ids = set(historical)
    if set(evidence) != alpha_ids or set(confidence) != alpha_ids:
        raise ExposureInputError("EXPOSURE_INPUT_SET_MISMATCH")

    if alpha_ids - valid_alpha_ids:
        raise ExposureInputError("UNKNOWN_ALPHA_ID")

    exposures = []
    for alpha_id in sorted(alpha_ids):
        result = calculate_exposure(
            historical_mapping=historical[alpha_id],
            current_evidence=evidence[alpha_id],
            agent_confidence=confidence[alpha_id],
        )
        exposures.append(
            {
                "alpha_id": alpha_id,
                "exposure_score": result["exposure_score"],
                "components": result["components"],
            }
        )

    return {
        "formula_version": EXPOSURE_FORMULA_VERSION,
        "ticker": safe_ticker,
        "exposures": exposures,
    }


__all__ = [
    "EXPOSURE_FORMULA_VERSION",
    "EXPOSURE_WEIGHTS",
    "ExposureInputError",
    "calculate_exposure",
    "compute_entity_alpha_exposures",
]
