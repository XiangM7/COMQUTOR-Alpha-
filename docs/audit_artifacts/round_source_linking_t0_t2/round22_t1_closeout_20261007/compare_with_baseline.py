#!/usr/bin/env python3
"""Round 22: compare the failing tests of a pytest JUnit file with the recorded pre-existing baseline (round 15's unfiltered full run:
42 failing nodeids, every one explained in round14/regression_attribution_manifest.md). A failure that is NOT in the baseline is new.

usage: compare_with_baseline.py <junit.xml> [--json <out.json>]
exit code: 0 when no failing test is outside the baseline, 1 otherwise.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
BASELINE = REPO / "docs/audit_artifacts/round_source_linking_t0_t2/round15_recovery_prep_20261006/regression_evidence/full_run.junit.xml"


def failing(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for case in ET.parse(path).getroot().iter("testcase"):
        kind = next((c.tag for c in case if c.tag in ("failure", "error")), None)
        if not kind:
            continue
        parts = case.get("classname", "").split(".")
        file, klass = None, []
        for i, part in enumerate(parts):
            if part.startswith("test_") or part == "conftest":
                file, klass = "/".join(parts[: i + 1]) + ".py", parts[i + 1:]
                break
        out[f"{file}::" + ("::".join(klass) + "::" if klass else "") + case.get("name", "")] = kind
    return out


def main(junit: Path, out_json: Path | None) -> int:
    baseline, current = failing(BASELINE), failing(junit)
    new = sorted(n for n in current if n not in baseline)
    result = {"junit": str(junit), "failing_now": len(current), "in_baseline": len(current) - len(new), "baseline_size": len(baseline), "new_failures": new}
    if out_json:
        out_json.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))
    return 0 if not new else 1


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--json"]
    if not args:
        print(__doc__)
        sys.exit(2)
    out = Path(sys.argv[sys.argv.index("--json") + 1]) if "--json" in sys.argv else None
    sys.exit(main(Path(args[0]), out))
