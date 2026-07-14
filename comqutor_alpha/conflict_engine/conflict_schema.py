"""Shared constants, reason codes, and pure helpers for the Week 4 Conflict Core.

Every rule here is either SOURCE-FROZEN (Development Plan v1.0) or
APPROVED -- SPEC-FROZEN FOR W4.1 (docs/week4_spec_freeze_audit.md, 2026-07-14
closure). Nothing in this module is a fresh W4.1 invention: nothing here
picks new business thresholds -- it only encodes decisions already recorded
in that document.

Numeric clamping/finiteness reuses ``graph_engine.graph_schema`` directly
(the audit's explicit instruction: reuse, do not re-implement a second,
possibly-inconsistent set of numeric rules).
"""

from __future__ import annotations

from comqutor_alpha.graph_engine.graph_schema import clamp_percent, is_finite_number

CONFLICT_SCHEMA_VERSION = "week4.alpha_conflicts.v1"
CONFLICT_FORMULA_VERSION = "week4.conflict_score.mvp_v1"

# Evidence-Strength (APPROVED -- SPEC-FROZEN FOR W4.1, week4_spec_freeze_audit.md #9):
# qualifying relations are exactly the three Week 3 `_EVIDENCE_RELATION_WEIGHT`
# entries with a positive weight. This is Week 4's own frozen definition --
# intentionally a literal constant, not derived from Week 3's internal dict,
# so a future change to Week 3's weighting never silently changes Week 4's
# admissibility rule (see tests/test_conflict_detector.py for a consistency
# canary against the current Week 3 weights).
QUALIFYING_RELATIONS = frozenset({"activation", "conditional", "mixed"})

# Admissibility (APPROVED -- SPEC-FROZEN FOR W4.1, audit #11): both sides of a
# candidate pair must have `status` at least `watch`.
ADMISSIBLE_STATUSES = frozenset({"watch", "active", "dominant", "regime_level"})

_DIRECTION_POSITIVE = "positive"
_DIRECTION_NEGATIVE = "negative"


class ConflictInputError(Exception):
    """Safe input-contract violation: carries a stable reason code only.

    Raised only for structural violations of the caller's contract (e.g. a
    non-mapping activation payload, a duplicate alpha_id within it) -- never
    for a candidate pair simply lacking evidence or falling below threshold,
    which are graceful `suppressed`/`rejected` outcomes instead, not
    exceptions. Never carries raw exception text, a traceback, or a local
    path.
    """

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


# ---------------------------------------------------------------------------
# Candidate reason codes (docs/week4_spec_freeze_audit.md #9 / this task's
# section 九). Defined as named constants so call sites can't typo a string
# literal into an unrecognized code.
# ---------------------------------------------------------------------------
REASON_MISSING_LEFT_ACTIVATION = "MISSING_LEFT_ACTIVATION"
REASON_MISSING_RIGHT_ACTIVATION = "MISSING_RIGHT_ACTIVATION"
REASON_BELOW_ACTIVATION_THRESHOLD = "BELOW_ACTIVATION_THRESHOLD"
REASON_MISSING_LEFT_EVIDENCE = "MISSING_LEFT_EVIDENCE"
REASON_MISSING_RIGHT_EVIDENCE = "MISSING_RIGHT_EVIDENCE"
REASON_AMBIGUOUS_ONLY = "AMBIGUOUS_ONLY"
REASON_ZERO_EVIDENCE_STRENGTH = "ZERO_EVIDENCE_STRENGTH"
REASON_INVALID_CONTRADICTION_WEIGHT = "INVALID_CONTRADICTION_WEIGHT"
REASON_INVALID_ACTIVATION_SCORE = "INVALID_ACTIVATION_SCORE"
REASON_NON_FINITE_SCORE_COMPONENT = "NON_FINITE_SCORE_COMPONENT"
REASON_RUN_ID_MISMATCH = "RUN_ID_MISMATCH"
REASON_TICKER_MISMATCH = "TICKER_MISMATCH"
REASON_SCHEMA_INVALID = "SCHEMA_INVALID"
REASON_DIRECTION_ROLE_UNRESOLVED = "DIRECTION_ROLE_UNRESOLVED"
REASON_DUPLICATE_PAIR = "DUPLICATE_PAIR"
# Only reachable via an optional single-pair evaluation helper, never via the
# main taxonomy-declared enumeration (which by construction never evaluates
# an undeclared pair).
REASON_PAIR_NOT_DECLARED = "PAIR_NOT_DECLARED"

# Reason codes that indicate the candidate's *data* is illegitimate (a
# structural/legality problem) rather than merely "this run's evidence is
# thin." REJECTED takes precedence over SUPPRESSED whenever both classes of
# reason are present on the same candidate.
REJECTED_CLASS_REASONS = frozenset(
    {
        REASON_MISSING_LEFT_ACTIVATION,
        REASON_MISSING_RIGHT_ACTIVATION,
        REASON_INVALID_CONTRADICTION_WEIGHT,
        REASON_INVALID_ACTIVATION_SCORE,
        REASON_NON_FINITE_SCORE_COMPONENT,
        REASON_RUN_ID_MISMATCH,
        REASON_TICKER_MISMATCH,
        REASON_SCHEMA_INVALID,
        REASON_DIRECTION_ROLE_UNRESOLVED,
        REASON_DUPLICATE_PAIR,
        REASON_PAIR_NOT_DECLARED,
    }
)

