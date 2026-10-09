"""Discriminating tests for the verified-support eligibility gate (T1
follow-up, 2026-09-28): ``comqutor_alpha.graph_engine.verified_evidence_
gate`` wraps the REAL, unmodified ``score_alpha_v2`` (Activation v2) and
``evaluate_conflict_admissibility`` (frozen B2 admissibility) -- these
tests exercise those two production functions directly through the
wrapper, never just ``compute_verified_support_eligibility`` in isolation,
so a passing test actually proves the gate changes real Activation/
Admissibility output, not merely that the eligibility helper itself
computes a boolean correctly.

Every fixture below satisfies the ORIGINAL, unchanged admission thresholds
(``ALPHA_SCORE_THRESHOLD=50.0``, ``MIN_SUPPORTING_EVIDENCE_PER_SIDE=2``,
``MIN_TICKER_SPECIFIC_SUPPORT_PER_SIDE=1`` -- reused, never redefined) --
the only variable between a passing and failing case is each claim's own
``source_link_status``/``content_support_review``, never a relaxed
threshold or a rewritten assertion.
"""

from __future__ import annotations

from functools import partial

import pytest

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.conflict_engine.conflict_admissibility import ADMITTED, evaluate_conflict_admissibility
from comqutor_alpha.conflict_engine.conflict_detector import _group_qualifying_claims_into_facts
from comqutor_alpha.graph_engine.activation_scorer_v2 import score_alpha_v2
from comqutor_alpha.graph_engine.verified_evidence_gate import (
    evaluate_conflict_admissibility_verified,
    filter_verified_qualifying_claims,
    index_structured_records_by_claim_id,
    score_alpha_v2_verified,
)
from comqutor_alpha.source_provenance import (
    ELIGIBILITY_REASON_CONTENT_VERSION_CHANGED_SINCE_REVIEW,
    ELIGIBILITY_REASON_ELIGIBLE,
    ELIGIBILITY_REASON_NOT_REVIEWED,
    ELIGIBILITY_REASON_SOURCE_LINK_NOT_VALID,
    ELIGIBILITY_REASON_SOURCE_OPPOSES_CLAIM,
    ELIGIBILITY_REASON_SUPPORT_STATUS_NOT_RESOLVED,
    SOURCE_LINK_VALID,
    SUPPORT_BACKGROUND,
    SUPPORT_CITATION_ONLY,
    SUPPORT_OPPOSES,
    SUPPORT_PENDING_REVIEW,
    SUPPORT_SUPPORTS,
    apply_content_support_review,
    build_content_support_review,
    compute_verified_support_eligibility,
)

TAXONOMY = load_alpha_taxonomy()
RUN_ID = "verified_gate_test_run"
TICKER = "NVDA"
_GROUP_INTO_FACTS = partial(_group_qualifying_claims_into_facts, run_id=RUN_ID, ticker=TICKER)


def _source(source_id: str, content_hash: str) -> dict:
    fragment_id = f"{source_id}:frag-0"
    # published_at is REQUIRED, not optional fixture detail: John follow-up
    # round task (2026-09-30) traced every "a valid, complete human review
    # should produce ELIGIBLE/ADMITTED" test in this file failing with
    # reason_code=DISCLOSURE_TIME_UNKNOWN -- a real, deliberately added
    # 2026-09-29 gate (compute_verified_support_eligibility's own docstring,
    # item 6) that this helper predates. A source whose disclosure timing is
    # unknown never counts as verified support, however resolvable/reviewed
    # it otherwise is -- this is the real, already-confirmed production
    # contract working as designed, not an implementation defect. Fixed
    # here, not by lowering any test's expected outcome.
    return {
        "source_id": source_id,
        "fragment_id": fragment_id,
        "content_hash": content_hash,
        "published_at": "2026-06-25T00:00:00Z",
    }


