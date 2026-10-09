#!/usr/bin/env python3
"""Round 19 -- reproduce, with the PRODUCTION functions and the SAVED artifacts only, how
  * A301 claims 31 / 33 / 36 reach (or fail to add weight to) the official A301 score, and
  * the A304 claim portfolio_manager:final_trade_decision:claim:10 is excluded,
  * why A301's agent-independence / ticker-specific / local-structure terms are what they are.

Zero Provider / search / data-fetch calls (no gateway is ever constructed), read-only on outputs/ (this script writes only next to itself).
Everything printed as a "reproduced" value is computed here by calling the production code; everything printed as "saved" is read from the artifact,
and the two are compared.

usage: .venv/bin/python reproduce_consumption_chain.py
"""
import hashlib, itertools, json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.graph_engine import activation_scorer_v2 as act
from comqutor_alpha.graph_engine import evidence_fact_index as efi
from comqutor_alpha.graph_engine.evidence_source_role import qualify_evidence_group
from comqutor_alpha.graph_engine.issuer_aliases import company_names_for_ticker
from comqutor_alpha.graph_engine.verified_evidence_gate import score_alpha_v2_verified
from comqutor_alpha.source_provenance import compute_verified_support_eligibility
from comqutor_alpha.structure_engine import claim_semantics as cs
from comqutor_alpha.structure_engine.alpha_mapper import map_claim_to_alpha

ROOT = "c904d4cc-dc09-495c-aec5-b056979948e1"
RECOVERY = "recovery-20261007T053635Z-26d6cd1a"
DERIVED = "requal-20261007T174744Z-664040d6"
runs = REPO / "outputs" / "runs"
jload = lambda p: json.loads(Path(p).read_text())

derived = runs / DERIVED
matches = {m["claim_id"]: m for m in jload(derived / "alpha_matches.json")["matches"]}
payload = jload(derived / "alpha_matches.json")
records = jload(derived / "structured_agent_outputs.json")["records"]
rec_by = {r["claim_id"]: r for r in records}
sources = jload(derived / "source_registry.json")["sources"]
src_by = {s["source_id"]: s for s in sources}
graph = jload(derived / "structure_graph.json")
activation = jload(derived / "alpha_activations.json")["activation_versions"]["v2_verified"]
a301_saved = next(a for a in activation["alphas"] if a["alpha_id"] == "A301")
raw_outputs = {o["agent_output_id"]: o for o in jload(runs / ROOT / "raw_agent_outputs.json")["agent_outputs"]}
taxonomy = load_alpha_taxonomy()
TICKER = graph["ticker"]
cid = lambda agent, section, n: f"{ROOT}:{agent}:{section}:claim:{n}"
A301_CLAIMS = {n: cid("fundamental_agent", "fundamentals_report", n) for n in (31, 33, 36)}
A304_CLAIM = cid("portfolio_manager", "final_trade_decision", 10)

# the recovery run's real classifier call for each claim (saved audit record; nothing is sent)
calls = {}
with open(runs / RECOVERY / "llm_semantic_calls.jsonl") as f:
    for line in f:
        d = json.loads(line)
        for c in d.get("claim_ids") or []:
            calls[c] = d


def context_of(claim_id, claim_text):
    parts = claim_id.split(":")
    agent_output_id = ":".join(parts[:3])
    text = raw_outputs[agent_output_id]["raw_output"]
    needle = claim_text[:40]
    i = text.find(needle)
    if i < 0:
        return {"located": False}
    start = text.rfind("\n", 0, i) + 1
    end = text.find("\n", i)
    end = len(text) if end < 0 else end
    prev_start = text.rfind("\n", 0, max(start - 1, 0)) + 1
    nxt_end = text.find("\n", end + 1)
    headings = [m for m in re.finditer(r"^(#{1,4} .*|\*\*\d+\..*)$", text[:i], flags=re.M)]
    return {
        "located": True, "agent_output_id": agent_output_id, "char_offset": i,
        "section_heading": headings[-1].group(0) if headings else None,
        "paragraph_or_bullet": text[start:end][:1800],
        "previous_line": text[prev_start:max(start - 1, 0)][:600],
        "next_line": text[end + 1:(len(text) if nxt_end < 0 else nxt_end)][:600],
        "claim_sentence_itself_carries_fragment_marker": bool(re.search(r"fragment_?id", claim_text)),
    }


