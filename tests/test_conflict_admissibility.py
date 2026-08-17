"""John's B2 Conflict Evidence Admissibility gate -- dedicated unit tests
(task B2_CONFLICT_EVIDENCE_ADMISSIBILITY).

Each test below calls ``evaluate_conflict_admissibility`` (or, where the
question is about main-conflict arbitration rather than a single pair's
admissibility, ``detect_alpha_conflicts`` directly) with hand-built,
minimal, fully-controlled inputs -- never a real offline fixture -- so each
of John's individually-specified requirements is pinned by its own
narrowly-scoped test, independent of any upstream fixture's evidence
volume. ``group_into_facts`` is always the real, unmodified
``conflict_detector._group_qualifying_claims_into_facts`` (which itself
delegates to the shared canonical ``evidence_fact_index.
group_evidence_candidates``) -- never a mock or a second grouping
implementation, exactly as production wires it.
"""

from __future__ import annotations

from functools import partial

from comqutor_alpha.alpha_library.alpha_schema import ConflictAlpha
from comqutor_alpha.conflict_engine.conflict_admissibility import (
    ADMITTED,
    ALL_REASON_CODES,
    ALPHA_SCORE_THRESHOLD,
    CANDIDATE,
    MIN_SUPPORTING_EVIDENCE_PER_SIDE,
    REASON_BEAR_SCORE_BELOW_THRESHOLD,
    REASON_BULL_SCORE_BELOW_THRESHOLD,
    REASON_INSUFFICIENT_BEAR_SUPPORTING_EVIDENCE,
    REASON_INSUFFICIENT_BULL_SUPPORTING_EVIDENCE,
    REASON_NO_BEAR_TICKER_SPECIFIC_SUPPORT,
    REASON_NO_BULL_TICKER_SPECIFIC_SUPPORT,
    evaluate_conflict_admissibility,
)
from comqutor_alpha.conflict_engine.conflict_detector import (
    _group_qualifying_claims_into_facts,
    detect_alpha_conflicts,
)
from tests.fixtures.week4_conflict_cases import (
    activation_entry,
    activation_payload,
    fake_alpha,
)

RUN_ID = "b2_unit_test_run"
TICKER = "NVDA"

_GROUP_INTO_FACTS = partial(_group_qualifying_claims_into_facts, run_id=RUN_ID, ticker=TICKER)


def _qualifying_claim(claim_id: str, evidence: str, *, score: float = 0.8, factors=()) -> dict:
    """The exact shape ``conflict_detector._gather_qualifying_evidence``
    already produces -- claim_id/match_score/evidence/factors/
    assertion_status/semantic_polarity -- built directly here (never through
    the full detector) so each test controls exactly one qualifying claim at
    a time."""
    return {
        "claim_id": claim_id,
        "match_score": score,
        "evidence": evidence,
        "source_agent_output_id": f"o_{claim_id}",
        "agent": f"agent_{claim_id}",
        "factors": tuple(factors),
        "assertion_status": "asserted",
        "semantic_polarity": "activation",
    }


def _match(claim_id: str, alpha_id: str, stance: str | None, *, stance_method: str = "llm") -> dict:
    """The raw alpha_matches.json record shape B2 reads stance from --
    ``stance_for_alpha`` looks up ``candidate_scores[].evidence_stance``.
    ``stance_method`` is attached exactly like a real B1-upgraded record
    (Sprint: Alpha-Relative Evidence Stance Classification) but B2 must
    never branch on it (task section 4)."""
    candidate: dict = {"alpha_id": alpha_id, "score": 0.8, "relation": "activation"}
    if stance is not None:
        candidate["evidence_stance"] = stance
        candidate["stance_method"] = stance_method
    return {"claim_id": claim_id, "candidate_scores": [candidate]}


def _evaluate(
    *,
    bull_alpha_id="BULL",
    bear_alpha_id="BEAR",
    bull_score=80.0,
    bear_score=80.0,
    bull_claims,
    bear_claims,
    matches,
):
    return evaluate_conflict_admissibility(
        bull_alpha_id=bull_alpha_id,
        bear_alpha_id=bear_alpha_id,
        bull_score=bull_score,
        bear_score=bear_score,
        bull_qualifying_claims=bull_claims,
        bear_qualifying_claims=bear_claims,
        alpha_matches=matches,
        ticker=TICKER,
        group_into_facts=_GROUP_INTO_FACTS,
    )


