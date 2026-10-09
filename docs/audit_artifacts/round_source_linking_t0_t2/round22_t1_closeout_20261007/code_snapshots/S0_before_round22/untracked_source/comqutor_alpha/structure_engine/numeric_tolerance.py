"""Numeric approximation tolerance (2026-10-06, T1 content-support v3 round).

Product rule (section 五 of the v3 spec): a claim's own stated number should
not be rejected merely because it is a reasonable rounding or a small,
genuine approximation of a real source value. This module implements ONLY
the pure numeric comparison step -- it never decides whether the claim and
source are even talking about the same object/metric/period/unit/direction
(that alignment check is the caller's job, before this module is ever
invoked: see the v3 spec's own explicit ordering, "先确认比较的是同一个
东西" before "比较方式"), and it never decides whether a sign flip, a
threshold crossing, or a wrong object/metric/period/unit should be excused
by a small relative error (those are exceptions the caller applies on top
of this module's own, narrower verdict -- see ``NumericToleranceResult.
rule_applied`` and the module docstring's own worked example: "claim
asserts 'breaks 100', source is actually 99" must not pass here just
because the gap is 1%).

Deliberately separate from ``comqutor_alpha.source_provenance.
_value_matches_any`` (0.5% relative tolerance): that function backs the
FULLY AUTOMATED, zero-LLM-oversight ``verify_data_fact_or_derived_
calculation`` gate, which stays at its existing, stricter threshold --
this module is for the LLM-facing/content-support-verification numeric
check specifically, where the v3 spec's own 3% default applies. Changing
the automated gate's own tolerance is out of this round's scope and was
not asked for.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- rule identifiers -------------------------------------------------------
RULE_EXACT = "EXACT"
RULE_ROUNDING_CONSISTENT = "ROUNDING_CONSISTENT"
RULE_RELATIVE_ERROR_WITHIN_TOLERANCE = "RELATIVE_ERROR_WITHIN_TOLERANCE"
RULE_ZERO_OR_NEAR_ZERO_SOURCE_ABSOLUTE_CHECK = "ZERO_OR_NEAR_ZERO_SOURCE_ABSOLUTE_CHECK"
RULE_EXCEEDS_TOLERANCE = "EXCEEDS_TOLERANCE"

DEFAULT_MAX_RELATIVE_ERROR = 0.03

# Below this absolute source magnitude, a relative-error comparison is not
# meaningful (dividing by a near-zero number produces a huge, uninformative
# relative error) -- see spec section 五.3 "来源为零或接近零时，不使用相对
# 误差放行". This default absolute band is deliberately small and generic;
# a caller with real knowledge of the source's own display/field precision
# (e.g. "this field is reported to 1 decimal place") should pass its own
# ``near_zero_absolute_tolerance`` rather than rely on this default.
DEFAULT_NEAR_ZERO_SOURCE_THRESHOLD = 1e-9
DEFAULT_NEAR_ZERO_ABSOLUTE_TOLERANCE = 0.01


@dataclass(frozen=True)
class NumericToleranceResult:
    """The result of comparing exactly one claim-stated number against
    exactly one real source-stated number. Never resolves object/metric/
    period/unit alignment, never resolves sign-flip/threshold-crossing
    exceptions -- both are the caller's own, separate responsibility,
    applied on top of this result (see module docstring)."""

    claim_value: float
    source_value: float
    absolute_difference: float
    # None exactly when source_value is zero/near-zero (relative error is
    # not meaningful there) -- never a fabricated number in that case.
    relative_error: float | None
    rule_applied: str
    within_tolerance: bool
    # Human-readable, saved alongside the above for the real record -- never
    # recomputed later from the bare numbers alone (see spec: "保存来源原
    # 值、claim值、归一化结果、差异及适用规则").
    explanation: str


def compare_numeric_values(
    claim_value: float,
    source_value: float,
    *,
    max_relative_error: float = DEFAULT_MAX_RELATIVE_ERROR,
    near_zero_source_threshold: float = DEFAULT_NEAR_ZERO_SOURCE_THRESHOLD,
    near_zero_absolute_tolerance: float = DEFAULT_NEAR_ZERO_ABSOLUTE_TOLERANCE,
) -> NumericToleranceResult:
    """Compares two ALREADY-NORMALIZED numbers (same unit, same scale --
    normalizing thousands separators / %/M/B/K suffixes is the caller's job,
    exactly as ``comqutor_alpha.source_provenance._parse_claim_numbers``
    already does elsewhere in this codebase; this function is reused for
    that normalized pair, never for raw, unnormalized text).

    Rule order (spec section 五.2/五.3), each one a possible real
    ``rule_applied`` outcome:
      1. Exact match (after normalization) -> RULE_EXACT.
      2. Source is zero/near-zero -> relative error is not used at all;
         falls back to an absolute-difference check against
         ``near_zero_absolute_tolerance`` -> RULE_ZERO_OR_NEAR_ZERO_SOURCE_
         ABSOLUTE_CHECK. ``relative_error`` is None in this branch, never a
         divide-by-near-zero artifact.
      3. Otherwise, relative_error = abs(claim - source) / abs(source).
         <= max_relative_error (default 3%) -> RULE_RELATIVE_ERROR_WITHIN_
         TOLERANCE (this also covers what a human would call "reasonable
         rounding" -- a dedicated separate rounding-detection pass is not
         needed: the relative-error check already subsumes it, and a
         caller wanting to CALL OUT a value as "this is exactly bankers'/
         standard rounding to N significant figures" can do so separately
         for display purposes using ``RULE_ROUNDING_CONSISTENT`` via
         :func:`is_consistent_rounding`, without changing this function's
         own pass/fail verdict).
      4. Otherwise -> RULE_EXCEEDS_TOLERANCE, within_tolerance=False. This
         function never auto-escalates this to "fabricated" -- it is only
         ever a numeric-comparison verdict (spec: "超过3%也不自动认定
         造假").
    """
    absolute_difference = abs(claim_value - source_value)

    if claim_value == source_value:
        return NumericToleranceResult(
            claim_value=claim_value,
            source_value=source_value,
            absolute_difference=0.0,
            relative_error=0.0,
            rule_applied=RULE_EXACT,
            within_tolerance=True,
            explanation="claim value exactly equals the source value after normalization",
        )

    if abs(source_value) <= near_zero_source_threshold:
        within = absolute_difference <= near_zero_absolute_tolerance
        return NumericToleranceResult(
            claim_value=claim_value,
            source_value=source_value,
            absolute_difference=absolute_difference,
            relative_error=None,
            rule_applied=RULE_ZERO_OR_NEAR_ZERO_SOURCE_ABSOLUTE_CHECK,
            within_tolerance=within,
            explanation=(
                f"source value is zero/near-zero ({source_value!r}); relative error is not "
                f"meaningful here, so absolute difference {absolute_difference!r} was checked "
                f"against an absolute tolerance of {near_zero_absolute_tolerance!r} instead "
                f"({'within' if within else 'exceeds'} tolerance)"
            ),
        )

    relative_error = absolute_difference / abs(source_value)
    within = relative_error <= max_relative_error
    return NumericToleranceResult(
        claim_value=claim_value,
        source_value=source_value,
        absolute_difference=absolute_difference,
        relative_error=relative_error,
        rule_applied=(RULE_RELATIVE_ERROR_WITHIN_TOLERANCE if within else RULE_EXCEEDS_TOLERANCE),
        within_tolerance=within,
        explanation=(
            f"relative_error = {absolute_difference!r} / {abs(source_value)!r} = "
            f"{relative_error:.6f} ({'<=' if within else '>'} {max_relative_error!r})"
        ),
    )


def is_consistent_rounding(claim_value: float, source_value: float, *, max_significant_digits: int = 6) -> bool:
    """Display-only helper: true when ``claim_value`` equals ``source_value``
    rounded to some real, plausible number of SIGNIFICANT FIGURES (e.g.
    121,732,200 rounded to 4 significant figures is 121,700,000 -> "121.7M").
    Never used to decide ``within_tolerance`` above (the relative-error
    check already covers every value this would flag, and more) -- only to
    let a caller label a result as "this specific case was a recognizable
    rounding," which the spec's own worked example calls out as a readable
    category distinct from a bare relative-error pass."""
    import math

    if source_value == 0:
        return claim_value == 0
    magnitude = math.floor(math.log10(abs(source_value)))
    for digits in range(1, max_significant_digits + 1):
        quantum = 10 ** (magnitude - digits + 1)
        rounded = round(source_value / quantum) * quantum
        if claim_value == rounded:
            return True
    return False