def mapper_reproduction(claim_id, alpha_id):
    """Re-run the PRODUCTION mapper on the saved structured record with the saved LLM selection injected (no gateway, no network)."""
    saved = matches[claim_id]
    outcome = {"outcome": "selected", "alpha_id": alpha_id, "fallback_reason": None, "diagnostic": {"enabled": True, "used": True, "status": "llm_selected"}}
    got = map_claim_to_alpha(rec_by[claim_id], taxonomy, llm_outcome_override=outcome)
    cand_new = next(c for c in got["candidate_scores"] if c["alpha_id"] == alpha_id)
    cand_old = next(c for c in saved["candidate_scores"] if c["alpha_id"] == alpha_id)
    keys = ("score", "keyword_score", "factor_score", "direction_score", "semantic_score", "relation", "eligible", "rejection_reason", "matched_keywords", "matched_factors")
    return {
        "reproduced_candidate": {k: cand_new.get(k) for k in keys},
        "saved_candidate": {k: cand_old.get(k) for k in keys},
        "candidate_reproduced_exactly": all(cand_new.get(k) == cand_old.get(k) for k in keys),
        "reproduced_final": {k: got.get(k) for k in ("matched_alpha", "match_status", "score", "assertion_status", "semantic_polarity", "deterministic_top_alpha", "deterministic_match_status")},
        "saved_final": {k: saved.get(k) for k in ("matched_alpha", "match_status", "score", "assertion_status", "semantic_polarity", "deterministic_top_alpha", "deterministic_match_status")},
        "final_reproduced_exactly": all(got.get(k) == saved.get(k) for k in ("matched_alpha", "match_status", "score", "assertion_status", "semantic_polarity", "deterministic_top_alpha", "deterministic_match_status")),
        "score_formula": "score = 0.50*keyword_score + 0.30*factor_score + 0.08*direction_score + 0.12*semantic_score   (alpha_mapper._candidate_score)",
        "score_recomputed_from_components": round(0.50 * cand_old["keyword_score"] + 0.30 * cand_old["factor_score"] + 0.08 * cand_old["direction_score"] + 0.12 * cand_old["semantic_score"], 4),
        "semantic_score_rule": "semantic_score = semantic_score_for_relation(relation) ONLY IF keyword_score > 0 or factor_score > 0, else 0.0 (alpha_mapper line 217); semantic_score_for_relation('activation') = 1.0 -- a relation-class indicator, not a model judgement",
    }


def verification_view(claim_id):
    r = rec_by[claim_id]
    review = r.get("content_support_review") or {}
    detail = r.get("content_support_llm_detail")
    detail = json.loads(detail) if isinstance(detail, str) else (detail or {})
    src = src_by.get(review.get("linked_source_id") or r.get("linked_source_id"))
    stored = next((row for row in jload(derived / "evidence_eligibility_requalification.json").get("claims_requalified", []) if row.get("claim_id") == claim_id), None)
    elig = compute_verified_support_eligibility(r, sources)
    return {
        "source_link": {k: r.get(k) for k in ("source_link_status", "linked_source_id", "linked_source_ids", "source_link_method")},
        "review_binding": {k: review.get(k) for k in ("status", "method", "linked_source_id", "linked_source_ids", "content_hash")},
        "bound_source": None if src is None else {k: src.get(k) for k in ("source_id", "source_type", "title", "provider", "instrument", "observation_date", "retrieved_at", "published_at", "fragment_id", "content_hash", "unit", "metadata_status")},
        "hash_check_sha256_excerpt_equals_stored_content_hash": None if src is None else hashlib.sha256((src.get("excerpt") or "").strip().encode("utf-8")).hexdigest() == src.get("content_hash"),
        "review_hash_equals_source_hash": None if src is None else review.get("content_hash") == src.get("content_hash"),
        "llm_content_support": {k: detail.get(k) for k in ("llm_status", "support_basis", "used_source_id", "used_location", "core_proposition", "supporting_quote_or_data", "inference_facts", "inference_assumptions", "unsupported_remainder", "unsupported_remainder_materiality", "rationale")},
        "eligibility_recomputed_now_by_production_function": {k: elig.get(k) for k in ("eligible", "reason_code")},
        "eligibility_saved_in_requalification_artifact": None if stored is None else {k: stored.get(k) for k in ("eligibility_after", "reason_after")},
    }


