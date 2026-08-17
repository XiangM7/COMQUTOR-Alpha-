"""Phase 1 Master evidence-alignment fix: end-to-end semantic-equivalence
tests for v3 (Provider proposal -> EvidenceQuoteResolver -> deterministic
normalization -> EXISTING canonical Shadow Schema -> EXISTING validator).
Mirrors test_shadow_v2_semantic_equivalence.py's coverage exactly, adapted
to v3's supporting_quotes proposal shape. Fake Provider only; zero Provider
calls.
"""

from __future__ import annotations

import json

from conftest import FakeSemanticInvoker, v3_abstention, v3_claim, v3_proposal

from comqutor_alpha.structure_engine.structured_output_shadow import build_candidate_segments
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v2 import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V2_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v3 import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V3_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3,
)
from comqutor_alpha.structure_engine.structured_output_shadow_v2 import build_shadow_request_v2
from comqutor_alpha.structure_engine.structured_output_shadow_v3 import (
    StructuredOutputShadowParserV3,
    build_shadow_request_v3,
    normalize_v3_proposal_to_canonical_bundle,
    parse_report_shadow_v3,
)


def test_single_claim_accepted_end_to_end(report):
    quote = "GPU demand increased in June."
    invoker = FakeSemanticInvoker(
        json.dumps(v3_proposal(claims=[v3_claim(claim=quote, supporting_quotes=[quote], direction="positive")]))
    )
    bundle = parse_report_shadow_v3(
        semantic_invoker=invoker,
        source_report=report,
        run_id="run-1",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id="run-1:news_agent:news_report",
        factor_vocabulary=[],
    )
    assert bundle["validation_summary"]["status"] == "accepted"
    assert bundle["claims"][0]["claim"] == quote
    assert bundle["claims"][0]["evidence"] == quote
    assert bundle["claims"][0]["source_spans"] == [
        {"start": report.index(quote), "end": report.index(quote) + len(quote), "exact_quote": quote}
    ]


def test_split_two_sentences_into_two_claims(report):
    q1, q2 = "GPU demand increased in June.", "Revenue growth remained strong."
    invoker = FakeSemanticInvoker(
        json.dumps(
            v3_proposal(
                claims=[
                    v3_claim(claim=q1, supporting_quotes=[q1]),
                    v3_claim(claim=q2, supporting_quotes=[q2]),
                ]
            )
        )
    )
    bundle = parse_report_shadow_v3(
        semantic_invoker=invoker,
        source_report=report,
        run_id="run-1",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id="run-1:news_agent:news_report",
        factor_vocabulary=[],
    )
    assert bundle["validation_summary"]["valid"] is True
    assert len(bundle["claims"]) == 2
    assert {c["claim"] for c in bundle["claims"]} == {q1, q2}


