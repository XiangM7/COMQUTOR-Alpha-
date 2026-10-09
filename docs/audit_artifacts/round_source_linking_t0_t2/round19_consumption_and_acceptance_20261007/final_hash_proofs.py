#!/usr/bin/env python3
"""Round 19 -- hash proofs that history was not touched and exactly what production code changed. Read-only. Writes final_hash_proofs.json beside itself.

  1. production tree: diff against the snapshot taken at the START of round 19 (expected: exactly the one reviewed read-time fix)
  2. original / recovery / direction / re-qualification run directories: byte-identical to their start-of-round hashes
  3. the historical AMD run d5b60b8a (the 34 items' run): the six SHA-256 values recorded by round 4 on 2026-10-04 are re-checked today
  4. the protected set (round-14 inventory) and both 34-item ledgers
"""
import hashlib, json, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))
from comqutor_alpha.classification_recovery import snapshot_directory_hashes

runs = REPO / "outputs" / "runs"
out = {"checks": {}}


def record(name, ok, **info):
    out["checks"][name] = {"ok": bool(ok), **info}
    print(("PASS " if ok else "FAIL ") + name, json.dumps(info, ensure_ascii=False, default=str)[:260])


# 1 -- production tree
before = json.loads((HERE / "production_tree_hashes_before_round19.json").read_text())["files"]
now = {}
for pattern in ("comqutor_alpha/**/*.py", "comqutor_alpha/**/*.yaml", "scripts/*.sh", "frontend/src/**/*.ts", "frontend/src/**/*.tsx"):
    for p in sorted(REPO.glob(pattern)):
        if p.is_file() and "__pycache__" not in p.parts and not p.name.endswith((".test.ts", ".test.tsx")):
            now[str(p.relative_to(REPO))] = hashlib.sha256(p.read_bytes()).hexdigest()
changed = sorted(k for k in set(before) | set(now) if before.get(k) != now.get(k))
backend_changed = [k for k in changed if not k.startswith("frontend/")]
frontend_changed = [k for k in changed if k.startswith("frontend/")]
record("backend_production_changes_this_round_are_exactly_the_one_reviewed_fix", backend_changed == ["comqutor_alpha/api/agent_output_reader.py"], files_before=len(before), files_now=len(now), backend_changed=backend_changed,
       note="the single reviewed change: read-time diagnostic receives the saved citation list (pre-change copy + SHA256SUMS in pre_change_snapshot_read_time_fix/)")
import time
record("frontend_files_changed_during_round19_by_someone_else_DISCLOSED_NOT_REVERTED", True, count=len(frontend_changed),
       files=[{"path": k, "change": "added" if k not in before else "modified", "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime((REPO / k).stat().st_mtime)), "sha256": now.get(k)} for k in frontend_changed],
       note="NOT authored by this round: no frontend file was edited by round 19. They appeared after the 11:31 snapshot (11:33-11:46) while ANOTHER Claude Code session was working in the same tree "
            "(its own memory note 'comqutor-ui-redesign-progress' says: frontend home-page /research redesign, uncommitted, directly in the main folder). Left exactly as found; "
            "the browser walkthrough ran against whatever the Vite dev server served at that time.")

# 2 -- run directories
for label, rid, fname in (("original_run", "c904d4cc-dc09-495c-aec5-b056979948e1", "original"), ("recovery_run", "recovery-20261007T053635Z-26d6cd1a", "recovery"),
                          ("direction_execution", "direction-20261007T065826Z-d311b8e2", "direction"), ("requalification_run", "requal-20261007T174744Z-664040d6", "requalification")):
    b = json.loads((HERE / f"{fname}_run_hashes_before_round19.json").read_text())
    n = snapshot_directory_hashes(runs / rid)
    record(f"{label}_byte_identical_to_start_of_round19", n == b, files=len(b), changed=sorted(k for k in set(n) | set(b) if n.get(k) != b.get(k)))

# 3 -- historical AMD run (the 34 items)
log = (REPO / "docs/audit_artifacts/round_source_linking_t0_t2/round4_amd_34_item_reverification_20261004/03_amd_run_readonly_integrity_check.log").read_text()
recorded = {m.group(2): m.group(1) for m in re.finditer(r"^([0-9a-f]{64})\s+(\S+)$", log, flags=re.M)}
mismatch = {p: (h, hashlib.sha256((REPO / p).read_bytes()).hexdigest()) for p, h in recorded.items() if hashlib.sha256((REPO / p).read_bytes()).hexdigest() != h}
newer = subprocess.run(["find", str(runs / "d5b60b8a-66b8-44c1-9f55-ee345e58c48d"), "-type", "f", "-newermt", "2026-10-07 11:00:00"], capture_output=True, text=True).stdout.split()
record("historical_amd_run_d5b60b8a_unchanged_since_round4", len(recorded) == 6 and not mismatch and not newer, hashes_recorded_2026_10_04=len(recorded), mismatches=mismatch, files_modified_since_round19_began=len(newer))

# 4 -- protected set and the 34-item ledgers
p = subprocess.run([str(REPO / ".venv/bin/python"), str(REPO / "docs/audit_artifacts/round_source_linking_t0_t2/round14_recovery_closure_20261006/snapshot_protected_hashes.py"), "--diff",
                    str(REPO / "docs/audit_artifacts/round_source_linking_t0_t2/round14_recovery_closure_20261006/protected_files_hashes_before.json")], capture_output=True, text=True)
verdict = json.loads(p.stdout[p.stdout.index("{"):])
record("protected_set_identical", verdict.get("identical") is True and not verdict.get("changed") and not verdict.get("removed") and not verdict.get("added"), changed=verdict.get("changed"), removed=verdict.get("removed"), added=verdict.get("added"))
ledgers = {"amd_34_item_ledger.json": "docs/audit_artifacts/round_source_linking_t0_t2/amd_34_item_ledger.json",
           "round4_ledger_v3": "docs/audit_artifacts/round_source_linking_t0_t2/round4_amd_34_item_reverification_20261004/02_amd_34_item_ledger_v3_CURRENT_MECHANISM.json"}
record("original_34_item_ledgers_hashes", True, **{k: hashlib.sha256((REPO / v).read_bytes()).hexdigest() for k, v in ledgers.items()},
       note="read-only inputs of the round-19 list; the protected-set check above already covers the ledger files")
(HERE / "final_hash_proofs.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
bad = [k for k, v in out["checks"].items() if not v["ok"]]
print("FAILED:", bad or "none")
sys.exit(1 if bad else 0)
