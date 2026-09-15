"""Tests for v0.1.3 MSFT A304 Negation-Aware Structure Extraction.

Covers the bounded, ticker-independent source-factor normalization added to
comqutor_alpha/structure_engine/factor_normalizer.py (FACTOR_ALIAS_PATTERNS,
Revenue Growth adverse-direction phrasing) and its consumption by
relation_grammar.py's clause-local span matching. No new negation logic was
added -- these tests confirm the EXISTING assertion_status_for()/
analyze_claim_semantics() negation machinery and the existing
`assertion_status != negated` downstream qualification gate already suppress
false-positive causal edges once the new factor-recognition gap is closed.

Design authority: docs/audit_artifacts/v0_1_3_msft_a304_negation_extraction_fix.md
"""

from __future__ import annotations

from comqutor_alpha.structure_engine.factor_normalizer import (
    extract_known_factors_from_text,
)
from comqutor_alpha.structure_engine.structure_extractor import (
    _extract_edges,
    _extract_factors,
)


def _record(claim: str, ticker: str = "MSFT", claim_id: str = "test:claim:1", factors=None):
    return {
        "ticker": ticker,
        "claim": claim,
        "evidence": claim,
        "claim_id": claim_id,
        "factors": factors or [],
    }


def _edges_for(claim: str, ticker: str = "MSFT"):
    record = _record(claim, ticker=ticker)
    factors = _extract_factors(record)
    return factors, _extract_edges(record, factors)


CANONICAL_CLAIM = "Any slowdown in Azure growth could trigger multiple compression."


# --- Canonical positive claim -----------------------------------------------


def test_canonical_positive_claim_extracts_causal_edge():
    factors, edges = _edges_for(CANONICAL_CLAIM)
    assert "Revenue Growth" in factors
    assert "Valuation Risk" in factors
    causal = [e for e in edges if e["edge_type"] == "causal"]
    assert len(causal) == 1
    assert causal[0]["assertion_status"] in ("conditional", "asserted")


def test_canonical_positive_claim_correct_edge_direction():
    _, edges = _edges_for(CANONICAL_CLAIM)
    edge = edges[0]
    assert edge["source_label"].endswith("Revenue Growth")
    assert edge["target_label"] == "Valuation Risk"
    # explicit anti-reversal check
    assert not (edge["source_label"] == "Valuation Risk")


# --- Factor normalization ----------------------------------------------------


def test_source_factor_normalized_from_generic_segment_phrasing():
    """"Azure" is claim CONTENT, never a coded trigger -- any segment/product
    noun in the same slot must normalize identically."""
    for segment_phrase in ["cloud growth", "subscription growth", "widget growth"]:
        factors = extract_known_factors_from_text(f"Slowdown in {segment_phrase} could trigger multiple compression.")
        assert "Revenue Growth" in factors, segment_phrase


def test_growth_deterioration_and_deceleration_forms_recognized():
    assert "Revenue Growth" in extract_known_factors_from_text("Growth deterioration may cause multiple contraction.")
    assert "Revenue Growth" in extract_known_factors_from_text("Decelerating revenue growth may pressure valuation multiples.")
    assert "Revenue Growth" in extract_known_factors_from_text("Slower Azure growth may pressure valuation multiples.")


def test_bare_slow_or_weak_tokens_not_treated_as_growth_factor():
    """Explicit anti-overreach control: bare, context-free 'slow'/'weak'
    must never resolve to Revenue Growth -- only the bounded phrase forms."""
    assert "Revenue Growth" not in extract_known_factors_from_text("The market feels slow and weak today.")


# --- Negated premise / consequence / relation --------------------------------


def test_negated_premise_no_false_causal_edge():
    factors, edges = _edges_for("This is not a slowdown scenario.")
    assert factors == []
    assert edges == []


def test_negated_premise_azure_growth_not_slowing_no_adverse_structure():
    factors, edges = _edges_for("Azure growth is not slowing.")
    assert factors == []
    assert edges == []


def test_negated_relation_no_positive_causal_edge():
    factors, edges = _edges_for("Slower growth would not cause multiple compression.")
    assert "Revenue Growth" in factors and "Valuation Risk" in factors
    causal = [e for e in edges if e["edge_type"] == "causal"]
    assert len(causal) == 1
    # the relation IS recognized (proving the mechanism works), but is
    # explicitly tagged negated -- never a positive/asserted causal edge.
    assert causal[0]["assertion_status"] == "negated"


