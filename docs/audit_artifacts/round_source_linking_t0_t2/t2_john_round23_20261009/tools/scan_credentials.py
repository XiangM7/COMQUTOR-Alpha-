#!/usr/bin/env python3
"""Credential and auth-header scan of a directory (standard library only). Copied from the T4 round 31/32 tool for the T2 John version (2026-10-09).

Every file is scanned as bytes, including the members of .zip and .tar.gz files.
1. Pattern scan (always): API-key shapes (sk-..., sk-ant-...), Bearer tokens, authorization / x-api-key / api-key header or
   field values other than an explicit redaction, and database URLs that carry a password.
2. Value scan (only with --env): every value in that .env file whose key looks like a key/secret/token/password, plus the
   password inside each database URL in it. Values are held in memory only; output names the .env key, never the value.

Output: counts and file paths only.

    python3 tools/scan_credentials.py                      # pattern scan of the package
    python3 tools/scan_credentials.py --env ../../../../../.env   # plus value scan (inside the repository)
"""
from __future__ import annotations

import argparse
import io
import json
import re
import tarfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

PKG = Path(__file__).resolve().parent.parent
REDACTED = re.compile(rb"^\W*(redacted|\*+|\[redacted\]|\*\*\*redacted\*\*\*|<redacted>|none|null)?\W*$", re.I)
PATTERNS = {  # group 1 = the credential-like value
    "api_key_sk": re.compile(rb"\b(sk-(?:ant-)?[A-Za-z0-9_\-]{20,})"),
    "bearer_token": re.compile(rb"Bearer\s+([A-Za-z0-9._\-]{16,})"),
    "db_url_with_password": re.compile(rb"\b(?:postgres(?:ql)?|mysql|mssql)(?:\+\w+)?://[^:/\s@\"']+:([^@\s\"']+)@"),
}
# Values that are visibly NOT credentials: redaction markers and the literal test-fixture strings used in the repository's tests
# (dummy DSNs such as fake:fake@127.0.0.1:1, u:p@host, user:pass@192.0.2.1, api_key="placeholder", sk-testsecret...). A match
# with one of these is reported under fixture_or_redacted, not as a hit.
FIXTURE_OR_REDACTED = {b"***REDACTED***", b"REDACTED", b"fake", b"p", b"pass", b"placeholder", b"sk-testsecret0123456789abcdef",
                       # round 32: literal stand-ins the tests and the zero-call replay set for DEEPSEEK_API_KEY
                       b"replay-not-a-key", b"test-not-a-key", b"mock-not-a-key",
                       # T2 John version (2026-10-09): the self-test FAKES tuple of Round 23's own credential_scan.py
                       b"sk-abcdefghijklmnopqrstuvwxyz012345", b"abcdefghijklmnopqrstuvwxyz0123456789ABC",
                       b"should-never-be-saved-0123456789", b"hunter2hunter2"}
HEADER_FIELD = re.compile(rb"[\"']?(authorization|x-api-key|api[_-]?key|proxy-authorization)[\"']?\s*[:=]\s*[\"']([^\"']*)[\"']", re.I)


def env_secrets(env_path: Path) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip().removeprefix("export ").strip(), value.strip().strip("'\"")
        if not value:
            continue
        if any(t in key.upper() for t in ("KEY", "SECRET", "TOKEN", "PASSWORD")) and len(value) >= 6:
            out[key] = value.encode()
        if "URL" in key.upper() and "://" in value:
            password = urlsplit(value).password
            if password and len(password) >= 6:
                out[f"{key}:password"] = password.encode()
    return out


def blobs(path: Path, root: Path):
    data = path.read_bytes()
    name = str(path.relative_to(root))
    yield name, data
    if path.suffix == ".zip":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for member in z.namelist():
                yield f"{name}!{member}", z.read(member)
    if path.name.endswith(".tar.gz"):
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
            for member in t.getmembers():
                if member.isfile():
                    yield f"{name}!{member.name}", t.extractfile(member).read()


def scan(root: Path, secrets: dict[str, bytes]) -> dict:
    hits, header_values, fixtures, scanned = [], {}, {}, 0
    for path in sorted(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        for name, data in blobs(path, root):
            scanned += 1
            for label, pattern in PATTERNS.items():
                for m in pattern.finditer(data):
                    if m.group(1) in FIXTURE_OR_REDACTED:
                        fixtures[f"{label}:{m.group(1).decode()}"] = fixtures.get(f"{label}:{m.group(1).decode()}", 0) + 1
                    else:
                        hits.append({"file": name, "kind": label, "offset": m.start()})
            for m in HEADER_FIELD.finditer(data):
                value = m.group(2)
                if REDACTED.match(value) or value in FIXTURE_OR_REDACTED:
                    header_values[value.decode(errors="replace") or "(empty)"] = header_values.get(value.decode(errors="replace") or "(empty)", 0) + 1
                else:
                    hits.append({"file": name, "kind": f"header_or_field:{m.group(1).decode().lower()}", "offset": m.start()})
            for key, value in secrets.items():
                if value in data:
                    hits.append({"file": name, "kind": f"env_value:{key}"})
    return {"blobs_scanned": scanned, "hits": hits, "redacted_header_or_field_values_seen": header_values, "fixture_or_redacted_matches": fixtures}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=str(PKG))
    ap.add_argument("--env")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    root = Path(args.target).resolve()
    secrets = env_secrets(Path(args.env)) if args.env else {}
    result = scan(root, secrets)
    doc = {"scanned_at": datetime.now(UTC).isoformat(), "target": root.name, "patterns": sorted(PATTERNS) + ["header_or_field"],
           "env_value_keys_checked": sorted(secrets), **result, "clean": not result["hits"]}
    if args.out:
        Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: doc[k] for k in ("target", "env_value_keys_checked", "blobs_scanned", "redacted_header_or_field_values_seen",
                                          "fixture_or_redacted_matches", "clean")},
                     ensure_ascii=False), f"hits={len(doc['hits'])}")
    for h in doc["hits"][:50]:
        print("HIT", json.dumps(h, ensure_ascii=False))
    return 0 if doc["clean"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
