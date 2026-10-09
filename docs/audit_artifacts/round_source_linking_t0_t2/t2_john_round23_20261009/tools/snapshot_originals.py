#!/usr/bin/env python3
"""T2 John version (2026-10-09): read-only hash snapshot of every original this round copies from or must leave untouched.

Standard library only; reads files, never writes anywhere except --out.

    python3 tools/snapshot_originals.py --out hash_proof/state_before.json
    python3 tools/snapshot_originals.py --out hash_proof/state_after_copy.json --compare hash_proof/state_before.json

Run digest = sha256 of "\\n".join(f"{relpath}\\t{sha256}") over the sorted files of the directory -- the same algorithm as the
Round 22 release manifest (`run_digest`), so the AMD digest is directly comparable with release_manifest_v2.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
HOME = Path.home()
SIX_RUNS = {
    "NVDA": "ded99ecd-a186-4a90-859e-0f1a0efa43db",
    "QQQ": "0d890564-2479-4361-94e8-25c48af3b9a8",
    "SNDK": "e8e0f398-7b26-4462-8135-a1410ea5b335",
    "MSFT": "64568bfb-fe0c-453c-9872-831a8dc339a0",
    "TSM": "fc09821e-c7cf-40a7-bd76-c98172e16992",
    "AMD": "d5b60b8a-66b8-44c1-9f55-ee345e58c48d",
}
ROUND_DIR = REPO / "docs/audit_artifacts/round_source_linking_t0_t2"
DIRECTORIES = {f"outputs/runs/{rid}": REPO / "outputs/runs" / rid for rid in SIX_RUNS.values()}
DIRECTORIES["round23_t2_completion_20261007"] = ROUND_DIR / "round23_t2_completion_20261007"
FILES = {
    "~/Desktop/t2.zip (uploaded T2 package)": HOME / "Desktop/t2.zip",
    "~/Desktop/t1.zip (uploaded T1 package)": HOME / "Desktop/t1.zip",
    "~/Desktop/t1/我方对应交付/运行产物打包/round22_runs.tar.gz (T1 run archive)": HOME / "Desktop/t1/我方对应交付/运行产物打包/round22_runs.tar.gz",
    "~/Desktop/COMQUTOR_John_T1_T2_reviewed.zip": HOME / "Desktop/COMQUTOR_John_T1_T2_reviewed.zip",
    "round22 release_manifest_v2.json": ROUND_DIR / "round22_t1_closeout_20261007/release_manifest_v2.json",
    "round22 run_directory_hashes/d5b60b8a.json": ROUND_DIR / "round22_t1_closeout_20261007/run_directory_hashes/d5b60b8a-66b8-44c1-9f55-ee345e58c48d.json",
}
T1_ARCHIVE = HOME / "Desktop/t1/我方对应交付/运行产物打包/round22_runs.tar.gz"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_digest(per_file: dict[str, str]) -> str:
    return sha256_bytes("\n".join(f"{rel}\t{per_file[rel]}" for rel in sorted(per_file)).encode())


def hash_dir(root: Path) -> dict:
    files = sorted(p for p in root.rglob("*") if p.is_file())
    per_file = {p.relative_to(root).as_posix(): sha256_file(p) for p in files}
    mtimes = [p.stat().st_mtime for p in files]
    return {
        "file_count": len(files),
        "total_bytes": sum(p.stat().st_size for p in files),
        "digest_sha256": run_digest(per_file),
        "per_file_sha256": per_file,
        "oldest_mtime_utc": datetime.fromtimestamp(min(mtimes), UTC).isoformat() if mtimes else None,
        "newest_mtime_utc": datetime.fromtimestamp(max(mtimes), UTC).isoformat() if mtimes else None,
        "symlinks": sum(1 for p in root.rglob("*") if p.is_symlink()),
    }


def is_appledouble(name: str) -> bool:
    """macOS '._<name>' metadata members that bsdtar adds (and hides in `tar -t`); they are not run files."""
    return name.rsplit("/", 1)[-1].startswith("._")


def hash_tar_member_dir(archive: Path, prefix: str) -> dict:
    per_file, sizes, appledouble = {}, 0, 0
    with tarfile.open(archive, "r:gz") as t:
        for m in t.getmembers():
            if not m.isfile():
                continue
            if is_appledouble(m.name) and (m.name.startswith(prefix + "/") or m.name == prefix.rsplit("/", 1)[0] + "/._" + prefix.rsplit("/", 1)[1]):
                appledouble += 1
            elif m.name.startswith(prefix + "/"):
                per_file[m.name[len(prefix) + 1:]] = sha256_bytes(t.extractfile(m).read())
                sizes += m.size
    return {"file_count": len(per_file), "total_bytes": sizes, "digest_sha256": run_digest(per_file), "per_file_sha256": per_file,
            "appledouble_members_excluded": appledouble}


def snapshot() -> dict:
    doc = {"taken_at": datetime.now(UTC).isoformat(), "directories": {}, "files": {}, "t1_archive_amd_members": None}
    for label, path in DIRECTORIES.items():
        doc["directories"][label] = hash_dir(path) if path.is_dir() else {"missing": True}
    for label, path in FILES.items():
        doc["files"][label] = {"sha256": sha256_file(path), "size": path.stat().st_size} if path.is_file() else {"missing": True}
    doc["t1_archive_amd_members"] = hash_tar_member_dir(T1_ARCHIVE, f"outputs/runs/{SIX_RUNS['AMD']}")
    return doc


def compare(before: dict, after: dict) -> dict:
    out = {"directories": {}, "files": {}, "t1_archive_amd_members": None}
    for label, b in before["directories"].items():
        a = after["directories"].get(label, {})
        out["directories"][label] = {"before": b.get("digest_sha256"), "after": a.get("digest_sha256"),
                                     "unchanged": b.get("digest_sha256") == a.get("digest_sha256") and "missing" not in b}
    for label, b in before["files"].items():
        a = after["files"].get(label, {})
        out["files"][label] = {"before": b.get("sha256"), "after": a.get("sha256"), "unchanged": b.get("sha256") == a.get("sha256") and "missing" not in b}
    b, a = before["t1_archive_amd_members"], after["t1_archive_amd_members"]
    out["t1_archive_amd_members"] = {"before": b["digest_sha256"], "after": a["digest_sha256"], "unchanged": b["digest_sha256"] == a["digest_sha256"]}
    out["all_unchanged"] = all(v["unchanged"] for group in ("directories", "files") for v in out[group].values()) and out["t1_archive_amd_members"]["unchanged"]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--compare")
    args = ap.parse_args(argv)
    doc = snapshot()
    if args.compare:
        doc["comparison_with"] = Path(args.compare).name
        doc["comparison"] = compare(json.loads(Path(args.compare).read_text(encoding="utf-8")), doc)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for label, d in doc["directories"].items():
        print(f"{label}: files={d.get('file_count')} digest={d.get('digest_sha256')}")
    for label, d in doc["files"].items():
        print(f"{label}: sha256={d.get('sha256')}")
    print(f"T1 archive AMD members: files={doc['t1_archive_amd_members']['file_count']} digest={doc['t1_archive_amd_members']['digest_sha256']}")
    if args.compare:
        print("all_unchanged =", doc["comparison"]["all_unchanged"])
        return 0 if doc["comparison"]["all_unchanged"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
