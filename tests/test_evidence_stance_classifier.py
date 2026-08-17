"""Sprint 2, Track B1: Alpha-relative Evidence Stance Classifier.

Covers task spec section 27 (12 fixed semantic acceptance cases, including
John's A304 rebuttal example) and section 28 items 1-20 (classifier-level
tests). Every case here is evaluated purely offline against
comqutor_alpha.structure_engine.evidence_stance -- no Provider/LLM calls.
"""

from __future__ import annotations

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.structure_engine import evidence_stance as es

TAXONOMY = load_alpha_taxonomy()


def _classify(claim, target_alpha_id, *, evidence="", matched_alpha=None, candidate=None, **extra_record):
    record = {"claim": claim, "evidence": evidence, **extra_record}
    if matched_alpha is not None:
        record["matched_alpha"] = matched_alpha
    return es.classify_evidence_stance(
        record=record, target_alpha_id=target_alpha_id, candidate=candidate, taxonomy=TAXONOMY
    )


# ---------------------------------------------------------------------------
# Section 27: fixed semantic acceptance cases
# ---------------------------------------------------------------------------


def test_case_1_johns_a304_rebuttal_opposes():
    result = _classify(
        "The valuation risk argument is a lazy heuristic that ignores the actual numbers.", "A304"
    )
    assert result.evidence_stance == es.OPPOSES_ALPHA
    assert es.REASON_EXPLICIT_REBUTTAL_OF_TARGET_ALPHA in result.stance_reason_codes
    assert result.requires_manual_review is False


def test_case_2_a304_direct_support():
    result = _classify("Valuation multiples are compressing as growth expectations normalize.", "A304")
    assert result.evidence_stance == es.SUPPORTS_ALPHA


def test_case_3_a304_mention_only():
    result = _classify("Management discussed valuation risk during the earnings call.", "A304")
    assert result.evidence_stance == es.MENTIONS_ALPHA


def test_case_4_a201_neutral_background():
    result = _classify("The company participates in the semiconductor market.", "A201")
    assert result.evidence_stance == es.NEUTRAL_BACKGROUND


def test_case_5_a101_direct_support():
    result = _classify("Hyperscaler capex accelerated and GPU demand strengthened.", "A101")
    assert result.evidence_stance == es.SUPPORTS_ALPHA


def test_case_6_a101_direct_opposition():
    result = _classify("Hyperscaler capex is slowing and GPU demand is weakening.", "A101")
    assert result.evidence_stance == es.OPPOSES_ALPHA


def test_case_7_a101_already_priced_in_opposes():
    result = _classify(
        "AI demand remains strong, but most of the benefit is already priced in.", "A101"
    )
    assert result.evidence_stance == es.OPPOSES_ALPHA
    assert result.evidence_stance != es.SUPPORTS_ALPHA


def test_case_7_a304_supports_counter_alpha_with_context():
    result = _classify(
        "AI demand remains strong, but most of the benefit is already priced in.",
        "A304",
        matched_alpha="A101",
    )
    assert result.evidence_stance in (es.SUPPORTS_ALPHA, es.SUPPORTS_COUNTER_ALPHA)
    if result.evidence_stance == es.SUPPORTS_COUNTER_ALPHA:
        assert result.counter_alpha_id == "A101"
    assert result.stance_reason_codes


def test_case_8_a501_recession_relief_opposes():
    result = _classify("Recession risks are easing as demand remains resilient.", "A501")
    assert result.evidence_stance == es.OPPOSES_ALPHA


def test_case_9_a103_conditional_support_flagged_for_review():
    result = _classify(
        "If cloud capex accelerates, AI infrastructure demand could improve.", "A103"
    )
    assert result.evidence_stance == es.SUPPORTS_ALPHA
    assert es.REASON_CONDITIONAL_SUPPORT in result.stance_reason_codes
    assert result.requires_manual_review is True


def test_case_10_canonical_counter_alpha_support():
    result = _classify(
        "GPU demand accelerated as hyperscalers increased AI capex.",
        "A304",
        matched_alpha="A101",
    )
    assert result.evidence_stance == es.SUPPORTS_COUNTER_ALPHA
    assert result.counter_alpha_id == "A101"


def test_case_11_same_claim_different_stance_per_alpha():
    claim = "GPU demand accelerated as hyperscalers increased AI capex."
    own = _classify(claim, "A101", matched_alpha="A101")
    counter = _classify(claim, "A304", matched_alpha="A101")
    assert own.evidence_stance == es.SUPPORTS_ALPHA
    assert counter.evidence_stance == es.SUPPORTS_COUNTER_ALPHA
    assert own.evidence_stance != counter.evidence_stance


