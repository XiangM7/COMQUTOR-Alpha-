#!/usr/bin/env python3
"""Round 22 (T0 delivery identity): build ``release_manifest_v2.json`` -- the machine-readable answer to "which code, input, model, rules
and logs produced this result file?" for the AMD / NVDA runs and every derived execution of the T1 chain.

Principles
  * every identity statement points at a FILE THAT EXISTS in the delivery (a code snapshot, a copied identity file, or a repo-relative path
    inside the working tree) and carries its sha256 -- never a hash alone;
  * nothing is backfilled from the current configuration: what a run did not record is written ``NOT_RECORDED`` / ``UNKNOWN`` with the reason;
  * code identity: the real HEAD + the complete uncommitted difference + the untracked source files (snapshots), nothing committed;
  * the old ``release_manifest.json`` (2026-10-01) is kept untouched and referenced.

Read-only on ``outputs/``; writes only under the Round 22 directory.

usage: build_release_manifest_v2.py --s0 <S0 snapshot dir> --s1 <S1 snapshot dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import sys
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))
ROUND_DIRS = REPO / "docs" / "audit_artifacts" / "round_source_linking_t0_t2"
OLD_MANIFEST = ROUND_DIRS / "release_manifest.json"
OUTPUTS = REPO / "outputs" / "runs"
IDENTITY_DIR = HERE / "run_identity_files"
DIRECTORY_HASH_DIR = HERE / "run_directory_hashes"

# --- John's three execution types (task sheet T0), as this manifest classifies each entry -------------------------------------
FRESH = "FRESH_RUN"
FROZEN_RECOMPUTE = "FROZEN_INPUT_RECOMPUTE"
REEVALUATION = "RESULT_REEVALUATION"

RUNS: list[dict] = [
    {"run_id": "d5b60b8a-66b8-44c1-9f55-ee345e58c48d", "role": "original_research_run", "execution_type": FRESH,
     "note": "the run of John's original 34 conflict-evidence items (evidence cutoff 2026-09-21); it predates source linking"},
    {"run_id": "034a0a60-430e-41f8-8321-03a11389707a", "role": "original_research_run", "execution_type": FRESH, "note": "NVDA; first real run after source capture was added"},
    {"run_id": "1bad76a7-72ac-4c8b-8189-2e5c0f1a6105", "role": "original_research_run", "execution_type": FRESH, "note": "AMD 2026-10-05"},
    {"run_id": "automated-eligibility-reeval-20261005T190101Z-d9b7fdba", "role": "derived_execution", "execution_type": REEVALUATION, "parent": "1bad76a7-72ac-4c8b-8189-2e5c0f1a6105"},
    {"run_id": "review-20261006T001859Z-ec6000de", "role": "derived_execution", "execution_type": FROZEN_RECOMPUTE, "parent": "1bad76a7-72ac-4c8b-8189-2e5c0f1a6105"},
    {"run_id": "review-20261006T001911Z-14407742", "role": "derived_execution", "execution_type": FROZEN_RECOMPUTE, "parent": "1bad76a7-72ac-4c8b-8189-2e5c0f1a6105"},
    {"run_id": "review-20261006T035219Z-884106de", "role": "derived_execution", "execution_type": FROZEN_RECOMPUTE, "parent": "1bad76a7-72ac-4c8b-8189-2e5c0f1a6105"},
    {"run_id": "review-20261006T035335Z-3d569e97", "role": "derived_execution", "execution_type": FROZEN_RECOMPUTE, "parent": "1bad76a7-72ac-4c8b-8189-2e5c0f1a6105"},
    {"run_id": "91d7c420-6197-46c3-93f9-bd42792c1ff7", "role": "original_research_run", "execution_type": FRESH, "note": "AMD 2026-10-06 (an earlier attempt of the same day)"},
    {"run_id": "91d7c420-6197-46c3-93f9-bd42792c1ff7-postproc-01", "role": "derived_execution", "execution_type": REEVALUATION, "parent": "91d7c420-6197-46c3-93f9-bd42792c1ff7"},
    {"run_id": "c904d4cc-dc09-495c-aec5-b056979948e1", "role": "original_research_run", "execution_type": FRESH, "note": "AMD 2026-10-06: the run the T1 chain of Rounds 16-22 is built on"},
    {"run_id": "recovery-20261007T053635Z-26d6cd1a", "role": "derived_execution", "execution_type": FROZEN_RECOMPUTE, "parent": "c904d4cc-dc09-495c-aec5-b056979948e1",
     "note": "973 alpha_classifier requests on the frozen inputs (real model calls); everything else reused"},
    {"run_id": "direction-20261007T065826Z-d311b8e2", "role": "execution_attempt_without_derived_run", "execution_type": FROZEN_RECOMPUTE, "parent": "recovery-20261007T053635Z-26d6cd1a",
     "note": "stopped by the frozen protocol after the first batch timed out; produced no model direction result and no derived run"},
    {"run_id": "requal-20261007T174744Z-664040d6", "role": "derived_execution", "execution_type": REEVALUATION, "parent": "recovery-20261007T053635Z-26d6cd1a", "note": "zero model calls"},
    {"run_id": "dependency-20261007T213234Z-3be0399d", "role": "derived_execution", "execution_type": REEVALUATION, "parent": "requal-20261007T174744Z-664040d6",
     "note": "interim (superseded, kept); zero model calls"},
    {"run_id": "dependency-20261007T220450Z-33128621", "role": "derived_execution", "execution_type": REEVALUATION, "parent": "requal-20261007T174744Z-664040d6",
     "note": "final; zero model calls; code identity = snapshot S0 (see code_identity)"},
]
IDENTITY_FILENAMES = ("metadata.json", "artifact_manifest.json", "llm_semantic_manifest.json", "tradingagents_llm_usage_summary.json",
                      "recovery_lineage.json", "requalification_lineage.json", "direction_lineage.json", "dependency_lineage.json",
                      "checkpoint_direction.json", "direction_results_when_stopped.json")
LOG_PATTERNS = ("llm_semantic_calls.jsonl", "tradingagents_llm_calls.jsonl", "recovery_match_records.jsonl", "error_logs")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(path: Path) -> str:
    return str(path.relative_to(REPO))


def entry(path: Path) -> dict:
    return {"path": rel(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def jload(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def directory_digest(run_dir: Path) -> dict:
    files = {str(p.relative_to(run_dir)): sha256_file(p) for p in sorted(run_dir.rglob("*")) if p.is_file()}
    digest = hashlib.sha256("\n".join(f"{k}\t{v}" for k, v in sorted(files.items())).encode("utf-8")).hexdigest()
    DIRECTORY_HASH_DIR.mkdir(parents=True, exist_ok=True)
    (DIRECTORY_HASH_DIR / f"{run_dir.name}.json").write_text(json.dumps({"run_id": run_dir.name, "file_count": len(files), "files": files}, indent=1, sort_keys=True), encoding="utf-8")
    return {"file_count": len(files), "directory_digest_sha256": digest, "per_file_hashes": rel(DIRECTORY_HASH_DIR / f"{run_dir.name}.json"),
            "content_location": rel(run_dir) + "/ (in the working tree; package with README step 6)"}


def prompt_texts() -> dict[str, dict]:
    """The prompt identity text of every Week2 semantic task, from the code being delivered, written out as files. A prompt whose sha256 equals the
    one a run recorded IS the text that run used (equal hash = equal text), whatever the run's own code identity is."""
    from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway, _TASK_RUNTIME_METADATA

    out_dir = HERE / "prompt_texts"
    out_dir.mkdir(parents=True, exist_ok=True)
    by_sha: dict[str, dict] = {}
    for task, meta in sorted(_TASK_RUNTIME_METADATA.items()):
        text = Week2LLMGateway.prompt_identity_text(task)
        digest = Week2LLMGateway.prompt_identity_sha256(task)
        target = out_dir / f"{meta['semantic_task']}__{meta['prompt_version']}.txt"
        target.write_text(text, encoding="utf-8")
        by_sha[digest] = {"task": meta["semantic_task"], "prompt_version": meta["prompt_version"], "file": rel(target), "sha256": digest}
    return by_sha