# A pair of always-sufficient, always-ticker-specific, always-distinct
# supporting claims for whichever side is not the focus of a given test.
def _two_clean_supports(alpha_id: str, side: str) -> tuple[list[dict], list[dict]]:
    claims = [
        _qualifying_claim(f"{side}_clean_1", f"{TICKER} datacenter demand is accelerating.", factors=["Revenue"]),
        _qualifying_claim(f"{side}_clean_2", f"{TICKER} new supply agreements were announced.", factors=["Supply"]),
    ]
    matches = [_match(c["claim_id"], alpha_id, "supports_alpha") for c in claims]
    return claims, matches


# ---------------------------------------------------------------------------
# (1) Full pass
# ---------------------------------------------------------------------------


def test_a_full_pass_both_sides_score_50_two_ticker_specific_facts_admits():
    bull_claims, bull_matches = _two_clean_supports("BULL", "bull")
    bear_claims, bear_matches = _two_clean_supports("BEAR", "bear")
    result = _evaluate(
        bull_score=50.0,
        bear_score=50.0,
        bull_claims=bull_claims,
        bear_claims=bear_claims,
        matches=[*bull_matches, *bear_matches],
    )
    assert result.status == ADMITTED
    assert result.reason_codes == ()
    assert result.bull.supporting_evidence_count == 2
    assert result.bear.supporting_evidence_count == 2
    assert result.bull.ticker_specific_support_count >= 1
    assert result.bear.ticker_specific_support_count >= 1


# ---------------------------------------------------------------------------
# (2) Score just below threshold
# ---------------------------------------------------------------------------


def test_b_score_just_below_threshold_is_candidate():
    bull_claims, bull_matches = _two_clean_supports("BULL", "bull")
    bear_claims, bear_matches = _two_clean_supports("BEAR", "bear")
    result = _evaluate(
        bull_score=49.99,
        bear_score=80.0,
        bull_claims=bull_claims,
        bear_claims=bear_claims,
        matches=[*bull_matches, *bear_matches],
    )
    assert result.status == CANDIDATE
    assert REASON_BULL_SCORE_BELOW_THRESHOLD in result.reason_codes
    assert REASON_BEAR_SCORE_BELOW_THRESHOLD not in result.reason_codes


# ---------------------------------------------------------------------------
# (3) Insufficient support: exactly one unique fact
# ---------------------------------------------------------------------------


def test_c_single_unique_supporting_fact_is_insufficient():
    bull_claims = [_qualifying_claim("bull1", f"{TICKER} datacenter demand is accelerating.")]
    bull_matches = [_match("bull1", "BULL", "supports_alpha")]
    bear_claims, bear_matches = _two_clean_supports("BEAR", "bear")
    result = _evaluate(
        bull_claims=bull_claims, bear_claims=bear_claims, matches=[*bull_matches, *bear_matches]
    )
    assert result.status == CANDIDATE
    assert REASON_INSUFFICIENT_BULL_SUPPORTING_EVIDENCE in result.reason_codes
    assert result.bull.supporting_evidence_count == 1 < MIN_SUPPORTING_EVIDENCE_PER_SIDE


# ---------------------------------------------------------------------------
# (4) Duplicate/near-paraphrase claims collapse to ONE evidence_fact_id
# ---------------------------------------------------------------------------


