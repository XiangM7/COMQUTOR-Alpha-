#!/usr/bin/env python3
"""The Round 24 delta: exactly what changed since the Round 23 state of the files this round touched.

Round 23's package holds the T2 diff against HEAD. This round changed some of those files and added others, so the diff READERS need next is Round 23 -> now.
`round23_state_of_changed_files/` holds the Round 23 version of every file this round modified (copied before the first edit; checked here against the sha256 Round 23
itself recorded in its t2_files.json). The delta is a unified diff of each of them against the working tree, plus a new-file diff for each file Round 24 added.
It is verified by applying it to a copy of the Round 23 state and comparing hashes.

usage: python tools/build_round24_delta.py
"""
from __future__ import annotations

import difflib
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
STATE = HERE / "round23_state_of_changed_files"
ROUND23_FILES = REPO / "docs/audit_artifacts/round_source_linking_t0_t2/round23_t2_completion_20261007/t2_files.json"
NEW_FILES = [
    "comqutor_alpha/regression/gold_contract_rules.py",
    "tests/test_t2_gold_contract_alpha_rules.py",
    "tests/test_t2_conflict_semantics_real_b2.py",
]
# the only modified file whose Round 23 text is not stored whole: this round only APPENDED four entries (PD-018..PD-021) to it
APPENDED_ONLY = {"docs/specs/product_decisions_and_unknowns.md": "\n## PD-018 — "}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    recorded = {e["path"]: e["sha256_working_tree"] for e in json.loads(ROUND23_FILES.read_text(encoding="utf-8"))["files"]}
    problems, files = [], []
    stored = sorted(p for p in STATE.rglob("*") if p.is_file())
    for path in stored:
        rel = path.relative_to(STATE).as_posix()
        if rel in recorded and sha(path.read_bytes()) != recorded[rel]:
            problems.append(f"{rel}: the stored Round 23 copy does not match the sha256 Round 23 recorded")
    rebuilt_notes = {}
    for rel, marker in APPENDED_ONLY.items():
        current = (REPO / rel).read_text(encoding="utf-8")
        before = current.split(marker, 1)[0]
        if sha(before.encode("utf-8")) != recorded[rel]:
            problems.append(f"{rel}: removing the appended entries does not give the text Round 23 recorded")
        target = STATE / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(before, encoding="utf-8")
        rebuilt_notes[rel] = "Round 23 text = the current file without the appended PD-018..PD-021 block (verified against Round 23's recorded sha256)"
    parts = []
    for path in sorted(p for p in STATE.rglob("*") if p.is_file()):
        rel = path.relative_to(STATE).as_posix()
        old, new = path.read_text(encoding="utf-8").splitlines(keepends=True), (REPO / rel).read_text(encoding="utf-8").splitlines(keepends=True)
        diff = "".join(difflib.unified_diff(old, new, f"a/{rel}", f"b/{rel}"))
        if diff:
            parts.append(diff if diff.endswith("\n") else diff + "\n")
            files.append({"path": rel, "kind": "modified_since_round23", "sha256_working_tree": sha((REPO / rel).read_bytes())})
    for rel in NEW_FILES:
        new = (REPO / rel).read_text(encoding="utf-8").splitlines(keepends=True)
        diff = "".join(difflib.unified_diff([], new, "/dev/null", f"b/{rel}"))
        parts.append(diff if diff.endswith("\n") else diff + "\n")
        files.append({"path": rel, "kind": "new_in_round24", "sha256_working_tree": sha((REPO / rel).read_bytes())})
    patch = "".join(parts)
    (HERE / "round24_delta.patch").write_text(patch, encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="r24_delta_verify_") as tmp:
        work = Path(tmp)
        for entry in files:
            if entry["kind"] == "modified_since_round23":
                destination = work / entry["path"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(STATE / entry["path"], destination)
        applied = subprocess.run(["git", "-C", str(work), "apply", "--unidiff-zero", str((HERE / "round24_delta.patch").resolve())], capture_output=True, text=True)
        if applied.returncode != 0:
            problems.append(f"delta does not apply to the Round 23 state: {applied.stderr.strip()[:400]}")
        else:
            for entry in files:
                produced = work / entry["path"]
                if not produced.is_file() or sha(produced.read_bytes()) != entry["sha256_working_tree"]:
                    problems.append(f"{entry['path']}: Round 23 state + delta differs from the working tree")
    added = sum(1 for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in patch.splitlines() if line.startswith("-") and not line.startswith("---"))
    result = {
        "patch": "round24_delta.patch",
        "patch_sha256": sha(patch.encode("utf-8")),
        "files": files,
        "totals": {"files": len(files), "lines_added": added, "lines_removed": removed},
        "appended_only_note": rebuilt_notes,
        "verification": {"method": "Round 23 state of each modified file + git apply in a temp directory, hashes compared with the working tree", "problems": problems, "ok": not problems},
    }
    (HERE / "round24_delta.json").write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("totals", "verification")}, indent=1))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
