"""Shared constants, enums, and numeric helpers for the Week 3 graph engine.

Mirrors the style of ``structure_engine/structure_schema.py``: plain
dataclasses/constants, no behavior that depends on wall-clock time or
dictionary iteration order.
"""

from __future__ import annotations

import math

from comqutor_alpha.alpha_library.alpha_loader import EXPECTED_ALPHA_IDS

GRAPH_SCHEMA_VERSION = "week3.structure_graph.v1"
GRAPH_BUILDER_VERSION = "week3.graph_builder.v1"
ACTIVATION_SCORER_VERSION = "week3.activation_scorer.v1"
GRAPH_COHERENCE_FORMULA_VERSION = "week3.graph_coherence.mvp_v1"
ACTIVATION_FORMULA_VERSION = "week3.activation.mvp_v1"

# The MVP-10 alpha set is owned by the alpha taxonomy loader; re-exported here
# so callers in this package have one place to import it from.
MVP_ALPHA_IDS = frozenset(EXPECTED_ALPHA_IDS)

VALID_NODE_TYPES = frozenset({"factor"})
VALID_GRAPH_EDGE_TYPES = frozenset({"causal", "supportive", "conflicting"})
VALID_ASSERTION_STATUSES = frozenset({"asserted", "conditional", "negated", "mixed", "unknown"})
VALID_MATCH_STATUSES = frozenset({"matched", "ambiguous", "no_match"})

VALID_ACTIVATION_STATUSES = frozenset(
    {"inactive", "watch", "active", "dominant", "regime_level"}
)

# (upper_bound_inclusive, status) evaluated in order; the first band whose
# upper bound the (already 0..100 clamped) score does not exceed applies.
_STATUS_BAND_UPPER_BOUNDS = (
    (30.0, "inactive"),
    (50.0, "watch"),
    (70.0, "active"),
    (85.0, "dominant"),
    (100.0, "regime_level"),
)


def is_finite_number(value) -> bool:
    """True only for values that convert to a real, finite float."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number)


def clamp_percent(value, minimum: float = 0.0, maximum: float = 100.0) -> float:
    """Clamp a value to a 0..100 (by default) range, treating NaN/Inf as safe.

    Non-finite input is not an error here: it is deterministically clamped
    (NaN and -Inf go to ``minimum``, +Inf goes to ``maximum``) so a bad
    upstream number can never propagate into an out-of-range or undefined
    score. Callers that must instead reject non-finite input (e.g. graph
    edge weights) use :func:`is_finite_number` explicitly first.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return minimum
    if math.isnan(number):
        return minimum
    if math.isinf(number):
        return maximum if number > 0 else minimum
    return round(min(max(number, minimum), maximum), 4)


def activation_status_band(score) -> str:
    """Map an activation score to exactly one documented status band.

    Boundaries are half-open on the lower side and closed on the upper side:
    0..30 inactive, (30..50] watch, (50..70] active, (70..85] dominant,
    (85..100] regime_level. Out-of-range input is clamped first (documented
    schema policy), never rejected, so this function always returns a valid
    band.
    """
    clamped = clamp_percent(score)
    for upper_bound, status in _STATUS_BAND_UPPER_BOUNDS:
        if clamped <= upper_bound:
            return status
    return "regime_level"  # unreachable given clamp_percent's ceiling of 100.0
