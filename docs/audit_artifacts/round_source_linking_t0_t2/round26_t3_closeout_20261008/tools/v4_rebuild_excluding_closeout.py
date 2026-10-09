#!/usr/bin/env python3
"""T3 closeout: attribution of tests/test_t3_joint_sample_driver.py::test_the_v4_sample_and_its_materials_rebuild_byte_for_byte.

The round-25 builder records, per sample, how many data files under docs/audit_artifacts already mention the claim
(select_joint_sample.exposure, which excludes only round 25's own directory). This closeout adds files that mention the same
claims, so a rebuild today counts more. This tool rebuilds the v4 sample with exactly one change -- the closeout directory is also
left out of that document scan -- and compares every output file byte for byte with the frozen B1_samples_v4/ (zero network).

    python v4_rebuild_excluding_closeout.py --out-dir <new dir> --report <json>
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
ROUND25 = REPO / "docs/audit_artifacts/round_source_linking_t0_t2/round25_t3_minimal_prep_20261008"
CLOSEOUT_DIR_NAME = HERE.parent.name
FILES = ("joint_sample_v4_manifest.json", "review_form_v4.json", "review_worksheet_v4.csv", "material_coverage.json", "replacement_log.json",
         "collection_list.json")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args(argv)
    sys.path.insert(0, str(ROUND25 / "tools"))
    import select_joint_sample as sel  # noqa: E402  (the builder's own module, as it imports it)

    for path in (REPO / "docs" / "audit_artifacts").rglob("*"):
        posix = path.as_posix()
        if not path.is_file() or "round25_t3_minimal_prep" in posix or CLOSEOUT_DIR_NAME in posix or path.suffix not in {".md", ".json", ".csv", ".jsonl"}:
            continue
        try:
            sel._DOC_INDEX.append((path.relative_to(REPO).as_posix(), path.suffix, path.read_text(encoding="utf-8")))
        except (UnicodeDecodeError, OSError):
            continue
    spec = importlib.util.spec_from_file_location("build_samples_v4", ROUND25 / "tools" / "build_samples_v4.py")
    assert spec is not None and spec.loader is not None
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    out = Path(args.out_dir)
    code = builder.main(["--out-dir", str(out)])
    result = {name: (out / name).read_bytes() == (ROUND25 / "B1_samples_v4" / name).read_bytes() for name in FILES}
    report = {"builder_exit_code": code, "excluded_from_document_scan": ["round25_t3_minimal_prep (as the builder does)", CLOSEOUT_DIR_NAME],
              "byte_identical_to_frozen_B1_samples_v4": result, "all_identical": all(result.values())}
    Path(args.report).write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return 0 if report["all_identical"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
