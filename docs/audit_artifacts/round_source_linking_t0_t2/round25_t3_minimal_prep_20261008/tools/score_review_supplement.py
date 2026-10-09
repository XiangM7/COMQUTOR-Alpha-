#!/usr/bin/env python3
"""Round 25 T3, after the human review: intake checks and a supplement to the frozen scorer. Zero network.

The official result is `t3_joint_sample_driver.py score` (unchanged). Its Alpha metrics use the post-gate outcome, so a model selection that
a production gate overrode counts as SELECTED_BUT_NOT_MATCHED. The reviewer stated that the gate's override is not reference truth, so this
tool adds the raw-selection view through the SAME scoring function, plus per-cell counts and a per-sample comparison. It never changes a
reviewer judgment or a prediction, and it writes new files only.

    python tools/run_with_network_trap.py tools/score_review_supplement.py --predictions <joint_predictions.jsonl> \
        --review-form <reviewed form> --original-form <B1_samples_v4/review_form_v4.json> --addendum <review_materials_frozen_ADDENDUM.json> \
        --materials-dir <execution>-materials --run-summary <execution>/run_summary.json --code-file-hashes <code_snapshot_partB/file_hashes.json> \
        --out-dir <D_human_review>
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
DRIVERS = REPO / "docs/audit_artifacts/round_source_linking_t0_t2"
TAXONOMY = "comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml"
JUDGMENT_KEYS = ("R1_claim_fidelity", "R1_source_relation", "R2_alpha", "R3_direction", "R4_evidence_eligibility")
# the reviewer's arithmetic in T3_Xiang_Mao_review_explanations.md ("数值复算"), recomputed from the same inputs
ARITHMETIC = {
    "FCF QoQ %": (lambda: (1558 / 2566 - 1) * 100, -39.2829),
    "receivables QoQ %": (lambda: (7281 / 6035 - 1) * 100, 20.6462),
    "revenue QoQ %": (lambda: (11536 / 10253 - 1) * 100, 12.5134),
    "forward EPS / static annualized": (lambda: 15.72189 / (1.38 * 4), 2.84817),
    "forward EPS / TTM EPS": (lambda: 15.63089 / 3.92, 3.98747),
    "50-day / 200-day average %": (lambda: (513.5342 / 374.7236 - 1) * 100, 37.0435),
    "attached price / 200-day average %": (lambda: (631.205017 / 374.7236 - 1) * 100, 68.4455),
    "10-06 price / 200 SMA %": (lambda: (654.91 / 379.12 - 1) * 100, 72.7448),
    "R&D YoY %": (lambda: (2528 / 1894 - 1) * 100, 33.4741),
    "gross margin 2026-06 %": (lambda: 6203 / 11536 * 100, 53.7708),
    "gross margin 2025-06 %": (lambda: 3059 / 7685 * 100, 39.8048),
    "capex ratio": (lambda: 808 / 389, 2.07712),
    "to upper band %": (lambda: (691.33 / 654.91 - 1) * 100, 5.5611),
    "to 10 EMA %": (lambda: (618.52 / 654.91 - 1) * 100, -5.5565),
    "to 50 SMA %": (lambda: (518.93 / 654.91 - 1) * 100, -20.7632),
    "net cash (bn)": (lambda: 13.111 - 4.276, 8.835),
}
# the collected daily points the reviewer cites for t3v3-037..040 (market, UTC date) -> Yes price
CITED_POINTS = {
    ("US recession by end of 2026", "2026-09-25"): 0.105, ("US recession by end of 2026", "2026-09-28"): 0.085,
    ("US recession by end of 2026", "2026-10-02"): 0.085, ("US recession by end of 2026", "2026-10-05"): 0.08,
    ("UK recession in 2026", "2026-10-05"): 0.07,
    ("Japan recession in 2026", "2026-10-02"): 0.045, ("Japan recession in 2026", "2026-10-04"): 0.04, ("Japan recession in 2026", "2026-10-05"): 0.045,
}


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_alpha_scorer():
    spec = importlib.util.spec_from_file_location("t3_diag_for_supplement", DRIVERS / "t3_diagnostic_evaluation_driver.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.score_against_human_labels


def intake(args, form: dict, original: dict) -> dict:
    items, orig_items = form["items"], original["items"]
    field_diffs = [(a["sample_id"], k) for a, b in zip(orig_items, items, strict=False) for k in set(a) | set(b) if k != "judgments" and a.get(k) != b.get(k)]
    top_diffs = sorted(k for k in set(original) | set(form) if k != "items" and original.get(k) != form.get(k))
    reviewers = Counter((i["judgments"].get("reviewer_id"), i["judgments"].get("reviewer_role"), i["judgments"].get("reviewed_at"),
                         i["judgments"].get("attests_no_prior_view_of_system_outputs")) for i in items)
    summary = json.loads(Path(args.run_summary).read_text(encoding="utf-8"))
    code_hashes = json.loads(Path(args.code_file_hashes).read_text(encoding="utf-8"))
    frozen_taxonomy = (code_hashes.get("files") or code_hashes).get(TAXONOMY, {}).get("sha256") if isinstance(code_hashes, dict) else None
    addendum = json.loads(Path(args.addendum).read_text(encoding="utf-8"))
    mdir = Path(args.materials_dir)
    raw_checks = {q: _sha(mdir / m["source"]["file"]) == m["source"]["response_sha256"] for q, m in addendum["markets"].items() if m.get("status") == "COLLECTED"}
    lookup = addendum["markets"]["US recession by end of 2026"]["market_lookup"]
    points = {(q, p["observed_at_utc"][:10]): p["yes_price"] for q, m in addendum["markets"].items() for p in m.get("points_in_window", [])}
    reviewed_at = {i["judgments"].get("reviewed_at") for i in items}
    return {
        "files": {"review_form": {"path": str(Path(args.review_form)), "sha256": _sha(args.review_form)},
                  "explanations": {"path": str(Path(args.review_form).with_name("T3_Xiang_Mao_review_explanations.md")),
                                   "sha256": _sha(Path(args.review_form).with_name("T3_Xiang_Mao_review_explanations.md"))}},
        "form_identity": {
            "original_form_sha256": _sha(args.original_form),
            "items": len(items), "same_sample_order": [i["sample_id"] for i in items] == [i["sample_id"] for i in orig_items],
            "non_judgment_item_fields_changed": field_diffs, "top_level_fields_changed": top_diffs,
            "every_item_has_all_judgment_keys": all(all(i["judgments"].get(k) for k in JUDGMENT_KEYS) for i in items),
        },
        "reviewer": [{"reviewer_id": r[0], "reviewer_role": r[1], "reviewed_at": r[2], "attests_no_prior_view_of_system_outputs": r[3], "items": n}
                     for r, n in reviewers.items()],
        "timing": {"reviewed_at": sorted(x for x in reviewed_at if x),
                   "reviewed_at_utc": sorted(datetime.fromisoformat(x).astimezone(timezone.utc).isoformat() for x in reviewed_at if x),
                   "predictions_finished_at": summary.get("finished_at") or summary.get("predict_finished_at"),
                   "note": "the review was completed after the predictions and the execution report existed; the reviewer did not attest to no prior view"},
        "taxonomy": {"path": TAXONOMY, "sha256_now": _sha(REPO / TAXONOMY), "sha256_in_frozen_code_snapshot": frozen_taxonomy,
                     "reviewer_stated_sha256": "c6d523beaee4942c71756a3fddbb8213d4ba2f8653fded088d73031ca80f3bfa"},
        "addendum": {"sha256": _sha(args.addendum), "raw_response_sha256_matches": raw_checks,
                     "gamma_lookup_sha256_matches": _sha(mdir / lookup["file"]) == lookup["response_sha256"],
                     "points_cited_by_reviewer_match": {f"{q} {d}": points.get((q, d)) == v for (q, d), v in CITED_POINTS.items()}},
        "reviewer_arithmetic": {name: {"recomputed": round(fn(), 4), "reviewer": stated, "matches_to_stated_precision": abs(fn() - stated) < 0.0006}
                                for name, (fn, stated) in ARITHMETIC.items()},
    }


def supplement(predictions: list[dict], form: dict, score_alpha) -> dict:
    preds = {p["sample_id"]: p for p in predictions}
    refs = {i["sample_id"]: {**i["judgments"], "ticker": i.get("ticker")} for i in form["items"]}
    items = [{"sample_id": sid, "your_judgment": j["R2_alpha"]} for sid, j in refs.items()]
    raw_records = [{"sample_id": sid, "predicted_alpha": preds[sid]["L2"]["raw_selected_alpha"],
                    "outcome_code": "MATCHED" if preds[sid]["L2"]["raw_selected_alpha"] else "NONE", "quota_category": preds[sid]["cell"]} for sid in refs]
    raw_view = score_alpha(raw_records, items)
    raw_view.pop("steps_covered", None)
    raw_view["view"] = ("RAW model selection before the production gates (alpha_specific_invalidation / positive_requirement); supplement only, "
                        "the official Alpha result is the post-gate view in score_result_official.json")

    def final(p):
        return p["L2"]["predicted_alpha"] if p["L2"]["outcome_code"] == "MATCHED" else p["L2"]["outcome_code"]

    rows, by_cell = [], {}
    for sid, j in refs.items():
        p = preds[sid]
        l1, l2, l3, l4 = p["L1"], p["L2"], p["L3"], p["L4"]
        raw = l2["raw_selected_alpha"] or "NONE"
        row = {
            "sample_id": sid, "cell": p["cell"], "ticker": j["ticker"], "material_status": p["material_status"],
            "reviewer": {k: j[k] for k in JUDGMENT_KEYS},
            "system_L1": l1.get("content_support_status") if l1["status"] == "LLM_RESULT" else f"{l1['status']}: {l1.get('reason')}",
            "system_L2_raw": raw, "system_L2_final": final(p), "gate_override": {k: v for k, v in (l2.get("override") or {}).items() if v},
            "L2_final_agrees": final(p) == j["R2_alpha"], "L2_raw_agrees": raw == j["R2_alpha"],
            "system_L3": l3.get("stance") if l3.get("status") == "LLM_RESULT" else l3.get("status"),
            "system_L4": None if l4["status"] != "DETERMINED" else {
                "activation_pool_eligible": l4["activation_pool_eligible"], "conflict_side_eligible": l4["conflict_side_eligible"],
                "selector_excluded": l4["selector"]["excluded_reason"], "verified_support": l4["verified_support"]["reason_code"]},
        }
        rows.append(row)
        c = by_cell.setdefault(p["cell"], Counter())
        c["items"] += 1
        c["final_agree"] += row["L2_final_agrees"]
        c["raw_agree"] += row["L2_raw_agrees"]
    disagreements = [{"sample_id": r["sample_id"], "reviewer": r["reviewer"]["R2_alpha"], "system_raw": r["system_L2_raw"], "system_final": r["system_L2_final"]}
                     for r in rows if not r["L2_final_agrees"]]
    qualifies = [{"sample_id": r["sample_id"], "reviewer_alpha": r["reviewer"]["R2_alpha"], "reviewer_direction": r["reviewer"]["R3_direction"],
                  "system_final": r["system_L2_final"], "system_L3": r["system_L3"], "system_L4": r["system_L4"]}
                 for r in rows if r["reviewer"]["R4_evidence_eligibility"] == "QUALIFIES"]
    return {
        "L2_alpha_raw_selection_view": raw_view,
        "L2_by_cell": {cell: dict(c) for cell, c in sorted(by_cell.items())},
        "L2_disagreements_post_gate": disagreements,
        "reviewer_distributions": {k: dict(Counter(j[k] for j in refs.values())) for k in JUDGMENT_KEYS},
        "reviewer_QUALIFIES_items": qualifies,
        "per_sample": rows,
        "note": "each link keeps its own denominator; reviewer R4 is single-claim semantic eligibility and does not assert any production gate passed",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    for name in ("--predictions", "--review-form", "--original-form", "--addendum", "--materials-dir", "--run-summary", "--code-file-hashes", "--out-dir"):
        ap.add_argument(name, required=True)
    args = ap.parse_args(argv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    targets = [out_dir / "intake_check.json", out_dir / "score_supplement.json"]
    if any(t.exists() for t in targets):
        print("refusing: output exists", file=sys.stderr)
        return 2
    form = json.loads(Path(args.review_form).read_text(encoding="utf-8"))
    original = json.loads(Path(args.original_form).read_text(encoding="utf-8"))
    predictions = [json.loads(line) for line in Path(args.predictions).read_text(encoding="utf-8").splitlines() if line.strip()]
    for doc, target in ((intake(args, form, original), targets[0]), (supplement(predictions, form, _load_alpha_scorer()), targets[1])):
        target.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print("wrote", target, _sha(target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
