#!/usr/bin/env python3
"""Round 19 -- credential scan of everything this round created or changed. Secret VALUES are read from .env in memory only and are never printed or written;
the result file records only counts and file names. Also applies generic token patterns and checks that no DB URL carries a plain password.
Scope: the round-19 folder (text files, plus the text members of the browser-exported ZIP), the two new test files, and the modified reader."""
import json, re, sys, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
from dotenv import dotenv_values

env = dotenv_values(REPO / ".env")
secret_values = set()
for k, v in env.items():
    if v and re.search(r"KEY|TOKEN|SECRET|PASSWORD", k, re.I) and len(v) >= 8:
        secret_values.add(v)
    if v and "://" in v and "@" in v:  # DB URLs: also the password component
        m = re.match(r"^[^:]+://[^:]+:([^@]+)@", v)
        if m and len(m.group(1)) >= 6:
            secret_values.add(m.group(1))
PATTERNS = {
    "openai_style_key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"), "google_key": re.compile(r"AIza[0-9A-Za-z_-]{30,}"), "aws_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), "bearer_token": re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{24,}"),
    "key_assignment": re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[=:]\s*['\"]?(?!<redacted|REDACTED|\*|None|null|\s)[A-Za-z0-9_\-/+=]{16,}"),
    "db_url_with_plain_password": re.compile(r"postgres(?:ql)?(?:\+\w+)?://[^:\s/]+:(?!<redacted>|REDACTED|\*)[^@\s<]{3,}@"),
}
targets = [p for p in HERE.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix not in {".png", ".pyc"}]
targets += [REPO / "tests/test_alpha_evidence_consumption_contract.py", REPO / "tests/test_agent_outputs_cited_source_list_read_time.py", REPO / "comqutor_alpha/api/agent_output_reader.py"]
scanned, hits = 0, []


def scan_text(label, text):
    global scanned
    scanned += 1
    for v in secret_values:
        if v in text:
            hits.append({"file": label, "kind": "exact_env_secret_value", "count": text.count(v)})
    for name, rx in PATTERNS.items():
        n = len(rx.findall(text))
        if n:
            hits.append({"file": label, "kind": name, "count": n})


for path in targets:
    label = str(path.relative_to(REPO))
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                scan_text(f"{label}::{name}", z.read(name).decode("utf-8", "replace"))
        continue
    try:
        scan_text(label, path.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:  # unreadable file: say so, do not skip silently
        hits.append({"file": label, "kind": f"UNREADABLE:{type(e).__name__}", "count": 1})
summary = f"{scanned} 个文本文件/ZIP 成员已扫描（{len(secret_values)} 个来自 .env 的密钥值做精确匹配，值不落盘）；命中 {len(hits)} 处" + ("：无" if not hits else "：见 credential_scan_result.json")
(HERE / "credential_scan_result.json").write_text(json.dumps({"scanned_items": scanned, "env_secret_values_checked": len(secret_values), "hits": hits, "summary": summary}, ensure_ascii=False, indent=1))
print(summary)
sys.exit(1 if hits else 0)
