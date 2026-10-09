import json
import os
import threading
import time
from typing import Any

import pytest
from dotenv import load_dotenv

from comqutor_alpha.structure_engine.alpha_mapper import map_claim_to_alpha
from comqutor_alpha.structure_engine.structure_extractor import extract_structures_from_records
from comqutor_alpha.structure_engine.structured_output_adapter import adapt_raw_agent_outputs
from comqutor_alpha.structure_engine.week2_llm import (
    Week2LLMGateway,
    build_server_week2_llm_gateway,
)


class _Response:
    def __init__(self, content):
        self.content = content


class _SequenceModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def invoke(self, _prompt):
        response = self.responses[self.calls]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        if callable(response):
            response = response()
        return _Response(response)


def _gateway(tmp_path, model, **kwargs):
    (tmp_path / "run1").mkdir(exist_ok=True)
    return Week2LLMGateway(
        model,
        run_id="run1",
        output_root=tmp_path,
        timeout_seconds=kwargs.get("timeout_seconds", 0.2),
        max_retries=kwargs.get("max_retries", 1),
        max_calls=kwargs.get("max_calls", 8),
    )


def _record(text, factors=None):
    raw_id = "run1:news_agent:news_report"
    return {
        "run_id": "run1",
        "ticker": "NVDA",
        "agent": "news_agent",
        "claim_id": f"{raw_id}:claim:1",
        "agent_output_id": f"{raw_id}:claim:1",
        "source_agent_output_id": raw_id,
        "claim": text,
        "evidence": text,
        "factors": factors or [],
        "direction": "neutral",
        "confidence": 0.8,
    }


def test_gateway_retries_invalid_json_then_returns_validated_result(tmp_path):
    model = _SequenceModel(["not json", '{"value": 7}'])
    gateway = _gateway(tmp_path, model)

    result = gateway.invoke_json(
        "alpha_classifier",
        {"allowed_alpha_ids": ["A101"]},
        lambda payload: payload["value"],
    )

    assert result == 7
    assert model.calls == 2
    log = (tmp_path / "run1" / "error_logs" / "week2_llm_errors.jsonl").read_text()
    assert "WEEK2_LLM_INVALID_JSON" in log


class _ResponseWithMetadata:
    def __init__(self, content, response_metadata):
        self.content = content
        self.response_metadata = response_metadata


class _MetadataSequenceModel:
    """Like _SequenceModel, but returns each queued response object AS-IS
    (never re-wrapped in a bare _Response) -- needed so a queued
    _ResponseWithMetadata's own .response_metadata (finish_reason/usage/id)
    survives, since _SequenceModel's own invoke() always wraps whatever it
    is given in a fresh _Response(content=...), which would otherwise
    discard response_metadata entirely."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def invoke(self, _prompt):
        response = self.responses[self.calls]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        return response


def _semantic_gateway(tmp_path, model, run_id="run-attempts", **kwargs):
    from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession

    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    session = SemanticRuntimeSession(
        run_id=run_id, output_directory=run_dir, execution_mode="test",
        provider="fake-provider", model="fake-model",
    )
    gateway = Week2LLMGateway(
        model, run_id=run_id, output_root=tmp_path,
        timeout_seconds=kwargs.get("timeout_seconds", 0.2),
        max_retries=kwargs.get("max_retries", 1),
        max_calls=kwargs.get("max_calls", 8),
        provider="fake-provider", model_name="fake-model", semantic_runtime=session,
    )
    return gateway, session


def test_request_attempts_retains_both_the_failed_and_the_successful_real_attempt(tmp_path):
    """2026-10-01 (v7 limited real-verification round): a real execution
    (t3live_20261001T230846Z_16d44096) showed the first of two real attempts
    had its own usage/finish_reason overwritten once the retry succeeded --
    unrecoverable even though it was a real, billed Provider call. Fixed by
    appending each attempt to request_attempts rather than only keeping
    "last_*". This is the exact scope-validation case the task asked for:
    attempt 1 fails (non-truncation), attempt 2 succeeds -- BOTH real
    attempts' own records must survive in the persisted call record."""
    model = _MetadataSequenceModel([
        _ResponseWithMetadata(
            "not valid json",
            {"id": "resp-attempt-1", "model_name": "fake-model", "finish_reason": "stop",
             "token_usage": {"completion_tokens": 50, "prompt_tokens": 100, "total_tokens": 150}},
        ),
        _ResponseWithMetadata(
            '{"decision": "none", "selected_alpha_id": null}',
            {"id": "resp-attempt-2", "model_name": "fake-model", "finish_reason": "stop",
             "token_usage": {"completion_tokens": 20, "prompt_tokens": 100, "total_tokens": 120}},
        ),
    ])
    gateway, session = _semantic_gateway(tmp_path, model)

    result = gateway.invoke_json("alpha_classifier", {"allowed_alpha_ids": ["A304"]}, lambda p: p)

    assert result == {"decision": "none", "selected_alpha_id": None}
    assert model.calls == 2

    records = [
        json.loads(line)
        for line in session.recorder.calls_path.read_text().splitlines()
        if line.strip()
    ]
    assert len(records) == 1
    attempts = records[0]["request_attempts"]
    assert len(attempts) == 2

    assert attempts[0]["attempt_number"] == 1
    assert attempts[0]["error_code"] == "WEEK2_LLM_INVALID_JSON"
    assert attempts[0]["finish_reason"] == "stop"
    assert attempts[0]["raw_usage"]["completion_tokens"] == 50

    assert attempts[1]["attempt_number"] == 2
    assert attempts[1]["provider_status"] == "success"
    assert attempts[1]["error_code"] is None
    assert attempts[1]["finish_reason"] == "stop"
    assert attempts[1]["raw_usage"]["completion_tokens"] == 20


