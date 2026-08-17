from __future__ import annotations

from copy import deepcopy

from conftest import bundle_for, claim_for, span_for

from comqutor_alpha.structure_engine.structured_output_shadow_prompt import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
)
from comqutor_alpha.structure_engine.structured_output_shadow_schema import (
    SHADOW_DUPLICATE_CLAIM,
    SHADOW_IDENTITY_MISMATCH,
    generate_shadow_claim_id,
    validate_shadow_bundle,
)


def test_identity_is_deterministic_and_sensitive_to_claim_and_span(report):
    span = [span_for(report, "GPU demand increased in June.")]
    kwargs = {
        "run_id": "run-shadow-1",
        "agent_output_id": "run-shadow-1:news_agent:news_report",
        "claim": "GPU demand increased.",
        "source_spans": span,
    }
    first = generate_shadow_claim_id(**kwargs)
    assert first == generate_shadow_claim_id(**kwargs)
    assert first != generate_shadow_claim_id(**{**kwargs, "claim": "GPU demand was flat."})
    changed_span = [{**span[0], "end": span[0]["end"] - 1, "exact_quote": span[0]["exact_quote"][:-1]}]
    assert first != generate_shadow_claim_id(**{**kwargs, "source_spans": changed_span})


def _validate(bundle, report, *, ticker="NVDA"):
    return validate_shadow_bundle(
        bundle,
        source_report=report,
        run_id="run-shadow-1",
        ticker=ticker,
        agent="news_agent",
        agent_output_id="run-shadow-1:news_agent:news_report",
        prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
        prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
        factor_vocabulary=("GPU Demand",),
    )


def test_duplicate_computed_identity_is_rejected(report):
    claim = claim_for(report, "GPU demand increased in June.")
    bundle = bundle_for(report, claims=[claim, deepcopy(claim)])
    assert SHADOW_DUPLICATE_CLAIM in _validate(bundle, report).reason_codes


def test_wrong_caller_identity_is_rejected(report):
    bundle = bundle_for(report, claims=[claim_for(report, "GPU demand increased in June.")])
    bundle["ticker"] = "AMD"
    result = _validate(bundle, report)
    assert SHADOW_IDENTITY_MISMATCH in result.reason_codes

