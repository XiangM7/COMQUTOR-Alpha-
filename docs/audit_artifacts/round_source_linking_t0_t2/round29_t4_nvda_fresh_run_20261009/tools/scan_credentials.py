#!/usr/bin/env python3
"""T4 Phase A: scan this round's directory for credential VALUES (read from .env in memory; never printed or written).

Secrets: every .env value whose key looks like a key/secret/token/password, plus the password inside each database URL. Every file
under the T4 directory is scanned as bytes, including members of .zip and .tar.gz files. Output: counts and file paths only.

    python scan_credentials.py --out hash_proof/credential_scan_result.json
"""
from __future__ import annotations

import argparse
import io
import json
import tarfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

HERE = Path(__file__).resolve().parent
T4 = HERE.parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())


def secrets() -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for key, value in dotenv_values(REPO / ".env").items():
        if not value:
            continue
        if any(t in key.upper() for t in ("KEY", "SECRET", "TOKEN", "PASSWORD")) and len(value) >= 6:
            out[key] = value.encode()
        if "URL" in key.upper() and "://" in value:
            try:
                password = make_url(value).password
            except Exception:
                password = None
            if password and len(password) >= 6:
                out[f"{key}:password"] = str(password).encode()
    return out


def blobs(path: Path):
    data = path.read_bytes()
    yield str(path.relative_to(T4)), data
    if path.suffix == ".zip":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in z.namelist():
                yield f"{path.relative_to(T4)}!{name}", z.read(name)
    if path.name.endswith(".tar.gz"):
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
            for member in t.getmembers():
                if member.isfile():
                    yield f"{path.relative_to(T4)}!{member.name}", t.extractfile(member).read()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    found = secrets()
    hits, scanned = [], 0
    for path in sorted(p for p in T4.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        for name, data in blobs(path):
            scanned += 1
            for key, value in found.items():
                if value in data:
                    hits.append({"file": name, "secret_key": key})
    doc = {"scanned_at": datetime.now(UTC).isoformat(), "directory": str(T4.relative_to(REPO)), "secret_values_checked": sorted(found),
           "blobs_scanned": scanned, "hits": hits, "clean": not hits}
    Path(args.out).write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: doc[k] for k in ("secret_values_checked", "blobs_scanned", "clean")}, indent=1), f"hits={len(hits)}")
    return 0 if not hits else 4


if __name__ == "__main__":
    raise SystemExit(main())
