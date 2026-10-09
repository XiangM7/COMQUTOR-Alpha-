#!/usr/bin/env python3
"""T4 round 34 (D1 fix): assemble the D1 supplement package for John from this round's own files (standard library only).
Writes only under --pkg (refuses to overwrite)."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True
R = Path(__file__).resolve().parents[1]
COPY = {  # package path -> source path under this round's directory
    "00_D1修复附录.md": "john_docs/00_D1修复附录.md",
    "README.md": "john_docs/README.md",
    "verify_d1_fix.py": "tools/verify_d1_fix.py",
    "01_before_after": "01_before_after",
    "02_code/round34_d1_changes.diff": "02_code/round34_d1_changes.diff",
    "02_code/changed_files.json": "02_code/changed_files.json",
    "02_code/prompt_versions.json": "02_code/prompt_versions.json",
    "03_tests": "03_tests",
    "04_production_entry": "04_production_entry",
    "05_hash_proof/state_before.json": "hash_proof/state_before.json",
    "05_hash_proof/state_after.json": "hash_proof/state_after.json",
    "05_hash_proof/README.md": "hash_proof/README.md",
    "tools": "tools",
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pkg", required=True)
    pkg = Path(ap.parse_args(argv).pkg)
    if pkg.exists():
        raise SystemExit(f"{pkg} exists; refusing to overwrite")
    n = 0
    for dst, src in COPY.items():
        s = R / src
        if s.is_dir():
            for p in sorted(s.rglob("*")):
                if p.is_file() and p.name != ".DS_Store" and "__pycache__" not in p.parts:
                    t = pkg / dst / p.relative_to(s)
                    t.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, t)
                    n += 1
        else:
            (pkg / dst).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, pkg / dst)
            n += 1
    print(f"copied {n} files into {pkg.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
