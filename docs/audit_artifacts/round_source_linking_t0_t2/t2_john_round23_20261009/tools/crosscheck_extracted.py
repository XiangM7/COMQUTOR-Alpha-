#!/usr/bin/env python3
"""T2 John version (2026-10-09): cross-check an UNZIPPED copy of the package against sources outside it (read-only).

Independent of the in-package verifier: recomputes hashes of the unzipped files and compares them with
  * the build directory the ZIP was made from (every file byte-identical, same file set),
  * the current originals in the repository's outputs/runs/ (the five copied runs, and AMD),
  * the AMD members of the T1 run archive and the Round 22 AMD hash record in the repository,
  * the Round 23 directory in the repository (every unedited file byte-identical; the two edited reader files differ).

    python3 tools/crosscheck_extracted.py <unzipped package root> --build <build dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from snapshot_originals import REPO, SIX_RUNS, T1_ARCHIVE, hash_tar_member_dir  # noqa: E402

R23 = "round23_t2_completion_20261007"
EDITED = {"01_中文简明验收报告_T2.md", "README_T2.md"}
R22_AMD = REPO / "docs/audit_artifacts/round_source_linking_t0_t2/round22_t1_closeout_20261007/run_directory_hashes/d5b60b8a-66b8-44c1-9f55-ee345e58c48d.json"


def tree(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and p.name != ".DS_Store"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("extracted")
    ap.add_argument("--build", required=True)
    args = ap.parse_args(argv)
    x, build = Path(args.extracted), Path(args.build)
    out: dict = {}

    xt, bt = tree(x), tree(build)
    out["extracted_equals_build_dir"] = {"files_extracted": len(xt), "files_build": len(bt), "identical": xt == bt,
                                         "differing": sorted(k for k in set(xt) | set(bt) if xt.get(k) != bt.get(k))[:20]}

    runs = {}
    for ticker, run_id in SIX_RUNS.items():
        copy = tree(x / "历史输入/outputs/runs" / run_id)
        orig = tree(REPO / "outputs/runs" / run_id)
        row = {"located": bool(copy), "files": len(copy), "equals_current_original": copy == orig}
        if ticker == "AMD":
            arch = hash_tar_member_dir(T1_ARCHIVE, f"outputs/runs/{run_id}")["per_file_sha256"]
            r22 = json.loads(R22_AMD.read_text(encoding="utf-8"))["files"]
            row["equals_t1_archive_members"] = copy == arch
            row["equals_round22_record_in_repository"] = copy == r22
        runs[ticker] = row
    out["six_inputs_vs_outside_sources"] = runs

    xr, rr = tree(x / "我方对应交付" / R23), tree(REPO / "docs/audit_artifacts/round_source_linking_t0_t2" / R23)
    out["round23_vs_repository"] = {
        "same_file_set": set(xr) == set(rr),
        "unedited_files_identical": all(xr[k] == rr[k] for k in rr if k not in EDITED),
        "edited_files_differ_as_expected": all(xr.get(k) != rr[k] for k in EDITED),
        "files": len(rr),
    }
    ok = (out["extracted_equals_build_dir"]["identical"]
          and all(r["located"] and r["equals_current_original"] and r.get("equals_t1_archive_members", True) and r.get("equals_round22_record_in_repository", True)
                  for r in runs.values())
          and out["round23_vs_repository"]["same_file_set"] and out["round23_vs_repository"]["unedited_files_identical"]
          and out["round23_vs_repository"]["edited_files_differ_as_expected"])
    out["all_ok"] = ok
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
