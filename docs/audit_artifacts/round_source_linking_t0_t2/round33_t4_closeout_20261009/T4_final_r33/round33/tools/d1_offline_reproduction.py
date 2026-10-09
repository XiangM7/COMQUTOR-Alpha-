#!/usr/bin/env python3
"""T4 round 33 (2026-10-09), D1: offline reproduction of the claim-enrichment (structured adapter) outcomes of a saved Fresh run.

Zero provider calls (run it under run_with_network_trap.py). For every structured_adapter call in the run's semantic ledger:

* the saved facts: call id, sequence, attempt ids, agent, segment count, offered candidate_sources, input size (the gateway's
  own measure), provider status, error code, timing, whether a request row and a response row exist in the wire audit;
* for every call that the production gateway would actually decide on locally or with a saved reply body (local refusal,
  in-time reply, the late reply of a timed-out request): the UNMODIFIED production path -- the server gateway builder, a real
  semantic session and ``structured_output_adapter._llm_batch_enrichment`` -- with the bottom HTTP transport answering with
  the saved reply body. Checks that the production code rebuilds exactly the request the run sent, and records the outcome
  and the ledger record it writes (in a temporary directory, never in the run);
* the exact validator message: ``_validate_llm_batch_enrichment`` (production, unmodified) on the saved reply;
* per item: which fields the reply carries vs the validator's required set, and a DIAGNOSTIC control -- the same item with
  one key added, ``"cited_source_id": null`` -- through the same validator, to see whether that missing key is the only
  blocking point. The control is not a fix, is never written into any run, and never invents a source id (null = "no
  citation").

Timeouts without a saved reply body are reported from the saved records only (there is no reply to parse).

    python3 tools/run_with_network_trap.py tools/d1_offline_reproduction.py --run 12591384-0b26-470d-a99d-a49c00be440b --out 01_d1/d1_fresh2.json
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections import Counter
from pathlib import Path

REPO = next(p for p in Path(__file__).resolve().parents if (p / "comqutor_alpha").is_dir())
SEPARATOR = "\nINPUT_JSON:\n"
PROFILE_ENV = {  # the run's own Week 2 configuration (metadata.run_environment.effective_config.week2_semantic); dummy key
    "COMQUTOR_WEEK2_LLM_ENABLED": "1",
    "COMQUTOR_WEEK2_LLM_PROVIDER": "deepseek",
    "COMQUTOR_WEEK2_LLM_MODEL": "deepseek-v4-flash",
    "COMQUTOR_WEEK2_LLM_BASE_URL": "https://api.deepseek.com",
    "COMQUTOR_WEEK2_LLM_PROFILE": "t3_verified_20261008",
    "DEEPSEEK_API_KEY": "replay-not-a-key",
}


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.is_file() else []


def _send_status(call: dict, has_response: bool) -> str:
    if call["provider_status"] == "not_called":
        return "not_sent_local_refusal"
    if call["provider_status"] == "timeout":
        return "sent_timeout_reply_arrived_after_deadline" if has_response else "sent_timeout_no_reply"
    return "sent_reply_received_in_time"


def _reply_payload(body: str) -> tuple[dict, str | None]:
    reply = json.loads(body)
    choice = reply["choices"][0]
    return json.loads(choice["message"]["content"]), choice.get("finish_reason")


def _validate(adapter, payload, segments, candidate_ids) -> dict:
    try:
        adapter._validate_llm_batch_enrichment(payload, segments, candidate_source_ids=candidate_ids)
        return {"accepted": True, "message": None}
    except ValueError as exc:
        return {"accepted": False, "message": str(exc)}


def _production_path(adapter, week2, session_cls, httpx, call, sources, reply_body, saved_request_body) -> dict:
    payload = call["input_payload"]
    arrivals: list[dict] = []

    def handler(request):
        body = json.loads(request.content)
        content = body["messages"][0]["content"]
        arrivals.append({
            "input_equals_saved_payload": json.loads(content.split(SEPARATOR, 1)[1]) == payload,
            "body_equals_saved_wire_body": saved_request_body is not None and body == json.loads(saved_request_body),
        })
        return httpx.Response(200, content=reply_body.encode("utf-8"), headers={"content-type": "application/json"})

    with tempfile.TemporaryDirectory() as tmp:
        run_id = "r33-d1-offline"
        (Path(tmp) / run_id).mkdir()
        gateway = week2.build_server_week2_llm_gateway(run_id, tmp, execution_id=run_id,
                                                       _base_transport_for_testing=httpx.MockTransport(handler))
        session = session_cls(run_id=run_id, output_directory=Path(tmp) / run_id, execution_mode="test", provider="deepseek",
                              model="deepseek-v4-flash")
        gateway.attach_semantic_runtime(session)
        budget_before = gateway.call_count
        out = adapter._llm_batch_enrichment(gateway, ticker=payload["ticker"], agent=payload["agent"],
                                            batch_segments=payload["segments"], sources=sources)
        ledger = _jsonl(Path(tmp) / run_id / "llm_semantic_calls.jsonl")
        rec = ledger[-1] if ledger else {}
        return {
            "enrichment_returned": out is not None,
            "transport_arrivals": len(arrivals),
            "budget_reservations": gateway.call_count - budget_before,
            "request_rebuilt_by_production_equals_saved": all(a["input_equals_saved_payload"] for a in arrivals) if arrivals else None,
            "request_body_equals_saved_wire_body": all(a["body_equals_saved_wire_body"] for a in arrivals) if arrivals else None,
            "ledger_record": {k: rec.get(k) for k in ("provider_status", "error_code", "validation_status", "fallback_reason", "fallback_used")},
        }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    os.environ.update(PROFILE_ENV)
    import httpx

    from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
    from comqutor_alpha.structure_engine import structured_output_adapter as adapter, week2_llm as week2

    run_dir = REPO / "outputs" / "t4_runs" / args.run
    ledger = [r for r in _jsonl(run_dir / "llm_semantic_calls.jsonl") if r["task"] == "structured_adapter"]
    requests = {r["attempt_id"]: r for r in _jsonl(run_dir / "error_logs" / "week2_llm_provider_request_audit.jsonl") if r["task"] == "claim_batch_enrichment"}
    replies = {r["attempt_id"]: r for r in _jsonl(run_dir / "error_logs" / "week2_llm_provider_response_audit.jsonl") if r["task"] == "claim_batch_enrichment"}
    sources = json.loads((run_dir / "source_registry.json").read_text(encoding="utf-8"))["sources"]
    required = sorted(adapter._LLM_BATCH_ENRICHMENT_REQUIRED_FIELDS)

    rows = []
    for call in sorted(ledger, key=lambda r: r["call_sequence"]):
        payload = call["input_payload"]
        attempt_ids = [a["attempt_id"] for a in call.get("request_attempts") or []]
        reply_row = next((replies[a] for a in attempt_ids if a in replies), None)
        request_row = next((requests[a] for a in attempt_ids if a in requests), None)
        candidate_ids = frozenset({s.get("source_id") for s in payload["candidate_sources"]} | {s.get("fragment_id") for s in payload["candidate_sources"]}) - {None}
        row = {
            "call_sequence": call["call_sequence"],
            "call_id": call["call_id"],
            "attempt_ids": attempt_ids,
            "agent": payload["agent"],
            "segments": len(payload["segments"]),
            "candidate_sources_offered": len(payload["candidate_sources"]),
            "input_chars": len(json.dumps(payload, ensure_ascii=False, default=str)),
            "input_limit_chars": week2.MAX_PROMPT_PAYLOAD_CHARS,
            "started_at": call.get("started_at"),
            "completed_at": call.get("completed_at"),
            "latency_ms": round(call["latency_ms"]) if call.get("latency_ms") is not None else None,
            "saved": {k: call.get(k) for k in ("provider_status", "error_code", "validation_status", "fallback_reason")},
            "wire_audit_request_row": request_row is not None,
            "wire_audit_request_at": request_row.get("created_at") if request_row else None,
            "wire_audit_reply_row": reply_row is not None,
            "wire_audit_reply_at": reply_row.get("created_at") if reply_row else None,
            "wire_audit_reply_status": reply_row.get("status_code") if reply_row else None,
        }
        row["send_status"] = _send_status(call, reply_row is not None)
        if row["send_status"] != "sent_timeout_no_reply":
            reply_body = reply_row["body"] if reply_row else '{"choices":[{"message":{"content":"{}"},"finish_reason":"stop"}]}'
            row["production_path"] = _production_path(adapter, week2, SemanticRuntimeSession, httpx, call, sources, reply_body,
                                                      request_row["body"] if request_row else None)
        if reply_row:
            reply, finish = _reply_payload(reply_row["body"])
            items = reply.get("claims") or []
            field_sets = Counter(tuple(sorted(item)) for item in items if isinstance(item, dict))
            row["reply"] = {
                "finish_reason": finish,
                "items": len(items),
                "item_field_sets": [{"fields": list(k), "items": v, "missing_vs_validator": sorted(set(required) - set(k)),
                                     "extra_vs_validator": sorted(set(k) - set(required))} for k, v in field_sets.items()],
                "any_item_mentions_cited_source_id": any("cited_source_id" in item for item in items if isinstance(item, dict)),
            }
            row["production_validator_on_saved_reply"] = _validate(adapter, reply, payload["segments"], candidate_ids)
            by_id = {s["segment_id"]: s for s in payload["segments"]}
            per_item = []
            for item in items:
                seg = by_id.get(item.get("segment_id")) if isinstance(item, dict) else None
                as_saved = _validate(adapter, {"claims": [item]}, [seg], candidate_ids) if seg else {"accepted": False, "message": "segment_id not in request"}
                control = _validate(adapter, {"claims": [{**item, "cited_source_id": None}]}, [seg], candidate_ids) if seg else as_saved
                per_item.append({"segment_id": item.get("segment_id"), "as_saved": as_saved, "control_with_null_citation": control})
            whole_control = _validate(adapter, {"claims": [{**i, "cited_source_id": None} for i in items]}, payload["segments"], candidate_ids)
            row["diagnostic_control"] = {
                "what": "the saved reply with one added key per item, cited_source_id = null (no citation); not a fix, never written into a run",
                "whole_batch": whole_control,
                "items_accepted_as_saved": sum(1 for p in per_item if p["as_saved"]["accepted"]),
                "items_accepted_with_null_citation": sum(1 for p in per_item if p["control_with_null_citation"]["accepted"]),
                "remaining_failures_with_null_citation": Counter(p["control_with_null_citation"]["message"] for p in per_item
                                                                 if not p["control_with_null_citation"]["accepted"]),
                "per_item": per_item,
            }
        rows.append(row)

    doc = {
        "run_id": args.run,
        "validator_required_fields": required,
        "frozen_instruction_fields": ["segment_id", "claim", "evidence", "source_section", "entities", "factors", "direction", "confidence"],
        "send_status_counts": Counter(r["send_status"] for r in rows),
        "calls": rows,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=list) + "\n", encoding="utf-8")
    for r in rows:
        pp = r.get("production_path") or {}
        dc = r.get("diagnostic_control") or {}
        print(f"seq {r['call_sequence']} {r['agent']:<22} segs={r['segments']:<3} cand={r['candidate_sources_offered']:<3} chars={r['input_chars']:<6} "
              f"{r['send_status']:<42} saved={r['saved']['error_code']} | prod: arrivals={pp.get('transport_arrivals')} "
              f"req==saved={pp.get('request_rebuilt_by_production_equals_saved')} body==wire={pp.get('request_body_equals_saved_wire_body')} "
              f"ledger={pp.get('ledger_record', {}).get('error_code')} | validator={(r.get('production_validator_on_saved_reply') or {}).get('message')} "
              f"| control: whole={dc.get('whole_batch', {}).get('accepted')} items_ok={dc.get('items_accepted_with_null_citation')}/{(r.get('reply') or {}).get('items')}")
    print("send status:", dict(doc["send_status_counts"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