def official_read(claim_id, alpha_id):
    """What the official scorer reads for this claim: exactly the three multiplicands of activation_scorer_v2._evidence_quality_component."""
    m = matches[claim_id]
    relation = efi.relation_for_match(m, alpha_id)
    assertion = str(m.get("assertion_status") or "unknown").lower()
    rel_w = act.RELATION_WEIGHTS.get(relation, 0.0)
    ass_w = act.ASSERTION_WEIGHTS.get(assertion, 0.0)
    return {
        "fields_read": {"record['score']": m["score"], "candidate['relation'] (via relation_for_match)": relation, "record['assertion_status']": assertion},
        "multipliers": {"RELATION_WEIGHTS[relation]": rel_w, "ASSERTION_WEIGHTS[assertion]": ass_w},
        "weight_contribution_to_its_fact_group": round(m["score"] * rel_w * ass_w, 6),
        "formula": "contribution = match_score x RELATION_WEIGHTS[relation] x ASSERTION_WEIGHTS[assertion]; per fact group the best member counts; sum over groups / EVIDENCE_QUALITY_SATURATION(4.0) x 100 = raw; x 0.35 = points",
    }


# ------------------------------------------------------------------ A301 claims 31 / 33 / 36
a301_rows = {}
for n, claim_id in A301_CLAIMS.items():
    r, m = rec_by[claim_id], matches[claim_id]
    call = calls.get(claim_id)
    a301_rows[str(n)] = {
        "claim_id": claim_id,
        "claim": r["claim"],
        "agent": r["agent"], "source_section": r["source_section"], "claim_index_0based": r["claim_index"], "extraction_method": r["extraction_method"],
        "record_fields_consumed_by_mapper": {"direction": r["direction"], "factors": r["factors"], "entities": r["entities"], "confidence": r["confidence"],
                                              "claim_quality": r["claim_quality"], "claim_quality_reason_codes": r["claim_quality_reason_codes"], "assertion_status": r["assertion_status"], "semantic_polarity": r["semantic_polarity"]},
        "context_in_original_report": context_of(claim_id, r["claim"]),
        "verification": verification_view(claim_id),
        "llm_alpha_selection": {
            "llm_selected_alpha_id": m.get("llm_selected_alpha_id"), "classifier": m.get("classifier"), "alpha_match_method": m.get("alpha_match_method"),
            "deterministic_top_alpha_before_llm": m.get("deterministic_top_alpha"), "deterministic_match_status_before_llm": m.get("deterministic_match_status"),
            "saved_call": None if call is None else {k: call.get(k) for k in ("call_id", "task", "model", "prompt_version", "input_sha256", "provider_status", "retry_count", "fallback_reason")},
            "model_output_contract": "alpha_classifier output = exactly {decision: select|none, selected_alpha_id}; no relevance strength, no direction, no confidence (alpha_mapper._classify_alpha_with_llm.validate_response)",
        },
        "final_match": {k: m.get(k) for k in ("match_status", "matched_alpha", "reason", "score", "keyword_score", "factor_score", "direction_score", "assertion_status", "semantic_polarity", "matched_evidence_stance", "matched_stance_reason_codes")},
        "relation_of_matched_candidate": next(c for c in m["candidate_scores"] if c["alpha_id"] == "A301")["relation"],
        "stance_method": next(c for c in m["candidate_scores"] if c["alpha_id"] == "A301")["stance_method"],
        "mapper_reproduction": mapper_reproduction(claim_id, "A301"),
        "official_scoring_read": official_read(claim_id, "A301"),
    }

