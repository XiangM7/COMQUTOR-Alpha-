#!/usr/bin/env python3
"""T2 John version (2026-10-09): copy the verifier into the package and write package_manifest.json (last step before zipping).

Standard library only; writes <pkg>/verify_t2_package.py and <pkg>/package_manifest.json. Rerunnable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
IGNORED_NAMES = {".DS_Store"}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pkg", required=True)
    args = ap.parse_args(argv)
    pkg = Path(args.pkg)
    shutil.copy2(TOOLS / "verify_t2_package.py", pkg / "verify_t2_package.py")
    files = []
    for p in sorted(pkg.rglob("*")):
        rel = p.relative_to(pkg).as_posix()
        if p.is_file() and p.name not in IGNORED_NAMES and rel != "package_manifest.json":
            files.append({"path": rel, "size": p.stat().st_size, "sha256": sha256_file(p)})
    doc = {
        "package": pkg.name,
        "recipient": "John",
        "written_at": datetime.now(UTC).isoformat(),
        "note": "Every file of the package except this manifest. Checked by verify_t2_package.py (check 1).",
        "file_count": len(files),
        "total_bytes": sum(f["size"] for f in files),
        "files": files,
    }
    (pkg / "package_manifest.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"manifest: {len(files)} files, {doc['total_bytes']:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
