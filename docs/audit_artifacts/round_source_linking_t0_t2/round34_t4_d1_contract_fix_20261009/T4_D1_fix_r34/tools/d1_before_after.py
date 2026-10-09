#!/usr/bin/env python3
"""T4 round 34 (2026-10-09), D1 fix: run the second NVDA Fresh run's two saved claim-enrichment replies, UNCHANGED, through the
production path of whatever code is checked out (run once before and once after the fix). Zero provider calls (run it under
run_with_network_trap.py).

Path: the server gateway builder (build_server_week2_llm_gateway) + a real semantic session + the unmodified
structured_output_adapter._llm_batch_enrichment; the bottom HTTP transport answers with the run's saved reply body (wire audit).
Per saved reply it records: the prompt version / identity the ledger wrote, whether the request is the one the run sent, the
outcome, and the production validator's own message. For all 9 adapter batches it also records the request size (the
gateway's own measure) under this code, so the effect of the contract change on the 60,000-character limit is visible.

The saved replies are answers to the v1 prompt; they lack cited_source_id. Rejecting them is the expected result after the
fix as well -- nothing here edits them, and nothing here claims anything about the v2 prompt's real model behaviour.

    python tools/run_with_network_trap.py <this file> --label before --out 01_before_after/before.json
"""
from __future__ import annotations

import argparse
import inspect
import json
import os
import tempfile
from pathlib import Path