# ------------------------------------------------------------------ all subsets of the official pool (production scorer)
company_names = company_names_for_ticker(TICKER)
view = activation


def a301_score(keep):
    variant = []
    for rec in records:
        if rec["claim_id"] in A301_CLAIMS.values() and rec["claim_id"] not in keep:
            rec = {**rec, "content_support_review": {}}  # leaves the verified pool (NOT_REVIEWED); nothing else changes
        variant.append(rec)
    out = score_alpha_v2_verified("A301", payload, taxonomy, structured_records=variant, sources=sources, graph_edges=graph.get("edges") or (),
                                  ticker=TICKER, company_names=company_names, run_timestamp=view["run_timestamp"], as_of=view["as_of"])
    comp = out["components"]
    return {"activation_score": out["activation_score"], "direction": out["direction"], "unique_evidence_count": out.get("unique_evidence_count"),
            "points": {k: v["contribution"] for k, v in comp.items()}, "cap_reason_codes": out["cap_reason_codes"]}


full = a301_score(set(A301_CLAIMS.values()))
subsets = {}
for size in range(0, 4):
    for combo in itertools.combinations(sorted(A301_CLAIMS), size):
        subsets["+".join(map(str, combo)) or "(none)"] = a301_score({A301_CLAIMS[n] for n in combo})
loo = {f"without_{n}": subsets["+".join(map(str, [k for k in sorted(A301_CLAIMS) if k != n]))]["activation_score"] for n in sorted(A301_CLAIMS)}

# ------------------------------------------------------------------ facts / periods / calculation relations
snap = src_by["src_582ac24bf4319648"]["data_snapshot"]
rev, gp = snap["periods"], snap["all_line_items"]["Gross Profit"]
M = lambda v: round(v / 1e6)
fact_rows = {
    "31": {"proposition": "quarterly Total Revenue sequence, five consecutive quarters", "line_item": "Total Revenue", "periods": sorted(rev), "operation": "none (direct restatement)",
           "claim_numbers_USD_M": [7685, 9246, 10270, 10253, 11536], "snapshot_values_USD_M": [M(rev[p]) for p in sorted(rev)],
           "all_claim_numbers_found_in_snapshot_at_expected_period": [M(rev[p]) for p in sorted(rev)] == [7685, 9246, 10270, 10253, 11536]},
    "33": {"proposition": "sequential pause then re-acceleration (derived reading of three of the same revenue points)", "line_item": "Total Revenue", "periods": ["2025-12-31", "2026-03-31", "2026-06-30"],
           "operation": "quarter-over-quarter differences", "claim_numbers_USD_M": [10253, 10270],
           "snapshot_values_USD_M": [M(rev["2026-03-31"]), M(rev["2025-12-31"])],
           "derived": {"Q1'26_vs_Q4'25_USD_M": M(rev["2026-03-31"]) - M(rev["2025-12-31"]), "Q2'26_vs_Q1'26_USD_M": M(rev["2026-06-30"]) - M(rev["2026-03-31"]),
                       "Q2'26_vs_Q1'26_pct": round((rev["2026-06-30"] / rev["2026-03-31"] - 1) * 100, 2),
                       "snapshot_comparison_block": snap["comparison"]},
           "all_claim_numbers_found_in_snapshot_at_expected_period": [M(rev["2026-03-31"]), M(rev["2025-12-31"])] == [10253, 10270]},
    "36": {"proposition": "Gross Profit YoY for the quarter ending 2026-06-30", "line_item": "Gross Profit", "periods": ["2025-06-30", "2026-06-30"], "operation": "year-over-year ratio",
           "claim_numbers_USD_M": [6203, 3059], "snapshot_values_USD_M": [M(gp["2026-06-30"]), M(gp["2025-06-30"])],
           "derived": {"ratio": round(gp["2026-06-30"] / gp["2025-06-30"], 4), "pct_change": round((gp["2026-06-30"] / gp["2025-06-30"] - 1) * 100, 2)},
           "all_claim_numbers_found_in_snapshot_at_expected_period": [M(gp["2026-06-30"]), M(gp["2025-06-30"])] == [6203, 3059]},
}
shared_31_33 = sorted(set(fact_rows["31"]["periods"]) & set(fact_rows["33"]["periods"]))
signatures = {}
for n, claim_id in A301_CLAIMS.items():
    r = rec_by[claim_id]
    signed = efi._sign(efi.EvidenceFactCandidate(claim_id=claim_id, claim_text=f"{r['claim']} {r['evidence']}".strip(), factors=tuple(r["factors"]), assertion_status=r["assertion_status"],
                                                 semantic_polarity=r["semantic_polarity"], duplicate_group_id=r.get("duplicate_group_id"), linked_source_id=r["linked_source_id"]))
    signatures[n] = signed
