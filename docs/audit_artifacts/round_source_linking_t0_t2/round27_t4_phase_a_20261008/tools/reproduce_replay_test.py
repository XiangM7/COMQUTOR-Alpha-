#!/usr/bin/env python3
"""T4 Phase A: reproduction for tests/test_artifact_export_and_api.py::test_replay_conflict_does_not_get_run_id_mismatch (zero network).

Runs exactly the test fixture's Architecture Replay (NVDA source run e434f80b, persist=True, a fresh temporary output root, no database
URL -> its own SQLite there), then evaluates BOTH versions of the test's assertions on the same result:
  HEAD (7a9aefa)   -- no RUN_ID_MISMATCH in any candidate evaluation; admitted_count > 0
  current (09-29)  -- no RUN_ID_MISMATCH; every claim's match_status is "unavailable"; candidate pairs still evaluated; admitted_count == 0
The source run directory is hashed before and after (read only).

    python run_with_network_trap.py reproduce_replay_test.py --work-dir <new dir> --out 02_replay_eslint/replay_test_reproduction.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
SOURCE_RUN = "e434f80b-e4d0-4b09-9471-d84532659de5"


def _tree(directory: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(directory.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(directory)).encode() + b"\0" + hashlib.sha256(p.read_bytes()).hexdigest().encode())
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    work = Path(args.work_dir)
    if work.exists():
        print("refusing: work dir exists", file=sys.stderr)
        return 2
    for name in ("COMQUTOR_DATABASE_URL", "COMQUTOR_ENV", "COMQUTOR_DATA_SANITY_ENABLED", "COMQUTOR_WEEK2_LLM_ENABLED"):
        os.environ.pop(name, None)
    os.chdir(REPO)
    from comqutor_alpha.replay.pipeline import run_structure_replay

    source = REPO / "outputs" / "runs" / SOURCE_RUN
    before = _tree(source)
    result = run_structure_replay(SOURCE_RUN, source_output_root="outputs/runs", replay_output_root=str(work), persist=True, comparison=False)
    after = _tree(source)
    conflicts = json.loads((Path(result.output_dir) / "conflict_results.json").read_text(encoding="utf-8"))
    matches = json.loads((Path(result.output_dir) / "alpha_matches.json").read_text(encoding="utf-8")).get("matches") or []
    evaluations = conflicts["arbitration"]["candidate_evaluations"]
    mismatch = sum("RUN_ID_MISMATCH" in (e.get("reason_codes") or []) for e in evaluations)
    admitted = conflicts["arbitration"]["admitted_count"]
    head = {"no_run_id_mismatch": mismatch == 0, "admitted_count_gt_0": admitted > 0}
    current = {"no_run_id_mismatch": mismatch == 0, "matches_present": bool(matches),
               "all_matches_unavailable": all(m.get("match_status") == "unavailable" for m in matches),
               "candidate_pairs_evaluated": bool(evaluations), "admitted_count_eq_0": admitted == 0}
    doc = {"source_run_id": SOURCE_RUN, "replay_output_dir": str(Path(result.output_dir).relative_to(work.parent)) if work.parent in Path(result.output_dir).parents else str(result.output_dir),
           "source_run_unchanged": before == after, "candidate_evaluations": len(evaluations), "run_id_mismatch_count": mismatch,
           "admitted_count": admitted, "claims": len(matches),
           "match_status_counts": {s: sum(m.get("match_status") == s for m in matches) for s in sorted({m.get("match_status") for m in matches})},
           "reason_codes_seen": sorted({c for e in evaluations for c in (e.get("reason_codes") or [])}),
           "head_version_assertions": head, "head_version_passes": all(head.values()),
           "current_version_assertions": current, "current_version_passes": all(current.values())}
    Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(doc, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
