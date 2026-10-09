#!/usr/bin/env python3
"""2026-10-06 (round 14, section 7): captures the ACTUAL client construction
arguments and serialized alpha_classifier request the future recovery would
use, through the REAL construction path (build_server_week2_llm_gateway ->
real tradingagents create_llm_client, spied via a pass-through wrapper, NOT
replaced) with only the bottom-most httpx transport faked. Zero network.

Also proves two identity facts against the ORIGINAL real c904d4cc run's own
persisted semantic records, so nothing here is a guess:
  - prompt identity: Week2LLMGateway.prompt_identity_sha256('alpha_classifier')
    now == the prompt_sha256 recorded on the original run's real calls.
  - request-input identity: for the original run's two successful real
    alpha_classifier calls, the payload rebuilt NOW from the frozen
    structured record hashes to exactly the input_sha256 the original run
    recorded -- i.e. the semantic-cache-key input is unchanged by this
    round's claim-identity work.

Reports for each parameter whether it is EXPLICIT (an env var the recovery
launcher must set) or a code DEFAULT. Does not choose or raise any value.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

import httpx  # noqa: E402

ORIGINAL_RUN_ID = "c904d4cc-dc09-495c-aec5-b056979948e1"
ORIGINAL_DIR = REPO_ROOT / "outputs" / "runs" / ORIGINAL_RUN_ID
OUT_PATH = Path(__file__).parent / "effective_request_config.json"

# The env the recovery launcher would set. EXPLICIT = must be exported by the
# operator's launcher; anything not listed here falls to a code default and
# is reported as such below.
RECOVERY_EXPLICIT_ENV = {
    "COMQUTOR_WEEK2_LLM_ENABLED": "1",
    "COMQUTOR_WEEK2_LLM_PROVIDER": "deepseek",
    "COMQUTOR_WEEK2_LLM_MODEL": "deepseek-v4-flash",
    "COMQUTOR_WEEK2_LLM_MAX_RETRIES": "0",
    "COMQUTOR_WEEK2_LLM_MAX_CALLS": "973",
    "COMQUTOR_WEEK2_LLM_CONCURRENCY": "4",
    "COMQUTOR_WEEK2_LLM_ENABLE_REQUEST_AUDIT": "1",
    "DEEPSEEK_API_KEY": "fixed-test-key-not-real",
}
# Env vars that, if SET, would change alpha_classifier's request. The
# recovery leaves all of them UNSET (matching the original run, whose real
# request_control shows max_tokens_value=None).
RECOVERY_DELIBERATELY_UNSET = (
    "COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS",
    "COMQUTOR_WEEK2_ALPHA_CLASSIFIER_MAX_TOKENS",
    "COMQUTOR_WEEK2_LLM_BASE_URL",
    "TRADINGAGENTS_LLM_BACKEND_URL",
)


def main() -> None:
    for name in RECOVERY_DELIBERATELY_UNSET:
        os.environ.pop(name, None)
    os.environ.update(RECOVERY_EXPLICIT_ENV)
    env_keys_before_imports = set(os.environ)

    import tradingagents.llm_clients as llm_clients  # noqa: E402  (tradingagents/__init__ calls load_dotenv, override=False)
    from comqutor_alpha.llm_runtime.cache import InMemoryLLMResponseCache
    from comqutor_alpha.llm_runtime.canonical_json import sha256_canonical_json
    from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
    from comqutor_alpha.structure_engine import alpha_mapper
    from comqutor_alpha.structure_engine.week2_llm import (
        DEFAULT_MAX_RETRIES,
        DEFAULT_TIMEOUT_SECONDS,
        Week2LLMGateway,
        build_server_week2_llm_gateway,
        resolve_alpha_classifier_concurrency,
    )

    # Pass-through spy: records the REAL constructor kwargs, then calls the
    # real factory unchanged.
    real_factory = llm_clients.create_llm_client
    constructor_calls: list[dict] = []

    def spy(**kwargs):
        safe = {k: ("<httpx.Client>" if k == "http_client" else v) for k, v in kwargs.items() if k != "api_key"}
        safe["api_key_supplied"] = "api_key" in kwargs
        constructor_calls.append(safe)
        return real_factory(**kwargs)

    llm_clients.create_llm_client = spy

    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request.read()
        captured.append(request)
        return httpx.Response(200, json={
            "id": "x", "object": "chat.completion", "created": 0, "model": "deepseek-v4-flash",
            "choices": [{"index": 0, "message": {"role": "assistant",
                         "content": '{"decision": "none", "selected_alpha_id": null}'}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})

    structured = json.loads((ORIGINAL_DIR / "structured_agent_outputs.json").read_text())
    records_by_id = {r["claim_id"]: r for r in structured["records"]}

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        gateway = build_server_week2_llm_gateway(
            "config-capture", tmp, enable_request_response_audit=False,
            _base_transport_for_testing=httpx.MockTransport(handler),
        )
        assert gateway is not None
        # NOTE: enable_request_response_audit=False here only because the
        # spy/capture reads the request at the MockTransport directly; audit
        # on/off does not alter the serialized request (proved by
        # tests/test_claim_identity_traceability.py). The audit flag the
        # recovery uses is reported below from the env, not assumed.
        (tmp / "config-capture").mkdir(exist_ok=True)
        gateway.attach_semantic_runtime(SemanticRuntimeSession(
            run_id="config-capture", output_directory=str(tmp / "config-capture"),
            execution_mode="live", provider=gateway.provider, model=gateway.model_name,
            cache=InMemoryLLMResponseCache()))

        sample_claim_id = next(iter(records_by_id))
        alpha_mapper.map_structured_records(
            [records_by_id[sample_claim_id]], classifier_enabled=True, llm_gateway=gateway, concurrency=1)

        request = captured[0]
        body = json.loads(request.content)
        message_content = body["messages"][0]["content"]
        body_without_messages = {k: v for k, v in body.items() if k != "messages"}

        request_control = None
        sample_model = gateway._resolve_task_model("alpha_classifier")
        from comqutor_alpha.structure_engine.week2_llm import _request_control_snapshot
        request_control = _request_control_snapshot(sample_model, "probe")

        gateway_attrs = {
            "timeout_seconds": gateway.timeout_seconds,
            "max_retries": gateway.max_retries,
            "max_calls": gateway.max_calls,
            "provider": gateway.provider,
            "model_name": gateway.model_name,
            "alpha_classifier_has_task_model_override": "alpha_classifier" in gateway._task_model_overrides,
        }

    from dotenv import dotenv_values
    dotenv_file_values = dotenv_values(REPO_ROOT / ".env")  # read directly: an explicit launcher export pre-empts injection, so the diff above cannot show it
    injected_by_dotenv = {
        k: os.environ[k] for k in sorted(set(os.environ) - env_keys_before_imports)
        if k.startswith(("COMQUTOR_WEEK2", "COMQUTOR_RESEARCH", "TRADINGAGENTS_LLM", "TRADINGAGENTS_QUICK"))
    }

    # --- identity proofs against the ORIGINAL run's real records -----------
    original_calls = [
        json.loads(line) for line in (ORIGINAL_DIR / "llm_semantic_calls.jsonl").read_text().splitlines()
        if line.strip()
    ]
    original_alpha = [r for r in original_calls if r["task"] == "alpha_classifier"]
    prompt_identity_now = Week2LLMGateway.prompt_identity_sha256("alpha_classifier")
    prompt_identity_original = {r["prompt_sha256"] for r in original_alpha}

    input_identity_checks = []
    taxonomy = alpha_mapper.load_alpha_taxonomy()
    for rec in original_alpha:
        # The original input_payload IS the exact request dict; match it to
        # its frozen structured record by claim/evidence text, then rebuild
        # the payload with today's code and compare hashes.
        text = rec["input_payload"]["claim"]
        matches = [r for r in records_by_id.values() if str(r.get("claim") or "") == text]
        rebuilt_hashes = []
        for frozen in matches:
            rebuilt = {
                "claim": str(frozen.get("claim") or ""),
                "evidence": str(frozen.get("evidence") or ""),
                "ticker": str(frozen.get("ticker") or ""),
                "factors": alpha_mapper._record_factors(frozen),
                "direction": alpha_mapper.normalize_direction(frozen.get("direction")),
                "alpha_taxonomy": alpha_mapper._alpha_taxonomy_request_block(taxonomy),
            }
            rebuilt_hashes.append(sha256_canonical_json(rebuilt))
        input_identity_checks.append({
            "original_call_id": rec["call_id"],
            "original_input_sha256": rec["input_sha256"],
            "frozen_records_with_same_claim_text": len(matches),
            "rebuilt_input_sha256_candidates": rebuilt_hashes,
            "matches_original": rec["input_sha256"] in rebuilt_hashes,
        })

    def source(name: str, default_desc: str) -> str:
        return "EXPLICIT (env set by recovery launcher)" if name in RECOVERY_EXPLICIT_ENV else default_desc

    report = {
        "captured_at_note": "zero network; MockTransport only; real create_llm_client via pass-through spy",
        "create_llm_client_constructor_kwargs": constructor_calls,
        "gateway_effective_attributes": gateway_attrs,
        "serialized_request": {
            "url": str(request.url),
            "method": request.method,
            "body_keys": sorted(body),
            "body_without_messages": body_without_messages,
            "messages_count": len(body["messages"]),
            "message_roles": [m["role"] for m in body["messages"]],
            "message_content_sha256": hashlib.sha256(message_content.encode()).hexdigest(),
            "message_content_chars": len(message_content),
            "header_names": sorted(request.headers.keys()),
            "x-stainless-read-timeout": request.headers.get("x-stainless-read-timeout"),
            "x-stainless-retry-count": request.headers.get("x-stainless-retry-count"),
        },
        "request_control_snapshot": request_control,
        "parameter_provenance": {
            "model": source("COMQUTOR_WEEK2_LLM_MODEL", "code default"),
            "provider": source("COMQUTOR_WEEK2_LLM_PROVIDER", "code default"),
            "max_calls": source("COMQUTOR_WEEK2_LLM_MAX_CALLS", f"code default"),
            "application_max_retries": (
                f"EXPLICIT env by recovery launcher (=0). WARNING: repo .env sets COMQUTOR_WEEK2_LLM_MAX_RETRIES="
                f"{dotenv_file_values.get('COMQUTOR_WEEK2_LLM_MAX_RETRIES', '<absent>')}; "
                "load_dotenv is override=False, so the launcher's explicit export is the ONLY thing keeping this at 0 -- "
                "a launcher that forgets it silently gets the .env value"
            ),
            "client_level_max_retries": "hardcoded 0 by build_server_week2_llm_gateway (client_kwargs max_retries=0), not env-controlled",
            "concurrency": source("COMQUTOR_WEEK2_LLM_CONCURRENCY", "code default"),
            "request_audit": source("COMQUTOR_WEEK2_LLM_ENABLE_REQUEST_AUDIT", "code default (off)"),
            "timeout_seconds": (
                f"FROM REPO .env (={injected_by_dotenv['COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS']}s), injected by tradingagents/__init__ load_dotenv at import; "
                f"overrides the code default {DEFAULT_TIMEOUT_SECONDS}s. Not set by the recovery launcher -> a launcher/.env change silently changes it; "
                "recommend the launcher export it explicitly to freeze it"
                if "COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS" in injected_by_dotenv
                else f"code DEFAULT ({DEFAULT_TIMEOUT_SECONDS}s)"
            ),
            "alpha_classifier_max_tokens": (
                "EXPLICIT" if "COMQUTOR_WEEK2_ALPHA_CLASSIFIER_MAX_TOKENS" in os.environ
                else "DEFAULT: no per-task override, no max_tokens sent (env var deliberately unset; matches original run's request_control.max_tokens_value=None)"
            ),
            "thinking_reasoning_control": "not set by this repo's request-building path: see serialized_request.body_without_messages for exactly what the client sends (any 'thinking'/'reasoning' key would appear there)",
            "resolved_alpha_classifier_concurrency": resolve_alpha_classifier_concurrency(),
        },
        "identity_proofs_vs_original_c904d4cc": {
            "prompt_identity_now": prompt_identity_now,
            "prompt_identity_in_original_real_calls": sorted(prompt_identity_original),
            "prompt_identity_unchanged": prompt_identity_original == {prompt_identity_now},
            "request_input_identity_checks": input_identity_checks,
            "all_request_inputs_unchanged": all(c["matches_original"] for c in input_identity_checks),
        },
        "env_values_injected_by_repo_dotenv_at_import": injected_by_dotenv,
        "observed_in_original_real_alpha_calls": [
            {
                "latency_ms": round(r["latency_ms"]),
                "token_usage": r["token_usage"],
                "reasoning_tokens": (r.get("provider_response") or {}).get("raw_usage", {}).get("completion_tokens_details", {}).get("reasoning_tokens"),
                "finish_reason": (r.get("provider_response") or {}).get("finish_reason"),
                "response_model_reported_by_provider": (r.get("provider_response") or {}).get("response_model"),
            }
            for r in original_alpha
        ],
        "explicit_env_for_recovery": {k: v for k, v in RECOVERY_EXPLICIT_ENV.items() if k != "DEEPSEEK_API_KEY"},
        "env_deliberately_left_unset": list(RECOVERY_DELIBERATELY_UNSET),
    }
    OUT_PATH.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))
    print(f"\nWritten to {OUT_PATH}")


if __name__ == "__main__":
    main()
