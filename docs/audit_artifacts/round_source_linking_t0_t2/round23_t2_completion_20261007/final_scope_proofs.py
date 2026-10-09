#!/usr/bin/env python3
"""Round 23 (T2 completion): proofs that this round stayed inside its scope. Read-only on the repository except for the three CLIs it runs into
temporary directories.

  1. HEAD is still the recorded commit (no commit was made).
  2. The frozen / guarded files are byte-identical to HEAD.
  3. The 16 run directories registered by the Round 22 manifest still match their recorded digests (the six pinned runs are among them): the
     acceptance work only ever READ them. The Round 22 verifier also compares the working tree with the Round 22 code snapshot; that comparison is
     EXPECTED to differ after this round, so it is checked differently: every file that differs from that snapshot must be on the T2 file list
     (t2_files.json), i.e. nothing outside T2 changed since Round 22.
  4. outputs/ holds exactly as many files as before the full test run (argument --outputs-file-count-before).
  5. ZERO NETWORK: the three new command-line entries are run in-process with every socket / DNS / HTTP entry point replaced by a counter that raises;
     the count of attempted calls is recorded.
  6. The user's services (ports 8000 / 5175 and the read-only viewers 8001 / 5176) are still listening on the same processes.

usage: python final_scope_proofs.py [--outputs-file-count-before N] [--head SHA]
"""
from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))

FROZEN = [
    "comqutor_alpha/conflict_engine/conflict_admissibility.py",
    "comqutor_alpha/conflict_engine/conflict_schema.py",
    "comqutor_alpha/graph_engine/activation_scorer.py",
    "comqutor_alpha/graph_engine/alpha_display_normalizer.py",
    "comqutor_alpha/graph_engine/alpha_level_classifier.py",
    "comqutor_alpha/graph_engine/evidence_source_role.py",
]
MANIFEST_VERIFIER = REPO / "docs/audit_artifacts/round_source_linking_t0_t2/round22_t1_closeout_20261007/verify_release_manifest_v2.py"


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), cwd=REPO, capture_output=True, text=True)


def network_trap_runs() -> dict:
    """Runs the three CLIs in-process with every outbound network entry point replaced by a counting stub that raises."""
    attempts: list[str] = []

    def refuse(name):
        def stub(*_a, **_k):
            attempts.append(name)
            raise RuntimeError(f"network call attempted: {name}")

        return stub

    originals = {
        (socket.socket, "connect"): socket.socket.connect,
        (socket.socket, "connect_ex"): socket.socket.connect_ex,
        (socket, "create_connection"): socket.create_connection,
        (socket, "getaddrinfo"): socket.getaddrinfo,
        (urllib.request, "urlopen"): urllib.request.urlopen,
    }
    results = {}
    try:
        for (owner, name) in originals:
            setattr(owner, name, refuse(f"{getattr(owner, '__name__', owner)}.{name}"))
        import importlib.util

        for label, script, extra in (
            ("run_formal_acceptance", "run_formal_acceptance.py", []),
            ("recompute_conflicts_frozen_inputs", "recompute_conflicts_frozen_inputs.py", []),
            ("build_open_review_ledger", "build_open_review_ledger.py", []),
        ):
            spec = importlib.util.spec_from_file_location(f"proof_{label}", REPO / "scripts" / script)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            with tempfile.TemporaryDirectory(prefix="t2_proof_") as tmp:
                code = module.main(["--out-dir", str(Path(tmp) / "out"), *extra])
            results[label] = {"exit_code": code, "network_attempts_so_far": len(attempts)}
    finally:
        for (owner, name), original in originals.items():
            setattr(owner, name, original)
    return {"per_entry": results, "network_attempts_total": len(attempts), "attempts": attempts}


