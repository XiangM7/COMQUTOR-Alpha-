"""Phase 1 Master, section 3: structured_claim_shadow task-level execution
policy (timeout_seconds=180, max_retries=1) must be fully isolated from the
three existing Week2 tasks and from the Gateway's shared instance defaults.

No test in this file waits anywhere near 180 real seconds -- the override
mechanism is proven with small, fast numbers; the literal 180.0/1 policy
values are proven by direct attribute inspection, not by timing.
"""

from __future__ import annotations

import json
import time

import pytest

from comqutor_alpha.llm_runtime.contracts import (
    EXECUTION_POLICY_SCHEMA_VERSION,
    validate_semantic_call_record,
)
from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
from comqutor_alpha.structure_engine.structured_output_shadow_provider import (
    STRUCTURED_CLAIM_SHADOW_EXECUTION_POLICY_SOURCE,
    STRUCTURED_CLAIM_SHADOW_MAX_RETRIES,
    STRUCTURED_CLAIM_SHADOW_TIMEOUT_SECONDS,
)
from comqutor_alpha.structure_engine.week2_llm import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    Week2LLMGateway,
)


class _SleepingModel:
    def __init__(self, sleep_seconds: float, payload: dict):
        self.sleep_seconds = sleep_seconds
        self.payload = payload
        self.calls = 0

    def invoke(self, _prompt):
        self.calls += 1
        time.sleep(self.sleep_seconds)
        return type("R", (), {"content": json.dumps(self.payload)})()


def _gateway(tmp_path, model, **kwargs):
    run_dir = tmp_path / "run1"
    run_dir.mkdir(exist_ok=True)
    return Week2LLMGateway(
        model,
        run_id="run1",
        output_root=tmp_path,
        timeout_seconds=kwargs.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
        max_retries=kwargs.get("max_retries", DEFAULT_MAX_RETRIES),
        max_calls=kwargs.get("max_calls", 8),
    )


# --- A. Existing tasks unchanged -------------------------------------------------


def test_structured_claim_shadow_policy_constants_are_the_approved_values():
    assert STRUCTURED_CLAIM_SHADOW_TIMEOUT_SECONDS == 180.0
    assert STRUCTURED_CLAIM_SHADOW_MAX_RETRIES == 1
    assert (
        STRUCTURED_CLAIM_SHADOW_EXECUTION_POLICY_SOURCE
        == "phase1_structured_claim_shadow_anthropic_policy"
    )


def test_shared_gateway_defaults_unchanged():
    assert DEFAULT_TIMEOUT_SECONDS == 15.0
    assert DEFAULT_MAX_RETRIES == 1


def test_existing_three_tasks_invoke_json_signature_has_no_policy_override(tmp_path):
    model = _SleepingModel(0.0, {"value": 1})
    gateway = _gateway(tmp_path, model)
    # invoke_json/invoke_json_with_trace never accepted timeout_seconds/
    # max_retries and still don't -- passing them must raise, not silently
    # widen behavior for the three existing tasks.
    with pytest.raises(TypeError):
        gateway.invoke_json(
            "alpha_classifier",
            {},
            lambda payload: payload,
            timeout_seconds=90,  # type: ignore[call-arg]
        )


def test_existing_task_uses_shared_timeout_not_shadow_override(tmp_path):
    def slow_response():
        time.sleep(0.05)
        return '{"value": 1}'

    class _Model:
        def invoke(self, _prompt):
            time.sleep(0.05)
            return type("R", (), {"content": '{"value": 1}'})()

    gateway = _gateway(tmp_path, _Model(), timeout_seconds=0.01, max_retries=0)
    result = gateway.invoke_json("alpha_classifier", {}, lambda payload: payload)
    assert result is None  # timed out against the SHARED 0.01s instance default
    log = (tmp_path / "run1" / "error_logs" / "week2_llm_errors.jsonl").read_text()
    assert "WEEK2_LLM_TIMEOUT" in log


# --- B. Shadow task override mechanism (scaled-down, no real 90s wait) -----------


def test_prebuilt_prompt_override_timeout_survives_beyond_shared_default(tmp_path):
    """A call that would time out against the shared instance default must
    succeed when a larger explicit override is supplied -- proving the
    override is not silently cancelled by the old shared timeout."""

    payload = {"ok": True}
    model = _SleepingModel(0.05, payload)  # longer than the 0.01s shared default
    gateway = _gateway(tmp_path, model, timeout_seconds=0.01, max_retries=1)

    invocation = gateway.invoke_prebuilt_json_prompt(
        task="structured_claim_shadow",
        prompt="PROMPT",
        prompt_version="v1",
        prompt_sha256="a" * 64,
        input_schema_version="s1",
        output_schema_version="s2",
        payload_for_identity={"x": 1},
        validator=lambda parsed: parsed,
        timeout_seconds=0.2,  # override: larger than the model's 0.05s sleep
        max_retries=0,
        execution_policy_source="phase1_structured_claim_shadow_task_policy",
    )

    assert invocation.provider_status == "success"
    assert invocation.provider_attempt_count == 1  # max_retries=0 -> at most one attempt
    assert invocation.effective_timeout_seconds == 0.2
    assert invocation.effective_max_retries == 0
    assert invocation.execution_policy_source == "phase1_structured_claim_shadow_task_policy"
    assert gateway.timeout_seconds == 0.01  # shared instance default never mutated
    assert gateway.max_retries == 1


