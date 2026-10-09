#!/usr/bin/env python3
"""Hashes every production source file (comqutor_alpha/**/*.py, scripts/*.sh, frontend/src non-test files)
so a later --diff proves exactly which production files a round changed (read-only).

usage: snapshot_production_tree.py <out.json>            write a snapshot
       snapshot_production_tree.py --diff <before.json>  compare the current tree with a snapshot (exit 1 on any difference)
"""
import hashlib, json, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]


def current():
    files = {}
    for pattern in ("comqutor_alpha/**/*.py", "comqutor_alpha/**/*.yaml", "scripts/*.sh", "frontend/src/**/*.ts", "frontend/src/**/*.tsx"):
        for p in sorted(REPO.glob(pattern)):
            if p.is_file() and "__pycache__" not in p.parts and not p.name.endswith((".test.ts", ".test.tsx")):
                files[str(p.relative_to(REPO))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return files


if sys.argv[1] == "--diff":
    before = json.loads(Path(sys.argv[2]).read_text())["files"]
    now = current()
    changed = sorted(k for k in set(before) | set(now) if before.get(k) != now.get(k))
    print(json.dumps({"files_before": len(before), "files_now": len(now), "changed": changed}, indent=1))
    sys.exit(1 if changed else 0)
Path(sys.argv[1]).write_text(json.dumps({"purpose": "production source hashes before round 19", "files": current()}, indent=1, sort_keys=True))
print("wrote", sys.argv[1], len(current()), "files")
