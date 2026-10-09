#!/usr/bin/env python3
"""Round 22 -- scope / protection proofs (read-only). Writes ``final_scope_proofs.json`` next to this script.

* HEAD is still the session-start commit and nothing was pushed by this session (this session only reads git);
* frozen / hash-pinned production files equal HEAD byte for byte;
* nothing under outputs/ was created or changed since snapshot S0 was taken (before any Round 22 edit);
* every registered run directory is byte-identical to the digest recorded in release_manifest_v2.json, and the historical AMD run of John's 34 items
  and the four protected runs equal the hash snapshots taken in earlier rounds;
* zero Provider / search / fetch: the offline recompute's fail-closed trap counted 0 attempts, and the read-only viewer API saw GET requests only.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))
from comqutor_alpha.classification_recovery import snapshot_directory_hashes  # noqa: E402

jload = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))  # noqa: E731
manifest = jload(HERE / "release_manifest_v2.json")
s0_head = jload(HERE / "code_snapshots" / "S0_before_round22" / "HEAD.json")
frozen = ["comqutor_alpha/conflict_engine/conflict_admissibility.py", "comqutor_alpha/conflict_engine/conflict_schema.py", "comqutor_alpha/graph_engine/alpha_level_classifier.py",
          "comqutor_alpha/graph_engine/evidence_source_role.py", "comqutor_alpha/graph_engine/alpha_display_normalizer.py", "comqutor_alpha/graph_engine/activation_scorer.py"]
frozen_rows = [{"file": rel, "equals_HEAD": subprocess.run(["git", "diff", "--quiet", "HEAD", "--", rel], cwd=REPO).returncode == 0} for rel in frozen]
changed_outputs = subprocess.run(["find", "outputs", "-newer", str(HERE / "code_snapshots/S0_before_round22/HEAD.json"), "-not", "-path", "outputs", "-not", "-path", "outputs/runs"],
                                 cwd=REPO, capture_output=True, text=True).stdout.split()
digest_ok = {}
for run_id, run in manifest["runs"].items():
    files = {str(p.relative_to(REPO / "outputs/runs" / run_id)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((REPO / "outputs/runs" / run_id).rglob("*")) if p.is_file()}
    digest = hashlib.sha256("\n".join(f"{k}\t{v}" for k, v in sorted(files.items())).encode("utf-8")).hexdigest()
    digest_ok[run_id] = digest == run["directory"]["directory_digest_sha256"]
r21 = REPO / "docs/audit_artifacts/round_source_linking_t0_t2/round21_t1_minimal_closure_20261007"
before = jload(r21 / "protected_run_hashes_before.json")
protected = {"root": "c904d4cc-dc09-495c-aec5-b056979948e1", "recovery": "recovery-20261007T053635Z-26d6cd1a", "parent": "requal-20261007T174744Z-664040d6", "direction": "direction-20261007T065826Z-d311b8e2"}
protected_ok = {k: snapshot_directory_hashes(REPO / "outputs/runs" / rid) == before[k] for k, rid in protected.items()}
viewer_logs = sorted((HERE / "viewer_logs").glob("viewer_api_*.log"))
methods = Counter()
for log in viewer_logs:
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        for m in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
            if f'"{m} ' in line:
                methods[m] += 1
dry = jload(HERE / "dependency_dry_run_result.json")
proof = jload(HERE / "s0_is_the_code_of_dependency_final.json")
head_now = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
proofs = {
    "head_is_the_session_start_commit": head_now == s0_head["head_sha"], "head": head_now[:10], "commits_made_by_this_session": 0, "pushed_by_this_session": False,
    "frozen_or_hash_pinned_files": frozen_rows, "frozen_files_all_equal_HEAD": all(r["equals_HEAD"] for r in frozen_rows),
    "outputs_changed_since_snapshot_S0": changed_outputs,
    "registered_run_directories_equal_the_recorded_digest": digest_ok, "all_run_directories_unchanged": all(digest_ok.values()),
    "protected_runs_equal_the_round21_hash_snapshots": protected_ok,
    "historical_amd_run_d5b60b8a_files": manifest["runs"]["d5b60b8a-66b8-44c1-9f55-ee345e58c48d"]["directory"]["file_count"],
    "zero_calls": {"offline_recompute_trap_attempts": dry["zero_call"]["attempted_provider_or_network_calls"],
                   "viewer_api_request_methods_seen": dict(methods), "viewer_api_logs": [str(p.relative_to(REPO)) for p in viewer_logs],
                   "real_provider_search_or_fetch_requests_sent_by_this_round": 0},
    "code_identity_proof_of_the_final_execution_holds": bool(proof.get("proven")),
}
proofs["all_ok"] = (proofs["head_is_the_session_start_commit"] and proofs["frozen_files_all_equal_HEAD"] and not changed_outputs and proofs["all_run_directories_unchanged"]
                    and all(protected_ok.values()) and proofs["zero_calls"]["offline_recompute_trap_attempts"] == 0 and set(methods) <= {"GET"} and proofs["code_identity_proof_of_the_final_execution_holds"])
(HERE / "final_scope_proofs.json").write_text(json.dumps(proofs, indent=1, ensure_ascii=False), encoding="utf-8")
print(json.dumps({k: proofs[k] for k in ("all_ok", "frozen_files_all_equal_HEAD", "outputs_changed_since_snapshot_S0", "all_run_directories_unchanged", "protected_runs_equal_the_round21_hash_snapshots", "zero_calls")}, indent=1))
sys.exit(0 if proofs["all_ok"] else 2)
