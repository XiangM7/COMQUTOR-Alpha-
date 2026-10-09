#!/usr/bin/env python3
"""T4 round 32: field-by-field comparison of the derived final-code execution (replay_fresh2_final_code.py) with the second
NVDA Fresh run it is based on. Read-only on both; standard library only.

The derived execution's own id is normalised back to the Fresh run's id before comparing (claim ids embed the run id).
Every difference is listed with its count and examples; ``expected`` marks the differences this round's engineering fixes are
supposed to cause (the five never-sent content-support requests now read ``input_too_large``; the new ledger error_message;
new artifacts), everything else must be identical.

    python compare_replay_with_fresh2.py --execution-dir outputs/t4_r32_verify_runs/<id> --out 05_replay/comparison.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
BASE_RUN_ID = "12591384-0b26-470d-a99d-a49c00be440b"
BASE_DIR = REPO / "outputs" / "t4_runs" / BASE_RUN_ID


def load(path: Path, execution_id: str | None = None):
    text = path.read_text(encoding="utf-8")
    if execution_id:
        text = text.replace(execution_id, BASE_RUN_ID)
    return json.loads(text)


def jl(path: Path, execution_id: str | None = None) -> list[dict]:
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if execution_id:
        text = text.replace(execution_id, BASE_RUN_ID)
    return [json.loads(x) for x in text.splitlines() if x.strip()]


def diff_records(left: dict, right: dict, ignore: set[str] = frozenset()) -> dict[str, list]:
    """key -> field -> list of keys whose value differs (left = Fresh, right = derived)."""
    out: dict[str, list] = defaultdict(list)
    for key in sorted(set(left) | set(right)):
        a, b = left.get(key), right.get(key)
        if a is None or b is None:
            out["<presence>"].append(key)
            continue
        for field in sorted(set(a) | set(b)):
            if field in ignore:
                continue
            if json.dumps(a.get(field), sort_keys=True) != json.dumps(b.get(field), sort_keys=True):
                out[field].append(key)
    return out


def summarize(diffs: dict[str, list]) -> dict:
    return {field: {"count": len(keys), "examples": keys[:5]} for field, keys in sorted(diffs.items())}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execution-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    ex = Path(args.execution_dir)
    if not ex.is_absolute():
        ex = REPO / ex
    eid = ex.name
    result: dict = {"based_on_run_id": BASE_RUN_ID, "execution_id": eid}

    # 1. claims and claim <-> source binding
    fs = load(BASE_DIR / "structured_agent_outputs.json")
    ds = load(ex / "structured_agent_outputs.json", eid)
    fr = {r["claim_id"]: r for r in fs["records"]}
    dr = {r["claim_id"]: r for r in ds["records"]}
    rec_diffs = diff_records(fr, dr, ignore={"run_id", "timestamp"})  # timestamp = record creation time of each execution
    binding = ("source_link_status", "source_link_method", "linked_source_id", "source_refs")
    result["claims"] = {"fresh": len(fr), "derived": len(dr), "same_claim_ids": set(fr) == set(dr), "ignored_volatile_fields": ["run_id", "timestamp"],
                        "claim_text_identical": all(fr[c].get("claim") == dr.get(c, {}).get("claim") for c in fr),
                        "source_binding_identical": all(all(json.dumps(fr[c].get(k)) == json.dumps(dr.get(c, {}).get(k)) for k in binding) for c in fr),
                        "field_differences": summarize(rec_diffs)}
    changed_reason = [c for c in rec_diffs.get("content_support_llm_fallback_reason", [])]
    result["claims"]["content_support_fallback_reason_changes"] = sorted(Counter(
        f"{fr[c].get('content_support_llm_fallback_reason')} -> {dr[c].get('content_support_llm_fallback_reason')}" for c in changed_reason).items())
    result["claims"]["content_support_status_identical"] = all(fr[c].get("content_support_status") == dr.get(c, {}).get("content_support_status") for c in fr)

    # 2. Alpha classification (raw model selection, final match, gates, stance candidates)
    fm = {m["claim_id"]: m for m in load(BASE_DIR / "alpha_matches.json")["matches"]}
    dm = {m["claim_id"]: m for m in load(ex / "alpha_matches.json", eid)["matches"]}
    m_diffs = diff_records(fm, dm, ignore={"run_id"})
    result["alpha_matches"] = {"field_differences": summarize(m_diffs),
                               "raw_selection_identical": all(fm[c].get("llm_selected_alpha_id") == dm.get(c, {}).get("llm_selected_alpha_id") for c in fm),
                               "final_match_identical": all(fm[c].get("matched_alpha") == dm.get(c, {}).get("matched_alpha") for c in fm),
                               "raw_selected": sum(1 for m in dm.values() if m.get("llm_selected_alpha_id")),
                               "final_matched": sum(1 for m in dm.values() if m.get("matched_alpha")),
                               "classification_unavailable": sum(1 for m in dm.values() if m.get("match_status") not in ("matched", "no_match"))}

    # 3. evidence stance audit
    def stance_index(payload):
        return {f"{r.get('claim_id')}|{r.get('alpha_id') or r.get('target_alpha_id')}": r for r in (payload.get("records") or [])}
    fsa, dsa = stance_index(load(BASE_DIR / "evidence_stance_audit.json")), stance_index(load(ex / "evidence_stance_audit.json", eid))
    def partition(index):  # evidence-fact group ids hash the run id; compare the grouping itself
        groups = defaultdict(set)
        for k, r in index.items():
            for gid in r.get("evidence_fact_group_ids") or []:
                groups[gid].add(k)
        return sorted(sorted(v) for v in groups.values())
    result["evidence_stance_audit"] = {"records": [len(fsa), len(dsa)],
                                       "field_differences": summarize(diff_records(fsa, dsa, ignore={"run_id", "evidence_fact_group_ids"})),
                                       "evidence_fact_grouping_identical": partition(fsa) == partition(dsa), "evidence_fact_groups": len(partition(fsa)),
                                       "note": "evidence_fact_group_ids are hashes of (run_id, ticker, member claim ids), so the ids differ by run id; the grouping is compared instead"}

    # 4. Structure Graph / activation
    fg, dg = load(BASE_DIR / "structure_graph.json"), load(ex / "structure_graph.json", eid)
    def alphas(g):
        return {a["alpha_id"]: {k: a.get(k) for k in ("activation_score", "activation_level", "qualified_level", "status", "evidence_count",
                                                      "raw_supporting_claim_count", "unique_evidence_fact_count", "ticker_specific_evidence_count",
                                                      "reason_codes", "blocked_reason_codes")} for a in (g.get("activation") or {}).get("alphas") or []}
    result["structure_graph"] = {"graph_metrics_identical": fg.get("graph_metrics") == dg.get("graph_metrics"),
                                 "nodes_identical": json.dumps(fg.get("nodes"), sort_keys=True) == json.dumps(dg.get("nodes"), sort_keys=True),
                                 "edges_identical": json.dumps(fg.get("edges"), sort_keys=True) == json.dumps(dg.get("edges"), sort_keys=True),
                                 "dominant": [len(fg.get("dominant_alphas") or []), len(dg.get("dominant_alphas") or [])],
                                 "active": [len(fg.get("active_alphas") or []), len(dg.get("active_alphas") or [])],
                                 "alpha_activation_differences": summarize(diff_records(alphas(fg), alphas(dg)))}

    # 5. conflicts
    fc, dc = load(BASE_DIR / "conflicts.json"), load(ex / "conflicts.json", eid)
    def evals(c):
        return {f"{e.get('left_alpha_id') or e.get('alpha_a')}__{e.get('right_alpha_id') or e.get('alpha_b')}": {"admitted": e.get("admitted"), "reason_codes": e.get("reason_codes")}
                for e in (c.get("arbitration") or {}).get("candidate_evaluations") or []}
    result["conflicts"] = {"admitted": [fc.get("admitted_conflict_count"), dc.get("admitted_conflict_count")],
                           "main_conflict": [fc.get("main_conflict"), dc.get("main_conflict")],
                           "candidate_evaluation_differences": summarize(diff_records(evals(fc), evals(dc)))}

    # 6. formal acceptance
    ff, df = load(BASE_DIR / "formal_acceptance.json"), load(ex / "formal_acceptance.json", eid)
    result["formal_acceptance"] = {"formal_status": [ff.get("formal_status"), df.get("formal_status")],
                                   "rule_verdicts_identical": [(r.get("rule_id"), r.get("verdict")) for r in ff.get("contract_rule_results") or []]
                                   == [(r.get("rule_id"), r.get("verdict")) for r in df.get("contract_rule_results") or []]}

    # 7. semantic ledger: same requests (task, normalised input, prompt identity) and outcomes
    def key(r):
        return f"{r['task']}|{json.dumps(r.get('input_payload'), sort_keys=True, ensure_ascii=False)}"
    fl, dl = jl(BASE_DIR / "llm_semantic_calls.jsonl"), jl(ex / "llm_semantic_calls.jsonl", eid)
    fidx, didx = defaultdict(list), defaultdict(list)
    for r in fl:
        fidx[key(r)].append(r)
    for r in dl:
        didx[key(r)].append(r)
    outcome_fields = ("prompt_version", "prompt_sha256", "input_schema_version", "output_schema_version", "provider", "model", "provider_status",
                      "validation_status", "fallback_reason", "error_code", "error_message", "validated_output_sha256")
    ledger_diffs: dict[str, list] = defaultdict(list)
    for k in sorted(set(fidx) | set(didx)):
        a, b = fidx.get(k, []), didx.get(k, [])
        if len(a) != len(b):
            ledger_diffs["<call count>"].append(k.split("|", 1)[0])
            continue
        for x, y in zip(sorted(a, key=lambda r: r.get("call_sequence") or 0), sorted(b, key=lambda r: r.get("call_sequence") or 0), strict=True):
            for f in outcome_fields:
                if json.dumps(x.get(f)) != json.dumps(y.get(f)):
                    ledger_diffs[f].append(f"{x['task']}:{x.get('fallback_reason')}->{y.get('fallback_reason')}")
    result["semantic_ledger"] = {"calls": [len(fl), len(dl)], "distinct_requests": [len(fidx), len(didx)],
                                 "same_request_set": set(fidx) == set(didx),
                                 "prompt_identity_by_task_fresh": sorted({(r["task"], r.get("prompt_sha256")) for r in fl}),
                                 "prompt_identity_by_task_derived": sorted({(r["task"], r.get("prompt_sha256")) for r in dl}),
                                 "outcome_differences": {f: {"count": len(v), "examples": sorted(Counter(v).items())[:6]} for f, v in sorted(ledger_diffs.items())}}

    # 8. never a valid NONE / verdict from a failure
    nd = [dr[c] for c in dr if dr[c].get("content_support_llm_fallback_reason") == "input_too_large"]
    result["failures_not_turned_into_answers"] = {
        "content_support_not_sent_input_too_large": len(nd),
        "not_sent_claims_status": sorted(Counter(r.get("content_support_status") for r in nd).items()),
        "not_sent_claims_with_llm_detail": sum(1 for r in nd if r.get("content_support_llm_detail")),
        "adapter_records_extraction_method": sorted(Counter(r.get("extraction_method") for r in dr.values()).items()),
        "alpha_unavailable_counted_as_none": sum(1 for m in dm.values() if m.get("match_status") != "matched" and m.get("alpha_match_fallback_reason")
                                                 and m.get("match_status") == "no_match"),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, default=str)[:6000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