def test_merge_two_supporting_quotes_produce_two_distinct_spans_never_one():
    report = "Factory utilization rose in June. The second shift supplied the extra units."
    q1, q2 = "Factory utilization rose in June.", "The second shift supplied the extra units."
    invoker = FakeSemanticInvoker(
        json.dumps(
            v3_proposal(
                claims=[
                    v3_claim(
                        claim="Factory utilization rose in June, helped by the second shift.",
                        supporting_quotes=[q1, q2],
                    )
                ]
            )
        )
    )
    bundle = parse_report_shadow_v3(
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
    assert len(spans) == 2
    assert spans[0]["exact_quote"] == q1
    assert spans[1]["exact_quote"] == q2
    # Never a fabricated concatenated single span across two report locations.
    assert spans[0]["end"] != spans[1]["start"]
    assert bundle["claims"][0]["evidence"] == f"{q1} {q2}"


def test_negation_preserved_when_evidence_correctly_cited():
    report = "The review found no decline in renewal demand this quarter."
    quote = "The review found no decline in renewal demand this quarter."
    claim_text = "The review found no decline in renewal demand."
    invoker = FakeSemanticInvoker(
        json.dumps(v3_proposal(claims=[v3_claim(claim=claim_text, supporting_quotes=[quote])]))
    )
    bundle = parse_report_shadow_v3(
        semantic_invoker=invoker,
        source_report=report,
        run_id="run-1",
        ticker="NVDA",
        agent="fundamental_agent",
        agent_output_id="run-1:fundamental_agent:fundamentals_report",
        factor_vocabulary=[],
    )
    assert bundle["validation_summary"]["valid"] is True
    assert "no decline" in bundle["claims"][0]["claim"]


def test_hypothetical_abstains_with_bounded_abstention_record():
    report = "If input costs rise, could margins narrow? Formatting complete."
    invoker = FakeSemanticInvoker(json.dumps(v3_proposal(claims=[], abstentions=[v3_abstention()])))
    bundle = parse_report_shadow_v3(
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
    assert len(bundle["abstentions"]) == 1


def test_quoted_attribution_preserved_in_claim_text():
    report = 'Analysts said demand "may accelerate" in the second half.'
    quote = 'Analysts said demand "may accelerate" in the second half.'
    invoker = FakeSemanticInvoker(
        json.dumps(v3_proposal(claims=[v3_claim(claim=quote, supporting_quotes=[quote])]))
    )
    bundle = parse_report_shadow_v3(
        semantic_invoker=invoker,
        source_report=report,
        run_id="run-1",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id="run-1:news_agent:news_report",
        factor_vocabulary=[],
    )
    assert bundle["validation_summary"]["valid"] is True
    assert "Analysts said" in bundle["claims"][0]["claim"]


def test_temporal_qualification_preserved():
    report = "Margins narrowed in Q1 but are expected to recover by Q3."
    quote = "Margins narrowed in Q1 but are expected to recover by Q3."
    invoker = FakeSemanticInvoker(
        json.dumps(v3_proposal(claims=[v3_claim(claim=quote, supporting_quotes=[quote], direction="negative")]))
    )
    bundle = parse_report_shadow_v3(
        semantic_invoker=invoker,
        source_report=report,
        run_id="run-1",
        ticker="NVDA",
        agent="fundamental_agent",
        agent_output_id="run-1:fundamental_agent:fundamentals_report",
        factor_vocabulary=[],
    )
    assert bundle["validation_summary"]["valid"] is True
    assert "Q1" in bundle["claims"][0]["claim"] and "Q3" in bundle["claims"][0]["claim"]


def test_confidence_and_direction_pass_through_when_valid(report):
    quote = "Revenue growth remained strong."
    invoker = FakeSemanticInvoker(
        json.dumps(
            v3_proposal(
                claims=[v3_claim(claim=quote, supporting_quotes=[quote], direction="positive", confidence=0.42)]
            )
        )
    )
    bundle = parse_report_shadow_v3(
        semantic_invoker=invoker,
        source_report=report,
        run_id="run-1",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id="run-1:news_agent:news_report",
        factor_vocabulary=[],
    )
    assert bundle["validation_summary"]["valid"] is True
    assert bundle["claims"][0]["direction"] == "positive"
    assert bundle["claims"][0]["confidence"] == 0.42


def test_invalid_direction_rejects_whole_bundle(report):
    quote = "Revenue growth remained strong."
    invoker = FakeSemanticInvoker(
        json.dumps(v3_proposal(claims=[v3_claim(claim=quote, supporting_quotes=[quote], direction="bullish")]))
    )
    bundle = parse_report_shadow_v3(
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


def test_factor_outside_caller_vocabulary_rejects_whole_bundle(report):
    quote = "Revenue growth remained strong."
    invoker = FakeSemanticInvoker(
        json.dumps(v3_proposal(claims=[v3_claim(claim=quote, supporting_quotes=[quote], factors=["not_a_real_factor"])]))
    )
    bundle = parse_report_shadow_v3(
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


def test_factor_within_caller_vocabulary_accepted(report):
    quote = "Revenue growth remained strong."
    invoker = FakeSemanticInvoker(
        json.dumps(v3_proposal(claims=[v3_claim(claim=quote, supporting_quotes=[quote], factors=["demand_growth"])]))
    )
    bundle = parse_report_shadow_v3(
        semantic_invoker=invoker,
        source_report=report,
        run_id="run-1",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id="run-1:news_agent:news_report",
        factor_vocabulary=["demand_growth"],
    )
    assert bundle["validation_summary"]["valid"] is True
    assert bundle["claims"][0]["factors"] == ["demand_growth"]


def test_ungrounded_entity_rejects_whole_bundle(report):
    quote = "Revenue growth remained strong."
    invoker = FakeSemanticInvoker(
        json.dumps(v3_proposal(claims=[v3_claim(claim=quote, supporting_quotes=[quote], entities=["Nonexistent Corp"])]))
    )
    bundle = parse_report_shadow_v3(
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


def test_grounded_entity_accepted():
    report = "Nvidia reported strong GPU demand in June."
    quote = "Nvidia reported strong GPU demand in June."
    invoker = FakeSemanticInvoker(
        json.dumps(v3_proposal(claims=[v3_claim(claim=quote, supporting_quotes=[quote], entities=["Nvidia"])]))
    )
    bundle = parse_report_shadow_v3(
        semantic_invoker=invoker,
        source_report=report,
        run_id="run-1",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id="run-1:news_agent:news_report",
        factor_vocabulary=[],
    )
    assert bundle["validation_summary"]["valid"] is True
    assert bundle["claims"][0]["entities"] == ["Nvidia"]


def test_claim_outside_any_candidate_hint_still_accepted():
    """CANDIDATE_HINTS are optional, non-authoritative location hints --
    they never cover the whole report, and the model may propose claims
    they do not cover at all (ADR-008)."""

    report = "A brand-new fact that no candidate segment ever located. Filler filler filler."
    quote = "A brand-new fact that no candidate segment ever located."
    invoker = FakeSemanticInvoker(
        json.dumps(v3_proposal(claims=[v3_claim(claim=quote, supporting_quotes=[quote])]))
    )
    bundle = parse_report_shadow_v3(
        semantic_invoker=invoker,
        source_report=report,
        run_id="run-1",
        ticker="NVDA",
        agent="fundamental_agent",
        agent_output_id="run-1:fundamental_agent:fundamentals_report",
        factor_vocabulary=[],
        candidate_segments=[],
    )
    assert bundle["validation_summary"]["valid"] is True


def test_candidate_lineage_resolves_to_real_candidate_segment_id(report):
    candidates, _filtered = build_candidate_segments(report, agent_output_id="run-1:news_agent:news_report")
    assert candidates, "fixture report must produce at least one candidate"
    target = candidates[0]
    quote = "GPU demand increased in June."
    invoker = FakeSemanticInvoker(
        json.dumps(
            v3_proposal(
                claims=[
                    v3_claim(
                        claim=quote,
                        supporting_quotes=[quote],
                        candidate_ids=[target["candidate_index"]],
                    )
                ]
            )
        )
    )
    bundle = parse_report_shadow_v3(
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


def test_hallucinated_candidate_id_is_silently_dropped_not_trusted(report):
    quote = "GPU demand increased in June."
    invoker = FakeSemanticInvoker(
        json.dumps(v3_proposal(claims=[v3_claim(claim=quote, supporting_quotes=[quote], candidate_ids=[9999])]))
    )
    bundle = parse_report_shadow_v3(
        semantic_invoker=invoker,
        source_report=report,
        run_id="run-1",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id="run-1:news_agent:news_report",
        factor_vocabulary=[],
    )
    assert bundle["validation_summary"]["valid"] is True
    assert bundle["claims"][0]["candidate_segment_ids"] == []


def test_identity_and_hashes_are_never_trusted_from_the_provider(report):
    """Even if a Provider proposal tried to smuggle identity/hash/authority
    fields, normalize_v3_proposal_to_canonical_bundle only ever reads
    'claim'/'supporting_quotes'/'entities'/'factors'/'direction'/
    'confidence'/'candidate_ids' from a claim object -- every other bundle
    field is caller-computed."""

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
                "source_report_sha256": "0" * 64,
                "production_authority": True,
                "shadow_only": False,
            }
        ],
        "abstentions": [],
    }
    invoker = FakeSemanticInvoker(json.dumps(malicious))
    bundle = parse_report_shadow_v3(
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
    assert bundle["source_report_sha256"] != "0" * 64
    assert bundle["production_authority"] is False
    assert bundle["shadow_only"] is True


def test_production_authority_and_shadow_only_are_always_caller_owned(report):
    """Regardless of Provider output content, shadow_only/production_authority
    are always exactly True/False -- never something Provider content can
    flip, whether the bundle is accepted, rejected, or a parser failure."""

    quote = "Revenue growth remained strong."
    accepted_invoker = FakeSemanticInvoker(
        json.dumps(v3_proposal(claims=[v3_claim(claim=quote, supporting_quotes=[quote])]))
    )
    rejected_invoker = FakeSemanticInvoker(
        json.dumps(v3_proposal(claims=[v3_claim(claim=quote, supporting_quotes=["not in report at all"])]))
    )
    error_invoker = FakeSemanticInvoker(error=RuntimeError("boom"))
    for invoker in (accepted_invoker, rejected_invoker, error_invoker):
        bundle = parse_report_shadow_v3(
            semantic_invoker=invoker,
            source_report=report,
            run_id="run-1",
            ticker="NVDA",
            agent="news_agent",
            agent_output_id="run-1:news_agent:news_report",
            factor_vocabulary=[],
        )
        assert bundle["shadow_only"] is True
        assert bundle["production_authority"] is False


def test_stable_claim_id_is_deterministic_across_repeated_calls(report):
    quote = "Revenue growth remained strong."
    proposal_json = json.dumps(v3_proposal(claims=[v3_claim(claim=quote, supporting_quotes=[quote])]))
    ids = []
    for _ in range(2):
        invoker = FakeSemanticInvoker(proposal_json)
        bundle = parse_report_shadow_v3(
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


def test_full_parser_class_round_trip_matches_module_function(report):
    quote = "Revenue growth remained strong."
    proposal_json = json.dumps(v3_proposal(claims=[v3_claim(claim=quote, supporting_quotes=[quote])]))
    parser = StructuredOutputShadowParserV3(FakeSemanticInvoker(proposal_json), factor_vocabulary=[])
    bundle = parser.parse_report_shadow_v3(
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


def test_last_resolution_log_resets_on_every_call(report):
    quote = "Revenue growth remained strong."
    parser = StructuredOutputShadowParserV3(
        FakeSemanticInvoker(json.dumps(v3_proposal(claims=[v3_claim(claim=quote, supporting_quotes=[quote])]))),
        factor_vocabulary=[],
    )
    parser.parse_report_shadow_v3(
        source_report=report,
        run_id="run-1",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id="run-1:news_agent:news_report",
    )
    assert len(parser.last_resolution_log) == 1

    parser.semantic_invoker = FakeSemanticInvoker(json.dumps(v3_proposal(claims=[], abstentions=[])))
    parser.parse_report_shadow_v3(
        source_report=report,
        run_id="run-1",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id="run-1:news_agent:news_report",
    )
    assert parser.last_resolution_log == []


def test_v2_and_v3_prompt_identities_are_distinct():
    assert STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2 != STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3
    assert STRUCTURED_OUTPUT_SHADOW_PROMPT_V2_SHA256 != STRUCTURED_OUTPUT_SHADOW_PROMPT_V3_SHA256


def test_v2_and_v3_cache_identity_never_collides_for_the_same_report(report):
    """Week2LLMGateway.invoke_prebuilt_json_prompt keys its semantic-runtime
    cache/call identity on (task, prompt_version, prompt_sha256,
    input_schema_version, output_schema_version, payload_for_identity).
    Since v2 and v3 always differ on prompt_version/prompt_sha256/
    input_schema_version for the identical underlying report/run/agent, a
    v2 result can never be mistaken for -- or silently reused as -- a v3
    result, even if a real cache were ever enabled (production runs use
    NullLLMResponseCache)."""

    candidates, _filtered = build_candidate_segments(report, agent_output_id="run-1:news_agent:news_report")
    common = {
        "source_report": report,
        "run_id": "run-1",
        "ticker": "NVDA",
        "agent": "news_agent",
        "agent_output_id": "run-1:news_agent:news_report",
        "candidate_segments": candidates,
        "factor_vocabulary": [],
    }
    v2_request = build_shadow_request_v2(**common)
    v3_request = build_shadow_request_v3(**common)
    assert v2_request["input_schema_version"] != v3_request["input_schema_version"]
    assert STRUCTURED_OUTPUT_SHADOW_PROMPT_V2_SHA256 != STRUCTURED_OUTPUT_SHADOW_PROMPT_V3_SHA256


def test_normalizer_returns_bundle_and_resolution_log_tuple(report):
    quote = "Revenue growth remained strong."
    bundle, resolution_log = normalize_v3_proposal_to_canonical_bundle(
        v3_proposal(claims=[v3_claim(claim=quote, supporting_quotes=[quote])]),
        source_report=report,
        run_id="run-1",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id="run-1:news_agent:news_report",
        candidate_index_to_id={},
    )
    assert bundle["claims"][0]["source_spans"][0]["exact_quote"] == quote
    assert resolution_log == [
        {"claim_index": 0, "quote_index": 0, "status": "UNIQUE_EXACT_MATCH", "match_count": 1}
    ]
