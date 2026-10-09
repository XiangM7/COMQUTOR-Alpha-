"""Before/after analysis for the Round-18 re-qualification (read-only; zero model calls; no scoring formula of its own).

"Before" = the recovery run's production artifacts. "After" = the new requal-* run's production artifacts. The one
number this module computes itself is a leave-one-out contribution, and it does so ONLY by calling the production scorer
(`score_alpha_v2_verified`) with the same inputs the pipeline used -- after first checking that this call reproduces the
pipeline's official score exactly.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
OUTPUT_ROOT = REPO_ROOT / "outputs" / "runs"
ROOT_RUN_ID = "c904d4cc-dc09-495c-aec5-b056979948e1"
PARENT_RUN_ID = "recovery-20261007T053635Z-26d6cd1a"
TIME_REASONS = ("DISCLOSURE_TIME_UNKNOWN", "CONTENT_VERSION_CHANGED_SINCE_REVIEW")
A304_CLAIM = f"{ROOT_RUN_ID}:portfolio_manager:final_trade_decision:claim:10"


def jload(path):
    return json.loads(Path(path).read_text())


def classification_breakdown(matches):
    """The correct four-way split -- never merged into a single 'NONE' figure."""
    out = Counter()
    overridden_by_alpha, overridden_reasons = Counter(), Counter()
    for m in matches:
        if m.get("alpha_match_method") != "llm":
            out["failed_or_unresolved"] += 1
        elif m.get("matched_alpha"):
            out["final_matches"] += 1
        elif m.get("llm_selected_alpha_id"):
            out["model_selected_overridden_to_no_match_by_mapper_gates"] += 1
            overridden_by_alpha[m["llm_selected_alpha_id"]] += 1
            overridden_reasons[m.get("reason")] += 1
        else:
            out["model_none"] += 1
    return {"total": len(matches), **dict(out), "overridden_by_alpha": dict(overridden_by_alpha), "overridden_reasons": dict(overridden_reasons)}


def _alphas(activation_versions, view):
    return {a["alpha_id"]: a for a in activation_versions[view]["alphas"]}


def _alpha_row(a, exposure):
    return {
        "activation_score": a["activation_score"], "uncapped_score": a["uncapped_score"], "eligible_cap": a["eligible_cap"],
        "cap_reason_codes": a["cap_reason_codes"], "status": a["status"], "direction": a["direction"], "activation_level": a.get("activation_level"),
        "target_level": a.get("target_level"), "qualified_level": a.get("qualified_level"), "blocked_reason_codes": a.get("blocked_reason_codes"),
        "evidence_count_claims": a["evidence_count"], "unique_evidence_facts": a["unique_evidence_fact_count"],
        "distinct_agents": a["distinct_supporting_agent_count"], "ticker_specific_evidence": a["ticker_specific_evidence_count"],
        "regime_gate_passed": a["regime_gate_passed"], "regime_gate_failures": a["regime_gate_failures"],
        "component_contributions": {k: v.get("contribution") for k, v in (a.get("components") or {}).items()},
        "exposure": {k: exposure.get(k) for k in ("exposure_status", "historical_mapping", "current_evidence", "final_exposure", "would_block_dominant", "would_block_regime_level", "reason_codes")} if exposure else None,
    }


def _conflict_rows(conflicts, official_alphas):
    rows = []
    for ev in conflicts["arbitration"]["candidate_evaluations"]:
        a, b = ev["alpha_a"], ev["alpha_b"]
        rows.append({
            "pair": f"{a} vs {b}", "outcome": ev["outcome"], "reason_codes": ev["reason_codes"],
            "qualifying_claims": [ev["evidence_audit"]["alpha_a"]["qualifying_count"], ev["evidence_audit"]["alpha_b"]["qualifying_count"]],
            "official_alpha_direction": [official_alphas[a]["direction"], official_alphas[b]["direction"]],
            "official_activation_score": [official_alphas[a]["activation_score"], official_alphas[b]["activation_score"]],
            "stance_dependent_admissibility_reached": not any(c in ("DIRECTION_ROLE_UNRESOLVED", "MISSING_LEFT_EVIDENCE", "MISSING_RIGHT_EVIDENCE", "AMBIGUOUS_ONLY", "ZERO_EVIDENCE_STRENGTH") for c in ev["reason_codes"]),
        })
    return rows


def _leave_one_out(derived, d_act, alpha_id, claim_ids):
    from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
    from comqutor_alpha.graph_engine.issuer_aliases import company_names_for_ticker
    from comqutor_alpha.graph_engine.verified_evidence_gate import score_alpha_v2_verified

    graph = jload(derived / "structure_graph.json")
    payload = jload(derived / "alpha_matches.json")
    records = jload(derived / "structured_agent_outputs.json")["records"]
    sources = jload(derived / "source_registry.json")["sources"]
    view = d_act["v2_verified"]

    def score(recs):
        return score_alpha_v2_verified(
            alpha_id, payload, load_alpha_taxonomy(), structured_records=recs, sources=sources, graph_edges=graph.get("edges") or (),
            ticker=graph.get("ticker"), company_names=company_names_for_ticker(graph.get("ticker")),
            run_timestamp=view["run_timestamp"], as_of=view["as_of"])["activation_score"]

    official = _alphas(d_act, "v2_verified")[alpha_id]["activation_score"]
    reproduced = score(records)
    result = {"official_pipeline_score": official, "reproduced_by_production_scorer": reproduced, "reproduced_exactly": abs(official - reproduced) < 1e-9, "per_claim_removed": {}}
    if not result["reproduced_exactly"]:
        return result
    for claim_id in claim_ids:
        variant = []
        for r in records:
            if r["claim_id"] == claim_id:
                r = {**r, "content_support_review": {}}  # removes this one claim from the verified pool (NOT_REVIEWED); nothing else changes
            variant.append(r)
        without = score(variant)
        result["per_claim_removed"][claim_id.split(":", 1)[1]] = {"score_without_this_claim": without, "marginal_contribution": round(official - without, 6)}
    return result


def _relation_reproduction(text):
    from comqutor_alpha.structure_engine.claim_semantics import alpha_relation, analyze_claim_semantics, normalize_text

    semantics = analyze_claim_semantics(normalize_text(text))
    fields = {k: getattr(semantics, k, None) for k in ("semantic_polarity", "negated", "mixed", "conditional", "competition_context")}
    branch = ("semantic_polarity == 'mention'" if semantics.semantic_polarity == "mention" else
              "negated assertion" if semantics.negated else "no mention/negation signal")
    return {"alpha_relation_A304": alpha_relation(text, "A304"), "analysis_fields": fields, "rule_branch_that_returns_mention": branch,
            "produced_by": "code: comqutor_alpha.structure_engine.claim_semantics.alpha_relation, called from alpha_mapper when the candidate is built (a deterministic text rule, not a model and not a failure fallback)"}


def build_results(execution_id, inputs, rows, evidence, zero_call):
    derived, parent = OUTPUT_ROOT / execution_id, OUTPUT_ROOT / PARENT_RUN_ID
    pm = {m["claim_id"]: m for m in inputs["matches_payload"]["matches"]}
    recs = {r["claim_id"]: r for r in inputs["records"]}
    sources_before = {s["source_id"]: s for s in inputs["registry"]["sources"]}
    p_act, d_act = jload(parent / "alpha_activations.json")["activation_versions"], jload(derived / "alpha_activations.json")["activation_versions"]
    p_v2, p_off, d_off = _alphas(p_act, "v2"), _alphas(p_act, "v2_verified"), _alphas(d_act, "v2_verified")
    p_exp = {r["alpha_id"]: r for r in jload(parent / "entity_alpha_exposures.json")["records"]}
    d_exp = {r["alpha_id"]: r for r in jload(derived / "entity_alpha_exposures.json")["records"]}
    p_conf, d_conf = jload(parent / "conflicts.json"), jload(derived / "conflicts.json")
    p_graph, d_graph = jload(parent / "structure_graph.json"), jload(derived / "structure_graph.json")

    excluded = {}
    for ev in d_conf["arbitration"]["candidate_evaluations"]:
        for side in ("alpha_a", "alpha_b"):
            for x in ev["evidence_audit"][side]["excluded"]:
                excluded[(ev["evidence_audit"][side]["alpha_id"], x["claim_id"])] = x["reason_code"]

    claim_rows = []
    for cid, (before, after) in rows.items():
        if before["reason_code"] not in TIME_REASONS:
            continue
        rec, m = recs[cid], pm[cid]
        review = rec.get("content_support_review") or {}
        used = review.get("linked_source_id") or rec.get("linked_source_id")
        alpha = m.get("matched_alpha")
        outcome = (f"matched {alpha}" if alpha else f"model selected {m['llm_selected_alpha_id']}, overridden to no_match by a mapper gate"
                   if m.get("llm_selected_alpha_id") else "model NONE")
        candidate = next((c for c in m.get("candidate_scores") or [] if c["alpha_id"] == alpha), None) if alpha else None
        group = None
        if alpha:
            group = next((g for g in d_off[alpha].get("evidence_fact_groups") or [] if cid in (g.get("member_claim_ids") or [])), None)
        claim_rows.append({
            "claim_id": cid, "agent": rec.get("agent"), "claim_full_text": rec.get("claim"),
            "review": {"method": review.get("method"), "status": review.get("status"), "bound_source_id": used, "bound_content_hash": review.get("content_hash"),
                       "record_primary_source_id": rec.get("linked_source_id"), "record_linked_source_ids": rec.get("linked_source_ids")},
            "bound_source_title": sources_before[used]["title"], "bound_source_published_at": sources_before[used].get("published_at"),
            "eligibility_before": before["reason_code"], "eligibility_after_binding_fix_only": inputs["intermediate"][cid]["reason_code"], "eligibility_after": after["reason_code"],
            "alpha_classification": outcome, "claim_quality": rec.get("claim_quality"), "assertion_status": rec.get("assertion_status"), "semantic_polarity": rec.get("semantic_polarity"),
            "candidate_relation_to_matched_alpha": candidate.get("relation") if candidate else None,
            "in_raw_pool_before": (cid in (p_v2[alpha].get("claim_ids") or [])) if alpha else None,
            "in_official_pool_before": (cid in (p_off[alpha].get("claim_ids") or [])) if alpha else None,
            "in_official_pool_after": (cid in (d_off[alpha].get("claim_ids") or [])) if alpha else None,
            "pool_exclusion_reason_after": excluded.get((alpha, cid)) if alpha else None,
            "official_fact_group_after": ({k: group.get(k) for k in ("evidence_fact_group_id", "member_claim_ids", "supporting_agents", "activation_eligible")} if group else None),
            "first_blocker_after": (None if (alpha and cid in (d_off[alpha].get("claim_ids") or [])) else
                                    "classification: model NONE" if not alpha and not m.get("llm_selected_alpha_id") else
                                    "classification: model selection overridden to no_match by a mapper gate" if not alpha else
                                    f"evidence qualification: {excluded.get((alpha, cid)) or 'not in official pool'}"),
        })

    alpha_rows = {a: {"before_official": _alpha_row(p_off[a], p_exp.get(a)), "after_official": _alpha_row(d_off[a], d_exp.get(a))} for a in sorted(p_off)}
    changed_alphas = [a for a, r in alpha_rows.items() if r["before_official"]["activation_score"] != r["after_official"]["activation_score"] or r["before_official"]["evidence_count_claims"] != r["after_official"]["evidence_count_claims"]]

    a301_claims = [c["claim_id"] for c in claim_rows if c["alpha_classification"] == "matched A301" and c["in_official_pool_after"]]
    loo = _leave_one_out(derived, d_act, "A301", a301_claims) if a301_claims else None

    a304 = recs[A304_CLAIM]
    a304_row = next(c for c in claim_rows if c["claim_id"] == A304_CLAIM)
    blockers = {
        "blocker_1_review_hash_vs_source": {
            "before": rows[A304_CLAIM][0]["reason_code"], "after": rows[A304_CLAIM][1]["reason_code"],
            "cause": "consumption/binding defect: the review's own bound source (src_582ac24bf4319648, the one the verifier USED) was compared against the record's primary link (src_7e133fa786f7aaa0); the review's hash equals the bound source's stored hash",
            "review_content_hash": a304["content_support_review"]["content_hash"], "bound_source_stored_hash": sources_before[a304["content_support_review"]["linked_source_id"]]["content_hash"],
            "content_changed": False, "resolved": rows[A304_CLAIM][1]["eligible"],
            "limitation": "the old review binds only the source the verifier used; the other cited source (src_7e133fa786f7aaa0) has no hash bound to this review",
        },
        "blocker_2_unsupported_relation": {
            "rejecting_function": "comqutor_alpha.conflict_engine.conflict_detector._gather_qualifying_evidence (relation not in QUALIFYING_RELATIONS); the activation scorer gives relation 'mention' weight 0.0",
            "field": "alpha_matches.matches[].candidate_scores[A304].relation", "stored_value": a304_row["candidate_relation_to_matched_alpha"],
            "reproduction": _relation_reproduction(a304["claim"]),
            "classification_was_model_produced": True, "classification_status": "llm_selected (the model chose A304)",
            "why_not_a_defect": "the relation is a deterministic text rule; it maps every negated assertion to 'mention' and cannot tell a negated REBUTTAL of the bulls' PEG defense (which would bear on A304) from a negation of A304's own thesis",
            "resolved": False, "needs": "a model semantic judgment of this claim's relation to A304 (support / oppose / background); not supplied here, not inferred by keyword rules",
        },
    }

    d_alpha_changes = {a: alpha_rows[a] for a in changed_alphas}
    summary = {
        "eligibility_reason_counts_before": dict(Counter(b["reason_code"] for b, _ in rows.values())),
        "eligibility_reason_counts_after": dict(Counter(a["reason_code"] for _, a in rows.values())),
        "claims_requalified": len(claim_rows),
        "claims_now_eligible": sum(1 for c in claim_rows if c["eligibility_after"] == "ELIGIBLE"),
        "claims_requalified_that_reach_an_official_pool": sum(1 for c in claim_rows if c["in_official_pool_after"]),
        "alphas_with_official_evidence_before": [a for a, r in alpha_rows.items() if r["before_official"]["evidence_count_claims"] > 0],
        "alphas_with_official_evidence_after": [a for a, r in alpha_rows.items() if r["after_official"]["evidence_count_claims"] > 0],
        "official_scores_after": {a: r["after_official"]["activation_score"] for a, r in alpha_rows.items() if r["after_official"]["activation_score"]},
        "activation_levels_after": dict(Counter(r["after_official"]["activation_level"] for r in alpha_rows.values())),
        "active_or_dominant_after": [a for a, r in alpha_rows.items() if r["after_official"]["activation_level"] in ("active", "dominant", "regime_level")],
        "dominant_alphas_after": d_graph.get("dominant_alphas"),
        "admitted_conflicts_before": p_conf["admitted_conflict_count"], "admitted_conflicts_after": d_conf["admitted_conflict_count"],
        "candidate_conflicts_before": p_conf["candidate_conflict_count"], "candidate_conflicts_after": d_conf["candidate_conflict_count"],
        "a304_blockers": {"binding_resolved": blockers["blocker_1_review_hash_vs_source"]["resolved"], "relation_resolved": False},
        "classification": classification_breakdown(inputs["matches_payload"]["matches"]),
        "direction": "not obtained; stance in alpha_matches is the production deterministic classifier",
        "model_or_network_calls_attempted": zero_call["attempted_provider_or_network_calls"],
    }
    return {
        "schema_version": "comqutor.evidence_eligibility_requalification.v1", "run_id": execution_id, "based_on_run_id": PARENT_RUN_ID, "root_research_run_id": ROOT_RUN_ID,
        "summary": summary, "classification_breakdown": summary["classification"], "time_evidence": evidence, "zero_call_proof": zero_call,
        "claims_requalified": claim_rows, "alpha_before_after_official": alpha_rows, "a301_leave_one_out_contribution": loo,
        "a304_blockers": blockers,
        "conflicts_before": _conflict_rows(p_conf, p_off), "conflicts_after": _conflict_rows(d_conf, d_off),
        "official_graph_before": {"dominant_alphas": p_graph.get("dominant_alphas")}, "official_graph_after": {"dominant_alphas": d_graph.get("dominant_alphas")},
    }
