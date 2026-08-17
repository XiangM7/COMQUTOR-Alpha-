from __future__ import annotations

from copy import deepcopy

import pytest
from conftest import bundle_for, claim_for

from comqutor_alpha.structure_engine.structured_output_shadow_prompt import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
)
from comqutor_alpha.structure_engine.structured_output_shadow_schema import (
    SHADOW_DIRECTION_INVALID,
    SHADOW_SCHEMA_INVALID,
    SHADOW_UNAPPROVED_FIELD,
    STRUCTURED_OUTPUT_SHADOW_SCHEMA_VERSION,
    validate_shadow_bundle,
)


def _validate(bundle, report):
    return validate_shadow_bundle(
        bundle,
        source_report=report,
        run_id="run-shadow-1",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id="run-shadow-1:news_agent:news_report",
        prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
        prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
        factor_vocabulary=("GPU Demand", "Revenue Growth"),
    )


def test_schema_version_is_frozen():
    assert STRUCTURED_OUTPUT_SHADOW_SCHEMA_VERSION == "comqutor.structured_claim_shadow.v1"


def test_valid_bundle(report):
    result = _validate(bundle_for(report, claims=[claim_for(report, "GPU demand increased in June.")]), report)
    assert result.valid
    assert result.status == "accepted"


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda value: value.pop("ticker"), SHADOW_SCHEMA_INVALID),
        (lambda value: value.update({"unexpected": True}), SHADOW_UNAPPROVED_FIELD),
        (lambda value: value["claims"][0].update({"direction": "bullish"}), SHADOW_DIRECTION_INVALID),
        (lambda value: value["claims"][0].update({"confidence": 1.1}), SHADOW_SCHEMA_INVALID),
        (lambda value: value.update({"shadow_only": False}), SHADOW_SCHEMA_INVALID),
        (lambda value: value.update({"production_authority": True}), SHADOW_SCHEMA_INVALID),
    ],
)
def test_invalid_schema_cases(report, mutation, reason):
    bundle = bundle_for(report, claims=[claim_for(report, "GPU demand increased in June.")])
    mutation(bundle)
    result = _validate(bundle, report)
    assert not result.valid
    assert reason in result.reason_codes


def test_claim_extra_field_is_rejected(report):
    bundle = deepcopy(bundle_for(report, claims=[claim_for(report, "GPU demand increased in June.")]))
    bundle["claims"][0]["reasoning"] = "hidden"
    result = _validate(bundle, report)
    assert SHADOW_UNAPPROVED_FIELD in result.reason_codes

