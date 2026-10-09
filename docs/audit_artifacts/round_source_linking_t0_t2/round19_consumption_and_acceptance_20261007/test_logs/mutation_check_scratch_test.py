"""Scratch (not in the repo): each production behaviour is changed in-process and the new contract test must then FAIL."""
import pytest
import sys
sys.path.insert(0, "/Users/xiangmao/COMQUTOR-Alpha-/tests")
import test_alpha_evidence_consumption_contract as t
from comqutor_alpha.graph_engine import activation_scorer_v2 as act
from comqutor_alpha.graph_engine import evidence_fact_index as efi
from comqutor_alpha.conflict_engine import conflict_admissibility as adm


def fails(fn, *a):
    try:
        fn(*a)
    except BaseException:
        return True
    return False


def test_mutation_mention_becomes_a_qualifying_relation(monkeypatch):
    monkeypatch.setattr(efi, "QUALIFYING_RELATIONS", frozenset({"activation", "conditional", "mixed", "mention"}))
    assert fails(t.test_mention_negated_and_context_only_are_never_upgraded_into_supporting_evidence)


def test_mutation_negated_assertion_gets_weight(monkeypatch):
    monkeypatch.setitem(act.ASSERTION_WEIGHTS, "negated", 0.7)
    assert fails(t.test_mention_negated_and_context_only_are_never_upgraded_into_supporting_evidence)


def test_mutation_zero_score_gets_a_floor(monkeypatch):
    original = act._evidence_quality_component

    def with_floor(groups):
        patched = {k: [{**m, "match_score": max(m["match_score"], 0.5)} for m in v] for k, v in groups.items()}
        return original(patched)
    monkeypatch.setattr(act, "_evidence_quality_component", with_floor)
    assert fails(t.test_llm_selected_alpha_with_zero_lexical_score_is_a_pool_member_with_zero_weight)


def test_mutation_absent_stance_counts_as_support(monkeypatch):
    monkeypatch.setattr(adm, "stance_for_alpha", lambda record, alpha_id: "supports_alpha")
    assert fails(t.test_only_an_explicit_supports_alpha_stance_counts_and_an_absent_stance_never_does, "neutral_background")


def test_mutation_shared_source_merges_everything(monkeypatch):
    monkeypatch.setattr(efi, "NEAR_MATCH_JACCARD_THRESHOLD", 0.0)
    monkeypatch.setattr(efi, "numeric_signature", lambda text: "")  # numbers no longer conflict: only the shared source is left
    assert fails(t.test_a_shared_source_alone_never_merges_different_facts)


def test_mutation_secondary_restatement_counts(monkeypatch):
    import comqutor_alpha.graph_engine.evidence_source_role as role
    monkeypatch.setattr(role, "source_role_for_agent", lambda agent: role.SOURCE_ROLE_PRIMARY_RESEARCH)
    assert fails(t.test_a_secondary_restatement_of_a_primary_fact_is_not_independent_evidence)
