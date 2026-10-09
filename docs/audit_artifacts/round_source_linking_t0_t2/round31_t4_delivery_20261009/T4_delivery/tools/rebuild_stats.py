#!/usr/bin/env python3
"""T4 delivery (round 31): rebuild every figure the main report quotes, OFFLINE and independently, from the package's own files
(standard library only; no repository code, no network, no database), and compare with report_figures.json.

Two independent sources are used and cross-checked:
  - the run's raw artifacts under runs/<run_id>/ (structured outputs, Alpha matches, structure graph, conflicts, semantic
    ledger, wire audit, gateway budget, research-agent call log; cost recomputed from token usage and the pricing table);
  - the claim ledgers under ledgers/<run>/ (built with the production evidence-trace code).

    python3 tools/rebuild_stats.py            # prints the comparison; exit 0 only if every figure matches and is cited
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent
RUNS = {"run2": ("12591384-0b26-470d-a99d-a49c00be440b", "run2_12591384"), "run1": ("fa642639-8d93-4f9a-9de1-2c4d789eade8", "run1_fa642639")}
TRIO = ("SUPPORTS", "CONDITIONAL", "PENDING_REVIEW")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def jl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.is_file() else []


def rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def rebuild_run(key: str) -> dict:
    run_id, rec = RUNS[key]
    d, led = PKG / "runs" / run_id, PKG / "ledgers" / rec
    out: dict[str, object] = {}
    records = load(d / "structured_agent_outputs.json")["records"]
    matches = load(d / "alpha_matches.json")["matches"]
    graph = load(d / "structure_graph.json")
    conflicts = load(d / "conflicts.json")
    ledger = jl(d / "llm_semantic_calls.jsonl")
    agent_calls = jl(d / "tradingagents_llm_calls.jsonl")
    wire = jl(d / "error_logs" / "week2_llm_provider_request_audit.jsonl")
    budget = load(d / "week2_gateway_budget.json")
    pricing = load(PKG / "usage_cost" / f"usage_reconciliation_{rec}.json")["pricing"]

    out["claims"] = len(records)
    out["alpha_final_match"] = sum(1 for m in matches if m.get("matched_alpha"))
    out["alpha_final_none"] = sum(1 for m in matches if m.get("match_status") == "no_match")
    out["alpha_classification_unavailable"] = sum(1 for m in matches if m.get("match_status") not in ("matched", "no_match"))
    out["alpha_raw_model_selection"] = sum(1 for m in matches if m.get("llm_selected_alpha_id"))
    out["alpha_gate_override"] = sum(1 for m in matches if m.get("llm_selected_alpha_id") and not m.get("matched_alpha"))
    out["alpha_override_invalidation"] = sum(1 for m in matches if m.get("alpha_specific_invalidation_override"))
    out["alpha_override_positive_requirement"] = sum(1 for m in matches if m.get("alpha_positive_requirement_override"))
    for alpha, n in Counter(m.get("matched_alpha") for m in matches if m.get("matched_alpha")).items():
        out[f"alpha_final_{alpha}"] = n
    cs = Counter(r.get("content_support_status") for r in records)
    for status in ("SUPPORTS", "CONDITIONAL", "PENDING_REVIEW", "BACKGROUND", "OPPOSES", "NOT_APPLICABLE"):
        out[f"cs_{status}"] = cs.get(status, 0)
    out["cs_trio_sum"] = sum(cs.get(s, 0) for s in TRIO)
    out["cs_supports_automated_no_request"] = sum(1 for r in records if r.get("content_support_status") == "SUPPORTS"
                                                  and r.get("content_support_method") == "AUTOMATED_DATA_FACT_VERIFIED")
    out["cs_not_applicable_not_linked"] = sum(1 for r in records if r.get("content_support_status") == "NOT_APPLICABLE" and r.get("content_support_method") == "NOT_LINKED")
    out["cs_not_applicable_no_source_registry"] = sum(1 for r in records if r.get("content_support_status") == "NOT_APPLICABLE"
                                                      and r.get("content_support_method") == "NO_SOURCE_REGISTRY")
    cs_calls = {c: r for r in ledger if r["task"] == "content_support_verification" for c in (r.get("claim_ids") or [])}
    sent = {c for c, r in cs_calls.items() if r.get("request_attempts")}
    out["cs_requests_sent"] = sum(1 for r in ledger if r["task"] == "content_support_verification" and r.get("request_attempts"))
    out["cs_ledger_records"] = sum(1 for r in ledger if r["task"] == "content_support_verification")
    out["cs_not_sent_input_too_large"] = sum(1 for r in ledger if r["task"] == "content_support_verification" and not r.get("request_attempts")
                                             and r.get("error_code") == "WEEK2_LLM_INPUT_TOO_LARGE")
    out["cs_trio_without_request"] = sum(1 for r in records if r.get("content_support_status") in TRIO and r["claim_id"] not in sent)
    out["cs_sent_other_status"] = sum(1 for r in records if r.get("content_support_status") not in TRIO and r["claim_id"] in sent)
    out["cs_sent_supports_material_remainder_conditional"] = sum(
        1 for r in records if r.get("content_support_status") == "CONDITIONAL" and r["claim_id"] in sent
        and ((cs_calls[r["claim_id"]].get("validated_output") or {}).get("items") or [{}])[0].get("status") == "SUPPORTS")
    out["cs_sent_llm_insufficient_pending"] = sum(
        1 for r in records if r.get("content_support_status") == "PENDING_REVIEW" and r["claim_id"] in sent
        and cs_calls[r["claim_id"]].get("validation_status") == "accepted")
    out["cs_sent_rejected_pending"] = sum(1 for r in records if r.get("content_support_status") == "PENDING_REVIEW" and r["claim_id"] in sent
                                          and cs_calls[r["claim_id"]].get("validation_status") == "rejected")

    pool = {str(det.get("claim_id")): a.get("alpha_id") for a in (graph.get("activation") or {}).get("alphas") or []
            for det in a.get("evidence_detail") or [] if det.get("claim_id")}
    out["pool_claims_structure_graph"] = len(pool)
    out["active_alphas"] = len(graph.get("active_alphas") or [])
    out["dominant_alphas"] = len(graph.get("dominant_alphas") or [])
    out["candidate_alphas"] = len(graph.get("candidate_alphas") or [])
    a301 = next((a for a in (graph.get("activation") or {}).get("alphas") or [] if a.get("alpha_id") == "A301"), {})
    out["A301_activation_score"] = a301.get("activation_score")
    out["admitted_conflicts"] = conflicts.get("admitted_conflict_count")
    evaluations = (conflicts.get("arbitration") or {}).get("candidate_evaluations") or []
    out["conflict_pairs_evaluated"] = len(evaluations)
    out["conflict_pairs_direction_role_unresolved"] = sum(1 for e in evaluations if "DIRECTION_ROLE_UNRESOLVED" in (e.get("reason_codes") or []))

    attempts = {}
    for r in ledger:
        for a in r.get("request_attempts") or []:
            attempts[(r["task"], a["attempt_id"])] = a
    out["agent_http_requests"] = len(agent_calls)
    out["agent_retries"] = sum(int(c.get("retry_count") or 0) for c in agent_calls)
    out["week2_http_requests_wire_audit"] = len(wire)
    out["week2_ledger_attempts"] = len(attempts)
    out["week2_budget_reservations"] = budget.get("budget_reservations")
    out["week2_retries"] = sum(int(r.get("retry_count") or 0) for r in ledger) + sum(max(0, len(r.get("request_attempts") or []) - 1) for r in ledger)
    out["week2_served_from_cache"] = sum(1 for r in ledger if (r.get("cache") or {}).get("hit"))
    out["week2_not_sent"] = sum(1 for r in ledger if not r.get("request_attempts") and not (r.get("cache") or {}).get("hit"))
    out["week2_timeouts"] = sum(1 for a in attempts.values() if a.get("provider_status") == "timeout")
    out["week2_transport_errors"] = sum(1 for a in attempts.values() if a.get("provider_status") == "provider_error")
    out["requests_missing_usage"] = sum(1 for a in attempts.values() if not a.get("raw_usage")) + sum(1 for c in agent_calls if not c.get("token_usage"))
    off, peak = pricing["deepseek_v4_flash_off_peak"], pricing["deepseek_v4_flash_peak"]
    floor = ceiling = 0.0
    for a in attempts.values():
        u = a.get("raw_usage")
        if not u:
            continue
        hit = u.get("prompt_cache_hit_tokens")
        miss = u.get("prompt_cache_miss_tokens")
        if hit is None or miss is None:
            hit, miss = 0, u.get("prompt_tokens") or 0
        outp = u.get("completion_tokens") or 0
        floor += (miss * off["input_cache_miss"] + hit * off["input_cache_hit"] + outp * off["output"]) / 1e6
        ceiling += (miss * peak["input_cache_miss"] + hit * peak["input_cache_hit"] + outp * peak["output"]) / 1e6
    for c in agent_calls:
        u = c.get("token_usage") or {}
        floor += ((u.get("input_tokens") or 0) * off["input_cache_miss"] + (u.get("output_tokens") or 0) * off["output"]) / 1e6
        ceiling += ((u.get("input_tokens") or 0) * peak["input_cache_miss"] + (u.get("output_tokens") or 0) * peak["output"]) / 1e6
    out["usd_off_peak_floor"] = round(floor, 2)
    out["usd_peak_ceiling"] = round(ceiling, 2)

    claim_rows = rows(led / "claims.csv")
    out["ledger_rows"] = len(claim_rows)
    out["ledger_in_official_pool"] = sum(1 for r in claim_rows if r["in_official_pool"] == "True")
    out["ledger_verified_support_eligible"] = sum(1 for r in claim_rows if r["verified_support_eligible"] == "True")
    out["ledger_missing_written_as_zero_or_none"] = sum(1 for r in claim_rows for k in ("source_ids", "content_support_method", "alpha_raw_model_selection")
                                                        if r[k] in ("", "0", "NONE"))
    key_rows = rows(led / "key_conclusions.csv")
    ks = Counter(r["source_support"] for r in key_rows)
    out["key_conclusions"] = len(key_rows)
    out["key_verified_support"] = ks.get("VERIFIED_SUPPORT", 0)
    out["key_partial_support"] = ks.get("PARTIAL_SUPPORT", 0)
    out["key_scored"] = sum(1 for r in key_rows if r["scoring"] != "NOT_SCORED")
    sup = rows(led / "supports.csv")
    out["supports_rows"] = len(sup)
    out["supports_matched"] = sum(1 for r in sup if r["alpha_match_status_code"] == "MATCHED")
    out["supports_model_none"] = sum(1 for r in sup if r["alpha_match_status_code"] == "MODEL_NONE")
    out["supports_in_pool"] = sum(1 for r in sup if r["in_official_pool"] == "True")
    out["supports_non_analytical"] = sum(1 for r in sup if r["not_scored_code"] == "NON_ANALYTICAL_QUALITY")
    # cross-checks between the two sources
    out["check_pool_ledger_equals_structure_graph"] = out["ledger_in_official_pool"] == sum(
        1 for c in pool if next((r for r in claim_rows if r["claim_id"] == c), {}).get("in_official_pool") == "True")
    out["check_ledger_rows_equal_claims"] = out["ledger_rows"] == out["claims"]
    out["check_reservations_equal_wire_audit_equal_attempts"] = out["week2_budget_reservations"] == out["week2_http_requests_wire_audit"] == out["week2_ledger_attempts"]
    out["check_cs_identity"] = out["cs_trio_sum"] - out["cs_trio_without_request"] + out["cs_sent_other_status"] == out["cs_requests_sent"]
    return out


def main() -> int:
    rebuilt = {f"{k}.{name}": value for k in RUNS for name, value in rebuild_run(k).items()}
    figures = load(PKG / "report_figures.json")
    report = (PKG / figures["report_file"]).read_text(encoding="utf-8")
    results, ok = [], True
    for fig in figures["figures"]:
        got = rebuilt.get(fig["id"], "<not rebuilt>")
        match = got == fig["value"]
        cited = fig["cited_as"] in report
        ok &= match and cited
        results.append({"id": fig["id"], "report_value": fig["value"], "rebuilt": got, "match": match, "cited_as": fig["cited_as"], "cited_in_report": cited})
    checks = {k: v for k, v in rebuilt.items() if ".check_" in k}
    ok &= all(checks.values())
    zero_none = {k: v for k, v in rebuilt.items() if k.endswith("ledger_missing_written_as_zero_or_none")}
    ok &= not any(zero_none.values())
    for r in results:
        print(("OK  " if r["match"] and r["cited_in_report"] else "FAIL"), r["id"], "report=", r["report_value"], "rebuilt=", r["rebuilt"],
              "" if r["cited_in_report"] else f"NOT CITED: {r['cited_as']!r}")
    print("cross-checks:", json.dumps(checks), "| missing values written as 0/NONE/empty:", json.dumps(zero_none))
    print(f"figures: {len(results)}, mismatched: {sum(1 for r in results if not r['match'])}, not cited: {sum(1 for r in results if not r['cited_in_report'])}")
    if "--json" in sys.argv:
        print(json.dumps({"rebuilt": rebuilt, "results": results}, ensure_ascii=False, default=str))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
