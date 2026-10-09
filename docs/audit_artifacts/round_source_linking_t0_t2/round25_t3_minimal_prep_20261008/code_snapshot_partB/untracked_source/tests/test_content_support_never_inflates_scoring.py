"""T1 Part Two (COMQUTOR Alpha next-round task, 2026-09-28): proves, along
the REAL Activation v2 scoring path and the REAL B2 conflict-admissibility
path -- never a re-implementation or a mock of either -- that
``content_support_status`` (SUPPORTS/OPPOSES/BACKGROUND/CITATION_ONLY/
CONDITIONAL/PENDING_REVIEW/NOT_APPLICABLE) has ZERO influence on either
path's real output.

This matters because T1 explicitly forbids "待审核、内容缺失或不支持的材料...
作为充分支持直接抬高 qualified Alpha 或 admitted conflict" (material that is
pending review, missing content, or non-supporting must never, by itself,
be treated as sufficient support that inflates a qualified Alpha or an
admitted conflict). The existing, unmodified scoring/admissibility gates
(comqutor_alpha.graph_engine.activation_scorer_v2.score_alpha_v2,
comqutor_alpha.conflict_engine.conflict_admissibility.
evaluate_conflict_admissibility) already read ONLY ``evidence_stance``
(via B1's own already-existing classification) as their real support
signal -- they never read ``content_support_status`` at all (grep-
confirmed: zero references in either module). These tests prove that
invariant BEHAVIORALLY, not just by static absence of a reference: two
claims identical in every field that actually feeds the real formula, but
carrying different ``content_support_status`` values, MUST produce
byte-identical scoring output.

A synthetic fixture may freely label ``content_support_status`` as
SUPPORTS/OPPOSES/etc. for this behavioral proof (T1 explicitly allows
"带审核来源的固定 fixtures" for exercising downstream logic) -- this never
means any of these labels are asserted as a real, human-reviewed
``john_approved``/production verdict.
"""

from __future__ import annotations

import pytest

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.conflict_engine.conflict_admissibility import (
    ADMITTED,
    CANDIDATE,
    evaluate_conflict_admissibility,
)
from comqutor_alpha.graph_engine.activation_scorer_v2 import score_alpha_v2
from comqutor_alpha.graph_engine.evidence_fact_index import group_evidence_candidates

TAXONOMY = load_alpha_taxonomy()
AS_OF = "2026-06-30"
RUN_TS = "2026-06-30"
ALPHA = "A304"


def _record(claim_id, agent, claim, *, content_support_status, source_link_status="VALID", linked_source_id=None):
    """Identical in every field score_alpha_v2's real formula actually
    reads (assertion_status/semantic_polarity/factor_score/keyword_score/
    claim_quality/direction/eligible_candidates) across every call in a
    given test -- only content_support_status (and its companion linkage
    fields) vary."""
    candidate = {
        "alpha_id": ALPHA,
        "relation": "activation",
        "matched_keywords": ["demand"],
        "matched_factors": ["Revenue Growth"],
    }
    return {
        "run_id": "oracle_run",
        "ticker": "ACME",
        "agent": agent,
        "claim_id": claim_id,
        "source_agent_output_id": f"{agent}:source",
        "claim": claim,
        "evidence": claim,
        "match_status": "matched",
        "matched_alpha": ALPHA,
        "score": 1.0,
        "assertion_status": "asserted",
        "semantic_polarity": "activation",
        "factor_score": 1.0,
        "keyword_score": 1.0,
        "eligible_candidates": [candidate],
        "claim_quality": "analytical",
        "direction": "positive",
        # The fields under test -- vary freely across otherwise-identical
        # calls; score_alpha_v2 must never read these.
        "content_support_status": content_support_status,
        "source_link_status": source_link_status,
        "linked_source_id": linked_source_id,
    }


def _payload(*records):
    return {"run_id": "oracle_run", "ticker": "ACME", "matches": list(records)}


def _score(payload):
    return score_alpha_v2(ALPHA, payload, TAXONOMY, graph_edges=(), ticker="ACME", run_timestamp=RUN_TS, as_of=AS_OF)


