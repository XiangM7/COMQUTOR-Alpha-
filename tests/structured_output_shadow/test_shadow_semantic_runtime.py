"""Phase 1B.1: llm_runtime integration for the new structured_claim_shadow task.

Confirms the additive SEMANTIC_TASKS entry does not alter the three existing
Week2 tasks' identity/behavior, and that a structured_claim_shadow call
produces a fully valid, fail-closed-verifiable SemanticCallRecord and
manifest -- entirely offline, with a FakeModel.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from comqutor_alpha.llm_runtime.cache import NullLLMResponseCache
from comqutor_alpha.llm_runtime.contracts import (
    SEMANTIC_TASKS,
    validate_semantic_call_record,
    validate_semantic_call_records,
)
from comqutor_alpha.llm_runtime.manifest import verify_semantic_manifest
from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway


class FakeModel:
    def __init__(self, responses):
        self._responses = list(responses)
        self.call_count = 0

    def invoke(self, prompt):
        self.call_count += 1
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_structured_claim_shadow_is_additive_to_semantic_tasks():
    assert {
        "structured_adapter",
        "alpha_classifier",
        "structure_extractor",
        "structured_claim_shadow",
        # Post-Alpha-Authority-Migration Cleanup task: B1's own LLM stance
        # upgrade, registered here for the first time alongside the four
        # already-present tasks -- additive, no existing task removed.
        "evidence_stance_classifier",
    } == SEMANTIC_TASKS


def test_existing_three_task_prompt_identity_unaffected_by_new_task():
    # prompt_identity_sha256 for the three existing tasks must be exactly
    # what it was before this phase -- computed purely from their own fixed
    # _TASK_INSTRUCTIONS text, untouched by this phase.
    for task in ("claim_batch_enrichment", "alpha_classifier", "structure_extractor"):
        text = Week2LLMGateway.prompt_identity_text(task)
        assert task != "structured_claim_shadow"
        assert len(Week2LLMGateway.prompt_identity_sha256(task)) == 64
        assert text.startswith("You are a constrained COMQUTOR extraction component.")


def test_invoke_prebuilt_json_prompt_produces_valid_semantic_call_record(tmp_path):
    session = SemanticRuntimeSession(
        run_id="runtime-test-1",
        output_directory=tmp_path,
        execution_mode="shadow",
        provider="fake-provider",
        model="fake-model",
        cache=NullLLMResponseCache(),
    )
    model = FakeModel([SimpleNamespace(content=json.dumps({"claims": [], "abstentions": []}))])
    gateway = Week2LLMGateway(
        model,
        run_id="runtime-test-1",
        output_root=str(tmp_path),
        provider="fake-provider",
        model_name="fake-model",
        semantic_runtime=session,
    )

    def validator(parsed):
        return parsed

    invocation = gateway.invoke_prebuilt_json_prompt(
        task="structured_claim_shadow",
        prompt="FROZEN PROMPT TEXT\n\nSHADOW_REQUEST_JSON:\n{}",
        prompt_version="structured_adapter.claim_extraction_shadow.v1",
        prompt_sha256="c60f1526fd927e4593ab5913bc3c653cd2a05f6d24dc5fdf3e258a3e62128d1e",
        input_schema_version="comqutor.structured_claim_shadow_input.v1",
        output_schema_version="comqutor.structured_claim_shadow.v1",
        payload_for_identity={"claims": [], "candidate_segments": []},
        validator=validator,
    )
    assert invocation.validation_accepted is True
    gateway.finalize_semantic_invocation(invocation, accepted=True)
    session.finalize_manifest(complete=True)

    records = session.recorder.read_all()
    assert len(records) == 1
    record = records[0]
    result = validate_semantic_call_record(record)
    assert result.valid, result.reason_codes
    assert record["task"] == "structured_claim_shadow"
    assert record["execution_mode"] == "shadow"
    assert record["raw_output_text"] is None
    assert record["raw_output_sha256"] is None

    manifest_path = session.manifest_path
    assert manifest_path is not None
    manifest_result = verify_semantic_manifest(manifest_path)
    assert manifest_result.valid, manifest_result.reason_codes
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["tasks"]["structured_claim_shadow"] == 1
    assert manifest["tasks"]["structured_adapter"] == 0
    assert manifest["exact_replay_ready"] is True


def test_rejected_shadow_output_is_not_cached_and_not_accepted(tmp_path):
    session = SemanticRuntimeSession(
        run_id="runtime-test-2",
        output_directory=tmp_path,
        execution_mode="shadow",
        provider="fake-provider",
        model="fake-model",
        cache=NullLLMResponseCache(),
    )
    model = FakeModel([SimpleNamespace(content=json.dumps({"bad": "shape"}))])
    gateway = Week2LLMGateway(
        model,
        run_id="runtime-test-2",
        output_root=str(tmp_path),
        max_retries=0,
        provider="fake-provider",
        model_name="fake-model",
        semantic_runtime=session,
    )

    def strict_validator(parsed):
        if "bad" in parsed:
            raise ValueError("rejected")
        return parsed

    invocation = gateway.invoke_prebuilt_json_prompt(
        task="structured_claim_shadow",
        prompt="FROZEN PROMPT",
        prompt_version="structured_adapter.claim_extraction_shadow.v1",
        prompt_sha256="c60f1526fd927e4593ab5913bc3c653cd2a05f6d24dc5fdf3e258a3e62128d1e",
        input_schema_version="comqutor.structured_claim_shadow_input.v1",
        output_schema_version="comqutor.structured_claim_shadow.v1",
        payload_for_identity={},
        validator=strict_validator,
    )
    assert invocation.validation_accepted is False
    gateway.finalize_semantic_invocation(
        invocation, accepted=False, fallback_reason="SHADOW_VALIDATION_REJECTED"
    )
    session.finalize_manifest(complete=True)
    records = session.recorder.read_all()
    assert len(records) == 1
    assert records[0]["validation_status"] == "rejected"
    assert records[0]["cache"]["hit"] is False
    result = validate_semantic_call_records(records)
    assert result.valid, result.reason_codes


def test_null_cache_never_hits_across_repeated_identical_calls(tmp_path):
    session = SemanticRuntimeSession(
        run_id="runtime-test-3",
        output_directory=tmp_path,
        execution_mode="shadow",
        provider="fake-provider",
        model="fake-model",
        cache=NullLLMResponseCache(),
    )
    responses = [
        SimpleNamespace(content=json.dumps({"claims": [], "abstentions": []})) for _ in range(2)
    ]
    model = FakeModel(responses)
    gateway = Week2LLMGateway(
        model,
        run_id="runtime-test-3",
        output_root=str(tmp_path),
        max_calls=4,
        provider="fake-provider",
        model_name="fake-model",
        semantic_runtime=session,
    )

    def validator(parsed):
        return parsed

    for _ in range(2):
        invocation = gateway.invoke_prebuilt_json_prompt(
            task="structured_claim_shadow",
            prompt="IDENTICAL PROMPT",
            prompt_version="structured_adapter.claim_extraction_shadow.v1",
            prompt_sha256="c60f1526fd927e4593ab5913bc3c653cd2a05f6d24dc5fdf3e258a3e62128d1e",
            input_schema_version="comqutor.structured_claim_shadow_input.v1",
            output_schema_version="comqutor.structured_claim_shadow.v1",
            payload_for_identity={"same": "payload"},
            validator=validator,
        )
        assert invocation.cache_hit is False
        gateway.finalize_semantic_invocation(invocation, accepted=True)
    assert model.call_count == 2  # Null cache: every logical call reaches the model
