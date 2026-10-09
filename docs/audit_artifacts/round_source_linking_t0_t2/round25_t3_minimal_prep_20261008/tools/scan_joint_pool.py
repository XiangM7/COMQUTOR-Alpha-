#!/usr/bin/env python3
"""Round 25 (T3 prep): which saved claims could enter the new 40-item joint sample, per John's scenario quota (16 A304 boundary /
8 A101-A103 / 4 each A001 A003 A102 A501), using ONLY the claim's own text and its linked source content -- never the Alpha
classifier's or the stance classifier's saved answers (alpha_matches.json / evidence_stance_audit.json are not opened).

A claim is in the CONTENT POOL only if its linked source carries real content (an excerpt or a data row): John's sample must carry
the original source fragment or data row, and a title/URL proves only that a source exists. Read-only; writes one JSON.

    python scan_joint_pool.py --out <json>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = next(p for p in Path(__file__).resolve().parents if (p / "comqutor_alpha").is_dir())
sys.path.insert(0, str(REPO))
# key_conclusion_group is a pure function of the record (agent, section, wording)
from comqutor_alpha.api.evidence_trace import key_conclusion_group  # noqa: E402

# Root research runs that carry a source registry with real content (the AMD c904d4cc lineage is read from its root; its derived
# executions share the same claims).
RUNS = (
    "034a0a60-430e-41f8-8321-03a11389707a",
    "1bad76a7-72ac-4c8b-8189-2e5c0f1a6105",
    "c904d4cc-dc09-495c-aec5-b056979948e1",
)
# Scenario rules on the claim text (+ the claim's own evidence text). They decide which quota cell a claim is a CANDIDATE for --
# never what its answer is. A claim can be a candidate for several cells.
SCENARIOS = {
    "A304_boundary": re.compile(
        r"\b(p/?e\b|pe ratio|price[- ]to[- ](?:earnings|sales|book)|p/s\b|ev/ebitda|ev/sales|multiples?\b|valuation|valued|"
        r"overvalued|undervalued|peg\b|premium|re-?rat(?:e|ing)|de-?rat(?:e|ing)|compression|expensive|stretched|"
        r"forward earnings|trailing earnings|earnings yield|priced (?:in|for))", re.I),
    # AI demand / AI infrastructure vocabulary; bare "capex", "server" or "cloud" without an AI term is not this scenario
    "A101_A103": re.compile(
        r"\b(ai\b|ai-|artificial intelligence|gpus?\b|accelerators?|instinct|mi3\d\d|mi4\d\d|mi5\d\d|data ?cent(?:er|re)s?|hyperscalers?)", re.I),
    "A001": re.compile(r"\b(rate cuts?|cut rates|fed\b|federal reserve|fomc|easing cycle|monetary easing|policy rate)", re.I),
    "A003": re.compile(r"\b(liquidity|money supply|m2\b|quantitative easing|\bqe\b|\bqt\b|balance[- ]sheet runoff|fund flows?|passive (?:flows?|buying)|index inclusion|rebalanc)", re.I),
    # inference as an AI workload, not "inference" meaning deduction
    "A102": re.compile(
        r"\b(inference (?:demand|workloads?|compute|spending|layer|chips?|market|revenue|deployments?|growth|traffic|capacity)|"
        r"(?:ai|enterprise|agent\w*|model) inference|inference and (?:agent|enterprise))", re.I),
    # macro recession vocabulary; a technical-indicator "contraction" is not this scenario
    "A501": re.compile(r"\b(recession|economic slowdown|economic (?:contraction|downturn)|unemployment|gdp\b|layoffs?|hard landing)", re.I),
}
# Text cues for the five A304 situations John names (mention / discuss risk / refute / conditional / data-supported compression).
# Used only to spread the A304 cell across situations -- the reviewer, not this cue, decides what a claim is.
A304_CUES = {
    "refute": re.compile(r"\b(not|isn't|aren't|overblown|justified|reasonable|undemanding|cheap|discount|misread|wrong)\b", re.I),
    "conditional": re.compile(r"\b(if|unless|could|would|might|should .{0,20}(?:miss|slow|disappoint))\b", re.I),
    "citation": re.compile(r"\b(according to|analysts?|consensus|said|says|reported|noted|estimates?|street)\b", re.I),
    "data": re.compile(r"\d"),
}


def content_of(source: dict) -> str | None:
    if source.get("excerpt"):
        return "excerpt"
    if source.get("data_snapshot"):
        return "data_row"
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    out = Path(args.out)
    if out.exists():
        print("refusing: output exists", out, file=sys.stderr)
        return 2
    rows, per_run = [], {}
    for run_id in RUNS:
        run_dir = REPO / "outputs" / "runs" / run_id
        records = json.loads((run_dir / "structured_agent_outputs.json").read_text(encoding="utf-8"))["records"]
        sources = {s["source_id"]: s for s in json.loads((run_dir / "source_registry.json").read_text(encoding="utf-8"))["sources"]}
        stats = Counter()
        for r in records:
            stats["records"] += 1
            src = sources.get(r.get("linked_source_id") or "")
            kind = content_of(src) if src else None
            if not kind:
                stats["no_content_source"] += 1
                continue
            stats[f"content_linked:{r.get('source_link_status')}:{src.get('source_type')}"] += 1
            text = f"{r.get('claim') or ''} {r.get('evidence') or ''}"
            cells = [name for name, rx in SCENARIOS.items() if rx.search(text)]
            cues = [name for name, rx in A304_CUES.items() if rx.search(text)] if "A304_boundary" in cells else []
            rows.append({
                "run_id": run_id, "claim_id": r["claim_id"], "agent": r.get("agent"), "claim_quality": r.get("claim_quality"),
                "source_link_status": r.get("source_link_status"), "source_type": src.get("source_type"), "content_kind": kind,
                "key_conclusion_group": key_conclusion_group(r), "scenario_cells": cells, "a304_cues": cues,
                "duplicate_group_id": r.get("duplicate_group_id"), "claim_text": r.get("claim"),
            })
        per_run[run_id] = dict(stats)
    cell_counts = {name: Counter() for name in SCENARIOS}
    for row in rows:
        for cell in row["scenario_cells"]:
            cell_counts[cell][row["source_link_status"]] += 1
            cell_counts[cell]["key_conclusion" if row["key_conclusion_group"] else "not_key_conclusion"] += 1
    document = {
        "what": "content-linked candidate claims per scenario cell (text rules only; no classifier output read)",
        "runs": per_run,
        "candidates_total": len(rows),
        "cell_counts": {k: dict(v) for k, v in cell_counts.items()},
        "candidates": rows,
    }
    out.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"candidates_total": len(rows), "cell_counts": document["cell_counts"], "runs": per_run}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
