#!/usr/bin/env python3
"""Round 23 (T2 completion): turn a pytest JUnit file of the FULL suite into the T2 test evidence - totals, the T2 test files one by one, and every failing
test checked against the recorded pre-existing baseline (round 15's unfiltered full run: 42 failing nodeids, each explained in round14's attribution manifest).

A failure that is not in the baseline is NEW. Failures are never hidden, re-pinned or skipped by this script; it only reads the JUnit file.

usage: summarize_test_evidence.py <full_run.junit.xml> [--out summary.json]
exit code 0 when no failing test is outside the baseline, 1 otherwise.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
BASELINE = REPO / "docs/audit_artifacts/round_source_linking_t0_t2/round15_recovery_prep_20261006/regression_evidence/full_run.junit.xml"

T2_TEST_FILES = [
    "test_acceptance_engine",
    "test_t2_acceptance_engine_qualified_evidence_scenarios",
    "test_t2_architecture_replay_never_shown_as_pass_or_no_conflict",
    "test_formal_acceptance_artifact_production_wiring",
    "test_no_gold_label_import_in_research_path",
    "test_t2_rule_config_errors",
    "test_label_v2_covers_john_frozen_baseline",
    "test_formal_acceptance_report",
    "test_frozen_input_conflict_recompute",
    "test_open_review_ledger",
    "test_t2_scenario_map_points_at_real_tests",
    "test_msft_a102_a304_taxonomy_adjudication",
    "test_a4_regression_runner",
    "test_j3_semantic_benchmark_j2_v0_2",
    "test_week4_golden_closure",
    "test_v0_1_3_offline_replay_proof",
]


def file_of(classname: str) -> str:
    for part in classname.split("."):
        if part.startswith("test_") or part == "conftest":
            return part
    return classname


def nodeid(case) -> str:
    parts = case.get("classname", "").split(".")
    for i, part in enumerate(parts):
        if part.startswith("test_") or part == "conftest":
            klass = parts[i + 1:]
            return "/".join(parts[: i + 1]) + ".py::" + ("::".join(klass) + "::" if klass else "") + case.get("name", "")
    return case.get("name", "")


def read(path: Path) -> list[tuple[str, str, str]]:
    rows = []
    for case in ET.parse(path).getroot().iter("testcase"):
        kind = next((c.tag for c in case if c.tag in ("failure", "error", "skipped")), "passed")
        rows.append((nodeid(case), file_of(case.get("classname", "")), kind))
    return rows


def main(junit: Path, out: Path | None) -> int:
    rows = read(junit)
    baseline_failing = {n for n, _f, k in read(BASELINE) if k in ("failure", "error")}
    failing = sorted(n for n, _f, k in rows if k in ("failure", "error"))
    new = [n for n in failing if n not in baseline_failing]
    per_file: dict[str, dict[str, int]] = defaultdict(lambda: {"passed": 0, "failure": 0, "error": 0, "skipped": 0})
    for _n, f, kind in rows:
        per_file[f][kind] += 1
    summary = {
        "junit": str(junit.name),
        "totals": {k: sum(1 for _n, _f, kind in rows if kind == k) for k in ("passed", "failure", "error", "skipped")},
        "tests": len(rows),
        "baseline": {"junit": str(BASELINE.relative_to(REPO)), "failing_nodeids": len(baseline_failing)},
        "failing_now": len(failing),
        "failing_now_in_baseline": len(failing) - len(new),
        "NEW_failures_not_in_baseline": new,
        "baseline_failures_that_now_pass": sorted(baseline_failing - set(failing)),
        "t2_test_files": {name: dict(per_file.get(name, {"passed": 0, "failure": 0, "error": 0, "skipped": 0})) for name in T2_TEST_FILES},
        "t2_test_files_total": {
            k: sum(per_file.get(name, {}).get(k, 0) for name in T2_TEST_FILES) for k in ("passed", "failure", "error", "skipped")
        },
        "t2_test_files_failing": [n for n in failing if file_of(n.split("::")[0].replace("/", ".").removesuffix(".py")) in T2_TEST_FILES],
    }
    if out:
        out.write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("totals", "failing_now", "failing_now_in_baseline", "NEW_failures_not_in_baseline", "baseline_failures_that_now_pass", "t2_test_files_total", "t2_test_files_failing")}, indent=1))
    return 0 if not new else 1


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--out"]
    if not args:
        print(__doc__)
        sys.exit(2)
    out_path = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else None
    sys.exit(main(Path(args[0]), out_path if out_path else None))
