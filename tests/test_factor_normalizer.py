import inspect

from comqutor_alpha.structure_engine.factor_normalizer import (
    extract_known_factors_from_text,
    normalize_factor_label,
)


def test_normalize_factor_label_canonical_form_is_stable():
    assert normalize_factor_label("AI Demand") == "AI Demand"


def test_normalize_factor_label_handles_lowercase_alias():
    assert normalize_factor_label("AI demand") == "AI Demand"


def test_normalize_factor_label_handles_spelled_out_alias():
    assert normalize_factor_label("artificial intelligence demand") == "AI Demand"


def test_normalize_factor_label_handles_ai_capex_alias():
    assert normalize_factor_label("ai capex") == "AI CapEx"


def test_normalize_factor_label_handles_gpu_demand_alias():
    assert normalize_factor_label("gpu demand") == "GPU Demand"


def test_normalize_factor_label_empty_value_returns_unknown():
    assert normalize_factor_label("") == "Unknown"
    assert normalize_factor_label(None) == "Unknown"


def test_extract_known_factors_detects_valuation_risk_phrasing():
    assert "Valuation Risk" in extract_known_factors_from_text(
        "The stock carries rich valuation risk."
    )
    assert "Valuation Risk" in extract_known_factors_from_text(
        "Any disappointment could trigger multiple compression."
    )


def test_no_circular_import_between_mapper_and_extractor():
    """alpha_mapper.py and structure_extractor.py must both depend on
    factor_normalizer.py rather than on each other, so importing either
    module alone (in either order) must never fail.
    """
    import comqutor_alpha.structure_engine.structure_extractor  # noqa: F401
    import comqutor_alpha.structure_engine.alpha_mapper  # noqa: F401


def test_structure_extractor_does_not_import_alpha_mapper():
    from comqutor_alpha.structure_engine import structure_extractor

    source = inspect.getsource(structure_extractor)
    assert "alpha_mapper" not in source
