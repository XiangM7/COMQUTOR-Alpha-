#!/usr/bin/env python3
"""T4 Phase A: persist frozen materials into the T4 PostgreSQL database through the production derived-run path (zero network).

For each frozen base run: copy its directory from outputs/runs into the T4 output directory (outputs/t4_runs), byte for byte and
hash-verified (the original is only read), then call the production
``classification_recovery.finalize_classification_recovery_execution`` with the base run's own alpha_matches reused verbatim -- an
old-result re-evaluation: the production week-3/week-4 pipeline, a research_runs row, the graph/match/activation/conflict rows and
the artifact manifest, all written through ``build_write_repository_from_env`` to comqutor_alpha_t4_test. No model, search or
data call is made (run under the network trap).

    python run_with_network_trap.py persist_frozen_runs.py --report 01_postgres/frozen_runs_persisted.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
SOURCE_ROOT = REPO / "outputs" / "runs"
T4_ROOT = REPO / "outputs" / "t4_runs"
T4_DB = "comqutor_alpha_t4_test"
BASES = {
    # final AMD execution of the T1 work (source links, verified-evidence gate, evidence trace); root run c904d4cc
    "amd_dependency": {"base": "dependency-20261007T220450Z-33128621", "root": "c904d4cc-dc09-495c-aec5-b056979948e1"},
    # historical SNDK run whose saved result has no main conflict (John: "SNDK 保留历史无主冲突展示")
    "sndk_historical": {"base": "52c23371-c374-4064-a91c-20c599ffa79c", "root": "52c23371-c374-4064-a91c-20c599ffa79c"},
}


def _tree_hashes(directory: Path) -> dict[str, str]:
    return {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(directory.rglob("*")) if p.is_file()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    args = ap.parse_args(argv)
    url = subprocess.run([sys.executable, str(HERE / "create_t4_databases.py"), "--print-url-for", T4_DB],
                         capture_output=True, text=True, check=True).stdout.strip()
    os.environ.update({"COMQUTOR_DATABASE_URL": url, "COMQUTOR_REQUIRE_DATABASE_NAME": T4_DB, "COMQUTOR_REQUIRE_DATABASE_DIALECT": "postgresql",
                       "COMQUTOR_WEEK2_LLM_ENABLED": "false", "COMQUTOR_REAL_TRADINGAGENTS_ENABLED": "false"})
    from comqutor_alpha.api.artifact_export import build_and_write_artifact_manifest
    from comqutor_alpha.classification_recovery import (
        DEPENDENCY_EXECUTION_MODE,
        DEPENDENCY_EXECUTION_TYPE,
        DEPENDENCY_LINEAGE_FILENAME,
        finalize_classification_recovery_execution,
        new_dependency_execution_id,
    )
    from comqutor_alpha.storage.db.repository import build_write_repository_from_env

    T4_ROOT.mkdir(parents=True, exist_ok=True)
    repository = build_write_repository_from_env(str(T4_ROOT))
    report = {"database": T4_DB, "output_root": str(T4_ROOT.relative_to(REPO)), "runs": {}}
    for label, spec in BASES.items():
        source, copy = SOURCE_ROOT / spec["base"], T4_ROOT / spec["base"]
        if copy.exists():
            print(f"refusing: {copy} exists", file=sys.stderr)
            return 2
        original_before = _tree_hashes(source)
        shutil.copytree(source, copy)
        copy_hashes = _tree_hashes(copy)
        metadata = json.loads((copy / "metadata.json").read_text(encoding="utf-8"))
        payload = json.loads((copy / "alpha_matches.json").read_text(encoding="utf-8"))
        execution_id = new_dependency_execution_id()
        extras = {k: metadata[k] for k in ("fact_dependency_contract",) if k in metadata}
        finalized = finalize_classification_recovery_execution(
            spec["base"], execution_id, assembled_alpha_matches=payload,
            recovery_provenance={"checkpoint_origin": "real", "note": "T4 PostgreSQL verification: frozen material re-evaluated through the "
                                 "production derived-run path; alpha_matches, structured records and source registry reused verbatim"},
            output_root=T4_ROOT, graph_repository=repository, execution_type=DEPENDENCY_EXECUTION_TYPE,
            execution_mode=DEPENDENCY_EXECUTION_MODE, lineage_filename=DEPENDENCY_LINEAGE_FILENAME,
            assembled_transformation="reused_verbatim_from_parent", root_run_id=spec["root"], metadata_extras=extras or None,
            lineage_extras={"purpose": "T4 Phase A PostgreSQL chain verification", "model_calls": 0, "searches": 0, "data_fetches": 0})
        manifest = None
        if finalized.get("status") == "ok":
            manifest = build_and_write_artifact_manifest(run_id=execution_id, ticker=metadata["ticker"], output_root=T4_ROOT)
        report["runs"][label] = {
            "base_run_id": spec["base"], "root_run_id": spec["root"], "execution_id": execution_id, "ticker": metadata["ticker"],
            "copy_byte_identical_to_original": copy_hashes == original_before, "files_copied": len(copy_hashes),
            "original_unchanged": _tree_hashes(source) == original_before,
            "finalized": {k: finalized.get(k) for k in ("status", "error_code", "run_status", "base_run_unchanged") if k in finalized},
            "artifact_completeness": (manifest or {}).get("artifact_completeness") if isinstance(manifest, dict) else None,
        }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, default=str))
    return 0 if all(r["finalized"].get("status") == "ok" for r in report["runs"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