def test_truncated_response_is_not_retried_and_preserves_the_truncation_reason(tmp_path):
    """A response whose own finish_reason is confirmed "length" must not be
    retried under the identical token configuration (the real execution
    t3live_20261001T230846Z_16d44096 showed this reliably truncates again,
    wasting a real billed request) -- and must never be recorded as NONE."""
    model = _MetadataSequenceModel([
        _ResponseWithMetadata(
            "",  # empty content -- all of the output budget went to reasoning
            {"id": "resp-truncated", "model_name": "fake-model", "finish_reason": "length",
             "token_usage": {"completion_tokens": 200, "prompt_tokens": 100, "total_tokens": 300}},
        ),
        # Never reached -- the retry loop must break before a second attempt.
        '{"decision": "select", "selected_alpha_id": "A304"}',
    ])
    gateway, session = _semantic_gateway(tmp_path, model, max_retries=1)

    result = gateway.invoke_json("alpha_classifier", {"allowed_alpha_ids": ["A304"]}, lambda p: p)

    assert result is None
    assert model.calls == 1  # the second, pre-queued response was never consumed

    records = [
        json.loads(line)
        for line in session.recorder.calls_path.read_text().splitlines()
        if line.strip()
    ]
    assert len(records) == 1
    record = records[0]
    assert record["error_code"] == "WEEK2_LLM_OUTPUT_TRUNCATED"
    assert record["retry_count"] == 0
    assert record["validation_status"] in {"rejected", "not_run"}
    attempts = record["request_attempts"]
    assert len(attempts) == 1
    assert attempts[0]["finish_reason"] == "length"
    assert attempts[0]["error_code"] == "WEEK2_LLM_OUTPUT_TRUNCATED"


def test_later_started_call_completing_first_does_not_lose_either_audit_record(tmp_path):
    """2026-10-02 (concurrent-audit-loss incident fix). Drives the REAL
    Week2LLMGateway -> SemanticRuntimeSession -> SemanticCallRecorder path
    (not a direct recorder-level test -- see tests/llm_runtime/
    test_recorder.py for that) with a fixed, order-controlled fake model:
    call 1 starts first (lower call_sequence, allocated by the real
    SemanticRuntimeSession before the model is ever invoked) but is made to
    block inside its own model.invoke() until call 2 -- which starts
    second -- has already returned and been fully persisted. This is
    exactly the real condition that lost ~240 real, billed attempts' own
    audit records in a live NVDA run (034a0a60-430e-41f8-8321-03a11389707a):
    a later-started call completing, and being appended, before an
    earlier-started one. Both records must survive."""
    call1_started = threading.Event()
    call2_persisted = threading.Event()

    class _OrderControlledModel:
        def __init__(self):
            self.calls = 0
            self._lock = threading.Lock()

        def invoke(self, prompt):
            with self._lock:
                self.calls += 1
                n = self.calls
            if n == 1:
                call1_started.set()
                assert call2_persisted.wait(timeout=5), "call 2 never signaled completion"
                return _Response('{"decision": "none", "selected_alpha_id": null}')
            return _Response('{"decision": "select", "selected_alpha_id": "A304"}')

    model = _OrderControlledModel()
    gateway, session = _semantic_gateway(tmp_path, model)
    results: dict[str, Any] = {}

    def run_call1():
        results["call1"] = gateway.invoke_json(
            "alpha_classifier", {"allowed_alpha_ids": ["A304"], "which": 1}, lambda p: p
        )

    def run_call2():
        assert call1_started.wait(timeout=5), "call 1 never started"
        results["call2"] = gateway.invoke_json(
            "alpha_classifier", {"allowed_alpha_ids": ["A304"], "which": 2}, lambda p: p
        )
        call2_persisted.set()

    thread1 = threading.Thread(target=run_call1)
    thread2 = threading.Thread(target=run_call2)
    thread1.start()
    assert call1_started.wait(timeout=5)
    thread2.start()
    thread1.join(timeout=10)
    thread2.join(timeout=10)

    assert results["call1"] == {"decision": "none", "selected_alpha_id": None}
    assert results["call2"] == {"decision": "select", "selected_alpha_id": "A304"}

    records = [
        json.loads(line)
        for line in session.recorder.calls_path.read_text().splitlines()
        if line.strip()
    ]
    assert len(records) == 2  # BOTH real attempts persisted -- neither lost
    by_which = {r["input_payload"]["which"]: r for r in records}
    assert set(by_which) == {1, 2}

    # Call 1 started first (lower call_sequence) but was appended/persisted
    # second (higher persist_sequence) -- the exact inversion that used to
    # be rejected as RECORDER_SEQUENCE_NOT_MONOTONIC.
    assert by_which[1]["call_sequence"] < by_which[2]["call_sequence"]
    assert by_which[1]["persist_sequence"] > by_which[2]["persist_sequence"]
    assert session.recorder.verify_integrity().valid

    # Replay/manifest validation (the same validator build_semantic_manifest
    # itself uses) must accept this real, out-of-order-completion artifact.
    from comqutor_alpha.llm_runtime.contracts import validate_semantic_call_records

    assert validate_semantic_call_records(records).valid

    # Request-budget counting is untouched by this fix -- two real attempts
    # were made, two calls were reserved against the budget.
    assert gateway.call_count == 2


