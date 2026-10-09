#!/usr/bin/env python3
"""2026-10-06 (round 14, section 5): proves the two NEW mid-batch crash
scenarios the instruction explicitly requires, beyond the already-covered
"finished N whole batches, then crashed" case from round 13:

  1. Responses already received and saved, but the enclosing batch's own
     checkpoint write never happened before the process stopped.
  2. A request was sent, but no valid response was ever saved (the process
     stopped between send and response-save).

Both are proven against the REAL request/response audit JSONL via
recover_alpha_classification.reconcile_claim_states_from_audit_log (round
14's new function, built on round 14's own claim_ids audit fix), using a
small, precisely controlled claim set and a real Week2LLMGateway with only
the bottom-most httpx transport faked -- not the full 973-claim set (that
scale is already covered by run_full_recovery_scale_test.py).

Verifies the required post-restart semantics exactly:
  - a "success" claim (including a valid NONE decision) is recoverable
    from the real audit log alone, even with a stale/behind checkpoint,
    and is never re-sent;
  - an "unknown_inflight" claim is surfaced distinctly and is NEVER
    automatically re-sent;
  - a "failed" claim is surfaced distinctly and is never silently upgraded
    to success/NONE;
  - the full identity set (success + failed + unknown + not-yet-sent) is
    preserved with no omissions and no extras.

This test's own fake-HTTP artifacts are written to a throwaway tmp_path
(via pytest's own fixture) -- never under outputs/runs/, never reusing or
polluting a future real recovery directory, cache, or checkpoint.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

import importlib.util

_SCRIPT = (
    Path(__file__).resolve().parents[1] / "docs" / "audit_artifacts" / "round_source_linking_t0_t2"
    / "round12_alpha_classifier_audit_fix_20261006" / "recover_alpha_classification.py"
)
pytestmark = pytest.mark.skipif(not _SCRIPT.exists(), reason="recovery script not present")
_spec = importlib.util.spec_from_file_location("recover_alpha_classification_mid_batch", _SCRIPT)
recover = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(recover)

from comqutor_alpha.llm_runtime.cache import InMemoryLLMResponseCache
from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
from comqutor_alpha.structure_engine.week2_llm import build_server_week2_llm_gateway


RUN_ID = "round14-mid-batch-crash-test"


def _success_body(decision: str, selected_alpha_id: str | None) -> dict:
    return {
        "id": "chatcmpl-fake", "object": "chat.completion", "created": 0, "model": "deepseek-v4-flash",
        "choices": [{"index": 0, "message": {
            "role": "assistant",
            "content": json.dumps({"decision": decision, "selected_alpha_id": selected_alpha_id}),
        }, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def _build_gateway(tmp_path: Path, monkeypatch, handler):
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "1")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MAX_RETRIES", "0")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixed-test-key-not-real")
    gateway = build_server_week2_llm_gateway(
        RUN_ID, tmp_path, enable_request_response_audit=True,
        _base_transport_for_testing=httpx.MockTransport(handler),
    )
    assert gateway is not None
    (tmp_path / RUN_ID).mkdir(exist_ok=True)
    gateway.attach_semantic_runtime(SemanticRuntimeSession(
        run_id=RUN_ID, output_directory=str(tmp_path / RUN_ID), execution_mode="live",
        provider=gateway.provider, model=gateway.model_name, cache=InMemoryLLMResponseCache(),
    ))
    return gateway


def test_reconciliation_covers_all_four_real_states(tmp_path, monkeypatch):
    """Five claims, one real Gateway, one batch -- deliberately engineered
    so the real audit log ends up containing all three reconcilable states
    plus one claim that is simply never sent at all:
      claim-ok-select   -> real HTTP 200, decision=select  -> "success"
      claim-ok-none     -> real HTTP 200, decision=none    -> "success" (valid NONE)
      claim-bad-500     -> real HTTP 500                   -> "failed"
      claim-crash-mid   -> handler raises mid-request (never returns a
                            response at all) -> request audited, response
                            never audited -> "unknown_inflight"
      claim-never-sent  -> never dispatched at all          -> absent entirely
    """
    # Matched on the real claim/evidence TEXT, never the claim_id -- by this
    # round's own design, claim_ids is out-of-band and never enters the
    # serialized payload/prompt the model receives (proven separately by
    # test_claim_ids_never_change_the_real_request_body in the main suite).
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        prompt = body["messages"][0]["content"]
        if "AMD margins are expanding" in prompt:
            return httpx.Response(200, json=_success_body("select", "A304"))
        if "weather in Santa Clara" in prompt:
            return httpx.Response(200, json=_success_body("none", None))
        if "Guidance was cut" in prompt:
            return httpx.Response(500, json={"error": "simulated provider failure"})
        if "broke below its 200-day average" in prompt:
            # Simulates the real process stopping mid-request: the request
            # IS audited (AuditingTransport saves it before forwarding), but
            # this exception means the wrapped transport's own
            # handle_request never returns, so _persist_response_audit is
            # never reached -- exactly "sent, no response ever saved."
            raise httpx.ConnectError("simulated crash mid-request, before any response")
        raise AssertionError(f"unexpected claim text in prompt: {prompt[:200]!r}")

    gateway = _build_gateway(tmp_path, monkeypatch, handler)

    claims = {
        "claim-ok-select": "AMD margins are expanding.",
        "claim-ok-none": "The weather in Santa Clara was mild.",
        "claim-bad-500": "Guidance was cut due to weak demand.",
        "claim-crash-mid": "The stock broke below its 200-day average.",
    }
    for claim_id, text in claims.items():
        payload = {"claim": text, "evidence": text, "ticker": "AMD", "factors": [],
                   "direction": "unknown", "alpha_taxonomy": {}}
        invocation = gateway.invoke_json_with_trace(
            "alpha_classifier", payload, lambda p: p, claim_ids=(claim_id,)
        )
        gateway.finalize_semantic_invocation(invocation, accepted=invocation.validation_accepted)
    # claim-never-sent: deliberately never dispatched at all.

    states = recover.reconcile_claim_states_from_audit_log(tmp_path, RUN_ID)

    assert states["claim-ok-select"]["state"] == "success"
    assert states["claim-ok-select"]["decision"]["selected_alpha_id"] == "A304"
    assert states["claim-ok-none"]["state"] == "success"
    assert states["claim-ok-none"]["decision"]["decision"] == "none", (
        "a valid NONE decision must reconcile as a genuinely completed, reusable "
        "classification -- not pending, not a failure"
    )
    assert states["claim-bad-500"]["state"] == "failed", (
        "a real 500 response must never be silently upgraded to success or NONE"
    )
    assert states["claim-crash-mid"]["state"] == "unknown_inflight", (
        "a request with no matching saved response must be surfaced as unknown, "
        "never assumed successful, never assumed failed"
    )
    assert "claim-never-sent" not in states, (
        "a claim that was never dispatched at all must be absent from the audit-log "
        "reconciliation entirely -- it is the caller's job to treat 'absent' as "
        "not-yet-sent, never this function's job to guess a state for it"
    )
    assert "__multi_attempt_warnings__" not in states


def test_mid_batch_crash_before_checkpoint_write_still_recovers_without_resend(tmp_path, monkeypatch):
    """The core required scenario: a batch's real HTTP work fully completes
    (every claim gets a real, audited response) but the process stops
    before THIS BATCH's own checkpoint write -- simulated here by simply
    never calling save_checkpoint for this batch, exactly representing
    what an abrupt stop at that exact point would leave on disk. A restart
    that trusted ONLY the (stale, behind) checkpoint would incorrectly
    re-send every claim in this batch. Reconciling against the real audit
    log first must recover all of them as already-done instead."""
    send_log: list[str] = []

    texts_by_claim = {
        "claim-1": "Claim one evidence text.",
        "claim-2": "Claim two evidence text.",
        "claim-3": "Claim three evidence text.",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        prompt = body["messages"][0]["content"]
        for cid, text in texts_by_claim.items():
            if text in prompt:
                send_log.append(cid)
                return httpx.Response(200, json=_success_body("none", None))
        raise AssertionError(f"unexpected prompt: {prompt[:200]!r}")

    gateway = _build_gateway(tmp_path, monkeypatch, handler)
    for claim_id, text in {
        "claim-1": "Claim one evidence text.",
        "claim-2": "Claim two evidence text.",
        "claim-3": "Claim three evidence text.",
    }.items():
        payload = {"claim": text, "evidence": text, "ticker": "AMD", "factors": [],
                   "direction": "unknown", "alpha_taxonomy": {}}
        invocation = gateway.invoke_json_with_trace(
            "alpha_classifier", payload, lambda p: p, claim_ids=(claim_id,)
        )
        gateway.finalize_semantic_invocation(invocation, accepted=invocation.validation_accepted)
    # Deliberately: no save_checkpoint() call here at all -- representing
    # the process stopping before this batch's checkpoint write, even
    # though all three real responses are already safely on disk.
    assert send_log == ["claim-1", "claim-2", "claim-3"]

    checkpoint = {"completed_claim_ids": {}}  # the real, stale state after the "crash"
    states = recover.reconcile_claim_states_from_audit_log(tmp_path, RUN_ID)

    all_three_claims = ["claim-1", "claim-2", "claim-3"]
    to_resend = [
        cid for cid in all_three_claims
        if cid not in checkpoint["completed_claim_ids"] and states.get(cid, {}).get("state") != "success"
    ]
    assert to_resend == [], (
        "reconciling against the real audit log must recover all three already-"
        "completed claims even though the (crashed, stale) checkpoint has none of "
        "them -- none should be queued for resend"
    )
    for cid in all_three_claims:
        assert states[cid]["state"] == "success"


def test_unknown_inflight_claim_is_never_automatically_resent(tmp_path, monkeypatch):
    """The other required scenario, isolated: a request was sent, no valid
    response was ever saved. On "restart," this claim must be excluded from
    both (a) the reusable-success set and (b) any automatic resend queue --
    it is surfaced as its own distinct, operator-reviewable bucket."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated crash mid-request")

    gateway = _build_gateway(tmp_path, monkeypatch, handler)
    payload = {"claim": "an in-flight claim", "evidence": "an in-flight claim", "ticker": "AMD",
               "factors": [], "direction": "unknown", "alpha_taxonomy": {}}
    invocation = gateway.invoke_json_with_trace(
        "alpha_classifier", payload, lambda p: p, claim_ids=("claim-inflight",)
    )
    gateway.finalize_semantic_invocation(invocation, accepted=invocation.validation_accepted)

    states = recover.reconcile_claim_states_from_audit_log(tmp_path, RUN_ID)
    assert states["claim-inflight"]["state"] == "unknown_inflight"

    # The required resume rule: only an explicit "state == success" claim is
    # ever treated as done-and-reusable; only a claim ABSENT from the audit
    # log entirely is eligible for a fresh send. "unknown_inflight" is
    # neither -- it must never automatically re-enter a resend queue, and
    # must never be treated as already complete.
    is_reusable = states["claim-inflight"]["state"] == "success"
    is_eligible_for_fresh_send = "claim-inflight" not in states
    assert not is_reusable
    assert not is_eligible_for_fresh_send