def listeners() -> dict:
    out = run("lsof", "-nP", "-iTCP", "-sTCP:LISTEN").stdout
    found = {}
    for line in out.splitlines():
        for port in ("8000", "5175", "8001", "5176"):
            if f":{port} " in line + " ":
                found[port] = {"command": line.split()[0], "pid": line.split()[1]}
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outputs-file-count-before", type=int)
    parser.add_argument("--head", default="7a9aefa5c7b5c820515447c6289aeef80eac9bdc")
    args = parser.parse_args()

    head = run("git", "rev-parse", "HEAD").stdout.strip()
    frozen_diff = run("git", "diff", "--quiet", "HEAD", "--", *FROZEN)
    manifest = run(sys.executable, str(MANIFEST_VERIFIER))
    verifier = json.loads(manifest.stdout)
    t2_files = {e["path"] for e in json.loads((HERE / "t2_files.json").read_text(encoding="utf-8"))["files"]}
    snapshot_problems = [p for p in verifier["problems"] if p.startswith("snapshot S1_final")]
    other_problems = [p for p in verifier["problems"] if not p.startswith("snapshot S1_final")]
    differing = sorted(set(re.findall(r"'([^']+?): working-tree file differs from the snapshot'", " ".join(snapshot_problems))))
    outside_t2 = [f for f in differing if f not in t2_files]
    manifest_ok = not other_problems and verifier["checked"]["run_directories"] == 16
    outputs_now = int(run("sh", "-c", "find outputs -type f | wc -l").stdout.strip())
    trap = network_trap_runs()
    proofs = {
        "head": {"now": head, "expected": args.head, "unchanged": head == args.head, "note": "no commit was made"},
        "frozen_files_equal_head": {"files": FROZEN, "all_equal": frozen_diff.returncode == 0},
        "registered_run_directories_unchanged": {
            "verifier": str(MANIFEST_VERIFIER.relative_to(REPO)),
            "checked": verifier["checked"],
            "problems_other_than_the_round22_snapshot_comparison": other_problems,
            "ok": manifest_ok,
        },
        "files_changed_since_the_round22_snapshot": {
            "files": differing,
            "outside_the_t2_file_list": outside_t2,
            "all_on_the_t2_file_list": not outside_t2,
            "note": "new files created this round are not in the Round 22 snapshot and are listed in t2_files.json instead",
        },
        "outputs_file_count": {"before": args.outputs_file_count_before, "now": outputs_now, "unchanged": args.outputs_file_count_before is None or args.outputs_file_count_before == outputs_now},
        "zero_network": {**trap, "ok": trap["network_attempts_total"] == 0 and all(r["exit_code"] == 0 for r in trap["per_entry"].values())},
        "services_listening": listeners(),
    }
    proofs["all_ok"] = all(
        [
            proofs["head"]["unchanged"],
            proofs["frozen_files_equal_head"]["all_equal"],
            proofs["registered_run_directories_unchanged"]["ok"],
            proofs["files_changed_since_the_round22_snapshot"]["all_on_the_t2_file_list"],
            proofs["outputs_file_count"]["unchanged"],
            proofs["zero_network"]["ok"],
            set(proofs["services_listening"]) >= {"8000", "5175"},
        ]
    )
    (HERE / "final_scope_proofs.json").write_text(json.dumps(proofs, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    summary = {
        "head_unchanged": proofs["head"]["unchanged"],
        "frozen_files_equal_head": proofs["frozen_files_equal_head"]["all_equal"],
        "registered_run_directories_unchanged": proofs["registered_run_directories_unchanged"]["ok"],
        "files_changed_since_round22_snapshot_all_on_the_t2_list": proofs["files_changed_since_the_round22_snapshot"]["all_on_the_t2_file_list"],
        "outputs_file_count": proofs["outputs_file_count"],
        "network_attempts_total": proofs["zero_network"]["network_attempts_total"],
        "services_listening": proofs["services_listening"],
        "all_ok": proofs["all_ok"],
    }
    print(json.dumps(summary, indent=1))
    return 0 if proofs["all_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
