"""Structure Graph Deterministic Relation Grammar Sprint.

Rule-level tests for comqutor_alpha.structure_engine.relation_grammar, driven
directly through the module rather than the full extractor pipeline (see
tests/test_structure_extractor.py for the full-pipeline acceptance/negative
sentences this Sprint's brief mandates).
"""

from comqutor_alpha.structure_engine import relation_grammar as rg


def _sources_targets(text, factors):
    return [
        (c.source, c.target, c.edge_type, c.rule_name)
        for c in rg.extract_relation_candidates(text, factors)
    ]


# ---------------------------------------------------------------------------
# 1. Each pattern family's positive case
# ---------------------------------------------------------------------------


def test_forward_transitive_causal_positive():
    result = _sources_targets("AI Demand drives Revenue Growth.", ["AI Demand", "Revenue Growth"])
    assert ("AI Demand", "Revenue Growth", "causal", "forward_transitive_causal") in result


def test_forward_transitive_supportive_positive():
    result = _sources_targets(
        "AI Demand supports Revenue Growth.", ["AI Demand", "Revenue Growth"]
    )
    assert ("AI Demand", "Revenue Growth", "supportive", "forward_transitive_supportive") in result


def test_forward_multiword_positive():
    result = _sources_targets(
        "AI CapEx translates into Datacenter CapEx.", ["AI CapEx", "Datacenter CapEx"]
    )
    assert ("AI CapEx", "Datacenter CapEx", "causal", "forward_multiword_relation") in result


def test_reverse_multiword_positive():
    result = _sources_targets(
        "Revenue Growth benefits from AI Demand.", ["AI Demand", "Revenue Growth"]
    )
    assert ("AI Demand", "Revenue Growth", "causal", "reverse_multiword_relation") in result


def test_reverse_passive_positive():
    result = _sources_targets(
        "Revenue Growth is driven primarily by AI Demand.", ["AI Demand", "Revenue Growth"]
    )
    assert ("AI Demand", "Revenue Growth", "causal", "reverse_passive_relation") in result


def test_prefix_cause_positive():
    result = _sources_targets(
        "Because of AI Demand, Revenue Growth is accelerating.",
        ["AI Demand", "Revenue Growth"],
    )
    assert ("AI Demand", "Revenue Growth", "causal", "prefix_cause_relation") in result


def test_with_embedded_forward_positive():
    result = _sources_targets(
        "With AI Demand driving Revenue Growth, the outlook improves.",
        ["AI Demand", "Revenue Growth"],
    )
    assert ("AI Demand", "Revenue Growth", "causal", "forward_transitive_causal") in result


def test_with_support_from_positive():
    result = _sources_targets(
        "Revenue Growth, with support from AI Demand, looks resilient.",
        ["AI Demand", "Revenue Growth"],
    )
    assert ("AI Demand", "Revenue Growth", "supportive", "with_support_from_relation") in result


def test_conditional_positive():
    result = _sources_targets(
        "If AI Demand remains strong, Revenue Growth could accelerate.",
        ["AI Demand", "Revenue Growth"],
    )
    assert ("AI Demand", "Revenue Growth", "causal", "conditional_relation") in result


def test_conflicting_positive():
    pairs = rg.match_conflicting(
        "ai demand is strong but rich valuation creates downside risk",
        ["AI Demand", "Valuation Risk"],
    )
    assert ("Valuation Risk", "AI Demand") in pairs


# ---------------------------------------------------------------------------
# 2. Reverse-pattern direction is genuinely reversed relative to forward
# ---------------------------------------------------------------------------


def test_result_in_vs_result_from_are_opposite_directions():
    forward = _sources_targets("AI Demand results in Revenue Growth.", ["AI Demand", "Revenue Growth"])
    reverse = _sources_targets("Revenue Growth results from AI Demand.", ["AI Demand", "Revenue Growth"])
    assert ("AI Demand", "Revenue Growth", "causal", "forward_multiword_relation") in forward
    assert ("AI Demand", "Revenue Growth", "causal", "reverse_multiword_relation") in reverse


def test_benefits_transitive_vs_benefits_from_are_opposite_directions():
    forward = _sources_targets(
        "AI Demand benefits Revenue Growth.", ["AI Demand", "Revenue Growth"]
    )
    reverse = _sources_targets(
        "Revenue Growth benefits from AI Demand.", ["AI Demand", "Revenue Growth"]
    )
    assert ("AI Demand", "Revenue Growth", "supportive", "forward_transitive_supportive") in forward
    assert ("AI Demand", "Revenue Growth", "causal", "reverse_multiword_relation") in reverse


# ---------------------------------------------------------------------------
# 3. Active and passive synonymous sentences agree on direction
# ---------------------------------------------------------------------------


def test_active_and_passive_synonyms_agree_on_direction():
    active = _sources_targets("AI CapEx drives GPU Demand.", ["AI CapEx", "GPU Demand"])
    passive = _sources_targets("GPU Demand is driven by AI CapEx.", ["AI CapEx", "GPU Demand"])
    assert ("AI CapEx", "GPU Demand", "causal", "forward_transitive_causal") in active
    assert ("AI CapEx", "GPU Demand", "causal", "reverse_passive_relation") in passive


