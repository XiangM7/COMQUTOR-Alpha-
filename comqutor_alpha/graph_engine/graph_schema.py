"""Shared constants, enums, and numeric helpers for the Week 3 graph engine.

Mirrors the style of ``structure_engine/structure_schema.py``: plain
dataclasses/constants, no behavior that depends on wall-clock time or
dictionary iteration order.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from comqutor_alpha.alpha_library.alpha_loader import EXPECTED_ALPHA_IDS

# Structure Graph contract versions. v1 is the historical, activation-v1-only
# shape; v2 is additive (activation_versions/primary_activation_version) but
# is NOT accepted interchangeably with v1 -- the top-level "activation"
# field's own meaning changed (v1 payload vs v2-primary payload), so a
# schema_version bump is required rather than treating this as a purely
# additive change. ``GRAPH_SCHEMA_VERSION`` is kept as an alias for v1: it is
# still what ``graph_builder.build_structure_graph``'s Stage-1 (structural,
# pre-activation) output uses, since nodes/edges/graph_metrics/coherence are
# unaffected by the activation-version split.
GRAPH_SCHEMA_VERSION_V1 = "week3.structure_graph.v1"
GRAPH_SCHEMA_VERSION_V2 = "week3.structure_graph.v2"
GRAPH_SCHEMA_VERSION = GRAPH_SCHEMA_VERSION_V1
VALID_GRAPH_SCHEMA_VERSIONS = frozenset({GRAPH_SCHEMA_VERSION_V1, GRAPH_SCHEMA_VERSION_V2})

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
    {"inactive", "watch", "active", "dominant", "regime_level", "candidate"}
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


# ---------------------------------------------------------------------------
# Structure Graph contract validation (Activation v2 Closure Review, Phase 1)
#
# Explicit, version-specific structural validation of one structure_graph.json
# payload. Deliberately does NOT accept schema_version by prefix/startswith,
# does NOT guess a version when absent, and does NOT treat v1 and v2 through
# one merged/union shape -- each version has its own required-key set, and a
# v2 payload's internal cross-references (primary_activation_version vs.
# activation_versions["v2"].formula_version; the top-level "activation" block
# vs. activation_versions["v2"]) are verified to actually agree, not merely
# both be well-typed in isolation. This is the single source of truth for
# graph-contract shape: both the write path (repository.persist_run) and the
# read path (repository.get_graph, the GET .../graph API) call the same
# function rather than maintaining two independent checks.
# ---------------------------------------------------------------------------


class GraphSchemaContractError(ValueError):
    """Raised when a structure_graph payload does not match its declared
    schema_version's required shape. Carries a stable reason_code only."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


GRAPH_SCHEMA_INVALID = "GRAPH_SCHEMA_INVALID"
GRAPH_SCHEMA_UNKNOWN_VERSION = "GRAPH_SCHEMA_MISMATCH"
GRAPH_SCHEMA_PRIMARY_MISMATCH = "GRAPH_SCHEMA_PRIMARY_MISMATCH"

_V1_REQUIRED_KEYS = frozenset({"schema_version", "nodes", "edges", "activation", "dominant_alphas"})
_V2_REQUIRED_KEYS = _V1_REQUIRED_KEYS | {"activation_versions", "primary_activation_version"}


def _require(condition: bool, reason_code: str) -> None:
    if not condition:
        raise GraphSchemaContractError(reason_code)


def _validate_activation_block_shape(activation: object, reason_code: str) -> None:
    _require(isinstance(activation, Mapping), reason_code)
    _require(isinstance(activation.get("formula_version"), str), reason_code)  # type: ignore[union-attr]
    _require(bool(activation.get("formula_version")), reason_code)  # type: ignore[union-attr]
    _require(isinstance(activation.get("alphas"), list), reason_code)  # type: ignore[union-attr]


