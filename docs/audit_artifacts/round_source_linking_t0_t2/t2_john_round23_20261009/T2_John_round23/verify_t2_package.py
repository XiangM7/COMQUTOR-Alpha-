#!/usr/bin/env python3
"""T2 Round 23 (John version): in-package completeness and identity check.

Run from the unpacked package root (the folder that holds 00_先看这里.md):

    python3 verify_t2_package.py            # human-readable report
    python3 verify_t2_package.py --json     # the same result as JSON on stdout

Python 3.9+ standard library only. No network, no services, writes nothing. Exit code 0 = every check passed, 1 = at least one
check failed. It checks files, hashes and identities only; it does not run the acceptance engine, pytest or any research.

Checks
  1 manifest       every file in package_manifest.json exists with the recorded size and sha256; no unlisted files
  2 six_inputs     the six input runs of the Round 23 verdict file are present under 历史输入/outputs/runs/<run_id>/ with the
                   file list, per-file sha256 and directory digest of 历史输入/run_inventory.json; run_id/ticker agree across the
                   directory name, the run's metadata.json and the verdict file; AMD also matches the Round 22 hash record
  3 evidence       rule files, diff, effective_rules, per-item verdicts, tables and raw test logs are present; rule-file sha256 equal
                   what effective_rules.json and t2_files.json recorded (the frozen Gold baseline: t2_files.json only); the
                   patch sha256 equals t2_files.json
  4 reader_edits   the edited reader documents have the sha256 recorded in 核查记录/文档修改记录.json
  5 references     every file path quoted in the reader documents exists in the package, or is a repository path (listed, not
                   failed: those need the original repository)
  6 readme         README.md separates in-package checks from commands that need the original repository
  7 credentials    pattern scan of every file for API keys, bearer tokens, auth headers and database URLs with a password
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
R23 = "我方对应交付/round23_t2_completion_20261007"
IGNORED_NAMES = {".DS_Store"}
DIGEST_NOTE = 'sha256 of "\\n".join(f"{relative_path}\\t{sha256}") over the sorted files'
REQUIRED = [
    "00_先看这里.md", "README.md", "01_John对T2的要求.md", "02_签收标准.md",
    "规则文件/alpha_taxonomy_v1.yaml", "规则文件/j2_provisional_regression_labels_v0.2.yaml",
    "规则文件/j2_provisional_regression_labels_v0.1.yaml", "规则文件/v0_2_john_frozen_gold_baseline.yaml",
    f"{R23}/01_中文简明验收报告_T2.md", f"{R23}/README_T2.md",
    f"{R23}/t2_changes.patch", f"{R23}/t2_files.json",
    f"{R23}/six_ticker/effective_rules.json", f"{R23}/six_ticker/formal_acceptance_verdicts.json",
    f"{R23}/six_ticker/formal_acceptance_tables.md",
    f"{R23}/frozen_input_recompute/frozen_input_conflict_recompute.json", f"{R23}/open_review_ledger/open_review_ledger.json",
    f"{R23}/scenario_map.md",
    f"{R23}/test_evidence/full_suite_AFTER.junit.xml", f"{R23}/test_evidence/full_suite_AFTER.log",
    f"{R23}/test_evidence/full_suite_vs_baseline.json", f"{R23}/test_evidence/NEW_failure_attribution.md",
    f"{R23}/test_evidence/t2_fast_set_AFTER.junit.xml", f"{R23}/test_evidence/t2_fast_set_AFTER.log",
    f"{R23}/test_evidence/t2_core_BEFORE_this_round.junit.xml", f"{R23}/test_evidence/t2_core_BEFORE_this_round.log",
    f"{R23}/test_evidence/msft_replay_BEFORE_this_round.log",
    "历史输入/run_inventory.json", "历史输入/run_inventory.md",
    "核查记录/历史哈希/round22_run_directory_hashes_d5b60b8a.json", "核查记录/历史哈希/round22_release_manifest_v2_excerpt.json",
    "核查记录/文档修改记录.json",
]
READER_DOCS = [
    "00_先看这里.md", "README.md", "历史输入/run_inventory.md",
    f"{R23}/01_中文简明验收报告_T2.md", f"{R23}/README_T2.md", f"{R23}/test_evidence/README.md",
    f"{R23}/test_evidence/NEW_failure_attribution.md", f"{R23}/sample_production_artifact/README.md",
]
REPO_PREFIXES = ("comqutor_alpha/", "scripts/", "tests/", "docs/", "frontend/", "tradingagents/", "outputs/", ".venv")
FILE_EXT = re.compile(r"\.(md|json|jsonl|py|patch|ya?ml|xml|log|txt|zip|gz|csv|docx|pdf)$")
CRED_PATTERNS = {
    "api_key_sk": re.compile(rb"\b(sk-(?:ant-)?[A-Za-z0-9_\-]{20,})"),
    "bearer_token": re.compile(rb"Bearer\s+([A-Za-z0-9._\-]{16,})"),
    "db_url_with_password": re.compile(rb"\b(?:postgres(?:ql)?|mysql|mssql)(?:\+\w+)?://[^:/\s@\"']+:([^@\s\"']+)@"),
}
CRED_FIELD = re.compile(rb"[\"']?(authorization|x-api-key|api[_-]?key|proxy-authorization)[\"']?\s*[:=]\s*[\"']([^\"']*)[\"']", re.I)
REDACTED = re.compile(rb"^\W*(redacted|\*+|\[redacted\]|\*\*\*redacted\*\*\*|<redacted>|none|null)?\W*$", re.I)
# literal stand-ins used by the repository's tests (dummy DSNs, placeholder keys) and the self-test FAKES tuple of Round 23's own
# credential_scan.py; reported separately, not as hits
FIXTURE = {b"***REDACTED***", b"REDACTED", b"fake", b"p", b"pass", b"placeholder", b"sk-testsecret0123456789abcdef",
           b"replay-not-a-key", b"test-not-a-key", b"mock-not-a-key",
           b"sk-abcdefghijklmnopqrstuvwxyz012345", b"abcdefghijklmnopqrstuvwxyz0123456789ABC", b"should-never-be-saved-0123456789",
           b"hunter2hunter2"}
# files the reader documents name that belong to another delivery, not to this package
EXTERNAL_REFERENCES = {"round22_runs.tar.gz": "T1 delivery: t1/我方对应交付/运行产物打包/round22_runs.tar.gz (AMD was taken from it)"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_digest(per_file: dict) -> str:
    return hashlib.sha256("\n".join(f"{rel}\t{per_file[rel]}" for rel in sorted(per_file)).encode()).hexdigest()


def load(rel: str):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def package_files() -> list:
    out = []
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT).as_posix()
        if p.is_file() and p.name not in IGNORED_NAMES and "__MACOSX" not in p.parts and "__pycache__" not in p.parts:
            out.append(rel)
    return out


def check_manifest() -> dict:
    manifest = load("package_manifest.json")
    listed = {f["path"]: f for f in manifest["files"]}
    problems = []
    for rel, f in listed.items():
        p = ROOT / rel
        if not p.is_file():
            problems.append(f"missing: {rel}")
        elif p.stat().st_size != f["size"] or sha256_file(p) != f["sha256"]:
            problems.append(f"hash/size differs: {rel}")
    unlisted = [rel for rel in package_files() if rel not in listed and rel != "package_manifest.json"]
    problems += [f"not in manifest: {rel}" for rel in unlisted]
    return {"ok": not problems, "files_listed": len(listed), "problems": problems}


def check_six_inputs() -> dict:
    inv = load("历史输入/run_inventory.json")
    verdicts = load(f"{R23}/six_ticker/formal_acceptance_verdicts.json")
    r22 = load("核查记录/历史哈希/round22_run_directory_hashes_d5b60b8a.json")
    r22_excerpt = load("核查记录/历史哈希/round22_release_manifest_v2_excerpt.json")
    problems, rows = [], []
    if {r["run_id"] for r in inv["runs"]} != set(verdicts["inputs"]["runs"].values()):
        problems.append("inventory run set differs from the Round 23 verdict file inputs.runs")
    for r in inv["runs"]:
        ticker, run_id = r["ticker"], r["run_id"]
        d = ROOT / r["package_path"]
        row = {"ticker": ticker, "run_id": run_id, "path": r["package_path"], "located": d.is_dir()}
        if not d.is_dir():
            problems.append(f"{ticker}: directory not found at {r['package_path']}")
            rows.append(row)
            continue
        actual = {p.relative_to(d).as_posix(): sha256_file(p) for p in sorted(d.rglob("*")) if p.is_file() and p.name not in IGNORED_NAMES}
        expected = {f["path"]: f["sha256"] for f in r["files"]}
        row["files"] = len(actual)
        row["per_file_sha256_match"] = actual == expected
        row["digest"] = run_digest(actual)
        row["digest_match"] = row["digest"] == r["directory_digest_sha256"]
        if set(actual) != set(expected):
            problems.append(f"{ticker}: file set differs (missing {sorted(set(expected) - set(actual))}, extra {sorted(set(actual) - set(expected))})")
        elif not row["per_file_sha256_match"]:
            problems.append(f"{ticker}: per-file sha256 differs for {sorted(k for k in actual if actual[k] != expected[k])}")
        meta = json.loads((d / "metadata.json").read_text(encoding="utf-8"))
        v = verdicts["tickers"][ticker]
        row["identity_match"] = d.name == run_id == meta.get("run_id") == v["run_id"] == verdicts["inputs"]["runs"][ticker] and meta.get("ticker") == ticker == v["ticker"]
        if not row["identity_match"]:
            problems.append(f"{ticker}: run_id/ticker disagree across directory, metadata.json and the verdict file")
        if r["historical_hash"]["exists"]:
            same = sum(1 for rel, h in r22["files"].items() if actual.get(rel) == h)
            row["round22_per_file"] = f"{same}/{len(r22['files'])}"
            row["round22_digest_match"] = row["digest"] == r22_excerpt["amd_directory_entry"]["directory_digest_sha256"] and r22["run_id"] == run_id
            if not row["round22_digest_match"] or same != len(r22["files"]) or set(actual) != set(r22["files"]):
                problems.append(f"{ticker}: does not match the Round 22 hash record")
        else:
            row["round22_per_file"] = "no historical record (copy == current original only)"
        rows.append(row)
    return {"ok": not problems, "runs": rows, "problems": problems, "digest_algorithm": DIGEST_NOTE}


def check_evidence() -> dict:
    problems = [f"missing: {rel}" for rel in REQUIRED if not (ROOT / rel).is_file()]
    if problems:
        return {"ok": False, "problems": problems}
    eff = load(f"{R23}/six_ticker/effective_rules.json")
    files = load(f"{R23}/t2_files.json")
    pairs = {"taxonomy": "规则文件/alpha_taxonomy_v1.yaml", "label_v2": "规则文件/j2_provisional_regression_labels_v0.2.yaml",
             "label_v1": "规则文件/j2_provisional_regression_labels_v0.1.yaml"}
    rule_hashes = {}
    for key, rel in pairs.items():
        actual = sha256_file(ROOT / rel)
        rule_hashes[rel] = {"sha256": actual, "effective_rules_recorded": eff[key]["sha256"], "match": actual == eff[key]["sha256"]}
        if actual != eff[key]["sha256"]:
            problems.append(f"{rel}: sha256 differs from effective_rules.json {key}")
        in_diff = [f for f in files["files"] if f["path"] == eff[key]["path"]]
        if in_diff and in_diff[0]["sha256_working_tree"] != actual:
            problems.append(f"{rel}: sha256 differs from t2_files.json")
    baseline_rel, baseline_repo = "规则文件/v0_2_john_frozen_gold_baseline.yaml", "docs/audit_artifacts/v0_2_john_frozen_gold_baseline.yaml"
    recorded = [f["sha256_working_tree"] for f in files["files"] if f["path"] == baseline_repo]
    actual = sha256_file(ROOT / baseline_rel)
    rule_hashes[baseline_rel] = {"sha256": actual, "t2_files_recorded": recorded[0] if recorded else None, "match": bool(recorded) and actual == recorded[0]}
    if not rule_hashes[baseline_rel]["match"]:
        problems.append(f"{baseline_rel}: sha256 differs from t2_files.json {baseline_repo}")
    patch_sha = sha256_file(ROOT / R23 / "t2_changes.patch")
    if patch_sha != files["patch_sha256"]:
        problems.append("t2_changes.patch sha256 differs from t2_files.json patch_sha256")
    junit = sorted(p.name for p in (ROOT / R23 / "test_evidence").glob("*.junit.xml"))
    logs = sorted(p.name for p in (ROOT / R23 / "test_evidence").glob("*.log"))
    return {"ok": not problems, "required_present": len(REQUIRED), "rule_files": rule_hashes, "patch_sha256": patch_sha,
            "patch_files": len(files["files"]), "raw_test_junit": junit, "raw_test_logs": logs, "problems": problems}


def check_reader_edits() -> dict:
    doc = load("核查记录/文档修改记录.json")
    problems = []
    for e in doc["edited_documents"]:
        if sha256_file(ROOT / e["package_path"]) != e["new_sha256"]:
            problems.append(f"{e['package_path']}: sha256 differs from 文档修改记录.json")
    return {"ok": not problems, "edited": [e["package_path"] for e in doc["edited_documents"]], "problems": problems}


def check_references() -> dict:
    diff_paths = [f["path"] for f in load(f"{R23}/t2_files.json")["files"]]
    basenames = {}
    for rel in package_files():
        basenames.setdefault(rel.rsplit("/", 1)[-1], []).append(rel)
    found, repo_in_diff, repo_only, external, missing = 0, set(), set(), {}, []
    for doc in READER_DOCS:
        doc_dir = (ROOT / doc).parent
        text = (ROOT / doc).read_text(encoding="utf-8")
        for token in re.findall(r"`([^`\n]+)`", text):
            t = token.strip().rstrip("/")
            if not t or any(c in t for c in " =*<>$(){}|,") or "::" in t or t.startswith(("/", "-", ".", "~", "http")):
                continue
            if "/" not in t and not FILE_EXT.search(t):
                continue
            bases = [doc_dir, ROOT, ROOT / R23, ROOT / "历史输入"]
            if any((b / t).exists() for b in bases):
                found += 1
            elif t.startswith("outputs/runs/") and (ROOT / "历史输入" / t).exists():
                found += 1
            elif "/" not in t and t in basenames:
                found += 1
            elif t in EXTERNAL_REFERENCES:
                external[t] = EXTERNAL_REFERENCES[t]
            elif t.startswith(REPO_PREFIXES) or any(p == t or p.endswith("/" + t) for p in diff_paths):
                (repo_in_diff if any(p == t or p.endswith("/" + t) for p in diff_paths) else repo_only).add(t)
            else:
                missing.append(f"{doc}: `{token}`")
    return {"ok": not missing, "package_references_found": found, "missing_in_package": missing,
            "references_to_other_deliveries": external,
            "repository_paths_whose_content_is_in_t2_changes_patch": sorted(repo_in_diff),
            "repository_only_paths_not_in_package": sorted(repo_only)}


def check_readme() -> dict:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    need = ["## 1. 只用本包即可执行", "## 2. 需要原仓库环境"]
    missing = [h for h in need if h not in text]
    return {"ok": not missing, "sections": need, "problems": [f"README.md lacks section {h}" for h in missing]}


def check_credentials() -> dict:
    hits, fixtures, scanned = [], {}, 0
    for rel in package_files():
        data = (ROOT / rel).read_bytes()
        scanned += 1
        for label, pattern in CRED_PATTERNS.items():
            for m in pattern.finditer(data):
                if m.group(1) in FIXTURE:
                    fixtures[label] = fixtures.get(label, 0) + 1
                else:
                    hits.append({"file": rel, "kind": label, "offset": m.start()})
        for m in CRED_FIELD.finditer(data):
            if REDACTED.match(m.group(2)) or m.group(2) in FIXTURE:
                fixtures["redacted_or_empty_field"] = fixtures.get("redacted_or_empty_field", 0) + 1
            else:
                hits.append({"file": rel, "kind": "field:" + m.group(1).decode().lower(), "offset": m.start()})
    return {"ok": not hits, "files_scanned": scanned, "hits": hits, "fixture_or_redacted_matches": fixtures}


CHECKS = [("1 manifest", check_manifest), ("2 six_inputs", check_six_inputs), ("3 evidence", check_evidence),
          ("4 reader_edits", check_reader_edits), ("5 references", check_references), ("6 readme", check_readme),
          ("7 credentials", check_credentials)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    results = {}
    for name, fn in CHECKS:
        try:
            results[name] = fn()
        except Exception as exc:  # a broken or missing input file is a failed check, not a crash
            results[name] = {"ok": False, "problems": [f"{type(exc).__name__}: {exc}"]}
    all_ok = all(r["ok"] for r in results.values())
    if args.json:
        print(json.dumps({"package_root": ROOT.name, "all_ok": all_ok, "checks": results}, ensure_ascii=False, indent=1))
        return 0 if all_ok else 1
    print(f"package: {ROOT.name}")
    for name, r in results.items():
        print(f"[{'PASS' if r['ok'] else 'FAIL'}] {name}")
        if name == "1 manifest":
            print(f"    files listed: {r.get('files_listed')}")
        if name == "2 six_inputs":
            for row in r.get("runs", []):
                print(f"    {row['ticker']:<5} {row['run_id']}  located={row['located']} files={row.get('files')} "
                      f"sha256={row.get('per_file_sha256_match')} digest={row.get('digest_match')} identity={row.get('identity_match')} "
                      f"round22={row.get('round22_per_file')}")
        if name == "3 evidence" and r["ok"]:
            for rel, h in r["rule_files"].items():
                print(f"    {rel}: {h['sha256'][:16]}… {'effective_rules' if 'effective_rules_recorded' in h else 't2_files.json'} match={h['match']}")
            print(f"    t2_changes.patch {r['patch_sha256'][:16]}… ({r['patch_files']} files); raw test files: {len(r['raw_test_junit'])} junit + {len(r['raw_test_logs'])} log")
        if name == "5 references":
            print(f"    package files referenced and present: {r.get('package_references_found')}; "
                  f"repository paths (content in t2_changes.patch): {len(r.get('repository_paths_whose_content_is_in_t2_changes_patch', []))}; "
                  f"repository-only paths (need the original repository): {r.get('repository_only_paths_not_in_package')}; "
                  f"other deliveries: {r.get('references_to_other_deliveries')}")
        if name == "7 credentials":
            print(f"    files scanned: {r.get('files_scanned')}; hits: {len(r.get('hits', []))}; fixture/redacted matches: {r.get('fixture_or_redacted_matches')}")
        for p in r.get("problems", []) + r.get("missing_in_package", []):
            print(f"    problem: {p}")
        for h in r.get("hits", [])[:20]:
            print(f"    hit: {h}")
    print("ALL CHECKS PASSED" if all_ok else "SOME CHECKS FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
