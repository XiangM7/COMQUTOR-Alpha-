"""W4.4 Exposure Engine v1 core tests.

Covers only the pure computational core (``comqutor_alpha/exposure_engine.py``):
formula precision, input validation, batch computation, determinism. Never
reads a formal ``entity_alpha_exposure_seed.yaml`` (it does not exist --
see docs/week4_spec_freeze_audit.md section 13) and never treats a
synthetic unit-test value as a product seed. Never wires the engine into
the research pipeline, an HTTP API, or the database -- none of that exists
in this module or in these tests.
"""

from __future__ import annotations

import copy
import math

import pytest

from comqutor_alpha.exposure_engine import (
    EXPOSURE_FORMULA_VERSION,
    EXPOSURE_WEIGHTS,
    ExposureInputError,
    calculate_exposure,
    compute_entity_alpha_exposures,
)

# A minimal, self-contained taxonomy stub -- only the alpha_id *keys* are
# ever read by compute_entity_alpha_exposures (via ``set(taxonomy)``), so
# any object works as a value. Explicitly NOT the real
# entity_alpha_exposure_seed.yaml (which does not exist) and NOT presented
# as one -- just a synthetic, clearly-fake identifier set for isolated unit
# tests of the batch-computation contract itself.
_FAKE_TAXONOMY = {"FAKE_A": object(), "FAKE_B": object(), "FAKE_C": object()}


# ---------------------------------------------------------------------------
# calculate_exposure: formula precision
# ---------------------------------------------------------------------------


def test_formula_weights_are_exactly_50_30_20():
    assert EXPOSURE_WEIGHTS == {
        "historical_mapping": 0.50,
        "current_evidence": 0.30,
        "agent_confidence": 0.20,
    }


def test_formula_precision_matches_hand_computed_value():
    result = calculate_exposure(historical_mapping=0.8, current_evidence=0.4, agent_confidence=0.6)

    expected = 0.8 * 0.50 + 0.4 * 0.30 + 0.6 * 0.20
    assert result["exposure_score"] == pytest.approx(expected)
    assert result["formula_version"] == EXPOSURE_FORMULA_VERSION


def test_exposure_score_exactly_equals_sum_of_contributions():
    result = calculate_exposure(historical_mapping=0.37, current_evidence=0.91, agent_confidence=0.05)

    components = result["components"]
    total = (
        components["historical_mapping"]["contribution"]
        + components["current_evidence"]["contribution"]
        + components["agent_confidence"]["contribution"]
    )
    assert result["exposure_score"] == total


def test_component_breakdown_reports_raw_weight_and_contribution():
    result = calculate_exposure(historical_mapping=0.5, current_evidence=0.5, agent_confidence=0.5)

    for name, weight in EXPOSURE_WEIGHTS.items():
        component = result["components"][name]
        assert component["raw"] == 0.5
        assert component["weight"] == weight
        assert component["contribution"] == pytest.approx(0.5 * weight)


def test_no_conflict_penalty_or_ranking_bonus_applied():
    result = calculate_exposure(historical_mapping=1.0, current_evidence=1.0, agent_confidence=1.0)
    assert result["exposure_score"] == pytest.approx(1.0)
    assert set(result) == {"formula_version", "exposure_score", "components"}


# ---------------------------------------------------------------------------
# calculate_exposure: 0/1 boundaries
# ---------------------------------------------------------------------------


def test_all_zero_boundary():
    result = calculate_exposure(historical_mapping=0.0, current_evidence=0.0, agent_confidence=0.0)
    assert result["exposure_score"] == 0.0


def test_all_one_boundary():
    result = calculate_exposure(historical_mapping=1.0, current_evidence=1.0, agent_confidence=1.0)
    assert result["exposure_score"] == pytest.approx(1.0)


def test_int_zero_and_one_are_accepted_as_numbers():
    result = calculate_exposure(historical_mapping=0, current_evidence=1, agent_confidence=0)
    assert result["exposure_score"] == pytest.approx(0.30)


# ---------------------------------------------------------------------------
# calculate_exposure: invalid input
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_value", [math.nan, math.inf, -math.inf])
def test_non_finite_values_rejected(bad_value):
    with pytest.raises(ExposureInputError) as exc_info:
        calculate_exposure(historical_mapping=bad_value, current_evidence=0.5, agent_confidence=0.5)
    assert exc_info.value.reason_code == "INVALID_EXPOSURE_INPUT"