def test_concurrent_success_timeout_and_retry_all_preserve_their_own_attempts(tmp_path):
    """2026-10-02 (concurrent-audit-loss incident fix). Three real logical
    calls dispatched concurrently through the same real Gateway/Session/
    recorder: one succeeds on its first attempt, one times out then
    succeeds on its one allowed retry, and one succeeds immediately but is
    made to finish (and persist) before the other two -- despite starting
    last. Every one of the three real logical calls, and every one of the
    real attempts within them (including the timed-out first attempt that
    preceded a successful retry), must be preserved -- none silently
    dropped by the concurrent persistence path.

    2026-10-06 (round 14): root cause of this test's occasional failure, and
    a correction of the first attempt to fix it.

    The ORIGINAL version never established the two orderings it asserts.
    (a) "call 3 started last" relied on thread start order, which is not
    guaranteed. (b) "call 3 persisted first" relied on an Event set INSIDE
    the model's own which==3 invoke(), i.e. before call 3's own post-
    processing had run, so call 1 (unblocked at that instant) and call 3
    raced to recorder.append(). Reproduced under recorded before/after
    snapshots (docs/audit_artifacts/.../round14_recovery_closure_20261006/
    flaky_test_root_cause_experiments.json): the original test fails
    against BOTH the pre-repair gateway and the current one, and fails
    deterministically against either when only call 3's persist is slowed --
    so the cause is the test's synchronization, not the gateway's identity,
    terminal-state, retry or logging behavior.

    A first fix made call 1's model.invoke() wait for call 3's full persist.
    That was wrong: that wait runs inside the gateway's own 0.05 s per-call
    timeout (which this test needs to be that short for call 2's retry
    scenario), so call 1 could itself time out (~1-2% of natural runs, 100%
    with a slowed persist). This version removes the model-level wait
    entirely. Orders are established where they are asserted: threads are
    started one at a time, each only after the previous call has actually
    begun (so call_sequence 1 < 2 < 3 is guaranteed); and call 1's PERSIST
    (recorder.append, outside any gateway timeout) waits for call 3's
    persist to have completed. Every assertion and every timing parameter
    below is unchanged."""

    def fast_response():
        return _Response('{"decision": "select", "selected_alpha_id": "A304"}')

    def slow_then_fast_response_factory():
        state = {"n": 0}

        def _respond():
            state["n"] += 1
            if state["n"] == 1:
                time.sleep(0.3)  # exceeds the gateway's own timeout_seconds below
            return _Response('{"decision": "select", "selected_alpha_id": "A101"}')

        return _respond

    started = {1: threading.Event(), 2: threading.Event(), 3: threading.Event()}
    call3_appended = threading.Event()

    class _ThirdCallPersistsFirstModel:
        """All three calls return promptly (call 2's first attempt overruns
        the gateway timeout and its retry succeeds). Each signals when its
        call has actually begun, so the test can start them in a guaranteed
        order."""

        def __init__(self):
            self._slow_then_fast = slow_then_fast_response_factory()

        def invoke(self, prompt):
            payload = json.loads(prompt.rsplit("INPUT_JSON:", 1)[-1])
            which = payload["which"]
            started[which].set()
            if which == 2:
                return self._slow_then_fast()
            return fast_response()

    model = _ThirdCallPersistsFirstModel()
    gateway, session = _semantic_gateway(tmp_path, model, timeout_seconds=0.05, max_retries=1)

    real_append = session.recorder.append

    def ordered_append(record):
        which = record["input_payload"]["which"]
        if which == 1:
            # Call 1 may not persist until call 3 has: this is the ordering
            # the test asserts, established at the persist step itself.
            assert call3_appended.wait(timeout=5), "call 3 never persisted"
        real_append(record)
        if which == 3:
            call3_appended.set()

    session.recorder.append = ordered_append

    results: dict[int, Any] = {}
    results_lock = threading.Lock()

    def run(which: int):
        result = gateway.invoke_json(
            "alpha_classifier", {"allowed_alpha_ids": ["A304"], "which": which}, lambda p: p
        )
        with results_lock:
            results[which] = result

    threads = []
    for which in (1, 2, 3):
        thread = threading.Thread(target=run, args=(which,))
        threads.append(thread)
        thread.start()
        assert started[which].wait(timeout=5), f"call {which} never began"
    for t in threads:
        t.join(timeout=10)

    assert results[1] == {"decision": "select", "selected_alpha_id": "A304"}
    assert results[2] == {"decision": "select", "selected_alpha_id": "A101"}
    assert results[3] == {"decision": "select", "selected_alpha_id": "A304"}

    records = [
        json.loads(line)
        for line in session.recorder.calls_path.read_text().splitlines()
        if line.strip()
    ]
    assert len(records) == 3  # all three logical calls persisted, none lost
    by_which = {r["input_payload"]["which"]: r for r in records}
    assert set(by_which) == {1, 2, 3}

    # call 2's one real timeout-then-retry attempt sequence is fully intact.
    attempts_2 = by_which[2]["request_attempts"]
    assert len(attempts_2) == 2
    assert attempts_2[0]["provider_status"] == "timeout"
    assert attempts_2[1]["provider_status"] == "success"
    assert by_which[2]["retry_count"] == 1

    assert len(by_which[1]["request_attempts"]) == 1
    assert len(by_which[3]["request_attempts"]) == 1

    # call 3 started last (highest call_sequence) but persisted first.
    assert by_which[3]["call_sequence"] > by_which[1]["call_sequence"]
    assert by_which[3]["persist_sequence"] < by_which[1]["persist_sequence"]

    persist_sequences = sorted(r["persist_sequence"] for r in records)
    assert persist_sequences == [0, 1, 2]  # strictly increasing, no gaps, none lost
    assert session.recorder.verify_integrity().valid

    from comqutor_alpha.llm_runtime.contracts import validate_semantic_call_records

    assert validate_semantic_call_records(records).valid

    # Request-budget counting reflects every real attempt including the
    # retry -- 1 (call 1) + 2 (call 2, timeout + retry) + 1 (call 3) = 4.
    assert gateway.call_count == 4


def test_gateway_exhaustion_logs_only_safe_codes(tmp_path):
    secret = "sk-provider-secret"
    model = _SequenceModel([f"api_key={secret}", f"token={secret}"])
    gateway = _gateway(tmp_path, model)

    result = gateway.invoke_json("alpha_classifier", {}, lambda payload: payload)
    log = (tmp_path / "run1" / "error_logs" / "week2_llm_errors.jsonl").read_text()

    assert result is None
    assert model.calls == 2
    assert secret not in log
    assert "api_key" not in log
    assert "WEEK2_LLM_INVALID_JSON" in log