grouping = {
    "saved_fact_groups": {str(n): a301_saved["evidence_fact_groups"] and [g for g in a301_saved["evidence_fact_groups"] if A301_CLAIMS[n] in json.dumps(g)][:1] for n in A301_CLAIMS},
    "numeric_signatures": {str(n): s.numeric_signature for n, s in signatures.items()},
    "pairwise": {f"{a}-{b}": {"token_jaccard": round(efi._jaccard(signatures[a].token_set, signatures[b].token_set), 3), "jaccard_threshold": efi.NEAR_MATCH_JACCARD_THRESHOLD,
                              "same_numeric_signature": signatures[a].numeric_signature == signatures[b].numeric_signature,
                              "same_duplicate_group": signatures[a].candidate.duplicate_group_id == signatures[b].candidate.duplicate_group_id,
                              "shared_linked_source": signatures[a].candidate.linked_source_id == signatures[b].candidate.linked_source_id}
                 for a, b in itertools.combinations(sorted(A301_CLAIMS), 2)},
    "rule_that_kept_them_apart": "evidence_fact_index.group_evidence_candidates: a shared linked_source_id is never a fact identity (source-pass requires non-conflicting numeric signature AND a positive same-fact signal); the three claims have conflicting numeric signatures, different duplicate groups and token Jaccard << 0.85",
}
fact_relations = {
    "rows": fact_rows,
    "data_points_shared_between_claim_31_and_33": {"line_item": "Total Revenue", "periods": shared_31_33, "all_of_claim_33s_periods_are_in_claim_31": set(fact_rows["33"]["periods"]) <= set(fact_rows["31"]["periods"])},
    "data_points_shared_between_claim_31_and_36_or_33_and_36": "none: claim 36 uses the Gross Profit line, a different line item",
    "counts": {"distinct_propositions": 3, "distinct_data_lines": 2, "sources": 1, "agents": 1, "report_bullets": {"31+33": "'Revenue acceleration is dramatic.' (same bullet, consecutive sentences)", "36": "'Gross margin expansion.' bullet"}},
    "grouping_evidence": grouping,
}

# ------------------------------------------------------------------ A304 claim
a304 = rec_by[A304_CLAIM]
a304_match = matches[A304_CLAIM]
text = a304["claim"]
norm = cs.normalize_text(text)
patterns = {name: (getattr(cs, name).search(norm).group(0) if getattr(cs, name).search(norm) else None)
            for name in ("_CONDITIONAL_PATTERN", "_CONTRAST_PATTERN", "_NEGATION_PATTERN", "_POSITIVE_PATTERN", "_NEGATIVE_PATTERN", "_COMPETITION_PATTERN", "_INVALIDATION_PATTERN", "_MENTION_ONLY_PATTERN")}
