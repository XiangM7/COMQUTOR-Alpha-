"""2026-10-08 (T3 closeout): the selectable Week 2 execution profile
``t3_verified_20261008`` (week2_execution_profile.py).

Built through the production ``build_server_week2_llm_gateway`` and the real
tradingagents client construction; only the lowest HTTP layer is a fake
(``_base_transport_for_testing``), so what reaches it is exactly what a real
run would put on the wire. These tests show wiring and failure handling, not
model behavior. Zero network.
"""

from __future__ import annotations

import json

import httpx
import pytest

from comqutor_alpha.structure_engine import week2_llm
from comqutor_alpha.structure_engine.week2_execution_profile import (
    PROFILE_ENV_VAR,
    T3_VERIFIED_20261008,
)
from comqutor_alpha.structure_engine.week2_llm import build_server_week2_llm_gateway

PROFILE_TASKS = ("content_support_verification", "alpha_classifier", "evidence_stance_classifier")


@pytest.fixture
def base_env(monkeypatch):
    """The deployed .env's conflicting values, to show which ones a profile replaces."""
    for name, value in {
        "COMQUTOR_WEEK2_LLM_ENABLED": "1",
        "COMQUTOR_WEEK2_LLM_PROVIDER": "deepseek",
        "COMQUTOR_WEEK2_LLM_MODEL": "deepseek-v4-flash",
        "COMQUTOR_WEEK2_LLM_BASE_URL": "https://api.deepseek.com",
        "COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS": "45",
        "COMQUTOR_WEEK2_LLM_MAX_RETRIES": "1",
        "COMQUTOR_WEEK2_LLM_CONCURRENCY": "8",
        "COMQUTOR_WEEK2_STANCE_CONCURRENCY": "8",
        "DEEPSEEK_API_KEY": "test-not-a-key",
    }.items():
        monkeypatch.setenv(name, value)
    for name in (PROFILE_ENV_VAR, "COMQUTOR_WEEK2_LLM_ENABLE_REQUEST_AUDIT", "COMQUTOR_WEEK2_CONTENT_SUPPORT_BATCH_SIZE",
                 "COMQUTOR_WEEK2_ALPHA_CLASSIFIER_MAX_TOKENS", "COMQUTOR_WEEK2_CONTENT_SUPPORT_MAX_TOKENS"):
        monkeypatch.delenv(name, raising=False)


def _completion(content: str) -> httpx.Response:
    return httpx.Response(200, json={"id": "fixed", "object": "chat.completion", "created": 0, "model": "deepseek-flash",
                                     "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                                     "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})


def _requests(tmp_path, run_id):
    path = tmp_path / run_id / "error_logs" / "week2_llm_provider_request_audit.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def test_without_a_profile_the_environment_behavior_is_unchanged(tmp_path, base_env):
    gateway = build_server_week2_llm_gateway("no-profile", tmp_path)
    assert gateway is not None
    assert gateway.execution_profile is None
    assert gateway.max_retries == 1
    assert all(gateway.task_timeout_seconds_for(task) == 45.0 for task in PROFILE_TASKS)
    assert gateway._audit_enabled is False
    assert week2_llm.resolve_alpha_classifier_concurrency() == 8
    assert week2_llm.resolve_evidence_stance_concurrency() == 8


def test_profile_replaces_timeouts_retries_audit_and_concurrency(tmp_path, base_env, monkeypatch):
    monkeypatch.setenv(PROFILE_ENV_VAR, "t3_verified_20261008")
    gateway = build_server_week2_llm_gateway("with-profile", tmp_path)
    assert gateway is not None
    assert gateway.execution_profile == "t3_verified_20261008"
    assert gateway.max_retries == 0
    assert gateway.task_timeout_seconds_for("content_support_verification") == 120.0
    assert gateway.task_timeout_seconds_for("alpha_classifier") == 45.0
    assert gateway.task_timeout_seconds_for("evidence_stance_classifier") == 120.0
    assert gateway.task_timeout_seconds_for("structure_extractor") == 45.0  # not a profile task: the shared env timeout
    assert gateway._audit_enabled is True
    assert week2_llm.resolve_alpha_classifier_concurrency() == 4
    assert week2_llm.resolve_evidence_stance_concurrency() == 4
    assert week2_llm._resolve_task_max_retries("evidence_stance_classifier", gateway.max_retries) == 0


