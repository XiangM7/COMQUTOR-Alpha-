#!/usr/bin/env python3
"""T4 round 32: verify the final T4 package wherever it was unzipped (standard library only; no API key, no network, no
database, starts no research).

  1 manifest   : every file in manifest.json present with its size and sha256; no unlisted file
  2 references : every package path quoted in the Markdown reports exists; README commands name existing scripts and contain no
                 absolute user path and no placeholder
  3 statistics : tools/rebuild_stats32.py rebuilds every figure of the final report from the package's own files
  4 artifacts  : the nested Round 31 ZIP has its recorded sha256; the PostgreSQL chain's Export ZIP of the derived execution
                 matches its manifest and the derived run directory byte for byte (incl. stage_disclosure.json); the demo's
                 page-download ZIP equals the second Fresh run's recorded Export hash
  5 secrets    : credential / auth-header scan of every file and archive member (tools/scan_credentials.py; --env adds values)
  6 identity   : the final code snapshot reproduces the final code identity recorded by the instances and the tests

    python3 tools/verify_package32.py [--env PATH] [--out FILE]
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True
PKG = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG / "tools"))
ROUND31_ZIP_SHA = "6f11b68844598b12e31ba36d0a2e756b133a1e17be76593eefebf1af555ec89b"
FRESH2_EXPORT_SHA = "49bd4650b60a8c9f6bf5b3d57d3baecba196889a1bfb70c1f4329ecd1b79cef3"
FINAL_TRACKED = "6cdd51e345929a1936845a416dd8a38c6f00ea3d0293afa03282d002dc96857c"
FINAL_UNTRACKED = "10ee75185ae8032bc9bdf304152a87c1d22db08120cdd546d31925277e21f0f6"
TOP = ("01_regressions/", "02_code/", "03_not_sent/", "03_postgres/", "04_tests/", "05_stage_disclosure/", "05_replay/", "06_frozen_checks/",
       "07_demo/", "references/", "runs/", "tools/")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_manifest() -> dict:
    manifest = json.loads((PKG / "manifest.json").read_text(encoding="utf-8"))
    listed = {e["path"]: e for e in manifest["files"]}
    missing = [p for p in listed if not (PKG / p).is_file()]
    mismatched = [p for p, e in listed.items() if (PKG / p).is_file() and ((PKG / p).stat().st_size != e["bytes"] or sha(PKG / p) != e["sha256"])]
    present = {str(p.relative_to(PKG)) for p in PKG.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    unlisted = sorted(present - set(listed) - {"manifest.json"})
    return {"files_listed": len(listed), "missing": missing, "mismatched": mismatched, "unlisted": unlisted, "ok": not (missing or mismatched or unlisted)}


def check_references() -> dict:
    missing, checked = [], 0
    for md in sorted(PKG.rglob("*.md")):
        if "superseded" in str(md) or md.parent.name in ("references",):
            continue
        for token in re.findall(r"`([^`\s]+)`", md.read_text(encoding="utf-8")):
            token = token.rstrip("，。、；:")
            if not token.startswith(TOP) and token not in ("manifest.json", "report_figures.json", "README.md", "00_T4最终交付报告.md"):
                continue
            pattern = re.sub(r"<[^>]+>", "*", token)
            checked += 1
            if not (list(PKG.glob(pattern)) if "*" in pattern else (PKG / pattern).exists()):
                missing.append({"file": str(md.relative_to(PKG)), "path": token})
    readme = (PKG / "README.md").read_text(encoding="utf-8")
    commands = [ln.strip() for block in re.findall(r"```bash\n(.*?)```", readme, re.S) for ln in block.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    problems = []
    for cmd in commands:
        if "/Users/" in cmd or re.search(r"<[^>]+>", cmd):
            problems.append({"command": cmd, "problem": "absolute user path or placeholder"})
        for script in re.findall(r"(?:^|\s)((?:\S*/)?tools/[\w.]+\.(?:py|sh))", cmd):
            if not (PKG / "tools" / Path(script).name).is_file():  # every script the README names has a copy in tools/
                problems.append({"command": cmd, "problem": f"script not found: {script}"})
    return {"report_paths_checked": checked, "missing_paths": missing, "readme_commands": len(commands), "readme_problems": problems,
            "ok": not missing and not problems and bool(commands)}


def check_statistics() -> dict:
    proc = subprocess.run([sys.executable, str(PKG / "tools" / "rebuild_stats32.py")], capture_output=True, text=True)
    return {"exit_code": proc.returncode, "summary": [ln for ln in proc.stdout.splitlines() if not ln.startswith("OK  ")][-4:], "ok": proc.returncode == 0}


def check_artifacts() -> dict:
    out = {"round31_zip_sha_matches": sha(PKG / "references" / "T4_delivery_round31_20261009.zip") == ROUND31_ZIP_SHA}
    exports = sorted((PKG / "03_postgres" / "exports").glob("*.zip"))
    entries = {}
    for z in exports:
        rid = z.stem
        run_dir = PKG / "runs" / rid
        with zipfile.ZipFile(z) as zf:
            names = zf.namelist()
            manifest = json.loads(zf.read("artifact_manifest.json"))
            listed = [a for a in manifest["artifacts"] if a.get("exists")]
            mism = [a["path"] for a in listed if zf.read(a["path"]) != (run_dir / a["path"]).read_bytes() or hashlib.sha256(zf.read(a["path"])).hexdigest() != a["sha256"]]
            entries[rid] = {"members": len(names), "manifest_files": len(listed), "byte_mismatch": mism, "stage_disclosure_in_zip": "stage_disclosure.json" in names,
                            "stage_disclosure_equals_run_dir": "stage_disclosure.json" in names and zf.read("stage_disclosure.json") == (run_dir / "stage_disclosure.json").read_bytes()}
    out["derived_execution_exports"] = entries
    demo = json.loads((PKG / "07_demo" / "recording_final" / "scenes.json").read_text(encoding="utf-8"))
    page_zip = PKG / "07_demo" / "recording_final" / demo["export_file"]
    out["demo_page_download_sha_equals_fresh2_export"] = sha(page_zip) == FRESH2_EXPORT_SHA
    out["ok"] = (out["round31_zip_sha_matches"] and out["demo_page_download_sha_equals_fresh2_export"] and bool(entries)
                 and all(not e["byte_mismatch"] and e["stage_disclosure_in_zip"] and e["stage_disclosure_equals_run_dir"] for e in entries.values()))
    return out


def check_secrets(env: str | None) -> dict:
    import scan_credentials

    secrets = scan_credentials.env_secrets(Path(env)) if env else {}
    result = scan_credentials.scan(PKG, secrets)
    return {"blobs_scanned": result["blobs_scanned"], "hit_count": len(result["hits"]), "hits": result["hits"][:20],
            "env_value_keys_checked": sorted(secrets), "fixture_or_redacted_matches": result["fixture_or_redacted_matches"], "ok": not result["hits"]}


def check_identity() -> dict:
    code = PKG / "02_code"
    tracked = sha(code / "final_tracked_diff_vs_HEAD.diff")
    entries = [x.split("  ", 1) for x in (code / "final_untracked_runtime_source_files.txt").read_text(encoding="utf-8").splitlines() if x.strip()]
    contents = {}
    with tarfile.open(code / "final_untracked_runtime_source.tar.gz", "r:gz") as tar:
        for m in tar.getmembers():
            if m.isfile():
                contents[m.name] = tar.extractfile(m).read()
    listing = "".join(f"{p}\0{hashlib.sha256(contents[p]).hexdigest()}\n" for _, p in sorted(entries, key=lambda e: e[1]) if p in contents)
    untracked = hashlib.sha256(listing.encode("utf-8")).hexdigest()
    recorded = json.loads((code / "final_code_identity.json").read_text(encoding="utf-8"))
    ready = json.loads((PKG / "03_postgres" / "snapshot_post_restart_result.json").read_text(encoding="utf-8"))["ready"]["code_identity"]
    demo = json.loads((PKG / "07_demo" / "recording_final" / "scenes.json").read_text(encoding="utf-8"))["ready_at_start"]["code_identity"]
    out = {"tracked_diff_file_sha256": tracked, "untracked_recomputed": untracked,
           "equals_recorded_final_identity": tracked == recorded["tracked_diff_sha256"] == FINAL_TRACKED and untracked == recorded["untracked_runtime_source_sha256"] == FINAL_UNTRACKED,
           "verify_instance_ran_final_code": ready["tracked_diff_sha256"] == FINAL_TRACKED and ready["untracked_runtime_source_sha256"] == FINAL_UNTRACKED,
           "demo_instance_ran_final_code": demo["tracked_diff_sha256"] == FINAL_TRACKED and demo["untracked_runtime_source_sha256"] == FINAL_UNTRACKED}
    tests = {}
    for g in ("new", "replay", "pg", "affected", "frontend"):
        text = (PKG / "04_tests" / f"{g}_command.txt").read_text(encoding="utf-8")
        before = re.search(r"code_identity_before \(tracked untracked\): (\S+) (\S+)", text)
        tests[g] = bool(before) and before.group(1) == FINAL_TRACKED and before.group(2) == FINAL_UNTRACKED and "code_unchanged_during_group: yes" in text
    out["tests_ran_on_final_code_unchanged"] = tests
    out["ok"] = out["equals_recorded_final_identity"] and out["verify_instance_ran_final_code"] and out["demo_instance_ran_final_code"] and all(tests.values())
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    report: dict = {"package": PKG.name}
    for name, fn in (("1_manifest", check_manifest), ("2_references", check_references), ("3_statistics", check_statistics),
                     ("4_artifacts", check_artifacts), ("5_secrets", lambda: check_secrets(args.env)), ("6_identity", check_identity)):
        report[name] = fn()
        print(f"{name}: {'PASS' if report[name]['ok'] else 'FAIL'}")
    report["all_ok"] = all(v["ok"] for v in report.values() if isinstance(v, dict))
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
