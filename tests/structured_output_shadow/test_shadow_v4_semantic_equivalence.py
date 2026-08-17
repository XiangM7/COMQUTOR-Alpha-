"""Phase 1 Master evidence-alignment fix, round 2: smoke-level semantic-
equivalence tests for v4. The full exhaustive coverage of this mechanism
(split/merge/negation/hypothesis/attribution/abstain/multi-span/factor/
direction/entity enforcement/candidate lineage/identity-never-trusted/
stable IDs) already exists in test_shadow_v3_semantic_equivalence.py and
applies identically here (the resolver and normalizer are byte-identical
logic, duplicated unchanged into structured_output_shadow_v4.py). These
tests confirm that byte-identical behavior actually holds for v4's own
module -- not a full re-derivation of every case. No Provider calls.
"""

from __future__ import annotations

import json

from conftest import FakeSemanticInvoker, v4_abstention, v4_claim, v4_proposal

from comqutor_alpha.structure_engine.structured_output_shadow import build_candidate_segments
from comqutor_alpha.structure_engine.structured_output_shadow_v4 import (
    StructuredOutputShadowParserV4,
    parse_report_shadow_v4,
)


def test_single_claim_accepted_end_to_end(report):
    quote = "GPU demand increased in June."
    invoker = FakeSemanticInvoker(
        json.dumps(v4_proposal(claims=[v4_claim(claim=quote, supporting_quotes=[quote], direction="positive")]))
    )
    bundle = parse_report_shadow_v4(
        semantic_invoker=invoker,
        source_report=report,
        run_id="run-1",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id="run-1:news_agent:news_report",
        factor_vocabulary=[],
    )
    assert bundle["validation_summary"]["status"] == "accepted"
    assert bundle["claims"][0]["source_spans"] == [
        {"start": report.index(quote), "end": report.index(quote) + len(quote), "exact_quote": quote}
    ]
    assert bundle["prompt_version"] == "structured_adapter.claim_extraction_shadow.v4"


def test_multi_span_claim_produces_two_distinct_spans_never_merged():
    report = "Factory utilization rose in June. The second shift supplied the extra units."
    q1, q2 = "Factory utilization rose in June.", "The second shift supplied the extra units."
    invoker = FakeSemanticInvoker(
        json.dumps(
            v4_proposal(
                claims=[v4_claim(claim="Factory utilization rose, helped by the second shift.", supporting_quotes=[q1, q2])]
            )
        )
    )
    bundle = parse_report_shadow_v4(
        semantic_invoker=invoker,
        source_report=report,
        run_id="run-1",
        ticker="NVDA",
        agent="fundamental_agent",
        agent_output_id="run-1:fundamental_agent:fundamentals_report",
        factor_vocabulary=[],
    )
    assert bundle["validation_summary"]["valid"] is True
    spans = bundle["claims"][0]["source_spans"]
    assert len(spans) == 2 and spans[0]["exact_quote"] == q1 and spans[1]["exact_quote"] == q2


def test_hypothetical_abstains_with_bounded_abstention_record():
    report = "If input costs rise, could margins narrow? Formatting complete."
    invoker = FakeSemanticInvoker(json.dumps(v4_proposal(claims=[], abstentions=[v4_abstention()])))
    bundle = parse_report_shadow_v4(
        semantic_invoker=invoker,
        source_report=report,
        run_id="run-1",
        ticker="NVDA",
        agent="fundamental_agent",
        agent_output_id="run-1:fundamental_agent:fundamentals_report",
        factor_vocabulary=[],
    )
    assert bundle["validation_summary"]["status"] == "abstained"
    assert bundle["claims"] == []


def test_factor_outside_vocabulary_rejects_whole_bundle(report):
    quote = "Revenue growth remained strong."
    invoker = FakeSemanticInvoker(
        json.dumps(v4_proposal(claims=[v4_claim(claim=quote, supporting_quotes=[quote], factors=["not_a_real_factor"])]))
    )
    bundle = parse_report_shadow_v4(
        semantic_invoker=invoker,
        source_report=report,
        run_id="run-1",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id="run-1:news_agent:news_report",
        factor_vocabulary=["demand_growth"],
    )
    assert bundle["validation_summary"]["valid"] is False
    assert "SHADOW_FACTOR_VOCABULARY_INVALID" in bundle["validation_summary"]["reason_codes"]


