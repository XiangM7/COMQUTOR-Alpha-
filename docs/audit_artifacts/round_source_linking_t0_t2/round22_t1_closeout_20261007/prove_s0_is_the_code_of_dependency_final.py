#!/usr/bin/env python3
"""Round 22: why snapshot S0 (the working tree immediately before Round 22 changed anything) is the code identity of the final offline
execution ``dependency-20261007T220450Z-33128621``. Read-only; writes ``s0_is_the_code_of_dependency_final.json`` next to this script.

Evidence, each independently checkable except check 1 (a one-time check, recorded as such):
  1. no backend / dataflow / script Python file was modified between the execution and the snapshot (checked immediately before S0 was
     taken -- recorded, NOT re-runnable now because Round 22 has changed files since);
  2. every such file Round 22 did NOT touch (sha256 equals S0) has a modification time at or before the execution -- re-checked now;
  3. the files Round 22 DID change are listed (their S0 content is in the snapshot);
  4. S0's own evidence-trace builder, run on the saved execution, reproduces its saved ``evidence_trace.json`` exactly (the one artifact of
     the execution that is produced by code Round 22 later changed);
  5. today's production pipeline, dry-run on the same frozen inputs, reproduces the comparison recorded for the execution (no functional drift
     of the Evidence Fact / Activation / Conflict recomputation).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))
FINAL = "dependency-20261007T220450Z-33128621"
RUN = REPO / "outputs" / "runs" / FINAL
S0 = HERE / "code_snapshots" / "S0_before_round22"
ROUND21 = REPO / "docs/audit_artifacts/round_source_linking_t0_t2/round21_t1_minimal_closure_20261007"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


executed_at = (RUN / "metadata.json").stat().st_mtime
s0_hashes = json.loads((S0 / "file_hashes.json").read_text(encoding="utf-8"))
s0_head = json.loads((S0 / "HEAD.json").read_text(encoding="utf-8"))

code_roots = ("comqutor_alpha/", "tradingagents/", "scripts/")
unchanged_ok, unchanged_newer, changed = 0, [], []
for path in sorted(p for p in REPO.glob("**/*.py") if "__pycache__" not in p.parts and ".venv" not in p.parts and "node_modules" not in p.parts):
    rel = str(path.relative_to(REPO))
    if not rel.startswith(code_roots):
        continue
    recorded = s0_hashes.get(rel)
    if recorded is None:  # tracked and identical to HEAD at S0 (not in the dirty list), or created after S0
        head_clean = True
    else:
        head_clean = False
    if recorded is not None and sha(path) != recorded["sha256"]:
        changed.append(rel)
        continue
    if recorded is None:
        # a file absent from S0's dirty list is identical to HEAD at S0; if it differs from S0 now it is listed by git diff -- skip, covered below
        import subprocess
        differs = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", rel], cwd=REPO).returncode != 0
        untracked = subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=REPO, capture_output=True).returncode != 0
        if differs or untracked:
            changed.append(rel)
            continue
    if path.stat().st_mtime <= executed_at:
        unchanged_ok += 1
    else:
        unchanged_newer.append(rel)

# check 4: S0's own trace builder reproduces the saved artifact
spec = importlib.util.spec_from_file_location("evidence_trace_S0", S0 / "untracked_source" / "comqutor_alpha" / "api" / "evidence_trace.py")
s0_trace = importlib.util.module_from_spec(spec)
sys.modules["evidence_trace_S0"] = s0_trace  # a module with dataclasses must be registered before it executes
spec.loader.exec_module(s0_trace)  # type: ignore[union-attr]
rebuilt = s0_trace.build_evidence_trace_artifact(FINAL, REPO / "outputs" / "runs")
saved = json.loads((RUN / "evidence_trace.json").read_text(encoding="utf-8"))
trace_equal = json.dumps(rebuilt, sort_keys=True) == json.dumps(saved, sort_keys=True)

# check 5: today's pipeline dry-run on the frozen inputs equals the comparison recorded for the execution
spec5 = importlib.util.spec_from_file_location("run_dependency_recompute_r21", ROUND21 / "run_dependency_recompute.py")
module = importlib.util.module_from_spec(spec5)
sys.modules["run_dependency_recompute_r21"] = module
spec5.loader.exec_module(module)  # type: ignore[union-attr]
module.HERE = HERE  # the dry run writes its result next to THIS script, never into the Round 21 folder
module.run_dry_run()
dry_now = json.loads((HERE / "dependency_dry_run_result.json").read_text(encoding="utf-8"))
dry_recorded = json.loads((ROUND21 / "dependency_dry_run_result.json").read_text(encoding="utf-8"))

result = {
    "execution": FINAL, "execution_files_last_written_local": datetime.fromtimestamp(executed_at).isoformat(timespec="seconds"),
    "snapshot_S0": {"dir": str(S0.relative_to(REPO)), "created_at_utc": s0_head["created_at_utc"], "head_sha": s0_head["head_sha"]},
    "check_1_no_code_file_changed_between_execution_and_snapshot": {
        "performed": "immediately before S0 was taken, before any Round 22 edit",
        "command": f"find comqutor_alpha tradingagents scripts -name '*.py' -newer outputs/runs/{FINAL}/metadata.json -not -path '*/__pycache__/*'",
        "result": "no file", "re_runnable_now": False, "why_not": "Round 22 has since modified code files, so the same command now lists them",
    },
    "check_2_untouched_code_files_were_last_modified_before_the_execution": {"checked": unchanged_ok + len(unchanged_newer), "modified_after_the_execution": unchanged_newer},
    "check_3_code_files_changed_by_round22": changed,
    "check_4_s0_trace_builder_reproduces_the_saved_evidence_trace": {"items": saved.get("item_count"), "equal": trace_equal},
    "check_5_current_pipeline_reproduces_the_recorded_dry_run_comparison": {"equal": dry_now["comparison"] == dry_recorded["comparison"],
                                                                            "zero_call_attempts": dry_now["zero_call"]["attempted_provider_or_network_calls"]},
}
ok = (not unchanged_newer) and trace_equal and result["check_5_current_pipeline_reproduces_the_recorded_dry_run_comparison"]["equal"]
result["basis"] = (
    "S0 is the code of this execution: no code file changed between the execution and S0 (check 1, one-time); every code file Round 22 left untouched "
    "predates the execution (check 2); S0's own trace builder reproduces the execution's saved evidence_trace.json exactly (check 4); and today's "
    "pipeline reproduces the recorded recompute (check 5). The files Round 22 changed afterwards are listed (check 3)." if ok else
    "NOT PROVEN -- see the checks"
)
result["proven"] = bool(ok)
(HERE / "s0_is_the_code_of_dependency_final.json").write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
print(json.dumps({k: result[k] for k in ("proven", "check_2_untouched_code_files_were_last_modified_before_the_execution", "check_4_s0_trace_builder_reproduces_the_saved_evidence_trace",
                                         "check_5_current_pipeline_reproduces_the_recorded_dry_run_comparison")}, indent=1), "\nchanged by round22:", len(changed))
sys.exit(0 if ok else 3)