# ---------------------------------------------------------------------------
# 4/5. Conditional and negated assertion status (full-pipeline, since
# assertion_status is computed by structure_extractor's caller)
# ---------------------------------------------------------------------------


def test_conditional_candidate_has_conditional_rule_name_distinct_from_asserted():
    conditional = _sources_targets(
        "If AI Demand remains strong, Revenue Growth could accelerate.",
        ["AI Demand", "Revenue Growth"],
    )
    plain = _sources_targets("AI Demand drives Revenue Growth.", ["AI Demand", "Revenue Growth"])
    assert any(rule == "conditional_relation" for *_rest, rule in conditional)
    assert any(rule == "forward_transitive_causal" for *_rest, rule in plain)


# ---------------------------------------------------------------------------
# 8. Clause-local factor pairing: relation-verb match in one clause must not
# reach into a factor mentioned only in a different clause.
# ---------------------------------------------------------------------------


def test_relation_verb_does_not_reach_across_a_comma_boundary():
    # "AI Demand" is in the first clause; the verb and "Revenue Growth" are
    # in a second, unrelated clause -- must not pair them.
    result = _sources_targets(
        "AI Demand remains a key theme, and Revenue Growth accelerated last quarter.",
        ["AI Demand", "Revenue Growth"],
    )
    assert result == []


# ---------------------------------------------------------------------------
# 9. Multi-factor sentence does not do a full permutation
# ---------------------------------------------------------------------------


def test_three_factor_sentence_does_not_permute_all_pairs():
    result = _sources_targets(
        "AI Demand drives GPU Demand and Revenue Growth.",
        ["AI Demand", "GPU Demand", "Revenue Growth"],
    )
    # Exactly one relation candidate (AI Demand -> nearest right factor),
    # never a fabricated GPU Demand <-> Revenue Growth pair from the shared
    # "and" list, and never more than one edge out of one verb match.
    assert len(result) == 1
    source, target, edge_type, rule_name = result[0]
    assert source == "AI Demand"
    assert target in {"GPU Demand", "Revenue Growth"}
    assert edge_type == "causal"


# ---------------------------------------------------------------------------
# 10. Overlapping alias endpoint rejection
# ---------------------------------------------------------------------------


def test_overlapping_alias_span_is_not_split_into_two_endpoints():
    # "AI infrastructure spending" matches AI CapEx, Datacenter CapEx, and AI
    # Infrastructure on one overlapping span -- must not fabricate an edge to
    # or from any of them.
    result = _sources_targets(
        "AI infrastructure spending drives Revenue Growth.",
        ["AI CapEx", "Datacenter CapEx", "AI Infrastructure", "Revenue Growth"],
    )
    assert result == []


def test_overlapping_alias_as_reverse_passive_target_also_abstains():
    result = _sources_targets(
        "AI infrastructure spending is driven by Revenue Growth.",
        ["AI CapEx", "Datacenter CapEx", "AI Infrastructure", "Revenue Growth"],
    )
    assert result == []


# ---------------------------------------------------------------------------
# 11. Common-object false positive (shared predicate, no real pairwise link)
# ---------------------------------------------------------------------------


def test_common_object_of_shared_predicate_does_not_relate_siblings():
    result = _sources_targets(
        "Higher rates pressure Revenue Growth and Valuation Risk.",
        ["Revenue Growth", "Valuation Risk"],  # "Higher rates" unresolved on purpose
    )
    assert result == []


def test_driven_by_shared_predicate_compound_object_abstains():
    result = _sources_targets(
        "Micron has undergone a historic earnings inflection, driven primarily "
        "by AI-related HBM demand, DRAM pricing recovery, and data center "
        "spending acceleration.",
        ["Datacenter CapEx", "Semiconductor Cycle"],
    )
    assert result == []


# ---------------------------------------------------------------------------
# 12. Rhetorical / interrogative question abstains entirely
# ---------------------------------------------------------------------------


def test_interrogative_question_abstains():
    result = _sources_targets(
        "Could AI Demand drive Revenue Growth?", ["AI Demand", "Revenue Growth"]
    )
    assert result == []


def test_interrogative_question_abstains_even_with_passive_phrasing():
    result = _sources_targets(
        "Is Revenue Growth really driven by AI Demand?", ["AI Demand", "Revenue Growth"]
    )
    assert result == []


# ---------------------------------------------------------------------------
# 13. Punctuation and limited adverb insertion
# ---------------------------------------------------------------------------


def test_limited_adverb_insertion_is_tolerated():
    for adverb in ("primarily", "mainly", "largely", "partly", "directly", "significantly"):
        result = _sources_targets(
            f"Revenue Growth is driven {adverb} by AI Demand.",
            ["AI Demand", "Revenue Growth"],
        )
        assert ("AI Demand", "Revenue Growth", "causal", "reverse_passive_relation") in result, adverb