def test_gateway_enforces_wall_clock_timeout(tmp_path):
    def slow_response():
        time.sleep(0.2)
        return '{"value": 1}'

    model = _SequenceModel([slow_response])
    gateway = _gateway(tmp_path, model, timeout_seconds=0.02, max_retries=0)
    started = time.monotonic()

    result = gateway.invoke_json("alpha_classifier", {}, lambda payload: payload)

    assert result is None
    assert time.monotonic() - started < 0.15
    log = (tmp_path / "run1" / "error_logs" / "week2_llm_errors.jsonl").read_text()
    assert "WEEK2_LLM_TIMEOUT" in log


def test_server_gateway_is_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("COMQUTOR_WEEK2_LLM_ENABLED", raising=False)

    assert build_server_week2_llm_gateway("run1", tmp_path) is None


def test_server_gateway_uses_existing_provider_factory_only_after_opt_in(tmp_path, monkeypatch):
    import tradingagents.llm_clients as llm_clients

    captured = {}
    model = _SequenceModel([])

    class FakeClient:
        def get_llm(self):
            return model

    def fake_factory(**kwargs):
        captured.update(kwargs)
        return FakeClient()

    (tmp_path / "run1").mkdir()
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "1")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_PROVIDER", "fake-provider")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MODEL", "fake-model")
    monkeypatch.setattr(llm_clients, "create_llm_client", fake_factory)

    gateway = build_server_week2_llm_gateway("run1", tmp_path)

    assert gateway is not None
    assert captured["provider"] == "fake-provider"
    assert captured["model"] == "fake-model"
    assert captured["max_retries"] == 0
    assert "api_key" not in captured
    assert "max_tokens" not in captured  # omitted by default -- no behavior change for existing callers


def test_server_gateway_omits_max_tokens_when_not_supplied(tmp_path, monkeypatch):
    """Every existing real caller (never passes max_tokens) keeps its exact
    current behavior -- no output-length cap at the client level."""
    import tradingagents.llm_clients as llm_clients

    captured = {}

    class FakeClient:
        def get_llm(self):
            return _SequenceModel([])

    def fake_factory(**kwargs):
        captured.update(kwargs)
        return FakeClient()

    (tmp_path / "run2").mkdir()
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "1")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_PROVIDER", "fake-provider")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MODEL", "fake-model")
    monkeypatch.setattr(llm_clients, "create_llm_client", fake_factory)

    build_server_week2_llm_gateway("run2", tmp_path)
    assert "max_tokens" not in captured


def test_server_gateway_forwards_max_tokens_to_the_real_client_constructor(tmp_path, monkeypatch):
    """2026-09-30 (fifth follow-up round): an explicit max_tokens must reach
    create_llm_client -- and, through it, a real ChatOpenAI/ChatAnthropic
    instance's own max_tokens field, not just be accepted and dropped."""
    from tradingagents.llm_clients.factory import create_llm_client as real_create_llm_client

    (tmp_path / "run3").mkdir()
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "1")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_PROVIDER", "openai")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MODEL", "gpt-5.5")

    gateway = build_server_week2_llm_gateway("run3", tmp_path, max_tokens=200)
    assert gateway is not None
    real_model = real_create_llm_client(provider="openai", model="gpt-5.5", max_tokens=200, api_key="placeholder").get_llm()
    assert real_model.max_tokens == 200
    # gateway's own underlying model (constructed via the SAME real factory,
    # same kwargs) has the identical real field set.
    assert gateway._model.max_tokens == 200


def test_server_gateway_deepseek_max_tokens_reaches_real_serialized_request(
    tmp_path, monkeypatch
):
    """2026-10-01 (DeepSeek max_tokens/max_completion_tokens compatibility
    fix): the prior test above only confirmed the real ChatOpenAI object's
    own ``max_tokens`` attribute was set -- it never inspected the actual
    HTTP JSON body sent to the Provider. The real
    t3live_20261001T014648Z_1fb9c9d5 execution's diagnostic found that
    attribute-level check was insufficient: langchain_openai's own base
    class unconditionally renames ``max_tokens`` -> ``max_completion_tokens``
    in the serialized request for EVERY model, and DeepSeek's real API does
    not recognize that name. This test drives a call through the real
    driver-facing surface (build_server_week2_llm_gateway ->
    Week2LLMGateway.invoke_json -> the real DeepSeekChatOpenAI instance),
    with only the httpx transport swapped for a request-capturing
    MockTransport, and asserts on the actual serialized JSON body -- proving
    the field-name fix reaches production code, not just the one-off ad-hoc
    script used to first discover and fix it. This does NOT verify
    DeepSeek's real server-side enforcement of the value (no live Provider
    call is made here)."""
    import httpx

    import tradingagents.llm_clients as llm_clients
    from tradingagents.llm_clients.factory import create_llm_client as real_create_llm_client

    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test-fixed",
                "object": "chat.completion",
                "created": 0,
                "model": "deepseek-v4-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": '{"value": 9}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    mock_http_client = httpx.Client(transport=httpx.MockTransport(handler))

    def wrapped_factory(**kwargs):
        # Only the transport is swapped -- every other kwarg (provider,
        # model, max_tokens, max_retries, timeout, ...) is exactly what the
        # real build_server_week2_llm_gateway would have passed.
        kwargs["http_client"] = mock_http_client
        return real_create_llm_client(**kwargs)

    monkeypatch.setattr(llm_clients, "create_llm_client", wrapped_factory)
    (tmp_path / "run_deepseek_fix").mkdir()
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "1")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MODEL", "deepseek-v4-flash")

    gateway = build_server_week2_llm_gateway("run_deepseek_fix", tmp_path, max_tokens=200)
    assert gateway is not None

    # Same production call surface the real evaluation driver uses -- request
    # limit (max_calls) and retry control (max_retries) are the gateway's own
    # real, unmodified defaults, not bypassed for this test.
    result = gateway.invoke_json(
        "alpha_classifier", {"allowed_alpha_ids": ["A101"]}, lambda payload: payload["value"]
    )

    assert result == 9
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["body"]["max_tokens"] == 200
    assert "max_completion_tokens" not in captured["body"]
    # The retry/budget controls are untouched by this fix -- one real
    # request was made, one call was reserved against the budget.
    assert gateway.call_count == 1


