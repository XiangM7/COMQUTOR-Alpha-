#!/usr/bin/env python3
"""T3 closeout: the consumption chain Alpha raw selection -> mapper relation -> LLM direction -> source eligibility -> evidence selector,
for every sample with a matched Alpha, from the match records the replayed L4 step actually consumed (zero network, no code change).

For each sample it records what each field says and which production function reads it, then evaluates the selector's gates ONE BY ONE
(quality, evidence text, match score, relation, assertion status) so that a sample excluded at the relation gate also shows which later
gates it would meet. That per-gate listing is a diagnostic only: the production selector stops at the first failing gate, and nothing here
changes which field has authority.

    python trace_relation_consumption.py --replay-dir 05_offline_replay/after_citation_fix --out 02_relation_consumption/relation_chain.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

FOCUS = ("t3v3-005", "t3v3-006", "t3v3-014", "t3v3-039")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay-dir", required=True)
    ap.add_argument("--review-form", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    from comqutor_alpha.graph_engine.evidence_fact_index import (
        QUALIFYING_RELATIONS,
        relation_for_match,
        select_supporting_alpha_claims,
    )
    from comqutor_alpha.structure_engine.claim_quality import CONSUMER_ACTIVATION, is_claim_eligible
    from comqutor_alpha.structure_engine.claim_semantics import (
        alpha_relation,
        analyze_claim_semantics,
        normalize_text,
    )

    replay_dir = Path(args.replay_dir)
    inputs = json.loads((replay_dir / "l4_inputs_by_sample.json").read_text(encoding="utf-8"))
    predictions = {json.loads(line)["sample_id"]: json.loads(line) for line in (replay_dir / "replayed_predictions.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()}
    reviewer = {i["sample_id"]: i["judgments"] for i in json.loads(Path(args.review_form).read_text(encoding="utf-8"))["items"]}
    rows = []
    for sid in sorted(predictions):
        p = predictions[sid]
        match = inputs[sid]["match"]
        raw, final = p["L2"]["raw_selected_alpha"], p["L2"]["predicted_alpha"]
        row = {"sample_id": sid, "L2_raw_selection": raw, "L2_after_gates": final if p["L2"]["outcome_code"] == "MATCHED" else p["L2"]["outcome_code"],
               "gate_overrides": {k: v for k, v in (p["L2"].get("override") or {}).items() if v},
               "reviewer": {k: reviewer[sid][k] for k in ("R2_alpha", "R3_direction", "R4_evidence_eligibility")}}
        if not final:
            row["chain"] = "no matched Alpha -> no relation, direction or eligibility step"
            rows.append(row)
            continue
        candidate = next((c for pool in ("eligible_candidates", "top_candidates", "candidate_scores") for c in (match.get(pool) or [])
                          if isinstance(c, dict) and c.get("alpha_id") == final), {})
        text = str(match.get("evidence") or match.get("claim") or "")
        semantics = analyze_claim_semantics(normalize_text(text))
        eligible, excluded, _ =select_supporting_alpha_claims([match], final)
        relation = relation_for_match(match, final)
        gates = {
            "1_claim_quality_analytical": is_claim_eligible(match, CONSUMER_ACTIVATION),
            "2_claim_id_and_evidence_text": bool(str(match.get("claim_id") or "").strip() and text.strip()),
            "3_match_score_finite_in_0_1": isinstance(match.get("score"), (int, float)) and 0.0 <= float(match["score"]) <= 1.0,
            "4_relation_in_activation_conditional_mixed": relation in QUALIFYING_RELATIONS,
            "5_assertion_not_negated": str(match.get("assertion_status") or "unknown").lower() != "negated",
        }
        row.update({
            "mapper": {"relation_read_by_selector": relation, "relation_from_text_rule_now": alpha_relation(text, final),
                       "assertion_status": match.get("assertion_status"), "semantic_polarity": match.get("semantic_polarity"),
                       "text_rule_flags": {"negated": semantics.negated, "conditional": semantics.conditional, "mixed": semantics.mixed,
                                           "polarity": semantics.semantic_polarity},
                       "deterministic_match_score": match.get("score"), "claim_quality": match.get("claim_quality")},
            "llm_direction": {"L3": p["L3"].get("stance"), "candidate_evidence_stance": candidate.get("evidence_stance"),
                              "stance_method": candidate.get("stance_method"), "matched_evidence_stance": match.get("matched_evidence_stance")},
            "source_eligibility": p["L4"]["verified_support"],
            "selector": {"eligible": bool(eligible), "first_failing_gate": excluded[0]["reason"] if excluded else None},
            "selector_gates_one_by_one": gates,
            "gates_failing_besides_relation": [g for g, ok in gates.items() if not ok and not g.startswith("4_")],
            "activation_pool_eligible": p["L4"]["activation_pool_eligible"],
        })
        rows.append(row)
    doc = {
        "replay": str(replay_dir),
        "field_authority": {
            "relation (mapper)": "claim_semantics.alpha_relation, a deterministic text rule; read by evidence_fact_index.select_supporting_alpha_claims "
                                  "(the single activation-evidence selector). Authority matrix: 'Factor/relation vocabulary remains deterministic authority'.",
            "assertion_status (mapper)": "deterministic text rule; selector gate 5 and Activation's negated weight 0.",
            "evidence_stance (LLM direction)": "evidence_stance_llm writes candidate_scores[].evidence_stance; read by conflict_admissibility and the "
                                                "conflict display only. Register PD-006 NOT_APPROVED: 'Evidence Stance remains deterministic shadow and "
                                                "cannot affect Activation or Conflict'; authority matrix: 'No production authority', 'CURRENT effect is SHADOW_ONLY'.",
            "verified support": "source_provenance.compute_verified_support_eligibility, from the content-support status and source link.",
        },
        "focus": list(FOCUS),
        "samples": rows,
    }
    Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    for row in rows:
        if row["sample_id"] in FOCUS or row.get("mapper"):
            m = row.get("mapper") or {}
            print(row["sample_id"], row["L2_raw_selection"], "->", row["L2_after_gates"], "| relation", m.get("relation_read_by_selector"),
                  "| assertion", m.get("assertion_status"), "| LLM", (row.get("llm_direction") or {}).get("L3"), "| verified",
                  (row.get("source_eligibility") or {}).get("reason_code"), "| selector", (row.get("selector") or {}).get("first_failing_gate"),
                  "| other failing gates", row.get("gates_failing_besides_relation"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
