#!/usr/bin/env python3
"""Compares two snapshots written by snapshot_all_saved_run_verdicts.py (the unified entry's verdict for EVERY saved run of the six tickers, before and
after a change) and says, run by run, what changed and WHICH RULE caused it. Pure file comparison: reads two JSON files, writes two new files.

    python compare_verdict_snapshots.py --before old.json --after new.json --out-json delta.json --out-md delta.md
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def _tuples(rows):
    return {tuple(r) for r in rows}


def _is_pair(subject):
    return "__" in str(subject)


def _cause(removed_review, added_review, removed_failure, added_failure, before, after):
    """A contract rule's subject is its rule id (NVDA-A101-AI-GROWTH); a conflict pair's is A101__A304."""
    causes = []
    if any(r[0] == "should_detect_if_supported" for r in removed_review):
        causes.append("conflict-pair should_detect is now a diagnostic that decides nothing (its review item left the verdict)")
    contract_added = [r for r in added_review if not _is_pair(r[1]) and r[0] in ("must_detect_if_evidence_present", "conditional_only")]
    if any(r[2] in ("not_evaluable",) for r in contract_added):
        causes.append("a Gold contract rule that should execute could not be evaluated for this run (the frozen trigger matrix is bound to another run)")
    if any(r[2] == "needs_review" for r in contract_added):
        causes.append("a Gold contract rule needs review on this run")
    if any(r[0] == "must_detect_if_evidence_present" and _is_pair(r[1]) for r in added_review):
        causes.append("conflict-pair must_detect: a required pair without a usable record is now 'not evaluated'")
    if any(f[0] == "must_detect_if_evidence_present" and _is_pair(f[1]) for f in removed_failure):
        causes.append("conflict-pair must_detect: a B2 correct rejection is no longer a failure")
    if any(not _is_pair(f[1]) for f in added_failure):
        causes.append("a Gold contract rule FAILs on this run (the frozen trigger matrix is bound to it)")
    return causes


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--out-md", required=True)
    args = ap.parse_args(argv)
    for out in (args.out_json, args.out_md):
        if Path(out).exists():
            print("refusing: output exists", out, file=sys.stderr)
            return 2
    before = json.loads(Path(args.before).read_text(encoding="utf-8"))["runs"]
    after = json.loads(Path(args.after).read_text(encoding="utf-8"))["runs"]
    if set(before) != set(after):
        print("the two snapshots do not cover the same runs", file=sys.stderr)
        return 3
    rows = []
    for key in sorted(before, key=lambda k: (before[k]["ticker"], str(before[k].get("analysis_date")), before[k]["run_id"])):
        b, a = before[key], after[key]
        rr_b, rr_a = _tuples(b["review_reasons"]), _tuples(a["review_reasons"])
        fr_b, fr_a = _tuples(b["failure_reasons"]), _tuples(a["failure_reasons"])
        row = {
            "ticker": b["ticker"],
            "run_id": b["run_id"],
            "analysis_date": b.get("analysis_date"),
            "status_before": b["formal_status"],
            "status_after": a["formal_status"],
            "changed": b["formal_status"] != a["formal_status"],
            "review_removed": sorted(rr_b - rr_a, key=str),
            "review_added": sorted(rr_a - rr_b, key=str),
            "failure_removed": sorted(fr_b - fr_a, key=str),
            "failure_added": sorted(fr_a - fr_b, key=str),
        }
        row["cause"] = _cause(rr_b - rr_a, rr_a - rr_b, fr_b - fr_a, fr_a - fr_b, b, a)
        rows.append(row)
    transitions = Counter((r["status_before"], r["status_after"]) for r in rows if r["changed"])
    by_ticker = {}
    for r in rows:
        t = by_ticker.setdefault(r["ticker"], {"runs": 0, "changed": 0})
        t["runs"] += 1
        t["changed"] += int(r["changed"])
    doc = {
        "runs_compared": len(rows),
        "runs_whose_formal_status_changed": sum(1 for r in rows if r["changed"]),
        "runs_whose_reasons_changed_but_status_did_not": sum(1 for r in rows if not r["changed"] and (r["review_removed"] or r["review_added"] or r["failure_removed"] or r["failure_added"])),
        "transitions": {f"{a} -> {b}": n for (a, b), n in sorted(transitions.items())},
        "by_ticker": by_ticker,
        "runs": rows,
    }
    Path(args.out_json).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    md = [
        "# Verdict delta over every saved run of the six tickers",
        "",
        f"- Runs compared: **{doc['runs_compared']}**; formal_status changed on **{doc['runs_whose_formal_status_changed']}**; reasons changed with the status unchanged on **{doc['runs_whose_reasons_changed_but_status_did_not']}**.",
        f"- Transitions: {json.dumps(doc['transitions'], ensure_ascii=False)}",
        "",
        "## Runs whose formal_status changed",
        "",
        "| Ticker | Run | Analysis date | Before | After | Cause |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        if r["changed"]:
            md.append(f"| {r['ticker']} | {r['run_id'][:8]} | {r['analysis_date']} | {r['status_before']} | {r['status_after']} | {'; '.join(r['cause']) or '—'} |")
    md += ["", "## Runs whose reasons changed but whose status did not", "", "| Ticker | Run | Status | Review items removed | Review items added | Failures removed | Failures added |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        if not r["changed"] and (r["review_removed"] or r["review_added"] or r["failure_removed"] or r["failure_added"]):
            md.append(
                f"| {r['ticker']} | {r['run_id'][:8]} | {r['status_after']} | {r['review_removed'] or '—'} | {r['review_added'] or '—'} | {r['failure_removed'] or '—'} | {r['failure_added'] or '—'} |".replace("|", "\\|", 0)
            )
    Path(args.out_md).write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({k: doc[k] for k in ("runs_compared", "runs_whose_formal_status_changed", "runs_whose_reasons_changed_but_status_did_not", "transitions")}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
