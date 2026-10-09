#!/usr/bin/env python3
"""Round 22: verify ``release_manifest_v2.json`` against the files it points at -- every hash, every copy, every snapshot.

Checks (all read-only):
  * the manifest's HEAD is the repository's real HEAD, and nothing was committed (HEAD is still the recorded commit);
  * the superseded 2026-10-01 manifest still has the recorded sha256 (kept, untouched);
  * both code snapshots rebuild from HEAD + patch + untracked copies and hash as recorded (``verify_snapshot.py``); the final one also equals the working tree;
  * ``round22_changes.patch`` exists and has the recorded sha256;
  * every rule file copy exists and hashes as recorded; every prompt text file hashes to the prompt identity hash the runs recorded;
  * for every registered run: each copied identity file equals its original in ``outputs/runs``; each log file hashes as recorded; the run directory's
    file-by-file digest equals the recorded digest (so any later change to a run directory is detected);
  * the final execution's code-identity proof says ``proven``.

usage: verify_release_manifest_v2.py   (writes release_manifest_v2_verification.json; exit code 0 only when everything matches)
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
MANIFEST = HERE / "release_manifest_v2.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_digest(run_dir: Path) -> tuple[int, str]:
    files = {str(p.relative_to(run_dir)): sha(p) for p in sorted(run_dir.rglob("*")) if p.is_file()}
    return len(files), hashlib.sha256("\n".join(f"{k}\t{v}" for k, v in sorted(files.items())).encode("utf-8")).hexdigest()


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    problems: list[str] = []
    checked = {"identity_file_copies": 0, "log_files": 0, "run_directories": 0, "rule_file_copies": 0}

    head_now = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    if head_now != manifest["git"]["head_sha"]:
        problems.append(f"HEAD is now {head_now[:10]}, the manifest recorded {manifest['git']['head_sha'][:10]} (something was committed or checked out)")

    old = manifest["supersedes"]
    old_path = REPO / old["path"]
    if not old_path.exists() or sha(old_path) != old["sha256"]:
        problems.append("the superseded manifest is missing or was changed")

    snapshots = manifest["code_snapshots"]
    for label, extra in (("S0_before_round22", []), ("S1_final", ["--against-working-tree"])):
        result = subprocess.run([sys.executable, str(HERE / "verify_snapshot.py"), str(REPO / snapshots[label]["dir"]), *extra], capture_output=True, text=True)
        try:
            verdict = json.loads(result.stdout)
        except json.JSONDecodeError:
            verdict = {"ok": False, "problems": [result.stdout[-300:] + result.stderr[-300:]]}
        if not verdict.get("ok"):
            problems.append(f"snapshot {label}: {verdict.get('problems')}")
    changes = snapshots.get("round22_changes")
    if not isinstance(changes, dict) or not (REPO / changes["path"]).exists() or sha(REPO / changes["path"]) != changes["sha256"]:
        problems.append("round22_changes.patch missing or changed")

    for rel, meta in manifest["rules"]["rule_files"].items():
        checked["rule_file_copies"] += 1
        copy = REPO / meta["snapshot_copy"]
        if not copy.exists() or sha(copy) != meta["sha256"]:
            problems.append(f"rule file copy {rel}: missing or different")

    checked["prompt_files"] = 0
    for rel, meta in manifest["prompts"]["files"].items():
        checked["prompt_files"] += 1
        path = REPO / rel
        if not path.exists() or sha(path) != meta["sha256"]:
            problems.append(f"prompt text {rel}: missing, or its sha256 is not the recorded prompt identity hash")

    for run_id, run in manifest["runs"].items():
        if run.get("status") == "DIRECTORY_MISSING":
            problems.append(f"{run_id}: directory missing")
            continue
        for name, meta in (run["input"]["identity_files"] or {}).items():
            checked["identity_file_copies"] += 1
            copy, original = REPO / meta["copy_in_delivery"], REPO / meta["original"]
            if not copy.exists() or sha(copy) != meta["sha256"] or not original.exists() or sha(original) != meta["sha256"]:
                problems.append(f"{run_id}/{name}: identity file copy or original differs from the recorded hash")
        for log in run["logs"]:
            checked["log_files"] += 1
            path = REPO / log["path"]
            if not path.exists() or sha(path) != log["sha256"]:
                problems.append(f"{run_id}: log {log['path']} missing or changed")
        for record in run.get("round_records", []):
            checked["round_records"] = checked.get("round_records", 0) + 1
            path = REPO / record["path"]
            if not path.exists() or sha(path) != record["sha256"]:
                problems.append(f"{run_id}: round record {record['path']} missing or changed")
        checked["run_directories"] += 1
        count, digest = run_digest(REPO / "outputs" / "runs" / run_id)
        if (count, digest) != (run["directory"]["file_count"], run["directory"]["directory_digest_sha256"]):
            problems.append(f"{run_id}: the run directory no longer matches its recorded digest ({count} files now, {run['directory']['file_count']} recorded)")
        if run["code_identity"]["status"] == "SNAPSHOT_S0" and not run["code_identity"]["proof"].get("proven"):
            problems.append(f"{run_id}: the code-identity proof is not 'proven'")

    result = {"manifest": str(MANIFEST.relative_to(REPO)), "head": head_now, "checked": checked, "problems": problems, "ok": not problems}
    (HERE / "release_manifest_v2_verification.json").write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=1, ensure_ascii=False))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
