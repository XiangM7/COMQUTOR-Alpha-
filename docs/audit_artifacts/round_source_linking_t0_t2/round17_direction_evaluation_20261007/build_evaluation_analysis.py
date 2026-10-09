#!/usr/bin/env python3
"""Per-Alpha funnel, per-candidate Conflict table and the fate of the 19 analytical SUPPORTS claims, read from the
production artifacts the classification-recovery run already produced (zero model calls, read-only).

PROVISIONAL BY CONSTRUCTION: the direction (evidence_stance_classifier) task has no saved real result, so every stance
in these artifacts is the production deterministic one. The funnel up to the verified-evidence gate and the Alpha-level
activation do not read stance at all; the one place stance is read (the Conflict admissibility gate) is only reached by
a candidate pair that has already passed the earlier conditions -- the table below shows whether any did.
"""
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
HERE = Path(__file__).resolve().parent
RUN = sys.argv[1] if len(sys.argv) > 1 else "recovery-20261007T053635Z-26d6cd1a"
ROOT = "c904d4cc-dc09-495c-aec5-b056979948e1"
d = REPO / "outputs" / "runs" / RUN

from comqutor_alpha.source_provenance import compute_verified_support_eligibility

J = lambda name: json.loads((d / name).read_text())
matches = J("alpha_matches.json")["matches"]
records = {r["claim_id"]: r for r in J("structured_agent_outputs.json")["records"]}
sources = J("source_registry.json").get("sources") or []
act = J("alpha_activations.json")["activation_versions"]
v2 = {a["alpha_id"]: a for a in act["v2"]["alphas"]}
v2v = {a["alpha_id"]: a for a in act["v2_verified"]["alphas"]}
conflicts = J("conflicts.json")
exposure = {r["alpha_id"]: r for r in J("entity_alpha_exposures.json")["records"]}
graph = J("structure_graph.json")
stance_audit = J("evidence_stance_audit.json")
stance_by_pair = {(r.get("claim_id"), r.get("alpha_id") or r.get("target_alpha_id")): r for r in stance_audit["records"]}
by_claim = {m["claim_id"]: m for m in matches}
elig = {cid: compute_verified_support_eligibility(r, sources) for cid, r in records.items()}

# exclusion reasons as the Conflict audit saw them, per (alpha, claim)
excluded_reason = {}
for ev in conflicts["arbitration"]["candidate_evaluations"]:
    for side in ("alpha_a", "alpha_b"):
        for x in ev["evidence_audit"][side]["excluded"]:
            excluded_reason[(ev["evidence_audit"][side]["alpha_id"], x["claim_id"])] = x["reason_code"]

summary_row = lambda a: {k: a.get(k) for k in ("activation_score", "uncapped_score", "status", "direction", "activation_level", "target_level", "qualified_level",
                                              "evidence_count", "unique_evidence_fact_count", "distinct_supporting_agent_count", "ticker_specific_evidence_count",
                                              "local_edge_count", "regime_gate_passed", "cap_reason_codes", "reason_codes", "blocked_reason_codes", "is_blocked")}