def test_semantic_call_record_captures_sanitized_request_control_and_provider_response(
    tmp_path, monkeypatch
):
    """2026-10-01 (Task 3 of the DeepSeek compatibility round): the existing
    SemanticCallRecord mechanism (not a new, separate logging system) now
    additively captures sanitized request-control parameters (endpoint,
    request model name, the actual serialized token-cap field name/value)
    and Provider response metadata (its own request_id, returned model
    name, raw usage) -- through the SAME real gateway -> real DeepSeek
    client -> MockTransport path as the test above, this time with a real
    SemanticRuntimeSession attached so the persisted record can be read
    back and checked field-by-field. No auth header or credential is ever
    captured (nothing here is sourced from them)."""
    import httpx

    import tradingagents.llm_clients as llm_clients
    from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
    from tradingagents.llm_clients.factory import create_llm_client as real_create_llm_client

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-provider-req-id-123",
                "object": "chat.completion",
                "created": 0,
                "model": "deepseek-v4-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": '{"value": 3}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 7,
                    "total_tokens": 27,
                    "prompt_tokens_details": {"cached_tokens": 0},
                },
            },
        )

    mock_http_client = httpx.Client(transport=httpx.MockTransport(handler))

    def wrapped_factory(**kwargs):
        kwargs["http_client"] = mock_http_client
        return real_create_llm_client(**kwargs)

    monkeypatch.setattr(llm_clients, "create_llm_client", wrapped_factory)
    run_dir = tmp_path / "run_request_control"
    run_dir.mkdir()
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "1")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MODEL", "deepseek-v4-flash")

    gateway = build_server_week2_llm_gateway("run_request_control", tmp_path, max_tokens=200)
    assert gateway is not None
    session = SemanticRuntimeSession(
        run_id="run_request_control",
        output_directory=run_dir,
        execution_mode="test",
        provider="deepseek",
        model="deepseek-v4-flash",
    )
    gateway.attach_semantic_runtime(session)

    result = gateway.invoke_json(
        "alpha_classifier", {"allowed_alpha_ids": ["A101"]}, lambda payload: payload["value"]
    )
    assert result == 3

    records = [
        json.loads(line)
        for line in session.recorder.calls_path.read_text().splitlines()
        if line.strip()
    ]
    assert len(records) == 1
    record = records[0]

    request_control = record["request_control"]
    assert request_control["endpoint"] == "https://api.deepseek.com"
    assert request_control["request_model"] == "deepseek-v4-flash"
    assert request_control["max_tokens_field"] == "max_tokens"
    assert request_control["max_tokens_value"] == 200

    provider_response = record["provider_response"]
    assert provider_response["provider_request_id"] == "chatcmpl-provider-req-id-123"
    assert provider_response["response_model"] == "deepseek-v4-flash"
    assert provider_response["finish_reason"] == "stop"
    # The raw usage object, not the already-trimmed three-field token_usage
    # summary -- retains provider-specific sub-fields like
    # prompt_tokens_details that the normalized summary discards.
    assert provider_response["raw_usage"]["prompt_tokens"] == 20
    assert provider_response["raw_usage"]["completion_tokens"] == 7
    assert "prompt_tokens_details" in provider_response["raw_usage"]

    # No auth header or credential anywhere in the persisted record.
    serialized = json.dumps(record)
    assert "api_key" not in serialized.lower()
    assert "authorization" not in serialized.lower()
    assert "placeholder" not in serialized  # the test's own dummy api_key value


def test_alpha_classifier_v7_prompt_reaches_the_real_serialized_request(tmp_path, monkeypatch):
    """2026-10-01 (AI-review comparison round): the v7 alpha_classifier
    prompt edit must actually reach the real outgoing request through the
    same real driver -> Gateway -> DeepSeek-client -> MockTransport path
    already used to verify the max_tokens fix -- not just exist as a Python
    string. Confirms wiring only; this does NOT claim any semantic-accuracy
    improvement (that requires a real Provider call, not performed here)."""
    import httpx

    import tradingagents.llm_clients as llm_clients
    from tradingagents.llm_clients.factory import create_llm_client as real_create_llm_client

    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-v7-wiring-check",
                "object": "chat.completion",
                "created": 0,
                "model": "deepseek-v4-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": '{"decision": "none", "selected_alpha_id": null}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    mock_http_client = httpx.Client(transport=httpx.MockTransport(handler))

    def wrapped_factory(**kwargs):
        kwargs["http_client"] = mock_http_client
        return real_create_llm_client(**kwargs)

    monkeypatch.setattr(llm_clients, "create_llm_client", wrapped_factory)
    (tmp_path / "run_v7_wiring").mkdir()
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "1")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MODEL", "deepseek-v4-flash")

    gateway = build_server_week2_llm_gateway("run_v7_wiring", tmp_path)
    assert gateway is not None

    result = gateway.invoke_json(
        "alpha_classifier", {"allowed_alpha_ids": ["A304"]}, lambda payload: payload
    )

    assert result == {"decision": "none", "selected_alpha_id": None}
    sent_prompt = captured["body"]["messages"][0]["content"]
    # The real, serialized outgoing prompt contains v7's new content...
    assert "First identify what the Evidence's own words actually assert" in sent_prompt
    assert "RELATIVE TO FUNDAMENTALS" in sent_prompt
    assert "tie-breaking preference" in sent_prompt
    assert "mechanical, structural flow tied to a specific event" in sent_prompt
    # ...and never the superseded v6 opening sentence.
    assert "Classify the Evidence against the FULL supplied Alpha taxonomy" not in sent_prompt
    # No real sample_id or frozen-pool claim text leaked into the prompt.
    assert "gold-final" not in sent_prompt
    assert "prod-run-" not in sent_prompt


