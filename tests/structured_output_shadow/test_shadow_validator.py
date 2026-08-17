from __future__ import annotations

import pytest
from conftest import bundle_for, claim_for, span_for

from comqutor_alpha.structure_engine.structured_output_shadow_prompt import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
)
from comqutor_alpha.structure_engine.structured_output_shadow_schema import (
    SHADOW_ENTITY_NOT_GROUNDED,
    SHADOW_EVIDENCE_NOT_PROVENANCED,
    SHADOW_FACTOR_VOCABULARY_INVALID,
    SHADOW_SOURCE_HASH_MISMATCH,
    SHADOW_SOURCE_REF_INVALID,
    SHADOW_SOURCE_SPAN_INVALID,
    assign_deterministic_claim_ids,
    validate_shadow_bundle,
)


def _validate(bundle, report, *, refs=()):
    return validate_shadow_bundle(
        assign_deterministic_claim_ids(bundle),
        source_report=report,
        run_id="run-shadow-1",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id="run-shadow-1:news_agent:news_report",
        prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
        prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
        factor_vocabulary=("GPU Demand", "Revenue Growth"),
        allowed_source_refs=refs,
    )


def test_unicode_and_multiline_exact_spans():
    report = "需求上升。\n第二行支持该结论。"
    claim = claim_for(report, report, spans=[span_for(report, report)])
    assert _validate(bundle_for(report, claims=[claim]), report).valid


def test_multiple_spans_support_bounded_combination():
    report = "GPU demand rose. Separate note. Revenue grew."
    spans = [span_for(report, "GPU demand rose."), span_for(report, "Revenue grew.")]
    claim = claim_for(
        report,
        "GPU demand rose.",
        spans=spans,
        evidence="GPU demand rose. Revenue grew.",
    )
    assert _validate(bundle_for(report, claims=[claim]), report).valid


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda claim: claim["source_spans"][0].update({"end": 999}), SHADOW_SOURCE_SPAN_INVALID),
        (lambda claim: claim["source_spans"][0].update({"exact_quote": "wrong"}), SHADOW_SOURCE_SPAN_INVALID),
        (lambda claim: claim.update({"evidence": "fact not in report"}), SHADOW_EVIDENCE_NOT_PROVENANCED),
        (lambda claim: claim.update({"factors": ["Invented Factor"]}), SHADOW_FACTOR_VOCABULARY_INVALID),
        (lambda claim: claim.update({"entities": ["ABSENT_ENTITY"]}), SHADOW_ENTITY_NOT_GROUNDED),
        (lambda claim: claim.update({"source_refs": ["invented://ref"]}), SHADOW_SOURCE_REF_INVALID),
    ],
)
def test_fail_closed_validation_cases(report, mutate, reason):
    claim = claim_for(report, "GPU demand increased in June.")
    mutate(claim)
    result = _validate(bundle_for(report, claims=[claim]), report)
    assert not result.valid
    assert reason in result.reason_codes


def test_source_hash_mismatch(report):
    bundle = bundle_for(report, claims=[claim_for(report, "GPU demand increased in June.")])
    bundle["source_report_sha256"] = "0" * 64
    assert SHADOW_SOURCE_HASH_MISMATCH in _validate(bundle, report).reason_codes


def test_overlapping_spans_are_diagnostic_not_automatic_semantic_error():
    report = "GPU demand increased sharply."
    first = claim_for(report, report, claim="Demand increased.")
    second = claim_for(report, report, claim="The increase was sharp.")
    result = _validate(bundle_for(report, claims=[first, second]), report)
    assert result.valid
    assert result.warnings[0].reason_code == "SHADOW_SOURCE_SPAN_OVERLAP"