def test_case_12_mixed_support_and_opposition_unresolved():
    result = _classify(
        "AI demand remains strong, but valuation pressure on the stock is building.", "A101"
    )
    assert result.evidence_stance == es.NEUTRAL_BACKGROUND
    assert es.REASON_MIXED_STANCE_UNRESOLVED in result.stance_reason_codes
    assert result.requires_manual_review is True


# ---------------------------------------------------------------------------
# Section 28 items 1-20: classifier-level tests
# ---------------------------------------------------------------------------


def test_1_johns_a304_rebuttal():
    result = _classify(
        "The valuation risk argument is a lazy heuristic that ignores the actual numbers.", "A304"
    )
    assert result.evidence_stance == es.OPPOSES_ALPHA


def test_2_direct_a304_support():
    result = _classify("Valuation multiples are compressing as growth expectations normalize.", "A304")
    assert result.evidence_stance == es.SUPPORTS_ALPHA


def test_3_mention_only():
    result = _classify("Management discussed valuation risk during the earnings call.", "A304")
    assert result.evidence_stance == es.MENTIONS_ALPHA


def test_4_generic_background():
    result = _classify("The company participates in the semiconductor market.", "A201")
    assert result.evidence_stance == es.NEUTRAL_BACKGROUND


def test_5_direct_a101_support():
    result = _classify("Hyperscaler capex accelerated and GPU demand strengthened.", "A101")
    assert result.evidence_stance == es.SUPPORTS_ALPHA


def test_6_direct_a101_opposition():
    result = _classify("Hyperscaler capex is slowing and GPU demand is weakening.", "A101")
    assert result.evidence_stance == es.OPPOSES_ALPHA


def test_7_risk_relief_opposes_risk_alpha():
    result = _classify("Recession risks are easing as demand remains resilient.", "A501")
    assert result.evidence_stance == es.OPPOSES_ALPHA
    assert es.REASON_RISK_RELIEF_OPPOSES_RISK_ALPHA in result.stance_reason_codes


def test_8_invalidation_opposes_opportunity_alpha():
    result = _classify("AI capex cuts and model demand slows sharply.", "A101")
    assert result.evidence_stance == es.OPPOSES_ALPHA


def test_9_canonical_counter_support():
    result = _classify(
        "GPU demand accelerated as hyperscalers increased AI capex.",
        "A304",
        matched_alpha="A101",
    )
    assert result.evidence_stance == es.SUPPORTS_COUNTER_ALPHA
    assert result.counter_alpha_id == "A101"


def test_10_non_canonical_pair_cannot_become_supports_counter_alpha():
    # A101 and A102 are not a declared canonical conflict pair.
    assert "A102" not in {c.alpha_id for c in TAXONOMY["A101"].conflict_alphas}
    result = _classify(
        "Enterprise AI applications increased inference workloads this quarter.",
        "A101",
        matched_alpha="A102",
    )
    assert result.evidence_stance != es.SUPPORTS_COUNTER_ALPHA


def test_11_conditional_support_flagged_manual_review():
    result = _classify("If cloud capex accelerates, AI infrastructure demand could improve.", "A103")
    assert result.requires_manual_review is True
    assert result.stance_confidence_band == es.CONFIDENCE_MEDIUM


def test_12_mixed_stance_flagged_manual_review():
    result = _classify(
        "AI demand remains strong, but valuation pressure on the stock is building.", "A101"
    )
    assert result.requires_manual_review is True


def test_13_same_claim_different_stance_for_different_alphas():
    claim = "GPU demand accelerated as hyperscalers increased AI capex."
    own = _classify(claim, "A101", matched_alpha="A101")
    counter = _classify(claim, "A304", matched_alpha="A101")
    assert own.evidence_stance != counter.evidence_stance


def test_14_unknown_alpha_safe_handling():
    result = _classify("Something happened.", "A999")
    assert result.evidence_stance is None
    assert es.REASON_UNKNOWN_ALPHA in result.stance_reason_codes
    assert result.requires_manual_review is True


def test_15_no_target_safe_handling():
    result = _classify("Something happened.", "")
    assert result.evidence_stance is None
    assert es.REASON_NO_TARGET_ALPHA in result.stance_reason_codes


def test_16_non_substantive_safe_handling():
    result = _classify("N/A", "A101", claim_quality="non_substantive")
    assert result.evidence_stance == es.NEUTRAL_BACKGROUND
    assert es.REASON_NON_SUBSTANTIVE in result.stance_reason_codes


