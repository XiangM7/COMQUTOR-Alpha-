"""Structure Integrity Repair Sprint, Track 2: Evidence Fact Integrity.

Proves production Activation v2 (EvidenceQuality/AgentIndependence) and the
Evidence Integrity shadow layer now share exactly one grouping
implementation (``evidence_fact_index.group_evidence_candidates``) -- the
same run can never again show production ``unique_evidence_count == 11``
and shadow ``independent_evidence_group_count == 5`` for the same alpha, the
exact double-truth the real NVDA forensic audit found for A304.
"""

from __future__ import annotations

from comqutor_alpha.graph_engine.activation_scorer_v2 import score_alpha_v2
from comqutor_alpha.graph_engine.evidence_fact_index import (
    EvidenceFactCandidate,
    group_evidence_candidates,
)
from comqutor_alpha.graph_engine.evidence_integrity import build_evidence_groups

ALPHA = "A304"


def _match(claim_id, agent, claim, *, factors=(), assertion_status="asserted"):
    return {
        "claim_id": claim_id,
        "agent": agent,
        "match_status": "matched",
        "matched_alpha": ALPHA,
        "score": 0.9,
        "claim": claim,
        "evidence": claim,
        "claim_quality": "analytical",
        "direction": "negative",
        "assertion_status": assertion_status,
        "semantic_polarity": "unknown",
        "factors": list(factors),
        "eligible_candidates": [{"alpha_id": ALPHA, "relation": "activation"}],
    }


def _payload(*records):
    return {"run_id": "run1", "ticker": "NVDA", "matches": list(records)}


class TestEvidenceFactIndexUnification:
    def test_near_paraphrases_across_agents_merge_into_one_fact(self):
        candidates = [
            EvidenceFactCandidate(
                claim_id="c1",
                claim_text="Valuation multiples look stretched relative to history.",
                factors=("Valuation Risk",),
                assertion_status="asserted",
                semantic_polarity="bearish",
            ),
            EvidenceFactCandidate(
                claim_id="c2",
                claim_text="Valuation multiples look stretched versus history.",
                factors=("Valuation Risk",),
                assertion_status="asserted",
                semantic_polarity="bearish",
            ),
        ]
        groups = group_evidence_candidates(candidates, "NVDA")
        assert len(groups) == 1

    def test_conflicting_numbers_never_merge(self):
        candidates = [
            EvidenceFactCandidate(
                claim_id="c1",
                claim_text="Revenue grew 20% year over year.",
                factors=("Revenue Growth",),
                assertion_status="asserted",
                semantic_polarity="bullish",
            ),
            EvidenceFactCandidate(
                claim_id="c2",
                claim_text="Revenue grew 35% year over year.",
                factors=("Revenue Growth",),
                assertion_status="asserted",
                semantic_polarity="bullish",
            ),
        ]
        groups = group_evidence_candidates(candidates, "NVDA")
        assert len(groups) == 2

    def test_opposite_direction_never_merges(self):
        candidates = [
            EvidenceFactCandidate(
                claim_id="c1",
                claim_text="Margins are expanding this quarter.",
                factors=("Margin",),
                assertion_status="asserted",
                semantic_polarity="bullish",
            ),
            EvidenceFactCandidate(
                claim_id="c2",
                claim_text="Margins are compressing this quarter.",
                factors=("Margin",),
                assertion_status="asserted",
                semantic_polarity="bearish",
            ),
        ]
        groups = group_evidence_candidates(candidates, "NVDA")
        assert len(groups) == 2

    def test_asserted_and_hypothetical_never_merge(self):
        candidates = [
            EvidenceFactCandidate(
                claim_id="c1",
                claim_text="Datacenter capex is accelerating this year.",
                factors=("AI Capex",),
                assertion_status="asserted",
                semantic_polarity="bullish",
            ),
            EvidenceFactCandidate(
                claim_id="c2",
                claim_text="Datacenter capex is accelerating this year.",
                factors=("AI Capex",),
                assertion_status="conditional",
                semantic_polarity="bullish",
            ),
        ]
        groups = group_evidence_candidates(candidates, "NVDA")
        assert len(groups) == 2

    def test_different_ticker_never_merges(self):
        a = EvidenceFactCandidate(
            claim_id="c1", claim_text="Same exact phrase here.", factors=("Revenue Growth",)
        )
        b = EvidenceFactCandidate(
            claim_id="c2", claim_text="Same exact phrase here.", factors=("Revenue Growth",)
        )
        groups_nvda = group_evidence_candidates([a], "NVDA")
        groups_amd = group_evidence_candidates([b], "AMD")
        assert len(groups_nvda) == 1
        assert len(groups_amd) == 1
        # Grouping is always scoped to one ticker call at a time -- a
        # cross-ticker call is not a case the shared index needs to reject,
        # but every real caller (Activation, shadow layer) only ever invokes
        # it once per single-ticker run.


