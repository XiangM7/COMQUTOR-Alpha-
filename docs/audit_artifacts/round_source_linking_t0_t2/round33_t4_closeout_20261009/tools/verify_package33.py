#!/usr/bin/env python3
"""T4 final delivery, Round 33 (2026-10-09): in-package check. Run from the unpacked package root (the folder that holds
00_T4最终交付报告.md):

    python3 verify_package33.py            # PASS / FAIL per check, exit 0 only if all pass
    python3 verify_package33.py --json     # the same result as JSON

Python 3.11+ standard library only. No repository, API key, database or network; writes nothing.

  1 manifest    every file in manifest.json present with its size and sha256; no unlisted file
  2 round32     every file of the Round 32 package manifest (round32/manifest.json) is byte-identical in round32/, or is one of
                the edited reader documents (sha256 as recorded in round33/records/文档修改记录.json), or one of the superseded
                files that were deliberately not copied; no other file in round32/
  3 figures     every figure in report_figures.json is rebuilt offline -- Round 32 figures with the rebuild() of
                round32/tools/rebuild_stats32.py over round32/'s own files, Round 33 figures from round33/'s result files --
                equals the recorded value, and is cited verbatim in the report
  4 round33     the three items' conclusions hold on their raw results (D1 per-batch outcomes and network-trap counts; the
                not-sent ledger balance and per-request rows; the viewer's code identity, Export sha256, disclosure, 0 blocked)
  5 references  every file path quoted in the reader documents of this version exists in the package (or inside the nested
                Round 31 ZIP's run directories); repository paths are listed, not failed; README commands name existing scripts
  6 credentials API-key / bearer / auth-field / password-URL pattern scan of every file, including members of nested ZIPs
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True  # importing round32/tools/rebuild_stats32.py must not write a __pycache__ into the package
PKG = Path(__file__).resolve().parent
R32 = PKG / "round32"
R33 = PKG / "round33"
REPORT = "00_T4最终交付报告.md"
FRESH2 = "12591384-0b26-470d-a99d-a49c00be440b"
ROUND31_ZIP = R32 / "references" / "T4_delivery_round31_20261009.zip"
IGNORED = {".DS_Store"}
READER_DOCS = [REPORT, "README.md", "round33/01_d1/D1_离线定位.md", "round33/02_viewer/查看入口核对.md",
               "round33/03_not_sent_reconcile/对账.md"]
REPO_PREFIXES = ("comqutor_alpha/", "scripts/", "tests/", "docs/", "frontend/", "tradingagents/", "outputs/", ".venv")
FILE_EXT = re.compile(r"\.(md|json|jsonl|py|mjs|sh|patch|diff|ya?ml|xml|log|txt|zip|gz|csv|png|mp4)$")
CRED = {
    "api_key_sk": re.compile(rb"\b(sk-(?:ant-)?[A-Za-z0-9_\-]{20,})"),
    "bearer_token": re.compile(rb"Bearer\s+([A-Za-z0-9._\-]{16,})"),
    "db_url_with_password": re.compile(rb"\b(?:postgres(?:ql)?|mysql|mssql)(?:\+\w+)?://[^:/\s@\"']+:([^@\s\"']+)@"),
}
CRED_FIELD = re.compile(rb"[\"']?(authorization|x-api-key|api[_-]?key|proxy-authorization)[\"']?\s*[:=]\s*[\"']([^\"']*)[\"']", re.I)
REDACTED = re.compile(rb"^\W*(redacted|\*+|\[redacted\]|\*\*\*redacted\*\*\*|<redacted>|none|null)?\W*$", re.I)
# literal stand-ins used by the repository's tests and the zero-call replays (same list as round32/tools/scan_credentials.py),
# plus the self-test fakes of Round 23's credential scanner; reported as fixtures, never as hits
FIXTURE = {b"***REDACTED***", b"REDACTED", b"fake", b"p", b"pass", b"placeholder", b"sk-testsecret0123456789abcdef",
           b"replay-not-a-key", b"test-not-a-key", b"mock-not-a-key",
           b"sk-abcdefghijklmnopqrstuvwxyz012345", b"abcdefghijklmnopqrstuvwxyz0123456789ABC", b"should-never-be-saved-0123456789",
           b"hunter2hunter2"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def files_under(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*")
                  if p.is_file() and p.name not in IGNORED and "__pycache__" not in p.parts and "__MACOSX" not in p.parts)


def check_manifest() -> dict:
    m = load(PKG / "manifest.json")
    listed = {f["path"]: f for f in m["files"]}
    problems = []
    for rel, f in listed.items():
        p = PKG / rel
        if not p.is_file():
            problems.append(f"missing: {rel}")
        elif p.stat().st_size != f["size"] or sha(p.read_bytes()) != f["sha256"]:
            problems.append(f"differs: {rel}")
    problems += [f"not in manifest: {rel}" for rel in files_under(PKG) if rel not in listed and rel != "manifest.json"]
    return {"ok": not problems, "files": len(listed), "problems": problems}


def check_round32() -> dict:
    original = {f["path"]: f["sha256"] for f in load(R32 / "manifest.json")["files"]}
    log = load(R33 / "records" / "文档修改记录.json")
    edited = {e["round32_path"]: e for e in log["edited_documents"]}
    superseded = {s["round32_path"]: s for s in log["superseded_not_copied"]}
    problems, identical = [], 0
    for rel, digest in original.items():
        p = R32 / rel
        if rel in superseded:
            if p.exists():
                problems.append(f"superseded file is present: {rel}")
            if superseded[rel]["original_sha256"] != digest:
                problems.append(f"superseded record sha differs from the Round 32 manifest: {rel}")
        elif rel in edited:
            if edited[rel]["original_sha256"] != digest:
                problems.append(f"edit record original sha differs from the Round 32 manifest: {rel}")
            if not p.is_file() or sha(p.read_bytes()) != edited[rel]["new_sha256"]:
                problems.append(f"edited file differs from its recorded new sha256: {rel}")
        elif not p.is_file():
            problems.append(f"missing: round32/{rel}")
        elif sha(p.read_bytes()) != digest:
            problems.append(f"differs from Round 32: round32/{rel}")
        else:
            identical += 1
    extra = [rel for rel in files_under(R32) if rel not in original and rel != "manifest.json"]
    problems += [f"not in the Round 32 manifest: round32/{rel}" for rel in extra]
    return {"ok": not problems, "round32_manifest_files": len(original), "byte_identical": identical,
            "edited": sorted(edited), "superseded_not_copied": sorted(superseded), "problems": problems}


def _rebuild_round32() -> dict:
    spec = importlib.util.spec_from_file_location("rebuild_stats32", R32 / "tools" / "rebuild_stats32.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # its PKG is round32/ (the parent of its tools/ folder)
    return module.rebuild()


def r33_figures() -> dict:
    d1 = load(R33 / "01_d1" / "d1_fresh2.json")
    d1b = load(R33 / "01_d1" / "d1_fresh1_supplementary.json")
    calls = {c["call_sequence"]: c for c in d1["calls"]}
    rec = load(R33 / "03_not_sent_reconcile" / "reconcile.json")
    view = load(R33 / "02_viewer" / "check" / "viewer_check_result.json")
    out = {
        "r33.d1.fresh2.timeouts": d1["send_status_counts"].get("sent_timeout_no_reply", 0) + d1["send_status_counts"].get("sent_timeout_reply_arrived_after_deadline", 0),
        "r33.d1.fresh2.not_sent_chars": next(c["input_chars"] for c in d1["calls"] if c["send_status"] == "not_sent_local_refusal"),
        "r33.d1.fresh2.rejected_in_time_segments": next(c["segments"] for c in d1["calls"] if c["send_status"] == "sent_reply_received_in_time"),
        "r33.d1.fresh2.control_in_time": f'{calls[8]["diagnostic_control"]["items_accepted_with_null_citation"]}/{calls[8]["reply"]["items"]}',
        "r33.d1.fresh2.control_late": f'{calls[1]["diagnostic_control"]["items_accepted_with_null_citation"]}/{calls[1]["reply"]["items"]}',
        "r33.d1.fresh2.requests_identical": all(c["production_path"]["request_body_equals_saved_wire_body"] for c in d1["calls"] if c.get("reply")),
        "r33.d1.fresh1.replies_whole_pass_with_null": sum(1 for c in d1b["calls"] if c.get("diagnostic_control", {}).get("whole_batch", {}).get("accepted")),
        "r33.d1.fresh1.replies_still_rejected": sum(1 for c in d1b["calls"] if c.get("reply") and not c["diagnostic_control"]["whole_batch"]["accepted"]),
        "r33.d1.network_attempts": sum(int(m) for log in ("run_log_fresh2.txt", "run_log_fresh1_supplementary.txt")
                                       for m in re.findall(r"network attempts: (\d+)", (R33 / "01_d1" / log).read_text(encoding="utf-8"))),
        "r33.reconcile.ledger": rec["send_ledger"]["ledger_records"],
        "r33.reconcile.sent": rec["send_ledger"]["sent_with_http_attempt"],
        "r33.reconcile.cache_hits": rec["send_ledger"]["same_run_cache_hits_not_sent"],
        "r33.reconcile.refused": rec["send_ledger"]["refused_locally_input_too_large"],
        "r33.reconcile.budget": rec["send_ledger"]["gateway_budget_reservations"],
        "r33.reconcile.replies": rec["send_ledger"]["wire_audit_reply_rows"],
        "r33.reconcile.malformed_labels": rec["facts"]["claim_labels_malformed_saved"],
        "r33.reconcile.real_malformed": rec["facts"]["real_malformed_replies"],
        "r33.reconcile.consistent_statements": sum(1 for s in rec["statements"] if s["consistent_with_records"]),
        "r33.viewer.export_sha256": view["export_sha256"],
        "r33.viewer.blocked": len(view["safety"]["blocked_requests"]),
        "r33.viewer.api_gets": len(view["safety"]["api_gets"]),
    }
    out.update({f"r33.reconcile.row.{r['call_sequence']}": r["input_chars"] for r in rec["refused_requests"]})
    return out


def check_figures() -> dict:
    figures = load(PKG / "report_figures.json")
    report = (PKG / REPORT).read_text(encoding="utf-8")
    rebuilt = {**_rebuild_round32(), **r33_figures()}
    bad = []
    for fig in figures["figures"]:
        got = rebuilt.get(fig["id"], "<not rebuilt>")
        if got != fig["value"] or fig["cited_as"] not in report:
            bad.append({"id": fig["id"], "recorded": fig["value"], "rebuilt": got, "cited": fig["cited_as"] in report})
    return {"ok": not bad, "figures": len(figures["figures"]), "from_round32": sum(1 for f in figures["figures"] if not f["id"].startswith("r33.")),
            "from_round33": sum(1 for f in figures["figures"] if f["id"].startswith("r33.")), "failing": bad}


def check_round33() -> dict:
    problems = []
    d1 = load(R33 / "01_d1" / "d1_fresh2.json")
    if dict(d1["send_status_counts"]) != {"sent_timeout_no_reply": 6, "sent_timeout_reply_arrived_after_deadline": 1, "not_sent_local_refusal": 1, "sent_reply_received_in_time": 1}:
        problems.append("D1: unexpected send status counts")
    for c in d1["calls"]:
        if c.get("reply"):
            if c["production_validator_on_saved_reply"]["message"] != "enrichment item fields do not match the strict schema":
                problems.append(f"D1: seq {c['call_sequence']} validator message differs")
            if any(fs["missing_vs_validator"] != ["cited_source_id"] or fs["extra_vs_validator"] for fs in c["reply"]["item_field_sets"]):
                problems.append(f"D1: seq {c['call_sequence']} reply fields are not 'exactly the 8 instructed fields'")
            if not c["diagnostic_control"]["whole_batch"]["accepted"]:
                problems.append(f"D1: seq {c['call_sequence']} control does not pass")
            if c["production_path"]["enrichment_returned"] or c["production_path"]["ledger_record"]["fallback_reason"] != "WEEK2_LLM_VALIDATION_FAILED":
                problems.append(f"D1: seq {c['call_sequence']} production path outcome differs from the run")
        if c["send_status"] == "not_sent_local_refusal" and c["production_path"]["transport_arrivals"] != 0:
            problems.append("D1: the oversized batch reached the transport")
    for log in ("run_log_fresh2.txt", "run_log_fresh1_supplementary.txt"):
        text = (R33 / "01_d1" / log).read_text(encoding="utf-8")
        if "network attempts: 0" not in text or "[exit 0]" not in text:
            problems.append(f"D1: {log} lacks 'network attempts: 0' / '[exit 0]'")
    rec = load(R33 / "03_not_sent_reconcile" / "reconcile.json")
    if not rec["send_ledger"]["balances"]:
        problems.append("reconcile: the ledger does not balance")
    f = rec["facts"]
    if (f["refused"], f["refused_cs"], f["refused_adapter"], f["refused_labelled_malformed"], f["corrected_to_input_too_large"], f["final_ledger_messages"]) != (6, 5, 1, 5, 5, 6):
        problems.append("reconcile: 6/5/1/5/5/6 does not hold")
    if [s["quote"] for s in rec["statements"] if not s["consistent_with_records"]] != ["6 个请求输入超限，且被标成 `malformed_response`"]:
        problems.append("reconcile: the set of inconsistent statements changed")
    if not all(s["quote_found_verbatim"] for s in rec["statements"]):
        problems.append("reconcile: a quoted statement was not found verbatim")
    # every quoted statement is also found verbatim in the copy this package carries
    with zipfile.ZipFile(ROUND31_ZIP) as z:
        def member(name):
            for info in z.infolist():
                if (info.filename if info.flag_bits & 0x800 else info.filename.encode("cp437").decode("utf-8")) == name:
                    return z.read(info).decode("utf-8")
            return ""
        copies = {"round30_t4_nvda_fresh_run2_20261009/FRESH_RUN2_REPORT.md": member("T4_delivery/run_records/run2_12591384/original_round30_FRESH_RUN2_REPORT.md"),
                  "round31_t4_delivery_20261009/T4_delivery/00_T4交付主报告.md": member("T4_delivery/00_T4交付主报告.md")}
    for s in rec["statements"]:
        if s["file"] in copies:
            text = copies[s["file"]]
        elif s["file"] == "round32_t4_closure_20261009/T4_final/00_T4最终交付报告.md":
            text = (PKG / REPORT).read_text(encoding="utf-8")  # superseded; its quoted sentences are carried into this report
        else:
            text = (R32 / s["file"].split("T4_final/", 1)[1]).read_text(encoding="utf-8")
        if s["quote"] not in text:
            problems.append(f"reconcile: quote not found in the package copy of {s['file']}: {s['quote']}")
    text = (R33 / "03_not_sent_reconcile" / "run_log.txt").read_text(encoding="utf-8")
    if "network attempts: 0" not in text or "[exit 0]" not in text:
        problems.append("reconcile: run_log.txt lacks 'network attempts: 0' / '[exit 0]'")
    view = load(R33 / "02_viewer" / "check" / "viewer_check_result.json")
    final = load(R32 / "02_code" / "final_code_identity.json")
    final_pair = (final.get("tracked_diff_sha256") or final.get("code_identity", {}).get("tracked_diff_sha256"),
                  final.get("untracked_runtime_source_sha256") or final.get("code_identity", {}).get("untracked_runtime_source_sha256"))
    ci = view["ready"]["code_identity"]
    if (ci["tracked_diff_sha256"], ci["untracked_runtime_source_sha256"]) != final_pair:
        problems.append("viewer: the instance did not serve the recorded final code")
    if view["ready"]["real_execution"] != "disabled" or view["ready"]["week2_semantic_enabled"]:
        problems.append("viewer: the instance is not read-only")
    scenes = load(R32 / "07_demo" / "recording_final" / "scenes.json")
    if view["export_sha256"] != scenes["export_sha256"]:
        problems.append("viewer: Export sha256 differs from the Round 32 demo export")
    sc = scenes["ready_at_start"]["code_identity"]
    if (sc["tracked_diff_sha256"], sc["untracked_runtime_source_sha256"]) != final_pair:
        problems.append("viewer: the Round 32 video was not recorded on the final code")
    if view["safety"]["blocked_requests"] or not all(s["ok"] for s in view["steps"]):
        problems.append("viewer: blocked requests or failed steps")
    texts = {s["value"]["disclosure_text"] for s in view["steps"] if s["name"] != "4_export"}
    if len(texts) != 1:
        problems.append("viewer: the disclosure panel text differs between reopenings")
    saved = {k: v for k, v in load(R32 / "05_stage_disclosure" / "stage_disclosure_run2_12591384.json").items() if k not in ("computed_by", "run_id")}
    if load(R33 / "02_viewer" / "check" / "api_stage_disclosure.json") != saved:
        problems.append("viewer: API stage_disclosure differs from the Round 32 copy")
    running = (R33 / "02_viewer" / "running_8002_5177_checks.txt").read_text(encoding="utf-8")
    if "1b53b9218286fd2f9954c3d64b60a031b5a8cbc5fa8b78eab55c55ede1a1f363" not in running or "stage_disclosure key present: False" not in running:
        problems.append("viewer: the 8002 mixed-version evidence is missing")
    return {"ok": not problems, "problems": problems}


def _nested_members() -> set[str]:
    with zipfile.ZipFile(ROUND31_ZIP) as z:  # its names are UTF-8 without the UTF-8 flag
        return {(i.filename if i.flag_bits & 0x800 else i.filename.encode("cp437").decode("utf-8")) for i in z.infolist() if not i.filename.endswith("/")}


def check_references() -> dict:
    members = _nested_members()
    names = files_under(PKG)
    basenames = {n.rsplit("/", 1)[-1] for n in names}
    found, repo, missing = 0, set(), []
    log = load(R33 / "records" / "文档修改记录.json")
    docs = READER_DOCS + [f"round32/{e['round32_path']}" for e in log["edited_documents"]]
    for doc in docs:
        doc_dir = (PKG / doc).parent
        for token in re.findall(r"`([^`\n]+)`", (PKG / doc).read_text(encoding="utf-8")):
            t = token.strip().rstrip("/")
            if not t or any(c in t for c in " =*<>$(){}|,…") or "::" in t or t.startswith(("/", "-", ".", "~", "http")):
                continue
            if "/" not in t and not FILE_EXT.search(t):
                continue
            if any((b / t).exists() for b in (doc_dir, PKG, R33, R32)) or ("/" not in t and t in basenames):
                found += 1
            elif any(m == t or m.endswith("/" + t) for m in members):
                found += 1
            elif t.startswith(REPO_PREFIXES) or re.match(r"round\d+_", t) or ("/" not in t and t.endswith(".py")):
                repo.add(t)  # repository code, or another round's folder under docs/audit_artifacts/round_source_linking_t0_t2/
            else:
                missing.append(f"{doc}: `{token}`")
    readme = (PKG / "README.md").read_text(encoding="utf-8")
    for script in re.findall(r"(?:\$R33/tools/|round32_t4_closure_20261009/tools/)([\w.]+\.(?:py|mjs|sh))", readme):
        if not ((R33 / "tools" / script).is_file() or (R32 / "tools" / script).is_file()):
            missing.append(f"README names a script that is not in the package: {script}")
    if "/Users/" in readme:
        missing.append("README contains an absolute user path")
    return {"ok": not missing, "found": found, "repository_paths": sorted(repo), "missing": missing}


def _blobs(rel: str):
    data = (PKG / rel).read_bytes()
    yield rel, data
    if rel.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for member in z.namelist():
                if not member.endswith("/"):
                    yield f"{rel}!{member}", z.read(member)


def check_credentials() -> dict:
    hits, fixtures, scanned = [], Counter(), 0
    for rel in files_under(PKG):
        for name, data in _blobs(rel):
            scanned += 1
            for label, pattern in CRED.items():
                for m in pattern.finditer(data):
                    if m.group(1) in FIXTURE:
                        fixtures[label] += 1
                    else:
                        hits.append({"file": name, "kind": label, "offset": m.start()})
            for m in CRED_FIELD.finditer(data):
                if REDACTED.match(m.group(2)) or m.group(2) in FIXTURE:
                    fixtures["redacted_or_fixture_field"] += 1
                else:
                    hits.append({"file": name, "kind": "field:" + m.group(1).decode().lower(), "offset": m.start()})
    return {"ok": not hits, "blobs_scanned": scanned, "hits": hits, "fixture_or_redacted": dict(fixtures)}


CHECKS = [("1 manifest", check_manifest), ("2 round32", check_round32), ("3 figures", check_figures), ("4 round33", check_round33),
          ("5 references", check_references), ("6 credentials", check_credentials)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    results = {}
    for name, fn in CHECKS:
        try:
            results[name] = fn()
        except Exception as exc:  # a missing or broken input is a failed check, not a crash
            results[name] = {"ok": False, "problems": [f"{type(exc).__name__}: {exc}"]}
    all_ok = all(r["ok"] for r in results.values())
    if args.json:
        print(json.dumps({"package": PKG.name, "all_ok": all_ok, "checks": results}, ensure_ascii=False, indent=1, default=str))
        return 0 if all_ok else 1
    print(f"package: {PKG.name}")
    for name, r in results.items():
        print(f"[{'PASS' if r['ok'] else 'FAIL'}] {name}")
        summary = {k: v for k, v in r.items() if k not in ("ok", "problems", "hits", "failing", "missing") and not isinstance(v, (list, dict))}
        if summary:
            print("    " + ", ".join(f"{k}={v}" for k, v in summary.items()))
        if name == "5 references":
            print(f"    repository paths (need the original repository): {r.get('repository_paths')}")
        for p in (r.get("problems") or []) + (r.get("missing") or []) + [json.dumps(x, ensure_ascii=False) for x in (r.get("failing") or [])] + [json.dumps(h) for h in (r.get("hits") or [])[:20]]:
            print(f"    problem: {p}")
    print("ALL CHECKS PASSED" if all_ok else "SOME CHECKS FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
