"""Phase 1 Master prompt-size fix: regression tests for the real, observed
failure mode from the actual v2 Anthropic Smoke attempt --
claude-sonnet-4-6 wraps its JSON response in a ```json markdown code fence
despite the explicit "Do not return Markdown" instruction (confirmed via two
disclosed, isolated diagnostic calls; see
docs/audit_artifacts/phase1_master/prompt_audit/
v2_json_format_diagnostic_findings.json). ``_MarkdownFenceStrippingModel``
strips exactly one whole-response fence before Week2LLMGateway's own
strict json.loads ever runs -- it never touches week2_llm.py and never
weakens the parser's fail-closed behavior for genuinely malformed content.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from comqutor_alpha.structure_engine.structured_output_shadow_provider import (
    _MarkdownFenceStrippingModel,
    _strip_markdown_json_fence,
)


class _FakeInnerModel:
    def __init__(self, response):
        self._response = response
        self.prompts: list[str] = []

    def invoke(self, prompt, *args, **kwargs):
        self.prompts.append(prompt)
        return self._response


def test_strip_helper_unwraps_json_tagged_fence():
    payload = {"claims": [], "abstentions": []}
    fenced = f"```json\n{json.dumps(payload)}\n```"
    assert json.loads(_strip_markdown_json_fence(fenced)) == payload


def test_strip_helper_unwraps_untagged_fence():
    payload = {"claims": [], "abstentions": []}
    fenced = f"```\n{json.dumps(payload)}\n```"
    assert json.loads(_strip_markdown_json_fence(fenced)) == payload


def test_strip_helper_leaves_unfenced_content_unchanged():
    text = '{"claims": [], "abstentions": []}'
    assert _strip_markdown_json_fence(text) == text


def test_strip_helper_tolerates_surrounding_whitespace():
    payload = {"claims": [], "abstentions": []}
    fenced = f"\n\n```json\n{json.dumps(payload)}\n```\n\n"
    assert json.loads(_strip_markdown_json_fence(fenced)) == payload


def test_strip_helper_does_not_touch_prose_before_the_fence():
    """Conservative: only a WHOLE-response fence is stripped. Prose before
    or after the fence is a different, genuinely-malformed shape that must
    still fail json.loads downstream, not be silently rescued."""

    text = 'Here is the JSON:\n```json\n{"claims": []}\n```'
    assert _strip_markdown_json_fence(text) == text


def test_strip_helper_leaves_malformed_content_inside_fence_still_broken():
    fenced = "```json\n{not valid json,,,}\n```"
    result = _strip_markdown_json_fence(fenced)
    assert result == "{not valid json,,,}"
    try:
        json.loads(result)
        raised = False
    except json.JSONDecodeError:
        raised = True
    assert raised, "malformed content inside the fence must still fail json.loads"


def test_wrapper_invoke_returns_stripped_content_on_the_same_response_object():
    payload = {"claims": [], "abstentions": []}
    response = SimpleNamespace(content=f"```json\n{json.dumps(payload)}\n```", usage_metadata={"input_tokens": 1})
    inner = _FakeInnerModel(response)
    wrapped = _MarkdownFenceStrippingModel(inner)
    result = wrapped.invoke("prompt text")
    assert result is response  # same object, mutated -- usage_metadata etc. preserved
    assert json.loads(result.content) == payload
    assert result.usage_metadata == {"input_tokens": 1}
    assert inner.prompts == ["prompt text"]


def test_wrapper_passes_through_unfenced_response_unchanged():
    response = SimpleNamespace(content='{"claims": [], "abstentions": []}')
    wrapped = _MarkdownFenceStrippingModel(_FakeInnerModel(response))
    result = wrapped.invoke("prompt text")
    assert result.content == '{"claims": [], "abstentions": []}'


def test_wrapper_passes_through_non_string_content_without_crashing():
    response = SimpleNamespace(content=None)
    wrapped = _MarkdownFenceStrippingModel(_FakeInnerModel(response))
    result = wrapped.invoke("prompt text")
    assert result.content is None


def test_wrapper_delegates_unknown_attributes_to_the_inner_model():
    inner = SimpleNamespace(invoke=lambda *_a, **_k: SimpleNamespace(content="{}"), some_attr="marker")
    wrapped = _MarkdownFenceStrippingModel(inner)
    assert wrapped.some_attr == "marker"