def test_d_three_near_duplicate_claims_count_as_one_not_three():
    # A shared, non-empty factor signature (matching ticker/assertion_status/
    # semantic_polarity, no conflicting relation_triple) puts all three in
    # the same Evidence Fact Index blocking bucket and merges them via the
    # exact factor/event-signature pass -- deterministic, not dependent on
    # tuning word-overlap to clear the separate Jaccard near-match pass.
    bull_claims = [
        _qualifying_claim("bull1", f"{TICKER} datacenter demand is accelerating this quarter.", factors=["Revenue"]),
        _qualifying_claim("bull2", f"{TICKER} datacenter demand is accelerating this quarter, sources say.", factors=["Revenue"]),
        _qualifying_claim("bull3", f"{TICKER} datacenter demand is accelerating this quarter -- confirmed.", factors=["Revenue"]),
    ]
    bull_matches = [_match(c["claim_id"], "BULL", "supports_alpha") for c in bull_claims]
    bear_claims, bear_matches = _two_clean_supports("BEAR", "bear")
    result = _evaluate(
        bull_claims=bull_claims, bear_claims=bear_claims, matches=[*bull_matches, *bear_matches]
    )
    # Three distinct claim_ids, all supports_alpha, all qualifying -- but the
    # shared canonical Evidence Fact Index recognizes them as the same
    # underlying fact restated three times, so the *unique* supporting
    # count is 1, still short of B2's >=2 minimum.
    assert len(result.bull.supporting_fact_group_ids) == 1
    assert result.bull.supporting_evidence_count == 1
    assert result.status == CANDIDATE
    assert REASON_INSUFFICIENT_BULL_SUPPORTING_EVIDENCE in result.reason_codes


# ---------------------------------------------------------------------------
# (5)-(8) Only the literal "supports_alpha" stance counts
# ---------------------------------------------------------------------------


def test_e_opposes_alpha_stance_does_not_count_as_support():
    bull_claims = [
        _qualifying_claim("bull1", f"{TICKER} fact one.", factors=["A"]),
        _qualifying_claim("bull2", f"{TICKER} fact two.", factors=["B"]),
    ]
    bull_matches = [_match(c["claim_id"], "BULL", "opposes_alpha") for c in bull_claims]
    bear_claims, bear_matches = _two_clean_supports("BEAR", "bear")
    result = _evaluate(
        bull_claims=bull_claims, bear_claims=bear_claims, matches=[*bull_matches, *bear_matches]
    )
    assert result.bull.supporting_evidence_count == 0
    assert result.status == CANDIDATE
    assert REASON_INSUFFICIENT_BULL_SUPPORTING_EVIDENCE in result.reason_codes


def test_f_mentions_alpha_stance_does_not_count_as_support():
    bull_claims = [
        _qualifying_claim("bull1", f"{TICKER} fact one.", factors=["A"]),
        _qualifying_claim("bull2", f"{TICKER} fact two.", factors=["B"]),
    ]
    bull_matches = [_match(c["claim_id"], "BULL", "mentions_alpha") for c in bull_claims]
    bear_claims, bear_matches = _two_clean_supports("BEAR", "bear")
    result = _evaluate(
        bull_claims=bull_claims, bear_claims=bear_claims, matches=[*bull_matches, *bear_matches]
    )
    assert result.bull.supporting_evidence_count == 0
    assert result.status == CANDIDATE


def test_g_neutral_background_stance_does_not_count_as_support():
    bull_claims = [
        _qualifying_claim("bull1", f"{TICKER} fact one.", factors=["A"]),
        _qualifying_claim("bull2", f"{TICKER} fact two.", factors=["B"]),
    ]
    bull_matches = [_match(c["claim_id"], "BULL", "neutral_background") for c in bull_claims]
    bear_claims, bear_matches = _two_clean_supports("BEAR", "bear")
    result = _evaluate(
        bull_claims=bull_claims, bear_claims=bear_claims, matches=[*bull_matches, *bear_matches]
    )
    assert result.bull.supporting_evidence_count == 0
    assert result.status == CANDIDATE


def test_h_supports_counter_alpha_stance_does_not_count_as_support():
    """supports_counter_alpha means the claim supports the OTHER side of a
    counter-alpha pairing -- it is never treated as support for THIS
    (target) alpha, even though it is a "supports_*"-shaped string."""
    bull_claims = [
        _qualifying_claim("bull1", f"{TICKER} fact one.", factors=["A"]),
        _qualifying_claim("bull2", f"{TICKER} fact two.", factors=["B"]),
    ]
    bull_matches = [_match(c["claim_id"], "BULL", "supports_counter_alpha") for c in bull_claims]
    bear_claims, bear_matches = _two_clean_supports("BEAR", "bear")
    result = _evaluate(
        bull_claims=bull_claims, bear_claims=bear_claims, matches=[*bull_matches, *bear_matches]
    )
    assert result.bull.supporting_evidence_count == 0
    assert result.status == CANDIDATE