def model_identity(run_dir: Path, prompts: dict[str, dict], role: str, lineage: dict | None) -> dict:
    meta = jload(run_dir / "metadata.json") or {}
    recorded = {"provider": meta.get("llm_provider"), "quick_model": meta.get("quick_model"), "deep_model": meta.get("deep_model"), "recorded_in": "metadata.json"}
    if role == "derived_execution":
        # a derived execution runs no research agent: its metadata is the root run's, copied verbatim
        out: dict = {"research_agents": "INHERITED_FROM_ROOT_RUN (no research agent ran in this execution; its metadata.json is the root run's, copied verbatim)",
                     "inherited_metadata": recorded if meta.get("llm_provider") else "NOT_RECORDED"}
        if lineage and "model_calls" in lineage:
            out["model_calls"] = {"recorded": lineage["model_calls"], "searches": lineage.get("searches"), "data_fetches": lineage.get("data_fetches"), "recorded_in": lineage["file"]}
        elif not (run_dir / "llm_semantic_calls.jsonl").is_file():
            out["model_calls"] = "NO_SEMANTIC_LEDGER_IN_THIS_EXECUTION (a model call would have written llm_semantic_calls.jsonl; the lineage does not state a count)"
    else:
        out = {"research_agents": recorded if meta.get("llm_provider") else "NOT_RECORDED"}
    manifest = jload(run_dir / "llm_semantic_manifest.json")
    calls_path = run_dir / "llm_semantic_calls.jsonl"
    if manifest and calls_path.is_file():
        tuples: dict[tuple, int] = {}
        for line in calls_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            key = (row.get("task"), row.get("prompt_version"), row.get("prompt_sha256"), row.get("provider"), row.get("model"))
            tuples[key] = tuples.get(key, 0) + 1
        out["semantic_steps"] = {
            "manifest": rel(run_dir / "llm_semantic_manifest.json"), "calls_file": rel(calls_path),
            "provider_call_count": manifest.get("provider_call_count"), "record_count": manifest.get("record_count"), "tasks": manifest.get("tasks"),
            "distinct_task_prompt_model": [
                {"task": t, "prompt_version": pv, "prompt_sha256": ps, "provider": pr, "model": md, "records": n,
                 "prompt_content_in_delivery": prompts[ps]["file"] if ps in prompts else
                 "NOT_IN_DELIVERY (hash only: no prompt text with this sha256 exists in the delivered code)"}
                for (t, pv, ps, pr, md), n in sorted(tuples.items(), key=lambda kv: tuple(str(x) for x in kv[0]))],
        }
    else:
        out["semantic_steps"] = "NOT_RECORDED (no llm_semantic_manifest.json / llm_semantic_calls.jsonl in this run directory)"
    return out


