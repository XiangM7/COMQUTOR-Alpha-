#!/usr/bin/env python3
"""Round 21 (T1 minimal closure): recompute the AMD requalification execution under the fact-dependency contract.

ZERO Provider / search / data-fetch calls (a fail-closed trap is installed around the whole recompute). The new
``dependency-*`` execution is based on the requalification execution (parent) with the original research run
``c904d4cc-...`` recorded as root. It reuses the parent's alpha_matches / structured records / source registry VERBATIM
(including the deterministic stance -- direction was never obtained) and only declares one extra run-level marker,
``fact_dependency_contract``, which the production pipeline reads. Nothing is re-judged and nothing is hand-edited:
the Evidence Fact grouping, Activation, Exposure and Conflict are recomputed by the existing production entry
(``finalize_classification_recovery_execution`` -> ``routes_research._run_week3_graph_pipeline``).

--dry-run  : recompute in a TEMPORARY copy (in-memory SQLite) and write only the before/after comparison.
--execute  : create the execution (writes only the new directory and its rows in the isolated test database).
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import socket
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))
HERE = Path(__file__).resolve().parent

ROOT_RUN_ID = "c904d4cc-dc09-495c-aec5-b056979948e1"
RECOVERY_RUN_ID = "recovery-20261007T053635Z-26d6cd1a"
PARENT_RUN_ID = "requal-20261007T174744Z-664040d6"
DIRECTION_RUN_ID = "direction-20261007T065826Z-d311b8e2"
OUTPUT_ROOT = (REPO_ROOT / "outputs" / "runs").resolve()
PROTECTED = {"root": ROOT_RUN_ID, "recovery": RECOVERY_RUN_ID, "parent": PARENT_RUN_ID, "direction": DIRECTION_RUN_ID}


def jload(path: Path):
    return json.loads(Path(path).read_text())


class ZeroCallTrap:
    """Fails closed on any Provider / network path while the recompute runs, and counts the attempts."""

    def __enter__(self):
        import httpx

        from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

        self.attempts: list[str] = []
        self._saved = []

        def block(name):
            def _raise(*a, **k):
                self.attempts.append(name)
                raise AssertionError(f"zero-call guard: {name}")
            return _raise

        def patch(obj, attr, name):
            self._saved.append((obj, attr, getattr(obj, attr)))
            setattr(obj, attr, block(name))

        patch(httpx.HTTPTransport, "handle_request", "httpx.HTTPTransport.handle_request")
        patch(httpx.Client, "send", "httpx.Client.send")
        for method in ("invoke_json", "invoke_json_with_trace", "invoke_prebuilt_json_prompt"):
            patch(Week2LLMGateway, method, f"Week2LLMGateway.{method}")
        real_getaddrinfo = socket.getaddrinfo

        def guarded_getaddrinfo(host, *a, **k):
            if str(host) not in ("localhost", "127.0.0.1", "::1"):
                self.attempts.append(f"getaddrinfo:{host}")
                raise AssertionError(f"zero-call guard: DNS lookup for {host}")
            return real_getaddrinfo(host, *a, **k)

        self._saved.append((socket, "getaddrinfo", real_getaddrinfo))
        socket.getaddrinfo = guarded_getaddrinfo
        return self

    def __exit__(self, *exc):
        for obj, attr, original in reversed(self._saved):
            setattr(obj, attr, original)
        return False


# ---------------------------------------------------------------------------
# Comparison of two structure graphs (parent vs recomputed)
# ---------------------------------------------------------------------------

ALPHA_FIELDS = ("activation_score", "status", "qualified_level", "evidence_count", "unique_evidence_fact_count",
                "raw_supporting_claim_count", "distinct_supporting_agents", "ticker_specific_evidence_count",
                "local_edge_count", "eligible_cap", "cap_reason_codes", "direction")


def _alphas(graph: dict, view: str | None = None) -> dict:
    block = graph["activation"] if view is None else graph["activation_versions"][view]
    return {a["alpha_id"]: a for a in block["alphas"]}


def compare_graphs(before: dict, after: dict) -> dict:
    out = {}
    for label, view in (("official (primary activation)", None), ("v2 raw diagnostic", "v2")):
        b, a = _alphas(before, view), _alphas(after, view)
        diffs = {}
        for alpha_id in sorted(b):
            changed = {}
            for field in ALPHA_FIELDS:
                if b[alpha_id].get(field) != a[alpha_id].get(field):
                    changed[field] = {"before": b[alpha_id].get(field), "after": a[alpha_id].get(field)}
            groups_b = sorted(sorted(g["member_claim_ids"]) for g in b[alpha_id].get("evidence_fact_groups") or [])
            groups_a = sorted(sorted(g["member_claim_ids"]) for g in a[alpha_id].get("evidence_fact_groups") or [])
            if groups_b != groups_a:
                changed["evidence_fact_groups"] = {"before_group_sizes": sorted(len(g) for g in groups_b), "after_group_sizes": sorted(len(g) for g in groups_a),
                                                   "merged": [[c.split(":claim:")[-1] for c in g] for g in groups_a if len(g) > 1 and g not in groups_b]}
            if sorted(b[alpha_id].get("claim_ids") or []) != sorted(a[alpha_id].get("claim_ids") or []):
                changed["claim_ids"] = "DIFFERENT"
            if changed:
                diffs[alpha_id] = changed
        out[label] = {"alphas_with_any_difference": diffs, "alphas_compared": len(b)}
    out["dominant_active_candidate_sets_equal"] = all(
        sorted(x["alpha_id"] for x in before.get(key, [])) == sorted(x["alpha_id"] for x in after.get(key, []))
        for key in ("dominant_alphas", "active_alphas", "regime_level_alphas", "candidate_alphas", "blocked_alphas")
    )
    return out


def run_dry_run() -> int:
    from comqutor_alpha.api import routes_research as rr
    from comqutor_alpha.classification_recovery import rebase_run_id
    from comqutor_alpha.graph_engine.claim_data_grounding import FACT_DEPENDENCY_CONTRACT
    from comqutor_alpha.storage.db.engine import build_engine
    from comqutor_alpha.storage.db.migrations import apply_migrations
    from comqutor_alpha.storage.db.repository import GraphPersistenceRepository

    parent_dir = OUTPUT_ROOT / PARENT_RUN_ID
    tmp_root = Path(tempfile.mkdtemp(prefix="dependency_dry_run_"))
    tmp_id = "dependency_dry_run"
    tmp_dir = tmp_root / tmp_id
    tmp_dir.mkdir()
    for name in ("metadata.json", "structured_agent_outputs.json", "alpha_matches.json", "extracted_structures.json", "source_registry.json", "raw_agent_outputs.json"):
        payload = rebase_run_id(jload(parent_dir / name), base_run_id=PARENT_RUN_ID, execution_id=tmp_id)
        if name == "metadata.json":
            payload["fact_dependency_contract"] = FACT_DEPENDENCY_CONTRACT
        (tmp_dir / name).write_text(json.dumps(payload))
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    with ZeroCallTrap() as trap:
        rr._run_week3_graph_pipeline(tmp_dir, graph_repository=GraphPersistenceRepository(engine), require_verified_evidence_gate=True)
    after = jload(tmp_dir / "structure_graph.json")
    before = jload(parent_dir / "structure_graph.json")
    result = {"mode": "dry-run (temporary copy, in-memory SQLite; no write to outputs/ or the database)",
              "zero_call": {"attempted_provider_or_network_calls": len(trap.attempts), "attempts": trap.attempts},
              "fact_dependency_contract_block": after.get("fact_dependency_contract"),
              "comparison": compare_graphs(before, after)}
    (HERE / "dependency_dry_run_result.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
    shutil.rmtree(tmp_root, ignore_errors=True)
    print(json.dumps(result["comparison"], indent=1, ensure_ascii=False)[:6000])
    print("zero-call attempts:", len(trap.attempts))
    return 0 if not trap.attempts else 4


def run_execute(execution_id: str | None) -> int:
    from dotenv import dotenv_values
    from sqlalchemy.engine import make_url

    test_url = dotenv_values(REPO_ROOT / ".env").get("COMQUTOR_TEST_DATABASE_URL")
    name = make_url(test_url).database if test_url else ""
    if not name or not name.endswith("_test"):
        print("BLOCKED: no isolated *_test database configured", file=sys.stderr)
        return 1
    os.environ["COMQUTOR_DATABASE_URL"] = test_url
    os.environ["COMQUTOR_REQUIRE_DATABASE_NAME"] = name

    from comqutor_alpha.api.artifact_export import build_and_write_artifact_manifest
    from comqutor_alpha.classification_recovery import (
        DEPENDENCY_EXECUTION_MODE, DEPENDENCY_EXECUTION_TYPE, DEPENDENCY_LINEAGE_FILENAME,
        finalize_classification_recovery_execution, new_dependency_execution_id, snapshot_directory_hashes)
    from comqutor_alpha.graph_engine.claim_data_grounding import FACT_DEPENDENCY_CONTRACT
    from comqutor_alpha.storage.db.repository import build_write_repository_from_env

    execution_id = execution_id or new_dependency_execution_id()
    if not execution_id.startswith("dependency-") or (OUTPUT_ROOT / execution_id).exists():
        print(f"BLOCKED: bad or existing execution id {execution_id}", file=sys.stderr)
        return 1
    before_hashes = {k: snapshot_directory_hashes(OUTPUT_ROOT / rid) for k, rid in PROTECTED.items()}
    (HERE / "protected_run_hashes_before.json").write_text(json.dumps(before_hashes, indent=1, sort_keys=True))
    metadata = jload(OUTPUT_ROOT / ROOT_RUN_ID / "metadata.json")
    payload = copy.deepcopy(jload(OUTPUT_ROOT / PARENT_RUN_ID / "alpha_matches.json"))
    repository = build_write_repository_from_env(str(OUTPUT_ROOT))
    with ZeroCallTrap() as trap:
        finalized = finalize_classification_recovery_execution(
            PARENT_RUN_ID, execution_id, assembled_alpha_matches=payload,
            recovery_provenance={"checkpoint_origin": "real",
                                 "note": "alpha_matches / structured records / source registry reused verbatim from the parent; only the run-level fact_dependency_contract marker is added"},
            output_root=OUTPUT_ROOT, graph_repository=repository,
            execution_type=DEPENDENCY_EXECUTION_TYPE, execution_mode=DEPENDENCY_EXECUTION_MODE,
            lineage_filename=DEPENDENCY_LINEAGE_FILENAME, assembled_transformation="reused_verbatim_from_parent",
            root_run_id=ROOT_RUN_ID, metadata_extras={"fact_dependency_contract": FACT_DEPENDENCY_CONTRACT},
            lineage_extras={"purpose": "T1 minimal closure: derived expressions of the same saved observations count as one independent evidence fact; claims, citations and scores' inputs are unchanged",
                            "model_calls": 0, "searches": 0, "data_fetches": 0})
    zero_call = {"attempted_provider_or_network_calls": len(trap.attempts), "attempts": trap.attempts}
    print("finalized:", json.dumps(finalized, default=str)[:700])
    if finalized.get("status") != "ok":
        return 3
    build_and_write_artifact_manifest(run_id=execution_id, ticker=metadata["ticker"], output_root=OUTPUT_ROOT)
    after_hashes = {k: snapshot_directory_hashes(OUTPUT_ROOT / rid) for k, rid in PROTECTED.items()}
    unchanged = {k: after_hashes[k] == before_hashes[k] for k in PROTECTED}
    comparison = compare_graphs(jload(OUTPUT_ROOT / PARENT_RUN_ID / "structure_graph.json"), jload(OUTPUT_ROOT / execution_id / "structure_graph.json"))
    report = {"execution_id": execution_id, "based_on": PARENT_RUN_ID, "root": ROOT_RUN_ID, "finalized": finalized, "zero_call": zero_call,
              "protected_runs_byte_identical_before_vs_after": unchanged, "comparison_parent_vs_new": comparison}
    (HERE / f"dependency_execution_report_{execution_id}.json").write_text(json.dumps(report, indent=1, default=str, ensure_ascii=False))
    print("protected runs unchanged:", unchanged, "| zero-call attempts:", len(trap.attempts))
    print("execution_id:", execution_id)
    return 0 if all(unchanged.values()) and not trap.attempts else 4


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--execution-id", default=None)
    args = parser.parse_args()
    sys.exit(run_execute(args.execution_id) if args.execute else run_dry_run())