def test_17_deterministic_repeated_classification():
    claim = "The valuation risk argument is a lazy heuristic that ignores the actual numbers."
    first = _classify(claim, "A304")
    second = _classify(claim, "A304")
    assert first == second


def test_18_no_candidate_score_changes():
    # The classifier is a pure function of its inputs -- it never mutates
    # the candidate mapping it is given.
    candidate = {"alpha_id": "A304", "relation": "activation", "score": 0.42, "keyword_score": 0.2, "factor_score": 1.0}
    snapshot = dict(candidate)
    _classify(
        "Valuation multiples are compressing as growth expectations normalize.",
        "A304",
        candidate=candidate,
    )
    assert candidate == snapshot


def test_19_no_match_status_changes():
    record = {"claim": "Valuation multiples are compressing.", "evidence": "", "match_status": "matched"}
    snapshot = dict(record)
    es.classify_evidence_stance(record=record, target_alpha_id="A304", candidate=None, taxonomy=TAXONOMY)
    assert record == snapshot


def test_20_no_alpha_eligibility_changes():
    # classify_evidence_stance never reads or writes an "eligible" key.
    candidate = {"alpha_id": "A101", "relation": "activation", "eligible": True, "keyword_score": 0.3, "factor_score": 0.0}
    _classify("Hyperscaler capex accelerated and GPU demand strengthened.", "A101", candidate=candidate)
    assert candidate["eligible"] is True


# ---------------------------------------------------------------------------
# Additional ontology / reason-code hygiene checks
# ---------------------------------------------------------------------------


def test_all_five_stances_are_reachable():
    reachable = set()
    reachable.add(_classify("...", "A101", claim_quality="non_substantive").evidence_stance)
    reachable.add(
        _classify(
            "The valuation risk argument is a lazy heuristic that ignores the actual numbers.", "A304"
        ).evidence_stance
    )
    reachable.add(
        _classify("Valuation multiples are compressing as growth expectations normalize.", "A304").evidence_stance
    )
    reachable.add(_classify("Management discussed valuation risk during the earnings call.", "A304").evidence_stance)
    reachable.add(
        _classify(
            "GPU demand accelerated as hyperscalers increased AI capex.", "A304", matched_alpha="A101"
        ).evidence_stance
    )
    assert reachable == es.VALID_EVIDENCE_STANCES


def test_reason_codes_are_from_the_centralized_vocabulary():
    cases = [
        ("The valuation risk argument is a lazy heuristic that ignores the actual numbers.", "A304", None),
        ("Valuation multiples are compressing as growth expectations normalize.", "A304", None),
        ("Management discussed valuation risk during the earnings call.", "A304", None),
        ("The company participates in the semiconductor market.", "A201", None),
        ("Hyperscaler capex accelerated and GPU demand strengthened.", "A101", None),
        ("Hyperscaler capex is slowing and GPU demand is weakening.", "A101", None),
        ("Recession risks are easing as demand remains resilient.", "A501", None),
        ("If cloud capex accelerates, AI infrastructure demand could improve.", "A103", None),
        ("GPU demand accelerated as hyperscalers increased AI capex.", "A304", "A101"),
        ("AI demand remains strong, but valuation pressure on the stock is building.", "A101", None),
    ]
    for claim, target, matched in cases:
        result = _classify(claim, target, matched_alpha=matched)
        for reason in result.stance_reason_codes:
            assert reason in es.VALID_REASON_CODES, reason


def test_confidence_band_is_always_valid_or_none():
    result = _classify("Hyperscaler capex accelerated and GPU demand strengthened.", "A101")
    assert result.stance_confidence_band in es.VALID_CONFIDENCE_BANDS


def test_low_confidence_always_requires_manual_review():
    result = _classify("Some very generic industry commentary about macro trends.", "A501")
    if result.stance_confidence_band == es.CONFIDENCE_LOW:
        assert result.requires_manual_review is True


def test_classification_method_is_stamped():
    result = _classify("Hyperscaler capex accelerated and GPU demand strengthened.", "A101")
    assert result.classification_method == es.CLASSIFIER_VERSION


def test_missing_classification_never_defaults_to_supports_alpha():
    # unknown alpha and empty target must never silently resolve to support.
    assert _classify("Something happened.", "A999").evidence_stance != es.SUPPORTS_ALPHA
    assert _classify("Something happened.", "").evidence_stance != es.SUPPORTS_ALPHA


def test_to_dict_round_trips_reason_codes_as_list():
    result = _classify("Hyperscaler capex accelerated and GPU demand strengthened.", "A101")
    payload = result.to_dict()
    assert isinstance(payload["stance_reason_codes"], list)
    assert payload["target_alpha_id"] == "A101"
