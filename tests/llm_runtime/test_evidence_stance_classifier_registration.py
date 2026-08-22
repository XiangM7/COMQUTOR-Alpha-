"""Post-Alpha-Authority-Migration Cleanup: evidence_stance_classifier (B1's
own LLM stance upgrade task, evidence_stance_llm.LLM_TASK_NAME) is now a
first-class registered semantic task -- same canonical mechanism as
structured_adapter/alpha_classifier/structure_extractor, no parallel
registry, no special-casing. Entirely offline: FakeModel only, no real
Provider call anywhere in this file.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from comqutor_alpha.llm_runtime.cache import NullLLMResponseCache, build_llm_cache_key
from comqutor_alpha.llm_runtime.contracts import SEMANTIC_TASKS
from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
from comqutor_alpha.replay.source_bundle import _SEMANTIC_TASKS as REPLAY_SEMANTIC_TASKS
from comqutor_alpha.replay.source_bundle import _SUPPORTED_CALL_IDENTITIES
from comqutor_alpha.structure_engine.week2_llm import (
    _TASK_RUNTIME_METADATA,
    Week2LLMGateway,
)

TASK = "evidence_stance_classifier"


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


# ---------------------------------------------------------------------------
# A. Recognized as a legal semantic task
# ---------------------------------------------------------------------------


def test_a_registered_in_canonical_semantic_tasks():
    assert TASK in SEMANTIC_TASKS


def test_a_registered_in_replay_source_bundle_semantic_tasks():
    """A second, separately-maintained copy of the task vocabulary
    (comqutor_alpha/replay/source_bundle.py, not imported from
    contracts.py) -- both must agree or a real recorded call succeeds at
    the runtime layer but then cannot be loaded for exact replay."""
    assert TASK in REPLAY_SEMANTIC_TASKS


def test_a_registered_in_replay_supported_call_identities():
    assert TASK in _SUPPORTED_CALL_IDENTITIES
    identity = _SUPPORTED_CALL_IDENTITIES[TASK]
    assert identity["prompt_version"] == _TASK_RUNTIME_METADATA[TASK]["prompt_version"]
    assert identity["input_schema_version"] == _TASK_RUNTIME_METADATA[TASK]["input_schema_version"]
    assert identity["output_schema_version"] == _TASK_RUNTIME_METADATA[TASK]["output_schema_version"]
    assert identity["taxonomy_version"] == _TASK_RUNTIME_METADATA[TASK]["taxonomy_version"]
    assert identity["prompt_sha256"] == Week2LLMGateway.prompt_identity_sha256(TASK)


# ---------------------------------------------------------------------------
# B. Execution policy / schema lookup succeeds through the same canonical
#    path used by other semantic tasks
# ---------------------------------------------------------------------------


def test_b_runtime_metadata_present_and_unchanged_by_this_task():
    """The registry fix conforms to B1's existing runtime metadata -- it
    does not rewrite it. prompt_version stays v3, the frozen B1 prompt."""
    metadata = _TASK_RUNTIME_METADATA[TASK]
    assert metadata["semantic_task"] == TASK
    assert metadata["prompt_version"] == "evidence_stance.llm_classifier.v3"
    assert metadata["input_schema_version"] == "evidence_stance.llm_classifier.input.v1"
    assert metadata["output_schema_version"] == "evidence_stance.llm_classifier.output.v1"
    assert metadata["taxonomy_version"] == "alpha_taxonomy_v1"


def test_b_prompt_identity_resolves_through_the_same_canonical_method():
    text = Week2LLMGateway.prompt_identity_text(TASK)
    assert text.startswith("You are a constrained COMQUTOR extraction component.")
    assert len(Week2LLMGateway.prompt_identity_sha256(TASK)) == 64


def test_b_cache_key_construction_succeeds_through_the_shared_helper():
    key = build_llm_cache_key(
        task=TASK,
        prompt_version=_TASK_RUNTIME_METADATA[TASK]["prompt_version"],
        prompt_sha256=Week2LLMGateway.prompt_identity_sha256(TASK),
        provider="fake-provider",
        model="fake-model",
        input_schema_version=_TASK_RUNTIME_METADATA[TASK]["input_schema_version"],
        output_schema_version=_TASK_RUNTIME_METADATA[TASK]["output_schema_version"],
        input_sha256="0" * 64,
        taxonomy_version=_TASK_RUNTIME_METADATA[TASK]["taxonomy_version"],
        run_id="registration-test",
    )
    assert key.startswith("comqutor:llm:v1:")


# ---------------------------------------------------------------------------
# C. A mocked invocation can enter the runtime without a registry failure
# ---------------------------------------------------------------------------


def _stance_payload():
    return {
        "items": [
            {
                "claim_id": "claim-1",
                "target_alpha_id": "A101",
                "ticker": "NVDA",
                "claim": "AI training demand is rising.",
                "evidence": "AI training demand is rising.",
                "target_alpha_name": "AI Expansion",
                "target_alpha_definition": "AI training and adoption increase demand for accelerators.",
            }
        ]
    }


def _batch_validator(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise TypeError("evidence_stance_classifier response missing an items array")
    return payload["items"]


def test_c_valid_response_enters_the_runtime_with_no_registry_failure(tmp_path):
    session = SemanticRuntimeSession(
        run_id="registration-test-c",
        output_directory=tmp_path,
        execution_mode="live",
        provider="fake-provider",
        model="fake-model",
        cache=NullLLMResponseCache(),
    )
    model = FakeModel(
        [
            SimpleNamespace(
                content=json.dumps(
                    {"items": [{"claim_id": "claim-1", "target_alpha_id": "A101", "stance": "neutral_background"}]}
                )
            )
        ]
    )
    gateway = Week2LLMGateway(
        model,
        run_id="registration-test-c",
        output_root=str(tmp_path),
        provider="fake-provider",
        model_name="fake-model",
        semantic_runtime=session,
    )

    invocation = gateway.invoke_json_with_trace(TASK, _stance_payload(), _batch_validator)

    assert invocation.validation_accepted is True
    assert invocation.error_code is None
    gateway.finalize_semantic_invocation(invocation, accepted=True)
    session.finalize_manifest(complete=True)

    records = session.recorder.read_all()
    assert len(records) == 1
    assert records[0]["task"] == TASK
    assert records[0]["validation_status"] == "accepted"
    manifest = json.loads(session.manifest_path.read_text(encoding="utf-8"))
    assert manifest["tasks"][TASK] == 1
    assert manifest["exact_replay_ready"] is True


# ---------------------------------------------------------------------------
# D. Malformed provider output still fails closed
# ---------------------------------------------------------------------------


def test_d_malformed_response_fails_closed_not_a_registry_error(tmp_path):
    session = SemanticRuntimeSession(
        run_id="registration-test-d",
        output_directory=tmp_path,
        execution_mode="live",
        provider="fake-provider",
        model="fake-model",
        cache=NullLLMResponseCache(),
    )
    model = FakeModel([SimpleNamespace(content=json.dumps({"not_items": []}))])
    gateway = Week2LLMGateway(
        model,
        run_id="registration-test-d",
        output_root=str(tmp_path),
        max_retries=0,
        provider="fake-provider",
        model_name="fake-model",
        semantic_runtime=session,
    )

    invocation = gateway.invoke_json_with_trace(TASK, _stance_payload(), _batch_validator)

    assert invocation.validation_accepted is False
    assert invocation.error_code == "WEEK2_LLM_VALIDATION_FAILED"
    gateway.finalize_semantic_invocation(
        invocation, accepted=False, fallback_reason=invocation.error_code
    )
    session.finalize_manifest(complete=True)

    records = session.recorder.read_all()
    assert len(records) == 1
    assert records[0]["validation_status"] == "rejected"
    assert records[0]["fallback_used"] is True
    assert records[0]["validated_output"] is None


# ---------------------------------------------------------------------------
# E. No real Provider calls
# ---------------------------------------------------------------------------


def test_e_no_real_provider_client_imported_by_this_module():
    import comqutor_alpha.llm_runtime.contracts as contracts_module
    import comqutor_alpha.replay.source_bundle as source_bundle_module

    for module in (contracts_module, source_bundle_module):
        source = module.__file__
        text = open(source, encoding="utf-8").read()
        assert "tradingagents" not in text.lower()
        assert "requests" not in text.lower()


def test_e_fake_model_call_count_matches_logical_calls_exactly(tmp_path):
    session = SemanticRuntimeSession(
        run_id="registration-test-e",
        output_directory=tmp_path,
        execution_mode="live",
        provider="fake-provider",
        model="fake-model",
        cache=NullLLMResponseCache(),
    )
    model = FakeModel(
        [SimpleNamespace(content=json.dumps({"items": [{"claim_id": "claim-1", "target_alpha_id": "A101", "stance": "neutral_background"}]}))]
    )
    gateway = Week2LLMGateway(
        model,
        run_id="registration-test-e",
        output_root=str(tmp_path),
        provider="fake-provider",
        model_name="fake-model",
        semantic_runtime=session,
    )
    gateway.invoke_json_with_trace(TASK, _stance_payload(), _batch_validator)
    assert model.call_count == 1  # exactly one logical call, zero real Provider calls


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
