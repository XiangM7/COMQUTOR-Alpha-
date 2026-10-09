#!/usr/bin/env python3
"""Original (Round 23) verdict next to the new (Round 24) verdict for each ticker, item by item: status, reasons, the rules in effect with their approval basis,
the evidence trigger and its source, the Alpha facts, the conflict results with B2's own reasons, the blocking impact, and what is diagnostic or not evaluable.
Reads two verdict documents and the saved runs' conflicts.json (read-only); writes two new files.

    python build_six_ticker_comparison.py --original <round 23 formal_acceptance_verdicts.json> --new <round 24 formal_acceptance_verdicts.json> --out-dir <new dir>
"""
import argparse
import json
import sys
from pathlib import Path

REPO = next(p for p in Path(__file__).resolve().parents if (p / "comqutor_alpha").is_dir())
sys.path.insert(0, str(REPO))

from comqutor_alpha.regression.acceptance_engine import (  # noqa: E402
    pair_admissibility_lookup,
    pair_record_state,
)


def _subject(r):
    return r.get("rule_id") or r.get("pair") or r.get("alpha_id") or ",".join(r.get("pairs") or ()) or ""


def _reasons(verdict):
    return sorted({(kind, r.get("family"), _subject(r), r.get("verdict")) for kind, rows in (("fail", verdict.get("failure_reasons") or ()), ("review", verdict.get("review_reasons") or ())) for r in rows}, key=str)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--original", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--runs-root", default=str(REPO / "outputs" / "runs"))
    args = ap.parse_args(argv)
    out = Path(args.out_dir)
    if out.exists() and any(out.iterdir()):
        print("refusing: output directory is not empty", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    original = json.loads(Path(args.original).read_text(encoding="utf-8"))["tickers"]
    new = json.loads(Path(args.new).read_text(encoding="utf-8"))["tickers"]
    doc = {"tickers": {}}
    for ticker, entry in new.items():
        old_v, new_v = original[ticker]["verdict"], entry["verdict"]
        old_r, new_r = set(map(tuple, _reasons(old_v))), set(map(tuple, _reasons(new_v)))
        conflicts = json.loads((Path(args.runs_root) / entry["run_id"] / "conflicts.json").read_text(encoding="utf-8"))
        lookup = pair_admissibility_lookup(conflicts)
        label = new_v["effective_rules"]["ticker_rules"]
        declared = sorted(set(label["must_detect_if_evidence_present"]["pairs"]) | set(label["conditional_only"]["pairs"]) | set(label["allowed_main_conflicts"]["pairs"]))
        pair_rows = []
        for pair in declared:
            record = lookup.get(pair)
            bucket = next(f for f in ("must_detect_if_evidence_present", "conditional_only", "allowed_main_conflicts") if pair in label[f]["pairs"])
            pair_rows.append(
                {
                    "pair": pair,
                    "declared_as": bucket,
                    "arbitration_state": pair_record_state(record),
                    "outcome": (record or {}).get("outcome"),
                    "b2_status": (record or {}).get("admissibility_status"),
                    "b2_reason_codes": (record or {}).get("reason_codes") or (record or {}).get("entry_reason_codes"),
                    "supports_bull_bear": [(record or {}).get("bull_supporting_evidence_count"), (record or {}).get("bear_supporting_evidence_count")],
                    "scores_bull_bear": [(record or {}).get("bull_score"), (record or {}).get("bear_score")],
                }
            )
        doc["tickers"][ticker] = {
            "run_id": entry["run_id"],
            "status_original": old_v["formal_status"],
            "status_new": new_v["formal_status"],
            "reasons_removed": sorted(old_r - new_r, key=str),
            "reasons_added": sorted(new_r - old_r, key=str),
            "reasons_unchanged": sorted(old_r & new_r, key=str),
            "contract_rules": [
                {
                    "rule_id": r["rule_id"],
                    "family": r["family"],
                    "blocking": r["blocking"],
                    "trigger": {k: r["evidence_trigger"].get(k) for k in ("state", "strength", "source", "matrix_run_id", "evaluated_run_id", "reason_code")},
                    "alpha_facts": [
                        {k: a[k] for k in ("alpha_id", "identification_state", "claims_matched_to_this_alpha", "claims_classification_unavailable", "activation_level", "activation_score", "level_is_official_detected_level")}
                        for a in (r.get("alpha_recognition") or r.get("component_alphas") or ())
                    ],
                    "requirement_satisfied": (r.get("requirement") or {}).get("satisfied"),
                    "verdict": r["verdict"],
                    "reason_code": r["reason_code"],
                    "blocks_release": r["blocks_release"],
                    "authority_basis_first_line": (r.get("authority_basis") or [""])[0],
                    "composite": {k: r.get(k) for k in ("allowed_family", "admitted_in_allowed_family", "admitted_outside_allowed_family")} if r["hit_type"] == "COMPOSITE_STRUCTURE_HIT" else None,
                }
                for r in new_v["contract_rule_results"]
            ],
            "contract_rules_not_executed_for_ticker": new_v["coverage"]["contract_rules_not_executed_for_ticker"],
            "release": new_v["release"],
            "conflicts": {"admitted": entry["admitted_conflicts"], "main_conflict": entry["main_conflict"], "declared_pairs": pair_rows, "undeclared_admitted": new_v["undeclared_admitted_conflicts"]},
            "diagnostic_findings": [{k: d[k] for k in ("pair", "verdict", "b2_reason_codes", "authority", "decides_formal_status")} for d in new_v["diagnostic_findings"]],
            "not_evaluable_items": [r for r in _reasons(new_v) if r[3] == "not_evaluable"],
            "pass_scope_note": new_v["coverage"].get("pass_scope_note"),
        }
    (out / "six_ticker_original_vs_new.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    def cell(v):
        return "—" if v in (None, [], "", {}) else str(v).replace("|", "/")

    md = ["# Round 23 verdict vs Round 24 verdict, ticker by ticker", "", "| Ticker | Run | Original | New | Why the status moved (or did not) |", "|---|---|---|---|---|"]
    for t, d in doc["tickers"].items():
        why = []
        if d["reasons_removed"]:
            why.append("left the verdict: " + "; ".join(f"{r[1]} {r[2]}" for r in d["reasons_removed"]))
        if d["reasons_added"]:
            why.append("entered the verdict: " + "; ".join(f"{r[1]} {r[2]} ({r[3]})" for r in d["reasons_added"]))
        if d["reasons_unchanged"]:
            why.append("unchanged: " + "; ".join(f"{r[1]} {r[2]}" for r in d["reasons_unchanged"]))
        md.append(f"| {t} | {d['run_id'][:8]} | {d['status_original']} | **{d['status_new']}** | {' ;  '.join(why) or '—'} |")
    for t, d in doc["tickers"].items():
        md += ["", f"## {t} — run `{d['run_id']}`", ""]
        md += ["**Gold contract rules executed for this ticker**", ""]
        if d["contract_rules"]:
            md += ["| Rule | Blocking | Evidence trigger (source / bound run → this run) | Alpha facts: identified / level (score) | Requirement met | Result | Blocks release | Reason |", "|---|---|---|---|---|---|---|---|"]
            for r in d["contract_rules"]:
                facts = "; ".join(f"{a['alpha_id']}: {a['identification_state']} ({a['claims_matched_to_this_alpha']} claims) / {a['activation_level']} ({a['activation_score']})" for a in r["alpha_facts"])
                tr = r["trigger"]
                md.append(
                    f"| {r['rule_id']} | {'yes' if r['blocking'] else 'no'} | {tr['state']}{'/' + str(tr['strength']) if tr['strength'] else ''} — {cell(tr['source'])}; {str(tr['matrix_run_id'])[:8]} → {str(tr['evaluated_run_id'])[:8]} | {cell(facts)} | {cell(r['requirement_satisfied'])} | {r['verdict']} | {'YES' if r['blocks_release'] else 'no'} | {cell(r['reason_code'])} |"
                )
        else:
            md.append("(none: no executed contract rule belongs to this ticker)")
        md += ["", f"Contract rules of this ticker NOT executed by the entry: {', '.join(d['contract_rules_not_executed_for_ticker']) or '—'}.  Release: **{d['release']['release_status']}** (blocks_release={d['release']['blocks_release']}; blocking unresolved: {d['release']['blocking_unresolved'] or '—'}).", ""]
        md += ["**Conflicts: what the run did, and what B2 said about each declared pair**", "", f"Admitted: {', '.join(d['conflicts']['admitted']) or 'none'}; main: {cell(d['conflicts']['main_conflict'])}; admitted but declared nowhere (review): {', '.join(d['conflicts']['undeclared_admitted']) or '—'}.", "", "| Pair | Declared as | Arbitration record | Outcome / B2 status | B2 or detector reasons | Supports bull/bear | Scores bull/bear |", "|---|---|---|---|---|---|---|"]
        for p in d["conflicts"]["declared_pairs"]:
            md.append(f"| {p['pair']} | {p['declared_as']} | {p['arbitration_state']} | {cell(p['outcome'])} / {cell(p['b2_status'])} | {cell(p['b2_reason_codes'])} | {p['supports_bull_bear']} | {p['scores_bull_bear']} |")
        md += ["", "**Diagnostic findings (engine-defined; decide nothing):** " + ("; ".join(f"{x['pair']} → {x['verdict']} (B2: {', '.join(x['b2_reason_codes']) or '—'})" for x in d["diagnostic_findings"]) or "none"), ""]
        md += ["**Not evaluable:** " + ("; ".join(f"{r[1]} {r[2]}" for r in d["not_evaluable_items"]) or "none"), ""]
        if d["pass_scope_note"]:
            md += [f"**PASS scope:** {d['pass_scope_note']}", ""]
    (out / "six_ticker_original_vs_new.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("tickers:", len(doc["tickers"]), "->", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