CONTENT_SUPPORT_STATUSES = [
    "SUPPORTS",
    "OPPOSES",
    "BACKGROUND",
    "CITATION_ONLY",
    "CONDITIONAL",
    "PENDING_REVIEW",
    "NOT_APPLICABLE",
]


class TestContentSupportStatusNeverAffectsActivationScoring:
    @pytest.mark.parametrize("content_support_status", CONTENT_SUPPORT_STATUSES)
    def test_activation_score_is_identical_regardless_of_content_support_status(self, content_support_status):
        baseline_payload = _payload(
            _record("c1", "news_agent", "Revenue growth accelerated sharply.", content_support_status="NOT_APPLICABLE"),
            _record("c2", "market_agent", "Guidance was raised for the coming year.", content_support_status="NOT_APPLICABLE"),
        )
        varied_payload = _payload(
            _record("c1", "news_agent", "Revenue growth accelerated sharply.", content_support_status=content_support_status),
            _record("c2", "market_agent", "Guidance was raised for the coming year.", content_support_status=content_support_status),
        )
        baseline = _score(baseline_payload)
        varied = _score(varied_payload)
        assert baseline == varied

    def test_opposing_content_support_status_never_gets_pooled_as_supporting(self):
        # A claim explicitly labeled OPPOSES (a simulated human-review
        # verdict against this claim's own cited source) must not gain any
        # scoring advantage over one labeled SUPPORTS -- both still score
        # identically because the REAL formula reads evidence_stance/
        # assertion_status, never this field. This directly proves "反对证据
        # 不能算作对原命题的支持" holds at the scoring layer, not merely by
        # field-naming convention.
        supports_payload = _payload(
            _record("c1", "news_agent", "Revenue growth accelerated sharply.", content_support_status="SUPPORTS")
        )
        opposes_payload = _payload(
            _record("c1", "news_agent", "Revenue growth accelerated sharply.", content_support_status="OPPOSES")
        )
        assert _score(supports_payload) == _score(opposes_payload)


