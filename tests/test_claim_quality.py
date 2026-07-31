"""Unified Claim Admissibility and Context-Only Routing Sprint.

Unit tests for ``comqutor_alpha.structure_engine.claim_quality``: the
deterministic ANALYTICAL / CONTEXT_ONLY / NON_SUBSTANTIVE classifier and the
shared ``is_claim_eligible`` downstream eligibility matrix.
"""

from __future__ import annotations

import pytest

from comqutor_alpha.structure_engine.claim_quality import (
    CONSUMER_ACTIVATION,
    CONSUMER_ANALYTICAL_PERSISTENCE,
    CONSUMER_CONFLICT,
    CONSUMER_MAPPING,
    CONSUMER_PRODUCT_FINDINGS,
    CONSUMER_STRUCTURE,
    QUALITY_ANALYTICAL,
    QUALITY_CONTEXT_ONLY,
    QUALITY_NON_SUBSTANTIVE,
    classify_claim_quality,
    is_claim_eligible,
)

# ---------------------------------------------------------------------------
# Required NON_SUBSTANTIVE sentences
# ---------------------------------------------------------------------------

NON_SUBSTANTIVE_SENTENCES = (
    "I now have all the data needed.",
    "Let me synthesize everything.",
    "I will now compile the report.",
    "Here is the comprehensive report.",
    "Moving on to the next section.",
)


@pytest.mark.parametrize("text", NON_SUBSTANTIVE_SENTENCES)
def test_process_language_is_non_substantive(text):
    result = classify_claim_quality(text, text)
    assert result.quality_class == QUALITY_NON_SUBSTANTIVE


@pytest.mark.parametrize("text", NON_SUBSTANTIVE_SENTENCES)
def test_process_language_is_non_substantive_even_with_real_entities(text):
    """The run's ticker is unconditionally present in every real claim's
    ``entities`` (see structured_output_adapter.extract_entities), so this
    is the harder, real-world-representative case: bare entity presence
    must never smuggle process language past the meta-commentary/transition
    hard-reject checks."""
    result = classify_claim_quality(text, text, entities=["NVDA"], direction="unknown")
    assert result.quality_class == QUALITY_NON_SUBSTANTIVE


def test_unknown_placeholder_is_non_substantive():
    result = classify_claim_quality("unknown", "unknown")
    assert result.quality_class == QUALITY_NON_SUBSTANTIVE
    assert "PLACEHOLDER_UNKNOWN" in result.reason_codes


def test_empty_text_is_non_substantive():
    result = classify_claim_quality("", "")
    assert result.quality_class == QUALITY_NON_SUBSTANTIVE


def test_disclaimer_only_is_non_substantive():
    text = "This report is not investment advice and is for informational purposes only."
    result = classify_claim_quality(text, text)
    assert result.quality_class == QUALITY_NON_SUBSTANTIVE
    assert "DISCLAIMER_ONLY" in result.reason_codes


def test_process_language_with_real_substance_is_not_rejected():
    """Mirrors the pre-existing adapter's own carve-out: a sentence that
    happens to start with narration is still kept once it also asserts
    something real."""
    text = "Based on the data, revenue grew 20%."
    result = classify_claim_quality(text, text)
    assert result.quality_class != QUALITY_NON_SUBSTANTIVE


# ---------------------------------------------------------------------------
# Required "must keep" sentences and their expected classification
# ---------------------------------------------------------------------------

MUST_KEEP_SENTENCES = (
    ("Based on the data, revenue grew 20%.", QUALITY_ANALYTICAL),
    ("Revenue declined 12% year over year.", QUALITY_ANALYTICAL),
    ("AI demand supports revenue growth.", QUALITY_ANALYTICAL),
    ("The company reported quarterly revenue of $2.3 billion.", QUALITY_CONTEXT_ONLY),
    ("The company introduced a new HBM product.", QUALITY_CONTEXT_ONLY),
    ("AI infrastructure demand drives storage demand.", QUALITY_ANALYTICAL),
)