def lineage_block(run_dir: Path) -> dict | None:
    for name in ("recovery_lineage.json", "requalification_lineage.json", "direction_lineage.json", "dependency_lineage.json"):
        data = jload(run_dir / name)
        if isinstance(data, dict):
            keep = {k: data.get(k) for k in ("execution_type", "based_on_run_id", "root_research_run_id", "created_at", "purpose", "model_calls", "searches", "data_fetches",
                                              "claim_count", "classification_source_counts") if k in data}
            if isinstance(data.get("recovery"), dict):  # keep the provenance note, not the per-claim map (975 entries)
                keep["recovery"] = {k: v for k, v in data["recovery"].items() if k in ("checkpoint_origin", "note")}
            keep["file"] = rel(run_dir / name)
            keep["lineage_chain"] = data.get("lineage_chain")
            keep["root_run_file_hashes_at_derivation"] = data.get("root_run_file_hashes_at_derivation") or data.get("original_run_file_hashes_at_derivation") or "NOT_RECORDED"
            return keep
    return None


def code_identity_for(run_id: str, s0: Path, s1: Path, s0_proof: dict) -> dict:
    if run_id == "dependency-20261007T220450Z-33128621":
        return {"status": "SNAPSHOT_S0", "snapshot": rel(s0), "head_json": rel(s0 / "HEAD.json"),
                "basis": s0_proof["basis"], "proof": s0_proof, "note": "the code that ran is S0; the files Round 22 changed afterwards are in round22_changes.patch"}
    return {"status": "UNKNOWN_NO_SNAPSHOT_AT_EXECUTION",
            "note": ("No snapshot of the working tree was taken when this execution ran, and HEAD alone (7a9aefa) does not identify code in a tree carrying "
                     "uncommitted changes. Nothing is inferred from today's tree. Earlier rounds kept HASH lists only for some states (see hash_records_from_earlier_rounds); "
                     "those lists carry no content and are not treated as code identity."),
            "hash_records_from_earlier_rounds": [rel(p) for p in sorted(ROUND_DIRS.glob("round1[49]*/*hashes_before*.json"))[:6]] +
                                                 [rel(p) for p in sorted(ROUND_DIRS.glob("round19*/production_tree_hashes_before_round19.json"))]}


