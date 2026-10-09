#!/usr/bin/env python3
"""Read-only SHA-256 manifest of everything this closure round promised not
to modify: the original c904d4cc run, the original AMD 34-item list and its
re-verification artifacts, the historical request/response audit run, and
earlier rounds' written reports. Run before and after; compare with --diff.

Deliberately EXCLUDED (code this round edits on purpose, so it is not a
frozen historical artifact): round12's recover_alpha_classification.py.
"""
import hashlib, json, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
ROUNDS = REPO / "docs" / "audit_artifacts" / "round_source_linking_t0_t2"
ROOTS = [
    REPO / "outputs" / "runs" / "c904d4cc-dc09-495c-aec5-b056979948e1",
    REPO / "outputs" / "runs" / "phase-c-amd-21-claim-verification",
    ROUNDS / "round4_amd_34_item_reverification_20261004",
    ROUNDS / "round11_amd_fresh_run_20261006",
    ROUNDS / "round12_alpha_classifier_audit_fix_20261006",
    ROUNDS / "round13_true_concurrent_audit_fix_20261006" / "01_true_concurrent_audit_fix_report.md",
]
# server_stdout_round2.log is the stdout of a backend process that is STILL RUNNING from
# the earlier AMD launcher and keeps appending health/list polling lines; it is a live
# log, not a historical result, so it cannot be a frozen artifact.
EXCLUDE_NAMES = {"recover_alpha_classification.py", "__pycache__", ".DS_Store", "server_stdout_round2.log"}
EXCLUDE_PREFIXES = ("recovery_dry_run_report_", "dry_run_scope_")


def files():
    for root in ROOTS:
        if root.is_file():
            yield root
        elif root.is_dir():
            for p in sorted(root.rglob("*")):
                if p.is_file() and not (set(p.parts) & EXCLUDE_NAMES) and not p.name.startswith(EXCLUDE_PREFIXES):
                    yield p


def snapshot():
    return {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files()}


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--diff":
        before = {k: v for k, v in json.loads(Path(sys.argv[2]).read_text()).items()
                  if Path(k).name not in EXCLUDE_NAMES and not Path(k).name.startswith(EXCLUDE_PREFIXES)}
        after = snapshot()
        changed = sorted(k for k in before if k in after and before[k] != after[k])
        removed = sorted(k for k in before if k not in after)
        added = sorted(k for k in after if k not in before)
        print(json.dumps({"files_before": len(before), "files_after": len(after),
                          "changed": changed, "removed": removed, "added": added,
                          "identical": not (changed or removed or added)}, indent=2))
        sys.exit(0 if not (changed or removed or added) else 1)
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    snap = snapshot()
    if out:
        out.write_text(json.dumps(snap, indent=1, sort_keys=True))
    print(f"{len(snap)} protected files hashed" + (f" -> {out}" if out else ""))
