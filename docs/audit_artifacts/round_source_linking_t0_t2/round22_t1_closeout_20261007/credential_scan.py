#!/usr/bin/env python3
"""Round 22 -- credential scan of everything this round created or changed. Secret VALUES are read from .env in memory only and are never printed
or written; the result file records only counts and file names. Also applies generic token patterns and checks that no DB URL carries a plain password.
Scope: the whole Round 22 folder (text files; the code snapshots included), the new/changed code, tests and fixtures of this round, and the text members
of any zip in the folder."""
import json, re, subprocess, sys, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
from dotenv import dotenv_values

env = dotenv_values(REPO / ".env")
secret_values = set()
for k, v in env.items():
    if v and re.search(r"KEY|TOKEN|SECRET|PASSWORD", k, re.I) and len(v) >= 8:
        secret_values.add(v)
    if v and "://" in v and "@" in v:
        m = re.match(r"^[^:]+://[^:]+:([^@]+)@", v)
        if m and len(m.group(1)) >= 6:
            secret_values.add(m.group(1))
PATTERNS = {
    "openai_style_key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"), "google_key": re.compile(r"AIza[0-9A-Za-z_-]{30,}"), "aws_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), "bearer_token": re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{24,}"),
    "key_assignment": re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[=:]\s*['\"]?(?!<redacted|REDACTED|\*|None|null|\s)[A-Za-z0-9_\-/+=]{16,}"),
    "db_url_with_plain_password": re.compile(r"postgres(?:ql)?(?:\+\w+)?://[^:\s/]+:(?!<redacted>|REDACTED|\*)[^@\s<]{3,}@"),
}
# the redaction test deliberately contains FAKE secret-looking strings (to prove they are removed). They are exempt by EXACT STRING wherever they appear (the
# test file, the change patch, the snapshot copies); any other match -- and any .env secret value -- still fails the scan.
FAKE_STRINGS = (
    "sk-abcdefghijklmnopqrstuvwxyz012345", "Bearer abcdefghijklmnopqrstuvwxyz0123456789ABC", "Bearer should-never-be-saved-0123456789",
    "postgresql://svc:hunter2hunter2@db.internal/app", "token=SECRETVALUE123456", "apikey=ABCDEF1234567890",
)
fake_seen: dict[str, int] = {}


def without_fakes(text: str) -> str:
    for fake in FAKE_STRINGS:
        n = text.count(fake)
        if n:
            fake_seen[fake[:12] + "…"] = fake_seen.get(fake[:12] + "…", 0) + n
            text = text.replace(fake, "<KNOWN-FAKE-TEST-STRING>")
    return text
# Group A: everything Round 22 created outside the code snapshots; Group B: the code/tests/fixtures Round 22 created or changed (the files of
# round22_changes.patch); Group C: the code snapshots -- scanned for the exact .env secret VALUES only (a real-leak check). Pattern hits in the
# snapshots come from pre-existing test files that already carry placeholder strings (fake DB URLs / fake keys) and are listed, not failed.
snapshots = HERE / "code_snapshots"
group_a = [p for p in HERE.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix not in {".png", ".pyc"} and snapshots not in p.parents]
patch = HERE / "round22_changes.patch"
if patch.exists():
    changed_rel = sorted({line.split()[2][3:] for line in patch.read_text(encoding="utf-8", errors="replace").splitlines() if line.startswith("diff -ruN")})
else:
    changed_rel = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.split()
group_b = [REPO / rel for rel in changed_rel if rel.startswith(("comqutor_alpha/", "tradingagents/", "tests/", "frontend/src/", "scripts/")) and (REPO / rel).is_file()]
group_c = [p for p in snapshots.rglob("*") if p.is_file()] if snapshots.exists() else []
targets = sorted(set(group_a) | set(group_b))
scanned, hits, snapshot_placeholder_hits = 0, [], []


def scan_text(label, text, *, exact_only=False):
    global scanned
    scanned += 1
    text = without_fakes(text)
    found = []
    for v in secret_values:
        if v in text:
            found.append({"file": label, "kind": "exact_env_secret_value", "count": text.count(v)})
    if not exact_only:
        for name, rx in PATTERNS.items():
            n = len(rx.findall(text))
            if n:
                found.append({"file": label, "kind": name, "count": n})
    if exact_only:
        hits.extend(found)
        return
    hits.extend(found)


for path in group_c:  # snapshots: real-leak check (exact values) + informational placeholder patterns
    label = str(path.relative_to(REPO))
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        hits.append({"file": label, "kind": f"UNREADABLE:{type(e).__name__}", "count": 1})
        continue
    scan_text(label, text, exact_only=True)
    text = without_fakes(text)
    for name, rx in PATTERNS.items():
        n = len(rx.findall(text))
        if n:
            snapshot_placeholder_hits.append({"file": label, "kind": name, "count": n})
for path in targets:
    label = str(path.relative_to(REPO))
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                scan_text(f"{label}::{name}", z.read(name).decode("utf-8", "replace"))
        continue
    try:
        scan_text(label, path.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        hits.append({"file": label, "kind": f"UNREADABLE:{type(e).__name__}", "count": 1})
summary = (f"{scanned} 个文本文件已扫描（{len(secret_values)} 个来自 .env 的密钥值做精确匹配，值不落盘；代码快照只做精确密钥值检查）；命中 {len(hits)} 处" + ("：无" if not hits else "：见 credential_scan_result.json")
           + (f"；另有已知的**假**密钥串（脱敏测试故意写入，按精确字符串豁免）出现 {sum(fake_seen.values())} 处" if fake_seen else ""))
(HERE / "credential_scan_result.json").write_text(json.dumps({"scanned_items": scanned, "env_secret_values_checked": len(secret_values), "hits": hits, "known_fake_test_strings_exempted_by_exact_string": fake_seen,
                                                                "pre_existing_placeholder_pattern_hits_in_snapshots_informational": snapshot_placeholder_hits, "summary": summary}, ensure_ascii=False, indent=1))
print(summary)
sys.exit(1 if hits else 0)
