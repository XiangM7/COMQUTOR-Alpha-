#!/usr/bin/env python3
"""Renders docs/specs/t2_acceptance_scenario_map.json (John's seven required scenarios -> the tests that prove them) as Markdown, from the JSON alone, and shows
for every cited test the outcome it had in the JUnit file(s) given -- so the map states what actually ran and passed, not only that a test of that name exists.

    python render_scenario_map.py --junit a.xml [--junit b.xml ...] --out scenario_map.md
"""
import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = next(p for p in Path(__file__).resolve().parents if (p / "comqutor_alpha").is_dir())
MAP = REPO / "docs" / "specs" / "t2_acceptance_scenario_map.json"
KIND_LABEL = {"engine_level": "rule function", "end_to_end_formal_status": "final status", "upstream_real_path": "upstream real code"}


def cell(value):
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def outcomes(paths):
    result = {}
    for path in paths:
        for case in ET.parse(path).getroot().iter("testcase"):
            name = case.get("name").split("[")[0]
            kind = "passed"
            for tag, label in (("failure", "FAILED"), ("error", "ERROR"), ("skipped", "skipped")):
                if case.find(tag) is not None:
                    kind = label
                    break
            result.setdefault((case.get("classname"), name), []).append(kind)
    return result


def lookup(found, node):
    path, *names = node.split("::")
    classname = ".".join([path[:-3].replace("/", "."), *names[:-1]])
    seen = found.get((classname, names[-1]))
    if not seen:
        return "not run in the given results"
    return "passed" if all(s == "passed" for s in seen) else "/".join(sorted(set(seen)))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--junit", action="append", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if Path(args.out).exists():
        print("refusing: output exists", args.out, file=sys.stderr)
        return 2
    doc = json.loads(MAP.read_text(encoding="utf-8"))
    found = outcomes(args.junit)
    out = [
        "# T2 — John's seven required scenarios → the tests that prove them",
        "",
        f"Source: {doc['source']}",
        "",
        f"> {doc['fixtures_note']}",
        "",
        "Fixture kinds: " + "; ".join(f"**{k}** = {v}" for k, v in doc["fixture_kinds"].items()),
        "",
        "Coverage statuses: " + "; ".join(f"**{k}** = {v}" for k, v in doc["coverage_statuses"].items()),
        "",
        "The map is checked by `tests/test_t2_scenario_map_points_at_real_tests.py` (every cited test exists; a scenario is only `covered` when something beyond hand-made records proves it). The *Outcome* column below is read from the JUnit files of this round's runs.",
    ]
    totals = {"cited": 0, "passed": 0}
    for scenario in doc["scenarios"]:
        out += ["", f"## {scenario['id']}. {scenario['john_scenario']} → {scenario['john_expected']}", "", f"**Coverage: {scenario['coverage_status']}**", "", "| Kind | Fixture | Test | Outcome | What it proves |", "|---|---|---|---|---|"]
        for t in scenario["tests"]:
            outcome = lookup(found, t["node"])
            totals["cited"] += 1
            totals["passed"] += outcome == "passed"
            out.append(f"| {KIND_LABEL[t['kind']]} | {t['fixture']} | `{t['node']}` | {outcome} | {cell(t['proves'])} |")
        if scenario.get("limits"):
            out += ["", f"*Limit:* {scenario['limits']}"]
    out += ["", f"Cited tests: **{totals['cited']}**; passed in this round's runs: **{totals['passed']}**.", ""]
    Path(args.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"cited {totals['cited']}, passed {totals['passed']}")
    return 0 if totals["cited"] == totals["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
