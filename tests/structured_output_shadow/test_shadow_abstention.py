from __future__ import annotations

from conftest import FakeSemanticInvoker, bundle_for

from comqutor_alpha.structure_engine.structured_output_shadow import StructuredOutputShadowParser
from comqutor_alpha.structure_engine.structured_output_shadow_schema import SHADOW_OUTPUT_TOO_LARGE

BASE = {
    "run_id": "run-shadow-1",
    "ticker": "NVDA",
    "agent": "news_agent",
    "agent_output_id": "run-shadow-1:news_agent:news_report",
}


def test_empty_valid_output():
    report = "Formatting complete. End of report."
    result = StructuredOutputShadowParser(FakeSemanticInvoker(bundle_for(report))).parse_report_shadow(
        source_report=report, **BASE
    )
    assert result["validation_summary"]["status"] == "empty_valid_output"
    assert result["claims"] == []
    assert result["production_authority"] is False


def test_explicit_abstention():
    report = "Could demand rise next year?"
    abstentions = [{"candidate_segment_ids": [], "reason_code": "QUESTION_ONLY", "notes": ""}]
    result = StructuredOutputShadowParser(
        FakeSemanticInvoker(bundle_for(report, abstentions=abstentions))
    ).parse_report_shadow(source_report=report, **BASE)
    assert result["validation_summary"]["status"] == "abstained"
    assert result["abstentions"][0]["reason_code"] == "QUESTION_ONLY"


def test_oversized_input_never_invokes_fake():
    fake = FakeSemanticInvoker({})
    result = StructuredOutputShadowParser(fake, max_input_bytes=8).parse_report_shadow(
        source_report="a report longer than eight bytes", **BASE
    )
    assert fake.calls == []
    assert result["validation_summary"]["status"] == "input_too_large"
    assert result["validation_summary"]["reason_codes"] == [SHADOW_OUTPUT_TOO_LARGE]


def test_disclaimer_can_be_omitted_without_fake_claim():
    report = "## Disclaimer\nNot investment advice."
    result = StructuredOutputShadowParser(FakeSemanticInvoker(bundle_for(report))).parse_report_shadow(
        source_report=report, **BASE
    )
    assert result["claims"] == []

