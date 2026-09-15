"""Alpha-Level Display Normalization (Step 7).

PRESENTATION / AUDIT NORMALIZATION ONLY. ``alpha_level_classifier`` (B4)
remains the sole activation authority -- this module never recomputes
``activation_score``, never re-groups Evidence Facts, never re-evaluates the
regime gate, and never re-derives ``is_blocked``/``blocked_from``/
``blocked_reason_codes``/``cap_reason_codes``. It only relabels those
already-authoritative fields into John's requested display vocabulary,
additively, alongside (never replacing) the existing ``qualified_level``/
``activation_level``/``is_blocked`` fields ``alpha_level_classifier`` already
writes on every Activation v2 alpha entry.

``candidate_active``: no authoritative existing definition for a state
distinct from plain ``"candidate"`` was found anywhere in this codebase.
This was independently confirmed by a prior, dedicated investigation
(``alpha_level_classifier.CAPPED_ACTIVE``'s own docstring,
``frontend/src/api/types.ts``'s ``ACTIVATION_DISPLAY_LEVELS`` comment, and
``tests/test_b4_activation_level_alignment.py::
test_i_candidate_shows_plain_candidate_no_authoritative_candidate_active_definition``
all agree). Per this task's explicit instruction not to fake a definition,
this module never assigns ``display_level="candidate_active"`` -- a
candidate-level Alpha's ``display_level`` stays exactly ``"candidate"``, and
``CANDIDATE_ACTIVE_STATUS`` records the outcome for the audit artifact.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from comqutor_alpha.graph_engine.alpha_level_classifier import (
    ACTIVE,
    CANDIDATE,
    CANONICAL_LEVELS,
    CAPPED_ACTIVE,
    DOMINANT,
    REGIME_LEVEL,
)

ALPHA_DISPLAY_NORMALIZATION_VERSION = "alpha_display_normalization.v1"

# John's requested display vocabulary (task section 0), minus
# "candidate_active" -- see module docstring for why it is never assigned.
DISPLAY_LEVELS = (CANDIDATE, ACTIVE, CAPPED_ACTIVE, DOMINANT, REGIME_LEVEL)

CANDIDATE_ACTIVE_REQUIRES_PRODUCT_DEFINITION = "CANDIDATE_ACTIVE_REQUIRES_PRODUCT_DEFINITION"

# UNKNOWN/malformed authoritative input fails conservatively to this sentinel
# -- never a real (and never a high) display level (task section 17).
UNKNOWN_DISPLAY_STATE = "UNKNOWN_DISPLAY_STATE"

# Deterministic, reason-code-driven diagnostic strings -- never new product
# copy/marketing language, never a replacement for the authoritative reason
# codes themselves (task section 16: codes are preserved verbatim in
# blocked_reason_codes/cap_reason_codes; this is a separate, additive field).
_LEVEL_EXPLANATIONS: dict[str, str] = {
    CANDIDATE: "Below the active threshold (score < 50) -- candidate signal only.",
    ACTIVE: "Meets the active threshold (score >= 50) with no dominant-level qualification ceiling in play.",
    CAPPED_ACTIVE: (
        "Score/evidence would reach dominant (or regime_level), but an existing "
        "qualification ceiling holds the authoritative level at active."
    ),
    DOMINANT: "Meets the dominant threshold (score >= 70) and every existing dominant qualification gate.",
    REGIME_LEVEL: "Meets the regime-level threshold (score >= 86) and every existing regime qualification gate.",
}


def normalize_alpha_display_state(entry: Mapping[str, Any]) -> dict[str, Any]:
    """One already-classified Activation v2 alpha entry -- i.e. it has
    already passed through
    ``alpha_level_classifier.classify_and_rebuild_collections`` and carries
    ``qualified_level``/``activation_level``/``is_blocked``/``blocked_from``/
    ``blocked_reason_codes``/``cap_reason_codes`` -- normalized into John's
    requested display contract. Pure relabeling: never recomputes
    ``activation_score``, never re-derives qualification.

    Fails conservatively (``display_level=UNKNOWN_DISPLAY_STATE``, never a
    real/high level) whenever the required authoritative fields are missing
    or malformed, rather than guessing (task section 17).
    """
    activation_score = entry.get("activation_score")
    authoritative_level = entry.get("qualified_level")
    raw_display_level = entry.get("activation_level")
    is_blocked = entry.get("is_blocked")

    ambiguous = (
        authoritative_level not in CANONICAL_LEVELS
        or raw_display_level not in DISPLAY_LEVELS
        or not isinstance(is_blocked, bool)
        or not isinstance(activation_score, (int, float))
        or isinstance(activation_score, bool)
    )

    if ambiguous:
        display_level = UNKNOWN_DISPLAY_STATE
        explanation = (
            "Authoritative B4 state missing or malformed -- reported ambiguous, "
            "never promoted to a display level."
        )
        authoritative_level_out = None
        blocked = False
    else:
        display_level = raw_display_level
        explanation = _LEVEL_EXPLANATIONS.get(display_level, "")
        authoritative_level_out = authoritative_level
        blocked = bool(is_blocked)

    return {
        "alpha_id": entry.get("alpha_id"),
        "activation_score": activation_score,
        "authoritative_level": authoritative_level_out,
        "display_level": display_level,
        "blocked": blocked,
        "blocked_reason_codes": list(entry.get("blocked_reason_codes") or ()),
        "cap_reason_codes": list(entry.get("cap_reason_codes") or ()),
        "display_explanation": explanation,
        "ambiguous": ambiguous,
        "normalization_contract_version": ALPHA_DISPLAY_NORMALIZATION_VERSION,
    }


def normalize_alpha_display_states(entries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Batch form of :func:`normalize_alpha_display_state` -- one call per
    entry, order preserved, no aggregation/re-ranking performed here."""
    return [normalize_alpha_display_state(entry) for entry in entries]


__all__ = [
    "ALPHA_DISPLAY_NORMALIZATION_VERSION",
    "DISPLAY_LEVELS",
    "CANDIDATE_ACTIVE_REQUIRES_PRODUCT_DEFINITION",
    "UNKNOWN_DISPLAY_STATE",
    "normalize_alpha_display_state",
    "normalize_alpha_display_states",
]
