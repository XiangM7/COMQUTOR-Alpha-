#!/usr/bin/env python3
"""Round 22: the exact difference between two code snapshots (S0 -> S1) as one unified patch, built from REBUILT trees -- never from memory.

Each snapshot is rebuilt in a temporary directory exactly as ``verify_snapshot.py`` does (``git archive HEAD`` of the touched paths,
``git apply`` of the snapshot's tracked patch, the untracked-source copies on top); the two trees are then compared with ``diff -ruN``
restricted to the union of paths either snapshot lists. Read-only on the repository.

usage: diff_snapshots.py <S0 dir> <S1 dir> <out.patch>
"""
from __future__ import annotations

import json
import subprocess
import sys
import tarfile
import tempfile
from io import BytesIO
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]


def rebuild(snapshot: Path, target: Path, paths: set[str]) -> None:
    head = json.loads((snapshot / "HEAD.json").read_text(encoding="utf-8"))["head_sha"]
    hashes = json.loads((snapshot / "file_hashes.json").read_text(encoding="utf-8"))
    tracked_in_head = sorted(paths)
    archive = subprocess.run(["git", "archive", head, "--", *tracked_in_head], cwd=REPO, capture_output=True)
    if archive.returncode == 0 and archive.stdout:  # paths absent from HEAD make git archive fail: retry one by one below
        with tarfile.open(fileobj=BytesIO(archive.stdout)) as tar:
            tar.extractall(target, filter="data")
    else:
        for rel in tracked_in_head:
            one = subprocess.run(["git", "archive", head, "--", rel], cwd=REPO, capture_output=True)
            if one.returncode == 0 and one.stdout:
                with tarfile.open(fileobj=BytesIO(one.stdout)) as tar:
                    tar.extractall(target, filter="data")
    patch = snapshot / "tracked_diff_vs_HEAD.patch"
    if patch.stat().st_size:
        # run inside the rebuilt tree (macOS temp dirs sit behind a /var -> /private/var symlink, which `git apply --directory=<abs>` refuses)
        done = subprocess.run(["git", "-C", str(target), "apply", str(patch.resolve())], capture_output=True, text=True)
        if done.returncode != 0:
            raise SystemExit(f"patch of {snapshot} does not apply: {done.stderr[:300]}")
    for rel, meta in hashes.items():
        if meta["class"] == "untracked_source":
            dst = target / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes((snapshot / "untracked_source" / rel).read_bytes())


def main(s0: Path, s1: Path, out: Path) -> int:
    h0 = json.loads((s0 / "file_hashes.json").read_text(encoding="utf-8"))
    h1 = json.loads((s1 / "file_hashes.json").read_text(encoding="utf-8"))
    paths = {p for p in set(h0) | set(h1) if not (h0.get(p) or h1.get(p)).get("is_rule_file") or (h0.get(p) or h1.get(p))["class"] != "rule_file"}
    with tempfile.TemporaryDirectory(prefix="snapshot_diff_") as tmp:
        a, b = Path(tmp) / "S0", Path(tmp) / "S1"
        a.mkdir(), b.mkdir()
        rebuild(s0, a, paths)
        rebuild(s1, b, paths)
        result = subprocess.run(["diff", "-ruN", "S0", "S1"], cwd=tmp, capture_output=True, text=True)
        if result.returncode not in (0, 1):
            raise SystemExit(f"diff failed: {result.stderr[:300]}")
        changed = sorted({line.split()[2][3:] for line in result.stdout.splitlines() if line.startswith("diff -ruN")})  # "diff -ruN S0/<path> S1/<path>"
    out.write_text(result.stdout, encoding="utf-8")
    print(json.dumps({"out": str(out.relative_to(REPO)), "bytes": out.stat().st_size, "files_changed_between_snapshots": len(changed), "files": changed}, indent=1))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve()))
