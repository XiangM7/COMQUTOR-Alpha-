#!/usr/bin/env python3
"""T4 round 32: diagnostic appendix of the requests both NVDA Fresh runs never sent because the input exceeded the local
60,000-character limit -- the HISTORICAL records are not rewritten; this appendix states, per request, what the saved record
says and what actually happened. Read-only, standard library only.

Per request: task, claim / batch, the input size measured exactly as the gateway measures it
(``json.dumps(payload, ensure_ascii=False, default=str)``, Week2LLMGateway.invoke_json_with_trace), the limit, call id,
attempts, whether a wire-audit request row exists, the budget evidence, usage, the saved label and the correct reading.

    python not_sent_appendix.py --out 03_not_sent/not_sent_appendix.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
RUNS = {"run2_12591384": "12591384-0b26-470d-a99d-a49c00be440b", "run1_fa642639": "fa642639-8d93-4f9a-9de1-2c4d789eade8"}
LIMIT = 60_000  # week2_llm.MAX_PROMPT_PAYLOAD_CHARS (unchanged this round)


def jl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.is_file() else []


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    doc = {"limit_chars": LIMIT, "measurement": "len(json.dumps(input_payload, ensure_ascii=False, default=str)) -- the gateway's own check",
           "runs": {}}
    for label, run_id in RUNS.items():
        d = REPO / "outputs" / "t4_runs" / run_id
        ledger = jl(d / "llm_semantic_calls.jsonl")
        wire_call_ids = {r.get("semantic_call_id") for r in jl(d / "error_logs" / "week2_llm_provider_request_audit.jsonl")}
        budget = json.loads((d / "week2_gateway_budget.json").read_text(encoding="utf-8")) if (d / "week2_gateway_budget.json").is_file() else {}
        attempts_total = sum(len(r.get("request_attempts") or []) for r in ledger)
        records = {r["claim_id"]: r for r in json.loads((d / "structured_agent_outputs.json").read_text(encoding="utf-8"))["records"]}
        rows = []
        for r in ledger:
            if r.get("error_code") != "WEEK2_LLM_INPUT_TOO_LARGE":
                continue
            size = len(json.dumps(r["input_payload"], ensure_ascii=False, default=str))
            payload = r["input_payload"]
            batch = payload.get("segments") or payload.get("items") or []
            claim_ids = r.get("claim_ids") or []
            row = {
                "task": r["task"], "call_id": r["call_id"], "call_sequence": r.get("call_sequence"), "started_at": r.get("started_at"),
                "claim_ids": claim_ids,
                "batch": {"agent": payload.get("agent"), "segments_or_items": len(batch)} if r["task"] == "structured_adapter" else None,
                "input_chars": size, "limit_chars": LIMIT, "over_limit_by": size - LIMIT,
                "request_attempts": len(r.get("request_attempts") or []), "wire_audit_request_row": r["call_id"] in wire_call_ids,
                "http_requests_sent": 0 if not r.get("request_attempts") and r["call_id"] not in wire_call_ids else "CHECK",
                "provider_status": r.get("provider_status"), "validation_status": r.get("validation_status"),
                "token_usage": r.get("token_usage"), "usage": "none: no request was sent, so no usage and no cost exist (not 'unknown')",
                "saved_fallback_reason": r.get("fallback_reason"),
                "saved_claim_label": (records.get(claim_ids[0]) or {}).get("content_support_llm_fallback_reason") if claim_ids else None,
                "saved_claim_status": (records.get(claim_ids[0]) or {}).get("content_support_status") if claim_ids else None,
                "correct_reading": "not sent: refused locally because the input exceeded the limit; no provider response exists",
                "label_is_wrong": r.get("fallback_reason") == "malformed_response",
            }
            rows.append(row)
        doc["runs"][label] = {
            "run_id": run_id, "not_sent": len(rows), "by_task": {t: sum(1 for x in rows if x["task"] == t) for t in sorted({x["task"] for x in rows})},
            "saved_label_malformed_response": sum(1 for x in rows if x["label_is_wrong"]),
            "budget_evidence": {"gateway_budget_reservations": budget.get("budget_reservations"), "ledger_http_attempts": attempts_total,
                                "reading": "reservations == attempts, and the size check precedes the reservation in the code "
                                           "(week2_llm.invoke_json_with_trace) -- so a never-sent request reserved no budget unit"},
            "requests": rows,
        }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: {kk: v[kk] for kk in ("not_sent", "by_task", "saved_label_malformed_response", "budget_evidence")} for k, v in doc["runs"].items()},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
