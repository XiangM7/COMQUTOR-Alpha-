"""Evidence Integrity Completion Sprint, Track B: Conflict Evidence Fact
Integration.

Proves Conflict Detector consumes the shared canonical Evidence Fact Index
for bull/bear evidence -- near-paraphrase claims collapse into one fact
(never inflating evidence_strength), the same agent counts once per fact,
and the canonical pair registry / conflict score formula stay untouched.
"""

from __future__ import annotations

from comqutor_alpha.alpha_library.alpha_schema import ConflictAlpha
from comqutor_alpha.conflict_engine.conflict_detector import (
    CONFLICT_FORMULA_VERSION,
    detect_alpha_conflicts,
    evaluate_conflict_pair,
)
from tests.fixtures.week4_conflict_cases import (
    activation_entry,
    activation_payload,
    fake_alpha,
    match_record,
)

TAXONOMY = {
    "A101": fake_alpha("A101", [ConflictAlpha(alpha_id="A304", contradiction_weight=0.9)]),
    "A304": fake_alpha("A304", [ConflictAlpha(alpha_id="A101", contradiction_weight=0.9)]),
}


def _payload(*claims):
    activation = activation_payload(
        activation_entry("A101", score=90, direction="positive"),
        activation_entry("A304", score=90, direction="negative"),
    )
    return activation, list(claims)