sem = cs.analyze_claim_semantics(norm)
a304_cand = next(c for c in a304_match["candidate_scores"] if c["alpha_id"] == "A304")
member = {"claim_id": A304_CLAIM, "agent": a304["agent"], "relation": a304_cand["relation"], "assertion_status": a304_match["assertion_status"], "record": a304_match}
role_result = qualify_evidence_group([member], is_ticker_specific=lambda mm: act._is_ticker_specific(a304, TICKER, company_names, act._entities_index(records)))[0]
eligible, excluded, warnings = efi.select_supporting_alpha_claims(payload["matches"], "A304")
conflicts = jload(derived / "conflicts.json")
a304_conflict_rows = []
for ev in conflicts["arbitration"]["candidate_evaluations"]:
    for side in ("alpha_a", "alpha_b"):
        audit = ev["evidence_audit"][side]
        if audit["alpha_id"] == "A304":
            hit = next((i for i in audit["excluded"] if i["claim_id"] == A304_CLAIM), None)
            a304_conflict_rows.append({"pair": f"{ev['alpha_a']} vs {ev['alpha_b']}", "this_claim_excluded_as": hit and hit["reason_code"], "A304_qualifying_claims_in_pair": audit["qualifying_count"],
                                       "pair_outcome": ev["outcome"], "pair_reason_codes": ev["reason_codes"]})
synthetic = {
    "label": "SYNTHETIC illustration, written for this report; not AMD data, not a model result, not a validation sample",
    "cases": {
        "a_negates_A304s_own_mechanism": "AMD's valuation is not a risk because earnings growth fully supports the current multiple.",
        "b_rebuts_a_counter_argument": "The claim that a PEG of 0.64 makes the valuation safe does not hold, because the forward EPS it relies on has not appeared in any reported quarter.",
        "c_mere_mention": "Valuation was not discussed in the meeting; the memo only mentions the multiple.",
    },
}
synthetic["text_rule_output"] = {k: {"assertion_status": cs.analyze_claim_semantics(v).assertion_status, "semantic_polarity": cs.analyze_claim_semantics(v).semantic_polarity, "alpha_relation_A304": cs.alpha_relation(v, "A304")}
                                 for k, v in synthetic["cases"].items()}
