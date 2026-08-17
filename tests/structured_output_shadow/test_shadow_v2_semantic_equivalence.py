"""Phase 1 Master prompt-size fix: proves the v2 minimal Provider-facing
proposal shape loses no semantic capability v1 had, end to end through the
SAME UNCHANGED canonical schema/validator
(comqutor.structured_claim_shadow.v1 / validate_shadow_bundle). Every case
here is Fake-Provider-driven and Provider-call-free -- these tests prove the
deterministic pipeline preserves whatever the model decided, not that a real
model makes good decisions (that remains SEMANTIC_QUALITY=UNPROVEN, unchanged,
pending human review).
"""

from __future__ import annotations

import json

from conftest import FakeSemanticInvoker, v2_abstention, v2_claim, v2_proposal, v2_span_for

from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v2 import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V2_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2,
)
from comqutor_alpha.structure_engine.structured_output_shadow_schema import (
    SHADOW_DIRECTION_INVALID,
    SHADOW_ENTITY_NOT_GROUNDED,
    SHADOW_FACTOR_VOCABULARY_INVALID,
    STRUCTURED_OUTPUT_SHADOW_SCHEMA_VERSION,
    assign_deterministic_claim_ids,
    validate_shadow_bundle,
)
from comqutor_alpha.structure_engine.structured_output_shadow_v2 import (
    StructuredOutputShadowParserV2,
    normalize_v2_proposal_to_canonical_bundle,
)

FACTOR_VOCAB = ["GPU Demand", "Revenue Growth", "Datacenter CapEx"]

RICH_REPORT = (
    "GPU demand rose sharply in June. "
    "Datacenter revenue growth accelerated as a result. "
    "The company said it does not expect a decline in renewal demand. "
    "If input costs rise, could margins narrow next year? "
    'According to a spokesperson, "management remains cautiously optimistic." '
    "Historically, Q3 has been the strongest quarter for bookings. "
    "Margins may face pressure, though the timing remains uncertain."
)

RUN_ID = "run-v2-1"
TICKER = "NVDA"
AGENT = "news_agent"
AGENT_OUTPUT_ID = "run-v2-1:news_agent:news_report"


def _run(report: str, proposal: dict, *, candidate_index_to_id: dict[int, str] | None = None):
    candidate_index_to_id = candidate_index_to_id or {}
    bundle = normalize_v2_proposal_to_canonical_bundle(
        proposal,
        source_report=report,
        run_id=RUN_ID,
        ticker=TICKER,
        agent=AGENT,
        agent_output_id=AGENT_OUTPUT_ID,
        candidate_index_to_id=candidate_index_to_id,
    )
    bundle = assign_deterministic_claim_ids(bundle)
    validation = validate_shadow_bundle(
        bundle,
        source_report=report,
        run_id=RUN_ID,
        ticker=TICKER,
        agent=AGENT,
        agent_output_id=AGENT_OUTPUT_ID,
        prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2,
        prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_V2_SHA256,
        factor_vocabulary=FACTOR_VOCAB,
        allowed_source_refs=(),
        allowed_candidate_segment_ids=list(candidate_index_to_id.values()),
    )
    bundle["validation_summary"] = validation.to_summary()
    return bundle, validation


def test_single_claim_round_trip():
    quote = "GPU demand rose sharply in June."
    proposal = v2_proposal(
        claims=[
            v2_claim(
                claim=quote,
                spans=[v2_span_for(RICH_REPORT, quote)],
                factors=["GPU Demand"],
                direction="positive",
                confidence=0.9,
            )
        ]
    )
    bundle, validation = _run(RICH_REPORT, proposal)
    assert validation.valid and validation.status == "accepted"
    assert bundle["schema_version"] == STRUCTURED_OUTPUT_SHADOW_SCHEMA_VERSION
    assert bundle["claims"][0]["claim"] == quote
    assert bundle["claims"][0]["evidence"] == quote
    assert bundle["claims"][0]["source_spans"][0]["exact_quote"] == quote


def test_split_into_two_claims():
    q1 = "GPU demand rose sharply in June."
    q2 = "Datacenter revenue growth accelerated as a result."
    proposal = v2_proposal(
        claims=[
            v2_claim(claim=q1, spans=[v2_span_for(RICH_REPORT, q1)]),
            v2_claim(claim=q2, spans=[v2_span_for(RICH_REPORT, q2)]),
        ]
    )
    bundle, validation = _run(RICH_REPORT, proposal)
    assert validation.valid
    assert len(bundle["claims"]) == 2
    assert {c["claim"] for c in bundle["claims"]} == {q1, q2}