REPO = next(p for p in Path(__file__).resolve().parents if (p / "comqutor_alpha").is_dir())
RUN = REPO / "outputs" / "t4_runs" / "12591384-0b26-470d-a99d-a49c00be440b"
SEPARATOR = "\nINPUT_JSON:\n"
EMPTY_REPLY = '{"choices":[{"message":{"content":"{\\"claims\\": []}"},"finish_reason":"stop"}]}'
PROFILE_ENV = {"COMQUTOR_WEEK2_LLM_ENABLED": "1", "COMQUTOR_WEEK2_LLM_PROVIDER": "deepseek", "COMQUTOR_WEEK2_LLM_MODEL": "deepseek-v4-flash",
               "COMQUTOR_WEEK2_LLM_BASE_URL": "https://api.deepseek.com", "COMQUTOR_WEEK2_LLM_PROFILE": "t3_verified_20261008",
               "DEEPSEEK_API_KEY": "replay-not-a-key"}


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    os.environ.update(PROFILE_ENV)
    import httpx

    from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
    from comqutor_alpha.run_environment import process_code_identity
    from comqutor_alpha.structure_engine import structured_output_adapter as adapter, week2_llm as week2

    calls = sorted((r for r in _jsonl(RUN / "llm_semantic_calls.jsonl") if r["task"] == "structured_adapter"), key=lambda r: r["call_sequence"])
    requests = {r["attempt_id"]: r for r in _jsonl(RUN / "error_logs" / "week2_llm_provider_request_audit.jsonl") if r["task"] == "claim_batch_enrichment"}
    replies = {r["attempt_id"]: r for r in _jsonl(RUN / "error_logs" / "week2_llm_provider_response_audit.jsonl") if r["task"] == "claim_batch_enrichment"}
    sources = json.loads((RUN / "source_registry.json").read_text(encoding="utf-8"))["sources"]
    validator_params = set(inspect.signature(adapter._validate_llm_batch_enrichment).parameters)

    batches, saved_replies = [], []
    for call in calls:
        saved_payload = call["input_payload"]
        attempt = next((a["attempt_id"] for a in call.get("request_attempts") or []), None)
        reply_row = replies.get(attempt)
        sent: list[dict] = []

        def handler(request, _body=(reply_row["body"] if reply_row else EMPTY_REPLY)):
            sent.append(json.loads(request.content))
            return httpx.Response(200, content=_body.encode("utf-8"), headers={"content-type": "application/json"})

        with tempfile.TemporaryDirectory() as tmp:
            run_id = "r34-d1-before-after"
            (Path(tmp) / run_id).mkdir()
            gateway = week2.build_server_week2_llm_gateway(run_id, tmp, execution_id=run_id, _base_transport_for_testing=httpx.MockTransport(handler))
            gateway.attach_semantic_runtime(SemanticRuntimeSession(run_id=run_id, output_directory=Path(tmp) / run_id, execution_mode="test",
                                                                   provider="deepseek", model="deepseek-v4-flash"))
            out = adapter._llm_batch_enrichment(gateway, ticker=saved_payload["ticker"], agent=saved_payload["agent"],
                                                batch_segments=saved_payload["segments"],
                                                sources=adapter.scope_sources_for_agent(saved_payload["agent"], sources))  # as production does
            led = _jsonl(Path(tmp) / run_id / "llm_semantic_calls.jsonl")[-1]
        payload_now = led["input_payload"]
        size_now = len(json.dumps(payload_now, ensure_ascii=False, default=str))
        batches.append({"call_sequence": call["call_sequence"], "agent": saved_payload["agent"], "segments": len(saved_payload["segments"]),
                        "input_chars_in_run": len(json.dumps(saved_payload, ensure_ascii=False, default=str)), "input_chars_this_code": size_now,
                        "sent_this_code": bool(sent), "refused_locally_this_code": led["provider_status"] == "not_called"})
        if not reply_row:
            continue
        reply = json.loads(json.loads(reply_row["body"])["choices"][0]["message"]["content"])
        if "candidate_source_ids_by_segment" in validator_params:  # the fixed code: per-segment scope from the request it built
            by_segment: dict[str, set] = {}
            for cand in payload_now["candidate_sources"]:
                for sid in cand.get("segment_ids") or []:
                    by_segment.setdefault(sid, set()).update({cand["source_id"], cand["fragment_id"]})
            kwargs = {"candidate_source_ids_by_segment": {k: frozenset(v) for k, v in by_segment.items()}}
        else:
            kwargs = {"candidate_source_ids": frozenset({c["source_id"] for c in payload_now["candidate_sources"]} | {c["fragment_id"] for c in payload_now["candidate_sources"]})}
        try:
            adapter._validate_llm_batch_enrichment(reply, payload_now["segments"], **kwargs)
            message = None
        except ValueError as exc:
            message = str(exc)
        prompt = sent[0]["messages"][0]["content"].split(SEPARATOR, 1)[0] if sent else None
        saved_body = json.loads(requests[attempt]["body"])
        saved_replies.append({
            "call_sequence": call["call_sequence"], "attempt_id": attempt, "reply_items": len(reply.get("claims") or []),
            "reply_item_fields": sorted({k for item in reply.get("claims") or [] for k in item}),
            "reply_body_sha256_unchanged": __import__("hashlib").sha256(reply_row["body"].encode("utf-8")).hexdigest() == reply_row["body_sha256"],
            "ledger_prompt_version": led["prompt_version"], "ledger_prompt_sha256": led["prompt_sha256"],
            "ledger_input_schema_version": led["input_schema_version"], "ledger_output_schema_version": led["output_schema_version"],
            "prompt_mentions_cited_source_id": bool(prompt and "cited_source_id" in prompt),
            "request_body_equals_the_run's_saved_request": bool(sent) and sent[0] == saved_body,
            "outcome": {"enrichment_returned": out is not None, "provider_status": led["provider_status"], "validation_status": led["validation_status"],
                        "fallback_reason": led["fallback_reason"], "fallback_used": led["fallback_used"]},
            "production_validator_message": message,
        })

    ci = process_code_identity()
    doc = {"label": args.label, "code_identity": {k: ci.get(k) for k in ("git_head", "tracked_diff_sha256", "untracked_runtime_source_sha256")},
           "current_prompt": {"prompt_version": week2._TASK_RUNTIME_METADATA["claim_batch_enrichment"]["prompt_version"],
                              "prompt_sha256": week2.Week2LLMGateway.prompt_identity_sha256("claim_batch_enrichment")},
           "saved_replies": saved_replies, "batch_sizes": batches}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[{args.label}] code {doc['code_identity']['tracked_diff_sha256'][:8]}/{doc['code_identity']['untracked_runtime_source_sha256'][:8]} "
          f"prompt {doc['current_prompt']['prompt_version']} {doc['current_prompt']['prompt_sha256'][:12]}")
    for r in saved_replies:
        print(f"  seq {r['call_sequence']} ({r['reply_items']} items, reply unchanged={r['reply_body_sha256_unchanged']}): ledger prompt {r['ledger_prompt_version']} "
              f"| request == run's request: {r['request_body_equals_the_run\'s_saved_request']} | enrichment returned: {r['outcome']['enrichment_returned']} "
              f"| {r['outcome']['validation_status']} / {r['outcome']['fallback_reason']} | validator: {r['production_validator_message']}")
    for b in batches:
        print(f"  batch seq {b['call_sequence']} {b['agent']:<18} segs={b['segments']:<3} chars run={b['input_chars_in_run']:<6} this code={b['input_chars_this_code']:<6} refused={b['refused_locally_this_code']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
