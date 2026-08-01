"""Evidence Integrity Completion Sprint, Track A: Production/Shadow Evidence
Eligibility Unification.

Proves Activation v2 production scoring and the Evidence Integrity shadow
layer now select the exact same eligible-claim set for a given alpha (via
the single canonical selector, ``evidence_fact_index.select_supporting_alpha_claims``)
-- not merely the same grouping algorithm over two different input pools.
"""

from __future__ import annotations

from comqutor_alpha.graph_engine.activation_scorer_v2 import (
    _duplicate_group_index,
    _gather_qualifying_evidence,
    _group_evidence,
    score_alpha_v2,
)
from comqutor_alpha.graph_engine.evidence_fact_index import (
    REASON_ASSERTION_NEGATED,
    REASON_NON_ANALYTICAL_QUALITY,
    REASON_RELATION_NOT_SUPPORTING,
    relation_triple_index,
    select_supporting_alpha_claims,
)
from comqutor_alpha.graph_engine.evidence_integrity import _build_candidates, build_evidence_groups

ALPHA = "A001"


def _match(claim_id, alpha_id, *, agent="news_agent", relation="activation", assertion="asserted", quality="analytical"):
    return {
        "claim_id": claim_id,
        "agent": agent,
        "match_status": "matched",
        "matched_alpha": alpha_id,
        "score": 0.8,
        "claim": f"claim text for {claim_id}",
        "evidence": f"claim text for {claim_id}",
        "claim_quality": quality,
        "direction": "positive",
        "assertion_status": assertion,
        "semantic_polarity": "unknown",
        "factors": [],
        "eligible_candidates": [{"alpha_id": alpha_id, "relation": relation}],
    }


def _payload(*records, run_id="run1", ticker="NVDA"):
    return {"run_id": run_id, "ticker": ticker, "matches": list(records)}


class TestSharedSelectorBasics:
    def test_committed_supporting_claim_is_eligible(self):
        matches = [_match("c1", ALPHA, relation="activation", assertion="asserted")]
        eligible, excluded, warnings = select_supporting_alpha_claims(matches, ALPHA)
        assert [r["claim_id"] for r in eligible] == ["c1"]
        assert excluded == []

    def test_non_analytical_quality_excluded_with_reason(self):
        matches = [_match("c1", ALPHA, quality="context_only")]
        eligible, excluded, _ = select_supporting_alpha_claims(matches, ALPHA)
        assert eligible == []
        assert excluded == [{"claim_id": "c1", "reason": REASON_NON_ANALYTICAL_QUALITY}]

    def test_non_substantive_quality_excluded_with_reason(self):
        matches = [_match("c1", ALPHA, quality="non_substantive")]
        eligible, excluded, _ = select_supporting_alpha_claims(matches, ALPHA)
        assert eligible == []
        assert excluded[0]["reason"] == REASON_NON_ANALYTICAL_QUALITY

    def test_counter_evidence_relation_excluded_with_reason(self):
        """The exact real NVDA A001 case: a claim resolved to
        ``invalidation`` (counter-evidence) is not supporting evidence."""
        matches = [_match("c1", ALPHA, relation="invalidation")]
        eligible, excluded, _ = select_supporting_alpha_claims(matches, ALPHA)
        assert eligible == []
        assert excluded == [{"claim_id": "c1", "reason": REASON_RELATION_NOT_SUPPORTING, "relation": "invalidation"}]

    def test_risk_relief_relation_excluded_with_reason(self):
        """The exact real NVDA A501 case."""
        matches = [_match("c1", ALPHA, relation="risk_relief")]
        eligible, excluded, _ = select_supporting_alpha_claims(matches, ALPHA)
        assert eligible == []
        assert excluded[0]["reason"] == REASON_RELATION_NOT_SUPPORTING

    def test_negated_assertion_excluded_with_reason(self):
        """The exact real NVDA A601 case."""
        matches = [_match("c1", ALPHA, relation="activation", assertion="negated")]
        eligible, excluded, _ = select_supporting_alpha_claims(matches, ALPHA)
        assert eligible == []
        assert excluded == [{"claim_id": "c1", "reason": REASON_ASSERTION_NEGATED}]

    def test_hedged_and_conditional_are_not_negated_and_pass_relation_gate(self):
        matches = [_match("c1", ALPHA, relation="conditional", assertion="conditional")]
        eligible, excluded, _ = select_supporting_alpha_claims(matches, ALPHA)
        assert [r["claim_id"] for r in eligible] == ["c1"]
        assert excluded == []

    def test_no_match_and_ambiguous_are_not_candidates_at_all(self):
        matches = [
            {**_match("c1", ALPHA), "match_status": "no_match", "matched_alpha": None},
            {**_match("c2", ALPHA), "match_status": "ambiguous", "matched_alpha": None},
        ]
        eligible, excluded, _ = select_supporting_alpha_claims(matches, ALPHA)
        assert eligible == []
        # Not "relevant" to this alpha in the committed sense -- no
        # exclusion record is fabricated for claims that were never
        # committed to this alpha at all.
        assert excluded == []