# ---------------------------------------------------------------------------
# Excluded-evidence reason codes (this task's section 七/十四): per-claim
# audit of why a specific piece of evidence did not qualify. A distinct
# namespace from the candidate-level reason codes above.
# ---------------------------------------------------------------------------
EXCLUDED_NON_COMMITTED_MATCH = "NON_COMMITTED_MATCH"
EXCLUDED_WRONG_ALPHA = "WRONG_ALPHA"
EXCLUDED_MISSING_CLAIM_ID = "MISSING_CLAIM_ID"
EXCLUDED_DUPLICATE_CLAIM = "DUPLICATE_CLAIM"
EXCLUDED_EMPTY_EVIDENCE = "EMPTY_EVIDENCE"
EXCLUDED_UNSUPPORTED_RELATION = "UNSUPPORTED_RELATION"
EXCLUDED_INVALID_MATCH_SCORE = "INVALID_MATCH_SCORE"


# (upper_bound_inclusive, level) evaluated in order; the first band whose
# upper bound the (already 0..100 clamped) score does not exceed applies.
# APPROVED -- SPEC-FROZEN FOR W4.1 (audit #8): [0,25] low, (25,50] medium,
# (50,75] medium_high, (75,100] high.
_CONFLICT_LEVEL_UPPER_BOUNDS = (
    (25.0, "low"),
    (50.0, "medium"),
    (75.0, "medium_high"),
    (100.0, "high"),
)


def conflict_level(score) -> str:
    """Map a conflict_score to exactly one documented level band.

    Half-open on the lower side, closed on the upper side -- 25.0 is `low`,
    25.0001 is `medium`. Out-of-range/non-finite input is clamped first via
    the reused ``graph_schema.clamp_percent`` (same policy as Week 3's own
    status bands), never raised, so this always returns a valid level
    string. A distinct name and namespace from Week 3's
    `activation_status_band` on purpose -- conflict levels and activation
    status bands are different scales with different boundaries and must
    never be interchanged.
    """
    clamped = clamp_percent(score)
    for upper_bound, level in _CONFLICT_LEVEL_UPPER_BOUNDS:
        if clamped <= upper_bound:
            return level
    return "high"  # unreachable given clamp_percent's ceiling of 100.0


def canonical_pair_key(alpha_id_1: str, alpha_id_2: str) -> tuple[str, str]:
    """Canonical Pair (APPROVED -- SPEC-FROZEN FOR W4.1, audit #10):
    ``alpha_a``/``alpha_b`` = the two alpha_ids sorted lexicographically.
    This is a dedup/identity key only -- it carries no bull/bear semantics.
    """
    alpha_a, alpha_b = sorted((str(alpha_id_1), str(alpha_id_2)))
    return alpha_a, alpha_b


def conflict_id(alpha_a: str, alpha_b: str) -> str:
    """Stable, canonical-order conflict identifier, e.g. ``"A101__A304"``."""
    return f"{alpha_a}__{alpha_b}"


def resolve_bull_bear(
    alpha_a: str, direction_a, alpha_b: str, direction_b
) -> tuple[str | None, str | None]:
    """Bull/Bear role resolution (APPROVED -- SPEC-FROZEN FOR W4.1, audit #10):
    role comes only from each side's own Week 3 activation ``direction`` --
    never from canonical order, alpha_id, or ticker. Returns
    ``(bull_alpha_id, bear_alpha_id)``, or ``(None, None)`` if the pair does
    not resolve to exactly one positive and one negative side.
    """
    if direction_a == _DIRECTION_POSITIVE and direction_b == _DIRECTION_NEGATIVE:
        return alpha_a, alpha_b
    if direction_a == _DIRECTION_NEGATIVE and direction_b == _DIRECTION_POSITIVE:
        return alpha_b, alpha_a
    return None, None


def dedupe_stable(codes) -> list[str]:
    """Deduplicate reason codes while preserving first-seen order."""
    seen: set[str] = set()
    ordered: list[str] = []
    for code in codes:
        if code not in seen:
            seen.add(code)
            ordered.append(code)
    return ordered


__all__ = [
    "CONFLICT_SCHEMA_VERSION",
    "CONFLICT_FORMULA_VERSION",
    "QUALIFYING_RELATIONS",
    "ADMISSIBLE_STATUSES",
    "ConflictInputError",
    "REASON_MISSING_LEFT_ACTIVATION",
    "REASON_MISSING_RIGHT_ACTIVATION",
    "REASON_BELOW_ACTIVATION_THRESHOLD",
    "REASON_MISSING_LEFT_EVIDENCE",
    "REASON_MISSING_RIGHT_EVIDENCE",
    "REASON_AMBIGUOUS_ONLY",
    "REASON_ZERO_EVIDENCE_STRENGTH",
    "REASON_INVALID_CONTRADICTION_WEIGHT",
    "REASON_INVALID_ACTIVATION_SCORE",
    "REASON_NON_FINITE_SCORE_COMPONENT",
    "REASON_RUN_ID_MISMATCH",
    "REASON_TICKER_MISMATCH",
    "REASON_SCHEMA_INVALID",
    "REASON_DIRECTION_ROLE_UNRESOLVED",
    "REASON_DUPLICATE_PAIR",
    "REASON_PAIR_NOT_DECLARED",
    "REJECTED_CLASS_REASONS",
    "EXCLUDED_NON_COMMITTED_MATCH",
    "EXCLUDED_WRONG_ALPHA",
    "EXCLUDED_MISSING_CLAIM_ID",
    "EXCLUDED_DUPLICATE_CLAIM",
    "EXCLUDED_EMPTY_EVIDENCE",
    "EXCLUDED_UNSUPPORTED_RELATION",
    "EXCLUDED_INVALID_MATCH_SCORE",
    "is_finite_number",
    "clamp_percent",
    "conflict_level",
    "canonical_pair_key",
    "conflict_id",
    "resolve_bull_bear",
    "dedupe_stable",
]