def test_merge_two_spans_into_one_claim_and_evidence_is_bounded_join():
    q1 = "GPU demand rose sharply in June."
    q2 = "Datacenter revenue growth accelerated as a result."
    proposal = v2_proposal(
        claims=[
            v2_claim(
                claim="GPU demand growth drove datacenter revenue acceleration.",
                spans=[v2_span_for(RICH_REPORT, q1), v2_span_for(RICH_REPORT, q2)],
            )
        ]
    )
    bundle, validation = _run(RICH_REPORT, proposal)
    assert validation.valid, validation.reason_codes
    assert bundle["claims"][0]["evidence"] == f"{q1} {q2}"


def test_negation_preserved_not_flipped():
    quote = "The company said it does not expect a decline in renewal demand."
    proposal = v2_proposal(
        claims=[v2_claim(claim=quote, spans=[v2_span_for(RICH_REPORT, quote)], direction="neutral")]
    )
    bundle, validation = _run(RICH_REPORT, proposal)
    assert validation.valid
    assert "does not expect a decline" in bundle["claims"][0]["claim"]


def test_hypothetical_question_abstained_not_asserted():
    quote = "If input costs rise, could margins narrow next year?"
    proposal = v2_proposal(
        abstentions=[v2_abstention(reason_code="HYPOTHETICAL_NOT_ASSERTED", notes=quote)]
    )
    bundle, validation = _run(RICH_REPORT, proposal)
    assert validation.valid and validation.status == "abstained"
    assert bundle["claims"] == []
    assert bundle["abstentions"][0]["reason_code"] == "HYPOTHETICAL_NOT_ASSERTED"


def test_quoted_attribution_preserved():
    quote = 'According to a spokesperson, "management remains cautiously optimistic."'
    proposal = v2_proposal(
        claims=[v2_claim(claim=quote, spans=[v2_span_for(RICH_REPORT, quote)])]
    )
    bundle, validation = _run(RICH_REPORT, proposal)
    assert validation.valid, validation.reason_codes
    assert bundle["claims"][0]["claim"].startswith("According to a spokesperson")


def test_temporal_qualification_preserved():
    quote = "Historically, Q3 has been the strongest quarter for bookings."
    proposal = v2_proposal(
        claims=[v2_claim(claim=quote, spans=[v2_span_for(RICH_REPORT, quote)])]
    )
    bundle, validation = _run(RICH_REPORT, proposal)
    assert validation.valid
    assert bundle["claims"][0]["claim"] == quote


def test_uncertainty_confidence_and_wording_preserved():
    quote = "Margins may face pressure, though the timing remains uncertain."
    proposal = v2_proposal(
        claims=[
            v2_claim(claim=quote, spans=[v2_span_for(RICH_REPORT, quote)], confidence=0.35)
        ]
    )
    bundle, validation = _run(RICH_REPORT, proposal)
    assert validation.valid
    assert bundle["claims"][0]["confidence"] == 0.35
    assert "uncertain" in bundle["claims"][0]["claim"]


def test_multiple_evidence_spans_all_validated():
    q1 = "GPU demand rose sharply in June."
    q2 = "Historically, Q3 has been the strongest quarter for bookings."
    proposal = v2_proposal(
        claims=[
            v2_claim(
                claim="Demand strength aligns with a historically strong quarter.",
                spans=[v2_span_for(RICH_REPORT, q1), v2_span_for(RICH_REPORT, q2)],
            )
        ]
    )
    bundle, validation = _run(RICH_REPORT, proposal)
    assert validation.valid, validation.reason_codes
    assert len(bundle["claims"][0]["source_spans"]) == 2


def test_factor_outside_vocabulary_rejected():
    quote = "GPU demand rose sharply in June."
    proposal = v2_proposal(
        claims=[
            v2_claim(claim=quote, spans=[v2_span_for(RICH_REPORT, quote)], factors=["Not A Real Factor"])
        ]
    )
    _bundle, validation = _run(RICH_REPORT, proposal)
    assert not validation.valid
    assert SHADOW_FACTOR_VOCABULARY_INVALID in validation.reason_codes