a304_chain = {
    "claim_id": A304_CLAIM, "claim": text, "agent": a304["agent"], "source_section": a304["source_section"],
    "context_in_original_report": context_of(A304_CLAIM, text),
    "verification": verification_view(A304_CLAIM),
    "llm_alpha_selection": {
        "llm_selected_alpha_id": a304_match.get("llm_selected_alpha_id"), "classifier": a304_match.get("classifier"),
        "saved_call": {k: calls[A304_CLAIM].get(k) for k in ("call_id", "task", "model", "prompt_version", "input_sha256", "provider_status", "retry_count")},
        "request_direction_field": calls[A304_CLAIM]["input_payload"].get("direction"),
        "what_selection_means": "the alpha_classifier prompt selects the Alpha whose thesis the Evidence most directly and substantively SUPPORTS OR OPPOSES; the output has no direction field. Its own A304 paragraph also says a rebuttal of someone else's valuation argument that does not itself assert a valuation conclusion does not satisfy A304.",
    },
    "deterministic_text_rule_trace": {
        "normalized_text_used": norm[:400], "regex_hits": patterns,
        "analyze_claim_semantics": {"assertion_status": sem.assertion_status, "semantic_polarity": sem.semantic_polarity, "negated": sem.negated, "mixed": sem.mixed, "conditional": sem.conditional},
        "branch_to_assertion_status": "negated and not risk_relief -> 'negated' (claim_semantics.analyze_claim_semantics)",
        "branch_to_semantic_polarity": "no competition/mention_only, not mixed (no _NEGATIVE_PATTERN hit), no risk_relief, no invalidation, negated -> 'mention'",
        "alpha_relation_A304": cs.alpha_relation(text, "A304"), "branch_to_relation": "semantics.semantic_polarity == 'mention' -> 'mention' (claim_semantics.alpha_relation)",
        "candidate_A304": {k: a304_cand.get(k) for k in ("score", "keyword_score", "factor_score", "direction_score", "semantic_score", "relation", "eligible", "rejection_reason", "evidence_stance", "stance_reason_codes", "stance_method")},
        "text_rule_is_not_a_model_output": True,
    },
    "downstream_gates_in_order": {
        "1_pool_selector": {"function": "evidence_fact_index.select_supporting_alpha_claims", "result_for_this_claim": next((e for e in excluded if e["claim_id"] == A304_CLAIM), "ELIGIBLE"),
                            "A304_official_raw_pool_size": len(eligible)},
        "2_activation_assertion_weight": {"ASSERTION_WEIGHTS['negated']": act.ASSERTION_WEIGHTS["negated"], "effect": "even if the relation were 'activation', a negated assertion is excluded by the selector and weighted 0.0"},
        "3_conflict_detector": {"function": "conflict_detector._gather_qualifying_evidence", "reason": "UNSUPPORTED_RELATION (relation not in QUALIFYING_RELATIONS); any reason code returns before the stance-admissibility call",
                                "saved_rejected_rows_mentioning_A304": a304_conflict_rows},
        "4_source_role_rule_if_1_to_3_were_cleared": {"function": "evidence_source_role.qualify_evidence_group", "agent_role": role_result["source_role"],
                                                      "result": role_result["activation_qualification_reason"], "activation_eligible": role_result["activation_eligible"],
                                                      "note": "computed on a one-member group with the real production ticker-specific test; shows that a resolved relation alone would not admit this Secondary-role claim"},
    },
    "existing_semantic_results_that_could_answer_the_relation": {
        "alpha_classifier": "answers 'which Alpha does it engage' only (select A304), not support/oppose",
        "content_support_verification": "answers axis 1 (source supports claim) only",
        "evidence_stance_classifier": "the task that answers support/oppose/mention/background per (claim, target Alpha): NOT obtained for this pair (Round 17: pair is in the frozen 162-pair manifest, reusable_from_base_run=false; batch 0 timed out and the run stopped before this pair)",
        "structure_extractor": "no structure edge is tied to this claim",
        "conclusion": "no valid model judgment of the relation exists, so none is masked by the consumer; the relation stays unresolved",
    },
    "text_rule_on_three_synthetic_cases": synthetic,
}

# ------------------------------------------------------------------ A301 zero / near-zero components
ent_idx = act._entities_index(records)
ticker_rows = {}
for n, claim_id in A301_CLAIMS.items():
    r = rec_by[claim_id]
    terms = [TICKER] + list(company_names)
    ticker_rows[str(n)] = {"claim_text_names_ticker_or_company": any(act._token_boundary_match(t, r["claim"]) for t in terms), "terms_tested": terms, "entities_field": ent_idx.get(claim_id),
                           "is_ticker_specific_by_production_function": act._is_ticker_specific(r, TICKER, company_names, ent_idx),
                           "bound_source_instrument": src_by[r["linked_source_id"]].get("instrument")}
