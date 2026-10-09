"""2026-10-06 (AMD c904d4cc post-run audit, round 11): reproduces, offline
and at zero real Provider cost, the exact real defect found in the c904d4cc
AMD Fresh Run -- alpha_classifier's own concurrency=4 default dispatched
onto the SAME shared, audit-enabled Week2LLMGateway, whose pending-attempt
tracking assumes strictly sequential use. In the real run this converted 973
of 975 real classification attempts into a silent "provider_error" (caught
by alpha_mapper._classify_alpha_with_llm's own blanket except clause), with
zero trace in week2_llm_errors.jsonl or llm_semantic_calls.jsonl.

Every test here goes through the REAL build_server_week2_llm_gateway
construction and the REAL map_structured_records/save_alpha_matches call
path -- never a globally-mocked create_llm_client, never a hand-rolled
Gateway stand-in -- with only the lowest-level httpx transport faked, per
this round's own explicit requirement.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import httpx
import pytest

from comqutor_alpha.structure_engine.alpha_mapper import map_structured_records
from comqutor_alpha.structure_engine.week2_llm import build_server_week2_llm_gateway


def _taxonomy_payload_alpha_ids():
    from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy

    return list(load_alpha_taxonomy())


def _make_record(idx: int) -> dict[str, Any]:
    return {
        "claim_id": f"testrun:agent:report:claim:{idx}",
        "claim": f"AMD claim number {idx} with some analytical content about margins.",
        "evidence": f"AMD claim number {idx} with some analytical content about margins.",
        "agent": "fundamental_agent",
        "ticker": "AMD",
        "direction": "unknown",
        "claim_quality": "analytical",
        "analysis_eligible": True,
        "factors": [],
    }


@pytest.fixture
def real_gateway_with_tracking_transport(tmp_path, monkeypatch):
    """Builds the REAL gateway via build_server_week2_llm_gateway, with
    audit enabled, through the REAL tradingagents.llm_clients.create_llm_client
    factory (never monkeypatched) -- only the bottom-most httpx transport is
    replaced, with a handler that tracks real concurrent overlap and real
    per-attempt identity, and introduces a small real delay so genuinely
    concurrent dispatch would genuinely overlap if it were still possible."""
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "1")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MAX_RETRIES", "0")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixed-test-key-not-real")

    state = {"in_flight": 0, "max_concurrent_observed": 0, "lock": threading.Lock(), "calls": []}

    def handler(request: httpx.Request) -> httpx.Response:
        with state["lock"]:
            state["in_flight"] += 1
            state["max_concurrent_observed"] = max(state["max_concurrent_observed"], state["in_flight"])
        try:
            time.sleep(0.05)  # real, small delay -- long enough for a real race to manifest
            body = json.loads(request.content)
            # Identify which claim this request was for, from its own real serialized content.
            claim_text = body["messages"][0]["content"]
            state["calls"].append(claim_text[-80:])
            return httpx.Response(
                200,
                json={
                    "id": "chatcmpl-fixed",
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
        finally:
            with state["lock"]:
                state["in_flight"] -= 1

    base_transport = httpx.MockTransport(handler)
    gateway = build_server_week2_llm_gateway(
        "testrun",
        tmp_path,
        enable_request_response_audit=True,
        _base_transport_for_testing=base_transport,
    )
    assert gateway is not None
    assert gateway._audit_enabled is True

    # Matches production exactly (run_research_request always attaches one
    # before any Week2 task runs) -- without it, _classify_alpha_with_llm
    # falls back to the older, non-trace invoke_json() seam, which is not
    # the real path a live run actually takes.
    from comqutor_alpha.llm_runtime.cache import InMemoryLLMResponseCache
    from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession

    (tmp_path / "testrun").mkdir(exist_ok=True)
    semantic_runtime = SemanticRuntimeSession(
        run_id="testrun",
        output_directory=str(tmp_path / "testrun"),
        execution_mode="live",
        provider=gateway.provider,
        model=gateway.model_name,
        cache=InMemoryLLMResponseCache(),
    )
    gateway.attach_semantic_runtime(semantic_runtime)
    return gateway, state


def test_default_model_is_audited(real_gateway_with_tracking_transport, tmp_path):
    gateway, state = real_gateway_with_tracking_transport
    records = [_make_record(1)]
    map_structured_records(
        records,
        classifier_enabled=True,
        llm_gateway=gateway,
        concurrency=1,
    )
    req_audit = (tmp_path / "testrun" / "error_logs" / "week2_llm_provider_request_audit.jsonl")
    assert req_audit.exists()
    lines = req_audit.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["task"] == "alpha_classifier"


def test_real_concurrent_dispatch_no_longer_fails_with_contextvar_identity_fix(
    real_gateway_with_tracking_transport, tmp_path
):
    """THE regression test for the real c904d4cc defect, updated for round
    13's TRUE concurrent-audit fix: before round 11's fix, map_structured_
    records genuinely dispatched 8 claims with concurrency=4 onto this SAME
    audited gateway, and most hit WEEK2_LLM_AUDIT_CONCURRENT_ATTEMPT
    (caught silently by alpha_mapper's own except clause, surfacing as
    alpha_match_method=llm_unavailable, fallback_reason=provider_error --
    exactly what the real run showed). Round 11's own interim fix forced
    concurrency=1 whenever audit was on. Round 13 replaces the Gateway's
    single-pending-attempt design with real, independent per-attempt
    identity (contextvars, explicitly propagated across call_with_timeout's
    nested executor) and REMOVES the forced-serial override -- this test
    now asserts GENUINE concurrent overlap (not serialization) still
    produces zero failures and zero identity confusion."""
    gateway, state = real_gateway_with_tracking_transport
    records = [_make_record(i) for i in range(8)]

    results = map_structured_records(
        records,
        classifier_enabled=True,
        llm_gateway=gateway,
        concurrency=4,  # the real production default (DEFAULT_ALPHA_CLASSIFIER_CONCURRENCY)
    )

    # Every one of the 8 real, genuinely concurrent requests still gets a
    # real, completed response (the fixed handler always returns a clean
    # "none" decision) -- zero audit-concurrency failures under real overlap.
    assert len(results) == 8
    for r in results:
        assert r.get("alpha_match_method") == "llm", (
            f"expected every claim to get a real, completed LLM classification, got "
            f"alpha_match_method={r.get('alpha_match_method')!r} "
            f"fallback_reason={r.get('alpha_match_fallback_reason')!r} -- the audit-concurrency "
            "defect may have recurred"
        )
        assert r.get("alpha_match_fallback_reason") is None

    # THE key assertion for round 13: the real transport DID genuinely
    # observe concurrent overlap (not serialized down to 1) -- proving this
    # is a real concurrency fix, not "configured for 4, actually 1."
    assert state["max_concurrent_observed"] > 1, (
        "expected genuine concurrent overlap at the real transport layer; "
        f"observed max_concurrent_observed={state['max_concurrent_observed']} -- "
        "if this is 1, concurrency is being silently serialized somewhere"
    )
    assert len(state["calls"]) == 8

    # Every one of the 8 real requests was independently audited -- the
    # exact thing that was completely missing for 973/975 claims in the
    # real c904d4cc run.
    req_audit = (tmp_path / "testrun" / "error_logs" / "week2_llm_provider_request_audit.jsonl")
    resp_audit = (tmp_path / "testrun" / "error_logs" / "week2_llm_provider_response_audit.jsonl")
    assert len(req_audit.read_text().splitlines()) == 8
    assert len(resp_audit.read_text().splitlines()) == 8


def test_alpha_classifier_override_client_is_audited(tmp_path, monkeypatch):
    """Fix B: alpha_classifier's own per-task max_tokens override client
    (COMQUTOR_WEEK2_ALPHA_CLASSIFIER_MAX_TOKENS) must ALSO route through the
    real AuditingTransport -- confirmed broken before this round's fix (the
    override called create_llm_client(...) without ever passing
    http_client=), confirmed fixed here by observing a real request-audit
    record appear for a call made through the OVERRIDE model specifically."""
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "1")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixed-test-key-not-real")
    monkeypatch.setenv("COMQUTOR_WEEK2_ALPHA_CLASSIFIER_MAX_TOKENS", "2048")

    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-fixed", "object": "chat.completion", "created": 0,
                "model": "deepseek-v4-flash",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": '{"decision": "none", "selected_alpha_id": null}'}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    gateway = build_server_week2_llm_gateway(
        "testrun2",
        tmp_path,
        enable_request_response_audit=True,
        _base_transport_for_testing=httpx.MockTransport(handler),
    )
    assert gateway is not None

    gateway.invoke_json_with_trace("alpha_classifier", {"allowed_alpha_ids": ["A304"]}, lambda p: p)

    assert len(captured) == 1
    assert captured[0].get("max_tokens") == 2048  # the override's own param reached the real body

    req_audit = tmp_path / "testrun2" / "error_logs" / "week2_llm_provider_request_audit.jsonl"
    assert req_audit.exists(), "alpha_classifier override client was never audited -- the real c904d4cc defect"
    entries = [json.loads(line) for line in req_audit.read_text().splitlines()]
    assert len(entries) == 1
    assert entries[0]["task"] == "alpha_classifier"


def test_content_support_override_client_is_still_audited_after_refactor(tmp_path, monkeypatch):
    """Regression guard: the shared _audited_http_client_kwarg() refactor
    must not have broken content_support_verification's own pre-existing
    (already fixed earlier this session) audit wiring."""
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "1")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixed-test-key-not-real")
    monkeypatch.setenv("COMQUTOR_WEEK2_CONTENT_SUPPORT_MAX_TOKENS", "16384")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-fixed", "object": "chat.completion", "created": 0,
                "model": "deepseek-v4-flash",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": '{"items": []}'}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    gateway = build_server_week2_llm_gateway(
        "testrun3",
        tmp_path,
        enable_request_response_audit=True,
        _base_transport_for_testing=httpx.MockTransport(handler),
    )
    assert gateway is not None
    gateway.invoke_json_with_trace("content_support_verification", {"items": []}, lambda p: p)

    req_audit = tmp_path / "testrun3" / "error_logs" / "week2_llm_provider_request_audit.jsonl"
    assert req_audit.exists()
    entries = [json.loads(line) for line in req_audit.read_text().splitlines()]
    assert len(entries) == 1
    assert entries[0]["task"] == "content_support_verification"