def test_task_model_overrides_routes_exactly_the_named_task_to_its_own_model(tmp_path):
    """2026-10-01 (NVDA Fresh Run request-shape budget task): a per-task
    model override must be used for exactly the named task and never bleed
    into any other task sharing the same gateway -- unit-level proof that
    Week2LLMGateway._resolve_task_model picks the override dict entry by
    task name, independent of the real client/env-var wiring tested below."""
    base_model = _SequenceModel(['{"value": "base"}'])
    override_model = _SequenceModel(['{"value": "override"}'])
    (tmp_path / "run1").mkdir(exist_ok=True)
    gateway = Week2LLMGateway(
        base_model,
        run_id="run1",
        output_root=tmp_path,
        task_model_overrides={"alpha_classifier": override_model},
    )

    # Real production alpha_classifier calls (comqutor_alpha.structure_
    # engine.alpha_mapper.map_claim_to_alpha) use invoke_json_with_trace
    # directly, never the semantic_runtime-less invoke_json()/
    # _invoke_json_legacy() path -- called the same way here so this test
    # exercises the actual code path a real run takes, not a different one.
    alpha_invocation = gateway.invoke_json_with_trace(
        "alpha_classifier", {}, lambda payload: payload["value"]
    )
    other_invocation = gateway.invoke_json_with_trace(
        "claim_batch_enrichment", {}, lambda payload: payload["value"]
    )

    assert alpha_invocation.validated_output == "override"
    assert other_invocation.validated_output == "base"
    assert override_model.calls == 1
    assert base_model.calls == 1


def test_alpha_classifier_max_tokens_env_var_reaches_only_the_alpha_classifier_real_request(
    tmp_path, monkeypatch
):
    """2026-10-01 (NVDA Fresh Run request-shape budget task): the real,
    enforced Alpha-classification single-call output cap must reach the
    real serialized request for alpha_classifier specifically, and must
    never change claim_batch_enrichment's own request (no shared-client
    max_tokens was configured here) -- confirmed through the same real
    driver -> Gateway -> DeepSeek-client -> MockTransport path already used
    for the v7 prompt wiring check above. Confirms wiring only; no real
    Provider call is made and no semantic-accuracy claim is implied."""
    import httpx

    import tradingagents.llm_clients as llm_clients
    from tradingagents.llm_clients.factory import create_llm_client as real_create_llm_client

    captured_bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-alpha-max-tokens-wiring-check",
                "object": "chat.completion",
                "created": 0,
                "model": "deepseek-v4-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": '{"decision": "none", "selected_alpha_id": null}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    mock_http_client = httpx.Client(transport=httpx.MockTransport(handler))

    def wrapped_factory(**kwargs):
        kwargs["http_client"] = mock_http_client
        return real_create_llm_client(**kwargs)

    monkeypatch.setattr(llm_clients, "create_llm_client", wrapped_factory)
    (tmp_path / "run_alpha_max_tokens_wiring").mkdir()
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "1")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("COMQUTOR_WEEK2_ALPHA_CLASSIFIER_MAX_TOKENS", "4096")

    gateway = build_server_week2_llm_gateway("run_alpha_max_tokens_wiring", tmp_path)
    assert gateway is not None

    # Real production alpha_classifier calls use invoke_json_with_trace
    # directly (comqutor_alpha.structure_engine.alpha_mapper.map_claim_to_
    # alpha) -- called the same way here, not via invoke_json(), whose
    # semantic_runtime-less fallback (_invoke_json_legacy) does not consult
    # task_model_overrides and would make this test pass even if the real
    # wiring were broken.
    gateway.invoke_json_with_trace(
        "claim_batch_enrichment", {"segments": []}, lambda payload: payload
    )
    gateway.invoke_json_with_trace(
        "alpha_classifier", {"allowed_alpha_ids": ["A304"]}, lambda payload: payload
    )

    assert len(captured_bodies) == 2
    enrichment_body, alpha_body = captured_bodies
    assert "max_tokens" not in enrichment_body
    assert "max_completion_tokens" not in enrichment_body
    assert alpha_body.get("max_tokens") == 4096
    assert "max_completion_tokens" not in alpha_body


def test_content_support_max_tokens_env_var_reaches_only_the_content_support_real_request(
    tmp_path, monkeypatch
):
    """2026-10-06 (AMD Fresh Run production-wiring task): mirrors the
    alpha_classifier test immediately above, for the new, equally additive
    COMQUTOR_WEEK2_CONTENT_SUPPORT_MAX_TOKENS override -- the real,
    enforced content-support-verification single-call output cap must
    reach the real serialized request for content_support_verification
    specifically, and must never change claim_batch_enrichment's own
    request. Confirms wiring only; no real Provider call is made."""
    import httpx

    import tradingagents.llm_clients as llm_clients
    from tradingagents.llm_clients.factory import create_llm_client as real_create_llm_client

    captured_bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-content-support-max-tokens-wiring-check",
                "object": "chat.completion",
                "created": 0,
                "model": "deepseek-v4-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": '{"items": []}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    mock_http_client = httpx.Client(transport=httpx.MockTransport(handler))

    def wrapped_factory(**kwargs):
        kwargs["http_client"] = mock_http_client
        return real_create_llm_client(**kwargs)

    monkeypatch.setattr(llm_clients, "create_llm_client", wrapped_factory)
    (tmp_path / "run_content_support_max_tokens_wiring").mkdir()
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "1")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("COMQUTOR_WEEK2_CONTENT_SUPPORT_MAX_TOKENS", "16384")

    gateway = build_server_week2_llm_gateway("run_content_support_max_tokens_wiring", tmp_path)
    assert gateway is not None

    gateway.invoke_json_with_trace(
        "claim_batch_enrichment", {"segments": []}, lambda payload: payload
    )
    gateway.invoke_json_with_trace(
        "content_support_verification", {"items": []}, lambda payload: payload
    )

    assert len(captured_bodies) == 2
    enrichment_body, content_support_body = captured_bodies
    assert "max_tokens" not in enrichment_body
    assert content_support_body.get("max_tokens") == 16384
    assert "max_completion_tokens" not in content_support_body