def test_invalid_direction_rejects_whole_bundle(report):
    quote = "Revenue growth remained strong."
    invoker = FakeSemanticInvoker(
        json.dumps(v4_proposal(claims=[v4_claim(claim=quote, supporting_quotes=[quote], direction="bullish")]))
    )
    bundle = parse_report_shadow_v4(
        semantic_invoker=invoker,
        source_report=report,
        run_id="run-1",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id="run-1:news_agent:news_report",
        factor_vocabulary=[],
    )
    assert bundle["validation_summary"]["valid"] is False
    assert "SHADOW_DIRECTION_INVALID" in bundle["validation_summary"]["reason_codes"]


def test_ungrounded_entity_rejects_whole_bundle(report):
    quote = "Revenue growth remained strong."
    invoker = FakeSemanticInvoker(
        json.dumps(v4_proposal(claims=[v4_claim(claim=quote, supporting_quotes=[quote], entities=["Nonexistent Corp"])]))
    )
    bundle = parse_report_shadow_v4(
        semantic_invoker=invoker,
        source_report=report,
        run_id="run-1",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id="run-1:news_agent:news_report",
        factor_vocabulary=[],
    )
    assert bundle["validation_summary"]["valid"] is False
    assert "SHADOW_ENTITY_NOT_GROUNDED" in bundle["validation_summary"]["reason_codes"]


def test_candidate_lineage_resolves_to_real_candidate_segment_id(report):
    candidates, _filtered = build_candidate_segments(report, agent_output_id="run-1:news_agent:news_report")
    assert candidates
    target = candidates[0]
    quote = "GPU demand increased in June."
    invoker = FakeSemanticInvoker(
        json.dumps(
            v4_proposal(
                claims=[v4_claim(claim=quote, supporting_quotes=[quote], candidate_ids=[target["candidate_index"]])]
            )
        )
    )
    bundle = parse_report_shadow_v4(
        semantic_invoker=invoker,
        source_report=report,
        run_id="run-1",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id="run-1:news_agent:news_report",
        factor_vocabulary=[],
        candidate_segments=candidates,
    )
    assert bundle["validation_summary"]["valid"] is True
    assert bundle["claims"][0]["candidate_segment_ids"] == [target["candidate_segment_id"]]


def test_identity_and_authority_fields_never_trusted_from_the_provider(report):
    quote = "Revenue growth remained strong."
    malicious = {
        "claims": [
            {
                "claim": quote,
                "supporting_quotes": [quote],
                "entities": [],
                "factors": [],
                "direction": "unknown",
                "confidence": 0.5,
                "shadow_claim_id": "attacker-supplied-id",
                "production_authority": True,
                "shadow_only": False,
            }
        ],
        "abstentions": [],
    }
    invoker = FakeSemanticInvoker(json.dumps(malicious))
    bundle = parse_report_shadow_v4(
        semantic_invoker=invoker,
        source_report=report,
        run_id="run-1",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id="run-1:news_agent:news_report",
        factor_vocabulary=[],
    )
    assert bundle["validation_summary"]["valid"] is True
    assert bundle["claims"][0]["shadow_claim_id"] != "attacker-supplied-id"
    assert bundle["production_authority"] is False
    assert bundle["shadow_only"] is True


def test_stable_claim_id_is_deterministic_across_repeated_calls(report):
    quote = "Revenue growth remained strong."
    proposal_json = json.dumps(v4_proposal(claims=[v4_claim(claim=quote, supporting_quotes=[quote])]))
    ids = []
    for _ in range(2):
        invoker = FakeSemanticInvoker(proposal_json)
        bundle = parse_report_shadow_v4(
            semantic_invoker=invoker,
            source_report=report,
            run_id="run-fixed",
            ticker="NVDA",
            agent="news_agent",
            agent_output_id="run-fixed:news_agent:news_report",
            factor_vocabulary=[],
        )
        ids.append(bundle["claims"][0]["shadow_claim_id"])
    assert ids[0] == ids[1]
    assert ids[0].startswith("shadow-claim-v1-")


def test_full_parser_class_round_trip_and_resolution_log(report):
    quote = "Revenue growth remained strong."
    proposal_json = json.dumps(v4_proposal(claims=[v4_claim(claim=quote, supporting_quotes=[quote])]))
    parser = StructuredOutputShadowParserV4(FakeSemanticInvoker(proposal_json), factor_vocabulary=[])
    bundle = parser.parse_report_shadow_v4(
        source_report=report,
        run_id="run-1",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id="run-1:news_agent:news_report",
    )
    assert bundle["validation_summary"]["valid"] is True
    assert parser.last_resolution_log == [
        {"claim_index": 0, "quote_index": 0, "status": "UNIQUE_EXACT_MATCH", "match_count": 1}
    ]