def environment() -> dict:
    libs = {}
    for name in ("fastapi", "sqlalchemy", "pydantic", "pandas", "numpy", "stockstats", "yfinance", "langgraph", "psycopg", "uvicorn", "pytest"):
        try:
            libs[name] = version(name)
        except PackageNotFoundError:
            libs[name] = "NOT_INSTALLED"
    return {
        "python": platform.python_version(), "platform": platform.platform(), "dependencies": libs,
        "database": {"recorded_for": "the dependency-* executions and the read-only viewer", "kind": "PostgreSQL (isolated database whose name ends in _test)",
                     "name": "comqutor_alpha_test", "connection_string": "NOT_RECORDED (credentials are never written to a manifest)",
                     "other_runs": "NOT_RECORDED per run unless the run's own files say so"},
    }


def rules_block(s1: Path, final_run: Path) -> dict:
    hashes = json.loads((s1 / "file_hashes.json").read_text(encoding="utf-8"))
    files = {}
    for rel_path, meta in sorted(hashes.items()):
        if meta.get("is_rule_file"):
            copy = s1 / "rule_files" / rel_path
            files[rel_path] = {"snapshot_copy": rel(copy), "sha256": meta["sha256"], "bytes": meta["bytes"]}
    graph = jload(final_run / "structure_graph.json") or {}
    conflicts = jload(final_run / "conflicts.json") or {}
    activation = graph.get("activation") or {}
    return {
        "rule_files": files,
        "versions_recorded_in_the_final_execution": {
            "activation_formula_version": activation.get("formula_version"), "primary_activation_version": graph.get("primary_activation_version"),
            "conflict_formula_version": conflicts.get("formula_version"), "conflict_source_schema": conflicts.get("source_schema_version"),
            "fact_dependency_contract": (jload(final_run / "metadata.json") or {}).get("fact_dependency_contract"),
            "evidence_trace_schema": (jload(final_run / "evidence_trace.json") or {}).get("schema_version"),
        },
        "note": "frozen / hash-pinned production files equal HEAD byte for byte (see ../round21_t1_minimal_closure_20261007/final_scope_proofs.json)",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--s0", required=True)
    parser.add_argument("--s1", required=True)
    args = parser.parse_args()
    s0, s1 = Path(args.s0).resolve(), Path(args.s1).resolve()
    s0_head, s1_head = jload(s0 / "HEAD.json"), jload(s1 / "HEAD.json")
    final_id = "dependency-20261007T220450Z-33128621"
    final_run = OUTPUTS / final_id
    proof_file = HERE / "s0_is_the_code_of_dependency_final.json"
    s0_proof = jload(proof_file) or {"basis": "NOT_PROVEN (s0_is_the_code_of_dependency_final.json missing)"}

    IDENTITY_DIR.mkdir(parents=True, exist_ok=True)
    prompts = prompt_texts()
    runs_out: dict[str, dict] = {}
    for spec in RUNS:
        run_dir = OUTPUTS / spec["run_id"]
        if not run_dir.is_dir():
            runs_out[spec["run_id"]] = {**spec, "status": "DIRECTORY_MISSING"}
            continue
        meta = jload(run_dir / "metadata.json") or {}
        lineage = lineage_block(run_dir)
        copies = {}
        for name in IDENTITY_FILENAMES:
            src = run_dir / name
            if src.is_file():
                dst = IDENTITY_DIR / spec["run_id"] / name
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copies[name] = {"copy_in_delivery": rel(dst), "original": rel(src), "sha256": sha256_file(src)}
        logs = []
        for pattern in LOG_PATTERNS:
            target = run_dir / pattern
            if target.is_file():
                logs.append(entry(target))
            elif target.is_dir():
                logs.extend(entry(p) for p in sorted(target.rglob("*")) if p.is_file())
        round_records = [entry(p) for p in sorted(ROUND_DIRS.glob(f"**/*{spec['run_id']}*")) if p.is_file() and p.suffix in {".json", ".md", ".log", ".jsonl"}][:12]
        runs_out[spec["run_id"]] = {
            **spec,
            "ticker": meta.get("ticker"), "analysis_date": meta.get("analysis_date"), "evidence_cutoff": meta.get("analysis_date"), "created_at": meta.get("created_at"),
            "parent_run_id": spec.get("parent") or meta.get("based_on_run_id"),
            "input": {"identity_files": copies, "inputs_hashed_at_derivation": (lineage or {}).get("root_run_file_hashes_at_derivation", "NOT_APPLICABLE (original run)")},
            "model": model_identity(run_dir, prompts, spec["role"], lineage),
            "lineage": lineage,
            "logs": logs,
            "round_records": round_records,
            "directory": directory_digest(run_dir),
            "code_identity": code_identity_for(spec["run_id"], s0, s1, s0_proof),
        }

    unknowns = [
        "Code at execution time is UNKNOWN for every run except dependency-20261007T220450Z-33128621 (no snapshot was taken when they ran).",
        "Per-call provider fetch times are not recorded for any run: the source registry carries a registry-write-time upper bound only.",
        "Raw provider tool responses are not saved by any run listed here; provider_response_audit.json exists only for runs made after Round 22's capture change (none yet).",
        "The input series behind technical indicators is not saved by any run listed here; derived_inputs.json exists only for runs made after Round 22's capture change (none yet).",
        "Historical per-step model configuration is whatever the run's own metadata / semantic manifest recorded; nothing is filled in from the current configuration.",
        "The database backing runs other than the dependency-* executions and the viewer is NOT_RECORDED.",
    ]
    manifest = {
        "schema_version": "release_manifest.v2",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "task": "COMQUTOR Alpha next-round task sheet -- T0 delivery identity, T1 closeout (Round 22)",
        "supersedes": {"path": rel(OLD_MANIFEST), "sha256": sha256_file(OLD_MANIFEST) if OLD_MANIFEST.exists() else None,
                       "note": "kept unchanged: it records the 2026-10-01 baseline and none of the later runs"},
        "git": {
            "branch": s1_head["branch"], "head_sha": s1_head["head_sha"], "head_subject": s1_head["head_subject"],
            "commits_made_for_this_delivery": 0, "pushed": False,
            "working_tree_has_uncommitted_changes": True,
            "uncommitted_tracked_files": s1_head["tracked_files_differing_from_head"], "untracked_source_files": s1_head["untracked_source_files_copied"],
            "warning": "HEAD alone does not identify the executed code: the tree carries a large uncommitted difference. The snapshots below are the code identity.",
        },
        "code_snapshots": {
            "S0_before_round22": {"dir": rel(s0), "head_json": entry(s0 / "HEAD.json"), "tracked_diff_vs_HEAD": entry(s0 / "tracked_diff_vs_HEAD.patch"),
                                  "file_hashes": entry(s0 / "file_hashes.json"), "untracked_source_files": s0_head["untracked_source_files_copied"],
                                  "meaning": "the working tree immediately BEFORE Round 22 changed anything: the code of dependency-20261007T220450Z-33128621"},
            "S1_final": {"dir": rel(s1), "head_json": entry(s1 / "HEAD.json"), "tracked_diff_vs_HEAD": entry(s1 / "tracked_diff_vs_HEAD.patch"),
                         "file_hashes": entry(s1 / "file_hashes.json"), "untracked_source_files": s1_head["untracked_source_files_copied"],
                         "meaning": "the working tree at delivery"},
            "round22_changes": entry(HERE / "round22_changes.patch") if (HERE / "round22_changes.patch").exists() else "MISSING",
            "how_to_rebuild": "git archive HEAD (paths in file_hashes.json) + git apply tracked_diff_vs_HEAD.patch + copy untracked_source/ ; verify with verify_snapshot.py",
        },
        "rules": rules_block(s1, final_run),
        "prompts": {"files": {v["file"]: {"sha256": v["sha256"], "task": v["task"], "prompt_version": v["prompt_version"]} for v in prompts.values()},
                    "note": ("prompt text of every Week2 semantic task in the delivered code; a run's recorded prompt_sha256 equal to one of these hashes means the run used "
                             "exactly that text. content_support.llm.v2.1 calls of the AMD runs carry the version string in their saved results but NO per-call prompt hash "
                             "(their calls are not in the semantic ledger), so that prompt is not bound to those calls")},
        "environment": environment(),
        "execution_type_legend": {
            FRESH: "Fresh Run: data fetched and the research agents run", FROZEN_RECOMPUTE: "frozen-input recompute: no new market data; a model may be called again",
            REEVALUATION: "result re-evaluation: the research result is unchanged; only evaluation / grouping / scoring is recomputed (zero model calls)",
        },
        "runs": runs_out,
        "unknowns": unknowns,
    }
    out = HERE / "release_manifest_v2.json"
    out.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"manifest": rel(out), "runs": len(runs_out), "missing_directories": [k for k, v in runs_out.items() if v.get("status") == "DIRECTORY_MISSING"],
                      "bytes": out.stat().st_size}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
