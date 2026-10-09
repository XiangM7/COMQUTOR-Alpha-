#!/usr/bin/env python3
"""T4 delivery (round 31): per-claim evidence / adoption ledger of one run, built OFFLINE from its saved artifacts.

Reads only the run directory (the original `outputs/t4_runs/<run_id>/` or the unzipped Export of the run, which carries every
file needed) and calls the production evidence-trace code (`comqutor_alpha.api.evidence_trace.load_trace_context`,
`build_claim_trace`, `build_key_conclusions` -- the same functions behind GET /api/research/{run_id}/evidence-trace). No
network, no database, no model call, no re-scoring: every value is what the run saved; a value the run did not save is written
"未记录" (not recorded) or "未执行" (step not executed) -- never 0, NONE or "not supported".

    python build_claim_ledger.py --run-dir <dir named by run_id> --out-dir <new dir>

Outputs: claims.json / claims.csv (every claim), key_conclusions.json / .csv, supports.json / .csv (content-support SUPPORTS),
stats.json (the counts the report quotes).

weight_contribution_read_time is what the production trace computes when the page or API reads the run (saved lexical match
score x relation weight x assertion weight, the number the UI shows); it is not a separately saved field and not a marginal
contribution. not_scored_code is the FIRST gate that stops a claim; the gates after it were not evaluated ("未检验").
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next((p for p in HERE.parents if (p / "comqutor_alpha").is_dir()), None)
if REPO is not None:
    sys.path.insert(0, str(REPO))

NR = "未记录"
NE = "未执行"


def v(value, missing=NR):
    if value is None or value == "" or value == []:
        return missing
    if isinstance(value, (list, tuple)):
        return ";".join(str(x) for x in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None) -> int:
    from comqutor_alpha.api.evidence_trace import build_claim_trace, build_key_conclusions, load_trace_context
    from comqutor_alpha.structure_engine.alpha_mapper import compute_alpha_classification_completion

    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)
    run_dir = Path(args.run_dir).resolve()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ctx = load_trace_context(run_dir.name, str(run_dir.parent))
    if ctx is None:
        print("cannot load the run's saved artifacts", file=sys.stderr)
        return 2
    alpha_level = {aid: (b.get("activation_level") or b.get("qualified_level") or b.get("status")) for aid, b in ctx.alpha_blocks.items()}
    # content-support request per claim from the run's semantic ledger (absent from an Export-only directory -> 未记录)
    ledger_path = run_dir / "llm_semantic_calls.jsonl"
    cs_request: dict[str, str] = {}
    if ledger_path.is_file():
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            call = json.loads(line) if line.strip() else None
            if not call or call.get("task") != "content_support_verification":
                continue
            state = (f"sent ({call.get('validation_status')})" if call.get("request_attempts")
                     else f"not_sent ({call.get('error_code')})")
            for claim_id in call.get("claim_ids") or []:
                cs_request[str(claim_id)] = state

    claims, rows = [], []
    for record in ctx.records:
        cid = str(record.get("claim_id"))
        t = build_claim_trace(ctx, cid)
        match = ctx.matches_by_id.get(cid) or {}
        ss, cs, el = t["source_support"], t["source_support"]["content_support"], t["source_support"]["eligibility"]
        am, st, sc, dep = t["alpha_match"], t["stance"], t["scoring"], t["dependency"]
        cs_ran = record.get("content_support_status") not in (None, "NOT_APPLICABLE")  # NOT_APPLICABLE: no source to check, no request
        no_link = ss["link"]["status"] in (None, "NOT_PROVIDED")
        src_missing = "未记录（无链接来源）" if no_link else NR
        no_final = "未执行（无最终 Alpha 匹配）"
        final_alpha = am.get("matched_alpha")
        claims.append(t)
        loc = t["claim"]["report_location"]
        rows.append({
            "claim_id": cid,
            "agent": v(t["claim"]["agent"]),
            "report_section": v(loc.get("section")),
            "agent_output_id": v(loc.get("agent_output_id")),
            "claim_index": v(loc.get("claim_index")),
            "context_paragraph": v(loc.get("paragraph")),
            "claim_text": v(t["claim"]["text"]),
            "claim_quality": v(t["claim"]["claim_quality"]),
            "key_conclusion_group": v(t["claim"]["key_conclusion_group"], "否"),
            "source_ids": v([s.get("source_id") for s in t["sources"]], src_missing),
            "source_fragments": v([s.get("fragment_id") for s in t["sources"] if s.get("fragment_id")], src_missing),
            "source_content_hashes": v([s.get("content_hash") for s in t["sources"] if s.get("content_hash")], src_missing),
            "source_content_available": v([("saved" if s.get("has_saved_content") else "not_saved") for s in t["sources"]], src_missing),
            "source_link_status": v(ss["link"]["status"]),
            "source_link_method": v(ss["link"]["method"]),
            "source_support_status_code": v(ss["status_code"]),
            "content_support_status": v(cs["status"]),
            "content_support_request_ledger": cs_request.get(cid, ("no_request" if ledger_path.is_file() else NR)),
            "content_support_method": v(cs["method"], NE if not cs_ran else NR),
            "content_support_llm_status": v(cs["llm_status"], NE if not cs_ran else NR),
            "content_support_basis": v(cs["support_basis"], NE if not cs_ran else NR),
            "content_support_fallback_reason": v(cs["fallback_reason"], "无" if cs_ran else NE),
            "verified_support_eligible": el["eligible"],
            "verified_support_eligibility_reason": v(el["reason_code"]),
            "alpha_raw_model_selection": v(am.get("llm_selected_alpha_id"), "NONE（模型未选择）" if am.get("alpha_match_method") == "llm" else NR),
            "alpha_final_match": v(final_alpha, "无最终匹配" if am.get("alpha_match_method") == "llm" else NR),
            "alpha_match_status_code": v(am.get("status_code")),
            "alpha_gate_override": v(am.get("mapper_override"), "无"),
            "alpha_match_method": v(am.get("alpha_match_method")),
            "alpha_fallback_reason": v(match.get("alpha_match_fallback_reason"), "无"),
            "relation_text_rule": v(st.get("relation"), NR if final_alpha else no_final),
            "assertion_status_text_rule": v(st.get("assertion_status"), NR if final_alpha else no_final),
            "relation_authority": "确定性文字规则（claim_semantics；PD-006 未批准 LLM 方向覆盖）" if st.get("relation") else (NR if final_alpha else no_final),
            "evidence_stance": v(st.get("evidence_stance"), NR if final_alpha else no_final),
            "evidence_stance_method": v(st.get("method"), NR if final_alpha else no_final),
            "stance_status_code": v(st.get("status_code")),
            "evidence_fact_group_members": v(dep.get("same_evidence_fact_members"), "无分组"),
            "in_official_pool": sc.get("in_official_pool"),
            "scoring_status_code": v(sc.get("status_code")),
            "not_scored_code": v(sc.get("not_scored_code"), "不适用（已入池）" if sc.get("in_official_pool") else NR),
            "later_gates_after_first_exclusion": "均已通过（入池）" if sc.get("in_official_pool") else "未检验（只记录第一个排除条件）",
            "scoring_reason": v(sc.get("reason")),
            "scoring_alpha_id": v(sc.get("alpha_id"), "无"),
            "weight_contribution_read_time": v(sc.get("weight_contribution"), "不适用（未入池）" if not sc.get("in_official_pool") else NR),
            "final_alpha_level": v(alpha_level.get(str(final_alpha)) if final_alpha else None, "无最终匹配"),
        })

    fields = list(rows[0])
    with (out / "claims.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    (out / "claims.json").write_text(json.dumps({"run_id": ctx.run_id, "claim_count": len(claims), "claims": claims}, ensure_ascii=False, default=str) + "\n",
                                     encoding="utf-8")

    key = build_key_conclusions(ctx)
    key_rows = []
    for group in key.get("groups") or []:
        for r in group.get("rows") or []:
            row = next(x for x in rows if x["claim_id"] == r["claim_id"])
            key_rows.append({"group": group.get("group"), "claim_id": r["claim_id"], "claim_text": r.get("text"),
                             "source_support": r["source_support"]["status_code"], "alpha_match": r["alpha_match"]["status_code"],
                             "stance": r["stance"]["status_code"], "scoring": r["scoring"]["status_code"],
                             "source_ids": row["source_ids"], "content_support_status": row["content_support_status"],
                             "content_support_fallback_reason": row["content_support_fallback_reason"],
                             "alpha_raw_model_selection": row["alpha_raw_model_selection"], "alpha_final_match": row["alpha_final_match"],
                             "in_official_pool": row["in_official_pool"], "not_scored_code": row["not_scored_code"],
                             "final_alpha_level": row["final_alpha_level"]})
    (out / "key_conclusions.json").write_text(json.dumps(key, ensure_ascii=False, default=str, indent=1) + "\n", encoding="utf-8")
    with (out / "key_conclusions.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(key_rows[0]))
        writer.writeheader()
        writer.writerows(key_rows)

    support_rows = [r for r in rows if r["content_support_status"] == "SUPPORTS"]
    (out / "supports.json").write_text(json.dumps(support_rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with (out / "supports.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(support_rows)

    matches_payload = {"matches": ctx.matches}
    raw_selected = [m for m in ctx.matches if m.get("llm_selected_alpha_id")]
    final_selected = [m for m in ctx.matches if m.get("matched_alpha")]
    overridden = [m for m in raw_selected if not m.get("matched_alpha")]
    conflicts = json.loads((run_dir / "conflicts.json").read_text(encoding="utf-8"))
    evaluations = (conflicts.get("arbitration") or {}).get("candidate_evaluations") or []
    stats = {
        "run_id": ctx.run_id,
        "inputs_sha256": {name: _sha(run_dir / name) for name in ("structured_agent_outputs.json", "alpha_matches.json", "source_registry.json",
                                                                   "structure_graph.json", "conflicts.json", "raw_agent_outputs.json")},
        "claims": len(rows),
        "alpha_classification_completion": compute_alpha_classification_completion(matches_payload),
        "alpha_raw_model_selection_count": len(raw_selected),
        "alpha_final_match_count": len(final_selected),
        "alpha_raw_selection_overridden_by_gate": len(overridden),
        "alpha_gate_override_reasons": dict(Counter(r["alpha_gate_override"] for r in rows if r["alpha_gate_override"] != "无")),
        "alpha_final_by_alpha": dict(Counter(m.get("matched_alpha") for m in final_selected).most_common()),
        "content_support_status": dict(Counter(r["content_support_status"] for r in rows)),
        "content_support_fallback_reason": dict(Counter(r["content_support_fallback_reason"] for r in rows if r["content_support_fallback_reason"] not in ("无", NE))),
        "source_support_status_code": dict(Counter(r["source_support_status_code"] for r in rows)),
        "verified_support_eligible": sum(1 for r in rows if r["verified_support_eligible"] is True),
        "in_official_pool": sum(1 for r in rows if r["in_official_pool"] is True),
        "scoring_status_code": dict(Counter(r["scoring_status_code"] for r in rows)),
        "not_scored_code": dict(Counter(r["not_scored_code"] for r in rows)),
        "key_conclusions": {"claim_count": key.get("claim_count"), "status_counts": key.get("status_counts")},
        "supports": {"count": len(support_rows),
                     "alpha_match_status": dict(Counter(r["alpha_match_status_code"] for r in support_rows)),
                     "in_official_pool": sum(1 for r in support_rows if r["in_official_pool"] is True),
                     "scoring_status": dict(Counter(r["scoring_status_code"] for r in support_rows)),
                     "not_scored_code": dict(Counter(r["not_scored_code"] for r in support_rows)),
                     "final_alpha_level": dict(Counter(r["final_alpha_level"] for r in support_rows))},
        "alphas": {aid: {"level": alpha_level.get(aid), "activation_score": b.get("activation_score"), "evidence_count": b.get("evidence_count"),
                         "raw_supporting_claim_count": b.get("raw_supporting_claim_count"), "unique_evidence_fact_count": b.get("unique_evidence_fact_count"),
                         "ticker_specific_evidence_count": b.get("ticker_specific_evidence_count"), "reason_codes": b.get("reason_codes"),
                         "blocked_reason_codes": b.get("blocked_reason_codes"), "diagnostic_reason_codes": b.get("diagnostic_reason_codes")}
                   for aid, b in sorted(ctx.alpha_blocks.items())},
        "conflicts": {"admitted_conflict_count": conflicts.get("admitted_conflict_count"), "candidate_conflict_count": conflicts.get("candidate_conflict_count"),
                      "main_conflict": conflicts.get("main_conflict"),
                      "candidate_evaluations": [{"pair": f"{e.get('left_alpha_id') or e.get('alpha_a')}__{e.get('right_alpha_id') or e.get('alpha_b')}",
                                                 "admitted": e.get("admitted"), "reason_codes": e.get("reason_codes")} for e in evaluations]},
    }
    (out / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: stats[k] for k in ("claims", "alpha_raw_model_selection_count", "alpha_final_match_count", "alpha_raw_selection_overridden_by_gate",
                                            "content_support_status", "in_official_pool", "key_conclusions")}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