def test_negated_consequence_denial_form():
    factors, edges = _edges_for("There is no reason to expect slower Azure growth to compress valuation.")
    causal = [e for e in edges if e["edge_type"] == "causal"]
    # Either no edge at all, or (if factors pair up) never a positive one.
    assert all(e["assertion_status"] == "negated" for e in causal)


# --- Risk-only / descriptive / unrelated mention -----------------------------


def test_risk_only_language_no_asserted_edge():
    factors, edges = _edges_for("There is a risk of slower Azure growth.")
    assert "Revenue Growth" in factors
    assert edges == []  # no target factor mentioned -> no edge attempted


def test_descriptive_only_no_causal_edge():
    factors, edges = _edges_for("Investors discussed a possible slowdown.")
    assert factors == []
    assert edges == []


def test_unrelated_valuation_mention_no_compression_edge():
    factors, edges = _edges_for("MSFT trades at a high valuation multiple.")
    assert "Valuation Risk" in factors
    assert "Revenue Growth" not in factors
    assert edges == []


def test_growth_is_strong_not_slowing_no_adverse_structure():
    factors, edges = _edges_for("Growth is strong, not slowing.")
    assert factors == []
    assert edges == []


# --- Mixed-clause hard case ---------------------------------------------------


def test_mixed_clause_does_not_fabricate_azure_slowdown_edge():
    """"Azure is not slowing, but valuation could compress if demand
    weakens." must NOT infer Azure slowdown -> multiple compression, and
    must not fabricate a demand-weakens -> valuation edge either, since bare
    "demand" (without an AI/GPU/Inference qualifier) is not a recognized
    factor under the existing, unmodified ontology."""
    factors, edges = _edges_for("Azure is not slowing, but valuation could compress if demand weakens.")
    assert "Revenue Growth" not in factors
    assert edges == []


# --- Boundary honesty: variants that do NOT gain an edge under the existing,
# unmodified TARGET-side ("Valuation Risk") alias set. These prove the fix
# is scoped to the source side only -- not loosened to make examples pass.


def test_pressure_valuation_multiples_variant_has_no_target_alias_yet():
    factors, edges = _edges_for("Decelerating revenue growth may pressure valuation multiples.")
    assert "Revenue Growth" in factors
    assert "Valuation Risk" not in factors  # "valuation multiples" is not an existing alias
    assert edges == []


def test_multiple_contraction_variant_has_no_target_alias_yet():
    factors, edges = _edges_for("Weaker revenue growth could lead to multiple contraction.")
    assert "Revenue Growth" in factors
    assert "Valuation Risk" not in factors  # "multiple contraction" is not an existing alias
    assert edges == []


# --- Ticker independence / no hardcoding -------------------------------------


def test_ticker_independent_behavior():
    for ticker in ["MSFT", "NVDA", "GOOGL", "ZZZZ"]:
        factors, edges = _edges_for("Slowdown in cloud growth could trigger multiple compression.", ticker=ticker)
        assert "Revenue Growth" in factors and "Valuation Risk" in factors
        causal = [e for e in edges if e["edge_type"] == "causal"]
        assert len(causal) == 1
        assert causal[0]["source_label"] == f"{ticker} Revenue Growth"
        assert causal[0]["target_label"] == "Valuation Risk"


def test_no_alpha_id_hardcoding_in_edge_output():
    """Structure extraction never sets alpha_ids directly -- Alpha
    association is a separate, unmodified downstream lineage authority."""
    _, edges = _edges_for(CANONICAL_CLAIM)
    for edge in edges:
        assert "alpha_ids" not in edge


# --- Existing extraction regression controls ---------------------------------


def test_existing_ai_capex_causal_edge_unchanged():
    claim = "AI capex is driving GPU demand higher across hyperscalers."
    factors, edges = _edges_for(claim, ticker="NVDA")
    causal = [e for e in edges if e["edge_type"] == "causal"]
    assert any(e["source_label"] == "AI CapEx" and e["target_label"] == "GPU Demand" for e in causal)


def test_existing_literal_revenue_growth_alias_unaffected():
    factors = extract_known_factors_from_text("Revenue growth accelerated this quarter.")
    assert "Revenue Growth" in factors


def test_existing_valuation_risk_alias_unaffected():
    factors = extract_known_factors_from_text("The stock trades at a rich valuation.")
    assert "Valuation Risk" in factors