# ---------------------------------------------------------------------------
# (9) Mixed evidence: only supports_alpha members are counted
# ---------------------------------------------------------------------------


def test_i_mixed_evidence_only_supports_alpha_members_are_counted():
    supports = [
        _qualifying_claim("s1", f"{TICKER} datacenter demand is accelerating.", factors=["Revenue"]),
        _qualifying_claim("s2", f"{TICKER} new supply agreements were announced.", factors=["Supply"]),
    ]
    opposes = [
        _qualifying_claim("o1", f"{TICKER} valuation is stretched.", factors=["Valuation"]),
        _qualifying_claim("o2", f"{TICKER} margins are compressing.", factors=["Margin"]),
        _qualifying_claim("o3", f"{TICKER} guidance was cut.", factors=["Guidance"]),
    ]
    mentions = [
        _qualifying_claim("m1", f"{TICKER} was discussed on the earnings call.", factors=["Call"]),
        _qualifying_claim("m2", f"{TICKER} appeared in a sector roundup.", factors=["Sector"]),
        _qualifying_claim("m3", f"{TICKER} was named among peers.", factors=["Peers"]),
        _qualifying_claim("m4", f"{TICKER} traded inline with the index.", factors=["Index"]),
    ]
    bull_claims = [*supports, *opposes, *mentions]
    bull_matches = [
        *(_match(c["claim_id"], "BULL", "supports_alpha") for c in supports),
        *(_match(c["claim_id"], "BULL", "opposes_alpha") for c in opposes),
        *(_match(c["claim_id"], "BULL", "mentions_alpha") for c in mentions),
    ]
    bear_claims, bear_matches = _two_clean_supports("BEAR", "bear")
    result = _evaluate(
        bull_claims=bull_claims, bear_claims=bear_claims, matches=[*bull_matches, *bear_matches]
    )
    assert result.bull.supporting_evidence_count == 2
    assert result.status == ADMITTED


# ---------------------------------------------------------------------------
# (10) No ticker-specific support at all
# ---------------------------------------------------------------------------


def test_j_two_supporting_facts_with_zero_ticker_specific_support_is_candidate():
    bull_claims = [
        _qualifying_claim("bull1", "Datacenter demand is accelerating industry-wide.", factors=["Revenue"]),
        _qualifying_claim("bull2", "New supply agreements were announced across the sector.", factors=["Supply"]),
    ]
    bull_matches = [_match(c["claim_id"], "BULL", "supports_alpha") for c in bull_claims]
    bear_claims, bear_matches = _two_clean_supports("BEAR", "bear")
    result = _evaluate(
        bull_claims=bull_claims, bear_claims=bear_claims, matches=[*bull_matches, *bear_matches]
    )
    assert result.bull.supporting_evidence_count == 2  # evidence count itself is sufficient
    assert result.bull.ticker_specific_support_count == 0
    assert result.status == CANDIDATE
    assert REASON_NO_BULL_TICKER_SPECIFIC_SUPPORT in result.reason_codes


# ---------------------------------------------------------------------------
# (11) One side has ticker-specific support, the other does not
# ---------------------------------------------------------------------------


def test_k_one_side_only_ticker_specific_is_candidate():
    bull_claims, bull_matches = _two_clean_supports("BULL", "bull")  # ticker-specific
    bear_claims = [
        _qualifying_claim("bear1", "Valuation is stretched industry-wide.", factors=["Valuation"]),
        _qualifying_claim("bear2", "Margins are compressing across the sector.", factors=["Margin"]),
    ]
    bear_matches = [_match(c["claim_id"], "BEAR", "supports_alpha") for c in bear_claims]
    result = _evaluate(
        bull_claims=bull_claims, bear_claims=bear_claims, matches=[*bull_matches, *bear_matches]
    )
    assert result.bull.ticker_specific_support_count >= 1
    assert result.bear.ticker_specific_support_count == 0
    assert result.status == CANDIDATE


