"""2026-10-06 (round 13): proves TRUE concurrent audit support -- the
contextvars-based per-attempt identity (week2_llm.py's own module-level
_current_audit_attempt ContextVar), explicitly propagated across
call_with_timeout's nested executor boundary via contextvars.copy_context()
+ ctx.run(), replacing the earlier single shared self._pending_audit_attempt
dict design that could only ever track one in-flight attempt at a time and
raised WEEK2_LLM_AUDIT_CONCURRENT_ATTEMPT for any second concurrent caller.

Every test here goes through the REAL build_server_week2_llm_gateway
construction (the same real tradingagents.llm_clients.create_llm_client
factory production uses, never monkeypatched) -- only the bottom-most
httpx transport is faked, per this round's explicit requirement. Controlled
synchronization (threading.Barrier) forces genuine, deterministic overlap --
never inferred from timing alone.

Covers required scenarios 1-2-3-4-5-6-7 of the round-13 instruction (#8,
the full-973-claim recovery-script integration test, is covered separately
in test_recover_alpha_classification scaling work):
  1. four-way real overlap, out-of-order completion, correct identity
  2. identical claim text does not cause identity confusion
  3. mixed task types share one gateway concurrently
  4. one HTTP error + one timeout + one success, independently resolved
  5. a late response arriving after a newer request does not corrupt it
  6. request-audit-save-failure (zero send) / response-audit-save-failure
     (in-flight calls still finalize; only future attempts are refused)
  7. hard call-cap and 0/0 retries still enforced under concurrency
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import httpx
import pytest

import comqutor_alpha.structure_engine.week2_llm as week2_llm
from comqutor_alpha.structure_engine.week2_llm import build_server_week2_llm_gateway


def _success_response(payload: dict) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-fixed", "object": "chat.completion", "created": 0,
            "model": "deepseek-v4-flash",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": json.dumps(payload)}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
    )


def _error_response(status: int = 500) -> httpx.Response:
    return httpx.Response(status, json={"error": {"message": "fake provider error", "type": "server_error"}})


def _build_real_gateway(run_id: str, tmp_path, monkeypatch, handler) -> Any:
    """Matches the real production construction path exactly: real
    create_llm_client factory, real Week2LLMGateway, real AuditingTransport
    -- only httpx.MockTransport stands in for the actual network."""
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "1")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MAX_RETRIES", "0")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixed-test-key-not-real")

    gateway = build_server_week2_llm_gateway(
        run_id, tmp_path,
        enable_request_response_audit=True,
        _base_transport_for_testing=httpx.MockTransport(handler),
    )
    assert gateway is not None
    assert gateway._audit_enabled is True

    from comqutor_alpha.llm_runtime.cache import InMemoryLLMResponseCache
    from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession

    (tmp_path / run_id).mkdir(exist_ok=True)
    semantic_runtime = SemanticRuntimeSession(
        run_id=run_id, output_directory=str(tmp_path / run_id), execution_mode="live",
        provider=gateway.provider, model=gateway.model_name, cache=InMemoryLLMResponseCache(),
    )
    gateway.attach_semantic_runtime(semantic_runtime)
    return gateway


def _read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _req_audit_path(tmp_path, run_id):
    return tmp_path / run_id / "error_logs" / "week2_llm_provider_request_audit.jsonl"


def _resp_audit_path(tmp_path, run_id):
    return tmp_path / run_id / "error_logs" / "week2_llm_provider_response_audit.jsonl"


# ---------------------------------------------------------------------------
# 1. Four-way real overlap, out-of-order completion, correct identity
# ---------------------------------------------------------------------------

def test_four_way_real_overlap_out_of_order_completion_correct_identity(tmp_path, monkeypatch):
    barrier = threading.Barrier(4, timeout=5.0)
    # Submitted in order A,B,C,D below but delays are reversed, so real
    # completion order is D,C,B,A -- proven out-of-order, not inferred.
    delays = {"claim-A": 0.4, "claim-B": 0.3, "claim-C": 0.2, "claim-D": 0.1}
    completion_order: list[str] = []
    order_lock = threading.Lock()

    def handler(request: httpx.Request) -> httpx.Response:
        barrier.wait()  # proves all 4 requests are genuinely in-flight simultaneously
        body = json.loads(request.content)
        prompt = body["messages"][0]["content"]
        for marker, delay in delays.items():
            if marker in prompt:
                time.sleep(delay)
                with order_lock:
                    completion_order.append(marker)
                return _success_response({"claim_id": marker, "decision": "none"})
        raise AssertionError("unrecognized prompt")

    gateway = _build_real_gateway("t1run", tmp_path, monkeypatch, handler)

    results: dict[str, Any] = {}
    lock = threading.Lock()

    def worker(claim_id: str):
        invocation = gateway.invoke_json_with_trace("alpha_classifier", {"claim_id": claim_id}, lambda p: p)
        with lock:
            results[claim_id] = invocation

    threads = [threading.Thread(target=worker, args=(cid,)) for cid in delays]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert completion_order == ["claim-D", "claim-C", "claim-B", "claim-A"], (
        f"expected reversed, out-of-order completion, got {completion_order}"
    )
    assert len(results) == 4
    for claim_id, invocation in results.items():
        assert invocation.validation_accepted, f"{claim_id} did not get a valid real response"
        assert invocation.validated_output["claim_id"] == claim_id, (
            f"identity mismatch: {claim_id}'s own invocation returned "
            f"validated_output for {invocation.validated_output['claim_id']!r} instead"
        )

    req_audit = _read_jsonl(_req_audit_path(tmp_path, "t1run"))
    resp_audit = _read_jsonl(_resp_audit_path(tmp_path, "t1run"))
    assert len(req_audit) == 4
    assert len(resp_audit) == 4
    req_by_attempt = {r["attempt_id"]: r for r in req_audit}
    assert len(req_by_attempt) == 4, "attempt_ids must all be distinct, never reused across concurrent calls"
    for resp in resp_audit:
        assert resp["attempt_id"] in req_by_attempt
        req = req_by_attempt[resp["attempt_id"]]
        req_claim = req["claim_ids"][0]
        resp_body = json.loads(resp["body"])
        resp_claim = json.loads(resp_body["choices"][0]["message"]["content"])["claim_id"]
        assert resp_claim == req_claim, (
            f"attempt_id {resp['attempt_id']} bound mismatched claims: "
            f"request claim_ids={req['claim_ids']!r}, response claim_id={resp_claim!r}"
        )


# ---------------------------------------------------------------------------
# 2. Identical claim text does not cause identity confusion
# ---------------------------------------------------------------------------

def test_identical_claim_text_does_not_cause_identity_confusion(tmp_path, monkeypatch):
    barrier = threading.Barrier(2, timeout=5.0)
    call_counter = {"n": 0}
    counter_lock = threading.Lock()

    def handler(request: httpx.Request) -> httpx.Response:
        barrier.wait()
        with counter_lock:
            call_counter["n"] += 1
            arrival = call_counter["n"]
        return _success_response({"decision": "none", "arrival_order": arrival})

    gateway = _build_real_gateway("t2run", tmp_path, monkeypatch, handler)

    results: dict[str, Any] = {}
    lock = threading.Lock()

    def worker(claim_id: str):
        invocation = gateway.invoke_json_with_trace(
            "alpha_classifier", {"claim_id": claim_id, "text": "identical text for both claims"}, lambda p: p
        )
        with lock:
            results[claim_id] = invocation

    t1 = threading.Thread(target=worker, args=("claim-X",))
    t2 = threading.Thread(target=worker, args=("claim-Y",))
    t1.start(); t2.start()
    t1.join(timeout=10); t2.join(timeout=10)

    assert results["claim-X"].validation_accepted
    assert results["claim-Y"].validation_accepted
    orders = {results["claim-X"].validated_output["arrival_order"], results["claim-Y"].validated_output["arrival_order"]}
    assert orders == {1, 2}, "each identical-text call must get its own distinct real response, never a duplicate"

    req_audit = _read_jsonl(_req_audit_path(tmp_path, "t2run"))
    assert len(req_audit) == 2
    claim_ids_seen = {r["claim_ids"][0] for r in req_audit}
    assert claim_ids_seen == {"claim-X", "claim-Y"}, (
        "audit must attribute each request to its OWN claim_id via attempt_id, "
        "never by matching identical prompt text"
    )


# ---------------------------------------------------------------------------
# 3. Mixed task types share one gateway concurrently
# ---------------------------------------------------------------------------

def test_mixed_task_types_share_gateway_concurrently(tmp_path, monkeypatch):
    barrier = threading.Barrier(2, timeout=5.0)

    def handler(request: httpx.Request) -> httpx.Response:
        barrier.wait()  # proves genuine overlap across two DIFFERENT tasks
        body = json.loads(request.content)
        prompt = body["messages"][0]["content"]
        if "alpha-marker" in prompt:
            return _success_response({"decision": "none", "seen_task": "alpha_classifier"})
        return _success_response({"items": [], "seen_task": "content_support_verification"})

    gateway = _build_real_gateway("t3run", tmp_path, monkeypatch, handler)

    results: dict[str, Any] = {}
    lock = threading.Lock()

    def worker_alpha():
        inv = gateway.invoke_json_with_trace("alpha_classifier", {"claim_id": "alpha-marker"}, lambda p: p)
        with lock:
            results["alpha"] = inv

    def worker_content():
        inv = gateway.invoke_json_with_trace("content_support_verification", {"claim_id": "content-marker"}, lambda p: p)
        with lock:
            results["content"] = inv

    t1 = threading.Thread(target=worker_alpha)
    t2 = threading.Thread(target=worker_content)
    t1.start(); t2.start()
    t1.join(timeout=10); t2.join(timeout=10)

    assert results["alpha"].validation_accepted
    assert results["content"].validation_accepted
    assert results["alpha"].validated_output["seen_task"] == "alpha_classifier"
    assert results["content"].validated_output["seen_task"] == "content_support_verification"

    req_audit = _read_jsonl(_req_audit_path(tmp_path, "t3run"))
    tasks_recorded = {r["task"] for r in req_audit}
    assert tasks_recorded == {"alpha_classifier", "content_support_verification"}, (
        "no single-pending-attempt collision: both tasks' own requests must be independently audited"
    )


# ---------------------------------------------------------------------------
# 4. One HTTP error + one timeout + one success, independently resolved
# ---------------------------------------------------------------------------

def test_one_http_error_one_timeout_one_success_independently_resolved(tmp_path, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        prompt = body["messages"][0]["content"]
        if "will-error" in prompt:
            return _error_response(500)
        if "will-timeout" in prompt:
            time.sleep(1.2)
            return _success_response({"decision": "none", "which": "will-timeout"})
        return _success_response({"decision": "none", "which": "will-succeed"})

    gateway = _build_real_gateway("t4run", tmp_path, monkeypatch, handler)
    gateway.timeout_seconds = 0.3  # plain attribute set, bypasses the >=1.0s env-var bound intentionally

    results: dict[str, Any] = {}
    lock = threading.Lock()

    def worker(name, marker):
        inv = gateway.invoke_json_with_trace("alpha_classifier", {"claim_id": marker}, lambda p: p)
        with lock:
            results[name] = inv

    threads = [
        threading.Thread(target=worker, args=("error", "will-error")),
        threading.Thread(target=worker, args=("timeout", "will-timeout")),
        threading.Thread(target=worker, args=("success", "will-succeed")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert results["success"].validation_accepted is True
    assert results["success"].provider_status == "success"
    assert results["error"].validation_accepted is False
    assert results["error"].provider_status == "provider_error"
    assert results["timeout"].validation_accepted is False
    assert results["timeout"].provider_status == "timeout"

    # Let the late "will-timeout" background call actually finish before
    # proving the gateway is not left in a stuck/pending state.
    time.sleep(1.2)
    final = gateway.invoke_json_with_trace("alpha_classifier", {"claim_id": "will-succeed-again"}, lambda p: p)
    assert final.validation_accepted is True

    req_audit = _read_jsonl(_req_audit_path(tmp_path, "t4run"))
    resp_audit = _read_jsonl(_resp_audit_path(tmp_path, "t4run"))
    # Every REQUEST that was actually sent (error, timeout, success, final) is audited.
    assert len(req_audit) == 4
    # Every one of those got a RESPONSE recorded too -- including the error's
    # 500 response and the timeout's own (late, but eventually real) response.
    assert len(resp_audit) == 4
    status_codes = sorted(r["status_code"] for r in resp_audit)
    assert status_codes == [200, 200, 200, 500]


# ---------------------------------------------------------------------------
# 5. A late response after a newer request started does not corrupt it
# ---------------------------------------------------------------------------

def test_late_response_after_timeout_does_not_corrupt_next_request(tmp_path, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        prompt = body["messages"][0]["content"]
        if "slow-claim" in prompt:
            time.sleep(0.6)  # finishes AFTER the gateway's own short timeout below
            return _success_response({"decision": "none", "which": "slow-claim"})
        return _success_response({"decision": "none", "which": "fast-claim"})

    gateway = _build_real_gateway("t5run", tmp_path, monkeypatch, handler)
    gateway.timeout_seconds = 0.1

    slow_invocation = gateway.invoke_json_with_trace("alpha_classifier", {"claim_id": "slow-claim"}, lambda p: p)
    assert slow_invocation.provider_status == "timeout"
    assert slow_invocation.validation_accepted is False

    # Immediately send a new, unrelated request while the slow one's real
    # background thread (its network call) is still genuinely running.
    fast_invocation = gateway.invoke_json_with_trace("alpha_classifier", {"claim_id": "fast-claim"}, lambda p: p)
    assert fast_invocation.validation_accepted is True
    assert fast_invocation.validated_output["which"] == "fast-claim"

    # Let the slow background call actually complete for real.
    time.sleep(0.8)

    req_audit = _read_jsonl(_req_audit_path(tmp_path, "t5run"))
    resp_audit = _read_jsonl(_resp_audit_path(tmp_path, "t5run"))
    assert len(req_audit) == 2
    assert len(resp_audit) == 2  # the late slow-claim response IS still audited, under its own identity

    resp_which = {json.loads(json.loads(r["body"])["choices"][0]["message"]["content"])["which"] for r in resp_audit}
    assert resp_which == {"slow-claim", "fast-claim"}

    slow_attempt_ids = {r["attempt_id"] for r in req_audit if r["claim_ids"] == ["slow-claim"]}
    fast_attempt_ids = {r["attempt_id"] for r in req_audit if r["claim_ids"] == ["fast-claim"]}
    assert slow_attempt_ids.isdisjoint(fast_attempt_ids), (
        "slow-claim's late response must never share an attempt_id with the newer fast-claim request"
    )
    slow_resp_attempt_ids = {r["attempt_id"] for r in resp_audit if "slow-claim" in r["body"]}
    assert slow_resp_attempt_ids == slow_attempt_ids, (
        "the late response audit must bind to slow-claim's OWN original attempt_id, "
        "never the newer fast-claim attempt_id allocated after it"
    )

    # The business result already recorded for the timeout is never
    # retroactively changed by the late real success.
    assert slow_invocation.provider_status == "timeout"
    assert slow_invocation.validation_accepted is False


# ---------------------------------------------------------------------------
# 6. Audit-save-failure: request-save failure means zero send; response-save
#    failure lets the in-flight call finalize but refuses future attempts.
# ---------------------------------------------------------------------------

def test_request_audit_save_failure_means_zero_send_and_blocks_future_calls(tmp_path, monkeypatch):
    send_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        send_count["n"] += 1
        return _success_response({"decision": "none"})

    gateway = _build_real_gateway("t6arun", tmp_path, monkeypatch, handler)

    real_append = week2_llm.append_jsonl_record

    def failing_append(run_id, artifact_path, record, *, output_root=None):
        if artifact_path == week2_llm.PROVIDER_REQUEST_AUDIT_ARTIFACT_PATH:
            raise OSError("simulated disk failure saving request audit")
        return real_append(run_id, artifact_path, record, output_root=output_root)

    monkeypatch.setattr(week2_llm, "append_jsonl_record", failing_append)

    first = gateway.invoke_json_with_trace("alpha_classifier", {"claim_id": "claim-1"}, lambda p: p)
    assert first.provider_status == "audit_unavailable"
    assert send_count["n"] == 0, "the real transport must never be reached when the request audit save fails"
    assert gateway.audit_write_failed is True
    calls_consumed_after_first = gateway.call_count

    second = gateway.invoke_json_with_trace("alpha_classifier", {"claim_id": "claim-2"}, lambda p: p)
    assert second.provider_status == "audit_unavailable"
    assert send_count["n"] == 0, "a second claim must also be refused with zero send once audit_write_failed is set"
    assert gateway.call_count == calls_consumed_after_first, (
        "a claim refused due to audit_write_failed must never consume real call budget "
        "(checked before _reserve_call in invoke_json_with_trace's own loop)"
    )


def test_response_audit_save_failure_finalizes_in_flight_calls_but_blocks_future(tmp_path, monkeypatch):
    barrier = threading.Barrier(2, timeout=5.0)

    def handler(request: httpx.Request) -> httpx.Response:
        barrier.wait()  # proves both "fail" and "ok" are genuinely in-flight together
        body = json.loads(request.content)
        prompt = body["messages"][0]["content"]
        which = "claim-fail" if "claim-fail" in prompt else "claim-ok"
        return _success_response({"decision": "none", "which": which})

    gateway = _build_real_gateway("t6brun", tmp_path, monkeypatch, handler)

    real_append = week2_llm.append_jsonl_record

    def failing_append(run_id, artifact_path, record, *, output_root=None):
        # Response audit records carry no claim_ids (only request records
        # do -- see _persist_response_audit) -- identify "claim-fail"'s own
        # response by its real, literal response body content instead.
        if (
            artifact_path == week2_llm.PROVIDER_RESPONSE_AUDIT_ARTIFACT_PATH
            and "claim-fail" in record.get("body", "")
        ):
            raise OSError("simulated disk failure saving THIS response audit only")
        return real_append(run_id, artifact_path, record, output_root=output_root)

    monkeypatch.setattr(week2_llm, "append_jsonl_record", failing_append)

    results: dict[str, Any] = {}
    lock = threading.Lock()

    def worker(claim_id: str):
        inv = gateway.invoke_json_with_trace("alpha_classifier", {"claim_id": claim_id}, lambda p: p)
        with lock:
            results[claim_id] = inv

    t_fail = threading.Thread(target=worker, args=("claim-fail",))
    t_ok = threading.Thread(target=worker, args=("claim-ok",))
    t_fail.start(); t_ok.start()
    t_fail.join(timeout=10); t_ok.join(timeout=10)

    # Both ALREADY-in-flight calls finalize with their real, correct result --
    # a response-save failure never un-does an already-received Provider answer.
    assert results["claim-fail"].validation_accepted is True
    assert results["claim-fail"].provider_status == "success"
    assert results["claim-ok"].validation_accepted is True
    assert results["claim-ok"].provider_status == "success"

    assert gateway.audit_write_failed is True

    send_count_before_third = len(
        [r for r in _read_jsonl(_req_audit_path(tmp_path, "t6brun"))]
    )
    third = gateway.invoke_json_with_trace("alpha_classifier", {"claim_id": "claim-after"}, lambda p: p)
    assert third.provider_status == "audit_unavailable", (
        "once a response-save failure has flipped audit_write_failed, a NEW claim "
        "(not already in-flight) must be refused before being scheduled"
    )
    send_count_after_third = len(_read_jsonl(_req_audit_path(tmp_path, "t6brun")))
    assert send_count_after_third == send_count_before_third, (
        "the refused third claim must generate no new request-audit record (zero send)"
    )


# ---------------------------------------------------------------------------
# 7. Hard call-cap and 0/0 retries still enforced under concurrency
# ---------------------------------------------------------------------------

def test_hard_call_cap_and_zero_retries_enforced_under_concurrency(tmp_path, monkeypatch):
    """Every one of 10 concurrent calls fails at the transport (500), with
    max_retries=0 and max_calls=5. The hard cap must still allow exactly 5
    real transport sends (never more), and each of those 5 gets exactly ONE
    attempt (never a retry) despite genuine concurrent dispatch."""
    send_count = {"n": 0}
    send_lock = threading.Lock()

    def handler(request: httpx.Request) -> httpx.Response:
        with send_lock:
            send_count["n"] += 1
        return _error_response(500)

    gateway = _build_real_gateway("t7run", tmp_path, monkeypatch, handler)
    gateway.max_calls = 5
    assert gateway.max_retries == 0

    results: list[Any] = []
    lock = threading.Lock()

    def worker(i: int):
        inv = gateway.invoke_json_with_trace("alpha_classifier", {"claim_id": f"claim-{i}"}, lambda p: p)
        with lock:
            results.append(inv)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(results) == 10
    assert send_count["n"] == 5, f"expected exactly 5 real transport sends (the hard cap), got {send_count['n']}"
    assert gateway.call_count == 5

    failed_with_provider_error = [r for r in results if r.provider_status == "provider_error"]
    refused_budget_exhausted = [r for r in results if r.provider_status == "budget_exhausted"]
    assert len(failed_with_provider_error) == 5
    assert len(refused_budget_exhausted) == 5
    for r in failed_with_provider_error:
        assert r.provider_attempt_count == 1, "max_retries=0 must mean exactly one attempt per sent call, never a retry"
    for r in refused_budget_exhausted:
        assert r.provider_attempt_count == 0, "a budget-refused call must never reach the transport at all"

    total_attempts_recorded = sum(r.provider_attempt_count for r in results)
    assert total_attempts_recorded == 5, (
        f"expected exactly 5 total real attempts across all 10 calls (cap={5}, retries=0), "
        f"got {total_attempts_recorded}"
    )

    req_audit = _read_jsonl(_req_audit_path(tmp_path, "t7run"))
    assert len(req_audit) == 5, "audit record count must match real transport sends exactly, never more"
