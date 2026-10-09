"""2026-10-06 (round 14): proves the claim_id -> semantic_call_id ->
attempt_id -> request/response identity chain added this round, which
closes the real, pre-existing gap found in round 13 (alpha_classifier's
own request-audit records always carried claim_ids=[], since the LLM-
facing payload never includes claim_id by design).

Every test goes through the REAL build_server_week2_llm_gateway
construction (the real tradingagents.llm_clients.create_llm_client
factory, never monkeypatched) with only the bottom-most httpx transport
faked. The central, explicit requirement this round adds: claim identity
is carried OUT OF BAND (an explicit claim_ids= keyword on
invoke_json_with_trace / start_call, stored on SemanticCallTrace), never
folded into the payload dict that becomes the model's own prompt or the
semantic cache key -- proven directly below by asserting byte-identical
request bodies with and without claim_ids supplied.
"""

from __future__ import annotations

import json
import threading
from typing import Any

import httpx
import pytest

import comqutor_alpha.structure_engine.week2_llm as week2_llm
from comqutor_alpha.llm_runtime.cache import InMemoryLLMResponseCache
from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
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


def _build_gateway(run_id: str, tmp_path, monkeypatch, handler) -> Any:
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
    (tmp_path / run_id).mkdir(exist_ok=True)
    semantic_runtime = SemanticRuntimeSession(
        run_id=run_id, output_directory=str(tmp_path / run_id), execution_mode="live",
        provider=gateway.provider, model=gateway.model_name, cache=InMemoryLLMResponseCache(),
    )
    gateway.attach_semantic_runtime(semantic_runtime)
    return gateway, semantic_runtime


def _read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_claim_ids_never_change_the_real_request_body(tmp_path, monkeypatch):
    """The exact proof the instruction requires: the literal bytes the
    model/transport receives are identical whether or not claim_ids is
    supplied -- out-of-band identity never touches the prompt."""
    captured: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.content)
        return _success_response({"decision": "none"})

    gateway_a, _ = _build_gateway("identity_a", tmp_path, monkeypatch, handler)
    payload = {"claim": "AMD margins are expanding.", "evidence": "AMD margins are expanding.",
               "ticker": "AMD", "factors": [], "direction": "unknown", "alpha_taxonomy": {}}
    gateway_a.invoke_json_with_trace("alpha_classifier", dict(payload), lambda p: p)

    gateway_b, _ = _build_gateway("identity_b", tmp_path, monkeypatch, handler)
    gateway_b.invoke_json_with_trace(
        "alpha_classifier", dict(payload), lambda p: p,
        claim_ids=("amd-run:claim:42",),
    )

    assert len(captured) == 2
    assert captured[0] == captured[1], (
        "supplying claim_ids must never change a single byte of the real request body "
        "the model/transport actually receives"
    )


