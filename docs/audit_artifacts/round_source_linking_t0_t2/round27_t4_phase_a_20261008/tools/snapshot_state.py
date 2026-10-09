#!/usr/bin/env python3
"""T4 Phase A: code identity and read-only input hashes (zero network).

code identity: git HEAD, sha256 of the complete tracked diff, and every untracked source file under the runtime/frontend/script roots
(path + sha256). read-only hashes: every file of the runs and execution/package directories this round must never modify.

    python snapshot_state.py --out hash_proof/state_before.json
    python snapshot_state.py --out hash_proof/state_after.json --compare hash_proof/state_before.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
SOURCE_ROOTS = ("comqutor_alpha", "tradingagents", "scripts", "frontend/src", "frontend/e2e")
READ_ONLY_DIRS = (
    "outputs/runs/034a0a60-430e-41f8-8321-03a11389707a",
    "outputs/runs/1bad76a7-72ac-4c8b-8189-2e5c0f1a6105",
    "outputs/runs/c904d4cc-dc09-495c-aec5-b056979948e1",
    "outputs/runs/recovery-20261007T053635Z-26d6cd1a",
    "outputs/runs/requal-20261007T174744Z-664040d6",
    "outputs/runs/dependency-20261007T213234Z-3be0399d",
    "outputs/runs/dependency-20261007T220450Z-33128621",
    "outputs/runs/direction-20261007T065826Z-d311b8e2",
    "outputs/t3_joint_evaluations/t3joint-20261008T170322Z-bd99811e",
    "outputs/t3_joint_evaluations/t3joint-20261008T170322Z-bd99811e-materials",
    "docs/audit_artifacts/round_source_linking_t0_t2/round25_t3_minimal_prep_20261008",
    "docs/audit_artifacts/round_source_linking_t0_t2/round26_t3_closeout_20261008",
)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=False).stdout


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def code_identity() -> dict:
    untracked = sorted(p for p in _git("ls-files", "--others", "--exclude-standard", "--", *SOURCE_ROOTS).splitlines()
                       if p and "__pycache__" not in p and "node_modules" not in p)
    tracked_changed = sorted(p for p in _git("diff", "HEAD", "--name-only").splitlines() if p)
    return {
        "git_head": _git("rev-parse", "HEAD").strip(),
        "tracked_diff_sha256": _sha_bytes(_git("diff", "HEAD", "--binary").encode("utf-8")),
        "tracked_changed_files": len(tracked_changed),
        "untracked_source_files": {p: _sha_bytes((REPO / p).read_bytes()) for p in untracked if (REPO / p).is_file()},
    }


def read_only_hashes() -> dict[str, str]:
    out = {}
    for directory in READ_ONLY_DIRS:
        for path in sorted((REPO / directory).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                out[str(path.relative_to(REPO))] = _sha_bytes(path.read_bytes())
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--compare")
    args = ap.parse_args(argv)
    out = Path(args.out)
    if out.exists():
        print("refusing: output exists", out, file=sys.stderr)
        return 2
    doc = {"taken_at": datetime.now(timezone.utc).isoformat(), "code_identity": code_identity(), "read_only_files": read_only_hashes()}
    summary = {"read_only_file_count": len(doc["read_only_files"]), "git_head": doc["code_identity"]["git_head"],
               "tracked_diff_sha256": doc["code_identity"]["tracked_diff_sha256"]}
    if args.compare:
        before = json.loads(Path(args.compare).read_text(encoding="utf-8"))
        b, a = before["read_only_files"], doc["read_only_files"]
        doc["read_only_comparison"] = {"changed": sorted(f for f in b if f in a and a[f] != b[f]), "missing": sorted(f for f in b if f not in a),
                                       "new": sorted(f for f in a if f not in b)}
        doc["read_only_comparison"]["unchanged"] = not any(doc["read_only_comparison"].values())
        bu, au = before["code_identity"]["untracked_source_files"], doc["code_identity"]["untracked_source_files"]
        doc["code_identity_changes"] = {
            "tracked_diff_changed": before["code_identity"]["tracked_diff_sha256"] != doc["code_identity"]["tracked_diff_sha256"],
            "untracked_added": sorted(set(au) - set(bu)), "untracked_removed": sorted(set(bu) - set(au)),
            "untracked_modified": sorted(p for p in au if p in bu and au[p] != bu[p])}
        summary.update({"read_only_unchanged": doc["read_only_comparison"]["unchanged"], **doc["code_identity_changes"]})
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