def test_request_audit_enabled_via_env_var_reaches_the_real_gateway(tmp_path, monkeypatch):
    """2026-10-06 (AMD Fresh Run production-wiring task): run_research_
    request's own internal call to build_server_week2_llm_gateway(run_id,
    output_root) never passes enable_request_response_audit explicitly
    (it cannot -- run_id is only known after the real TradingAgents graph
    has already run). COMQUTOR_WEEK2_LLM_ENABLE_REQUEST_AUDIT is the real
    env-var path that must reach the gateway through that exact call
    shape -- confirmed here by calling the function the same way (no
    enable_request_response_audit keyword at all), zero real network
    (week2_llm_enabled() gate and provider config let gateway construction
    get far enough to inspect _audit_enabled; no .invoke() is ever called)."""
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "1")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixed-test-key-not-real")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLE_REQUEST_AUDIT", "1")

    gateway = build_server_week2_llm_gateway("run_audit_env_var_wiring", tmp_path)
    assert gateway is not None
    assert gateway._audit_enabled is True


def test_request_audit_disabled_by_default_no_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "1")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixed-test-key-not-real")
    monkeypatch.delenv("COMQUTOR_WEEK2_LLM_ENABLE_REQUEST_AUDIT", raising=False)

    gateway = build_server_week2_llm_gateway("run_audit_env_var_default", tmp_path)
    assert gateway is not None
    assert gateway._audit_enabled is False


def test_gateway_call_budget_prevents_unbounded_retries(tmp_path):
    model = _SequenceModel(["not json", '{"value": 2}'])
    gateway = _gateway(tmp_path, model, max_calls=1)

    result = gateway.invoke_json("alpha_classifier", {}, lambda payload: payload)
    log = (tmp_path / "run1" / "error_logs" / "week2_llm_errors.jsonl").read_text()

    assert result is None
    assert model.calls == 1
    assert "WEEK2_LLM_CALL_BUDGET_EXHAUSTED" in log


def test_structured_adapter_uses_valid_llm_claims(tmp_path):
    # Complete Claim Coverage Sprint: the LLM only *enriches* an already-
    # segmented claim -- it must echo the deterministic segment's own
    # claim/evidence/source_section back verbatim, keyed by segment_id.
    raw_text = "AI demand is rising because GPU orders increased 20%."
    raw_id = "run1:news_agent:news_report"
    response = {
        "claims": [
            {
                "segment_id": f"{raw_id}:segment:0",
                "claim": raw_text,
                "evidence": raw_text,
                "entities": ["AI", "GPU"],
                "factors": ["AI Demand", "GPU Demand"],
                "direction": "positive",
                "confidence": 0.9,
                "source_section": None,
                # T1 source-linking chain, 2026-09-28: cited_source_id is a
                # REQUIRED (nullable) field in the real enrichment schema
                # (_LLM_BATCH_ENRICHMENT_REQUIRED_FIELDS) -- omitting it
                # made this "valid" response actually fail strict-schema
                # validation and silently fall back to
                # deterministic_splitter, defeating this test's own stated
                # purpose of exercising the LLM path.
                "cited_source_id": None,
            }
        ]
    }
    gateway = _gateway(tmp_path, _SequenceModel([json.dumps(response)]), max_retries=0)

    records = adapt_raw_agent_outputs(
        {"agent_output_id": raw_id, "agent": "news_agent", "raw_output": raw_text},
        "run1",
        "NVDA",
        llm_gateway=gateway,
    )

    assert records[0]["extraction_method"] == "llm_strict_json"
    assert records[0]["claim_id"] == f"{raw_id}:claim:1"
    assert records[0]["source_agent_output_id"] == raw_id
    assert records[0]["evidence"] == raw_text
    assert records[0]["direction"] == "positive"


def test_structured_adapter_falls_back_after_invalid_llm_fields(tmp_path):
    raw_text = "AI demand drives GPU demand."
    invalid = json.dumps(
        {
            "claims": [
                {
                    "segment_id": "whatever:segment:0",
                    "claim": raw_text,
                    "evidence": raw_text,
                    "entities": [],
                    "factors": ["AI Demand", "GPU Demand"],
                    "direction": "positive",
                    "confidence": 4,
                    "source_section": None,
                }
            ]
        }
    )
    model = _SequenceModel([invalid, invalid])
    gateway = _gateway(tmp_path, model)

    records = adapt_raw_agent_outputs(
        {"agent": "news_agent", "raw_output": raw_text},
        "run1",
        "NVDA",
        llm_gateway=gateway,
    )

    assert model.calls == 2
    assert records[0]["extraction_method"] == "deterministic_splitter"
    assert records[0]["claim"] == raw_text