def _qualifying_claim(claim_id: str, evidence: str, *, factors: tuple[str, ...] = ()) -> dict:
    """The exact shape ``_gather_qualifying_evidence``/``conflict_detector``
    already produce for a qualifying claim -- never a
    ``content_support_review``/``source_link_status`` field of its own; those
    live only on the claim's own persisted structured record, looked up
    separately by claim_id (exactly as production does)."""
    return {
        "claim_id": claim_id,
        "match_score": 0.8,
        "evidence": evidence,
        "source_agent_output_id": f"o_{claim_id}",
        "agent": f"agent_{claim_id}",
        "factors": tuple(factors),
        "assertion_status": "asserted",
        "semantic_polarity": "activation",
    }


def _match(claim_id: str, alpha_id: str, stance: str) -> dict:
    candidate = {"alpha_id": alpha_id, "score": 0.8, "relation": "activation", "evidence_stance": stance}
    return {"claim_id": claim_id, "candidate_scores": [candidate]}


def _human_reviewed_record(claim_id: str, source: dict, *, status: str) -> dict:
    review = apply_content_support_review(
        {"claim_id": claim_id, "source_link_status": SOURCE_LINK_VALID, "linked_source_id": source["fragment_id"]},
        status=status,
        reviewer="analyst_a",
        rationale="human-reviewed against the captured excerpt",
        reviewed_at="2026-09-28T00:00:00Z",
        sources=[source],
    )
    return review


def _pending_record(claim_id: str, source: dict) -> dict:
    return {
        "claim_id": claim_id,
        "source_link_status": SOURCE_LINK_VALID,
        "linked_source_id": source["fragment_id"],
        "content_support_status": SUPPORT_PENDING_REVIEW,
        "content_support_review": build_content_support_review(SUPPORT_PENDING_REVIEW),
    }


def _two_claims_and_matches(side: str, alpha_id: str) -> tuple[list[dict], list[dict]]:
    claims = [
        _qualifying_claim(f"{side}_1", f"{TICKER} datacenter demand is accelerating.", factors=["Revenue"]),
        _qualifying_claim(f"{side}_2", f"{TICKER} new supply agreements were announced.", factors=["Supply"]),
    ]
    matches = [_match(c["claim_id"], alpha_id, "supports_alpha") for c in claims]
    return claims, matches


def _evaluate_verified(*, bull_claims, bear_claims, matches, structured_records, sources, bull_score=60.0, bear_score=60.0):
    return evaluate_conflict_admissibility_verified(
        bull_alpha_id="BULL",
        bear_alpha_id="BEAR",
        bull_score=bull_score,
        bear_score=bear_score,
        bull_qualifying_claims=bull_claims,
        bear_qualifying_claims=bear_claims,
        alpha_matches=matches,
        ticker=TICKER,
        group_into_facts=_GROUP_INTO_FACTS,
        structured_records=structured_records,
        sources=sources,
    )


def _baseline_result(*, bull_claims, bear_claims, matches, bull_score=60.0, bear_score=60.0):
    """The SAME real, unmodified, unfiltered ``evaluate_conflict_
    admissibility`` -- used as the "would admit under today's existing
    (unverified) rules" control, so each test proves the gate actually
    CHANGES the outcome, not merely that the wrapper runs."""
    return evaluate_conflict_admissibility(
        bull_alpha_id="BULL",
        bear_alpha_id="BEAR",
        bull_score=bull_score,
        bear_score=bear_score,
        bull_qualifying_claims=bull_claims,
        bear_qualifying_claims=bear_claims,
        alpha_matches=matches,
        ticker=TICKER,
        group_into_facts=_GROUP_INTO_FACTS,
    )


# ---------------------------------------------------------------------------
# (1) An evidence set satisfying every ORIGINAL admission condition (score,
# count, ticker-specificity), with review status forced to PENDING_REVIEW
# only, must NOT reach verified ADMITTED.
# ---------------------------------------------------------------------------