def test_bool_rejected_even_though_bool_is_an_int_subclass():
    with pytest.raises(ExposureInputError) as exc_info:
        calculate_exposure(historical_mapping=True, current_evidence=0.5, agent_confidence=0.5)
    assert exc_info.value.reason_code == "INVALID_EXPOSURE_INPUT"

    with pytest.raises(ExposureInputError):
        calculate_exposure(historical_mapping=0.5, current_evidence=False, agent_confidence=0.5)


def test_string_number_rejected_no_implicit_coercion():
    with pytest.raises(ExposureInputError) as exc_info:
        calculate_exposure(historical_mapping="0.5", current_evidence=0.5, agent_confidence=0.5)
    assert exc_info.value.reason_code == "INVALID_EXPOSURE_INPUT"


def test_none_rejected():
    with pytest.raises(ExposureInputError) as exc_info:
        calculate_exposure(historical_mapping=None, current_evidence=0.5, agent_confidence=0.5)
    assert exc_info.value.reason_code == "INVALID_EXPOSURE_INPUT"


def test_negative_number_rejected_not_clamped():
    with pytest.raises(ExposureInputError):
        calculate_exposure(historical_mapping=-0.1, current_evidence=0.5, agent_confidence=0.5)


def test_greater_than_one_rejected_not_clamped():
    with pytest.raises(ExposureInputError):
        calculate_exposure(historical_mapping=1.1, current_evidence=0.5, agent_confidence=0.5)


def test_exception_carries_only_reason_code_no_raw_payload():
    try:
        calculate_exposure(historical_mapping="super-secret-value", current_evidence=0.5, agent_confidence=0.5)
        raise AssertionError("expected ExposureInputError")
    except ExposureInputError as exc:
        assert exc.reason_code == "INVALID_EXPOSURE_INPUT"
        assert "super-secret-value" not in str(exc)


# ---------------------------------------------------------------------------
# compute_entity_alpha_exposures: batch computation
# ---------------------------------------------------------------------------


def test_multi_alpha_batch_computation():
    result = compute_entity_alpha_exposures(
        ticker="SYNTH",
        historical_mapping={"FAKE_A": 0.9, "FAKE_B": 0.2, "FAKE_C": 0.5},
        current_evidence={"FAKE_A": 0.3, "FAKE_B": 0.7, "FAKE_C": 0.5},
        agent_confidence={"FAKE_A": 0.6, "FAKE_B": 0.4, "FAKE_C": 0.5},
        taxonomy=_FAKE_TAXONOMY,
    )

    assert result["formula_version"] == EXPOSURE_FORMULA_VERSION
    assert result["ticker"] == "SYNTH"
    assert [item["alpha_id"] for item in result["exposures"]] == ["FAKE_A", "FAKE_B", "FAKE_C"]

    fake_a = next(item for item in result["exposures"] if item["alpha_id"] == "FAKE_A")
    expected = 0.9 * 0.50 + 0.3 * 0.30 + 0.6 * 0.20
    assert fake_a["exposure_score"] == pytest.approx(expected)


def test_exposures_sorted_by_alpha_id_regardless_of_input_order():
    result = compute_entity_alpha_exposures(
        ticker="SYNTH",
        historical_mapping={"FAKE_C": 0.5, "FAKE_A": 0.9, "FAKE_B": 0.2},
        current_evidence={"FAKE_B": 0.7, "FAKE_C": 0.5, "FAKE_A": 0.3},
        agent_confidence={"FAKE_A": 0.6, "FAKE_C": 0.5, "FAKE_B": 0.4},
        taxonomy=_FAKE_TAXONOMY,
    )
    assert [item["alpha_id"] for item in result["exposures"]] == ["FAKE_A", "FAKE_B", "FAKE_C"]


def test_input_order_does_not_affect_result_values():
    kwargs_a = {
        "ticker": "SYNTH",
        "historical_mapping": {"FAKE_A": 0.9, "FAKE_B": 0.2},
        "current_evidence": {"FAKE_A": 0.3, "FAKE_B": 0.7},
        "agent_confidence": {"FAKE_A": 0.6, "FAKE_B": 0.4},
        "taxonomy": _FAKE_TAXONOMY,
    }
    kwargs_b = {
        "ticker": "SYNTH",
        "historical_mapping": {"FAKE_B": 0.2, "FAKE_A": 0.9},
        "current_evidence": {"FAKE_B": 0.7, "FAKE_A": 0.3},
        "agent_confidence": {"FAKE_B": 0.4, "FAKE_A": 0.6},
        "taxonomy": _FAKE_TAXONOMY,
    }
    assert compute_entity_alpha_exposures(**kwargs_a) == compute_entity_alpha_exposures(**kwargs_b)