# ---------------------------------------------------------------------------
# (12) Exact boundary: score == 50 passes
# ---------------------------------------------------------------------------


def test_l_exact_boundary_score_of_50_passes():
    assert ALPHA_SCORE_THRESHOLD == 50.0
    bull_claims, bull_matches = _two_clean_supports("BULL", "bull")
    bear_claims, bear_matches = _two_clean_supports("BEAR", "bear")
    result = _evaluate(
        bull_score=50.0,
        bear_score=50.0,
        bull_claims=bull_claims,
        bear_claims=bear_claims,
        matches=[*bull_matches, *bear_matches],
    )
    assert result.status == ADMITTED


def test_l_just_below_boundary_score_of_49_999_fails():
    bull_claims, bull_matches = _two_clean_supports("BULL", "bull")
    bear_claims, bear_matches = _two_clean_supports("BEAR", "bear")
    result = _evaluate(
        bull_score=49.999,
        bear_score=50.0,
        bull_claims=bull_claims,
        bear_claims=bear_claims,
        matches=[*bull_matches, *bear_matches],
    )
    assert result.status == CANDIDATE
    assert REASON_BULL_SCORE_BELOW_THRESHOLD in result.reason_codes


# ---------------------------------------------------------------------------
# (15) stance_method (llm vs deterministic_fallback) never affects admission
# ---------------------------------------------------------------------------


def test_o_stance_method_llm_vs_deterministic_fallback_count_identically():
    def _run(method: str):
        bull_claims = [
            _qualifying_claim("bull1", f"{TICKER} datacenter demand is accelerating.", factors=["Revenue"]),
            _qualifying_claim("bull2", f"{TICKER} new supply agreements were announced.", factors=["Supply"]),
        ]
        bull_matches = [
            _match(c["claim_id"], "BULL", "supports_alpha", stance_method=method) for c in bull_claims
        ]
        bear_claims, bear_matches = _two_clean_supports("BEAR", "bear")
        return _evaluate(
            bull_claims=bull_claims, bear_claims=bear_claims, matches=[*bull_matches, *bear_matches]
        )

    llm_result = _run("llm")
    fallback_result = _run("deterministic_fallback")
    assert llm_result.status == fallback_result.status == ADMITTED
    assert llm_result.bull.supporting_evidence_count == fallback_result.bull.supporting_evidence_count == 2


# ---------------------------------------------------------------------------
# (16) Multiple simultaneous failure reasons are all persisted
# ---------------------------------------------------------------------------


def test_p_multiple_simultaneous_failure_reasons_are_all_persisted():
    bull_claims = [_qualifying_claim("bull1", "Generic industry-wide statement.")]
    bull_matches = [_match("bull1", "BULL", "opposes_alpha")]
    bear_claims = [_qualifying_claim("bear1", "Another generic industry-wide statement.")]
    bear_matches = [_match("bear1", "BEAR", "mentions_alpha")]
    result = _evaluate(
        bull_score=10.0,
        bear_score=10.0,
        bull_claims=bull_claims,
        bear_claims=bear_claims,
        matches=[*bull_matches, *bear_matches],
    )
    assert result.status == CANDIDATE
    # Every one of the six reachable failure reasons fires simultaneously:
    # both scores below threshold, both sides lack sufficient supporting
    # evidence (0, since neither claim's stance is supports_alpha), and
    # both sides therefore also lack ticker-specific support.
    assert set(result.reason_codes) == {
        REASON_BULL_SCORE_BELOW_THRESHOLD,
        REASON_BEAR_SCORE_BELOW_THRESHOLD,
        REASON_INSUFFICIENT_BULL_SUPPORTING_EVIDENCE,
        REASON_INSUFFICIENT_BEAR_SUPPORTING_EVIDENCE,
        REASON_NO_BULL_TICKER_SPECIFIC_SUPPORT,
        REASON_NO_BEAR_TICKER_SPECIFIC_SUPPORT,
    }
    assert set(result.reason_codes).issubset(ALL_REASON_CODES)


