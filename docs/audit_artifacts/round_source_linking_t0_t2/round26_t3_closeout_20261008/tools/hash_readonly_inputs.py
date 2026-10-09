#!/usr/bin/env python3
"""T3 closeout: hash every read-only input of the closeout (zero network), or compare against an earlier hash file.

Scope: the original execution directory and its collected materials, the whole Round 25 package (frozen sample, form, plan, execution
results, the human review files and the official scoring), and the 128 files of the original runs and frozen inputs that Round 25's own
hash proof listed.

    python hash_readonly_inputs.py --out hash_proof/readonly_inputs_before.json
    python hash_readonly_inputs.py --out hash_proof/readonly_inputs_after.json --compare hash_proof/readonly_inputs_before.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
EXECUTION_ID = "t3joint-20261008T170322Z-bd99811e"
ROUND25 = "docs/audit_artifacts/round_source_linking_t0_t2/round25_t3_minimal_prep_20261008"
ROOTS = [f"outputs/t3_joint_evaluations/{EXECUTION_ID}", f"outputs/t3_joint_evaluations/{EXECUTION_ID}-materials", ROUND25]
ROUND25_PROOF = f"{ROUND25}/C_execution_results/hash_proof_original_runs_and_materials.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect() -> dict[str, str]:
    files: set[str] = set(json.loads((REPO / ROUND25_PROOF).read_text(encoding="utf-8"))["before"])
    for root in ROOTS:
        for p in (REPO / root).rglob("*"):
            if p.is_file() and "__pycache__" not in p.parts:
                files.add(str(p.relative_to(REPO)))
    return {f: _sha(REPO / f) for f in sorted(files) if (REPO / f).is_file()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--compare")
    args = ap.parse_args(argv)
    out = Path(args.out)
    if out.exists():
        print("refusing: output exists", out, file=sys.stderr)
        return 2
    hashes = collect()
    doc = {"taken_at": datetime.now(timezone.utc).isoformat(), "scope": ROOTS + [f"the 'before' file list of {ROUND25_PROOF}"],
           "file_count": len(hashes), "files": hashes}
    if args.compare:
        before = json.loads(Path(args.compare).read_text(encoding="utf-8"))["files"]
        doc["compared_with"] = args.compare
        doc["changed"] = sorted(f for f in before if f in hashes and before[f] != hashes[f])
        doc["missing_now"] = sorted(f for f in before if f not in hashes)
        doc["new_files"] = sorted(f for f in hashes if f not in before)
        doc["unchanged"] = not doc["changed"] and not doc["missing_now"]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in doc.items() if k != "files"}, ensure_ascii=False))
    return 0 if doc.get("unchanged", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
