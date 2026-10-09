#!/usr/bin/env python3
"""Round 24 (T2 gap closure): proofs that this round stayed inside its scope. Read-only on the repository except for the entries it runs into temporary
directories under a network trap.

  1. HEAD is the recorded commit (no commit was made).
  2. The scoring / B2 / Alpha-level / display / source-role modules are byte-identical to HEAD (no formula, threshold or level rule changed).
  3. Since the start of this round (the mtime of test_evidence/BEFORE_t2_affected.exitcode, written before the first edit) the only repository files that
     changed are the ones round24_delta.json lists; nothing under outputs/ changed; nothing in the Round 23 package changed; no file of John's frozen
     Gold inputs, the label files or the taxonomy changed.
  4. The frozen Gold inputs still have the sha256 their freeze recorded; the label v0.2 and taxonomy files are the Round 23 ones.
  5. The 16 run directories the Round 22 manifest registers still match their recorded digests (the acceptance work only ever READ them). The verifier also
     compares the working tree with the Round 22 code snapshot; that comparison is EXPECTED to differ, so each differing file must be on the T2 file list.
  6. ZERO NETWORK: the three entries are run in-process with every socket / DNS / HTTP entry point replaced by a counter that raises.
  7. The user's services (8000 / 5175 and the read-only viewers 8001 / 5176) are still listening.

usage: python tools/final_scope_proofs.py [--outputs-file-count-before N] [--head SHA]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import socket
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent  # the Round 24 directory
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
sys.path.insert(0, str(REPO))

FROZEN_CODE = [
    "comqutor_alpha/conflict_engine/conflict_admissibility.py",
    "comqutor_alpha/conflict_engine/conflict_schema.py",
    "comqutor_alpha/graph_engine/activation_scorer.py",
    "comqutor_alpha/graph_engine/alpha_display_normalizer.py",
    "comqutor_alpha/graph_engine/alpha_level_classifier.py",
    "comqutor_alpha/graph_engine/evidence_source_role.py",
]
FROZEN_INPUTS = {
    "docs/audit_artifacts/v0_2_gold_operational_contract.json": "e2df7139e19ec998afc6335caf4d53528dd3f4356a46d4e9a88d9d04b520000f",
    "docs/audit_artifacts/v0_2_evidence_trigger_matrix.json": "3e8e7402803632198b01c2a08a98929031929cc4b909927dc7e475d37b5d22a1",
    "docs/audit_artifacts/v0_2_gold_freeze_manifest.json": "081e66b405ac039f9fe64c2689e346c6f91de1448d6405e449e49ce74e8e0540",
    "docs/audit_artifacts/v0_2_john_frozen_gold_baseline.yaml": "b8165911b78aa46fa4993a6b209d47e2b66e152547a618e2587facd97eb79a9c",
    "comqutor_alpha/config/j2_provisional_regression_labels_v0.2.yaml": "667262aaa15a94a5c660488493f7386a4e6ec6b8c02f1293927d887bf7920ba6",
    "comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml": "c6d523beaee4942c71756a3fddbb8213d4ba2f8653fded088d73031ca80f3bfa",
}
WATCHED_ROOTS = ["comqutor_alpha", "tradingagents", "cli", "evaluation", "scripts", "tests", "frontend/src", "docs/specs", "docs/audit_artifacts/v0_2_gold_operational_contract.json"]
ROUND23 = "docs/audit_artifacts/round_source_linking_t0_t2/round23_t2_completion_20261007"
MANIFEST_VERIFIER = REPO / "docs/audit_artifacts/round_source_linking_t0_t2/round22_t1_closeout_20261007/verify_release_manifest_v2.py"


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), cwd=REPO, capture_output=True, text=True)


def newer_than(marker: Path, roots: list[str]) -> list[str]:
    stamp = marker.stat().st_mtime
    found = []
    for root in roots:
        base = REPO / root
        paths = [base] if base.is_file() else [p for p in base.rglob("*") if p.is_file()] if base.exists() else []
        for p in paths:
            if "__pycache__" in p.parts or "node_modules" in p.parts or p.suffix == ".pyc":
                continue
            if p.stat().st_mtime > stamp:
                found.append(p.relative_to(REPO).as_posix())
    return sorted(found)


def network_trap_runs() -> dict:
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
        for owner, name in originals:
            setattr(owner, name, refuse(f"{getattr(owner, '__name__', owner)}.{name}"))
        import importlib.util

        for label, script in (
            ("run_formal_acceptance", "run_formal_acceptance.py"),
            ("recompute_conflicts_frozen_inputs", "recompute_conflicts_frozen_inputs.py"),
            ("build_open_review_ledger", "build_open_review_ledger.py"),
        ):
            spec = importlib.util.spec_from_file_location(f"proof_{label}", REPO / "scripts" / script)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            with tempfile.TemporaryDirectory(prefix="r24_proof_") as tmp:
                code = module.main(["--out-dir", str(Path(tmp) / "out")])
            results[label] = {"exit_code": code, "network_attempts_so_far": len(attempts)}
    finally:
        for (owner, name), original in originals.items():
            setattr(owner, name, original)
    return {"per_entry": results, "network_attempts_total": len(attempts), "attempts": attempts}


def listeners() -> dict:
    found = {}
    for line in run("lsof", "-nP", "-iTCP", "-sTCP:LISTEN").stdout.splitlines():
        for port in ("8000", "5175", "8001", "5176"):
            if f":{port} " in line + " ":
                found[port] = {"command": line.split()[0], "pid": line.split()[1]}
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outputs-file-count-before", type=int)
    parser.add_argument("--head", default="7a9aefa5c7b5c820515447c6289aeef80eac9bdc")
    args = parser.parse_args()
    marker = HERE / "test_evidence" / "BEFORE_t2_affected.exitcode"
    delta = json.loads((HERE / "round24_delta.json").read_text(encoding="utf-8"))
    t2_files = {e["path"] for e in json.loads((HERE / "t2_files.json").read_text(encoding="utf-8"))["files"]}
    expected_changed = {e["path"] for e in delta["files"]}

    head = run("git", "rev-parse", "HEAD").stdout.strip()
    frozen_code_diff = run("git", "diff", "--quiet", "HEAD", "--", *FROZEN_CODE)
    changed = newer_than(marker, WATCHED_ROOTS)
    outputs_changed = newer_than(marker, ["outputs"])
    round23_changed = newer_than(marker, [ROUND23])
    inputs = {rel: {"sha256": hashlib.sha256((REPO / rel).read_bytes()).hexdigest(), "expected": want} for rel, want in FROZEN_INPUTS.items()}
    manifest = json.loads(run(sys.executable, str(MANIFEST_VERIFIER)).stdout)
    snapshot_problems = [p for p in manifest["problems"] if p.startswith("snapshot S1_final")]
    other_problems = [p for p in manifest["problems"] if not p.startswith("snapshot S1_final")]
    differing = sorted(set(re.findall(r"'([^']+?): working-tree file differs from the snapshot'", " ".join(snapshot_problems))))
    outputs_now = int(run("sh", "-c", "find outputs -type f | wc -l").stdout.strip())
    trap = network_trap_runs()
    proofs = {
        "head": {"now": head, "expected": args.head, "unchanged": head == args.head, "note": "no commit was made"},
        "scoring_b2_level_modules_equal_head": {"files": FROZEN_CODE, "all_equal": frozen_code_diff.returncode == 0},
        "files_changed_since_the_start_of_the_round": {
            "marker": "test_evidence/BEFORE_t2_affected.exitcode (written before the first edit)",
            "watched_roots": WATCHED_ROOTS,
            "files": changed,
            "outside_the_round24_delta": sorted(set(changed) - expected_changed),
            "round24_delta_files_not_changed": sorted(expected_changed - set(changed)),
            "ok": not (set(changed) - expected_changed),
        },
        "outputs_changed_since_the_start_of_the_round": {"files": outputs_changed, "ok": not outputs_changed},
        "round23_package_changed_since_the_start_of_the_round": {"files": round23_changed, "ok": not round23_changed},
        "frozen_inputs_unchanged": {"files": inputs, "ok": all(v["sha256"] == v["expected"] for v in inputs.values())},
        "registered_run_directories_unchanged": {
            "verifier": str(MANIFEST_VERIFIER.relative_to(REPO)),
            "checked": manifest["checked"],
            "problems_other_than_the_round22_snapshot_comparison": other_problems,
            "ok": not other_problems and manifest["checked"]["run_directories"] == 16,
        },
        "files_differing_from_the_round22_snapshot_are_all_on_the_t2_list": {
            "files": differing,
            "outside_the_t2_file_list": sorted(set(differing) - t2_files),
            "ok": not (set(differing) - t2_files),
        },
        "outputs_file_count": {"before": args.outputs_file_count_before, "now": outputs_now, "unchanged": args.outputs_file_count_before is None or args.outputs_file_count_before == outputs_now},
        "zero_network": {**trap, "ok": trap["network_attempts_total"] == 0 and all(r["exit_code"] == 0 for r in trap["per_entry"].values())},
        "services_listening": listeners(),
    }
    proofs["all_ok"] = all(
        [
            proofs["head"]["unchanged"],
            proofs["scoring_b2_level_modules_equal_head"]["all_equal"],
            proofs["files_changed_since_the_start_of_the_round"]["ok"],
            proofs["outputs_changed_since_the_start_of_the_round"]["ok"],
            proofs["round23_package_changed_since_the_start_of_the_round"]["ok"],
            proofs["frozen_inputs_unchanged"]["ok"],
            proofs["registered_run_directories_unchanged"]["ok"],
            proofs["files_differing_from_the_round22_snapshot_are_all_on_the_t2_list"]["ok"],
            proofs["outputs_file_count"]["unchanged"],
            proofs["zero_network"]["ok"],
            set(proofs["services_listening"]) >= {"8000", "5175"},
        ]
    )
    (HERE / "final_scope_proofs.json").write_text(json.dumps(proofs, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    summary = {
        "head_unchanged": proofs["head"]["unchanged"],
        "scoring_b2_level_modules_equal_head": proofs["scoring_b2_level_modules_equal_head"]["all_equal"],
        "changed_since_start_all_in_delta": proofs["files_changed_since_the_start_of_the_round"]["ok"],
        "outside_the_delta": proofs["files_changed_since_the_start_of_the_round"]["outside_the_round24_delta"],
        "outputs_changed": proofs["outputs_changed_since_the_start_of_the_round"]["files"],
        "round23_package_changed": proofs["round23_package_changed_since_the_start_of_the_round"]["files"],
        "frozen_inputs_unchanged": proofs["frozen_inputs_unchanged"]["ok"],
        "run_directories_unchanged": proofs["registered_run_directories_unchanged"]["ok"],
        "outputs_file_count": proofs["outputs_file_count"],
        "network_attempts_total": proofs["zero_network"]["network_attempts_total"],
        "services_listening": proofs["services_listening"],
        "all_ok": proofs["all_ok"],
    }
    print(json.dumps(summary, indent=1))
    return 0 if proofs["all_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