# ---------------------------------------------------------------------------
# Ticker-specific signal: proven genuinely discriminating, not a fake
# always-True field (task section 9: "test must NOT set every fixture
# ticker_specific=True to force a pass").
# ---------------------------------------------------------------------------


def test_ticker_specific_signal_is_not_a_fake_always_true_field():
    """A claim that mentions a DIFFERENT ticker/company (same shape, same
    stance, same qualifying status -- only the ticker token differs) must
    NOT count as ticker-specific support for THIS run's ticker. If the
    signal were secretly always True (the exact failure mode a prior sprint
    found and fixed elsewhere in this codebase), this test would wrongly
    admit."""
    bull_claims = [
        _qualifying_claim("bull1", "AAPL datacenter demand is accelerating.", factors=["Revenue"]),
        _qualifying_claim("bull2", "AMD new supply agreements were announced.", factors=["Supply"]),
    ]
    bull_matches = [_match(c["claim_id"], "BULL", "supports_alpha") for c in bull_claims]
    bear_claims, bear_matches = _two_clean_supports("BEAR", "bear")
    result = _evaluate(
        bull_claims=bull_claims, bear_claims=bear_claims, matches=[*bull_matches, *bear_matches]
    )
    assert result.bull.supporting_evidence_count == 2  # evidence itself is fine
    assert result.bull.ticker_specific_support_count == 0  # but none of it is NVDA-specific
    assert result.status == CANDIDATE
    assert REASON_NO_BULL_TICKER_SPECIFIC_SUPPORT in result.reason_codes

    # Positive control, same shape, only the ticker token changed: this
    # proves the check genuinely discriminates rather than always failing.
    ticker_specific_claims = [
        _qualifying_claim("bull1", f"{TICKER} datacenter demand is accelerating.", factors=["Revenue"]),
        _qualifying_claim("bull2", f"{TICKER} new supply agreements were announced.", factors=["Supply"]),
    ]
    ticker_specific_matches = [_match(c["claim_id"], "BULL", "supports_alpha") for c in ticker_specific_claims]
    positive_result = _evaluate(
        bull_claims=ticker_specific_claims, bear_claims=bear_claims, matches=[*ticker_specific_matches, *bear_matches]
    )
    assert positive_result.bull.ticker_specific_support_count >= 1
    assert positive_result.status == ADMITTED


# ---------------------------------------------------------------------------
# (13)/(14): main-conflict arbitration -- tested through the real Conflict
# Detector (``detect_alpha_conflicts``), since these are properties of
# arbitration across multiple declared pairs, not of a single pair's
# admissibility in isolation.
# ---------------------------------------------------------------------------

_TWO_PAIR_TAXONOMY = {
    "A": fake_alpha("A", [ConflictAlpha(alpha_id="B", contradiction_weight=0.9)]),
    "B": fake_alpha("B", [ConflictAlpha(alpha_id="A", contradiction_weight=0.9)]),
    "C": fake_alpha("C", [ConflictAlpha(alpha_id="D", contradiction_weight=0.9)]),
    "D": fake_alpha("D", [ConflictAlpha(alpha_id="C", contradiction_weight=0.9)]),
}


def _raw_match(claim_id, alpha_id, evidence, *, score=0.8, stance="supports_alpha"):
    return {
        "claim_id": claim_id,
        "source_agent_output_id": f"o_{claim_id}",
        "agent": f"agent_{claim_id}",
        "match_status": "matched",
        "matched_alpha": alpha_id,
        "matched_alpha_name": alpha_id,
        "score": score,
        "direction": "positive",
        "assertion_status": "asserted",
        "semantic_polarity": "activation",
        "claim": evidence,
        "evidence": evidence,
        "reason": "test fixture",
        "plausible_alphas": [],
        "candidate_scores": [
            {"alpha_id": alpha_id, "score": score, "relation": "activation", "evidence_stance": stance}
        ],
        "claim_quality": "analytical",
        "factors": [],
    }