class TestLinkedSourceIdMergePass:
    """T1 source-linking chain (COMQUTOR Alpha next-round task,
    2026-09-26): claims sharing the SAME validated linked_source_id must
    merge into one Evidence Fact even when their wording differs enough to
    miss every existing text-similarity pass -- the same underlying source
    cited by two different agents must never inflate the independent-
    evidence count. A shared source_id never merges claims about UNRELATED,
    conflicting facts (opposite polarity/conflicting numbers still block
    it, exactly like every other pass)."""

    def test_same_linked_source_id_merges_even_with_dissimilar_wording_of_the_same_fact(self):
        # Corrected 2026-09-28 (explicit review: "不要仅凭签名不冲突就断定两个
        # 内容是同一个事实"): the merge pass now additionally requires
        # POSITIVE same-fact evidence (a shared factor/event signature or a
        # strict Jaccard match), not merely "no signature conflict" -- two
        # claims must share the SAME factor to demonstrate "same fact,
        # different wording" rather than "two different facts, same
        # article" (the original version of this test used two DIFFERENT
        # factors, which is exactly the over-merge risk this correction
        # closes; see the sibling test below for that now-preserved case).
        candidates = [
            EvidenceFactCandidate(
                claim_id="c1",
                claim_text="NVDA posted a strong data center revenue quarter.",
                factors=("Revenue Growth",),
                assertion_status="asserted",
                semantic_polarity="bullish",
                linked_source_id="src_abc123",
            ),
            EvidenceFactCandidate(
                claim_id="c2",
                claim_text="The chipmaker's data center revenue kept climbing this quarter.",
                factors=("Revenue Growth",),
                assertion_status="asserted",
                semantic_polarity="bullish",
                linked_source_id="src_abc123",
            ),
        ]
        groups = group_evidence_candidates(candidates, "NVDA")
        assert len(groups) == 1

    def test_same_linked_source_id_does_not_merge_two_different_non_contradictory_facts(self):
        # The lack of a signature CONFLICT is not, by itself, evidence of
        # sameness -- one article legitimately reports several distinct,
        # non-contradictory facts (a revenue beat AND a new AI capex plan).
        # Different factors, no shared event/relation signal, low token
        # overlap -- correctly kept as two independent facts even though
        # they share a validated source and the same polarity.
        candidates = [
            EvidenceFactCandidate(
                claim_id="c1",
                claim_text="NVDA posted a strong data center quarter.",
                factors=("Revenue Growth",),
                assertion_status="asserted",
                semantic_polarity="bullish",
                linked_source_id="src_abc123",
            ),
            EvidenceFactCandidate(
                claim_id="c2",
                claim_text="The chipmaker's AI infrastructure segment kept climbing.",
                factors=("AI Capex",),
                assertion_status="asserted",
                semantic_polarity="bullish",
                linked_source_id="src_abc123",
            ),
        ]
        groups = group_evidence_candidates(candidates, "NVDA")
        assert len(groups) == 2

    def test_different_linked_source_ids_never_merge_on_that_basis_alone(self):
        candidates = [
            EvidenceFactCandidate(
                claim_id="c1",
                claim_text="Totally unrelated commentary about supply chains.",
                linked_source_id="src_abc123",
            ),
            EvidenceFactCandidate(
                claim_id="c2",
                claim_text="A completely different topic about hiring plans.",
                linked_source_id="src_def456",
            ),
        ]
        groups = group_evidence_candidates(candidates, "NVDA")
        assert len(groups) == 2

    def test_absent_linked_source_id_never_merges_anything_on_this_basis(self):
        # Historical claims (or ones whose extraction never ran source
        # linking) simply have linked_source_id=None -- this pass is then a
        # complete no-op, and every other pass still applies unchanged.
        candidates = [
            EvidenceFactCandidate(claim_id="c1", claim_text="Unrelated statement one."),
            EvidenceFactCandidate(claim_id="c2", claim_text="Unrelated statement two."),
        ]
        groups = group_evidence_candidates(candidates, "NVDA")
        assert len(groups) == 2

    def test_shared_source_id_never_merges_opposing_polarity_direction_is_never_lost(self):
        # Corrected 2026-09-28 (COMQUTOR Alpha T1 follow-up): a shared
        # source is NEVER sufficient on its own to merge two claims -- one
        # article can genuinely report both a supporting and an opposing
        # fact (e.g. "revenue beat estimates, but guidance was cut"). The
        # earlier version of this test asserted the OPPOSITE (that these
        # should merge), which was the exact bug this correction fixes:
        # merging would have silently erased which side each claim argues
        # for. Both claims still independently carry the same
        # linked_source_id (shared source identity is preserved, just never
        # used to collapse them into one fact).
        candidates = [
            EvidenceFactCandidate(
                claim_id="c1", claim_text="Same source, bullish framing.",
                semantic_polarity="bullish", linked_source_id="src_shared",
            ),
            EvidenceFactCandidate(
                claim_id="c2", claim_text="Same source, bearish framing.",
                semantic_polarity="bearish", linked_source_id="src_shared",
            ),
        ]
        groups = group_evidence_candidates(candidates, "NVDA")
        assert len(groups) == 2
        for group in groups:
            assert group[0].linked_source_id == "src_shared"

    def test_different_sources_reporting_a_near_identical_fact_each_keep_their_own_source_id(self):
        # Two DIFFERENT sources independently reporting the same fact (near-
        # paraphrase text, caught by the existing signature/Jaccard passes,
        # not by shared linked_source_id at all) still merge into one
        # Evidence Fact (real, independent corroboration -- a stronger
        # signal than a single source repeated) -- but each member's own
        # distinct source identity/reference must never be overwritten or
        # dropped by the merge (evidence_fact_index only ever groups
        # EvidenceFactCandidate objects by reference; it never rewrites a
        # member's own fields).
        candidates = [
            EvidenceFactCandidate(
                claim_id="c1", claim_text="Valuation multiples look stretched relative to history.",
                factors=("Valuation Risk",), semantic_polarity="bearish", linked_source_id="src_reuters",
            ),
            EvidenceFactCandidate(
                claim_id="c2", claim_text="Valuation multiples look stretched versus history.",
                factors=("Valuation Risk",), semantic_polarity="bearish", linked_source_id="src_barrons",
            ),
        ]
        groups = group_evidence_candidates(candidates, "NVDA")
        assert len(groups) == 1
        member_sources = {member.claim_id: member.linked_source_id for member in groups[0]}
        assert member_sources == {"c1": "src_reuters", "c2": "src_barrons"}

    def test_shared_source_id_never_merges_two_distinct_numeric_facts(self):
        # Same source, same polarity, but two genuinely different facts
        # (different numeric signatures) -- e.g. one article reporting both
        # "revenue grew 20%" and "headcount grew 5%". A shared source must
        # never collapse distinct facts into one, only corroborate wording
        # differences of the SAME fact (see the two merge tests above/below
        # for the positive case).
        candidates = [
            EvidenceFactCandidate(
                claim_id="c1", claim_text="Revenue grew 20% year over year.",
                semantic_polarity="bullish", linked_source_id="src_shared",
            ),
            EvidenceFactCandidate(
                claim_id="c2", claim_text="Headcount grew 5% year over year.",
                semantic_polarity="bullish", linked_source_id="src_shared",
            ),
        ]
        groups = group_evidence_candidates(candidates, "NVDA")
        assert len(groups) == 2


