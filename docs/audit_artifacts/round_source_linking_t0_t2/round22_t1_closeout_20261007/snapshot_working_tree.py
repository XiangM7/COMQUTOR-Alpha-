#!/usr/bin/env python3
"""Round 22 (T0 delivery identity): snapshot the REAL code state of the working tree -- never only hashes.

Nothing is committed, pushed, stashed or otherwise written to git: this script only READS git (``git diff``,
``git ls-files``, ``git rev-parse``) and WRITES files under the output directory.

For one snapshot ``<out>`` it writes
    HEAD.json                      branch, the real HEAD sha + subject, UTC time, counts
    git_status_porcelain.txt       ``git status --porcelain`` as it was
    tracked_diff_vs_HEAD.patch     ``git diff HEAD --binary`` -- the complete uncommitted difference of every tracked file
    untracked_source/<path>        a FULL COPY of every untracked source file (comqutor_alpha/, tradingagents/, tests/,
                                   frontend/, scripts/, ...): the content that exists nowhere in git
    rule_files/<path>              a FULL COPY of the rule files the manifest binds (taxonomy, frozen gold baseline, ...)
    deleted_tracked_files.txt      tracked files deleted in the working tree (normally empty)
    file_hashes.json               sha256 + size of: every tracked file that differs from HEAD (its CURRENT content),
                                   every untracked source copy and every rule file
so a reader can rebuild the exact tree: ``git archive HEAD`` + ``git apply tracked_diff_vs_HEAD.patch`` + the copies, and
verify each file against ``file_hashes.json`` (see ``verify_snapshot.py``).

Untracked evidence directories (``docs/audit_artifacts``, ``outputs``) are NOT source code and are not copied here; they are
bound by hash and relative path in the release manifest instead.

usage: snapshot_working_tree.py <out_dir>
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
EXCLUDED_PARTS = {"__pycache__", "node_modules", ".venv", ".vite", "dist", ".DS_Store", ".pytest_cache"}
EXCLUDED_SUFFIXES = (".pyc", ".pyo", ".log")
# untracked files under these roots are SOURCE (copied in full); everything else untracked is evidence/outputs (hash-bound elsewhere)
SOURCE_ROOTS = ("comqutor_alpha/", "tradingagents/", "tests/", "frontend/", "scripts/", ".github/")
SOURCE_ROOT_FILES = ("pyproject.toml", "requirements.txt", "package.json", "README.md", ".env.example", "Makefile")
# the rule files a release manifest binds (copied in full, wherever they live)
RULE_FILES = (
    "comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml",
    "comqutor_alpha/config/j2_provisional_regression_labels_v0.2.yaml",
    "docs/audit_artifacts/v0_2_john_frozen_gold_baseline.yaml",
)


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=REPO, check=True, capture_output=True).stdout


def names(*args: str) -> list[str]:
    return [p for p in git(*args, "-z").decode("utf-8").split("\0") if p]


def excluded(rel: str) -> bool:
    parts = set(Path(rel).parts)
    return bool(parts & EXCLUDED_PARTS) or rel.endswith(EXCLUDED_SUFFIXES)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(out_dir: Path) -> int:
    if out_dir.exists() and any(out_dir.iterdir()):
        print(f"refusing to overwrite a non-empty snapshot directory: {out_dir}", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)

    head = git("rev-parse", "HEAD").decode().strip()
    subject = git("log", "-1", "--format=%s").decode().strip()
    branch = git("rev-parse", "--abbrev-ref", "HEAD").decode().strip()
    porcelain = git("status", "--porcelain")
    (out_dir / "git_status_porcelain.txt").write_bytes(porcelain)
    (out_dir / "tracked_diff_vs_HEAD.patch").write_bytes(git("diff", "HEAD", "--binary", "--no-color"))

    tracked_changed = [p for p in names("diff", "--name-only", "HEAD") if not excluded(p)]
    deleted = [p for p in tracked_changed if not (REPO / p).exists()]
    (out_dir / "deleted_tracked_files.txt").write_text("\n".join(sorted(deleted)) + ("\n" if deleted else ""), encoding="utf-8")

    hashes: dict[str, dict] = {}
    for rel in sorted(tracked_changed):
        if rel in deleted:
            continue
        hashes[rel] = {"class": "tracked_differs_from_HEAD", "sha256": sha256_of(REPO / rel), "bytes": (REPO / rel).stat().st_size}

    untracked = [p for p in names("ls-files", "--others", "--exclude-standard") if not excluded(p)]
    copied = 0
    for rel in sorted(untracked):
        if not (rel.startswith(SOURCE_ROOTS) or rel in SOURCE_ROOT_FILES):
            continue
        src = REPO / rel
        if not src.is_file():
            continue
        dst = out_dir / "untracked_source" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        hashes[rel] = {"class": "untracked_source", "sha256": sha256_of(src), "bytes": src.stat().st_size}
        copied += 1

    rule_copied = 0
    for rel in RULE_FILES:
        src = REPO / rel
        if not src.is_file():
            continue
        dst = out_dir / "rule_files" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        hashes.setdefault(rel, {"class": "rule_file", "sha256": sha256_of(src), "bytes": src.stat().st_size})
        hashes[rel]["is_rule_file"] = True
        rule_copied += 1

    (out_dir / "file_hashes.json").write_text(json.dumps(hashes, indent=1, sort_keys=True), encoding="utf-8")
    summary = {
        "snapshot_dir": str(out_dir.relative_to(REPO)),
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "branch": branch, "head_sha": head, "head_subject": subject,
        "tracked_files_differing_from_head": len(tracked_changed), "tracked_files_deleted": len(deleted),
        "untracked_source_files_copied": copied, "rule_files_copied": rule_copied,
        "hashed_files": len(hashes),
        "tracked_diff_sha256": sha256_of(out_dir / "tracked_diff_vs_HEAD.patch"),
        "note": "Nothing was committed or stashed. Untracked evidence directories are not copied (bound by hash and path in the manifest).",
    }
    (out_dir / "HEAD.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1]).resolve()))