def _validate_v1_graph_shape(graph_json: Mapping[str, object]) -> None:
    _require(_V1_REQUIRED_KEYS.issubset(graph_json), GRAPH_SCHEMA_INVALID)
    _validate_activation_block_shape(graph_json.get("activation"), GRAPH_SCHEMA_INVALID)


def _validate_v2_graph_shape(graph_json: Mapping[str, object]) -> None:
    _require(_V2_REQUIRED_KEYS.issubset(graph_json), GRAPH_SCHEMA_INVALID)
    activation = graph_json.get("activation")
    _validate_activation_block_shape(activation, GRAPH_SCHEMA_INVALID)

    activation_versions = graph_json.get("activation_versions")
    _require(isinstance(activation_versions, Mapping), GRAPH_SCHEMA_INVALID)
    v1_block = activation_versions.get("v1")  # type: ignore[union-attr]
    v2_block = activation_versions.get("v2")  # type: ignore[union-attr]
    _validate_activation_block_shape(v1_block, GRAPH_SCHEMA_INVALID)
    _validate_activation_block_shape(v2_block, GRAPH_SCHEMA_INVALID)

    primary_activation_version = graph_json.get("primary_activation_version")
    _require(
        isinstance(primary_activation_version, str) and bool(primary_activation_version),
        GRAPH_SCHEMA_INVALID,
    )
    # The declared primary must actually match the v2 block it claims to
    # summarize -- a mismatch here means the payload's own cross-references
    # disagree, which is data corruption, not merely an unknown version.
    _require(
        primary_activation_version == v2_block.get("formula_version"),  # type: ignore[union-attr]
        GRAPH_SCHEMA_PRIMARY_MISMATCH,
    )
    # The top-level "activation" field (the primary payload callers read) is
    # required to be exactly the v2 block it is primary for -- not merely an
    # independently-consistent payload that happens to agree on paper.
    _require(activation == v2_block, GRAPH_SCHEMA_PRIMARY_MISMATCH)


def validate_structure_graph_contract(graph_json: object) -> None:
    """Validate one structure_graph payload against its own declared
    ``schema_version``. Raises :class:`GraphSchemaContractError` (never
    returns a value) on any violation:

    - not a mapping, or missing/non-string/unknown ``schema_version``;
    - a v1 payload missing any required v1 key or with a malformed
      ``activation`` block;
    - a v2 payload missing any required v2 key (including
      ``activation_versions``/``primary_activation_version``), with a
      malformed v1/v2 sub-payload, or whose ``primary_activation_version``/
      top-level ``activation`` disagree with ``activation_versions["v2"]``.
    """
    _require(isinstance(graph_json, Mapping), GRAPH_SCHEMA_INVALID)
    schema_version = graph_json.get("schema_version")
    if schema_version == GRAPH_SCHEMA_VERSION_V1:
        _validate_v1_graph_shape(graph_json)
        return
    if schema_version == GRAPH_SCHEMA_VERSION_V2:
        _validate_v2_graph_shape(graph_json)
        return
    raise GraphSchemaContractError(GRAPH_SCHEMA_UNKNOWN_VERSION)


def primary_activation_version_for(graph_json: Mapping[str, object]) -> str | None:
    """The primary activation formula version for one *already-validated*
    structure_graph payload, computed strictly per its own schema_version --
    never guessed, never backfilled from one version to the other.

    - ``week3.structure_graph.v1``: primary is ``activation.formula_version``.
    - ``week3.structure_graph.v2``: primary is the payload's own
      ``primary_activation_version`` field.
    - any other/missing schema_version: ``None``.
    """
    schema_version = graph_json.get("schema_version")
    if schema_version == GRAPH_SCHEMA_VERSION_V1:
        activation = graph_json.get("activation")
        return activation.get("formula_version") if isinstance(activation, Mapping) else None
    if schema_version == GRAPH_SCHEMA_VERSION_V2:
        value = graph_json.get("primary_activation_version")
        return value if isinstance(value, str) else None
    return None
