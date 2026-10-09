#!/usr/bin/env python3
"""Round 23 (T2 completion): build the T2-ONLY diff against the real HEAD and prove it applies to a clean checkout of HEAD.

The working tree holds the changes of every task (T1..T4) uncommitted. John's sign-off asks for "commit、diff"; there is no commit (not made, by
instruction), so the diff is taken against the real HEAD and restricted to the files T2 owns:

  * tracked files T2 owns entirely            -> the whole `git diff HEAD`
  * tracked files shared with other tasks     -> only the hunks that concern the formal acceptance wiring (HUNK_FILTER)
  * files that do not exist at HEAD           -> a full "new file" diff (`git diff --no-index /dev/null <file>`)

Writes t2_changes.patch and t2_files.json next to this script, then rebuilds the touched files from `git archive HEAD` + the patch in a temp
directory and checks them against the working tree. The repository is only read.

usage: python build_t2_patch.py
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tarfile
import tempfile
from io import BytesIO
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]

T2_FILES = [
    # rule files
    "comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml",
    "comqutor_alpha/config/j2_provisional_regression_labels_v0.2.yaml",
    # code
    "comqutor_alpha/regression/acceptance_engine.py",
    "comqutor_alpha/regression/labels_v2.py",
    "comqutor_alpha/regression/formal_acceptance_report.py",
    "comqutor_alpha/regression/frozen_input_conflict_recompute.py",
    "comqutor_alpha/regression/open_review_ledger.py",
    "comqutor_alpha/api/formal_acceptance_artifact.py",
    "comqutor_alpha/api/routes_research.py",
    "comqutor_alpha/storage/file_store.py",
    "scripts/run_formal_acceptance.py",
    "scripts/recompute_conflicts_frozen_inputs.py",
    "scripts/build_open_review_ledger.py",
    # tests
    "tests/test_acceptance_engine.py",
    "tests/test_t2_acceptance_engine_qualified_evidence_scenarios.py",
    "tests/test_t2_architecture_replay_never_shown_as_pass_or_no_conflict.py",
    "tests/test_formal_acceptance_artifact_production_wiring.py",
    "tests/test_no_gold_label_import_in_research_path.py",
    "tests/test_t2_rule_config_errors.py",
    "tests/test_label_v2_covers_john_frozen_baseline.py",
    "tests/test_formal_acceptance_report.py",
    "tests/test_frozen_input_conflict_recompute.py",
    "tests/test_open_review_ledger.py",
    "tests/test_t2_scenario_map_points_at_real_tests.py",
    "tests/test_msft_a102_a304_taxonomy_adjudication.py",
    "tests/test_a4_regression_runner.py",
    "tests/test_j3_semantic_benchmark_j2_v0_2.py",
    "tests/test_week4_golden_closure.py",
    "tests/test_v0_1_3_offline_replay_proof.py",
    "tests/test_evidence_review_v2.py",
    "tests/test_step10_final_e2e_qa.py",
    "tests/test_step11_provider_health_rerun.py",
    "tests/test_high_value_unclassified_recovery.py",
    # specs / docs that the tests read or that record the decision
    "docs/specs/product_decisions_and_unknowns.md",
    "docs/specs/t2_acceptance_scenario_map.json",
    "docs/audit_artifacts/msft_a102_a304_taxonomy_adjudication_report.md",
    "docs/audit_artifacts/v0_2_john_frozen_gold_baseline.yaml",
]
# Files that other tasks also changed: only the hunks mentioning this text belong to T2.
HUNK_FILTER = {
    "comqutor_alpha/api/routes_research.py": "formal_acceptance",
    "comqutor_alpha/storage/file_store.py": "formal_acceptance",
}


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def is_tracked(path: str) -> bool:
    return subprocess.run(["git", "ls-files", "--error-unmatch", path], cwd=REPO, capture_output=True).returncode == 0


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def filtered_diff(path: str, needle: str) -> str:
    """Only the hunks of `git diff HEAD -U0 -- path` whose text contains `needle` (zero context, so unrelated neighbours never ride along)."""
    out = git("diff", "HEAD", "-U0", "--", path)
    header, hunks, current = [], [], None
    for line in out.splitlines(keepends=True):
        if line.startswith("@@"):
            current = [line]
            hunks.append(current)
        elif current is None:
            header.append(line)
        else:
            current.append(line)
    kept = ["".join(h) for h in hunks if needle in "".join(h)]
    return "".join(header) + "".join(kept) if kept else ""


def count(patch: str) -> tuple[int, int]:
    plus = sum(1 for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++"))
    minus = sum(1 for line in patch.splitlines() if line.startswith("-") and not line.startswith("---"))
    return plus, minus


def main() -> int:
    head = git("rev-parse", "HEAD").strip()
    parts: list[str] = []
    inventory: list[dict] = []
    for rel in T2_FILES:
        path = REPO / rel
        if not path.is_file():
            raise SystemExit(f"T2 file missing from the working tree: {rel}")
        if not is_tracked(rel):
            diff = subprocess.run(["git", "diff", "--no-index", "--", "/dev/null", rel], cwd=REPO, capture_output=True, text=True).stdout
            kind = "new_file"
        elif rel in HUNK_FILTER:
            diff, kind = filtered_diff(rel, HUNK_FILTER[rel]), "tracked_formal_acceptance_hunks_only"
        else:
            diff, kind = git("diff", "HEAD", "--", rel), "tracked_whole_file_diff"
        if not diff.strip():
            raise SystemExit(f"{rel}: T2 owns this file but it has no difference from HEAD")
        plus, minus = count(diff)
        parts.append(diff if diff.endswith("\n") else diff + "\n")
        inventory.append({"path": rel, "kind": kind, "lines_added": plus, "lines_removed": minus, "sha256_working_tree": sha256_of(path)})

    patch = "".join(parts)
    (HERE / "t2_changes.patch").write_text(patch, encoding="utf-8")

    # ---- prove the patch rebuilds the T2 files from a clean HEAD ----------------------------------------------------------------------
    tracked = [e["path"] for e in inventory if e["kind"] != "new_file"]
    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix="t2_patch_verify_") as tmp:
        tmp_dir = Path(tmp)
        archive = subprocess.run(["git", "archive", head, "--", *tracked], cwd=REPO, capture_output=True)
        if archive.returncode != 0:
            raise SystemExit(f"git archive failed: {archive.stderr.decode()[:300]}")
        with tarfile.open(fileobj=BytesIO(archive.stdout)) as tar:
            tar.extractall(tmp_dir, filter="data")
        for entry in inventory:
            if entry["kind"] == "new_file" and subprocess.run(["git", "cat-file", "-e", f"{head}:{entry['path']}"], cwd=REPO, capture_output=True).returncode == 0:
                problems.append(f"{entry['path']}: listed as new but exists at HEAD")
        applied = subprocess.run(["git", "-C", str(tmp_dir), "apply", "--unidiff-zero", str((HERE / 't2_changes.patch').resolve())], capture_output=True, text=True)
        if applied.returncode != 0:
            problems.append(f"patch does not apply to HEAD {head[:10]}: {applied.stderr.strip()[:400]}")
        else:
            for entry in inventory:
                rebuilt = tmp_dir / entry["path"]
                if not rebuilt.is_file():
                    problems.append(f"{entry['path']}: not produced by HEAD + patch")
                elif entry["kind"] == "tracked_formal_acceptance_hunks_only":
                    text = rebuilt.read_text(encoding="utf-8")
                    if not re.search(r"formal_acceptance", text):
                        problems.append(f"{entry['path']}: HEAD + patch lacks the formal acceptance hunks")
                elif sha256_of(rebuilt) != entry["sha256_working_tree"]:
                    problems.append(f"{entry['path']}: HEAD + patch hashes differently from the working tree")
    result = {
        "head": head,
        "branch": git("rev-parse", "--abbrev-ref", "HEAD").strip(),
        "commit": "none was made (instruction: no commit); the diff is against the real HEAD above",
        "patch": "t2_changes.patch",
        "patch_sha256": sha256_of(HERE / "t2_changes.patch"),
        "files": inventory,
        "totals": {"files": len(inventory), "lines_added": sum(e["lines_added"] for e in inventory), "lines_removed": sum(e["lines_removed"] for e in inventory)},
        "rebuild_check": {"method": "git archive HEAD (tracked files) + git apply --unidiff-zero in a temp directory", "problems": problems, "ok": not problems},
    }
    (HERE / "t2_files.json").write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("head", "totals", "rebuild_check")}, indent=1))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