def test_pending_review_only_does_not_reach_verified_admitted():
    bull_claims, bull_matches = _two_claims_and_matches("bull", "BULL")
    bear_claims, bear_matches = _two_claims_and_matches("bear", "BEAR")
    matches = [*bull_matches, *bear_matches]

    sources = [_source("s_bull_1", "h1"), _source("s_bull_2", "h2"), _source("s_bear_1", "h3"), _source("s_bear_2", "h4")]
    structured_records = [
        _pending_record("bull_1", sources[0]),
        _pending_record("bull_2", sources[1]),
        _pending_record("bear_1", sources[2]),
        _pending_record("bear_2", sources[3]),
    ]

    # Control: the SAME evidence, through the REAL unfiltered production
    # function, already admits today (proves the fixture itself is sound
    # and satisfies every original threshold).
    baseline = _baseline_result(bull_claims=bull_claims, bear_claims=bear_claims, matches=matches)
    assert baseline.status == ADMITTED

    verified = _evaluate_verified(
        bull_claims=bull_claims, bear_claims=bear_claims, matches=matches,
        structured_records=structured_records, sources=sources,
    )
    assert verified.status != ADMITTED
    assert verified.bull.supporting_evidence_count == 0
    assert verified.bear.supporting_evidence_count == 0


# ---------------------------------------------------------------------------
# (2) The SAME set, now with a valid source and a complete, valid human
# review, produces the expected (admitted) result under the ORIGINAL rules.
# ---------------------------------------------------------------------------


def test_valid_source_and_complete_human_review_produces_expected_admitted_result():
    bull_claims, bull_matches = _two_claims_and_matches("bull", "BULL")
    bear_claims, bear_matches = _two_claims_and_matches("bear", "BEAR")
    matches = [*bull_matches, *bear_matches]

    sources = [_source("s_bull_1", "h1"), _source("s_bull_2", "h2"), _source("s_bear_1", "h3"), _source("s_bear_2", "h4")]
    structured_records = [
        _human_reviewed_record("bull_1", sources[0], status=SUPPORT_SUPPORTS),
        _human_reviewed_record("bull_2", sources[1], status=SUPPORT_SUPPORTS),
        _human_reviewed_record("bear_1", sources[2], status=SUPPORT_SUPPORTS),
        _human_reviewed_record("bear_2", sources[3], status=SUPPORT_SUPPORTS),
    ]

    verified = _evaluate_verified(
        bull_claims=bull_claims, bear_claims=bear_claims, matches=matches,
        structured_records=structured_records, sources=sources,
    )
    assert verified.status == ADMITTED
    assert verified.reason_codes == ()
    assert verified.bull.supporting_evidence_count == 2
    assert verified.bear.supporting_evidence_count == 2
    assert verified.bull.ticker_specific_support_count >= 1
    assert verified.bear.ticker_specific_support_count >= 1


# ---------------------------------------------------------------------------
# (3) BACKGROUND/CITATION_ONLY -- even under a genuine HUMAN_REVIEWED review
# -- must never count as direct supporting evidence.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("non_support_status", [SUPPORT_BACKGROUND, SUPPORT_CITATION_ONLY])
def test_background_and_citation_only_never_count_as_direct_support(non_support_status):
    source = _source("s1", "h1")
    record = _human_reviewed_record("c1", source, status=non_support_status)
    eligibility = compute_verified_support_eligibility(record, [source])
    assert eligibility["eligible"] is False
    assert eligibility["reason_code"] == ELIGIBILITY_REASON_SUPPORT_STATUS_NOT_RESOLVED

    claims = [_qualifying_claim("c1", f"{TICKER} background context only.")]
    kept = filter_verified_qualifying_claims(claims, index_structured_records_by_claim_id([record]), [source])
    assert kept == []


# ---------------------------------------------------------------------------
# (4) Eligibility is lost when the source becomes invalid, the review is
# missing, or the content version changes since review.
# ---------------------------------------------------------------------------