@pytest.mark.parametrize(("text", "expected"), MUST_KEEP_SENTENCES)
def test_must_keep_sentences_classify_as_expected(text, expected):
    result = classify_claim_quality(text, text)
    assert result.quality_class == expected


@pytest.mark.parametrize(("text", "expected"), MUST_KEEP_SENTENCES)
def test_must_keep_sentences_classify_as_expected_with_real_entities(text, expected):
    result = classify_claim_quality(text, text, entities=["NVDA"])
    assert result.quality_class == expected


def test_analytical_does_not_require_direction_to_be_resolved():
    """The Sprint's own canonical example: a claim with a clear factor
    relation is ANALYTICAL even though the stock direction is unknown."""
    text = "AI infrastructure demand drives storage demand."
    result = classify_claim_quality(text, text, direction="unknown")
    assert result.quality_class == QUALITY_ANALYTICAL


# ---------------------------------------------------------------------------
# Additional worked examples from the Sprint brief
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    (
        "High valuation creates downside risk.",
        "Volume remains elevated, indicating selling pressure.",
        "If demand remains strong, margins could improve.",
    ),
)
def test_risk_and_forecast_claims_are_analytical(text):
    result = classify_claim_quality(text, text)
    assert result.quality_class == QUALITY_ANALYTICAL


def test_common_analyst_idiom_signs_of_weakness_is_not_a_false_event_predicate():
    """'signs of weakness' is a very common analyst phrase where 'signs' is
    a noun, not the event-predicate verb 'signs' (a contract) -- must not be
    misdetected as an EVENT_PREDICATE_TERMS hit."""
    text = "Volume shows signs of weakness in the chart."
    result = classify_claim_quality(text, text)
    assert result.features.has_event_predicate is False


def test_bare_fact_with_no_analytical_signal_is_context_only_not_non_substantive():
    text = "The conference is scheduled for September."
    result = classify_claim_quality(text, text, entities=["NVDA"])
    assert result.quality_class == QUALITY_CONTEXT_ONLY


# ---------------------------------------------------------------------------
# Interrogative feature: diagnostic only, never a forced hard rule here
# (relation_grammar's own abstention on "?" is a separate, already-covered
# concern for edge extraction specifically).
# ---------------------------------------------------------------------------


def test_is_interrogative_is_tracked_as_a_feature_flag():
    text = "Could AI demand slow next quarter?"
    result = classify_claim_quality(text, text)
    assert result.features.is_interrogative is True


def test_is_interrogative_false_for_a_declarative_claim():
    text = "AI demand supports revenue growth."
    result = classify_claim_quality(text, text)
    assert result.features.is_interrogative is False


# ---------------------------------------------------------------------------
# Input-order independence (spec test #12)
# ---------------------------------------------------------------------------


def test_factor_and_entity_list_order_does_not_affect_classification():
    text = "AI demand supports revenue growth."
    forward = classify_claim_quality(
        text, text, factors=["AI Demand", "Revenue Growth"], entities=["NVDA", "AI"]
    )
    reversed_order = classify_claim_quality(
        text, text, factors=["Revenue Growth", "AI Demand"], entities=["AI", "NVDA"]
    )
    assert forward.quality_class == reversed_order.quality_class == QUALITY_ANALYTICAL
    assert forward.reason_codes == reversed_order.reason_codes


# ---------------------------------------------------------------------------
# is_claim_eligible: the shared downstream eligibility matrix
# ---------------------------------------------------------------------------

ALL_CONSUMERS = (
    CONSUMER_MAPPING,
    CONSUMER_STRUCTURE,
    CONSUMER_ACTIVATION,
    CONSUMER_CONFLICT,
    CONSUMER_PRODUCT_FINDINGS,
    CONSUMER_ANALYTICAL_PERSISTENCE,
)


@pytest.mark.parametrize("consumer", ALL_CONSUMERS)
def test_non_substantive_is_never_eligible_for_any_consumer(consumer):
    record = {"claim_quality": "non_substantive", "direction": "positive"}
    assert is_claim_eligible(record, consumer) is False