def test_input_mappings_are_not_mutated():
    historical = {"FAKE_A": 0.9, "FAKE_B": 0.2}
    evidence = {"FAKE_A": 0.3, "FAKE_B": 0.7}
    confidence = {"FAKE_A": 0.6, "FAKE_B": 0.4}
    historical_copy = copy.deepcopy(historical)
    evidence_copy = copy.deepcopy(evidence)
    confidence_copy = copy.deepcopy(confidence)

    compute_entity_alpha_exposures(
        ticker="SYNTH",
        historical_mapping=historical,
        current_evidence=evidence,
        agent_confidence=confidence,
        taxonomy=_FAKE_TAXONOMY,
    )

    assert historical == historical_copy
    assert evidence == evidence_copy
    assert confidence == confidence_copy


def test_same_input_is_deterministic():
    kwargs = {
        "ticker": "SYNTH",
        "historical_mapping": {"FAKE_A": 0.9, "FAKE_B": 0.2},
        "current_evidence": {"FAKE_A": 0.3, "FAKE_B": 0.7},
        "agent_confidence": {"FAKE_A": 0.6, "FAKE_B": 0.4},
        "taxonomy": _FAKE_TAXONOMY,
    }
    first = compute_entity_alpha_exposures(**kwargs)
    second = compute_entity_alpha_exposures(**kwargs)
    assert first == second


def test_default_path_accepts_real_mvp10_alpha_ids():
    # taxonomy=None -> validates against the static EXPECTED_ALPHA_IDS
    # constant only, never a loaded taxonomy. A101/A304 are real MVP-10
    # alpha_ids; the *values* here are synthetic unit-test inputs, never
    # presented as a product seed.
    result = compute_entity_alpha_exposures(
        ticker="SYNTH",
        historical_mapping={"A101": 0.5, "A304": 0.5},
        current_evidence={"A101": 0.5, "A304": 0.5},
        agent_confidence={"A101": 0.5, "A304": 0.5},
    )
    assert [item["alpha_id"] for item in result["exposures"]] == ["A101", "A304"]


def test_default_path_rejects_unknown_alpha_id():
    with pytest.raises(ExposureInputError) as exc_info:
        compute_entity_alpha_exposures(
            ticker="SYNTH",
            historical_mapping={"NOT_A_REAL_MVP10_ID": 0.5},
            current_evidence={"NOT_A_REAL_MVP10_ID": 0.5},
            agent_confidence={"NOT_A_REAL_MVP10_ID": 0.5},
        )
    assert exc_info.value.reason_code == "UNKNOWN_ALPHA_ID"


def test_default_path_never_reads_any_file(monkeypatch):
    """Proves the pure/no-filesystem contract directly: with every file
    open blocked, taxonomy=None (the default path) must still succeed for
    real MVP-10 alpha_ids -- it can only be validating against the static
    EXPECTED_ALPHA_IDS constant, never opening/parsing
    alpha_taxonomy_v1.yaml or any other file."""
    import pathlib

    def _forbidden_open(self, *args, **kwargs):
        raise AssertionError(f"unexpected filesystem read: {self}")

    monkeypatch.setattr(pathlib.Path, "open", _forbidden_open)

    result = compute_entity_alpha_exposures(
        ticker="SYNTH",
        historical_mapping={"A101": 0.4, "A304": 0.6},
        current_evidence={"A101": 0.5, "A304": 0.5},
        agent_confidence={"A101": 0.5, "A304": 0.5},
    )

    assert [item["alpha_id"] for item in result["exposures"]] == ["A101", "A304"]
    assert result["formula_version"] == EXPOSURE_FORMULA_VERSION


def test_explicit_taxonomy_mapping_seam_still_works():
    result = compute_entity_alpha_exposures(
        ticker="SYNTH",
        historical_mapping={"FAKE_A": 0.5},
        current_evidence={"FAKE_A": 0.5},
        agent_confidence={"FAKE_A": 0.5},
        taxonomy=_FAKE_TAXONOMY,
    )
    assert [item["alpha_id"] for item in result["exposures"]] == ["FAKE_A"]


def test_explicit_taxonomy_non_mapping_rejected():
    with pytest.raises(ExposureInputError) as exc_info:
        compute_entity_alpha_exposures(
            ticker="SYNTH",
            historical_mapping={"FAKE_A": 0.5},
            current_evidence={"FAKE_A": 0.5},
            agent_confidence={"FAKE_A": 0.5},
            taxonomy=["FAKE_A", "FAKE_B"],
        )
    assert exc_info.value.reason_code == "INVALID_EXPOSURE_INPUT"