def test_mapper_applies_a_valid_llm_selection(tmp_path):
    """Alpha Mapper authority migration: a valid LLM select unconditionally
    becomes the semantic matched_alpha (classifier status "llm_selected",
    not the pre-migration "applied"). See
    tests/test_alpha_mapper_llm_authority.py for the full acceptance suite,
    including the case where the LLM's choice is entirely absent from
    deterministic Tier-1 candidates."""
    model = _SequenceModel(
        [json.dumps({"decision": "select", "selected_alpha_id": "A101"})]
    )
    gateway = _gateway(tmp_path, model, max_retries=0)
    record = _record(
        "AI training demand is rising, but rich valuation creates downside risk.",
        ["AI Demand", "Valuation Risk"],
    )

    result = map_claim_to_alpha(record, llm_gateway=gateway)

    assert result["match_status"] == "matched"
    assert result["matched_alpha"] == "A101"
    assert result["classifier"]["status"] == "llm_selected"
    assert result["alpha_match_method"] == "llm"


def test_mapper_invalid_llm_candidate_falls_back_without_response_leak(tmp_path):
    invalid = json.dumps(
        {
            "decision": "select",
            "selected_alpha_id": "A999",
            "hidden_reasoning": "provider-private-text",
        }
    )
    gateway = _gateway(tmp_path, _SequenceModel([invalid, invalid]))
    record = _record(
        "AI training demand is rising, but rich valuation creates downside risk.",
        ["AI Demand", "Valuation Risk"],
    )

    result = map_claim_to_alpha(record, llm_gateway=gateway)

    # Pure-LLM Alpha semantic authority: an unrecognized-shape/unknown-Alpha
    # response is an operational failure (unavailable), never a
    # deterministic fallback -- see tests/test_alpha_mapper_llm_authority.py.
    assert result["match_status"] == "unavailable"
    assert result["matched_alpha"] is None
    assert result["classifier"]["status"] == "invalid_output"
    assert "provider-private-text" not in json.dumps(result)
    assert "A999" not in json.dumps(result)


def test_structure_extractor_uses_validated_llm_edge(tmp_path):
    response = {
        "edges": [
            {
                "source_factor": "AI Demand",
                "target_factor": "GPU Demand",
                "edge_type": "causal",
                "assertion_status": "asserted",
                "confidence": 0.91,
            }
        ]
    }
    gateway = _gateway(tmp_path, _SequenceModel([json.dumps(response)]), max_retries=0)

    payload = extract_structures_from_records(
        [_record("AI demand drives GPU demand.", ["AI Demand", "GPU Demand"])],
        llm_gateway=gateway,
    )

    assert len(payload["edges"]) == 1
    assert payload["edges"][0]["extraction_method"] == "llm_strict_json"
    assert payload["edges"][0]["evidence"] == "AI demand drives GPU demand."


def test_structure_extractor_invalid_llm_edge_uses_deterministic_fallback(tmp_path):
    invalid = json.dumps(
        {
            "edges": [
                {
                    "source_factor": "Invented Factor",
                    "target_factor": "GPU Demand",
                    "edge_type": "causal",
                    "assertion_status": "asserted",
                    "confidence": 0.9,
                }
            ]
        }
    )
    gateway = _gateway(tmp_path, _SequenceModel([invalid, invalid]))

    payload = extract_structures_from_records(
        [_record("AI demand drives GPU demand.", ["AI Demand", "GPU Demand"])],
        llm_gateway=gateway,
    )

    assert len(payload["edges"]) == 1
    assert payload["edges"][0]["extraction_method"] == "deterministic_rules"
    assert payload["metadata"]["deterministic_edge_count"] == 1


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("COMQUTOR_RUN_WEEK2_PROVIDER_SMOKE") != "1",
    reason="set COMQUTOR_RUN_WEEK2_PROVIDER_SMOKE=1 to allow three provider calls",
)
def test_explicit_low_cost_provider_smoke(tmp_path, monkeypatch):
    """Exercise the three Week 2 LLM tasks with a three-call hard limit."""
    load_dotenv()
    from tradingagents.llm_clients.api_key_env import get_api_key_env

    provider = (
        os.getenv("COMQUTOR_WEEK2_LLM_PROVIDER")
        or os.getenv("TRADINGAGENTS_LLM_PROVIDER")
        or ""
    ).strip()
    model = (
        os.getenv("COMQUTOR_WEEK2_LLM_MODEL")
        or os.getenv("TRADINGAGENTS_QUICK_THINK_LLM")
        or ""
    ).strip()
    key_env = get_api_key_env(provider)
    if not provider or not model or not key_env or not os.getenv(key_env):
        pytest.skip("configured API-key-backed provider credentials are unavailable")

    run_id = "provider-smoke"
    (tmp_path / run_id).mkdir()
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "1")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MAX_RETRIES", "0")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MAX_CALLS", "3")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS", "30")
    gateway = build_server_week2_llm_gateway(run_id, tmp_path)
    assert gateway is not None

    raw_text = "AI demand is rising because GPU demand is increasing."
    records = adapt_raw_agent_outputs(
        {
            "agent_output_id": f"{run_id}:news_agent:news_report",
            "agent": "news_agent",
            "raw_output": raw_text,
        },
        run_id,
        "NVDA",
        llm_gateway=gateway,
    )
    assert records and records[0]["extraction_method"] == "llm_strict_json"

    classification = map_claim_to_alpha(
        _record(
            "AI demand is strong, but rich valuation creates downside risk.",
            ["AI Demand", "Valuation Risk"],
        ),
        llm_gateway=gateway,
    )
    assert classification["classifier"]["used"] is True
    assert classification["match_status"] == "ambiguous" or (
        classification["match_status"] == "matched"
        and classification["matched_alpha"] in classification["plausible_alphas"]
    )

    structures = extract_structures_from_records(
        [_record("AI demand drives GPU demand.", ["AI Demand", "GPU Demand"])],
        llm_gateway=gateway,
    )
    assert structures["metadata"]["llm_edge_count"] >= 1
    assert gateway.call_count == 3
