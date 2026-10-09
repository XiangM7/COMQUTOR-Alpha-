#!/usr/bin/env python3
"""T4 round 33 (2026-10-09): write <pkg>/manifest.json -- every file of the package except the manifest itself (size, sha256).
Standard library only; the last step before zipping."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pkg", required=True)
    pkg = Path(ap.parse_args(argv).pkg)
    files = [{"path": p.relative_to(pkg).as_posix(), "size": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
             for p in sorted(pkg.rglob("*"))
             if p.is_file() and p.name != ".DS_Store" and "__pycache__" not in p.parts and p.relative_to(pkg).as_posix() != "manifest.json"]
    doc = {"schema": "t4.round33.manifest.v1", "package": pkg.name, "recipient": "John", "written_at": datetime.now(UTC).isoformat(),
           "file_count": len(files), "total_bytes": sum(f["size"] for f in files), "files": files}
    (pkg / "manifest.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"manifest: {len(files)} files, {doc['total_bytes']:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
