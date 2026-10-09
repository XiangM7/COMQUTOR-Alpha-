#!/usr/bin/env python3
"""Round 22: prove a code snapshot is complete and self-consistent -- without touching the repository.

Rebuilds the snapshot's tracked files in a TEMPORARY directory (``git archive HEAD`` of just the touched paths, then
``git apply tracked_diff_vs_HEAD.patch``), then checks every entry of ``file_hashes.json``:
  * tracked_differs_from_HEAD  -> the rebuilt file's sha256 equals the recorded one  (the patch really contains the change)
  * untracked_source / rule_file -> the snapshot's own copy hashes to the recorded value
Optionally (``--against-working-tree``) also compares each recorded file with the CURRENT working-tree file.

Read-only on the repository (git archive / git apply run against a temp dir). Exit code 0 only when everything matches.

usage: verify_snapshot.py <snapshot_dir> [--against-working-tree]
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tarfile
import tempfile
from io import BytesIO
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(snapshot: Path, against_wt: bool) -> int:
    hashes = json.loads((snapshot / "file_hashes.json").read_text(encoding="utf-8"))
    head = json.loads((snapshot / "HEAD.json").read_text(encoding="utf-8"))["head_sha"]
    tracked = sorted(p for p, v in hashes.items() if v["class"] == "tracked_differs_from_HEAD")
    problems: list[str] = []

    with tempfile.TemporaryDirectory(prefix="snapshot_verify_") as tmp:
        tmp_dir = Path(tmp)
        if tracked:
            archive = subprocess.run(["git", "archive", head, "--", *tracked], cwd=REPO, capture_output=True)
            # files that are new relative to HEAD (tracked only via the index) simply are not in the archive
            if archive.returncode == 0 and archive.stdout:
                with tarfile.open(fileobj=BytesIO(archive.stdout)) as tar:
                    tar.extractall(tmp_dir, filter="data")  # our own git archive
        patch = snapshot / "tracked_diff_vs_HEAD.patch"
        if patch.stat().st_size:
            # run inside the rebuilt tree: macOS temp dirs sit behind a /var -> /private/var symlink, which `git apply --directory=<abs>` refuses
            applied = subprocess.run(["git", "-C", str(tmp_dir), "apply", str(patch.resolve())], capture_output=True, text=True)
            if applied.returncode != 0:
                problems.append(f"patch does not apply to HEAD {head[:10]}: {applied.stderr.strip()[:300]}")
        for rel in tracked:
            rebuilt = tmp_dir / rel
            if not rebuilt.is_file():
                problems.append(f"{rel}: not reproduced from HEAD + patch")
            elif sha256_of(rebuilt) != hashes[rel]["sha256"]:
                problems.append(f"{rel}: HEAD + patch hashes differently from the recorded content")

    for rel, meta in sorted(hashes.items()):
        if meta["class"] == "tracked_differs_from_HEAD":
            copy = None
        elif meta["class"] == "untracked_source":
            copy = snapshot / "untracked_source" / rel
        else:
            copy = snapshot / "rule_files" / rel
        if copy is not None:
            if not copy.is_file():
                problems.append(f"{rel}: snapshot copy missing")
            elif sha256_of(copy) != meta["sha256"]:
                problems.append(f"{rel}: snapshot copy hash differs from the recorded hash")
        if meta.get("is_rule_file") and meta["class"] != "rule_file":
            rule_copy = snapshot / "rule_files" / rel
            if not rule_copy.is_file() or sha256_of(rule_copy) != meta["sha256"]:
                problems.append(f"{rel}: rule-file copy missing or different")
        if against_wt:
            current = REPO / rel
            if not current.is_file() or sha256_of(current) != meta["sha256"]:
                problems.append(f"{rel}: working-tree file differs from the snapshot")

    result = {"snapshot": str(snapshot.relative_to(REPO)) if snapshot.is_relative_to(REPO) else str(snapshot), "head": head,
              "tracked_rebuilt_from_HEAD_plus_patch": len(tracked), "files_checked": len(hashes), "against_working_tree": against_wt,
              "problems": problems, "ok": not problems}
    print(json.dumps(result, indent=1))
    return 0 if not problems else 1


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(Path(args[0]).resolve(), "--against-working-tree" in sys.argv))