@pytest.mark.parametrize("consumer", ALL_CONSUMERS)
def test_analytical_is_eligible_for_every_consumer_regardless_of_direction(consumer):
    """An analytical claim's own generic `direction` field is not a second
    gate: whether it counts as real Activation/Conflict evidence is already
    decided by the existing, alpha-relative `relation` field those formulas
    score on -- see claim_quality.is_claim_eligible's docstring."""
    for direction in ("positive", "negative", "neutral", "unknown"):
        record = {"claim_quality": "analytical", "direction": direction}
        assert is_claim_eligible(record, consumer) is True


def test_context_only_eligible_for_mapping_and_analytical_persistence():
    record = {"claim_quality": "context_only", "direction": "unknown"}
    assert is_claim_eligible(record, CONSUMER_MAPPING) is True
    assert is_claim_eligible(record, CONSUMER_ANALYTICAL_PERSISTENCE) is True


def test_context_only_never_eligible_for_activation_or_conflict():
    record = {"claim_quality": "context_only", "direction": "positive"}
    assert is_claim_eligible(record, CONSUMER_ACTIVATION) is False
    assert is_claim_eligible(record, CONSUMER_CONFLICT) is False


def test_context_only_hidden_from_product_findings_by_default():
    record = {"claim_quality": "context_only", "direction": "unknown"}
    assert is_claim_eligible(record, CONSUMER_PRODUCT_FINDINGS) is False


def test_context_only_structure_eligibility_depends_on_relation_candidate():
    record = {"claim_quality": "context_only", "direction": "unknown"}
    assert is_claim_eligible(record, CONSUMER_STRUCTURE, has_relation_candidate=False) is False
    assert is_claim_eligible(record, CONSUMER_STRUCTURE, has_relation_candidate=True) is True


def test_analytical_structure_eligibility_is_unconditional_even_without_a_relation_candidate():
    record = {"claim_quality": "analytical", "direction": "unknown"}
    assert is_claim_eligible(record, CONSUMER_STRUCTURE, has_relation_candidate=False) is True


def test_is_claim_eligible_rejects_an_unknown_consumer_name():
    record = {"claim_quality": "analytical"}
    with pytest.raises(ValueError):
        is_claim_eligible(record, "not_a_real_consumer")


def test_is_claim_eligible_lazily_reclassifies_a_record_with_no_stamped_quality():
    """Historical records (pre-dating this Sprint) never had a
    `claim_quality` field stamped by the adapter -- is_claim_eligible must
    still resolve a correct answer purely from the record's own already-
    persisted claim/evidence/entities/factors/direction fields, without
    ever writing back to the record or its source artifact."""
    record = {
        "claim": "Revenue declined 12% year over year.",
        "evidence": "Revenue declined 12% year over year.",
        "entities": ["NVDA"],
        "factors": [],
        "direction": "negative",
    }
    assert "claim_quality" not in record
    assert is_claim_eligible(record, CONSUMER_MAPPING) is True
    assert is_claim_eligible(record, CONSUMER_ACTIVATION) is True
    # Confirm the record itself was never mutated by the lazy fallback.
    assert "claim_quality" not in record


def test_is_claim_eligible_lazily_reclassifies_non_substantive_records_too():
    record = {
        "claim": "Let me synthesize everything.",
        "evidence": "Let me synthesize everything.",
        "entities": ["NVDA"],
        "factors": [],
        "direction": "unknown",
    }
    assert is_claim_eligible(record, CONSUMER_MAPPING) is False


def test_is_claim_eligible_trusts_a_stamped_claim_quality_without_recomputing():
    """A record whose text alone would classify differently must still use
    the stamped value verbatim -- the adapter's own classification (computed
    once, with full context) is authoritative."""
    record = {
        "claim_quality": "analytical",
        "claim": "Let me synthesize everything.",
        "evidence": "Let me synthesize everything.",
        "direction": "unknown",
    }
    assert is_claim_eligible(record, CONSUMER_MAPPING) is True