funnel = []
for alpha_id in sorted(v2):
    m_claims = [m for m in matches if m.get("matched_alpha") == alpha_id]
    ids = [m["claim_id"] for m in m_claims]
    reasons = Counter(elig[c]["reason_code"] for c in ids)
    quality = Counter((records[c].get("claim_quality"), bool(records[c].get("analysis_eligible"))) for c in ids)
    stances = Counter(next((cand.get("evidence_stance") for cand in (by_claim[c].get("candidate_scores") or []) if cand.get("alpha_id") == alpha_id), None) for c in ids)
    methods = Counter(next((cand.get("stance_method") for cand in (by_claim[c].get("candidate_scores") or []) if cand.get("alpha_id") == alpha_id), None) for c in ids)
    funnel.append({
        "alpha_id": alpha_id, "alpha_name": v2[alpha_id]["alpha_name"],
        "1_matched_claims": len(ids),
        "2_content_support_eligible_claims": sum(1 for c in ids if elig[c]["eligible"]),
        "2_ineligible_reason_counts": dict(reasons),
        "3_claim_quality_among_matched": {f"{q}|analysis_eligible={e}": n for (q, e), n in quality.items()},
        "3_raw_pool_claims_v2": len(v2[alpha_id].get("claim_ids") or []),
        "3_raw_pool_unique_evidence_count_v2": v2[alpha_id]["evidence_count"],
        "4_unique_evidence_facts_v2": v2[alpha_id]["unique_evidence_fact_count"],
        "5_distinct_agents_v2": v2[alpha_id]["distinct_supporting_agent_count"], "5_ticker_specific_v2": v2[alpha_id]["ticker_specific_evidence_count"],
        "6_alpha_direction_v2": v2[alpha_id]["direction"], "6_deterministic_stance_mix_of_matched": {str(k): n for k, n in stances.items()}, "6_stance_methods": {str(k): n for k, n in methods.items()},
        "raw_view_v2": summary_row(v2[alpha_id]),
        "official_view_v2_verified": summary_row(v2v[alpha_id]),
        "official_qualification": v2v[alpha_id].get("evidence_qualification"),
        "7_exposure": {k: exposure[alpha_id].get(k) for k in ("historical_mapping", "current_evidence", "agent_confidence", "final_exposure", "would_block_dominant", "would_block_regime_level", "reason_codes")},
        "8_activation_level_official": v2v[alpha_id]["activation_level"], "9_status_official": v2v[alpha_id]["status"],
    })

cand = []
for ev in conflicts["arbitration"]["candidate_evaluations"]:
    a, b = ev["alpha_a"], ev["alpha_b"]
    side = lambda x: {"alpha_id": x["alpha_id"], "qualifying_claims": x["qualifying_count"], "excluded": dict(Counter(e["reason_code"] for e in x["excluded"]))}
    cand.append({
        "pair": f"{a} vs {b}", "outcome": ev["outcome"], "reason_codes": ev["reason_codes"],
        "side_a": {**side(ev["evidence_audit"]["alpha_a"]), "alpha_direction_raw_v2": v2[a]["direction"], "alpha_direction_official": v2v[a]["direction"],
                   "activation_score_raw_v2": v2[a]["activation_score"], "activation_score_official": v2v[a]["activation_score"], "activation_level_official": v2v[a]["activation_level"]},
        "side_b": {**side(ev["evidence_audit"]["alpha_b"]), "alpha_direction_raw_v2": v2[b]["direction"], "alpha_direction_official": v2v[b]["direction"],
                   "activation_score_raw_v2": v2[b]["activation_score"], "activation_score_official": v2v[b]["activation_score"], "activation_level_official": v2v[b]["activation_level"]},
        "admissibility_executed": any(code in ("INSUFFICIENT_SUPPORTING_EVIDENCE", "INSUFFICIENT_TICKER_SPECIFIC_SUPPORT", "SCORE_BELOW_THRESHOLD") or code.startswith("ADMISSIBILITY") for code in ev["reason_codes"]),
    })

