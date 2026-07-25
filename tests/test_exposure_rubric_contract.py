"""Entity Alpha Exposure Rubric Contract v1 -- freeze tests.

Covers: strict load/validate of the canonical YAML, MVP-10 assignment
completeness, taxonomy consistency, deterministic scoring, the semantic
fingerprint (and its immutability guarantee), and package-resource loading.
No entity Seed data, no ticker, no pipeline/API/frontend/Activation/Conflict
wiring is exercised or created here -- this file only proves the contract
itself is frozen and correct.
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest
import yaml

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.exposure.rubric_contract import (
    CONTRACT_RESOURCE_NAME,
    EXPECTED_ALLOWED_IMPACT_SEMANTICS,
    EXPECTED_MVP10_ALPHA_IDS,
    ExposureContractError,
    compute_contract_fingerprint,
    compute_structural_exposure,
    load_exposure_rubric_contract,
    validate_exposure_rubric_contract,
)

FROZEN_V1_FINGERPRINT = "98348e1f8de82013dd50874c90daf084af03df33aaa8f398b2cc3cc2ae612c0c"

EXPECTED_RUBRIC_IDS = {
    "rate_sensitivity_rubric.v1",
    "liquidity_sensitivity_rubric.v1",
    "operating_theme_rubric.v1",
    "industry_cycle_rubric.v1",
    "fundamental_growth_rubric.v1",
    "valuation_risk_rubric.v1",
    "recession_sensitivity_rubric.v1",
    "narrative_reflexivity_rubric.v1",
}

EXPECTED_RUBRIC_WEIGHTS = {
    "rate_sensitivity_rubric.v1": {
        "equity_duration_sensitivity": 0.35,
        "financing_cost_sensitivity": 0.25,
        "rate_sensitive_end_demand": 0.25,
        "transmission_persistence": 0.15,
    },
    "liquidity_sensitivity_rubric.v1": {
        "risk_appetite_beta": 0.30,
        "external_financing_dependence": 0.25,
        "flow_positioning_sensitivity": 0.25,
        "liquidity_to_business_transmission": 0.20,
    },
    "operating_theme_rubric.v1": {
        "direct_product_service_exposure": 0.35,
        "economic_materiality": 0.30,
        "end_market_dependence": 0.20,
        "exposure_persistence": 0.15,
    },
    "industry_cycle_rubric.v1": {
        "industry_revenue_concentration": 0.30,
        "cycle_operating_leverage": 0.30,
        "inventory_pricing_sensitivity": 0.25,
        "capex_order_cycle_sensitivity": 0.15,
    },
    "fundamental_growth_rubric.v1": {
        "demand_to_revenue_conversion": 0.30,
        "estimate_revision_sensitivity": 0.25,
        "operating_leverage": 0.25,
        "growth_visibility_persistence": 0.20,
    },
    "valuation_risk_rubric.v1": {
        "valuation_premium": 0.30,
        "cash_flow_duration": 0.25,
        "expectation_crowding": 0.25,
        "discount_rate_sensitivity": 0.20,
    },
    "recession_sensitivity_rubric.v1": {
        "cyclical_demand_exposure": 0.30,
        "fixed_cost_operating_leverage": 0.25,
        "balance_sheet_refinancing_risk": 0.25,
        "customer_credit_sensitivity": 0.20,
    },
    "narrative_reflexivity_rubric.v1": {
        "thematic_purity": 0.30,
        "attention_intensity": 0.25,
        "flow_positioning_sensitivity": 0.25,
        "price_reflexivity_dependence": 0.20,
    },
}

EXPECTED_ASSIGNMENTS = {
    "A001": ("Rate Cut Cycle", "rate_sensitivity_rubric.v1", "supportive_sensitivity"),
    "A003": ("Liquidity Expansion", "liquidity_sensitivity_rubric.v1", "supportive_sensitivity"),
    "A101": ("AI Expansion", "operating_theme_rubric.v1", "supportive_sensitivity"),
    "A102": ("Inference Explosion", "operating_theme_rubric.v1", "supportive_sensitivity"),
    "A103": ("AI Infrastructure", "operating_theme_rubric.v1", "supportive_sensitivity"),
    "A201": ("Semiconductor Supercycle", "industry_cycle_rubric.v1", "supportive_sensitivity"),
    "A301": ("Revenue Expansion", "fundamental_growth_rubric.v1", "supportive_sensitivity"),
    "A304": ("Multiple Compression", "valuation_risk_rubric.v1", "adverse_sensitivity"),
    "A501": ("Recession Risk", "recession_sensitivity_rubric.v1", "adverse_sensitivity"),
    "A601": ("Narrative Momentum", "narrative_reflexivity_rubric.v1", "reflexive_dependency"),
}


@pytest.fixture(scope="module")
def contract():
    return load_exposure_rubric_contract()


def _contract_yaml_path() -> Path:
    return Path(__file__).resolve().parents[1] / "comqutor_alpha" / "exposure" / CONTRACT_RESOURCE_NAME


# ---------------------------------------------------------------------------
# 1-6: top-level fixed values
# ---------------------------------------------------------------------------


class TestTopLevelFixedValues:
    def test_contract_loads(self, contract):
        assert isinstance(contract, dict)

    def test_schema_version_exact(self, contract):
        assert contract["schema_version"] == "comqutor.entity_alpha_exposure_rubric_contract.v1"

    def test_contract_version_exact(self, contract):
        assert contract["contract_version"] == "exposure-rubric-contract-v1"

    def test_taxonomy_version_exact(self, contract):
        assert contract["taxonomy_version"] == "alpha_taxonomy_v1"

    def test_score_scale_exact(self, contract):
        assert contract["score_scale"] == [0.00, 0.25, 0.50, 0.75, 1.00]

    def test_score_semantics_exact(self, contract):
        scale = contract["score_semantics"]["scale"]
        assert {float(k): v for k, v in scale.items()} == {
            0.00: "none_confirmed",
            0.25: "peripheral",
            0.50: "meaningful",
            0.75: "major",
            1.00: "core",
        }
        assert contract["score_semantics"]["missing_exposure_semantics"]
        assert "no_seed" in contract["score_semantics"]["missing_exposure_semantics"]


# ---------------------------------------------------------------------------
# 7-9: eight rubrics, four dimensions each, weights sum to 1.0
# ---------------------------------------------------------------------------


class TestRubricStructure:
    def test_exactly_eight_rubrics_present(self, contract):
        assert set(contract["rubrics"]) == EXPECTED_RUBRIC_IDS

    @pytest.mark.parametrize("rubric_id", sorted(EXPECTED_RUBRIC_WEIGHTS))
    def test_rubric_has_exactly_four_dimensions(self, contract, rubric_id):
        assert len(contract["rubrics"][rubric_id]["dimensions"]) == 4

    @pytest.mark.parametrize("rubric_id", sorted(EXPECTED_RUBRIC_WEIGHTS))
    def test_rubric_dimension_weights_match_and_sum_to_one(self, contract, rubric_id):
        dimensions = contract["rubrics"][rubric_id]["dimensions"]
        actual = {d["dimension_id"]: d["weight"] for d in dimensions}
        assert actual == EXPECTED_RUBRIC_WEIGHTS[rubric_id]
        assert abs(sum(actual.values()) - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# 10-18: MVP-10 assignment table
# ---------------------------------------------------------------------------


class TestAlphaAssignments:
    def test_assignment_set_exact(self, contract):
        assert set(contract["alpha_assignments"]) == EXPECTED_MVP10_ALPHA_IDS
        assert {
            "A001", "A003", "A101", "A102", "A103", "A201", "A301", "A304", "A501", "A601",
        } == EXPECTED_MVP10_ALPHA_IDS

    def test_every_alpha_mapped_exactly_once(self, contract):
        assignments = contract["alpha_assignments"]
        assert len(assignments) == len(set(assignments)) == 10

    @pytest.mark.parametrize("alpha_id", sorted(EXPECTED_ASSIGNMENTS))
    def test_assignment_matches_frozen_table(self, contract, alpha_id):
        name, rubric_id, impact = EXPECTED_ASSIGNMENTS[alpha_id]
        assignment = contract["alpha_assignments"][alpha_id]
        assert assignment["name"] == name
        assert assignment["rubric_id"] == rubric_id
        assert assignment["impact_semantics"] == impact

    def test_alpha_name_matches_taxonomy_exactly(self, contract):
        taxonomy = load_alpha_taxonomy()
        for alpha_id, assignment in contract["alpha_assignments"].items():
            assert assignment["name"] == taxonomy[alpha_id].name_en

    def test_a101_a102_a103_use_operating_theme_rubric(self, contract):
        for alpha_id in ("A101", "A102", "A103"):
            assert contract["alpha_assignments"][alpha_id]["rubric_id"] == "operating_theme_rubric.v1"

    def test_a102_scope_excludes_generic_ai_datacenter_semiconductor(self, contract):
        scope_definition = contract["alpha_assignments"]["A102"]["scope_definition"].lower()
        assert "generic ai" in scope_definition or "must not be treated" in scope_definition
        assert "inference" in scope_definition

    def test_a304_uses_valuation_risk_rubric(self, contract):
        assert contract["alpha_assignments"]["A304"]["rubric_id"] == "valuation_risk_rubric.v1"
        assert contract["alpha_assignments"]["A304"]["impact_semantics"] == "adverse_sensitivity"

    def test_a501_uses_recession_sensitivity_rubric(self, contract):
        assert contract["alpha_assignments"]["A501"]["rubric_id"] == "recession_sensitivity_rubric.v1"
        assert contract["alpha_assignments"]["A501"]["impact_semantics"] == "adverse_sensitivity"

    def test_a601_uses_narrative_reflexivity_rubric(self, contract):
        assert contract["alpha_assignments"]["A601"]["rubric_id"] == "narrative_reflexivity_rubric.v1"
        assert contract["alpha_assignments"]["A601"]["impact_semantics"] == "reflexive_dependency"

    def test_impact_semantics_exact_for_every_alpha(self, contract):
        for alpha_id, (_, _, impact) in EXPECTED_ASSIGNMENTS.items():
            assert contract["alpha_assignments"][alpha_id]["impact_semantics"] == impact
        assert {
            "supportive_sensitivity", "adverse_sensitivity", "reflexive_dependency",
        } == EXPECTED_ALLOWED_IMPACT_SEMANTICS

    def test_only_operating_theme_assignments_carry_scope(self, contract):
        for alpha_id, assignment in contract["alpha_assignments"].items():
            has_scope = "scope_key" in assignment or "scope_definition" in assignment
            if alpha_id in ("A101", "A102", "A103"):
                assert has_scope
            else:
                assert not has_scope


# ---------------------------------------------------------------------------
# 19-34: strict validator rejection tests
# ---------------------------------------------------------------------------


def _valid_payload(contract):
    return copy.deepcopy(contract)


class TestStrictValidatorRejections:
    def test_unknown_top_level_field_rejected(self, contract):
        payload = _valid_payload(contract)
        payload["unexpected_field"] = "x"
        with pytest.raises(ExposureContractError):
            validate_exposure_rubric_contract(payload)

    def test_missing_top_level_field_rejected(self, contract):
        payload = _valid_payload(contract)
        del payload["score_scale"]
        with pytest.raises(ExposureContractError):
            validate_exposure_rubric_contract(payload)

    def test_unknown_rubric_field_rejected(self, contract):
        payload = _valid_payload(contract)
        payload["rubrics"]["rate_sensitivity_rubric.v1"]["extra"] = "x"
        with pytest.raises(ExposureContractError):
            validate_exposure_rubric_contract(payload)

    def test_unknown_dimension_field_rejected(self, contract):
        payload = _valid_payload(contract)
        payload["rubrics"]["rate_sensitivity_rubric.v1"]["dimensions"][0]["extra"] = "x"
        with pytest.raises(ExposureContractError):
            validate_exposure_rubric_contract(payload)

    def test_missing_dimension_rejected(self, contract):
        payload = _valid_payload(contract)
        payload["rubrics"]["rate_sensitivity_rubric.v1"]["dimensions"].pop()
        with pytest.raises(ExposureContractError):
            validate_exposure_rubric_contract(payload)

    def test_fifth_dimension_rejected(self, contract):
        payload = _valid_payload(contract)
        dims = payload["rubrics"]["rate_sensitivity_rubric.v1"]["dimensions"]
        extra = copy.deepcopy(dims[0])
        extra["dimension_id"] = "an_extra_fifth_dimension"
        dims.append(extra)
        with pytest.raises(ExposureContractError):
            validate_exposure_rubric_contract(payload)

    def test_weight_not_summing_to_one_rejected(self, contract):
        payload = _valid_payload(contract)
        payload["rubrics"]["rate_sensitivity_rubric.v1"]["dimensions"][0]["weight"] = 0.99
        with pytest.raises(ExposureContractError):
            validate_exposure_rubric_contract(payload)

    def test_negative_weight_rejected(self, contract):
        payload = _valid_payload(contract)
        dims = payload["rubrics"]["rate_sensitivity_rubric.v1"]["dimensions"]
        dims[0]["weight"] = -0.35
        dims[1]["weight"] = dims[1]["weight"] + 0.70  # keep the (irrelevant) sum near 1.0
        with pytest.raises(ExposureContractError):
            validate_exposure_rubric_contract(payload)

    @pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
    def test_nan_infinity_weight_rejected(self, contract, bad_value):
        payload = _valid_payload(contract)
        payload["rubrics"]["rate_sensitivity_rubric.v1"]["dimensions"][0]["weight"] = bad_value
        with pytest.raises(ExposureContractError):
            validate_exposure_rubric_contract(payload)

    def test_assignment_referencing_unknown_rubric_rejected(self, contract):
        payload = _valid_payload(contract)
        payload["alpha_assignments"]["A001"]["rubric_id"] = "does_not_exist_rubric.v1"
        with pytest.raises(ExposureContractError):
            validate_exposure_rubric_contract(payload)

    def test_duplicate_alpha_assignment_key_in_yaml_does_not_silently_multiply(self, contract):
        # PyYAML's loader keeps the *last* value for a repeated mapping key
        # rather than raising or merging. If a future edit to the source
        # YAML accidentally duplicated an alpha_id key, this proves the
        # parsed result is still exactly one entry (never two, never a
        # silently summed/appended value) -- and that the resulting
        # (necessarily taxonomy-mismatched) content is still rejected.
        raw_path = _contract_yaml_path()
        original_text = raw_path.read_text(encoding="utf-8")
        needle = "  A001:\n    name: Rate Cut Cycle"
        assert original_text.count(needle) == 1
        duplicated_text = original_text.replace(
            needle,
            needle + "\n  A001:\n    name: Rate Cut Cycle (duplicate)",
        )
        payload = yaml.safe_load(duplicated_text)
        assert len(payload["alpha_assignments"]) == len(contract["alpha_assignments"]) == 10
        assert payload["alpha_assignments"]["A001"]["name"] == "Rate Cut Cycle (duplicate)"
        with pytest.raises(ExposureContractError):
            validate_exposure_rubric_contract(payload)

    def test_missing_mvp_alpha_rejected(self, contract):
        payload = _valid_payload(contract)
        del payload["alpha_assignments"]["A601"]
        with pytest.raises(ExposureContractError):
            validate_exposure_rubric_contract(payload)

    def test_extra_non_mvp_alpha_rejected(self, contract):
        payload = _valid_payload(contract)
        payload["alpha_assignments"]["A999"] = dict(payload["alpha_assignments"]["A001"])
        with pytest.raises(ExposureContractError):
            validate_exposure_rubric_contract(payload)

    def test_taxonomy_name_mismatch_rejected(self, contract):
        payload = _valid_payload(contract)
        payload["alpha_assignments"]["A001"]["name"] = "Totally Wrong Name"
        with pytest.raises(ExposureContractError):
            validate_exposure_rubric_contract(payload)

    def test_taxonomy_version_mismatch_rejected(self, contract):
        payload = _valid_payload(contract)
        payload["taxonomy_version"] = "alpha_taxonomy_v2"
        with pytest.raises(ExposureContractError):
            validate_exposure_rubric_contract(payload)

    def test_illegal_impact_semantics_rejected(self, contract):
        payload = _valid_payload(contract)
        payload["alpha_assignments"]["A001"]["impact_semantics"] = "made_up_semantics"
        with pytest.raises(ExposureContractError):
            validate_exposure_rubric_contract(payload)

    def test_illegal_score_scale_rejected(self, contract):
        payload = _valid_payload(contract)
        payload["score_scale"] = [0.0, 0.2, 0.5, 0.75, 1.0]
        with pytest.raises(ExposureContractError):
            validate_exposure_rubric_contract(payload)

    def test_scope_fields_on_non_theme_alpha_rejected(self, contract):
        payload = _valid_payload(contract)
        payload["alpha_assignments"]["A001"]["scope_key"] = "should_not_be_here"
        with pytest.raises(ExposureContractError):
            validate_exposure_rubric_contract(payload)

    def test_missing_scope_fields_on_theme_alpha_rejected(self, contract):
        payload = _valid_payload(contract)
        del payload["alpha_assignments"]["A101"]["scope_key"]
        del payload["alpha_assignments"]["A101"]["scope_definition"]
        with pytest.raises(ExposureContractError):
            validate_exposure_rubric_contract(payload)


# ---------------------------------------------------------------------------
# 35-40: deterministic compute
# ---------------------------------------------------------------------------


class TestComputeStructuralExposure:
    def test_example_computation(self, contract):
        result = compute_structural_exposure(
            "operating_theme_rubric.v1",
            {
                "direct_product_service_exposure": 0.75,
                "economic_materiality": 0.50,
                "end_market_dependence": 0.75,
                "exposure_persistence": 1.00,
            },
            contract=contract,
        )
        expected = 0.75 * 0.35 + 0.50 * 0.30 + 0.75 * 0.20 + 1.00 * 0.15
        assert result == pytest.approx(round(expected, 4))

    def test_missing_dimension_rejected(self, contract):
        with pytest.raises(ExposureContractError):
            compute_structural_exposure(
                "operating_theme_rubric.v1",
                {
                    "direct_product_service_exposure": 0.75,
                    "economic_materiality": 0.50,
                    "end_market_dependence": 0.75,
                },
                contract=contract,
            )

    def test_extra_unknown_dimension_rejected(self, contract):
        with pytest.raises(ExposureContractError):
            compute_structural_exposure(
                "operating_theme_rubric.v1",
                {
                    "direct_product_service_exposure": 0.75,
                    "economic_materiality": 0.50,
                    "end_market_dependence": 0.75,
                    "exposure_persistence": 1.00,
                    "not_a_real_dimension": 0.25,
                },
                contract=contract,
            )

    def test_off_scale_score_rejected(self, contract):
        with pytest.raises(ExposureContractError):
            compute_structural_exposure(
                "operating_theme_rubric.v1",
                {
                    "direct_product_service_exposure": 0.6,
                    "economic_materiality": 0.50,
                    "end_market_dependence": 0.75,
                    "exposure_persistence": 1.00,
                },
                contract=contract,
            )

    def test_output_is_finite_and_in_unit_interval(self, contract):
        result = compute_structural_exposure(
            "narrative_reflexivity_rubric.v1",
            {
                "thematic_purity": 1.0,
                "attention_intensity": 1.0,
                "flow_positioning_sensitivity": 1.0,
                "price_reflexivity_dependence": 1.0,
            },
            contract=contract,
        )
        assert math.isfinite(result)
        assert 0.0 <= result <= 1.0
        assert result == 1.0

    def test_input_order_does_not_affect_result(self, contract):
        scores_a = {
            "direct_product_service_exposure": 0.25,
            "economic_materiality": 0.75,
            "end_market_dependence": 0.50,
            "exposure_persistence": 0.00,
        }
        scores_b = dict(reversed(list(scores_a.items())))
        result_a = compute_structural_exposure("operating_theme_rubric.v1", scores_a, contract=contract)
        result_b = compute_structural_exposure("operating_theme_rubric.v1", scores_b, contract=contract)
        assert result_a == result_b

    def test_unknown_rubric_id_rejected(self, contract):
        with pytest.raises(ExposureContractError):
            compute_structural_exposure("not_a_real_rubric.v1", {}, contract=contract)


# ---------------------------------------------------------------------------
# 41-44: semantic fingerprint
# ---------------------------------------------------------------------------


class TestSemanticFingerprint:
    def test_fingerprint_is_stable_across_repeated_calls(self, contract):
        assert compute_contract_fingerprint(contract) == compute_contract_fingerprint(contract)

    def test_yaml_formatting_change_does_not_affect_fingerprint(self, contract):
        # Re-parse the same file's text with different (but semantically
        # equivalent) YAML formatting: different key order, extra blank
        # lines, and a comment. The fingerprint must be identical.
        raw_path = _contract_yaml_path()
        original_text = raw_path.read_text(encoding="utf-8")
        payload = yaml.safe_load(original_text)

        reformatted_text = "# a harmless comment\n\n\n" + yaml.safe_dump(
            payload, sort_keys=False, default_flow_style=False
        )
        reformatted_payload = yaml.safe_load(reformatted_text)

        assert compute_contract_fingerprint(payload) == compute_contract_fingerprint(reformatted_payload)

    def test_semantic_change_changes_fingerprint(self, contract):
        mutated = copy.deepcopy(contract)
        mutated["rubrics"]["rate_sensitivity_rubric.v1"]["dimensions"][0]["definition"] += " (mutated)"
        assert compute_contract_fingerprint(mutated) != compute_contract_fingerprint(contract)

    def test_frozen_expected_fingerprint(self, contract):
        assert compute_contract_fingerprint(contract) == FROZEN_V1_FINGERPRINT


# ---------------------------------------------------------------------------
# 45-46: package resource loading
# ---------------------------------------------------------------------------


class TestPackageResourceLoading:
    def test_loads_via_importlib_resources(self):
        payload = load_exposure_rubric_contract()
        assert payload["schema_version"] == "comqutor.entity_alpha_exposure_rubric_contract.v1"

    def test_does_not_depend_on_working_directory(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        payload = load_exposure_rubric_contract()
        assert payload["contract_version"] == "exposure-rubric-contract-v1"

    def test_module_never_hardcodes_a_local_absolute_path(self):
        import comqutor_alpha.exposure.rubric_contract as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "/Users/" not in source
        assert "/home/" not in source


# ---------------------------------------------------------------------------
# 47-50: no entity/seed/pipeline content
# ---------------------------------------------------------------------------


class TestNoEntitySeedOrPipelineContent:
    def test_no_entities_in_contract(self, contract):
        serialized = json.dumps(contract).lower()
        for forbidden in ("nvda", "sndk", '"mu"', "ticker"):
            assert forbidden not in serialized

    def test_no_ticker_field_anywhere(self, contract):
        assert "ticker" not in json.dumps(contract).lower()

    def test_no_actual_seed_scores_present(self, contract):
        # The contract only ever declares dimension *definitions* and
        # *weights* -- never a concrete per-entity dimension score value.
        for rubric in contract["rubrics"].values():
            for dimension in rubric["dimensions"]:
                assert set(dimension) == {"dimension_id", "weight", "definition"}

    def test_no_activation_or_conflict_weights_present(self, contract):
        serialized = json.dumps(contract).lower()
        for forbidden in ("activation_score", "conflict_score", "contradiction_weight"):
            assert forbidden not in serialized
