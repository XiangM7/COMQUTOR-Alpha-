"""Zero-cost, offline tests for comqutor_alpha.structure_engine.
numeric_tolerance -- covers the v3 spec's own section 五 worked examples
directly, so a future change to the tolerance rule has to explicitly
confront these exact numbers, not just an abstract threshold."""

from __future__ import annotations

from comqutor_alpha.structure_engine.numeric_tolerance import (
    RULE_EXACT,
    RULE_EXCEEDS_TOLERANCE,
    RULE_RELATIVE_ERROR_WITHIN_TOLERANCE,
    RULE_ZERO_OR_NEAR_ZERO_SOURCE_ABSOLUTE_CHECK,
    compare_numeric_values,
    is_consistent_rounding,
)


def test_exact_match():
    result = compare_numeric_values(0.64, 0.64)
    assert result.rule_applied == RULE_EXACT
    assert result.within_tolerance is True
    assert result.relative_error == 0.0


def test_spec_example_rounding_121_7m():
    # source 121,732,200, claim writes 121.7M (already normalized to
    # 121_700_000.0 by the caller's own M-suffix parsing before this
    # function ever sees it).
    result = compare_numeric_values(121_700_000.0, 121_732_200.0)
    assert result.within_tolerance is True
    assert result.rule_applied == RULE_RELATIVE_ERROR_WITHIN_TOLERANCE
    assert result.relative_error < 0.001
    assert is_consistent_rounding(121_700_000.0, 121_732_200.0)


def test_spec_example_100_vs_102_5_is_within_tolerance():
    result = compare_numeric_values(102.5, 100.0)
    assert result.within_tolerance is True
    assert result.rule_applied == RULE_RELATIVE_ERROR_WITHIN_TOLERANCE
    assert abs(result.relative_error - 0.025) < 1e-9


def test_spec_example_growth_rate_20_vs_20_5_percentage_points():
    # Source growth rate 20%, claim writes 20.5% -- stated as a difference
    # of 0.5 percentage points, but the RELATIVE error (as fractions, i.e.
    # 0.20 vs 0.205) is 2.5%, not 0.5%. Both numbers must be saved
    # separately per the spec ("同时保存两个差异，不能混淆") -- this test
    # only exercises the relative-error side, on the normalized fraction
    # values (0.20, 0.205), matching how _parse_claim_numbers already
    # converts a "%" suffix.
    result = compare_numeric_values(0.205, 0.20)
    assert result.within_tolerance is True
    assert abs(result.relative_error - 0.025) < 1e-9
    # The absolute percentage-point difference is a SEPARATE number the
    # caller computes directly (0.205 - 0.20 = 0.005 = 0.5 points) -- not
    # this function's own relative_error, confirmed distinct here.
    assert abs(result.absolute_difference - 0.005) < 1e-9
    assert abs(result.absolute_difference - result.relative_error) > 0.01


def test_just_over_three_percent_exceeds_tolerance():
    result = compare_numeric_values(103.01, 100.0)
    assert result.within_tolerance is False
    assert result.rule_applied == RULE_EXCEEDS_TOLERANCE


def test_exactly_three_percent_is_within_tolerance_boundary_inclusive():
    result = compare_numeric_values(103.0, 100.0)
    assert result.within_tolerance is True
    assert result.rule_applied == RULE_RELATIVE_ERROR_WITHIN_TOLERANCE


def test_spec_example_breaks_100_vs_actual_99_not_excused_by_raw_relative_error():
    # The spec's own explicit warning: claim asserts "breaks 100", source is
    # actually 99 -- only ~1% relative error, but this is a THRESHOLD-
    # CROSSING case this module alone must never resolve as "fine". This
    # test documents that this function's own within_tolerance=True verdict
    # is NOT sufficient on its own -- a caller must separately check
    # whether the claim's own asserted threshold (100) was actually crossed
    # by the real source value (99), which this function does not know
    # about at all (it only ever compares two bare numbers, never a
    # claim's own stated threshold semantics). This is exactly why section
    # 五.3's exceptions are the CALLER's responsibility, not this module's.
    result = compare_numeric_values(100.0, 99.0)
    assert result.within_tolerance is True  # correct, narrow answer: 99 and 100 are numerically close
    # The caller (never this function) is responsible for noticing that
    # "100" was the claim's own asserted crossing-threshold and that 99
    # does not actually cross it -- documented here, not enforced here.


def test_zero_source_uses_absolute_tolerance_not_relative():
    result = compare_numeric_values(0.005, 0.0)
    assert result.relative_error is None
    assert result.rule_applied == RULE_ZERO_OR_NEAR_ZERO_SOURCE_ABSOLUTE_CHECK
    assert result.within_tolerance is True


def test_zero_source_large_claim_value_exceeds_absolute_tolerance():
    result = compare_numeric_values(5.0, 0.0)
    assert result.relative_error is None
    assert result.rule_applied == RULE_ZERO_OR_NEAR_ZERO_SOURCE_ABSOLUTE_CHECK
    assert result.within_tolerance is False


def test_negative_values_use_absolute_difference_correctly():
    result = compare_numeric_values(-103.0, -100.0)
    assert result.within_tolerance is True
    assert result.rule_applied == RULE_RELATIVE_ERROR_WITHIN_TOLERANCE


def test_sign_flip_is_not_a_small_relative_error_case():
    # +100 vs -100: absolute_difference=200, relative_error=2.0 (200%) --
    # correctly NOT within tolerance; this module does not need a special
    # sign-flip rule because the relative-error math already rejects it,
    # but this test documents that fact explicitly rather than assuming it.
    result = compare_numeric_values(100.0, -100.0)
    assert result.within_tolerance is False
    assert result.rule_applied == RULE_EXCEEDS_TOLERANCE


def test_is_consistent_rounding_true_for_display_rounding():
    assert is_consistent_rounding(121.7, 121.732) is True  # same rounding relationship at a smaller scale
    assert is_consistent_rounding(121_700_000.0, 121_732_200.0) is True


def test_is_consistent_rounding_false_for_unrelated_numbers():
    assert is_consistent_rounding(50.0, 121_732_200.0) is False


def test_explanation_field_is_populated_and_traceable():
    result = compare_numeric_values(102.5, 100.0)
    assert "relative_error" in result.explanation
    assert "100.0" in result.explanation or "100" in result.explanation