def test_eligibility_lost_on_invalid_source_missing_review_or_content_change():
    source = _source("s1", "h1")

    valid_record = _human_reviewed_record("c1", source, status=SUPPORT_SUPPORTS)
    assert compute_verified_support_eligibility(valid_record, [source])["reason_code"] == ELIGIBILITY_REASON_ELIGIBLE

    invalid_source_record = dict(valid_record)
    invalid_source_record["source_link_status"] = "CONTENT_UNAVAILABLE"
    result = compute_verified_support_eligibility(invalid_source_record, [source])
    assert result["eligible"] is False
    assert result["reason_code"] == ELIGIBILITY_REASON_SOURCE_LINK_NOT_VALID

    missing_review_record = dict(valid_record)
    missing_review_record["content_support_review"] = None
    result = compute_verified_support_eligibility(missing_review_record, [source])
    assert result["eligible"] is False
    assert result["reason_code"] == ELIGIBILITY_REASON_NOT_REVIEWED

    changed_content_source = _source("s1", "h1-changed")
    result = compute_verified_support_eligibility(valid_record, [changed_content_source])
    assert result["eligible"] is False
    assert result["reason_code"] == ELIGIBILITY_REASON_CONTENT_VERSION_CHANGED_SINCE_REVIEW


# ---------------------------------------------------------------------------
# (5) Opposing evidence (content_support_review.status == OPPOSES) retains
# its correct direction/role -- it is NOT miscast as unsupported/invalid,
# and its own (independent) evidence_stance/bull-bear role is unaffected.
# ---------------------------------------------------------------------------


def test_opposing_content_review_is_excluded_from_verified_support_not_treated_as_ambiguous():
    """Part 2 correction (2026-09-28): content_support_status=OPPOSES means
    the source REBUTS this claim's own assertion -- it must NOT count as
    verified support for whichever camp the claim's evidence_stance placed
    it in. It is still a real, resolved, HUMAN_REVIEWED signal (never
    lumped in with PENDING_REVIEW/BACKGROUND as merely "unresolved") -- its
    own reason code and support_status preserve the rebuttal relationship
    rather than discarding it -- but the claim is never auto-flipped to
    argue the opposite thesis; it is simply excluded from the verified-
    support pool its own side would otherwise have drawn it into."""
    source = _source("s_opposes", "h1")
    record = _human_reviewed_record("bear_3", source, status=SUPPORT_OPPOSES)
    eligibility = compute_verified_support_eligibility(record, [source])
    assert eligibility["eligible"] is False
    assert eligibility["reason_code"] == ELIGIBILITY_REASON_SOURCE_OPPOSES_CLAIM
    assert eligibility["support_status"] == SUPPORT_OPPOSES

    bull_claims, bull_matches = _two_claims_and_matches("bull", "BULL")
    bear_claims, bear_matches = _two_claims_and_matches("bear", "BEAR")
    bear_extra_claim = _qualifying_claim(
        "bear_3", f"{TICKER} margin pressure from rising input costs.", factors=["Margin"]
    )
    bear_extra_match = _match("bear_3", "BEAR", "supports_alpha")
    bear_claims = [*bear_claims, bear_extra_claim]
    matches = [*bull_matches, *bear_matches, bear_extra_match]

    bull_sources = [_source("s_bull_1", "hb1"), _source("s_bull_2", "hb2")]
    bear_sources = [_source("s_bear_1", "hbe1"), _source("s_bear_2", "hbe2")]
    structured_records = [
        _human_reviewed_record("bull_1", bull_sources[0], status=SUPPORT_SUPPORTS),
        _human_reviewed_record("bull_2", bull_sources[1], status=SUPPORT_SUPPORTS),
        _human_reviewed_record("bear_1", bear_sources[0], status=SUPPORT_SUPPORTS),
        _human_reviewed_record("bear_2", bear_sources[1], status=SUPPORT_SUPPORTS),
        record,  # bear_3's own review: OPPOSES -- must be excluded, never counted, never flipped.
    ]
    sources = [*bull_sources, *bear_sources, source]

    verified_bear_pool = filter_verified_qualifying_claims(
        bear_claims, index_structured_records_by_claim_id(structured_records), sources
    )
    assert {c["claim_id"] for c in verified_bear_pool} == {"bear_1", "bear_2"}

    verified = _evaluate_verified(
        bull_claims=bull_claims, bear_claims=bear_claims, matches=matches,
        structured_records=structured_records, sources=sources,
    )
    assert verified.status == ADMITTED
    # Only the two genuine SUPPORTS-reviewed bear claims count; bear_3
    # (OPPOSES) is excluded, yet the two real supports alone still satisfy
    # MIN_SUPPORTING_EVIDENCE_PER_SIDE -- the exclusion of a rebutting
    # citation never wrongly suppresses the side's genuine support.
    assert verified.bear.supporting_evidence_count == 2


