#!/usr/bin/env python3
"""T4 D1 fix (Round 34, 2026-10-09): in-package check of the D1 supplement. Run from the unpacked folder that holds
00_D1修复附录.md:

    python3 verify_d1_fix.py           # PASS / FAIL per check, exit 0 only if all pass
    python3 verify_d1_fix.py --json

Python 3.9+ standard library only. No repository, API key, database or network; writes nothing.

  1 manifest     every file in manifest.json present with its size and sha256; no unlisted file
  2 prompts      the v1 and v2 prompt identities recompute from the saved instruction texts, match the replay registry, and
                 v1 equals the identity both Fresh runs recorded
  3 replies      before the fix: the two saved replies (unchanged) were rejected for the missing field on the run's own
                 request; after: still rejected (they lack the field) while the request carries the v2 prompt; batch sizes
  4 tests        the D1 test group passed with 0 failures / errors, 0 blocked network attempts, code unchanged during the
                 run and equal to the recorded final code; the integrity-pin test failed before and after on the same node
  5 diff         the diff file's sha256 matches changed_files.json and it changes exactly the listed files
  6 references   every file path quoted in the appendix / README exists in this folder (repository paths listed, not failed)
  7 credentials  API-key / bearer / auth-field / password-URL pattern scan of every file
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PKG = Path(__file__).resolve().parent
V1_RECORDED = "c6822099e2171c6fbad72c36bf2881bcd59bd4d4ad2fc20e10ab62af50b5bfd9"
FIELD_SET_MESSAGE = "enrichment item fields do not match the strict schema"
EXPECTED_CHANGED = {
    "comqutor_alpha/structure_engine/week2_llm.py", "comqutor_alpha/structure_engine/structured_output_adapter.py",
    "comqutor_alpha/replay/source_bundle.py", "docs/specs/week2_semantic_runtime_integration_contract_v1.md",
    "tests/test_t1_source_linking_pipeline.py", "tests/test_t4_round34_d1_adapter_citation_contract.py",
}
DOCS = ["00_D1修复附录.md", "README.md", "04_production_entry/生产入口证明.md", "05_hash_proof/README.md"]
REPO_PREFIXES = ("comqutor_alpha/", "scripts/", "tests/", "docs/", "frontend/", "tradingagents/", "outputs/", ".venv")
FILE_EXT = re.compile(r"\.(md|json|jsonl|py|sh|diff|xml|log|txt|zip)$")
CRED = {
    "api_key_sk": re.compile(rb"\b(sk-(?:ant-)?[A-Za-z0-9_\-]{20,})"),
    "bearer_token": re.compile(rb"Bearer\s+([A-Za-z0-9._\-]{16,})"),
    "db_url_with_password": re.compile(rb"\b(?:postgres(?:ql)?|mysql|mssql)(?:\+\w+)?://[^:/\s@\"']+:([^@\s\"']+)@"),
}
CRED_FIELD = re.compile(rb"[\"']?(authorization|x-api-key|api[_-]?key|proxy-authorization)[\"']?\s*[:=]\s*[\"']([^\"']*)[\"']", re.I)
REDACTED = re.compile(rb"^\W*(redacted|\*+|\[redacted\]|\*\*\*redacted\*\*\*|<redacted>|none|null)?\W*$", re.I)
# literal stand-ins of the repository's tests / zero-call replays, plus the self-test fakes of Round 23's credential scanner
# (listed in tools/scan_credentials.py and therefore named in credential_scan_result.json); fixtures, never hits
FIXTURE = {b"***REDACTED***", b"REDACTED", b"fake", b"p", b"pass", b"placeholder", b"sk-testsecret0123456789abcdef",
           b"replay-not-a-key", b"test-not-a-key", b"mock-not-a-key",
           b"sk-abcdefghijklmnopqrstuvwxyz012345", b"abcdefghijklmnopqrstuvwxyz0123456789ABC", b"should-never-be-saved-0123456789",
           b"hunter2hunter2"}
# files the documents name that belong to another delivery
EXTERNAL_REFERENCES = {"T4_final_round33_20261009.zip": "the T4 final delivery (Round 33), unchanged; this folder supplements it"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(rel: str):
    return json.loads((PKG / rel).read_text(encoding="utf-8"))


def files() -> list:
    return sorted(p.relative_to(PKG).as_posix() for p in PKG.rglob("*") if p.is_file() and p.name != ".DS_Store" and "__pycache__" not in p.parts)


def check_manifest() -> dict:
    listed = {f["path"]: f for f in load("manifest.json")["files"]}
    problems = [f"missing or differs: {rel}" for rel, f in listed.items()
                if not (PKG / rel).is_file() or (PKG / rel).stat().st_size != f["size"] or sha((PKG / rel).read_bytes()) != f["sha256"]]
    problems += [f"not in manifest: {rel}" for rel in files() if rel not in listed and rel != "manifest.json"]
    return {"ok": not problems, "files": len(listed), "problems": problems}


def check_prompts() -> dict:
    p = load("02_code/prompt_versions.json")
    problems = []
    for key in ("v1_retired", "v2_live"):
        text = p["identity_prefix"] + p[key]["instruction"] + p["identity_separator"]
        if sha(text.encode("utf-8")) != p[key]["prompt_sha256"] or p[key]["prompt_sha256"] != p[key]["prompt_sha256_via_gateway"]:
            problems.append(f"{key}: identity does not recompute from its instruction text")
    if p["v1_retired"]["prompt_sha256"] != V1_RECORDED:
        problems.append("v1 identity differs from the one both Fresh runs recorded")
    registry = {i["prompt_version"]: i["prompt_sha256"] for i in p["replay_registry_structured_adapter"]}
    if registry != {p["v1_retired"]["prompt_version"]: p["v1_retired"]["prompt_sha256"], p["v2_live"]["prompt_version"]: p["v2_live"]["prompt_sha256"]}:
        problems.append("replay registry does not list exactly v1 and v2 with these identities")
    if "cited_source_id" in p["v1_retired"]["instruction"] or "cited_source_id" not in p["v2_live"]["instruction"]:
        problems.append("v1 should not and v2 should ask for cited_source_id")
    return {"ok": not problems, "v1": p["v1_retired"]["prompt_sha256"], "v2": p["v2_live"]["prompt_sha256"], "problems": problems}


def check_replies() -> dict:
    before, after = load("01_before_after/before.json"), load("01_before_after/after.json")
    problems = []
    for label, doc, version, same_request in (("before", before, "week2.claim_batch_enrichment.v1", True), ("after", after, "week2.claim_batch_enrichment.v2", False)):
        if len(doc["saved_replies"]) != 2:
            problems.append(f"{label}: expected the two saved replies")
        for r in doc["saved_replies"]:
            if not r["reply_body_sha256_unchanged"] or "cited_source_id" in r["reply_item_fields"]:
                problems.append(f"{label}: seq {r['call_sequence']} reply changed or carries the field")
            if r["ledger_prompt_version"] != version or r["request_body_equals_the_run's_saved_request"] is not same_request:
                problems.append(f"{label}: seq {r['call_sequence']} prompt version / request identity unexpected")
            if r["outcome"]["enrichment_returned"] or r["outcome"]["validation_status"] != "rejected" or r["production_validator_message"] != FIELD_SET_MESSAGE:
                problems.append(f"{label}: seq {r['call_sequence']} not rejected for the missing field")
        log = (PKG / f"01_before_after/{label}_log.txt").read_text(encoding="utf-8")
        if "network attempts: 0" not in log or "[exit 0]" not in log:
            problems.append(f"{label}_log.txt lacks 'network attempts: 0' / '[exit 0]'")
    refused_change = [b["call_sequence"] for b, a in zip(before["batch_sizes"], after["batch_sizes"]) if b["refused_locally_this_code"] != a["refused_locally_this_code"]]
    if refused_change:
        problems.append(f"the size limit outcome changed for batches {refused_change}")
    deltas = {b["call_sequence"]: a["input_chars_this_code"] - b["input_chars_this_code"] for b, a in zip(before["batch_sizes"], after["batch_sizes"])}
    return {"ok": not problems, "batch_size_deltas_chars": deltas, "problems": problems}


def _junit(rel: str) -> dict:
    root = ET.parse(PKG / rel).getroot()
    suites = [root] if root.tag == "testsuite" else list(root)
    totals = {k: sum(int(s.get(k, 0)) for s in suites) for k in ("tests", "failures", "errors", "skipped")}
    totals["failed_nodes"] = sorted(f"{tc.get('classname')}::{tc.get('name')}" for s in suites for tc in s.iter("testcase")
                                    if tc.find("failure") is not None or tc.find("error") is not None)
    return totals


def check_tests() -> dict:
    problems = []
    d1 = _junit("03_tests/d1_junit.xml")
    cmd = (PKG / "03_tests/d1_command.txt").read_text(encoding="utf-8")
    final = load("02_code/changed_files.json")["code_identity_after"]
    if d1["failures"] or d1["errors"]:
        problems.append(f"d1 group failures/errors: {d1['failed_nodes']}")
    if "exit_code: 0" not in cmd or "code_unchanged_during_group: yes" not in cmd:
        problems.append("d1 command record lacks exit_code 0 / code unchanged")
    if f"{final['tracked_diff_sha256']} {final['untracked_runtime_source_sha256']}" not in cmd:
        problems.append("d1 group did not run on the recorded final code")
    if load("03_tests/d1_net_trap.json")["blocked_attempts"] != 0:
        problems.append("d1 group attempted an outbound connection")
    pin = _junit("03_tests/pin_junit.xml")
    before_log = (PKG / "03_tests/source_integrity_pin_BEFORE.log").read_text(encoding="utf-8")
    pin_node = "test_current_semantic_components_match_approved_phase1_master_baseline"
    if not (len(pin["failed_nodes"]) == 1 and pin_node in pin["failed_nodes"][0] and pin_node in before_log and "1 failed, 3 passed" in before_log):
        problems.append("integrity-pin status differs from 'the same single node failing before and after'")
    return {"ok": not problems, "d1": {k: d1[k] for k in ("tests", "failures", "errors", "skipped")}, "pin_failed_nodes": pin["failed_nodes"], "problems": problems}


def check_diff() -> dict:
    record = load("02_code/changed_files.json")
    diff = (PKG / "02_code/round34_d1_changes.diff").read_bytes()
    problems = []
    if sha(diff) != record["diff_sha256"]:
        problems.append("diff sha256 differs from changed_files.json")
    changed = {f["path"] for f in record["files"] if f["changed"]}
    if changed != EXPECTED_CHANGED:
        problems.append(f"changed files differ: {sorted(changed ^ EXPECTED_CHANGED)}")
    in_diff = set(re.findall(r"^\+\+\+ b/(\S+)", diff.decode("utf-8"), re.M))
    if in_diff != changed:
        problems.append(f"diff headers differ from the changed-file list: {sorted(in_diff ^ changed)}")
    return {"ok": not problems, "changed_files": sorted(changed), "problems": problems}


def check_references() -> dict:
    present = set(files())
    basenames = {f.rsplit("/", 1)[-1] for f in present}
    found, repo, missing = 0, set(), []
    for doc in DOCS:
        doc_dir = (PKG / doc).parent
        for token in re.findall(r"`([^`\n]+)`", (PKG / doc).read_text(encoding="utf-8")):
            t = token.strip().rstrip("/")
            if not t or any(c in t for c in " =*<>$(){}|,…") or "::" in t or t.startswith(("/", "-", ".", "~", "http")):
                continue
            if "/" not in t and not FILE_EXT.search(t):
                continue
            if any((b / t).exists() for b in (doc_dir, PKG)) or ("/" not in t and t in basenames):
                found += 1
            elif t in EXTERNAL_REFERENCES:
                repo.add(f"{t} (other delivery)")
            elif t.startswith(REPO_PREFIXES) or re.match(r"round\d+_", t) or ("/" not in t and t.endswith(".py")):
                repo.add(t)
            else:
                missing.append(f"{doc}: `{token}`")
    readme = (PKG / "README.md").read_text(encoding="utf-8")
    if "/Users/" in readme:
        missing.append("README contains an absolute user path")
    return {"ok": not missing, "found": found, "repository_paths": sorted(repo), "missing": missing}


def check_credentials() -> dict:
    hits, scanned = [], 0
    for rel in files():
        data = (PKG / rel).read_bytes()
        scanned += 1
        for label, pattern in CRED.items():
            hits += [{"file": rel, "kind": label} for m in pattern.finditer(data) if m.group(1) not in FIXTURE]
        hits += [{"file": rel, "kind": "field"} for m in CRED_FIELD.finditer(data) if not (REDACTED.match(m.group(2)) or m.group(2) in FIXTURE)]
    return {"ok": not hits, "files_scanned": scanned, "hits": hits}


CHECKS = [("1 manifest", check_manifest), ("2 prompts", check_prompts), ("3 replies", check_replies), ("4 tests", check_tests),
          ("5 diff", check_diff), ("6 references", check_references), ("7 credentials", check_credentials)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    results = {}
    for name, fn in CHECKS:
        try:
            results[name] = fn()
        except Exception as exc:
            results[name] = {"ok": False, "problems": [f"{type(exc).__name__}: {exc}"]}
    ok = all(r["ok"] for r in results.values())
    if args.json:
        print(json.dumps({"all_ok": ok, "checks": results}, ensure_ascii=False, indent=1))
        return 0 if ok else 1
    for name, r in results.items():
        print(f"[{'PASS' if r['ok'] else 'FAIL'}] {name}")
        info = {k: v for k, v in r.items() if k not in ("ok", "problems", "missing", "hits")}
        if info:
            print("    " + json.dumps(info, ensure_ascii=False))
        for p in (r.get("problems") or []) + (r.get("missing") or []) + [json.dumps(h) for h in (r.get("hits") or [])[:20]]:
            print(f"    problem: {p}")
    print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