def test_m_candidate_conflict_can_never_become_main_conflict_regardless_of_score():
    """A/B looks strong by activation (95/95) but only has ONE unique
    supports_alpha fact on the bull side -- denied admission. C/D looks
    modest by activation (51/51, barely above B2's own threshold) but has
    genuinely sufficient, ticker-specific, supports_alpha evidence on both
    sides -- admitted. main_conflict must be C__D: a CANDIDATE conflict is
    structurally incapable of becoming main (its ``conflict`` object is
    never even constructed for the public result -- see
    conflict_detector._evaluate_candidate), regardless of how strong its
    own activation scores looked."""
    activation = activation_payload(
        activation_entry("A", score=95.0, direction="positive"),
        activation_entry("B", score=95.0, direction="negative"),
        activation_entry("C", score=51.0, direction="positive"),
        activation_entry("D", score=51.0, direction="negative"),
    )
    matches = [
        _raw_match("a1", "A", f"{TICKER} strong datacenter demand signal one."),
        _raw_match("b1", "B", f"{TICKER} strong valuation risk signal one."),
        _raw_match("c1", "C", f"{TICKER} modest datacenter demand signal one."),
        _raw_match("c2", "C", f"{TICKER} modest new supply agreement signal two."),
        _raw_match("d1", "D", f"{TICKER} modest valuation risk signal one."),
        _raw_match("d2", "D", f"{TICKER} modest margin compression signal two."),
    ]
    result = detect_alpha_conflicts(
        run_id=RUN_ID, ticker=TICKER, activation_payload=activation, alpha_matches=matches,
        taxonomy=_TWO_PAIR_TAXONOMY,
    )
    assert result["main_conflict"] is not None
    assert result["main_conflict"]["conflict_id"] == "C__D"
    assert [c["conflict_id"] for c in result["conflicts"]] == ["C__D"]

    evaluations = {(c["alpha_a"], c["alpha_b"]): c for c in result["arbitration"]["candidate_evaluations"]}
    ab = evaluations[("A", "B")]
    assert ab["outcome"] == "suppressed"
    assert ab["admissibility"]["status"] == CANDIDATE
    # The would-be-strong-looking activation scores remain visible in the
    # diagnostic (proving this was a genuinely strong-looking candidate,
    # not a weak one) -- yet it still cannot outrank a modest admitted pair.
    assert ab["admissibility"]["bull_score"] == 95.0
    assert ab["admissibility"]["bear_score"] == 95.0
    assert "conflict" not in ab


def test_n_zero_admitted_conflicts_main_is_none_and_candidates_are_preserved():
    """When every declared pair fails B2, main_conflict is None and
    conflicts is empty -- but every evaluated candidate remains fully
    visible (with its own admissibility diagnostic) in
    arbitration.candidate_evaluations, never silently deleted."""
    activation = activation_payload(
        activation_entry("A", score=95.0, direction="positive"),
        activation_entry("B", score=95.0, direction="negative"),
        activation_entry("C", score=95.0, direction="positive"),
        activation_entry("D", score=95.0, direction="negative"),
    )
    matches = [
        _raw_match("a1", "A", f"{TICKER} strong datacenter demand signal one."),
        _raw_match("b1", "B", f"{TICKER} strong valuation risk signal one."),
        _raw_match("c1", "C", f"{TICKER} strong datacenter demand signal two."),
        _raw_match("d1", "D", f"{TICKER} strong valuation risk signal two."),
    ]
    result = detect_alpha_conflicts(
        run_id=RUN_ID, ticker=TICKER, activation_payload=activation, alpha_matches=matches,
        taxonomy=_TWO_PAIR_TAXONOMY,
    )
    assert result["main_conflict"] is None
    assert result["conflicts"] == []
    evaluations = {(c["alpha_a"], c["alpha_b"]): c for c in result["arbitration"]["candidate_evaluations"]}
    assert set(evaluations) == {("A", "B"), ("C", "D")}
    for pair in (("A", "B"), ("C", "D")):
        item = evaluations[pair]
        assert item["outcome"] == "suppressed"
        assert item["admissibility"]["status"] == CANDIDATE
        assert item["admissibility"]["reason_codes"]