nineteen = [c["claim_id"] for c in json.loads((REPO / "docs/audit_artifacts/round_source_linking_t0_t2/round12_alpha_classifier_audit_fix_20261006/19_analytical_supports_claim_list.json").read_text())["claims"]]
rows = []
for n, cid in enumerate(nineteen, 1):
    r, m = records[cid], by_claim[cid]
    review = r.get("content_support_review") or {}
    alpha = m.get("matched_alpha")
    row = {
        "n": n, "claim_id": cid.split(":", 1)[1], "claim": m.get("claim"),
        "content_support": {"source_link_status": r.get("source_link_status"), "linked_source_id": r.get("linked_source_id"), "status": r.get("content_support_status"),
                            "method": r.get("content_support_method"), "review_method": review.get("method"), "review_status": review.get("status"),
                            "basis": review.get("support_basis") or review.get("rationale") or review.get("reason"), "eligibility_for_scoring": elig[cid]},
        "claim_quality": r.get("claim_quality"), "analysis_eligible": r.get("analysis_eligible"), "quality_reason_codes": r.get("claim_quality_reason_codes"),
        "classification": {"model_selected_alpha": m.get("llm_selected_alpha_id"), "matched_alpha": alpha, "match_status": m.get("match_status"), "reason": m.get("reason"),
                           "alpha_match_method": m.get("alpha_match_method"), "fallback_reason": m.get("alpha_match_fallback_reason")},
    }
    if alpha:
        cand_row = next(c for c in m["candidate_scores"] if c["alpha_id"] == alpha)
        row["direction_judgment"] = {"real_direction_result": None, "note": "no real direction result exists (direction task not completed)",
                                     "production_deterministic_stance": cand_row.get("evidence_stance"), "method": cand_row.get("stance_method"), "confidence_band": cand_row.get("stance_confidence_band")}
        row["in_raw_pool_v2"] = cid in (v2[alpha].get("claim_ids") or [])
        row["in_official_pool_v2_verified"] = cid in (v2v[alpha].get("claim_ids") or [])
        row["raw_pool_exclusion_reason_in_conflict_audit"] = excluded_reason.get((alpha, cid))
        group = next((g for g in v2[alpha].get("evidence_fact_groups") or [] if cid in (g.get("claim_ids") or g.get("member_claim_ids") or [])), None)
        row["raw_view_fact_group"] = {k: group.get(k) for k in list(group)[:12]} if group else None
        row["alpha_level_context_v2"] = summary_row(v2[alpha])
        row["alpha_level_context_official"] = summary_row(v2v[alpha])
    rows.append(row)

# --- how the raw-qualifying claims fall at the verified gate (the first blocker per Alpha) --------------------------------
for f in funnel:
    pool = v2[f["alpha_id"]].get("claim_ids") or []
    f["3_raw_qualifying_claims_by_content_eligibility"] = dict(Counter(elig[c]["reason_code"] for c in pool))

def outcome_of(cid):
    m = by_claim[cid]
    if m.get("matched_alpha"):
        return f"matched {m['matched_alpha']}"
    if m.get("llm_selected_alpha_id"):
        return f"model selected {m['llm_selected_alpha_id']}, overridden to no_match by a mapper gate"
    if m.get("alpha_match_method") != "llm":
        return "classification failed (timeout)"
    return "model NONE"

eligible_rows = []
for cid, e in elig.items():
    if e["eligible"]:
        m = by_claim[cid]
        alpha = m.get("matched_alpha")
        eligible_rows.append({"claim_id": cid.split(":", 1)[1], "outcome": outcome_of(cid), "in_raw_pool": (cid in (v2[alpha].get("claim_ids") or [])) if alpha else None,
                              "claim_quality": records[cid].get("claim_quality"), "in_nineteen": cid in set(json.loads((REPO / "docs/audit_artifacts/round_source_linking_t0_t2/round12_alpha_classifier_audit_fix_20261006/19_analytical_supports_claim_list.json").read_text())["claims"] and [c["claim_id"] for c in json.loads((REPO / "docs/audit_artifacts/round_source_linking_t0_t2/round12_alpha_classifier_audit_fix_20261006/19_analytical_supports_claim_list.json").read_text())["claims"]])})

t1_counts = {
    "source_link_status": dict(Counter(r.get("source_link_status") for r in records.values())),
    "content_support_method_among_linked": dict(Counter(r.get("content_support_method") for r in records.values() if r.get("source_link_status") == "VALID")),
    "content_support_status_among_linked": dict(Counter(r.get("content_support_status") for r in records.values() if r.get("source_link_status") == "VALID")),
    "eligibility_reason_counts_all": dict(Counter(e["reason_code"] for e in elig.values())),
}

def first_blockers(row):
    out = []
    cl = row["classification"]
    if not cl["matched_alpha"]:
        out.append("classification: the model returned NONE ('no canonical Alpha materially fits') -- the claim never became Alpha evidence; this is a real classification result, not a source or verification shortfall")
        return out
    e = row["content_support"]["eligibility_for_scoring"]["reason_code"]
    if e != "ELIGIBLE":
        out.append(f"verified-evidence gate: {e}")
    if not row["in_raw_pool_v2"]:
        out.append(f"evidence qualification (raw view): excluded as {row['raw_pool_exclusion_reason_in_conflict_audit']}")
    return out

