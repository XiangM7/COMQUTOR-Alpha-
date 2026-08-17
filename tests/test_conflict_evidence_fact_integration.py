"""Evidence Integrity Completion Sprint, Track B: Conflict Evidence Fact
Integration.

Proves Conflict Detector consumes the shared canonical Evidence Fact Index
for bull/bear evidence -- near-paraphrase claims collapse into one fact
(never inflating evidence_strength), the same agent counts once per fact,
and the canonical pair registry / conflict score formula stay untouched.

John's B2 Conflict Evidence Admissibility gate (task
B2_CONFLICT_EVIDENCE_ADMISSIBILITY) is layered strictly downstream of all of
this: it only gates whether an already-fully-computed ``conflict`` dict (with
these exact Evidence-Fact-Index-driven fields) is returned by
``evaluate_conflict_pair`` at all -- a candidate that does not itself clear
B2's own >=2-unique-supports_alpha-fact-per-side (with >=1 ticker-specific)
minimum never reaches a ``result["conflict"]`` key, regardless of how
correctly its Evidence Fact Index wiring behaved internally. Every fixture
below therefore adds one additional, genuinely distinct, ticker-specific,
``supports_alpha`` claim per side (``match_record``'s own defaults) beyond
whatever the test's original narrow scenario already had, purely so the
pair clears B2 and the ``conflict`` dict becomes observable again --
the ORIGINAL scenario's claims/assertions are otherwise preserved exactly,
with any per-fact assertions retargeted at the specific fact group under
test (by its member claim ids) rather than a positional/aggregate index, so
adding an unrelated second fact cannot silently weaken what is being
proven. See task spec section 23/25 ("never tune upstream stages to force
a prettier result") -- this is the inverse case: enriching a fixture to
satisfy a *stricter, correct* new gate without changing what the original
assertions establish.
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

TICKER = "NVDA"


def _payload(*claims):
    activation = activation_payload(
        activation_entry("A101", score=90, direction="positive"),
        activation_entry("A304", score=90, direction="negative"),
    )
    return activation, list(claims)


def _fact_group_with_member(structure_block, claim_id):
    for fact in structure_block["evidence_facts"]:
        if claim_id in fact["member_claim_ids"]:
            return fact
    raise AssertionError(f"no evidence fact contains claim_id {claim_id!r}")


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
            # B2: a second, genuinely distinct, ticker-specific bull fact --
            # the near-paraphrase pair above still collapses into its own
            # single fact (checked below by member_claim_ids, not by the
            # aggregate unique_fact_count alone), this just gets bull to
            # B2's >=2-unique-facts minimum so the conflict is admitted.
            match_record("c1b", "A101", agent="fundamentals_agent", factors=["Revenue Growth"]),
            match_record("c3", "A304", agent="bear_researcher", evidence="Valuation risk is elevated."),
            match_record("c3b", "A304", agent="second_bear_agent"),
        )
        result = evaluate_conflict_pair(
            "A101", "A304", activation_payload=activation, alpha_matches=matches,
            taxonomy=TAXONOMY, ticker=TICKER,
        )
        conflict = result["conflict"]
        assert conflict["bull_raw_claim_count"] == 3
        assert conflict["bull_unique_fact_count"] == 2
        assert conflict["bull_overlap_ratio"] == round(1.0 - 2 / 3, 4)

        paraphrase_fact = _fact_group_with_member(conflict["bull_structure"], "c1")
        assert paraphrase_fact["member_claim_ids"] == ["c1", "c2"]
        assert paraphrase_fact["supporting_agents"] == ["market_agent", "news_agent"]

    def test_unique_bull_and_bear_facts_are_correct_when_all_distinct(self):
        activation, matches = _payload(
            match_record("c1", "A101", agent="market_agent", evidence="Datacenter revenue is accelerating.", factors=["Revenue Growth"]),
            # B2: ticker-specific text on the second bull fact so bull has
            # >=1 ticker-specific supporting fact -- still fully distinct
            # text/factor from c1, so "no collapsing" is unaffected.
            match_record("c2", "A101", agent="news_agent", evidence="NVDA new supply agreements were announced.", factors=["AI Capex"]),
            match_record("c3", "A304", agent="bear_researcher", evidence="Valuation multiples remain stretched.", factors=["Valuation Risk"]),
            # B2: a second, distinct, ticker-specific bear fact (bull already
            # has 2 distinct facts). Both sides remain "all claims distinct,
            # no collapsing".
            match_record("c4", "A304", agent="second_bear_agent", evidence="NVDA insider selling has picked up.", factors=["Insider Activity"]),
        )
        result = evaluate_conflict_pair(
            "A101", "A304", activation_payload=activation, alpha_matches=matches,
            taxonomy=TAXONOMY, ticker=TICKER,
        )
        conflict = result["conflict"]
        assert conflict["bull_raw_claim_count"] == 2
        assert conflict["bull_unique_fact_count"] == 2
        assert conflict["bull_overlap_ratio"] == 0.0
        assert conflict["bear_raw_claim_count"] == 2
        assert conflict["bear_unique_fact_count"] == 2
        assert conflict["bear_overlap_ratio"] == 0.0

    def test_same_agent_in_same_fact_group_counted_once(self):
        activation, matches = _payload(
            match_record("c1", "A101", agent="market_agent", evidence="Same underlying fact stated once.", factors=["AI Capex"]),
            match_record("c2", "A101", agent="market_agent", evidence="Same underlying fact stated once more.", factors=["AI Capex"]),
            # B2: a second, genuinely distinct bull fact from a different
            # agent, purely to clear the >=2-unique-facts minimum -- the
            # same-agent pair's own fact group is checked below by its
            # member claim ids, independent of this addition.
            match_record("c1b", "A101", agent="fundamentals_agent", factors=["Revenue Growth"]),
            match_record("c3", "A304", agent="bear_researcher", evidence="Valuation risk is elevated."),
            match_record("c3b", "A304", agent="second_bear_agent"),
        )
        result = evaluate_conflict_pair(
            "A101", "A304", activation_payload=activation, alpha_matches=matches,
            taxonomy=TAXONOMY, ticker=TICKER,
        )
        conflict = result["conflict"]
        assert conflict["bull_unique_fact_count"] == 2

        same_agent_fact = _fact_group_with_member(conflict["bull_structure"], "c1")
        assert same_agent_fact["member_claim_ids"] == ["c1", "c2"]
        # The point of this test: two claims from the SAME agent in the
        # SAME fact group count that agent once, not twice.
        assert same_agent_fact["supporting_agents"] == ["market_agent"]

    def test_evidence_fact_group_ids_are_present_on_structure_blocks(self):
        activation, matches = _payload(
            match_record("c1", "A101", agent="market_agent", evidence="Datacenter revenue is accelerating.", factors=["Revenue Growth"]),
            match_record("c1b", "A101", agent="fundamentals_agent", factors=["AI Capex"]),
            match_record("c2", "A304", agent="bear_researcher", evidence="Valuation risk is elevated.", factors=["Valuation Risk"]),
            match_record("c2b", "A304", agent="second_bear_agent"),
        )
        result = evaluate_conflict_pair(
            "A101", "A304", activation_payload=activation, alpha_matches=matches,
            taxonomy=TAXONOMY, ticker=TICKER,
        )
        conflict = result["conflict"]
        c1_fact = _fact_group_with_member(conflict["bull_structure"], "c1")
        assert c1_fact["representative_claim_id"] == "c1"
        assert c1_fact["member_claim_ids"] == ["c1"]
        assert c1_fact["supporting_agents"] == ["market_agent"]
        assert c1_fact["grouping_method"] == "evidence_fact_index.v1"

    def test_shared_fact_groups_are_never_silently_double_counted(self):
        """Bull and bear pools are disjoint by construction (a claim's
        matched_alpha is singular) -- shared_fact_group_ids is honestly
        computed as empty, not assumed."""
        activation, matches = _payload(
            match_record("c1", "A101", agent="market_agent", evidence="Datacenter revenue is accelerating.", factors=["Revenue Growth"]),
            match_record("c1b", "A101", agent="fundamentals_agent", factors=["AI Capex"]),
            match_record("c2", "A304", agent="bear_researcher", evidence="Valuation risk is elevated.", factors=["Valuation Risk"]),
            match_record("c2b", "A304", agent="second_bear_agent"),
        )
        result = evaluate_conflict_pair(
            "A101", "A304", activation_payload=activation, alpha_matches=matches,
            taxonomy=TAXONOMY, ticker=TICKER,
        )
        conflict = result["conflict"]
        assert conflict["shared_fact_group_ids"] == []
        assert conflict["shared_fact_group_count"] == 0
        assert conflict["shared_fact_resolution"] == "no_overlap"

    def test_conflict_score_formula_and_registry_are_unchanged(self):
        """The canonical pair declaration and the score formula
        (min(activation) x contradiction_weight x evidence_strength) are
        byte-identical -- only the evidence_strength INPUT semantics
        changed. The added second claim per side reuses the same score as
        the first, so the mean (and therefore the expected formula result)
        is byte-identical to what this test originally asserted."""
        activation, matches = _payload(
            match_record("c1", "A101", agent="market_agent", evidence="Datacenter revenue is accelerating.", score=0.9, factors=["Revenue Growth"]),
            match_record("c1b", "A101", agent="fundamentals_agent", score=0.9, factors=["AI Capex"]),
            match_record("c2", "A304", agent="bear_researcher", evidence="Valuation risk is elevated.", score=0.7, factors=["Valuation Risk"]),
            match_record("c2b", "A304", agent="second_bear_agent", score=0.7),
        )
        result = evaluate_conflict_pair(
            "A101", "A304", activation_payload=activation, alpha_matches=matches,
            taxonomy=TAXONOMY, ticker=TICKER,
        )
        conflict = result["conflict"]
        expected_strength = (0.9 + 0.7) / 2.0
        expected_score = min(90.0, 90.0) * 0.9 * expected_strength
        assert conflict["evidence_strength"] == round(expected_strength, 4)
        assert conflict["conflict_score"] == round(expected_score, 4)

    def test_all_six_declared_pairs_still_evaluated(self):
        """Regression guard against the real alpha taxonomy's 6 canonical
        pairs -- Track B must never reduce pair coverage. Unaffected by B2:
        pair enumeration/evaluation happens for every declared pair
        regardless of admissibility outcome."""
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