def test_prebuilt_prompt_override_timeout_still_times_out_when_exceeded(tmp_path):
    model = _SleepingModel(0.2, {"ok": True})
    gateway = _gateway(tmp_path, model, timeout_seconds=5.0, max_retries=1)

    invocation = gateway.invoke_prebuilt_json_prompt(
        task="structured_claim_shadow",
        prompt="PROMPT",
        prompt_version="v1",
        prompt_sha256="a" * 64,
        input_schema_version="s1",
        output_schema_version="s2",
        payload_for_identity={"x": 1},
        validator=lambda parsed: parsed,
        timeout_seconds=0.02,  # override: smaller than the shared 5.0s default
        max_retries=0,
        execution_policy_source="phase1_structured_claim_shadow_task_policy",
    )

    assert invocation.provider_status == "timeout"
    assert invocation.provider_attempt_count == 1  # exactly one attempt, no retry
    assert invocation.effective_timeout_seconds == 0.02
    assert invocation.effective_max_retries == 0


def test_max_retries_zero_means_at_most_one_attempt_even_on_failure(tmp_path):
    class _AlwaysInvalid:
        def __init__(self):
            self.calls = 0

        def invoke(self, _prompt):
            self.calls += 1
            return type("R", (), {"content": "not json"})()

    model = _AlwaysInvalid()
    gateway = _gateway(tmp_path, model, timeout_seconds=1.0, max_retries=1)

    invocation = gateway.invoke_prebuilt_json_prompt(
        task="structured_claim_shadow",
        prompt="PROMPT",
        prompt_version="v1",
        prompt_sha256="a" * 64,
        input_schema_version="s1",
        output_schema_version="s2",
        payload_for_identity={"x": 1},
        validator=lambda parsed: parsed,
        timeout_seconds=1.0,
        max_retries=0,
        execution_policy_source="phase1_structured_claim_shadow_task_policy",
    )
    assert model.calls == 1
    assert invocation.provider_attempt_count == 1
    assert invocation.retry_count == 0


def test_transient_429_retries_once_and_records_reason(tmp_path):
    class _HTTP429(Exception):
        status_code = 429

    class _Model:
        def __init__(self):
            self.calls = 0

        def invoke(self, _prompt):
            self.calls += 1
            if self.calls == 1:
                raise _HTTP429()
            return type("R", (), {"content": '{"ok": true}'})()

    model = _Model()
    gateway = _gateway(tmp_path, model, max_retries=0)
    invocation = gateway.invoke_prebuilt_json_prompt(
        task="structured_claim_shadow",
        prompt="PROMPT",
        prompt_version="v1",
        prompt_sha256="a" * 64,
        input_schema_version="s1",
        output_schema_version="s2",
        payload_for_identity={"x": 1},
        validator=lambda parsed: parsed,
        timeout_seconds=1.0,
        max_retries=1,
        execution_policy_source="phase1_structured_claim_shadow_anthropic_policy",
    )
    assert model.calls == 2
    assert invocation.provider_status == "success"
    assert invocation.retry_count == 1
    assert invocation.attempt_history[0]["retry_reason"] == "HTTP_429"
    assert invocation.attempt_history[0]["retry_delay_seconds"] == 0.0


def test_malformed_json_and_validation_rejection_never_retry(tmp_path):
    class _Model:
        def __init__(self, content):
            self.calls = 0
            self.content = content

        def invoke(self, _prompt):
            self.calls += 1
            return type("R", (), {"content": self.content})()

    malformed = _Model("not-json")
    malformed_invocation = _gateway(tmp_path, malformed).invoke_prebuilt_json_prompt(
        task="structured_claim_shadow",
        prompt="PROMPT",
        prompt_version="v1",
        prompt_sha256="a" * 64,
        input_schema_version="s1",
        output_schema_version="s2",
        payload_for_identity={"x": 1},
        validator=lambda parsed: parsed,
        max_retries=1,
    )
    assert malformed.calls == 1
    assert malformed_invocation.attempt_history[-1]["status"] == "invalid_json"

    rejected = _Model('{"ok": true}')
    rejected_invocation = _gateway(tmp_path, rejected).invoke_prebuilt_json_prompt(
        task="structured_claim_shadow",
        prompt="PROMPT",
        prompt_version="v1",
        prompt_sha256="a" * 64,
        input_schema_version="s1",
        output_schema_version="s2",
        payload_for_identity={"x": 1},
        validator=lambda _parsed: (_ for _ in ()).throw(ValueError("rejected")),
        max_retries=1,
    )
    assert rejected.calls == 1
    assert rejected_invocation.provider_status == "success"
    assert rejected_invocation.attempt_history[-1]["status"] == "validation_rejected"