class TestConflictUsesSharedEvidenceFactIndex:
    def test_near_paraphrase_bull_claims_collapse_into_one_fact(self):
        activation, matches = _payload(
            match_record(
                "c1", "A101", agent="market_agent",
                evidence="AI capex is accelerating GPU demand across hyperscalers.",
                factors=["AI Capex"],
            ),
            match_record(
                "c2", "A101", agent="news_agent",
                evidence="AI capex is accelerating GPU demand across hyperscalers this quarter.",
                factors=["AI Capex"],
            ),
            match_record("c3", "A304", agent="bear_researcher", evidence="Valuation risk is elevated."),
        )
        result = evaluate_conflict_pair(
            "A101", "A304", activation_payload=activation, alpha_matches=matches, taxonomy=TAXONOMY
        )
        conflict = result["conflict"]
        assert conflict["bull_raw_claim_count"] == 2
        assert conflict["bull_unique_fact_count"] == 1
        assert conflict["bull_distinct_agent_count"] == 2
        assert conflict["bull_overlap_ratio"] == 0.5
        assert len(conflict["bull_fact_group_ids"]) == 1

    def test_unique_bull_and_bear_facts_are_correct_when_all_distinct(self):
        activation, matches = _payload(
            match_record("c1", "A101", agent="market_agent", evidence="Datacenter revenue is accelerating.", factors=["Revenue Growth"]),
            match_record("c2", "A101", agent="news_agent", evidence="New supply agreements were announced.", factors=["AI Capex"]),
            match_record("c3", "A304", agent="bear_researcher", evidence="Valuation multiples remain stretched.", factors=["Valuation Risk"]),
        )
        result = evaluate_conflict_pair(
            "A101", "A304", activation_payload=activation, alpha_matches=matches, taxonomy=TAXONOMY
        )
        conflict = result["conflict"]
        assert conflict["bull_raw_claim_count"] == 2
        assert conflict["bull_unique_fact_count"] == 2
        assert conflict["bull_overlap_ratio"] == 0.0
        assert conflict["bear_raw_claim_count"] == 1
        assert conflict["bear_unique_fact_count"] == 1

    def test_same_agent_in_same_fact_group_counted_once(self):
        activation, matches = _payload(
            match_record("c1", "A101", agent="market_agent", evidence="Same underlying fact stated once.", factors=["AI Capex"]),
            match_record("c2", "A101", agent="market_agent", evidence="Same underlying fact stated once more.", factors=["AI Capex"]),
            match_record("c3", "A304", agent="bear_researcher", evidence="Valuation risk is elevated."),
        )
        result = evaluate_conflict_pair(
            "A101", "A304", activation_payload=activation, alpha_matches=matches, taxonomy=TAXONOMY
        )
        conflict = result["conflict"]
        assert conflict["bull_unique_fact_count"] == 1
        assert conflict["bull_distinct_agent_count"] == 1

    def test_evidence_fact_group_ids_are_present_on_structure_blocks(self):
        activation, matches = _payload(
            match_record("c1", "A101", agent="market_agent", evidence="Datacenter revenue is accelerating.", factors=["Revenue Growth"]),
            match_record("c2", "A304", agent="bear_researcher", evidence="Valuation risk is elevated.", factors=["Valuation Risk"]),
        )
        result = evaluate_conflict_pair(
            "A101", "A304", activation_payload=activation, alpha_matches=matches, taxonomy=TAXONOMY
        )
        conflict = result["conflict"]
        bull_facts = conflict["bull_structure"]["evidence_facts"]
        assert len(bull_facts) == 1
        assert bull_facts[0]["representative_claim_id"] == "c1"
        assert bull_facts[0]["member_claim_ids"] == ["c1"]
        assert bull_facts[0]["supporting_agents"] == ["market_agent"]
        assert bull_facts[0]["grouping_method"] == "evidence_fact_index.v1"

    def test_shared_fact_groups_are_never_silently_double_counted(self):
        """Bull and bear pools are disjoint by construction (a claim's
        matched_alpha is singular) -- shared_fact_group_ids is honestly
        computed as empty, not assumed."""
        activation, matches = _payload(
            match_record("c1", "A101", agent="market_agent", evidence="Datacenter revenue is accelerating."),
            match_record("c2", "A304", agent="bear_researcher", evidence="Valuation risk is elevated."),
        )
        result = evaluate_conflict_pair(
            "A101", "A304", activation_payload=activation, alpha_matches=matches, taxonomy=TAXONOMY
        )
        conflict = result["conflict"]
        assert conflict["shared_fact_group_ids"] == []
        assert conflict["shared_fact_group_count"] == 0
        assert conflict["shared_fact_resolution"] == "no_overlap"

    def test_conflict_score_formula_and_registry_are_unchanged(self):
        """The canonical pair declaration and the score formula
        (min(activation) x contradiction_weight x evidence_strength) are
        byte-identical -- only the evidence_strength INPUT semantics
        changed."""
        activation, matches = _payload(
            match_record("c1", "A101", agent="market_agent", evidence="Datacenter revenue is accelerating.", score=0.9),
            match_record("c2", "A304", agent="bear_researcher", evidence="Valuation risk is elevated.", score=0.7),
        )
        result = evaluate_conflict_pair(
            "A101", "A304", activation_payload=activation, alpha_matches=matches, taxonomy=TAXONOMY
        )
        conflict = result["conflict"]
        expected_strength = (0.9 + 0.7) / 2.0
        expected_score = min(90.0, 90.0) * 0.9 * expected_strength
        assert conflict["evidence_strength"] == round(expected_strength, 4)
        assert conflict["conflict_score"] == round(expected_score, 4)

    def test_all_six_declared_pairs_still_evaluated(self):
        """Regression guard against the real alpha taxonomy's 6 canonical
        pairs -- Track B must never reduce pair coverage."""
        from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy

        taxonomy = load_alpha_taxonomy()
        activation = activation_payload(
            *(activation_entry(alpha_id, score=70, direction="positive") for alpha_id in sorted(taxonomy))
        )
        result = detect_alpha_conflicts(
            run_id="run1", ticker="NVDA", activation_payload=activation, alpha_matches=[], taxonomy=taxonomy
        )
        assert result["arbitration"]["declared_pair_count"] == 6
        assert len(result["arbitration"]["candidate_evaluations"]) == 6
        assert result["formula_version"] == CONFLICT_FORMULA_VERSION
