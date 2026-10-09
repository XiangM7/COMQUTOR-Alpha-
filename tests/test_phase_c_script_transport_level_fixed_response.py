"""2026-10-06 (Phase C controlled single-request verification round):
exercises the ACTUAL round10 ``03_phase_c_execution_script.py`` -- not a
reimplementation of its logic -- with ONLY the lowest httpx transport
replaced by a fixed-response ``httpx.MockTransport``. Every other real
function on the path (``run_preflight``, ``verify_live_client_config``,
``run``, ``build_server_week2_llm_gateway``, the real
``Week2LLMGateway`` retry/budget loop, ``AuditingTransport``) executes
unmodified. Zero real Provider calls: the MockTransport never reaches a
real socket.

This also directly verifies the new audit-persistence mechanism is
accurate, not approximate: the request body captured by the MockTransport
handler (the literal bytes the "network" -- the mock -- received) is
compared against the body independently saved to
``error_logs/week2_llm_provider_request_audit.jsonl`` via the real
``append_jsonl_record``/``Week2LLMGateway._persist_request_audit`` path.

Every test passes ``_gateway_output_root_for_testing=tmp_path`` --
``run_preflight()`` still reads the REAL, historical AMD run data (it
needs no redirection), but the Gateway's OWN new per-execution audit
writes must never land in the real project ``outputs/runs/`` tree. An
earlier version of this file relied on the ``COMQUTOR_OUTPUT_DIR`` env
var instead, which ``build_server_week2_llm_gateway`` never consults when
an explicit ``output_root`` is passed (it always is, here) -- that
mistake briefly wrote fake test data into the real
``outputs/runs/phase-c-amd-21-claim-verification/`` directory, since
cleaned up by hand (see the 2026-10-06 report for the full account)."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from tests._content_support_v2_fixture_helpers import v2_response

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT
    / "docs/audit_artifacts/round_source_linking_t0_t2/round10_amd_official_scoring_trace_20261006"
    / "03_phase_c_execution_script.py"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("phase_c_script_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _restore_process_environment():
    """2026-10-06 (round 14, regression closure): the script under test calls
    load_dotenv(.env) and then assigns os.environ["COMQUTOR_WEEK2_LLM_ENABLED"/
    "MAX_RETRIES"/"MAX_CALLS"/...] directly, and these tests only monkeypatch
    the API key -- so those writes (plus whatever .env injects, including
    COMQUTOR_DATABASE_URL) outlived this module and every later test in a full
    pytest session (w5_*, week1a, week4, ...) started with the Week2 gateway
    switched on. Confirmed with a per-test env probe over a full run (1,523
    tests started with the leaked values). This restores the process
    environment exactly after each test; no assertion in this file changes."""
    with patch.dict("os.environ"):
        yield


@pytest.fixture
def script():
    return _load_script_module()


def _valid_support_response_body(request_body: bytes) -> bytes:
    payload = json.loads(request_body)
    messages = payload.get("messages", [])
    input_json_text = next((m["content"] for m in messages if "INPUT_JSON:" in m.get("content", "")), "")
    input_json = json.loads(input_json_text.split("INPUT_JSON:\n", 1)[1])
    items = []
    for item in input_json["items"]:
        candidate = item["allowed_candidates"][0]
        items.append(
            v2_response(
                claim_id=item["claim_id"],
                status="SUPPORTS",
                used_source_id=candidate["source_id"],
                used_location="excerpt",
                supporting_quote_or_data=candidate["excerpt"][:30],
                supported_proposition=item["proposition"],
            )
        )
    content = json.dumps({"items": items})
    return json.dumps(
        {
            "id": "chatcmpl-fixed-test",
            "object": "chat.completion",
            "model": payload.get("model", "deepseek-v4-flash"),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        }
    ).encode("utf-8")


def _truncated_response_body(request_body: bytes) -> bytes:
    payload = json.loads(request_body)
    return json.dumps(
        {
            "id": "chatcmpl-fixed-truncated",
            "object": "chat.completion",
            "model": payload.get("model", "deepseek-v4-flash"),
            "choices": [{"index": 0, "message": {"role": "assistant", "content": ""}, "finish_reason": "length"}],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 4096,
                "total_tokens": 4196,
                "completion_tokens_details": {"reasoning_tokens": 4096},
            },
        }
    ).encode("utf-8")


class _RecordingHandler:
    """The fixed-response Provider boundary stand-in. Every call it
    receives is a REAL httpx.Request that has already passed through
    AuditingTransport.handle_request (and therefore already past
    _persist_request_audit) -- it is the single source of truth for "what
    did the transport actually receive", used to verify the saved audit
    record is not merely a reconstruction."""

    def __init__(self, responder=_valid_support_response_body):
        self.received_requests: list[httpx.Request] = []
        self.responder = responder

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.received_requests.append(request)
        body = self.responder(request.content)
        return httpx.Response(200, json=json.loads(body))


def _env_for_real_config(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixed-test-key-not-real")


def _args(*, execute: bool, max_calls: int = 21, max_tokens: int = 4096, target_claim_ids=None, execution_id=None):
    return argparse.Namespace(
        execute=execute, max_calls=max_calls, max_tokens=max_tokens,
        target_claim_ids=target_claim_ids or [], execution_id=execution_id,
    )


def _run(script, args, *, mock_transport, tmp_path):
    return script.run(
        args,
        _base_transport_for_testing=mock_transport,
        _gateway_output_root_for_testing=tmp_path,
        _results_dir_for_testing=tmp_path / "executions",
    )


def test_without_execute_flag_zero_requests_reach_transport(script, monkeypatch, tmp_path):
    _env_for_real_config(monkeypatch)
    handler = _RecordingHandler()
    mock_transport = httpx.MockTransport(handler)
    result = _run(script, _args(execute=False), mock_transport=mock_transport, tmp_path=tmp_path)
    assert result is None
    assert handler.received_requests == []


def test_21_inputs_produce_21_single_claim_requests_at_the_real_transport(script, monkeypatch, tmp_path):
    _env_for_real_config(monkeypatch)
    handler = _RecordingHandler()
    mock_transport = httpx.MockTransport(handler)
    result = _run(script, _args(execute=True, max_calls=21), mock_transport=mock_transport, tmp_path=tmp_path)

    assert len(handler.received_requests) == 21
    for request in handler.received_requests:
        body = json.loads(request.content)
        input_json_text = next(m["content"] for m in body["messages"] if "INPUT_JSON:" in m.get("content", ""))
        input_json = json.loads(input_json_text.split("INPUT_JSON:\n", 1)[1])
        assert len(input_json["items"]) == 1, "each real request reaching transport must carry exactly one claim"
        # Property 2: candidates stay scoped to this one claim's own source.
        claim_id = input_json["items"][0]["claim_id"]
        candidate_source_ids = {c["source_id"] for c in input_json["items"][0]["allowed_candidates"]}
        assert candidate_source_ids == {"src_5bd8a947130d1949"}, claim_id
        # Property 4: DeepSeek's real wire body uses max_tokens, never
        # max_completion_tokens (langchain_openai's own base class would
        # otherwise rename it; DeepSeekChatOpenAI._get_request_payload
        # renames it back -- this proves that correction reaches the
        # literal bytes, not just the pre-client kwargs).
        assert "max_tokens" in body
        assert "max_completion_tokens" not in body
        assert body["max_tokens"] == 4096

    assert result["stats"]["requested_count"] == 21
    assert result["stats"]["real_provider_attempts"] == 21


def test_saved_request_audit_matches_literal_transport_bytes_exactly(script, monkeypatch, tmp_path):
    """The core proof Part 4 point 3 requires: the audit record saved by
    Week2LLMGateway._persist_request_audit must equal -- not approximate
    -- the literal bytes the mock transport (standing in for the real
    network) received for the SAME request."""
    _env_for_real_config(monkeypatch)
    handler = _RecordingHandler()
    mock_transport = httpx.MockTransport(handler)
    _run(script, _args(execute=True, max_calls=3), mock_transport=mock_transport, tmp_path=tmp_path)

    from comqutor_alpha.storage.file_store import read_jsonl_records

    saved_requests = read_jsonl_records(
        "phase-c-amd-21-claim-verification",
        "error_logs/week2_llm_provider_request_audit.jsonl",
        output_root=str(tmp_path),
    )
    assert len(saved_requests) == len(handler.received_requests)
    for saved, real in zip(saved_requests, handler.received_requests, strict=True):
        real_body_text = real.content.decode("utf-8")
        assert saved["body"] == real_body_text, "saved request body must equal the literal transport-received bytes"
        assert saved["body_sha256"] == hashlib.sha256(real_body_text.encode("utf-8")).hexdigest()
        header_names_lower = {k.lower() for k in saved["headers"]}
        if "authorization" in header_names_lower:
            actual_key = next(k for k in saved["headers"] if k.lower() == "authorization")
            assert saved["headers"][actual_key] == "REDACTED"

    saved_responses = read_jsonl_records(
        "phase-c-amd-21-claim-verification",
        "error_logs/week2_llm_provider_response_audit.jsonl",
        output_root=str(tmp_path),
    )
    assert len(saved_responses) == len(saved_requests)
    for saved_resp, saved_req in zip(saved_responses, saved_requests, strict=True):
        assert saved_resp["attempt_id"] == saved_req["attempt_id"]


def test_global_call_cap_enforced_before_transport_is_ever_reached(script, monkeypatch, tmp_path):
    _env_for_real_config(monkeypatch)
    handler = _RecordingHandler()
    mock_transport = httpx.MockTransport(handler)
    result = _run(script, _args(execute=True, max_calls=5), mock_transport=mock_transport, tmp_path=tmp_path)

    assert len(handler.received_requests) == 5, "requests beyond the real max_calls cap must never reach the transport"
    assert result["stats"]["fallback_reason_counts"]["budget_exhausted"] == 16


def test_truncated_response_single_attempt_zero_retry(script, monkeypatch, tmp_path):
    """Property 5: client+app retries both 0 -- a truncated/failing
    response produces exactly ONE real request to the transport per claim,
    never retried under the same config."""
    _env_for_real_config(monkeypatch)
    handler = _RecordingHandler(responder=_truncated_response_body)
    mock_transport = httpx.MockTransport(handler)
    one_claim_id = json.loads(
        (
            REPO_ROOT
            / "docs/audit_artifacts/round_source_linking_t0_t2/round9_llm_content_support_20261006"
            / "01_amd_21_analytical_claims_raw.json"
        ).read_text()
    )[0]["claim_id"]
    result = _run(
        script, _args(execute=True, max_calls=21, target_claim_ids=[one_claim_id]),
        mock_transport=mock_transport, tmp_path=tmp_path,
    )
    assert len(handler.received_requests) == 1, "max_retries=0 must mean exactly one real transport call for this claim"
    assert result["stats"]["real_provider_attempts"] == 1


def test_request_audit_save_failure_means_zero_send(script, monkeypatch, tmp_path):
    """Property 8a: if the request record fails to persist BEFORE sending,
    the request must never reach the transport at all."""
    _env_for_real_config(monkeypatch)
    handler = _RecordingHandler()
    mock_transport = httpx.MockTransport(handler)

    from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

    with patch.object(Week2LLMGateway, "_persist_request_audit", side_effect=RuntimeError("disk full (simulated)")):
        result = _run(script, _args(execute=True, max_calls=21), mock_transport=mock_transport, tmp_path=tmp_path)

    assert handler.received_requests == [], "a request-audit save failure must prevent the request from ever being sent"
    assert result["stats"]["fallback_reason_counts"].get("audit_write_failed", 0) == 21


def test_response_audit_save_failure_stops_subsequent_sends(script, monkeypatch, tmp_path):
    """Property 8b: a response-record save failure must not undo the
    current (already-answered) attempt, but must stop every later one."""
    _env_for_real_config(monkeypatch)
    handler = _RecordingHandler()
    mock_transport = httpx.MockTransport(handler)

    from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

    with patch.object(
        Week2LLMGateway, "_persist_response_audit", side_effect=RuntimeError("disk full (simulated)")
    ):
        result = _run(script, _args(execute=True, max_calls=21), mock_transport=mock_transport, tmp_path=tmp_path)

    assert len(handler.received_requests) == 1, (
        "the first attempt's response-save failure must still allow that ONE already-sent request through, "
        "but no further claim's request should ever reach the transport"
    )
    assert result["stats"]["fallback_reason_counts"].get("audit_write_failed", 0) == 20