# ---------------------------------------------------------------------------
# Activation link: score_alpha_v2_verified over the SAME real, unmodified
# score_alpha_v2 -- closes the "Evidence Fact -> Activation" segment of the
# required chain (the admissibility tests above inject a fixed score and so
# never exercise score_alpha_v2 itself).
# ---------------------------------------------------------------------------


def test_score_alpha_v2_verified_drops_unreviewed_evidence_from_activation_pool():
    payload = {
        "run_id": RUN_ID,
        "ticker": TICKER,
        "matches": [
            {
                "run_id": RUN_ID, "ticker": TICKER, "agent": "market_agent", "claim_id": "act_1",
                "claim": f"{TICKER} datacenter revenue growth is accelerating.",
                "evidence": f"{TICKER} datacenter revenue growth is accelerating.",
                "match_status": "matched", "matched_alpha": "A101", "score": 1.0,
                "assertion_status": "asserted", "semantic_polarity": "activation",
                "factor_score": 1.0, "keyword_score": 1.0,
                "eligible_candidates": [{"alpha_id": "A101", "relation": "activation", "matched_keywords": ["demand"], "matched_factors": ["Revenue Growth"]}],
                "claim_quality": "analytical", "direction": "positive",
            },
            {
                "run_id": RUN_ID, "ticker": TICKER, "agent": "fundamental_agent", "claim_id": "act_2",
                "claim": f"{TICKER}'s order backlog continues to expand this quarter.",
                "evidence": f"{TICKER}'s order backlog continues to expand this quarter.",
                "match_status": "matched", "matched_alpha": "A101", "score": 1.0,
                "assertion_status": "asserted", "semantic_polarity": "activation",
                "factor_score": 1.0, "keyword_score": 1.0,
                "eligible_candidates": [{"alpha_id": "A101", "relation": "activation", "matched_keywords": ["backlog"], "matched_factors": ["Order Backlog"]}],
                "claim_quality": "analytical", "direction": "positive",
            },
        ],
    }
    source = _source("s1", "h1")
    structured_records = [
        _human_reviewed_record("act_1", source, status=SUPPORT_SUPPORTS),
        _pending_record("act_2", _source("s2", "h2")),
    ]

    baseline = score_alpha_v2(
        "A101", payload, TAXONOMY, ticker=TICKER, run_timestamp="2026-06-30", as_of="2026-06-30",
    )
    verified = score_alpha_v2_verified(
        "A101", payload, TAXONOMY, structured_records=structured_records, sources=[source, _source("s2", "h2")],
        ticker=TICKER, run_timestamp="2026-06-30", as_of="2026-06-30",
    )
    assert baseline["components"]["evidence_quality"]["unique_semantic_groups"] == 2
    assert verified["components"]["evidence_quality"]["unique_semantic_groups"] == 1
    assert verified["activation_score"] < baseline["activation_score"]
