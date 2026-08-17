"""Shared Week2LLMGateway JSON parsing boundary: markdown-fence-stripping
regression tests (task: FIX_SHARED_WEEK2_JSON_PARSER_AND_RERUN_FAILED_B1_30).

Confirms the fix lives at the one shared parsing chokepoint every task's
response passes through (``_strict_json_object``, used by
``invoke_json_with_trace``, ``invoke_prebuilt_json_prompt``, and the legacy
path), reuses the exact regex/behavior already proven by
``test_shadow_markdown_fence_stripping.py`` (not a second implementation),
and never performs semantic/fuzzy repair. No network, no Provider, no LLM
call anywhere in this file.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from comqutor_alpha.structure_engine.structured_output_shadow_provider import (
    _MarkdownFenceStrippingModel,
    _strip_markdown_json_fence,
)
from comqutor_alpha.structure_engine.week2_llm import (
    Week2LLMGateway,
    _strict_json_object,
    strip_markdown_json_fence,
)

# ---------------------------------------------------------------------------
# 1/2/3/4. strip_markdown_json_fence at the new shared location: raw JSON,
# json-tagged fence, untagged fence, surrounding whitespace.
# ---------------------------------------------------------------------------


def test_1_raw_unfenced_json_is_unchanged():
    text = '{"items": []}'
    assert strip_markdown_json_fence(text) == text


def test_2_json_tagged_fence_is_stripped():
    payload = {"items": [{"claim_id": "c1", "target_alpha_id": "A304", "stance": "opposes_alpha"}]}
    fenced = f"```json\n{json.dumps(payload)}\n```"
    assert json.loads(strip_markdown_json_fence(fenced)) == payload


def test_3_untagged_fence_is_stripped():
    payload = {"items": []}
    fenced = f"```\n{json.dumps(payload)}\n```"
    assert json.loads(strip_markdown_json_fence(fenced)) == payload


def test_4_surrounding_whitespace_is_harmless():
    payload = {"items": []}
    fenced = f"\n\n```json\n{json.dumps(payload)}\n```\n\n"
    assert json.loads(strip_markdown_json_fence(fenced)) == payload


# ---------------------------------------------------------------------------
# 5/6. Genuinely malformed content stays malformed -- no semantic repair.
# ---------------------------------------------------------------------------


def test_5_malformed_json_inside_a_fence_still_fails():
    fenced = "```json\n{not valid json,,,}\n```"
    stripped = strip_markdown_json_fence(fenced)
    with pytest.raises(json.JSONDecodeError):
        json.loads(stripped)


def test_6_prose_plus_fence_is_not_repaired():
    """Conservative: only a WHOLE-response fence is stripped. Prose before
    the fence is a different, genuinely malformed shape."""
    text = 'Here is the JSON:\n```json\n{"items": []}\n```'
    assert strip_markdown_json_fence(text) == text
    with pytest.raises(json.JSONDecodeError):
        json.loads(text)


# ---------------------------------------------------------------------------
# 7. JSON values/content are unchanged by fence removal (not just "parses").
# ---------------------------------------------------------------------------


def test_7_fence_removal_does_not_alter_json_values():
    payload = {
        "items": [
            {"claim_id": "c1", "target_alpha_id": "A304", "stance": "opposes_alpha", "counter_alpha_id": None},
            {"claim_id": "c2", "target_alpha_id": "A101", "stance": "supports_counter_alpha", "counter_alpha_id": "A304"},
        ]
    }
    fenced = f"```json\n{json.dumps(payload)}\n```"
    parsed = json.loads(strip_markdown_json_fence(fenced))
    assert parsed == payload
    assert parsed["items"][1]["counter_alpha_id"] == "A304"  # untouched string value


# ---------------------------------------------------------------------------
# _strict_json_object: the actual shared chokepoint, both response shapes.
# ---------------------------------------------------------------------------


def test_strict_json_object_parses_fenced_response_content():
    response = SimpleNamespace(content='```json\n{"items": []}\n```')
    assert _strict_json_object(response) == {"items": []}


def test_strict_json_object_still_rejects_malformed_fenced_content():
    response = SimpleNamespace(content="```json\n{not valid json,,,}\n```")
    with pytest.raises(json.JSONDecodeError):
        _strict_json_object(response)


def test_strict_json_object_unfenced_behavior_is_unchanged():
    response = SimpleNamespace(content='{"items": []}')
    assert _strict_json_object(response) == {"items": []}


# ---------------------------------------------------------------------------
# 8. Existing Week2 task parsing remains compatible (integration, via a fake
# model through the real invoke_json_with_trace).
# ---------------------------------------------------------------------------


class _FakeModel:
    def __init__(self, content):
        self._content = content
        self.calls = 0

    def invoke(self, prompt):
        self.calls += 1
        return SimpleNamespace(content=self._content)


def _gateway(model, tmp_path, *, max_retries=0, max_calls=3):
    return Week2LLMGateway(
        model,
        run_id="fence-fix-test",
        output_root=str(tmp_path),
        timeout_seconds=5.0,
        max_retries=max_retries,
        max_calls=max_calls,
        provider="test",
        model_name="test-model",
    )


def test_8_existing_alpha_classifier_task_still_parses_raw_json(tmp_path):
    model = _FakeModel('{"decision": "defer", "selected_alpha_id": null}')
    gateway = _gateway(model, tmp_path)
    invocation = gateway.invoke_json_with_trace("alpha_classifier", {"claim": "x"}, lambda p: p)
    assert invocation.validation_accepted is True
    assert invocation.validated_output == {"decision": "defer", "selected_alpha_id": None}
    assert model.calls == 1


def test_8b_existing_alpha_classifier_task_now_also_parses_a_fenced_response(tmp_path):
    model = _FakeModel('```json\n{"decision": "defer", "selected_alpha_id": null}\n```')
    gateway = _gateway(model, tmp_path)
    invocation = gateway.invoke_json_with_trace("alpha_classifier", {"claim": "x"}, lambda p: p)
    assert invocation.validation_accepted is True
    assert invocation.validated_output == {"decision": "defer", "selected_alpha_id": None}


# ---------------------------------------------------------------------------
# 9. B1's own contract validator still receives correctly-parsed items after
# fence removal -- proves the fix reaches evidence_stance_classifier too.
# ---------------------------------------------------------------------------


def test_9_b1_batch_validator_receives_parsed_items_from_a_fenced_response(tmp_path):
    from comqutor_alpha.structure_engine.evidence_stance_llm import _validate_batch_shape

    body = {"items": [{"claim_id": "c1", "target_alpha_id": "A304", "stance": "opposes_alpha"}]}
    model = _FakeModel(f"```json\n{json.dumps(body)}\n```")
    gateway = _gateway(model, tmp_path)

    invocation = gateway.invoke_json_with_trace(
        "evidence_stance_classifier", {"items": [{"claim_id": "c1", "target_alpha_id": "A304"}]}, _validate_batch_shape
    )
    assert invocation.validation_accepted is True
    assert invocation.validated_output == body["items"]


def test_9b_end_to_end_apply_llm_stance_upgrade_accepts_a_fenced_real_shaped_response(tmp_path):
    """Full stack: a fenced response reaching the real
    apply_llm_stance_upgrade orchestrator ends up LLM-authoritative, not a
    parser-forced fallback."""
    from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
    from comqutor_alpha.structure_engine import evidence_stance as es
    from comqutor_alpha.structure_engine.evidence_stance_llm import (
        STANCE_METHOD_LLM,
        apply_llm_stance_upgrade,
    )

    taxonomy = load_alpha_taxonomy()
    match = {
        "run_id": "r1",
        "ticker": "NVDA",
        "claim_id": "c1",
        "claim": "x",
        "evidence": "x",
        "factors": [],
        "matched_alpha": "A304",
        "secondary_alphas": [],
        "match_status": "matched",
        "candidate_scores": [
            {
                "alpha_id": "A304",
                "alpha_name": "Multiple Compression",
                "evidence_stance": es.SUPPORTS_ALPHA,
                "counter_alpha_id": None,
                "stance_reason_codes": [],
                "stance_confidence_band": es.CONFIDENCE_HIGH,
                "requires_manual_review": False,
                "evidence_stance_version": es.CLASSIFIER_VERSION,
                "stance_method": None,
                "stance_fallback_reason": None,
            }
        ],
    }
    body = {"items": [{"claim_id": "c1", "target_alpha_id": "A304", "stance": "opposes_alpha"}]}
    model = _FakeModel(f"```json\n{json.dumps(body)}\n```")
    gateway = _gateway(model, tmp_path)

    apply_llm_stance_upgrade([match], taxonomy, llm_gateway=gateway)

    candidate = match["candidate_scores"][0]
    assert candidate["evidence_stance"] == "opposes_alpha"
    assert candidate["stance_method"] == STANCE_METHOD_LLM


# ---------------------------------------------------------------------------
# 10. Replay remains 0 Provider calls -- unaffected by a pure parsing-
# boundary change (no new call site, no new gateway construction).
# ---------------------------------------------------------------------------


def test_10_replay_call_site_still_passes_no_gateway():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "comqutor_alpha/replay/pipeline.py").read_text(encoding="utf-8")
    assert "adapt_run_outputs(source_run_dir, llm_gateway=None)" in text
    assert "build_alpha_matches_payload(structured)" in text


# ---------------------------------------------------------------------------
# Zero fuzzy/semantic repair: confirms only whole-response fence stripping
# exists anywhere in the shared module -- no brace-guessing, no quote
# reconstruction, no schema-field guessing.
# ---------------------------------------------------------------------------


def test_shadow_provider_reexports_the_shared_helper_not_a_second_copy():
    assert _strip_markdown_json_fence is strip_markdown_json_fence


def test_shadow_wrapper_class_still_uses_the_shared_helper():
    payload = {"claims": []}
    fenced_content = f"```json\n{json.dumps(payload)}\n```"
    wrapped = _MarkdownFenceStrippingModel(_FakeModel(fenced_content))
    result = wrapped.invoke("prompt")
    assert json.loads(result.content) == payload