class TestProductionShadowConsistency:
    """A001 / A501 / A601 forensic fixtures -- the exact three alphas the
    prior sprint left inconsistent."""

    def _assert_consistent(self, matches, alpha_id, *, run_id="run1", ticker="NVDA"):
        payload = _payload(*matches, run_id=run_id, ticker=ticker)
        dup_idx = _duplicate_group_index([])
        rel_idx = relation_triple_index([])
        qualifying, _warnings = _gather_qualifying_evidence(payload, alpha_id, dup_idx, rel_idx)
        prod_ids = sorted(q["claim_id"] for q in qualifying)

        shadow_candidates = _build_candidates(payload, graph_edges=[], structured_records=[])
        shadow_ids = sorted(c.claim_id for c in shadow_candidates if c.matched_alpha == alpha_id)

        assert prod_ids == shadow_ids, f"production={prod_ids} shadow={shadow_ids}"
        return prod_ids

    def test_a001_fixture_consistent(self):
        # Real case: a committed A001 claim resolved to "invalidation" --
        # both layers must now exclude it identically.
        matches = [_match("c1", "A001", relation="invalidation")]
        ids = self._assert_consistent(matches, "A001")
        assert ids == []

    def test_a501_fixture_consistent(self):
        matches = [
            _match("c1", "A501", relation="risk_relief"),
            _match("c2", "A501", relation="activation"),
        ]
        ids = self._assert_consistent(matches, "A501")
        assert ids == ["c2"]

    def test_a601_fixture_consistent(self):
        matches = [_match("c1", "A601", relation="activation", assertion="negated")]
        ids = self._assert_consistent(matches, "A601")
        assert ids == []

    def test_analytical_claim_eligibility_consistent(self):
        matches = [_match("c1", ALPHA, quality="analytical")]
        self._assert_consistent(matches, ALPHA)

    def test_context_only_exclusion_consistent(self):
        matches = [_match("c1", ALPHA, quality="context_only")]
        ids = self._assert_consistent(matches, ALPHA)
        assert ids == []

    def test_non_substantive_exclusion_consistent(self):
        matches = [_match("c1", ALPHA, quality="non_substantive")]
        ids = self._assert_consistent(matches, ALPHA)
        assert ids == []

    def test_committed_match_eligibility_consistent(self):
        matches = [_match("c1", ALPHA)]
        ids = self._assert_consistent(matches, ALPHA)
        assert ids == ["c1"]

    def test_non_committed_match_exclusion_consistent(self):
        matches = [{**_match("c1", ALPHA), "match_status": "ambiguous", "matched_alpha": None}]
        ids = self._assert_consistent(matches, ALPHA)
        assert ids == []

    def test_assertion_policy_consistent_asserted_hedged_conditional(self):
        matches = [
            _match("c1", ALPHA, relation="activation", assertion="asserted"),
            _match("c2", ALPHA, relation="conditional", assertion="conditional"),
        ]
        ids = self._assert_consistent(matches, ALPHA)
        assert ids == ["c1", "c2"]

    def test_fact_group_ids_identical_between_production_and_shadow(self):
        matches = [
            _match("c1", ALPHA, agent="market_agent"),
            _match("c2", ALPHA, agent="news_agent"),
        ]
        payload = _payload(*matches)
        dup_idx = _duplicate_group_index([])
        qualifying, _ = _gather_qualifying_evidence(payload, ALPHA, dup_idx, {})
        prod_groups = _group_evidence(qualifying, "NVDA", "run1")
        prod_group_ids = sorted(prod_groups.keys())

        shadow_groups = build_evidence_groups(payload, run_id="run1", ticker="NVDA")
        shadow_group_ids = sorted(g.evidence_group_id for g in shadow_groups if ALPHA in g.supported_alpha_ids)

        assert prod_group_ids == shadow_group_ids

    def test_all_ten_mvp_alphas_reconciled_on_a_synthetic_multi_alpha_fixture(self):
        from comqutor_alpha.alpha_library.alpha_loader import EXPECTED_ALPHA_IDS

        matches = []
        for i, alpha_id in enumerate(sorted(EXPECTED_ALPHA_IDS)):
            # Mix of supporting and counter-evidence per alpha, matching the
            # real NVDA profile that exposed the original inconsistency.
            matches.append(_match(f"c{i}a", alpha_id, relation="activation"))
            matches.append(_match(f"c{i}b", alpha_id, relation="invalidation"))
        payload = _payload(*matches)

        dup_idx = _duplicate_group_index([])
        shadow_candidates = _build_candidates(payload, graph_edges=[], structured_records=[])
        for alpha_id in sorted(EXPECTED_ALPHA_IDS):
            qualifying, _ = _gather_qualifying_evidence(payload, alpha_id, dup_idx, {})
            prod_ids = sorted(q["claim_id"] for q in qualifying)
            shadow_ids = sorted(c.claim_id for c in shadow_candidates if c.matched_alpha == alpha_id)
            assert prod_ids == shadow_ids == [f"c{sorted(EXPECTED_ALPHA_IDS).index(alpha_id)}a"]


class TestScoreAlphaV2UsesSharedSelector:
    def test_score_alpha_v2_excludes_counter_evidence_from_supporting_count(self):
        matches = [
            _match("c1", ALPHA, relation="activation"),
            _match("c2", ALPHA, relation="invalidation"),
        ]
        payload = _payload(*matches)
        result = score_alpha_v2(ALPHA, payload, taxonomy={}, graph_edges=[], ticker="NVDA")
        assert result["raw_supporting_claim_count"] == 1
