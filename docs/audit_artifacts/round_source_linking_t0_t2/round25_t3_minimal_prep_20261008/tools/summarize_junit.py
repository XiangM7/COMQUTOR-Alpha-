#!/usr/bin/env python3
"""Summarizes one or more JUnit XML files (raw pytest results) into counts and a per-test outcome map, and optionally compares them with a baseline JUnit file
test id by test id. A test that passed in the baseline and does not pass now is listed as a regression; a test that fails in both is listed with both messages --
'it failed in the old baseline' is a fact to examine, not a reason to stop looking.

    python summarize_junit.py --junit a.xml [--junit b.xml ...] [--baseline-junit base.xml] --out-json summary.json --out-md summary.md
"""
import argparse
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


def load(paths):
    outcomes, messages = {}, {}
    for path in paths:
        for case in ET.parse(path).getroot().iter("testcase"):
            key = f"{case.get('classname')}::{case.get('name')}"
            kind, text = "passed", ""
            for tag in ("failure", "error", "skipped"):
                node = case.find(tag)
                if node is not None:
                    kind = {"failure": "failed", "error": "error", "skipped": "skipped"}[tag]
                    text = (node.get("message") or node.text or "").strip().splitlines()[0][:300] if (node.get("message") or node.text) else ""
                    break
            outcomes[key] = kind
            messages[key] = text
    return outcomes, messages


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--junit", action="append", required=True)
    ap.add_argument("--baseline-junit", action="append", default=[])
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--out-md", required=True)
    args = ap.parse_args(argv)
    for out in (args.out_json, args.out_md):
        if Path(out).exists():
            print("refusing: output exists", out, file=sys.stderr)
            return 2
    now, now_msg = load(args.junit)
    counts = Counter(now.values())
    doc = {"files": [Path(p).name for p in args.junit], "total": len(now), "counts": dict(counts), "not_passing": {k: {"outcome": v, "message": now_msg[k]} for k, v in sorted(now.items()) if v != "passed"}}
    if args.baseline_junit:
        base, base_msg = load(args.baseline_junit)
        shared = sorted(set(now) & set(base))
        doc["baseline"] = {
            "files": [Path(p).name for p in args.baseline_junit],
            "tests_in_common": len(shared),
            "passed_in_baseline_and_not_passing_now": [{"test": k, "now": now[k], "message": now_msg[k]} for k in shared if base[k] == "passed" and now[k] != "passed"],
            "failing_in_both": [{"test": k, "baseline_message": base_msg[k], "now_message": now_msg[k], "same_message": base_msg[k] == now_msg[k]} for k in shared if base[k] != "passed" and now[k] != "passed"],
            "failing_in_baseline_passing_now": [k for k in shared if base[k] != "passed" and now[k] == "passed"],
            "not_in_baseline": len(set(now) - set(base)),
        }
    Path(args.out_json).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    md = ["# Test results", "", f"Files: {', '.join(doc['files'])}", "", f"Total **{doc['total']}**: " + ", ".join(f"{v} {k}" for k, v in sorted(doc["counts"].items())), ""]
    if doc["not_passing"]:
        md += ["## Not passing", "", "| Test | Outcome | First line of the message |", "|---|---|---|"] + [f"| `{k}` | {v['outcome']} | {v['message'].replace('|', '/')} |" for k, v in doc["not_passing"].items()]
    if "baseline" in doc:
        b = doc["baseline"]
        md += ["", f"## Against the baseline ({', '.join(b['files'])})", "", f"- Tests in common: {b['tests_in_common']}; not in the baseline: {b['not_in_baseline']}", f"- **Passed in the baseline and not passing now: {len(b['passed_in_baseline_and_not_passing_now'])}**"]
        md += [f"  - `{r['test']}` → {r['now']}: {r['message']}" for r in b["passed_in_baseline_and_not_passing_now"]]
        md += [f"- Failing in both: {len(b['failing_in_both'])}"] + [f"  - `{r['test']}` (same message: {r['same_message']})" for r in b["failing_in_both"]]
        md += [f"- Failing in the baseline, passing now: {len(b['failing_in_baseline_passing_now'])}"]
    Path(args.out_md).write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({"total": doc["total"], "counts": doc["counts"]}), "| regressions vs baseline:", len(doc.get("baseline", {}).get("passed_in_baseline_and_not_passing_now", [])) if "baseline" in doc else "n/a")
    return 0


if __name__ == "__main__":
    sys.exit(main())