edges = jload(derived / "extracted_structures.json")["edges"]
a301_committed = sorted(c for c, m in matches.items() if m["match_status"] == "matched" and m["matched_alpha"] == "A301")
edge_claims = {c for e in edges for c in (e.get("source_claim_ids") or [])}
raw_eligible, raw_excluded, _ = efi.select_supporting_alpha_claims(payload["matches"], "A301")
zero_components = {
    "agent_independence": {"saved": a301_saved["components"]["agent_independence"], "formula": "0.70 x min(distinct_agents/3,1)x100 + 0.30 x min(cross_agent_confirmed_groups/2,1)x100", "distinct_agents": ["fundamental_agent"],
                           "recomputed_raw": round(0.70 * min(1 / 3, 1) * 100 + 0.30 * 0, 4), "manufactured": False,
                           "note": "a single agent gives 1/3 of the coverage term; the term is independent of every claim's match score (it needs only >= 1 qualifying claim)"},
    "ticker_specificity": {"saved": a301_saved["components"]["ticker_specificity"], "rule": "activation_scorer_v2._is_ticker_specific: the claim TEXT must name the ticker/company at a token boundary; the entities field is not trusted (the run ticker is auto-appended upstream); the bound source's instrument is not consulted",
                           "per_claim": ticker_rows,
                           "counterfactual_NOT_APPLIED": {"if_bound_source_instrument_counted": "ticker_specificity raw 0 -> 100, +10.0 points, A301 21.3056 -> 31.3056 (still < 50); this is a scoring-policy change (new input to a frozen formula), not a consumption fix"}},
    "local_structure": {"saved": a301_saved["components"]["local_structure_support"], "relation_edges_total": len(edges), "edges_built_by": {"canonical_relation": 17, "llm_structure_extractor": 0, "deterministic": 0},
                        "committed_A301_matches": len(a301_committed), "of_which_behind_any_relation_edge": len([c for c in a301_committed if c in edge_claims]),
                        "official_pool_claims_behind_an_edge": [n for n, c in A301_CLAIMS.items() if c in edge_claims],
                        "graph_edges_incident_to_A301": 0,
                        "structure_extractor_calls_in_original_run": 3, "claims_given_to_extractor": ["news_agent:news_report:claim:67", "news_agent:news_report:claim:68", "fundamental_agent:fundamentals_report:claim:5"],
                        "verdict": "no structure was built from A301's claims (data-restatement sentences contain no cause-effect relation); existing structure is not mis-consumed"},
    "pool_funnel_A301": {"committed_matches": len(a301_committed), "raw_pool_after_quality_relation_assertion": len(raw_eligible),
                         "raw_pool_excluded_reasons": {k: sum(1 for e in raw_excluded if e["reason"] == k) for k in sorted({e["reason"] for e in raw_excluded})},
                         "official_verified_pool": a301_saved["unique_evidence_count"] and len(a301_saved["claim_ids"])},
}

out = {
    "purpose": "Round 19 reproduction: LLM judgement -> official score, A301 claims 31/33/36; A304 claim 10; A301 zero components",
    "zero_model_calls": True, "inputs": {"derived_execution": DERIVED, "original_run": ROOT, "recovery_run": RECOVERY},
    "a301_official_score_saved": a301_saved["activation_score"], "a301_official_score_reproduced_by_production_scorer": full["activation_score"],
    "a301_reproduced_exactly": abs(a301_saved["activation_score"] - full["activation_score"]) < 1e-9,
    "a301_claims": a301_rows,
    "a301_subset_scores_production_scorer": subsets,
    "a301_leave_one_out_MARGINAL_NON_ADDITIVE": {"official": full["activation_score"], **loo,
                                                 "reading": "marginal contributions of different claims overlap (claim 33 or 36 alone would also keep the agent-coverage and recency points); they must not be added up or read as 'claim 31 produced all 21.3056'"},
    "a301_fact_relations": fact_relations,
    "a301_zero_components": zero_components,
    "a304_claim10": a304_chain,
}
(HERE / "consumption_chain_reproduction.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str))
print("official A301 score: saved", out["a301_official_score_saved"], "| reproduced", out["a301_official_score_reproduced_by_production_scorer"], "| exact", out["a301_reproduced_exactly"])
for n, row in a301_rows.items():
    mr = row["mapper_reproduction"]
    print(f"claim {n}: candidate reproduced exactly={mr['candidate_reproduced_exactly']} final reproduced exactly={mr['final_reproduced_exactly']} | score {row['final_match']['score']} | weight contribution {row['official_scoring_read']['weight_contribution_to_its_fact_group']} | eligibility now {row['verification']['eligibility_recomputed_now_by_production_function']}")
print("subsets:", {k: v["activation_score"] for k, v in subsets.items()})
print("A304 gate 1:", a304_chain["downstream_gates_in_order"]["1_pool_selector"]["result_for_this_claim"], "| gate 4:", a304_chain["downstream_gates_in_order"]["4_source_role_rule_if_1_to_3_were_cleared"]["result"])
print("synthetic text-rule output:", synthetic["text_rule_output"])
print("wrote", HERE / "consumption_chain_reproduction.json")
