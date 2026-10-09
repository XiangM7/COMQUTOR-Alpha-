#!/usr/bin/env python3
"""T4 Phase A: attribution check for tests/test_t3_joint_sample_driver.py::test_the_v4_sample_and_its_materials_rebuild_byte_for_byte.

The v4 builder counts "prior mentions" of each sampled claim id over every .json/.jsonl under docs/audit_artifacts (excluding only the
round-25 package), so audit files written by LATER rounds raise the count. This rebuilds v4 into a scratch directory with the round-26
and round-27 packages also excluded from that scan, and compares all six files byte for byte with the saved B1_samples_v4. Zero network.

    python check_v4_rebuild_excluding_later_rounds.py --work-dir <new dir> --out test_evidence/v4_rebuild_excluding_later_rounds.json
"""
import argparse, importlib.util, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
PKG = REPO / "docs/audit_artifacts/round_source_linking_t0_t2/round25_t3_minimal_prep_20261008"
LATER = ("round26_t3_closeout_20261008", "round27_t4_phase_a_20261008")
NAMES = ("joint_sample_v4_manifest.json", "review_form_v4.json", "review_worksheet_v4.csv", "material_coverage.json", "replacement_log.json", "collection_list.json")



def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--work-dir", required=True); ap.add_argument("--out", required=True); a = ap.parse_args(argv)
    sys.path.insert(0, str(PKG / "tools"))
    import select_joint_sample as sel
    sel._DOC_INDEX.clear() if isinstance(getattr(sel, "_DOC_INDEX", None), list) else None
    _orig_read_text = Path.read_text
    def _guarded(self, *args, **kwargs):  # hide later-round files from the mention index only
        if any(l in self.as_posix() for l in LATER) and self.suffix in {".md", ".json", ".csv", ".jsonl"}:
            raise OSError("excluded later-round file")
        return _orig_read_text(self, *args, **kwargs)
    Path.read_text = _guarded
    spec = importlib.util.spec_from_file_location("build_samples_v4", PKG / "tools" / "build_samples_v4.py")
    builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
    code = builder.main(["--out-dir", a.work_dir])
    Path.read_text = _orig_read_text
    result = {"builder_exit": code, "excluded_from_mention_scan": list(LATER),
              "byte_identical": {n: (Path(a.work_dir) / n).read_bytes() == (PKG / "B1_samples_v4" / n).read_bytes() for n in NAMES}}
    result["all_identical"] = all(result["byte_identical"].values())
    Path(a.out).write_text(json.dumps(result, indent=1) + "\n"); print(json.dumps(result, indent=1))
    return 0 if result["all_identical"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
