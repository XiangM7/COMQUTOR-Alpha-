#!/usr/bin/env python3
"""T4 round 32: write manifest.json -- path, size and sha256 of every file in the package except manifest.json itself
(standard library only). Run last.

    python3 tools/build_manifest32.py
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    files = sorted(p for p in PKG.rglob("*") if p.is_file() and p.name not in ("manifest.json", ".DS_Store") and "__pycache__" not in p.parts)
    entries = [{"path": str(p.relative_to(PKG)), "bytes": p.stat().st_size, "sha256": sha(p)} for p in files]
    refs = json.loads((PKG / "references" / "prior_packages.json").read_text(encoding="utf-8"))
    doc = {"schema": "t4.round32.final_manifest.v1", "package": "T4_final", "generated_at": datetime.now(UTC).isoformat(),
           "file_count": len(entries), "total_bytes": sum(e["bytes"] for e in entries), "self_contained": False,
           "not_in_package": {"external_files": {k: {"path_under_home": v["path_under_home"], "sha256": v["sha256"]} for k, v in refs["external_files"].items()},
                              "reproduction_needs": "the repository at the final code identity (02_code/) and the local PostgreSQL for tests, chain and replay"},
           "files": entries}
    (PKG / "manifest.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"file_count": doc["file_count"], "total_bytes": doc["total_bytes"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