# --- Execution-policy persistence (versioned, additive metadata) -----------------


def test_execution_policy_persisted_for_shadow_and_absent_for_existing_tasks(tmp_path):
    session = SemanticRuntimeSession(
        run_id="run1",
        output_directory=tmp_path,
        execution_mode="shadow",
        provider="deepseek",
        model="deepseek-v4-flash",
        profile_id="comqutor_anthropic_medium_sonnet46_v1",
    )
    gateway = _gateway(tmp_path, _SleepingModel(0.0, {"ok": True}), timeout_seconds=1.0, max_retries=1)
    gateway.semantic_runtime = session

    shadow_invocation = gateway.invoke_prebuilt_json_prompt(
        task="structured_claim_shadow",
        prompt="PROMPT",
        prompt_version="v1",
        prompt_sha256="a" * 64,
        input_schema_version="s1",
        output_schema_version="s2",
        payload_for_identity={"x": 1},
        validator=lambda parsed: parsed,
        timeout_seconds=180.0,
        max_retries=1,
        execution_policy_source="phase1_structured_claim_shadow_anthropic_policy",
    )
    gateway.finalize_semantic_invocation(shadow_invocation, accepted=True)

    existing_invocation = gateway.invoke_json_with_trace(
        "alpha_classifier", {"allowed_alpha_ids": []}, lambda payload: payload
    )
    gateway.finalize_semantic_invocation(existing_invocation, accepted=True)

    session.finalize_manifest(complete=True)
    lines = (tmp_path / "llm_semantic_calls.jsonl").read_text().splitlines()
    records = [json.loads(line) for line in lines]
    assert len(records) == 2

    shadow_record = next(r for r in records if r["task"] == "structured_claim_shadow")
    existing_record = next(r for r in records if r["task"] == "alpha_classifier")

    assert "execution_policy" not in existing_record  # byte-identical to pre-policy shape
    assert shadow_record["profile_id"] == "comqutor_anthropic_medium_sonnet46_v1"
    assert shadow_record["execution_policy"]["schema_version"] == EXECUTION_POLICY_SCHEMA_VERSION
    assert shadow_record["execution_policy"]["effective_timeout_seconds"] == 180.0
    assert shadow_record["execution_policy"]["effective_max_retries"] == 1
    assert shadow_record["execution_policy"]["first_attempt_status"] == "success"
    assert shadow_record["execution_policy"]["final_status"] == "success"

    assert validate_semantic_call_record(shadow_record).valid
    assert validate_semantic_call_record(existing_record).valid


def test_execution_policy_validator_rejects_malformed_policy():
    from comqutor_alpha.llm_runtime.canonical_json import sha256_canonical_json

    base = {
        "schema_version": "comqutor.semantic_call.v1",
        "call_id": "run1:semantic:0:x",
        "run_id": "run1",
        "call_sequence": 0,
        "task": "structured_claim_shadow",
        "execution_mode": "shadow",
        "prompt_version": "v1",
        "prompt_sha256": "a" * 64,
        "input_schema_version": "s1",
        "output_schema_version": "s2",
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "taxonomy_version": None,
        "input_payload": {},
        "input_sha256": sha256_canonical_json({}),
        "raw_output_text": None,
        "raw_output_sha256": None,
        "validated_output": None,
        "validated_output_sha256": None,
        "started_at": "2026-01-01T00:00:00+00:00",
        "completed_at": "2026-01-01T00:00:01+00:00",
        "latency_ms": 1000,
        "token_usage": {"input_tokens": None, "output_tokens": None, "total_tokens": None},
        "cache": {"cache_key": "comqutor:llm:v1:" + "b" * 64, "hit": False},
        "retry_count": 0,
        "validation_status": "not_run",
        "provider_status": "timeout",
        "fallback_used": False,
        "fallback_reason": None,
        "error_code": "WEEK2_LLM_TIMEOUT",
        "error_message": None,
    }
    valid_record = {**base, "execution_policy": {
        "schema_version": "comqutor.semantic_call_execution_policy.v1",
        "effective_timeout_seconds": 90.0,
        "effective_max_retries": 0,
        "execution_policy_source": "phase1_structured_claim_shadow_task_policy",
    }}
    assert validate_semantic_call_record(valid_record).valid

    malformed_record = {**base, "execution_policy": {"effective_timeout_seconds": "not-a-number"}}
    result = validate_semantic_call_record(malformed_record)
    assert not result.valid
    assert "SEMANTIC_EXECUTION_POLICY_FIELD_MISSING" in result.reason_codes
