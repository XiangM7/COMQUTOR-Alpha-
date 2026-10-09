#!/usr/bin/env python3
"""Round 24 (T2 gap closure): credential scan of everything this round created or changed - the whole Round 24 directory (text files) and the working-tree
copy of every file listed in t2_files.json. Secret VALUES are read from .env in memory only and are never printed or written; the result records counts and
file names only. Also applies generic token patterns. Known FAKE test strings (pre-existing placeholders in test files) are exempt by exact string only.

usage: python tools/credential_scan.py   # writes credential_scan_result.json into the Round 24 directory; exit 0 only with no hit
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent  # the Round 24 directory
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())

from dotenv import dotenv_values  # noqa: E402

env = dotenv_values(REPO / ".env")
secrets = set()
for key, value in env.items():
    if value and re.search(r"KEY|TOKEN|SECRET|PASSWORD", key, re.I) and len(value) >= 8:
        secrets.add(value)
    if value and "://" in value and "@" in value:
        match = re.match(r"^[^:]+://[^:]+:([^@]+)@", value)
        if match and len(match.group(1)) >= 6:
            secrets.add(match.group(1))
PATTERNS = {
    "openai_style_key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "google_key": re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    "aws_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "bearer_token": re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{24,}"),
    "key_assignment": re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[=:]\s*['\"]?(?!<redacted|REDACTED|\*|None|null|\s)[A-Za-z0-9_\-/+=]{16,}"),
    "db_url_with_plain_password": re.compile(r"postgres(?:ql)?(?:\+\w+)?://[^:\s/]+:(?!<redacted>|REDACTED|\*)[^@\s<]{3,}@"),
}
FAKES = (
    "sk-abcdefghijklmnopqrstuvwxyz012345", "Bearer abcdefghijklmnopqrstuvwxyz0123456789ABC", "Bearer should-never-be-saved-0123456789",
    "postgresql://svc:hunter2hunter2@db.internal/app", "token=SECRETVALUE123456", "apikey=ABCDEF1234567890",
    # placeholders that the RAW test output of the full suite prints: the launcher-isolation tests (which fail in the baseline) print their fake URLs,
    # and a redaction test's parametrization id contains a fake key. Exempt by exact string only.
    "postgresql+psycopg://fake:fake@127.0.0.1:1/FAKE_PRODUCTION_MARKER_DB",
    "postgresql+psycopg://fake:fake@127.0.0.1:2/FAKE_ISOLATED_TEST_MARKER_DB_test",
    "api_key=sk-sensitive-value",
)
scanned = 0
secret_hits: list[str] = []
pattern_hits: list[dict] = []


def shape(text: str) -> str:
    return re.sub(r"[a-z]", "a", re.sub(r"[A-Z]", "A", re.sub(r"[0-9]", "9", text)))[:40]


def scan(label: str, data: bytes) -> None:
    global scanned
    text = data.decode("utf-8", errors="replace")
    scanned += 1
    if any(s in text for s in secrets):
        secret_hits.append(label)
    clean = text
    for fake in FAKES:
        clean = clean.replace(fake, "")
    for name, rx in PATTERNS.items():
        match = rx.search(clean)
        if match:
            pattern_hits.append({"file": label, "pattern": name, "shape_of_match": shape(match.group(0)), "length": len(match.group(0))})


files = {p for p in HERE.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix not in {".png", ".pyc", ".gz", ".zip"}}
if (HERE / "t2_files.json").exists():
    files |= {REPO / entry["path"] for entry in json.loads((HERE / "t2_files.json").read_text(encoding="utf-8"))["files"]}
for path in sorted(files):
    scan(str(path.relative_to(REPO)), path.read_bytes())
result = {
    "files_scanned": scanned,
    "exact_env_secret_values_found_in": secret_hits,
    "pattern_hits": pattern_hits,
    "note": "pattern hits are listed with the SHAPE of the match only (character classes), never the text",
    "ok": not secret_hits and not pattern_hits,
}
(HERE / "credential_scan_result.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
print(json.dumps({k: result[k] for k in ("files_scanned", "exact_env_secret_values_found_in", "pattern_hits", "ok")}, indent=1))
sys.exit(0 if result["ok"] else 1)
