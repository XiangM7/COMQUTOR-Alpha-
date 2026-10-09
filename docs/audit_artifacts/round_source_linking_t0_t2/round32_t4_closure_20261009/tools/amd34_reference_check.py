#!/usr/bin/env python3
"""T4 round 32: AMD -- the existing 34-item traceability regression is REFERENCED, not re-reviewed: path + sha256 of the fixed
list, the full ledger, the coverage mapping and the Round 21 integrity result, and a check that the list files still carry the
sha256 the Round 21 integrity check recorded. Read-only, standard library only.

    python amd34_reference_check.py --out 06_frozen_checks/amd34_reference.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
B = "docs/audit_artifacts/round_source_linking_t0_t2"
FILES = {
    "fixed_34_list_json": f"{B}/round19_consumption_and_acceptance_20261007/amd_34_fixed_acceptance_list.json",
    "fixed_34_list_csv": f"{B}/round19_consumption_and_acceptance_20261007/amd_34_fixed_acceptance_list.csv",
    "full_34_item_ledger": f"{B}/amd_34_item_ledger.json",
    "coverage_mapping_34": f"{B}/round22_t1_closeout_20261007/coverage_mapping_34.json",
    "round21_integrity_result": f"{B}/round21_t1_minimal_closure_20261007/amd34_list_integrity_result.json",
    "round21_integrity_script": f"{B}/round21_t1_minimal_closure_20261007/verify_amd34_list_intact.py",
    "round22_t1_report": f"{B}/round22_t1_closeout_20261007/01_中文简明验收报告_收尾版.md",
}


def sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    files = {k: {"path": v, "exists": (REPO / v).is_file(), "sha256": sha(REPO / v)} for k, v in FILES.items()}
    integrity = json.loads((REPO / FILES["round21_integrity_result"]).read_text(encoding="utf-8"))
    h = integrity["checks"]["H_saved_files_unchanged"]["expected"]
    coverage = json.loads((REPO / FILES["coverage_mapping_34"]).read_text(encoding="utf-8"))
    doc = {
        "scope": "reference only: the 34 items are not re-reviewed and no historical material is backfilled (T4 round 32 task book)",
        "files": files,
        "list_hashes_equal_round21_record": {"json": files["fixed_34_list_json"]["sha256"] == h["json"], "csv": files["fixed_34_list_csv"]["sha256"] == h["csv"]},
        "round21_integrity_all_checks_pass": integrity.get("all_checks_pass"),
        "round21_verified_at": integrity.get("verified_at_utc"),
        "historical_run": integrity.get("historical_run"),
        "coverage_mapping_summary": {k: coverage.get(k) for k in ("what_this_is", "historical_run", "new_flow_run", "total_old_items")},
        "status_of_the_34_items": "unchanged: still 'not verified' (Round 22 report section 3) -- coverage of problem types by the new flow is not verification of the old items",
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"all_exist": all(f["exists"] for f in files.values()), **doc["list_hashes_equal_round21_record"],
                      "round21_all_checks_pass": doc["round21_integrity_all_checks_pass"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