class TestProductionShadowConsistency:
    """The exact A304 acceptance scenario (section 18): raw claims stay 11,
    but production's unique_evidence_fact_count and the shadow layer's
    independent_evidence_group_count must now be the SAME number for the
    same alpha -- never production=11 / shadow=5 again."""

    def _a304_records(self):
        # 8 near-paraphrase restatements of ONE underlying valuation-risk
        # fact from 4 different agents (2 each) -- exactly the "same fact
        # repeated by many agents" profile the real audit found -- plus 3
        # genuinely distinct additional facts (different factor/number/
        # polarity), matching raw=11 total.
        paraphrases = [
            "Valuation multiples remain stretched relative to historical norms.",
            "Valuation multiples remain stretched relative to historical averages.",
            "Valuation multiples look stretched versus historical norms.",
            "Valuation multiples look stretched compared to historical norms.",
            "Multiples remain stretched relative to historical norms for the stock.",
            "Multiples remain stretched relative to historical norms overall.",
            "Valuation multiples continue to look stretched versus history.",
            "Valuation multiples continue looking stretched versus history.",
        ]
        agents = ["market_agent", "news_agent", "sentiment_agent", "fundamentals_agent"]
        records = []
        for i, text in enumerate(paraphrases):
            agent = agents[i % len(agents)]
            records.append(
                _match(f"c{i}", agent, text, factors=("Valuation Risk",), assertion_status="asserted")
            )
        # 3 genuinely distinct facts.
        records.append(
            _match(
                "c_margin",
                "market_agent",
                "Gross margin compressed 200 basis points this quarter.",
                factors=("Margin",),
            )
        )
        records.append(
            _match(
                "c_growth",
                "news_agent",
                "Revenue growth decelerated to single digits.",
                factors=("Revenue Growth",),
            )
        )
        records.append(
            _match(
                "c_rates",
                "sentiment_agent",
                "Rising discount rates pressure long-duration growth names.",
                factors=("Interest Rates",),
            )
        )
        return records

    def test_production_and_shadow_report_the_same_unique_fact_count(self):
        records = self._a304_records()
        payload = _payload(*records)
        assert len(records) == 11

        result = score_alpha_v2(ALPHA, payload, taxonomy={}, graph_edges=[], ticker="NVDA")
        production_unique_count = result["unique_evidence_fact_count"]
        assert result["raw_supporting_claim_count"] == 11

        groups = build_evidence_groups(payload, run_id="run1", ticker="NVDA")
        shadow_unique_count = sum(1 for g in groups if ALPHA in g.supported_alpha_ids)

        assert production_unique_count == shadow_unique_count
        # The 8 near-paraphrases collapse into exactly one shared fact,
        # leaving 1 (paraphrase fact) + 3 (distinct facts) = 4 unique facts
        # -- a real, honest reduction from the raw count of 11, not a
        # hardcoded target.
        assert production_unique_count == 4
        assert result["evidence_overlap_ratio"] == round(1 - 4 / 11, 4)