for row in rows:
    row["first_blocking_conditions"] = first_blockers(row)

result = {
    "run_id": RUN, "root_research_run_id": ROOT, "provisional": "stance = production deterministic classifier; no real direction result exists",
    "stance_audit_summary": stance_audit["summary"], "stance_effect_mode_label": {"effect_mode": stance_audit["effect_mode"], "stance_effect_applied": stance_audit["stance_effect_applied"]},
    "graph": {"evidence_gate_applied": graph.get("evidence_gate_applied"), "dominant_alphas": graph.get("dominant_alphas"), "policy": graph.get("evidence_gate_policy_version")},
    "funnel": funnel, "conflict_candidates": cand, "conflicts_summary": {k: conflicts[k] for k in ("admitted_conflict_count", "candidate_conflict_count")} | {"arbitration": {k: v for k, v in conflicts["arbitration"].items() if k != "candidate_evaluations"}},
    "nineteen": rows,
    "eligibility_reason_counts_all_claims": dict(Counter(e["reason_code"] for e in elig.values())),
    "eligible_claims_total": sum(1 for e in elig.values() if e["eligible"]),
    "eligible_claims": eligible_rows,
    "t1_related_counts": t1_counts,
}
(HERE / "evaluation_analysis_provisional.json").write_text(json.dumps(result, indent=1, default=str))
print("eligibility over ALL claims:", result["eligibility_reason_counts_all_claims"], "| eligible:", result["eligible_claims_total"])
print("dominant:", graph.get("dominant_alphas"), "| gate applied:", graph.get("evidence_gate_applied"))
print("\nALPHA FUNNEL (matched | eligible-of-matched | raw-pool claims | raw facts | agents | direction | score raw -> official | level | exposure)")
for f in funnel:
    print(f["alpha_id"], f["alpha_name"][:22].ljust(22), f["1_matched_claims"], f["2_content_support_eligible_claims"], f["3_raw_pool_claims_v2"], f["4_unique_evidence_facts_v2"],
          f["5_distinct_agents_v2"], f["6_alpha_direction_v2"], f"{f['raw_view_v2']['activation_score']:.1f}->{f['official_view_v2_verified']['activation_score']:.1f}", f["8_activation_level_official"], f["7_exposure"]["final_exposure"], f["raw_view_v2"]["activation_level"])
print("\nCONFLICT CANDIDATES")
for c in cand: print(c["pair"], c["outcome"], c["reason_codes"], "| qualifying", c["side_a"]["qualifying_claims"], c["side_b"]["qualifying_claims"], "| dir raw", c["side_a"]["alpha_direction_raw_v2"], c["side_b"]["alpha_direction_raw_v2"])
print("\n19 CLAIMS")
for r in rows:
    print(r["n"], r["claim_id"][:34], "|", r["classification"]["matched_alpha"], "| src:", r["content_support"]["source_link_status"], "| cs:", r["content_support"]["status"], r["content_support"]["method"], "| elig:", r["content_support"]["eligibility_for_scoring"]["reason_code"], "| q:", r["claim_quality"], r["analysis_eligible"], "| rawpool:", r.get("in_raw_pool_v2"), "official:", r.get("in_official_pool_v2_verified"), "| excl:", r.get("raw_pool_exclusion_reason_in_conflict_audit"))

print("\nRAW-QUALIFYING CLAIMS BY CONTENT ELIGIBILITY (per Alpha)")
for f in funnel:
    print(f["alpha_id"], f["3_raw_qualifying_claims_by_content_eligibility"])
print("\nELIGIBLE (40) outcomes:", dict(Counter(r["outcome"].split(",")[0] for r in eligible_rows)), "| eligible AND matched AND in raw pool:", sum(1 for r in eligible_rows if r["in_raw_pool"]))
print("T1 counts:", json.dumps(t1_counts))
for r in rows:
    if r["classification"]["matched_alpha"]:
        print(r["n"], r["claim_id"], "| group:", {k: (r["raw_view_fact_group"] or {}).get(k) for k in ("evidence_fact_group_id", "supporting_agents", "activation_eligible")}, "| blockers:", r["first_blocking_conditions"])