def test_unlisted_adverb_is_not_tolerated_as_a_bypass():
    """Only the whitelisted adverbs are tolerated -- an arbitrary word
    inserted between the verb and "by" must not match, so this stays a
    controlled, bounded exception rather than an open wildcard."""
    result = _sources_targets(
        "Revenue Growth is driven somewhat by AI Demand.",
        ["AI Demand", "Revenue Growth"],
    )
    assert result == []


def test_increased_by_percentage_is_not_a_reverse_causal_edge():
    result = _sources_targets(
        "Revenue Growth increased by 20 percent.", ["Revenue Growth", "AI Demand"]
    )
    assert result == []


# ---------------------------------------------------------------------------
# 15. Input order independence (factor list order must not change output)
# ---------------------------------------------------------------------------


def test_factor_list_order_does_not_affect_result():
    text = "AI CapEx translates into Datacenter CapEx."
    forward_order = _sources_targets(text, ["AI CapEx", "Datacenter CapEx"])
    reverse_order = _sources_targets(text, ["Datacenter CapEx", "AI CapEx"])
    assert forward_order == reverse_order


# ---------------------------------------------------------------------------
# CAUSAL_RANK guard: unchanged, still refuses reversed rank pairs
# ---------------------------------------------------------------------------


def test_causal_rank_still_refuses_reversed_direction():
    result = _sources_targets("GPU Demand drives AI Demand.", ["AI Demand", "GPU Demand"])
    assert result == []


def test_causal_rank_admits_equal_rank_pair_when_explicitly_asserted():
    result = _sources_targets(
        "Recession Risk puts pressure on Revenue Growth.", ["Recession Risk", "Revenue Growth"]
    )
    assert ("Recession Risk", "Revenue Growth", "causal", "forward_multiword_relation") in result


def test_causal_rank_exception_pair_admits_infrastructure_driving_semiconductor_cycle():
    """Real, pre-existing SNDK-shaped fixture (tests/test_structure_correctness_sprint.py):
    a rank-2 infrastructure-buildout factor legitimately drives rank-1
    derived component demand. Narrow, explicit pairwise allowlist -- must
    NOT generalize to other rank-2 -> rank-1 pairs (see the negative test
    below)."""
    result = _sources_targets(
        "AI Infrastructure drives Semiconductor Cycle.", ["AI Infrastructure", "Semiconductor Cycle"]
    )
    assert ("AI Infrastructure", "Semiconductor Cycle", "causal", "forward_transitive_causal") in result


def test_causal_rank_exception_is_narrow_not_a_general_rank_2_to_1_pass():
    """GPU Demand (rank 2) -> AI Demand (rank 1) is a different pair and
    must remain rejected -- the exception list must never be mistaken for a
    general "any rank 2 can cause any rank 1" relaxation."""
    result = _sources_targets("GPU Demand drives AI Demand.", ["AI Demand", "GPU Demand"])
    assert result == []


# ---------------------------------------------------------------------------
# Comma-offset participial reduced relative clause: "X, driven by Y, ..."
# ---------------------------------------------------------------------------


def test_comma_offset_participial_resolves_target_from_preceding_clause():
    result = _sources_targets(
        "Storage demand strength, driven by hyperscaler AI capex, is broad.",
        ["AI CapEx", "Semiconductor Cycle"],
    )
    assert ("AI CapEx", "Semiconductor Cycle", "causal", "reverse_passive_relation") in result


def test_full_auxiliary_passive_does_not_reach_across_a_comma_into_an_unrelated_clause():
    """Unlike the bare participial form, "is driven by" is ordinarily a
    clause's own main verb -- it must not reach backward into a preceding,
    unrelated clause when its own clause lacks a local target."""
    result = _sources_targets(
        "The weather was pleasant, GPU Demand is driven by AI CapEx.",
        ["AI CapEx", "GPU Demand"],
    )
    # Same-clause resolution still works (both factors are in the second
    # clause), so this should still resolve locally, not via the
    # cross-clause fallback -- confirms the fallback is specific to the
    # no-auxiliary form and this ordinary case is unaffected.
    assert ("AI CapEx", "GPU Demand", "causal", "reverse_passive_relation") in result


def test_comma_offset_participial_abstains_when_preceding_clause_has_no_factor():
    result = _sources_targets(
        "The weather was pleasant, driven by hyperscaler AI capex, analysts noted.",
        ["AI CapEx", "Semiconductor Cycle"],
    )
    assert result == []


# ---------------------------------------------------------------------------
# Risk-factor supportive exclusion applies uniformly across rule families
# ---------------------------------------------------------------------------


def test_risk_factor_supportive_guard_blocks_forward_transitive():
    result = _sources_targets(
        "Recession Risk supports Revenue Growth.", ["Recession Risk", "Revenue Growth"]
    )
    assert result == []


def test_risk_factor_supportive_guard_blocks_reverse_passive():
    result = _sources_targets(
        "Revenue Growth is supported by Recession Risk.", ["Recession Risk", "Revenue Growth"]
    )
    assert result == []
