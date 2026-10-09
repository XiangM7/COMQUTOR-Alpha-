#!/usr/bin/env python3
"""Render docs/specs/t2_acceptance_scenario_map.json (John's seven required scenarios -> the tests that prove them) as Markdown, from the JSON alone.

usage: python render_scenario_map.py            # writes scenario_map.md next to this script
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAP = HERE.parents[3] / "docs" / "specs" / "t2_acceptance_scenario_map.json"

KIND_LABEL = {
    "engine_level": "engine (synthetic)",
    "end_to_end_formal_status": "final status (synthetic)",
    "upstream_real_path": "upstream real code",
}


def cell(value) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def main() -> None:
    doc = json.loads(MAP.read_text(encoding="utf-8"))
    out = [
        "# T2 — John's seven required scenarios → the tests that prove them",
        "",
        f"Source: {doc['source']}",
        "",
        f"> {doc['fixtures_note']}",
        "",
        "Kinds: " + "; ".join(f"**{KIND_LABEL[k]}** = {v}" for k, v in doc["kinds"].items()),
        "",
        "The map is checked by `tests/test_t2_scenario_map_points_at_real_tests.py`: every test cited below exists.",
    ]
    for scenario in doc["scenarios"]:
        out += ["", f"## {scenario['id']}. {scenario['john_scenario']} → {scenario['john_expected']}", "", "| Kind | Test | What it proves |", "|---|---|---|"]
        out += [f"| {KIND_LABEL[t['kind']]} | `{t['node']}` | {cell(t['proves'])} |" for t in scenario["tests"]]
        if scenario.get("limits"):
            out += ["", f"*Limit:* {scenario['limits']}"]
    (HERE / "scenario_map.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("wrote", HERE / "scenario_map.md")


if __name__ == "__main__":
    main()
