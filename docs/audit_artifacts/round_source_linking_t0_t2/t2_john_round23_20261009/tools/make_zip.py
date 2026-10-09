#!/usr/bin/env python3
"""T2 John version (2026-10-09): zip the package directory (standard library only).

Entries are written in sorted order under the package folder name, with the UTF-8 filename flag set (so Chinese names unpack
correctly everywhere), and without .DS_Store. Refuses to overwrite an existing ZIP.
"""
from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path

IGNORED_NAMES = {".DS_Store"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pkg", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    pkg, out = Path(args.pkg).resolve(), Path(args.out)
    if out.exists():
        raise SystemExit(f"{out} already exists; refusing to overwrite")
    files = [p for p in sorted(pkg.rglob("*")) if p.is_file() and p.name not in IGNORED_NAMES]
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in files:
            info = zipfile.ZipInfo.from_file(p, arcname=f"{pkg.name}/{p.relative_to(pkg).as_posix()}")
            info.compress_type = zipfile.ZIP_DEFLATED
            info.flag_bits |= 0x800
            with p.open("rb") as f:
                z.writestr(info, f.read(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
    print(f"{out.name}: {len(files)} files, {out.stat().st_size:,} bytes, sha256 {hashlib.sha256(out.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
