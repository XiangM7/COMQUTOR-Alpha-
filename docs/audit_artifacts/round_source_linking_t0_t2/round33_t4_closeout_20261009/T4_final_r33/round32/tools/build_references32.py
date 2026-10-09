#!/usr/bin/env python3
"""T4 final delivery (round 32): path + sha256 of the earlier packages this delivery refers to (T1/T2/T3 and the T4 rounds 27-30),
WITHOUT copying or repacking them. Run inside the repository (build time only); the result is references/prior_packages.json.

    python3 tools/build_references.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent  # the round-32 directory when run from round32/tools, T4_final when packaged
REPO = next(p for p in PKG.parents if (p / "comqutor_alpha").is_dir())
B = "docs/audit_artifacts/round_source_linking_t0_t2"

REPO_FILES = {
    "T1": [f"{B}/round22_t1_closeout_20261007/01_中文简明验收报告_收尾版.md", f"{B}/round22_t1_closeout_20261007/release_manifest_v2.json",
           f"{B}/round22_t1_closeout_20261007/release_manifest_v2_verification.json", f"{B}/round21_t1_minimal_closure_20261007/01_中文简明验收报告.md"],
    "T2": [f"{B}/round24_t2_gap_closure_20261007/01_中文简明验收报告_T2.md", f"{B}/round24_t2_gap_closure_20261007/README_T2.md",
           f"{B}/round23_t2_completion_20261007/01_中文简明验收报告_T2.md"],
    "T3": [f"{B}/round26_t3_closeout_20261008/00_T3_main_report.md", f"{B}/round26_t3_closeout_20261008/delivery/T3_delivery_t3joint-20261008T170322Z-bd99811e.zip",
           f"{B}/round26_t3_closeout_20261008/delivery/verify_report.json"],
    "T4_round27_phase_a": [f"{B}/round27_t4_phase_a_20261008/README.md", f"{B}/round27_t4_phase_a_20261008/READINESS_STATUS.md",
                           f"{B}/round27_t4_phase_a_20261008/TEST_REPORT.md", f"{B}/round27_t4_phase_a_20261008/05_demo/DEMO_FLOW.md"],
    "T4_round28_launch_protection": [f"{B}/round28_t4_launch_protection_20261008/README.md", f"{B}/round28_t4_launch_protection_20261008/REPORT.md",
                                     f"{B}/round28_t4_launch_protection_20261008/TEST_REPORT.md"],
    "T4_round29_fresh_run1": [f"{B}/round29_t4_nvda_fresh_run_20261009/FRESH_RUN_REPORT.md"],
    "T4_round30_fresh_run2": [f"{B}/round30_t4_nvda_fresh_run2_20261009/FRESH_RUN2_REPORT.md"],
    "T4_round31_delivery": [f"{B}/round31_t4_delivery_20261009/T4_delivery_round31_20261009.zip",
                            f"{B}/round31_t4_delivery_20261009/T4_delivery/00_T4交付主报告.md",
                            f"{B}/round31_t4_delivery_20261009/unzip_verification/verify_package_result.json"],
}
EXTERNAL = {  # outside the repository: listed with path relative to the home directory, hash and how to obtain
    "T1": "Desktop/t1.zip",
    "T2": "Desktop/t2.zip",
    "T3": "Desktop/T3_delivery_t3joint-20261008T170322Z-bd99811e.zip",
    "John task sheet": "Downloads/COMQUTOR Alpha 下一轮开发任务单.docx",
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    out = {"generated_at": datetime.now(UTC).isoformat(), "note": "referenced by path and sha256 only; not copied into this package",
           "repository_files": {}, "external_files": {}}
    for group, paths in REPO_FILES.items():
        out["repository_files"][group] = [{"path": p, "exists": (REPO / p).is_file(), "bytes": (REPO / p).stat().st_size if (REPO / p).is_file() else None,
                                           "sha256": sha(REPO / p) if (REPO / p).is_file() else None} for p in paths]
    home = Path.home()
    for group, rel in EXTERNAL.items():
        p = home / rel
        out["external_files"][group] = {"path_under_home": f"~/{rel}", "exists": p.is_file(), "bytes": p.stat().st_size if p.is_file() else None,
                                        "sha256": sha(p) if p.is_file() else None,
                                        "how_to_obtain": "Xiang Mao 本机文件；需要时由负责人另行提供（不在本包内）"}
    t3_repo = next(x for x in out["repository_files"]["T3"] if x["path"].endswith(".zip"))
    out["t3_desktop_copy_equals_repo_copy"] = t3_repo["sha256"] == out["external_files"]["T3"]["sha256"]
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else PKG / "references" / "prior_packages.json"
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({g: [x["exists"] for x in v] for g, v in out["repository_files"].items()}, ensure_ascii=False),
          json.dumps({g: v["exists"] for g, v in out["external_files"].items()}, ensure_ascii=False), "t3 same:", out["t3_desktop_copy_equals_repo_copy"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
