#!/usr/bin/env python3
"""T4 delivery (round 31): write manifest.json -- path, size and sha256 of every file in this package except manifest.json
itself (standard library only). Run last, after every other file is final.

    python3 tools/build_manifest.py
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
    files = sorted(p for p in PKG.rglob("*") if p.is_file() and p.name != "manifest.json" and "__pycache__" not in p.parts
                   and p.name != ".DS_Store")
    entries = [{"path": str(p.relative_to(PKG)), "bytes": p.stat().st_size, "sha256": sha(p)} for p in files]
    refs = json.loads((PKG / "references" / "prior_packages.json").read_text(encoding="utf-8"))
    doc = {
        "schema": "t4.round31.delivery_manifest.v1",
        "package": "T4_delivery",
        "generated_at": datetime.now(UTC).isoformat(),
        "file_count": len(entries),
        "total_bytes": sum(e["bytes"] for e in entries),
        "self_contained": False,
        "not_in_package": {
            "prior_packages": "T1/T2/T3 delivery packages and the earlier T4 round directories: path and sha256 only, see references/prior_packages.json",
            "external_files": {k: {"path_under_home": v["path_under_home"], "sha256": v["sha256"], "bytes": v["bytes"], "how_to_obtain": v["how_to_obtain"]}
                               for k, v in refs["external_files"].items()},
            "repository_code": "regenerating the claim ledgers with the production code needs the repository at the code identity in code_identity/",
        },
        "files": entries,
    }
    (PKG / "manifest.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"file_count": doc["file_count"], "total_bytes": doc["total_bytes"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