def test_profile_requests_carry_each_task_timeout_on_the_wire_and_no_extra_control_fields(tmp_path, base_env, monkeypatch):
    monkeypatch.setenv(PROFILE_ENV_VAR, "t3_verified_20261008")
    app_timeouts = {}
    real_call_with_timeout = week2_llm.call_with_timeout

    def recording_call_with_timeout(function, timeout_seconds):
        app_timeouts.setdefault("calls", []).append(timeout_seconds)
        return real_call_with_timeout(function, timeout_seconds)

    monkeypatch.setattr(week2_llm, "call_with_timeout", recording_call_with_timeout)
    hits = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(request)
        return _completion("{}")

    run_id = "profile-wire"
    gateway = build_server_week2_llm_gateway(run_id, tmp_path, execution_id=run_id, _base_transport_for_testing=httpx.MockTransport(handler))
    assert gateway is not None
    observed = {}
    for task in PROFILE_TASKS:
        app_timeouts["calls"] = []
        invocation = gateway.invoke_json_with_trace(task, {"items": [{"claim_id": f"c-{task}"}]}, lambda parsed: parsed)
        assert invocation.validation_accepted and invocation.provider_attempt_count == 1
        observed[task] = app_timeouts["calls"]
    assert observed == {"content_support_verification": [120.0], "alpha_classifier": [45.0], "evidence_stance_classifier": [120.0]}

    records = _requests(tmp_path, run_id)
    assert [r["task"] for r in records] == list(PROFILE_TASKS)
    for record in records:
        body = json.loads(record["body"])
        assert sorted(body) == ["messages", "model", "stream"]  # no max_tokens/temperature/thinking/reasoning control field
        assert body["model"] == "deepseek-v4-flash" and body["stream"] is False
        assert record["headers"]["x-stainless-retry-count"] == "0"
        assert record["headers"]["authorization"] == "REDACTED"
        assert record["url"] == "https://api.deepseek.com/chat/completions"
    read_timeouts = {r["task"]: r["headers"]["x-stainless-read-timeout"] for r in records}
    assert read_timeouts == {"content_support_verification": "120.0", "alpha_classifier": "45.0", "evidence_stance_classifier": "120.0"}
    assert len(hits) == 3


def test_profile_content_support_batch_size_reaches_the_production_call(tmp_path, base_env, monkeypatch):
    import comqutor_alpha.structure_engine.structured_output_adapter as soa

    run_dir = tmp_path / "run_profile_batch"
    run_dir.mkdir()
    (run_dir / "raw_agent_outputs.json").write_text(json.dumps(
        {"run_id": "run_profile_batch", "ticker": "AMD", "agent_outputs": [{"agent": "news_agent", "raw_output": "AI demand supports GPU demand."}]}))
    captured = {}
    real_fn = soa.apply_llm_content_support_verification

    def spy(records, sources, *, llm_gateway=None, batch_size=None):
        captured["batch_size"] = batch_size
        return real_fn(records, sources, llm_gateway=llm_gateway, batch_size=batch_size)

    monkeypatch.setattr(soa, "apply_llm_content_support_verification", spy)
    monkeypatch.setenv("COMQUTOR_WEEK2_CONTENT_SUPPORT_BATCH_SIZE", "5")
    monkeypatch.setenv(PROFILE_ENV_VAR, "t3_verified_20261008")
    soa.adapt_run_outputs(run_dir, llm_gateway=None)
    assert captured["batch_size"] == T3_VERIFIED_20261008.content_support_batch_size == 1


def test_unknown_profile_builds_no_gateway_and_records_why(tmp_path, base_env, monkeypatch):
    monkeypatch.setenv(PROFILE_ENV_VAR, "not_a_profile")
    assert build_server_week2_llm_gateway("unknown-profile", tmp_path) is None
    errors = (tmp_path / "unknown-profile" / "error_logs" / "week2_llm_errors.jsonl").read_text(encoding="utf-8")
    assert "WEEK2_LLM_PROFILE_UNKNOWN" in errors


@pytest.mark.parametrize("failure", ["read_timeout_after_send", "http_500"])
def test_failure_or_unknown_outcome_is_not_a_valid_none_and_is_not_resent(tmp_path, base_env, monkeypatch, failure):
    """A request that was sent but never answered (unknown) and one answered with an error are each tried once
    (both retry layers 0) and end as a classification failure -- never as the model's own NONE."""
    from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
    from comqutor_alpha.structure_engine.alpha_mapper import (
        compute_alpha_classification_completion,
        map_structured_records,
    )

    monkeypatch.setenv(PROFILE_ENV_VAR, "t3_verified_20261008")
    hits = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(request)
        if failure == "read_timeout_after_send":
            raise httpx.ReadTimeout("no response", request=request)
        return httpx.Response(500, json={"error": {"message": "server error"}})

    run_id = f"profile-failure-{failure}"
    gateway = build_server_week2_llm_gateway(run_id, tmp_path, execution_id=run_id, _base_transport_for_testing=httpx.MockTransport(handler))
    # production attaches the run's semantic session before mapping (without one, an audited gateway refuses to send at all)
    from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession

    (tmp_path / run_id).mkdir(exist_ok=True)
    gateway.attach_semantic_runtime(SemanticRuntimeSession(run_id=run_id, output_directory=tmp_path / run_id, execution_mode="test",
                                                           provider="deepseek", model="deepseek-v4-flash"))
    record = {"claim_id": f"{run_id}:agent:claim:1", "claim": "Hyperscaler AI capex keeps rising, lifting accelerator demand.",
              "evidence": "Hyperscaler AI capex keeps rising, lifting accelerator demand.", "ticker": "NVDA", "agent": "news_agent",
              "factors": [], "direction": "positive", "claim_quality": "analytical"}
    matches = map_structured_records([record], load_alpha_taxonomy(), llm_gateway=gateway, concurrency=1)
    assert len(hits) == 1
    match = matches[0]
    assert match.get("matched_alpha") in (None, "")
    assert match.get("alpha_match_fallback_reason")
    completion = compute_alpha_classification_completion({"matches": matches})
    assert completion["valid_none_count"] == 0
    assert completion["call_failure_count"] == 1
    records = _requests(tmp_path, run_id)
    assert len(records) == 1 and records[0]["headers"]["x-stainless-retry-count"] == "0"