def test_invalid_direction_rejected():
    quote = "GPU demand rose sharply in June."
    proposal = v2_proposal(
        claims=[v2_claim(claim=quote, spans=[v2_span_for(RICH_REPORT, quote)], direction="bullish")]
    )
    _bundle, validation = _run(RICH_REPORT, proposal)
    assert not validation.valid
    assert SHADOW_DIRECTION_INVALID in validation.reason_codes


def test_ungrounded_entity_rejected():
    quote = "GPU demand rose sharply in June."
    proposal = v2_proposal(
        claims=[
            v2_claim(
                claim=quote, spans=[v2_span_for(RICH_REPORT, quote)], entities=["Completely Fictional Corp"]
            )
        ]
    )
    _bundle, validation = _run(RICH_REPORT, proposal)
    assert not validation.valid
    assert SHADOW_ENTITY_NOT_GROUNDED in validation.reason_codes


def test_claim_outside_any_candidate_hint_still_accepted():
    """v2 only sends offset hints for the located subset of candidates; the
    model must still be free to find and cite spans nowhere among those
    hints, using only its own reading of agent_report."""

    quote = "Margins may face pressure, though the timing remains uncertain."
    proposal = v2_proposal(claims=[v2_claim(claim=quote, spans=[v2_span_for(RICH_REPORT, quote)])])
    # candidate_index_to_id intentionally has no entry overlapping this span.
    bundle, validation = _run(RICH_REPORT, proposal, candidate_index_to_id={0: "cand-0"})
    assert validation.valid, validation.reason_codes
    assert bundle["claims"][0]["candidate_segment_ids"] == []


def test_candidate_lineage_resolved_from_short_id():
    quote = "GPU demand rose sharply in June."
    proposal = v2_proposal(
        claims=[
            v2_claim(claim=quote, spans=[v2_span_for(RICH_REPORT, quote)], candidate_ids=[0])
        ]
    )
    bundle, validation = _run(
        RICH_REPORT, proposal, candidate_index_to_id={0: "run-v2-1:news_agent:news_report:shadow-candidate:abc"}
    )
    assert validation.valid, validation.reason_codes
    assert bundle["claims"][0]["candidate_segment_ids"] == [
        "run-v2-1:news_agent:news_report:shadow-candidate:abc"
    ]


def test_identity_fields_always_caller_owned_even_when_proposal_has_none():
    """The v2 Provider proposal shape has no identity fields at all -- prove
    the final bundle is still fully, correctly identified from caller
    inputs alone."""

    quote = "GPU demand rose sharply in June."
    proposal = v2_proposal(claims=[v2_claim(claim=quote, spans=[v2_span_for(RICH_REPORT, quote)])])
    assert "run_id" not in proposal and "schema_version" not in proposal
    bundle, validation = _run(RICH_REPORT, proposal)
    assert validation.valid
    assert bundle["run_id"] == RUN_ID
    assert bundle["ticker"] == TICKER
    assert bundle["agent"] == AGENT
    assert bundle["agent_output_id"] == AGENT_OUTPUT_ID
    assert bundle["shadow_only"] is True
    assert bundle["production_authority"] is False


def test_claim_and_abstention_round_trip_via_full_parser():
    """End-to-end through StructuredOutputShadowParserV2 (prompt build ->
    Fake Provider -> JSON parse -> normalize -> validate), not just the
    normalizer in isolation."""

    q1 = "GPU demand rose sharply in June."
    q2 = "If input costs rise, could margins narrow next year?"
    proposal = v2_proposal(
        claims=[v2_claim(claim=q1, spans=[v2_span_for(RICH_REPORT, q1)], factors=["GPU Demand"])],
        abstentions=[v2_abstention(reason_code="HYPOTHETICAL_NOT_ASSERTED", notes=q2)],
    )
    fake = FakeSemanticInvoker(json.dumps(proposal))
    parser = StructuredOutputShadowParserV2(fake, factor_vocabulary=FACTOR_VOCAB)
    result = parser.parse_report_shadow_v2(
        source_report=RICH_REPORT,
        run_id=RUN_ID,
        ticker=TICKER,
        agent=AGENT,
        agent_output_id=AGENT_OUTPUT_ID,
    )
    assert result["validation_summary"]["status"] == "accepted"
    assert len(result["claims"]) == 1
    assert len(result["abstentions"]) == 1
    assert fake.calls[0]["request"]["agent_report"] == RICH_REPORT
    # The wire request never carried claim/evidence text duplicating the report.
    assert "claim_hint" not in json.dumps(fake.calls[0]["request"])
    assert "evidence_hint" not in json.dumps(fake.calls[0]["request"])