def test_four_way_concurrent_full_identity_chain(tmp_path, monkeypatch):
    """claim_id -> semantic_call_id -> attempt_id -> request/response, proven
    correct under genuine 4-way concurrent dispatch, including two claims
    with IDENTICAL text (duplicate-content, a real, confirmed-occurring
    case in the frozen AMD c904d4cc claim set)."""
    barrier = threading.Barrier(4, timeout=5.0)
    claims = {
        "claim-A": "AMD margins are expanding this quarter.",
        "claim-B": "Guidance was raised due to demand.",
        "claim-C": "AMD margins are expanding this quarter.",  # identical text to claim-A
        "claim-D": "The stock broke below its 50-day average.",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        barrier.wait()
        body = json.loads(request.content)
        prompt = body["messages"][0]["content"]
        # Identify by matching the (unique-enough) evidence text embedded
        # in the real prompt -- a reasonable test-side lookup since the
        # model payload intentionally never carries claim_id; identical
        # text pairs (claim-A/claim-C) aren't disambiguated this way, which
        # is exactly why the assertions below check per ATTEMPT via
        # claim_ids/semantic_call_id, never by re-deriving claim_id from
        # response content.
        return _success_response({"decision": "none"})

    gateway, semantic_runtime = _build_gateway("identity_4way", tmp_path, monkeypatch, handler)

    results: dict[str, Any] = {}
    lock = threading.Lock()

    def worker(claim_id: str, text: str):
        payload = {"claim": text, "evidence": text, "ticker": "AMD", "factors": [],
                   "direction": "unknown", "alpha_taxonomy": {}}
        invocation = gateway.invoke_json_with_trace(
            "alpha_classifier", payload, lambda p: p, claim_ids=(claim_id,)
        )
        gateway.finalize_semantic_invocation(invocation, accepted=invocation.validation_accepted)
        with lock:
            results[claim_id] = invocation

    threads = [threading.Thread(target=worker, args=(cid, text)) for cid, text in claims.items()]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(results) == 4
    for cid, invocation in results.items():
        assert invocation.validation_accepted, f"{cid} did not get a valid response"

    req_audit = _read_jsonl(tmp_path / "identity_4way" / "error_logs" / "week2_llm_provider_request_audit.jsonl")
    resp_audit = _read_jsonl(tmp_path / "identity_4way" / "error_logs" / "week2_llm_provider_response_audit.jsonl")
    semantic_calls = _read_jsonl(tmp_path / "identity_4way" / "llm_semantic_calls.jsonl")

    assert len(req_audit) == 4
    assert len(resp_audit) == 4
    assert len(semantic_calls) == 4

    # Level 1: every real request-audit record's claim_ids is a real,
    # correct, SINGLE-element match -- never [] (the round-13 gap), never
    # more than one claim's id, never swapped between the identical-text pair.
    req_claim_ids = {tuple(r["claim_ids"]) for r in req_audit}
    assert req_claim_ids == {(cid,) for cid in claims}, (
        f"expected each request audited under exactly its own claim_ids, got {req_claim_ids}"
    )

    # Level 2: request <-> response <-> semantic-call join via attempt_id /
    # semantic_call_id -- all three must agree on claim_ids for the same
    # logical call, even for the two identical-TEXT claims (A and C).
    req_by_attempt = {r["attempt_id"]: r for r in req_audit}
    resp_by_attempt = {r["attempt_id"]: r for r in resp_audit}
    assert set(req_by_attempt) == set(resp_by_attempt)
    semantic_by_call_id = {r["call_id"]: r for r in semantic_calls}

    for attempt_id, req in req_by_attempt.items():
        resp = resp_by_attempt[attempt_id]
        assert resp["claim_ids"] == req["claim_ids"], (
            f"request/response claim_ids mismatch for attempt {attempt_id}"
        )
        assert resp["semantic_call_id"] == req["semantic_call_id"]
        assert req["semantic_call_id"] in semantic_by_call_id, (
            "every attempt's semantic_call_id must resolve to a real llm_semantic_calls.jsonl record"
        )
        semantic_record = semantic_by_call_id[req["semantic_call_id"]]
        assert semantic_record["claim_ids"] == req["claim_ids"], (
            "the semantic call record's own claim_ids must agree with its audit records -- "
            "the full claim_id -> semantic_call_id -> attempt_id -> request/response chain"
        )

    # The two identical-TEXT claims (A and C) still got fully independent,
    # non-colliding identity chains end-to-end.
    assert semantic_by_call_id[req_by_attempt[
        next(a for a, r in req_by_attempt.items() if r["claim_ids"] == ["claim-A"])
    ]["semantic_call_id"]]["call_id"] != semantic_by_call_id[req_by_attempt[
        next(a for a, r in req_by_attempt.items() if r["claim_ids"] == ["claim-C"])
    ]["semantic_call_id"]]["call_id"]


def test_cache_reuse_explicitly_cites_its_real_source_call(tmp_path, monkeypatch):
    """Two claims, IDENTICAL text (so the SAME semantic cache_key) but
    DIFFERENT claim_ids. The second one must hit the cache (zero additional
    real send) while still getting its OWN correct claim_ids in its own
    persisted record -- AND that record's cache.source_call_id must
    literally equal the FIRST claim's own real call_id, not a guess, not a
    timestamp-based inference."""
    send_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        send_count["n"] += 1
        return _success_response({"decision": "none"})

    gateway, _ = _build_gateway("identity_cache", tmp_path, monkeypatch, handler)
    same_text = "Revenue guidance was raised due to strong demand."
    payload = {"claim": same_text, "evidence": same_text, "ticker": "AMD", "factors": [],
               "direction": "unknown", "alpha_taxonomy": {}}

    inv_first = gateway.invoke_json_with_trace(
        "alpha_classifier", dict(payload), lambda p: p, claim_ids=("claim-source",)
    )
    gateway.finalize_semantic_invocation(inv_first, accepted=inv_first.validation_accepted)

    inv_second = gateway.invoke_json_with_trace(
        "alpha_classifier", dict(payload), lambda p: p, claim_ids=("claim-reuser",)
    )
    gateway.finalize_semantic_invocation(inv_second, accepted=inv_second.validation_accepted)

    assert send_count["n"] == 1, "the second, identical-content call must be served from cache, not re-sent"
    assert inv_second.cache_hit is True

    semantic_calls = _read_jsonl(tmp_path / "identity_cache" / "llm_semantic_calls.jsonl")
    assert len(semantic_calls) == 2
    by_claim = {tuple(r["claim_ids"]): r for r in semantic_calls}
    source_record = by_claim[("claim-source",)]
    reuser_record = by_claim[("claim-reuser",)]

    assert source_record["cache"]["hit"] is False
    assert reuser_record["cache"]["hit"] is True
    assert reuser_record["cache"]["source_call_id"] == source_record["call_id"], (
        "a cache-hit record must explicitly cite the REAL call_id of the record that "
        "actually produced the reused output, not merely say hit=True with no origin"
    )
    # And its own claim identity is still its own, not the source's.
    assert reuser_record["claim_ids"] == ["claim-reuser"]


def test_timeout_and_late_response_both_preserve_claim_identity(tmp_path, monkeypatch):
    """A call that times out, and whose background send then completes
    late, must preserve its OWN claim_ids throughout -- in both the
    (early, timeout) business result and the (late) response audit."""
    import time

    def handler(request: httpx.Request) -> httpx.Response:
        time.sleep(0.3)
        return _success_response({"decision": "none"})

    gateway, _ = _build_gateway("identity_timeout", tmp_path, monkeypatch, handler)
    gateway.timeout_seconds = 0.05
    payload = {"claim": "slow claim text", "evidence": "slow claim text", "ticker": "AMD",
               "factors": [], "direction": "unknown", "alpha_taxonomy": {}}

    invocation = gateway.invoke_json_with_trace(
        "alpha_classifier", payload, lambda p: p, claim_ids=("claim-timeout",)
    )
    assert invocation.provider_status == "timeout"

    time.sleep(0.5)  # let the late background response actually land

    req_audit = _read_jsonl(tmp_path / "identity_timeout" / "error_logs" / "week2_llm_provider_request_audit.jsonl")
    resp_audit = _read_jsonl(tmp_path / "identity_timeout" / "error_logs" / "week2_llm_provider_response_audit.jsonl")
    assert len(req_audit) == 1
    assert len(resp_audit) == 1
    assert req_audit[0]["claim_ids"] == ["claim-timeout"]
    assert resp_audit[0]["claim_ids"] == ["claim-timeout"], (
        "the late response audit must still carry the correct claim_ids for the call it "
        "actually belongs to, even though the caller already moved on after the timeout"
    )


def test_content_support_verification_claim_ids_unaffected_by_new_param(tmp_path, monkeypatch):
    """Regression guard: content_support_verification never passes the new
    claim_ids= keyword and must keep resolving identity exactly as before
    (from its own "items" list inside payload)."""
    def handler(request: httpx.Request) -> httpx.Response:
        return _success_response({"items": []})

    gateway, _ = _build_gateway("identity_content_support", tmp_path, monkeypatch, handler)
    gateway.invoke_json_with_trace(
        "content_support_verification",
        {"items": [{"claim_id": "cs-claim-1"}, {"claim_id": "cs-claim-2"}]},
        lambda p: p,
    )
    req_audit = _read_jsonl(
        tmp_path / "identity_content_support" / "error_logs" / "week2_llm_provider_request_audit.jsonl"
    )
    assert len(req_audit) == 1
    assert sorted(req_audit[0]["claim_ids"]) == ["cs-claim-1", "cs-claim-2"]


# ---------------------------------------------------------------------------
# Compatibility guards for the two regressions the round-14 full run exposed:
#   1. a gateway-like object with the older 3-argument invoke_json_with_trace
#      silently turned into a fake "provider_error" (TypeError swallowed);
#   2. replay's private mirror of the semantic-record validator rejected the
#      new optional fields, failing every replay of a post-change run closed.
# ---------------------------------------------------------------------------

from types import SimpleNamespace  # noqa: E402

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy  # noqa: E402
from comqutor_alpha.structure_engine import alpha_mapper  # noqa: E402


def _stub_invocation(decision: dict):
    return SimpleNamespace(
        validation_accepted=True, validated_output={"outcome": "none", "alpha_id": ""},
        error_code=None, provider_status="success", trace_handle=None,
    )


class _ThreeArgGateway:
    """The older gateway-like signature many test doubles (and any external
    wrapper) still use: no claim_ids parameter at all."""

    def __init__(self):
        self.semantic_runtime = object()
        self.calls = []

    def invoke_json_with_trace(self, task, payload, validator):
        self.calls.append((task, "no-claim_ids-kwarg"))
        return _stub_invocation({})

    def finalize_semantic_invocation(self, invocation, *, accepted, fallback_reason=None):
        pass


class _ClaimIdsGateway(_ThreeArgGateway):
    def invoke_json_with_trace(self, task, payload, validator, *, claim_ids=None):
        self.calls.append((task, claim_ids))
        return _stub_invocation({})


class _KwargsGateway(_ThreeArgGateway):
    def invoke_json_with_trace(self, task, payload, validator, **kwargs):
        self.calls.append((task, kwargs.get("claim_ids")))
        return _stub_invocation({})


_RECORD = {"claim_id": "run:agent:claim:7", "claim": "c", "evidence": "c", "ticker": "AMD",
           "factors": [], "direction": "unknown"}


def _classify(gateway):
    return alpha_mapper._classify_alpha_with_llm(_RECORD, load_alpha_taxonomy(), None, True, 5.0, llm_gateway=gateway)


def test_three_argument_gateway_still_classifies_instead_of_becoming_a_fake_provider_error():
    gateway = _ThreeArgGateway()
    outcome = _classify(gateway)
    assert gateway.calls == [("alpha_classifier", "no-claim_ids-kwarg")]
    assert outcome["outcome"] == "none", f"must classify normally, got {outcome}"
    assert outcome.get("fallback_reason") in (None, "")


@pytest.mark.parametrize("gateway_cls", [_ClaimIdsGateway, _KwargsGateway])
def test_a_gateway_that_declares_claim_ids_or_kwargs_receives_the_claim_identity(gateway_cls):
    gateway = gateway_cls()
    _classify(gateway)
    assert gateway.calls == [("alpha_classifier", ("run:agent:claim:7",))]


def test_adapter_deferred_finalize_proxy_forwards_claim_ids_untouched():
    from comqutor_alpha.structure_engine.structured_output_adapter import _DeferredFinalizeGatewayProxy

    inner = _ClaimIdsGateway()
    proxy = _DeferredFinalizeGatewayProxy(inner)
    proxy.invoke_json_with_trace("alpha_classifier", {"claim": "c"}, lambda p: p, claim_ids=("run:agent:claim:7",))
    assert inner.calls == [("alpha_classifier", ("run:agent:claim:7",))]
    # and the proxy used as the gateway for the classifier call site is detected as accepting claim_ids
    assert alpha_mapper._gateway_accepts_claim_ids(proxy) is True
    assert alpha_mapper._gateway_accepts_claim_ids(_ThreeArgGateway()) is False


def test_replay_validator_accepts_the_new_optional_fields_end_to_end_and_still_rejects_malformed_ones(
    tmp_path, monkeypatch
):
    """Records produced by the REAL gateway + semantic runtime (including a
    cache-hit record carrying cache.source_call_id) must pass replay's own
    private copy of the record validator; malformed values still fail closed."""
    from comqutor_alpha.replay import source_bundle

    gateway, _ = _build_gateway("identity_replay", tmp_path, monkeypatch, lambda request: _success_response({"decision": "none"}))
    payload = {"claim": "Replay me.", "evidence": "Replay me.", "ticker": "AMD", "factors": [],
               "direction": "unknown", "alpha_taxonomy": {}}
    for claim in ("claim-first", "claim-second"):  # identical payload -> second is a cache hit
        inv = gateway.invoke_json_with_trace("alpha_classifier", dict(payload), lambda p: p, claim_ids=(claim,))
        gateway.finalize_semantic_invocation(inv, accepted=inv.validation_accepted)

    records = _read_jsonl(tmp_path / "identity_replay" / "llm_semantic_calls.jsonl")
    assert len(records) == 2
    assert records[0]["claim_ids"] == ["claim-first"] and "source_call_id" not in records[0]["cache"]
    assert records[1]["cache"]["hit"] is True and records[1]["cache"]["source_call_id"] == records[0]["call_id"]
    assert source_bundle._call_collection_errors(records) == []

    bad_claims = [{**records[0], "claim_ids": ["", "x"]}]
    assert "SEMANTIC_CLAIM_IDS_INVALID" in source_bundle._call_collection_errors(bad_claims)
    bad_claims = [{**records[0], "claim_ids": "not-a-list"}]
    assert "SEMANTIC_CLAIM_IDS_INVALID" in source_bundle._call_collection_errors(bad_claims)
    bad_cache = [{**records[1], "cache": {**records[1]["cache"], "source_call_id": ""}}]
    assert "SEMANTIC_CACHE_INVALID" in source_bundle._call_collection_errors(bad_cache)
    unknown_cache_key = [{**records[1], "cache": {**records[1]["cache"], "surprise": 1}}]
    assert "SEMANTIC_CACHE_INVALID" in source_bundle._call_collection_errors(unknown_cache_key)
    unknown_field = [{**records[0], "surprise": 1}]
    assert "SEMANTIC_RECORD_FIELDS_INVALID" in source_bundle._call_collection_errors(unknown_field)