def test_explicit_taxonomy_key_must_be_nonempty_str():
    with pytest.raises(ExposureInputError) as exc_info:
        compute_entity_alpha_exposures(
            ticker="SYNTH",
            historical_mapping={"FAKE_A": 0.5},
            current_evidence={"FAKE_A": 0.5},
            agent_confidence={"FAKE_A": 0.5},
            taxonomy={"": object()},
        )
    assert exc_info.value.reason_code == "INVALID_EXPOSURE_INPUT"


# ---------------------------------------------------------------------------
# compute_entity_alpha_exposures: invalid input
# ---------------------------------------------------------------------------


def test_unknown_alpha_id_rejected():
    with pytest.raises(ExposureInputError) as exc_info:
        compute_entity_alpha_exposures(
            ticker="SYNTH",
            historical_mapping={"NOT_A_REAL_ALPHA": 0.5},
            current_evidence={"NOT_A_REAL_ALPHA": 0.5},
            agent_confidence={"NOT_A_REAL_ALPHA": 0.5},
            taxonomy=_FAKE_TAXONOMY,
        )
    assert exc_info.value.reason_code == "UNKNOWN_ALPHA_ID"


def test_mapping_key_set_mismatch_rejected_not_defaulted():
    with pytest.raises(ExposureInputError) as exc_info:
        compute_entity_alpha_exposures(
            ticker="SYNTH",
            historical_mapping={"FAKE_A": 0.9, "FAKE_B": 0.2},
            current_evidence={"FAKE_A": 0.3},  # missing FAKE_B -- must not default to 0
            agent_confidence={"FAKE_A": 0.6, "FAKE_B": 0.4},
            taxonomy=_FAKE_TAXONOMY,
        )
    assert exc_info.value.reason_code == "EXPOSURE_INPUT_SET_MISMATCH"


def test_extra_alpha_not_in_historical_mapping_is_rejected_not_auto_added():
    with pytest.raises(ExposureInputError) as exc_info:
        compute_entity_alpha_exposures(
            ticker="SYNTH",
            historical_mapping={"FAKE_A": 0.9},
            current_evidence={"FAKE_A": 0.3, "FAKE_B": 0.7},  # FAKE_B not in historical_mapping
            agent_confidence={"FAKE_A": 0.6},
            taxonomy=_FAKE_TAXONOMY,
        )
    assert exc_info.value.reason_code == "EXPOSURE_INPUT_SET_MISMATCH"


def test_empty_ticker_rejected():
    with pytest.raises(ExposureInputError) as exc_info:
        compute_entity_alpha_exposures(
            ticker="",
            historical_mapping={"FAKE_A": 0.5},
            current_evidence={"FAKE_A": 0.5},
            agent_confidence={"FAKE_A": 0.5},
            taxonomy=_FAKE_TAXONOMY,
        )
    assert exc_info.value.reason_code == "INVALID_TICKER"


def test_non_string_ticker_rejected():
    with pytest.raises(ExposureInputError) as exc_info:
        compute_entity_alpha_exposures(
            ticker=None,
            historical_mapping={"FAKE_A": 0.5},
            current_evidence={"FAKE_A": 0.5},
            agent_confidence={"FAKE_A": 0.5},
            taxonomy=_FAKE_TAXONOMY,
        )
    assert exc_info.value.reason_code == "INVALID_TICKER"


def test_batch_propagates_calculate_exposure_input_validation():
    with pytest.raises(ExposureInputError) as exc_info:
        compute_entity_alpha_exposures(
            ticker="SYNTH",
            historical_mapping={"FAKE_A": math.nan},
            current_evidence={"FAKE_A": 0.5},
            agent_confidence={"FAKE_A": 0.5},
            taxonomy=_FAKE_TAXONOMY,
        )
    assert exc_info.value.reason_code == "INVALID_EXPOSURE_INPUT"


def test_non_mapping_historical_mapping_rejected():
    with pytest.raises(ExposureInputError) as exc_info:
        compute_entity_alpha_exposures(
            ticker="SYNTH",
            historical_mapping=["FAKE_A", 0.5],
            current_evidence={"FAKE_A": 0.5},
            agent_confidence={"FAKE_A": 0.5},
            taxonomy=_FAKE_TAXONOMY,
        )
    assert exc_info.value.reason_code == "INVALID_EXPOSURE_INPUT"
