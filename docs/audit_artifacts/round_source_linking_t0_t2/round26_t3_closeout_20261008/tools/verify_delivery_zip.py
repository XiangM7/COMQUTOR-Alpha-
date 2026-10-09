#!/usr/bin/env python3
"""T3 closeout: unpack the delivery ZIP into a new directory and check it (the scoring step runs under the network trap).

1. every file's sha256 against SHA256SUMS.txt, and every unpacked file listed there;
2. every file path cited in backticks by the package's reports resolves inside the unpacked tree;
3. credential scan of the whole unpacked tree (exact .env secret values, read in memory only, plus token patterns);
4. the official score is reproduced from the unpacked inputs with the repository's frozen driver and compared byte for byte.

    python verify_delivery_zip.py --zip <zip> --unpack-dir <new dir> --report <json>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
D = "docs/audit_artifacts/round_source_linking_t0_t2"
CLOSEOUT = f"{D}/{HERE.parent.name}"
R25 = f"{D}/round25_t3_minimal_prep_20261008"
E = "outputs/t3_joint_evaluations/t3joint-20261008T170322Z-bd99811e"
REPORTS = ("README.md", "00_T3_main_report.md", "01_citation_rejections/six_rejections.md", "02_relation_consumption/relation_consumption.md",
           "03_task_profile/task_profile.md", "04_reports/issue_list.md", "04_reports/john_t3_requirements_map.md",
           "04_reports/a304_a101_a103_correspondence.md", "test_evidence/README.md")
PATH_TOKEN = re.compile(r"`([^`\s]+)`")
FILE_LIKE = re.compile(r"\.(json|jsonl|md|py|csv|diff|patch|log|txt|xml|yaml|sh)$|/$")
PATTERNS = {
    "openai_style_key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "google_key": re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    "aws_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "bearer_token": re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{24,}"),
    "key_assignment": re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[=:]\s*['\"]?(?!<redacted|REDACTED|\*|None|null|\s)[A-Za-z0-9_\-/+=]{16,}"),
    "db_url_with_plain_password": re.compile(r"postgres(?:ql)?(?:\+\w+)?://[^:\s/]+:(?!<redacted>|REDACTED|\*)[^@\s<]{3,}@"),
}
# exact placeholder strings already present in packaged, pre-existing files (Round 25's scanner list) -- exempt by exact string only
FAKES = (
    "sk-abcdefghijklmnopqrstuvwxyz012345", "Bearer abcdefghijklmnopqrstuvwxyz0123456789ABC", "Bearer should-never-be-saved-0123456789",
    "postgresql://svc:hunter2hunter2@db.internal/app", "token=SECRETVALUE123456", "apikey=ABCDEF1234567890",
    "postgresql+psycopg://fake:fake@127.0.0.1:1/FAKE_PRODUCTION_MARKER_DB", "postgresql+psycopg://fake:fake@127.0.0.1:2/FAKE_ISOLATED_TEST_MARKER_DB_test",
    "api_key=sk-sensitive-value", 'secret = "sk-provider-secret"', "postgresql+psycopg://fake:fake@192.0.2.1:5999/comqutor_alpha",
    "postgresql+psycopg://user:pass@192.0.2.1:5999/comqutor_alpha", 'api_key="rehearsal-not-a-key"',
)


def _secrets() -> set[str]:
    from dotenv import dotenv_values

    found = set()
    for key, value in dotenv_values(REPO / ".env").items():
        if value and re.search(r"KEY|TOKEN|SECRET|PASSWORD", key, re.I) and len(value) >= 8:
            found.add(value)
        match = re.match(r"^[^:]+://[^:]+:([^@]+)@", value or "")
        if match and len(match.group(1)) >= 6:
            found.add(match.group(1))
    return found


def _resolve(token: str, root: Path, report_dir: Path, names: set[str]) -> str:
    """'package' when the cited path exists in the unpacked tree (tried against the report's own directory, the package roots and the
    code tree, or -- for a bare file name -- anywhere in the package); 'repository_code' when it is a code location the reports cite for
    context that exists in the repository but is deliberately not packaged; 'missing' otherwise."""
    token = token.rstrip(".,;:)").replace("round25…", R25).replace("round26…", CLOSEOUT)
    bases = (report_dir, root, root / CLOSEOUT, root / D, root / R25, root / "code" / "after", root / "code" / "after" / "comqutor_alpha",
             root / "code" / "reference", root / "code" / "diff")
    if any((base / token).exists() for base in bases) or ("/" not in token.rstrip("/") and token.rstrip("/") in names):
        return "package"
    for repo_base in (REPO, REPO / "comqutor_alpha", REPO / "comqutor_alpha" / "api", REPO / "comqutor_alpha" / "structure_engine"):
        if (repo_base / token).exists():
            return "repository_code"
    return "missing"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True)
    ap.add_argument("--unpack-dir", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args(argv)
    root = Path(args.unpack_dir)
    if root.exists():
        print("refusing: unpack dir exists", root, file=sys.stderr)
        return 2
    with zipfile.ZipFile(args.zip) as zf:
        zf.extractall(root)
    sums = {line.split("  ", 1)[1]: line.split("  ", 1)[0] for line in (root / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines() if line}
    unpacked = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    sha_mismatch = sorted(rel for rel, digest in sums.items() if not (root / rel).is_file() or hashlib.sha256((root / rel).read_bytes()).hexdigest() != digest)
    not_listed = sorted(unpacked - set(sums) - {"SHA256SUMS.txt"})

    unresolved: dict[str, list[str]] = {}
    repository_code: dict[str, list[str]] = {}
    checked = 0
    names = {p.name for p in root.rglob("*")}
    for report in REPORTS:
        text = (root / CLOSEOUT / report).read_text(encoding="utf-8")
        for token in PATH_TOKEN.findall(text):
            if not FILE_LIKE.search(token.rstrip(".,;:)")) or any(ch in token for ch in "<>*{}$…") and "round2" not in token:
                continue
            if any(ch in token for ch in "<>*{}$") or token.startswith(("http", "-", ".")):
                continue
            checked += 1
            where = _resolve(token, root, (root / CLOSEOUT / report).parent, names)
            if where == "missing":
                unresolved.setdefault(report, []).append(token)
            elif where == "repository_code":
                repository_code.setdefault(report, []).append(token)

    secrets = _secrets()
    secret_hits, pattern_hits = [], []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix in {".zip", ".png", ".gz"}:
            continue
        text = path.read_bytes().decode("utf-8", errors="replace")
        rel = path.relative_to(root).as_posix()
        if any(s in text for s in secrets):
            secret_hits.append(rel)
        clean = text
        for fake in FAKES:
            clean = clean.replace(fake, "")
        for name, rx in PATTERNS.items():
            if rx.search(clean):
                pattern_hits.append({"file": rel, "pattern": name})

    score_out = root.parent / f"{root.name}_reproduced_score.json"
    score_out.unlink(missing_ok=True)
    proc = subprocess.run([sys.executable, str(HERE / "run_with_network_trap.py"), str(REPO / D / "t3_joint_sample_driver.py"), "score",
                           "--predictions", str(root / E / "joint_predictions.jsonl"),
                           "--review-form", str(root / R25 / "D_human_review/review_form_v4_Xiang_Mao_HUMAN_REVIEWED.json"),
                           "--history", str(root / R25 / "B3_budget/historical_alpha_answers_COMPARISON_ONLY.json"), "--out", str(score_out)],
                          cwd=REPO, capture_output=True, text=True, check=False)
    reproduced = score_out.is_file() and score_out.read_bytes() == (root / R25 / "D_human_review/score_result_official.json").read_bytes()
    report = {"zip": args.zip, "zip_sha256": hashlib.sha256(Path(args.zip).read_bytes()).hexdigest(), "files_unpacked": len(unpacked),
              "sha256_mismatches": sha_mismatch, "files_not_listed": not_listed,
              "report_path_references_checked": checked, "unresolved_references": unresolved,
              "cited_repository_code_not_packaged": {k: sorted(set(v)) for k, v in repository_code.items()},
              "credential_scan": {"files_scanned": len(unpacked), "exact_env_secret_values_found_in": secret_hits, "pattern_hits": pattern_hits},
              "official_score_reproduced_byte_identical": reproduced, "score_command_tail": (proc.stdout + proc.stderr).strip().splitlines()[-2:],
              "ok": not sha_mismatch and not not_listed and not unresolved and not secret_hits and not pattern_hits and reproduced}
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
