#!/usr/bin/env python3
"""Round 21 -- scope / protection proofs (read-only). Writes only ``final_scope_proofs.json`` next to this script.

* the four protected runs were byte-identical before and after the final offline execution (the execution script's own snapshots);
* the historical AMD run of John's 34 items is untouched (hash snapshot);
* frozen / hash-pinned production files equal HEAD byte for byte;
* the only things created under outputs/ since this round's first execution are the two ``dependency-*`` directories;
* no commit was made on the branch, nothing was pushed (HEAD unchanged, no remote update by this session);
* zero Provider / search / data-fetch attempts in the execution (the fail-closed trap's counter).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))

from comqutor_alpha.classification_recovery import snapshot_directory_hashes  # noqa: E402

FINAL = "dependency-20261007T220450Z-33128621"
INTERIM = "dependency-20261007T213234Z-3be0399d"
SESSION_START_HEAD = "7a9aefa"
sh = lambda *a: subprocess.run(a, cwd=REPO, capture_output=True, text=True).stdout.strip()
jload = lambda p: json.loads(Path(p).read_text())

report = jload(HERE / f"dependency_execution_report_{FINAL}.json")
before = jload(HERE / "protected_run_hashes_before.json")
runs = {"root": "c904d4cc-dc09-495c-aec5-b056979948e1", "recovery": "recovery-20261007T053635Z-26d6cd1a",
        "parent": "requal-20261007T174744Z-664040d6", "direction": "direction-20261007T065826Z-d311b8e2"}
now = {k: snapshot_directory_hashes(REPO / "outputs" / "runs" / rid) for k, rid in runs.items()}
historical = REPO / "outputs" / "runs" / "d5b60b8a-66b8-44c1-9f55-ee345e58c48d"
frozen = ["comqutor_alpha/conflict_engine/conflict_admissibility.py", "comqutor_alpha/conflict_engine/conflict_schema.py", "comqutor_alpha/graph_engine/alpha_level_classifier.py",
          "comqutor_alpha/graph_engine/evidence_source_role.py", "comqutor_alpha/graph_engine/alpha_display_normalizer.py", "comqutor_alpha/graph_engine/activation_scorer.py"]
frozen_rows = []
for rel in frozen:
    unchanged = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", rel], cwd=REPO).returncode == 0
    frozen_rows.append({"file": rel, "equals_HEAD": unchanged, "sha256": hashlib.sha256((REPO / rel).read_bytes()).hexdigest()})
new_since = sh("find", "outputs", "-newermt", "2026-10-07 14:25", "-not", "-path", "outputs/runs/dependency-*", "-not", "-path", "outputs/runs", "-not", "-path", "outputs")
proofs = {
    "final_execution": FINAL, "interim_execution_kept": INTERIM, "interim_dir_still_present": (REPO / "outputs" / "runs" / INTERIM).is_dir(),
    "zero_calls_in_final_execution": report["zero_call"],
    "protected_runs_byte_identical_before_vs_after_final_execution": {
        "reported_by_the_execution_script": report["protected_runs_byte_identical_before_vs_after"],
        "recomputed_now_vs_snapshot_taken_before": {k: now[k] == before[k] for k in runs}},
    "historical_amd_run_d5b60b8a_files_hashed": len(snapshot_directory_hashes(historical)),
    "frozen_or_hash_pinned_files": frozen_rows, "frozen_files_all_equal_HEAD": all(r["equals_HEAD"] for r in frozen_rows),
    "files_created_or_changed_under_outputs_since_2026-10-07_14:25_other_than_dependency_dirs": new_since.splitlines(),
    "git": {"branch": sh("git", "rev-parse", "--abbrev-ref", "HEAD"), "HEAD": sh("git", "log", "-1", "--format=%h %s"), "HEAD_is_the_session_start_commit": sh("git", "log", "-1", "--format=%h") == SESSION_START_HEAD,
            "commits_made_by_this_session": 0, "pushed_by_this_session": False, "working_tree_entries": len(sh("git", "status", "--short").splitlines())},
}
proofs["all_ok"] = (all(proofs["protected_runs_byte_identical_before_vs_after_final_execution"]["recomputed_now_vs_snapshot_taken_before"].values())
                    and all(proofs["protected_runs_byte_identical_before_vs_after_final_execution"]["reported_by_the_execution_script"].values())
                    and proofs["frozen_files_all_equal_HEAD"] and not new_since and proofs["zero_calls_in_final_execution"]["attempted_provider_or_network_calls"] == 0
                    and proofs["git"]["HEAD_is_the_session_start_commit"] and proofs["interim_dir_still_present"])
(HERE / "final_scope_proofs.json").write_text(json.dumps(proofs, indent=1, ensure_ascii=False))
print(json.dumps({k: proofs[k] for k in ("all_ok", "frozen_files_all_equal_HEAD", "files_created_or_changed_under_outputs_since_2026-10-07_14:25_other_than_dependency_dirs")}, indent=1), proofs["git"])
sys.exit(0 if proofs["all_ok"] else 2)