class TestContentSupportStatusNeverAffectsConflictAdmissibility:
    def _sides(self, *, bull_content_support_status, bear_content_support_status):
        def group_into_facts(claims):
            from comqutor_alpha.graph_engine.evidence_fact_index import EvidenceFactCandidate

            by_id = {c["claim_id"]: c for c in claims}
            candidates = [
                EvidenceFactCandidate(claim_id=c["claim_id"], claim_text=c["evidence"]) for c in claims
            ]
            groups = group_evidence_candidates(candidates, "ACME")

            class _Summary:
                def __init__(self, groups):
                    self.fact_group_ids = [f"g{i}" for i in range(len(groups))]
                    self.fact_groups = [[by_id[c.claim_id] for c in g] for g in groups]

            return _Summary(groups)

        bull_claims = [
            {
                "claim_id": "bull1",
                "evidence": "ACME revenue accelerated sharply this quarter, beating estimates.",
                "evidence_stance": "supports_alpha",
                "entities": ["ACME"],
                "content_support_status": bull_content_support_status,
            },
            {
                "claim_id": "bull2",
                "evidence": "ACME margins expanded meaningfully on operating leverage.",
                "evidence_stance": "supports_alpha",
                "entities": ["ACME"],
                "content_support_status": bull_content_support_status,
            },
        ]
        bear_claims = [
            {
                "claim_id": "bear1",
                "evidence": "ACME valuation multiples look stretched relative to history.",
                "evidence_stance": "supports_alpha",
                "entities": ["ACME"],
                "content_support_status": bear_content_support_status,
            },
            {
                "claim_id": "bear2",
                "evidence": "ACME competitive pressure is intensifying across the segment.",
                "evidence_stance": "supports_alpha",
                "entities": ["ACME"],
                "content_support_status": bear_content_support_status,
            },
        ]
        alpha_matches = [
            {"claim_id": c["claim_id"], "candidate_scores": [{"alpha_id": "BULL", "evidence_stance": "supports_alpha"}]}
            for c in bull_claims
        ] + [
            {"claim_id": c["claim_id"], "candidate_scores": [{"alpha_id": "BEAR", "evidence_stance": "supports_alpha"}]}
            for c in bear_claims
        ]
        return bull_claims, bear_claims, alpha_matches, group_into_facts

    def test_admissibility_result_is_identical_regardless_of_content_support_status(self):
        bull_claims, bear_claims, alpha_matches, group_into_facts = self._sides(
            bull_content_support_status="NOT_APPLICABLE", bear_content_support_status="NOT_APPLICABLE"
        )
        baseline = evaluate_conflict_admissibility(
            bull_alpha_id="BULL", bear_alpha_id="BEAR", bull_score=80.0, bear_score=80.0,
            bull_qualifying_claims=bull_claims, bear_qualifying_claims=bear_claims,
            alpha_matches=alpha_matches, ticker="ACME", group_into_facts=group_into_facts,
        )

        bull_claims2, bear_claims2, alpha_matches2, group_into_facts2 = self._sides(
            bull_content_support_status="SUPPORTS", bear_content_support_status="OPPOSES"
        )
        varied = evaluate_conflict_admissibility(
            bull_alpha_id="BULL", bear_alpha_id="BEAR", bull_score=80.0, bear_score=80.0,
            bull_qualifying_claims=bull_claims2, bear_qualifying_claims=bear_claims2,
            alpha_matches=alpha_matches2, ticker="ACME", group_into_facts=group_into_facts2,
        )
        assert baseline.status == varied.status == ADMITTED
        assert baseline.to_dict() == varied.to_dict()

    def test_pending_review_content_never_elevates_a_below_threshold_candidate_to_admitted(self):
        # Only ONE claim per side -- below B2's own MIN_SUPPORTING_EVIDENCE_
        # PER_SIDE=2 threshold regardless of content_support_status. Even
        # labeling it SUPPORTS must not push it over B2's real, unmodified
        # threshold -- proving PENDING_REVIEW/SUPPORTS labels never
        # substitute for genuine independent evidence count.
        def group_into_facts(claims):
            from comqutor_alpha.graph_engine.evidence_fact_index import (
                EvidenceFactCandidate,
            )

            by_id = {c["claim_id"]: c for c in claims}
            candidates = [EvidenceFactCandidate(claim_id=c["claim_id"], claim_text=c["evidence"]) for c in claims]
            groups = group_evidence_candidates(candidates, "ACME")

            class _Summary:
                def __init__(self, groups):
                    self.fact_group_ids = [f"g{i}" for i in range(len(groups))]
                    self.fact_groups = [[by_id[c.claim_id] for c in g] for g in groups]

            return _Summary(groups)

        for content_support_status in ("SUPPORTS", "PENDING_REVIEW"):
            bull_claims = [
                {
                    "claim_id": "bull1", "evidence": "Revenue accelerated sharply this quarter.",
                    "evidence_stance": "supports_alpha", "entities": ["ACME"],
                    "content_support_status": content_support_status,
                }
            ]
            bear_claims = [
                {
                    "claim_id": "bear1", "evidence": "ACME valuation multiples look stretched relative to history.",
                    "evidence_stance": "supports_alpha", "entities": ["ACME"],
                    "content_support_status": content_support_status,
                },
                {
                    "claim_id": "bear2", "evidence": "ACME competitive pressure is intensifying across the segment.",
                    "evidence_stance": "supports_alpha", "entities": ["ACME"],
                    "content_support_status": content_support_status,
                },
            ]
            alpha_matches = [
                {"claim_id": "bull1", "candidate_scores": [{"alpha_id": "BULL", "evidence_stance": "supports_alpha"}]},
                {"claim_id": "bear1", "candidate_scores": [{"alpha_id": "BEAR", "evidence_stance": "supports_alpha"}]},
                {"claim_id": "bear2", "candidate_scores": [{"alpha_id": "BEAR", "evidence_stance": "supports_alpha"}]},
            ]
            result = evaluate_conflict_admissibility(
                bull_alpha_id="BULL", bear_alpha_id="BEAR", bull_score=80.0, bear_score=80.0,
                bull_qualifying_claims=bull_claims, bear_qualifying_claims=bear_claims,
                alpha_matches=alpha_matches, ticker="ACME", group_into_facts=group_into_facts,
            )
            assert result.status == CANDIDATE, content_support_status
            assert "INSUFFICIENT_BULL_SUPPORTING_EVIDENCE" in result.reason_codes
