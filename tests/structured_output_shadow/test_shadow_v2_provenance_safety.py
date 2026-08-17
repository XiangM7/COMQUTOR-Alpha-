"""Phase 1 Master prompt-size fix: proves exact_quote is correctly
reconstructed as report[start:end] from Provider-supplied offsets alone (v2
never receives exact_quote text from the Provider), and that invalid spans
are rejected -- never silently repaired or fuzzy-matched -- by the same,
unchanged validate_shadow_bundle used by v1.
"""

from __future__ import annotations

import json

from conftest import FakeSemanticInvoker, v2_claim, v2_proposal, v2_span_for

from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v2 import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V2_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2,
)
from comqutor_alpha.structure_engine.structured_output_shadow_schema import (
    SHADOW_SOURCE_SPAN_INVALID,
    assign_deterministic_claim_ids,
    validate_shadow_bundle,
)
from comqutor_alpha.structure_engine.structured_output_shadow_v2 import (
    StructuredOutputShadowParserV2,
    normalize_v2_proposal_to_canonical_bundle,
)

RUN_ID = "run-v2-prov"
TICKER = "NVDA"
AGENT = "news_agent"
AGENT_OUTPUT_ID = "run-v2-prov:news_agent:news_report"
FACTOR_VOCAB: list[str] = []


def _run(report: str, proposal: dict):
    bundle = normalize_v2_proposal_to_canonical_bundle(
        proposal,
        source_report=report,
        run_id=RUN_ID,
        ticker=TICKER,
        agent=AGENT,
        agent_output_id=AGENT_OUTPUT_ID,
        candidate_index_to_id={},
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
        allowed_candidate_segment_ids=[],
    )
    return bundle, validation


def test_exact_quote_reconstructed_from_offsets():
    report = "GPU demand rose sharply in June."
    proposal = v2_proposal(claims=[v2_claim(claim=report, spans=[{"start": 0, "end": len(report)}])])
    bundle, validation = _run(report, proposal)
    assert validation.valid
    assert bundle["claims"][0]["source_spans"][0]["exact_quote"] == report


def test_unicode_and_emoji_offsets_reconstructed():
    report = "NVIDIA \U0001f7e2 reported über-strong GPU demand in Q2."
    quote = "über-strong GPU demand"
    proposal = v2_proposal(claims=[v2_claim(claim=quote, spans=[v2_span_for(report, quote)])])
    bundle, validation = _run(report, proposal)
    assert validation.valid, validation.reason_codes
    assert bundle["claims"][0]["source_spans"][0]["exact_quote"] == quote


def test_newline_and_punctuation_offsets_reconstructed():
    report = "Line one: revenue up.\nLine two: margins, up too!\nLine three: done."
    quote = "Line two: margins, up too!"
    proposal = v2_proposal(claims=[v2_claim(claim=quote, spans=[v2_span_for(report, quote)])])
    bundle, validation = _run(report, proposal)
    assert validation.valid, validation.reason_codes
    assert bundle["claims"][0]["source_spans"][0]["exact_quote"] == quote


def test_overlapping_spans_across_claims_recorded_as_warning_not_error():
    report = "GPU demand rose sharply in June and drove strong bookings."
    span_a = {"start": 0, "end": 33}  # "GPU demand rose sharply in June"
    span_b = {"start": 20, "end": len(report)}  # overlaps span_a
    proposal = v2_proposal(
        claims=[
            v2_claim(claim="GPU demand rose.", spans=[span_a]),
            v2_claim(claim="Demand drove bookings.", spans=[span_b]),
        ]
    )
    bundle, validation = _run(report, proposal)
    assert validation.valid
    assert any(w.reason_code == "SHADOW_SOURCE_SPAN_OVERLAP" for w in validation.warnings)


def test_non_int_offset_type_rejected_not_crashed():
    report = "GPU demand rose sharply in June."
    proposal = v2_proposal(
        claims=[v2_claim(claim="GPU demand rose.", spans=[{"start": "0", "end": 10}])]
    )
    _bundle, validation = _run(report, proposal)  # must not raise
    assert not validation.valid
    assert SHADOW_SOURCE_SPAN_INVALID in validation.reason_codes
    # The final, caller-facing result (via the full parser, not the raw
    # normalizer helper above) carries no fabricated claim on rejection.
    fake = FakeSemanticInvoker(json.dumps(proposal))
    result = StructuredOutputShadowParserV2(fake, factor_vocabulary=FACTOR_VOCAB).parse_report_shadow_v2(
        source_report=report, run_id=RUN_ID, ticker=TICKER, agent=AGENT, agent_output_id=AGENT_OUTPUT_ID
    )
    assert result["validation_summary"]["status"] == "validation_rejected"
    assert result["claims"] == []


def test_negative_offset_rejected():
    report = "GPU demand rose sharply in June."
    proposal = v2_proposal(claims=[v2_claim(claim="x", spans=[{"start": -5, "end": 10}])])
    _bundle, validation = _run(report, proposal)
    assert not validation.valid
    assert SHADOW_SOURCE_SPAN_INVALID in validation.reason_codes


def test_out_of_range_end_offset_rejected():
    report = "GPU demand rose sharply in June."
    proposal = v2_proposal(claims=[v2_claim(claim="x", spans=[{"start": 0, "end": len(report) + 500}])])
    _bundle, validation = _run(report, proposal)
    assert not validation.valid
    assert SHADOW_SOURCE_SPAN_INVALID in validation.reason_codes


def test_inverted_offset_rejected():
    report = "GPU demand rose sharply in June."
    proposal = v2_proposal(claims=[v2_claim(claim="x", spans=[{"start": 20, "end": 5}])])
    _bundle, validation = _run(report, proposal)
    assert not validation.valid
    assert SHADOW_SOURCE_SPAN_INVALID in validation.reason_codes


def test_missing_span_keys_rejected_not_crashed():
    report = "GPU demand rose sharply in June."
    proposal = v2_proposal(claims=[v2_claim(claim="x", spans=[{"start": 0}])])
    _bundle, validation = _run(report, proposal)  # must not raise KeyError
    assert not validation.valid
    fake = FakeSemanticInvoker(json.dumps(proposal))
    result = StructuredOutputShadowParserV2(fake, factor_vocabulary=FACTOR_VOCAB).parse_report_shadow_v2(
        source_report=report, run_id=RUN_ID, ticker=TICKER, agent=AGENT, agent_output_id=AGENT_OUTPUT_ID
    )
    assert result["claims"] == []


def test_span_not_an_object_rejected_not_crashed():
    report = "GPU demand rose sharply in June."
    proposal = {"claims": [{"claim": "x", "source_spans": ["not-an-object"], "entities": [], "factors": [], "direction": "unknown", "confidence": 0.5}]}
    bundle, validation = _run(report, proposal)  # must not raise
    assert not validation.valid


def test_empty_spans_list_rejected_not_silently_accepted():
    report = "GPU demand rose sharply in June."
    proposal = v2_proposal(claims=[v2_claim(claim="x", spans=[])])
    _bundle, validation = _run(report, proposal)
    assert not validation.valid
    assert SHADOW_SOURCE_SPAN_INVALID in validation.reason_codes
