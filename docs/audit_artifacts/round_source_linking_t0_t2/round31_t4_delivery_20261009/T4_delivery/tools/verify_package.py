#!/usr/bin/env python3
"""T4 delivery (round 31): verify this package wherever it was unzipped (standard library only; no API key, no network, no
database, starts no research).

Checks
  1. manifest  : every file listed in manifest.json exists with the recorded size and sha256; no unlisted file
  2. references: every package path quoted in the Markdown reports exists; README commands name existing scripts and contain
                 no absolute user path and no placeholder
  3. statistics: tools/rebuild_stats.py rebuilds every figure of the main report from the raw run files and the ledgers
  4. export    : each run's API Export ZIP has 20 entries, each byte-identical to runs/<run_id>/; the page-download ZIP has
                 the same sha256; the run-2 ZIP sha256 equals the value recorded at the time (round 30)
  5. secrets   : credential / auth-header pattern scan of every file and archive member (plus a value scan with --env)
  6. identity  : the code snapshot reproduces both runs' recorded code identity; the runs' effective config equals the
                 frozen config
  optional     : --regenerate-ledgers (needs the repository at the same code identity): rebuild the claim ledgers with the
                 production evidence-trace code into a temporary directory and compare byte for byte;
                 chapter copies: if ffmpeg is available, the video stream of every *_chapters.mp4 equals the original

    python3 tools/verify_package.py [--env PATH] [--regenerate-ledgers] [--repo PATH] [--out FILE]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True  # leave no __pycache__ inside the package
PKG = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG / "tools"))
RUNS = {"run2_12591384": "12591384-0b26-470d-a99d-a49c00be440b", "run1_fa642639": "fa642639-8d93-4f9a-9de1-2c4d789eade8"}
RUN2_EXPORT_SHA_RECORDED = "49bd4650b60a8c9f6bf5b3d57d3baecba196889a1bfb70c1f4329ecd1b79cef3"  # round30 verification_result.json
TOP = ("runs/", "run_records/", "ledgers/", "usage_cost/", "code_identity/", "tests/", "video/", "references/", "tools/")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_manifest() -> dict:
    manifest = json.loads((PKG / "manifest.json").read_text(encoding="utf-8"))
    listed = {e["path"]: e for e in manifest["files"]}
    missing, mismatched = [], []
    for path, entry in listed.items():
        p = PKG / path
        if not p.is_file():
            missing.append(path)
        elif p.stat().st_size != entry["bytes"] or sha(p) != entry["sha256"]:
            mismatched.append(path)
    present = {str(p.relative_to(PKG)) for p in PKG.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    unlisted = sorted(present - set(listed) - {"manifest.json"})
    return {"files_listed": len(listed), "missing": missing, "mismatched": mismatched, "unlisted": unlisted,
            "ok": not missing and not mismatched and not unlisted}


def check_references() -> dict:
    missing = []
    checked = 0
    for md in sorted(PKG.rglob("*.md")):
        if "original_round" in md.name or md.parent.name in ("round27", "round28", "01_postgres", "02_replay_eslint"):
            continue  # verbatim copies of older reports keep their own (older) paths
        for token in re.findall(r"`([^`\s]+)`", md.read_text(encoding="utf-8")):
            token = token.rstrip("，。、；:")
            if not token.startswith(TOP) and token not in ("manifest.json", "report_figures.json", "README.md", "00_T4交付主报告.md"):
                continue
            if "::" in token or re.search(r":\d+$", token) or (token.startswith("tests/") and token.split("/")[1] not in ("round27", "round28", "测试证据索引.md")):
                continue  # pytest node ids and repository test files are references into the repository, not package paths
            pattern = re.sub(r"<[^>]+>", "*", token)
            checked += 1
            if not (list(PKG.glob(pattern)) if "*" in pattern else (PKG / pattern).exists()):
                missing.append({"file": str(md.relative_to(PKG)), "path": token})
    readme = (PKG / "README.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```bash\n(.*?)```", readme, re.S)
    commands = [line.strip() for block in blocks for line in block.splitlines() if line.strip() and not line.strip().startswith("#")]
    problems = []
    for cmd in commands:
        if "/Users/" in cmd or re.search(r"<[^>]+>", cmd):
            problems.append({"command": cmd, "problem": "absolute user path or placeholder"})
        for script in re.findall(r"(?:^|\s)((?:\S*/)?tools/[\w.]+\.py)", cmd):
            local = script.split("T4_delivery/", 1)[-1] if "T4_delivery/" in script else script
            if not (PKG / local).is_file():
                problems.append({"command": cmd, "problem": f"script not found: {script}"})
    return {"report_paths_checked": checked, "missing_paths": missing, "readme_commands": len(commands), "readme_problems": problems,
            "ok": not missing and not problems and len(commands) > 0}


def check_statistics() -> dict:
    proc = subprocess.run([sys.executable, str(PKG / "tools" / "rebuild_stats.py")], capture_output=True, text=True)
    tail = [line for line in proc.stdout.splitlines() if not line.startswith("OK  ")]
    return {"exit_code": proc.returncode, "summary": tail[-3:], "ok": proc.returncode == 0}


def check_exports() -> dict:
    out, ok = {}, True
    for rec, run_id in RUNS.items():
        zpath = PKG / "run_records" / rec / "api_export.zip"
        page = PKG / "run_records" / rec / "page_download_export.zip"
        mismatched = []
        with zipfile.ZipFile(zpath) as z:
            names = z.namelist()
            for name in names:
                if z.read(name) != (PKG / "runs" / run_id / name).read_bytes():
                    mismatched.append(name)
        entry = {"entries": len(names), "byte_mismatch_vs_run_dir": mismatched, "api_export_sha256": sha(zpath), "page_download_sha256": sha(page)}
        entry["page_equals_api"] = entry["page_download_sha256"] == entry["api_export_sha256"]
        if rec == "run2_12591384":
            entry["equals_sha_recorded_in_round30"] = entry["api_export_sha256"] == RUN2_EXPORT_SHA_RECORDED
        entry_ok = len(names) == 20 and not mismatched and entry["page_equals_api"] and entry.get("equals_sha_recorded_in_round30", True)
        entry["ok"] = entry_ok
        ok &= entry_ok
        out[rec] = entry
    return {**out, "ok": ok}


def check_secrets(env: str | None) -> dict:
    import scan_credentials

    secrets = scan_credentials.env_secrets(Path(env)) if env else {}
    result = scan_credentials.scan(PKG, secrets)
    return {"blobs_scanned": result["blobs_scanned"], "hits": result["hits"][:20], "hit_count": len(result["hits"]),
            "env_value_keys_checked": sorted(secrets), "redacted_header_or_field_values_seen": result["redacted_header_or_field_values_seen"],
            "fixture_or_redacted_matches": result["fixture_or_redacted_matches"], "ok": not result["hits"]}


def check_identity() -> dict:
    import build_run_identity

    snap = PKG / "code_identity"
    diff_sha = sha(snap / "tracked_diff_vs_HEAD.diff")
    untracked = build_run_identity.untracked_identity_from_snapshot(snap / "untracked_runtime_source.tar.gz", snap / "untracked_runtime_source_files.txt")
    frozen = json.loads((snap / "frozen_config.json").read_text(encoding="utf-8"))
    out, ok = {"tracked_diff_file_sha256": diff_sha, "untracked_recomputed": untracked["recomputed_untracked_runtime_source_sha256"]}, True
    for rec, run_id in RUNS.items():
        env = json.loads((PKG / "runs" / run_id / "metadata.json").read_text(encoding="utf-8"))["run_environment"]
        r = {"tracked_matches": env["code_identity"]["tracked_diff_sha256"] == diff_sha,
             "untracked_matches": env["code_identity"]["untracked_runtime_source_sha256"] == untracked["recomputed_untracked_runtime_source_sha256"],
             "week2_config_equals_frozen": env["effective_config"]["week2_semantic"] == frozen["effective_config"]["week2"],
             "agent_config_equals_frozen": env["effective_config"]["research_agents"] == frozen["effective_config"]["agents"],
             "database": f"{env['database'].get('dialect')} {env['database'].get('database')}"}
        r["ok"] = all(v for k, v in r.items() if k != "database") and r["database"] == "postgresql comqutor_alpha_t4_test"
        ok &= r["ok"]
        out[rec] = r
    return {**out, "ok": ok and not untracked["missing_from_tar"] and not untracked["listed_sha_mismatch"]}


def check_chapters() -> dict:
    ffmpeg = shutil.which("ffmpeg") or ("/opt/homebrew/bin/ffmpeg" if Path("/opt/homebrew/bin/ffmpeg").is_file() else None)
    if not ffmpeg:
        return {"skipped": "ffmpeg not available", "ok": True}
    build = json.loads((PKG / "video" / "chapters_build.json").read_text(encoding="utf-8"))
    results = []
    for r in build["results"]:
        def md5(p):
            return subprocess.run([ffmpeg, "-v", "error", "-i", str(PKG / p), "-map", "0:v:0", "-c", "copy", "-f", "md5", "-"],
                                  capture_output=True, text=True, check=True).stdout.strip().removeprefix("MD5=")
        a, b = md5(r["video"]), md5(r["chaptered_copy"])
        results.append({"video": r["video"], "stream_md5_equal": a == b, "equals_recorded": a == r["original_video_stream_md5"]})
    return {"results": results, "ok": all(x["stream_md5_equal"] and x["equals_recorded"] for x in results)}


def regenerate_ledgers(repo: Path) -> dict:
    py = repo / ".venv" / "bin" / "python"
    py = py if py.is_file() else Path(sys.executable)
    head = subprocess.run(["git", "diff", "HEAD", "--binary"], cwd=repo, capture_output=True, text=True).stdout
    current = hashlib.sha256(head.encode("utf-8")).hexdigest()
    out, ok = {"repo_tracked_diff_sha256_now": current,
               "repo_code_equals_run_code": current == sha(PKG / "code_identity" / "tracked_diff_vs_HEAD.diff")}, True
    with tempfile.TemporaryDirectory() as tmp:
        for rec, run_id in RUNS.items():
            target = Path(tmp) / rec
            proc = subprocess.run([str(py), str(PKG / "tools" / "build_claim_ledger.py"), "--run-dir", str(PKG / "runs" / run_id), "--out-dir", str(target)],
                                  capture_output=True, text=True, cwd=repo, env={**os.environ, "PYTHONPATH": str(repo)})
            diffs = [p.name for p in sorted((PKG / "ledgers" / rec).iterdir()) if not (target / p.name).is_file() or (target / p.name).read_bytes() != p.read_bytes()]
            out[rec] = {"exit_code": proc.returncode, "files_differing": diffs, "ok": proc.returncode == 0 and not diffs}
            ok &= out[rec]["ok"]
    out["ok"] = ok
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", help="a .env file for the credential VALUE scan (values never printed)")
    ap.add_argument("--regenerate-ledgers", action="store_true")
    ap.add_argument("--repo", help="repository root for --regenerate-ledgers (default: a parent of this package)")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    report: dict = {"package": PKG.name}
    for name, fn in (("1_manifest", check_manifest), ("2_references", check_references), ("3_statistics", check_statistics),
                     ("4_export", check_exports), ("5_secrets", lambda: check_secrets(args.env)), ("6_identity", check_identity),
                     ("optional_chapters", check_chapters)):
        report[name] = fn()
        print(f"{name}: {'PASS' if report[name]['ok'] else 'FAIL'}")
    if args.regenerate_ledgers:
        repo = Path(args.repo) if args.repo else next((p for p in PKG.parents if (p / "comqutor_alpha").is_dir()), None)
        report["optional_regenerate_ledgers"] = regenerate_ledgers(repo) if repo else {"skipped": "repository not found", "ok": False}
        print(f"optional_regenerate_ledgers: {'PASS' if report['optional_regenerate_ledgers']['ok'] else 'FAIL'}")
    report["all_ok"] = all(v["ok"] for v in report.values() if isinstance(v, dict))
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
