#!/usr/bin/env python3
"""T4 delivery (round 31): request / usage / cost reconciliation of one run, OFFLINE from its saved files.

Inputs (all inside the run directory copy): tradingagents_llm_calls.jsonl (research agents), llm_semantic_calls.jsonl (Week 2
ledger, one record per logical call), error_logs/week2_llm_provider_request_audit.jsonl and ..._response_audit.jsonl (one row
per HTTP request forwarded / response received), week2_gateway_budget.json (gateway reservations, when the run wrote it),
llm_usage_report.json (the run's own usage report), structured_agent_outputs.json (claims and content-support statuses).

Every count is kept separate and named by layer and task: claims, logical calls, cache hits, gateway reservations, HTTP
requests, not sent (with reason), outcomes, requests missing usage. Costs are copied from the run's usage report with the pricing
basis from comqutor_alpha.llm.cost_basis; requests without usage are counted as not estimable, never as zero cost. No network.

    python build_usage_reconciliation.py --run-dir <run dir copy> --out <json>
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next((p for p in HERE.parents if (p / "comqutor_alpha").is_dir()), None)
if REPO is not None:
    sys.path.insert(0, str(REPO))


def jl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main(argv=None) -> int:
    from comqutor_alpha.llm import cost_basis

    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    d = Path(args.run_dir)
    agent_calls = jl(d / "tradingagents_llm_calls.jsonl")
    ledger = jl(d / "llm_semantic_calls.jsonl")
    requests = jl(d / "error_logs" / "week2_llm_provider_request_audit.jsonl")
    responses = jl(d / "error_logs" / "week2_llm_provider_response_audit.jsonl")
    usage = json.loads((d / "llm_usage_report.json").read_text(encoding="utf-8"))
    budget = json.loads((d / "week2_gateway_budget.json").read_text(encoding="utf-8")) if (d / "week2_gateway_budget.json").is_file() else None
    records = json.loads((d / "structured_agent_outputs.json").read_text(encoding="utf-8"))["records"]

    week2 = {}
    tasks = sorted({r["task"] for r in ledger} | {r["task"] for r in requests})
    task_alias = {"claim_batch_enrichment": "structured_adapter"}
    for task in tasks:
        semantic = task_alias.get(task, task)
        recs = [r for r in ledger if r["task"] == semantic]
        week2.setdefault(semantic, {})
        entry = week2[semantic]
        entry["logical_calls"] = len(recs)
        entry["served_from_cache"] = sum(1 for r in recs if (r.get("cache") or {}).get("hit"))
        entry["not_sent"] = dict(Counter(r.get("error_code") for r in recs if r["provider_status"] in ("not_called", "budget_exhausted")
                                         and not r.get("request_attempts") and not (r.get("cache") or {}).get("hit")))
        entry["ledger_attempts"] = sum(len(r.get("request_attempts") or []) for r in recs)
        entry["http_requests_wire_audit"] = entry.get("http_requests_wire_audit", 0) + sum(1 for r in requests if task_alias.get(r["task"], r["task"]) == semantic and r["task"] == task)
        entry["ledger_outcome"] = dict(Counter(f"{r['provider_status']}|{r['validation_status']}|{r.get('error_code')}" for r in recs))
        step = usage["per_step"].get(f"week2_semantic:{semantic}") or {}
        entry["usage_report"] = {k: step.get(k) for k in ("actual_http_requests", "retries", "outcomes", "requests_with_usage", "requests_missing_usage")}
        entry["usage_report"]["cost_estimate_usd"] = step.get("cost_estimate_usd")
    claims_by_task = {"alpha_classifier": len(records),
                      "content_support_verification": len({c for r in ledger if r["task"] == "content_support_verification" for c in (r.get("claim_ids") or [])})}

    # content support: claims by final status vs whether a request was sent (explains status sums vs request counts)
    cs_calls = {}
    for r in ledger:
        if r["task"] == "content_support_verification":
            for c in r.get("claim_ids") or []:
                cs_calls[c] = r
    cross = Counter()
    for rec in records:
        call = cs_calls.get(rec["claim_id"])
        if call is None:
            how = f"no_request ({rec.get('content_support_method') or 'no method'})"
        elif call.get("request_attempts"):
            how = f"request_sent ({call['validation_status']})"
        else:
            how = f"not_sent ({call.get('error_code')})"
        cross[(rec.get("content_support_status"), how)] += 1
    status_counts = Counter(rec.get("content_support_status") for rec in records)
    sent = sum(n for (status, how), n in cross.items() if how.startswith("request_sent"))
    trio = status_counts["SUPPORTS"] + status_counts["CONDITIONAL"] + status_counts["PENDING_REVIEW"]
    trio_without_request = sum(n for (status, how), n in cross.items() if status in ("SUPPORTS", "CONDITIONAL", "PENDING_REVIEW") and not how.startswith("request_sent"))
    sent_outside_trio = sum(n for (status, how), n in cross.items() if status not in ("SUPPORTS", "CONDITIONAL", "PENDING_REVIEW") and how.startswith("request_sent"))

    totals = usage["totals"]
    doc = {
        "run_id": d.name,
        "research_agent_layer": {
            "upstream_agent_outputs": usage["upstream_agents"]["count"],
            "logical_calls": len(agent_calls),
            "http_requests": totals["research_agent"]["actual_http_requests"],
            "retries": totals["research_agent"]["retries"],
            "outcomes": totals["research_agent"]["outcomes"],
            "requests_missing_usage": totals["research_agent"]["requests_missing_usage"],
            "cost_estimate_usd": totals["research_agent"]["cost_estimate_usd"],
        },
        "week2_layer": {
            "logical_calls": totals["week2_semantic"]["logical_calls"],
            "served_from_cache": totals["week2_semantic"]["served_from_cache"],
            "not_sent": totals["week2_semantic"]["not_sent"],
            "not_sent_reasons": totals["week2_semantic"]["not_sent_reasons"],
            "gateway_budget_reservations": (budget or {}).get("budget_reservations"),
            "gateway_cap": (budget or {}).get("max_calls"),
            "http_requests_wire_audit": len(requests),
            "responses_received_wire_audit": len(responses),
            "response_status_codes": dict(Counter(str(r.get("status_code")) for r in responses)),
            "http_requests_usage_report": totals["week2_semantic"]["actual_http_requests"],
            "retries": totals["week2_semantic"]["retries"],
            "outcomes": totals["week2_semantic"]["outcomes"],
            "requests_missing_usage": totals["week2_semantic"]["requests_missing_usage"],
            "cost_estimate_usd": totals["week2_semantic"]["cost_estimate_usd"],
            "by_task": week2,
            "claims_by_task": claims_by_task,
        },
        "all_layers_cost_estimate_usd": totals["all"]["cost_estimate_usd"],
        "content_support_status_vs_request": {
            "status_counts_over_all_claims": dict(status_counts),
            "crosstab": [{"final_status": s, "request": h, "claims": n} for (s, h), n in sorted(cross.items(), key=lambda kv: -kv[1])],
            "requests_sent": sent,
            "supports_plus_conditional_plus_pending_review": trio,
            "of_which_without_a_sent_request": trio_without_request,
            "sent_requests_with_other_final_status": sent_outside_trio,
            "identity": f"{trio} - {trio_without_request} + {sent_outside_trio} = {trio - trio_without_request + sent_outside_trio} (requests sent: {sent})",
        },
        "pricing": {
            "source": {f"{k[0]}:{k[1]}": v for k, v in cost_basis.PRICING_SOURCE.items()},
            "unit": "USD per 1,000,000 tokens",
            "deepseek_v4_flash_off_peak": {"input_cache_miss": cost_basis._PRICING_USD_PER_MILLION_TOKENS[("deepseek", "deepseek-v4-flash")][0],
                                           "input_cache_hit": cost_basis._CACHE_HIT_INPUT_USD_PER_MILLION_TOKENS[("deepseek", "deepseek-v4-flash")][0],
                                           "output": cost_basis._PRICING_USD_PER_MILLION_TOKENS[("deepseek", "deepseek-v4-flash")][1]},
            "deepseek_v4_flash_peak": {"input_cache_miss": cost_basis._PEAK_PRICING_USD_PER_MILLION_TOKENS[("deepseek", "deepseek-v4-flash")][0],
                                       "input_cache_hit": cost_basis._CACHE_HIT_INPUT_USD_PER_MILLION_TOKENS[("deepseek", "deepseek-v4-flash")][1],
                                       "output": cost_basis._PEAK_PRICING_USD_PER_MILLION_TOKENS[("deepseek", "deepseek-v4-flash")][1]},
            "formula": usage["pricing"]["method"],
            "scope": "estimates over the requests whose provider returned usage; requests without usage are 'not estimable' and EXCLUDED "
                     "(not counted as zero); not a bill or an actual charge",
        },
    }
    Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"agent_http": doc["research_agent_layer"]["http_requests"], "week2_http_audit": len(requests),
                      "week2_reservations": doc["week2_layer"]["gateway_budget_reservations"], "not_sent": doc["week2_layer"]["not_sent"],
                      "missing_usage": totals["all"]["requests_missing_usage"], "cs_identity": doc["content_support_status_vs_request"]["identity"],
                      "usd": totals["all"]["cost_estimate_usd"]["off_peak_floor"], "usd_peak": totals["all"]["cost_estimate_usd"]["peak_ceiling"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
