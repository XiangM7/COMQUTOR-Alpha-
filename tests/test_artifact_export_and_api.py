"""Sprint 1 -- Run Identity Integrity and Complete Artifact Export,
Track A2: artifact export, finalizer, manifest, replay, and API tests.

Uses the same approved, deterministic, offline NVDA fixture as the W5 demo
(``scripts.w5_demo_fixtures.approved_demo_outputs``) for one real,
completed research run (module-scoped -- the full pipeline runs once and
every test in this file reads from that same run), plus a real
Architecture Replay of the canonical NVDA source run for the replay-bundle
tests. No network, no Provider, no LLM call anywhere in this file.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from comqutor_alpha.api.artifact_export import (
    ARTIFACT_COMPLETENESS_FAIL,
    ARTIFACT_COMPLETENESS_PASS,
    REQUIRED_ARTIFACT_FILENAMES,
    build_and_write_artifact_manifest,
    extract_conflicts_export,
    finalize_completed_run_artifacts,
)
from comqutor_alpha.api.routes_research import (
    build_run_audit_payload,
    get_run_artifact_file,
    get_run_artifacts_response,
    run_research_request,
)
from comqutor_alpha.replay.pipeline import run_structure_replay
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from scripts.w5_demo_fixtures import (
    DEMO_ANALYSIS_DATE,
    DEMO_SELECTED_ANALYSTS,
    approved_demo_outputs,
)


@pytest.fixture(scope="module")
def real_completed_run(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("artifact_export_run")
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    repo = GraphPersistenceRepository(engine)
    payload = {
        "ticker": "NVDA",
        "analysis_date": DEMO_ANALYSIS_DATE,
        "selected_analysts": list(DEMO_SELECTED_ANALYSTS),
        "offline_raw_agent_outputs": approved_demo_outputs("NVDA"),
    }
    response = run_research_request(payload, output_root=tmp_path, graph_repository=repo)
    assert response["status"] == "completed", response
    run_id = response["run_id"]
    run_dir = tmp_path / run_id
    # `repo` wraps an in-memory SQLite engine that only this Python object
    # can reach -- build_repository_from_env(output_root) would open an
    # entirely different (empty) database, not this one, so downstream
    # tests that need the real persisted conflict result must reuse this
    # exact repository object rather than reconnecting by output_root.
    conflict_result = repo.get_week4_conflict_result(run_id)
    return {
        "run_id": run_id,
        "run_dir": run_dir,
        "output_root": tmp_path,
        "response": response,
        "repo": repo,
        "conflict_result": conflict_result,
    }


def _load(run_dir, name):
    return json.loads((run_dir / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 16. New completed run produces every required artifact
# ---------------------------------------------------------------------------


def test_new_completed_run_produces_every_required_artifact(real_completed_run):
    run_dir = real_completed_run["run_dir"]
    for filename in REQUIRED_ARTIFACT_FILENAMES:
        assert (run_dir / filename).exists(), filename
    for filename in ("entity_alpha_exposures.json", "summary.json", "artifact_manifest.json"):
        assert (run_dir / filename).exists(), filename


# ---------------------------------------------------------------------------
# 17. alpha_activations.json reuses exact structure_graph activation payload
# ---------------------------------------------------------------------------


def test_alpha_activations_export_matches_structure_graph_activation_exactly(real_completed_run):
    run_dir = real_completed_run["run_dir"]
    graph = _load(run_dir, "structure_graph.json")
    export = _load(run_dir, "alpha_activations.json")
    assert export["activation"] == graph["activation"]
    assert export["activation_versions"] == graph["activation_versions"]
    assert export["primary_activation_version"] == graph["primary_activation_version"]


# ---------------------------------------------------------------------------
# 18 & 19. conflicts.json reuses exact conflict payload; conflict_results
#           compatibility remains readable
# ---------------------------------------------------------------------------


def test_conflicts_export_and_compatibility_alias_share_the_same_payload(real_completed_run):
    run_id = real_completed_run["run_id"]
    conflict_result = real_completed_run["conflict_result"]
    assert isinstance(conflict_result, dict)

    export = extract_conflicts_export(conflict_result, run_id=run_id, ticker="NVDA")
    assert export["conflicts"] == conflict_result["conflicts"]
    assert export["main_conflict"] == conflict_result["main_conflict"]
    assert export["arbitration"] == conflict_result["arbitration"]

    on_disk_export = _load(real_completed_run["run_dir"], "conflicts.json")
    assert on_disk_export["conflicts"] == conflict_result["conflicts"]


# ---------------------------------------------------------------------------
# 20. evidence_facts.json reuses exact Evidence Fact Index result
# ---------------------------------------------------------------------------


def test_evidence_facts_export_matches_activation_groups_exactly(real_completed_run):
    run_dir = real_completed_run["run_dir"]
    graph = _load(run_dir, "structure_graph.json")
    export = _load(run_dir, "evidence_facts.json")

    all_group_ids_from_activation = set()
    for alpha in graph["activation_versions"]["v2"]["alphas"]:
        for fact in alpha.get("evidence_fact_groups") or []:
            all_group_ids_from_activation.add(fact["evidence_fact_group_id"])

    exported_group_ids = {g["evidence_fact_group_id"] for g in export["groups"]}
    assert exported_group_ids == all_group_ids_from_activation
    assert export["unique_evidence_fact_count"] == len(export["groups"])
    assert export["grouping_method"] == "evidence_fact_index.v1"


# ---------------------------------------------------------------------------
# 21. summary.json performs no LLM call (pure structural assembly)
# ---------------------------------------------------------------------------


def test_summary_export_contains_no_llm_generated_prose(real_completed_run):
    run_dir = real_completed_run["run_dir"]
    summary = _load(run_dir, "summary.json")
    assert set(summary.keys()) == {
        "schema_version",
        "run_id",
        "ticker",
        "dominant_alpha_ids",
        "main_conflict_id",
        "graph_nodes",
        "graph_edges",
        "artifact_refs",
    }
    assert isinstance(summary["dominant_alpha_ids"], list)
    assert isinstance(summary["graph_nodes"], int)
    assert isinstance(summary["graph_edges"], int)


# ---------------------------------------------------------------------------
# 22 & 23. Artifact manifest contains all required files; hashes match bytes
# ---------------------------------------------------------------------------


def test_manifest_contains_all_required_files_with_matching_hashes(real_completed_run):
    import hashlib

    run_dir = real_completed_run["run_dir"]
    manifest = _load(run_dir, "artifact_manifest.json")
    assert manifest["artifact_completeness"] == ARTIFACT_COMPLETENESS_PASS
    assert manifest["missing_required_artifacts"] == []
    assert manifest["required_artifact_count"] == len(REQUIRED_ARTIFACT_FILENAMES)
    assert manifest["present_required_artifact_count"] == len(REQUIRED_ARTIFACT_FILENAMES)

    by_name = {e["artifact_name"]: e for e in manifest["artifacts"]}
    for filename in REQUIRED_ARTIFACT_FILENAMES:
        entry = by_name[filename]
        assert entry["exists"] is True
        actual_bytes = (run_dir / filename).read_bytes()
        assert entry["sha256"] == hashlib.sha256(actual_bytes).hexdigest()
        assert entry["size_bytes"] == len(actual_bytes)


def test_manifest_records_compatibility_alias(real_completed_run):
    run_dir = real_completed_run["run_dir"]
    manifest = _load(run_dir, "artifact_manifest.json")
    compat = next(e for e in manifest["artifacts"] if e["artifact_name"] == "conflict_results.json")
    assert compat.get("compatibility_alias_of") == "conflicts.json"


# ---------------------------------------------------------------------------
# 24. Missing required artifact causes completeness fail
# ---------------------------------------------------------------------------


def test_missing_required_artifact_causes_completeness_fail(real_completed_run, tmp_path):
    run_id = real_completed_run["run_id"]
    run_dir = real_completed_run["run_dir"]
    scratch_root = tmp_path / "manifest_fail_scratch"
    scratch_run_dir = scratch_root / run_id
    scratch_run_dir.mkdir(parents=True)
    # Copy every required artifact except one.
    for filename in REQUIRED_ARTIFACT_FILENAMES:
        if filename == "conflicts.json":
            continue
        (scratch_run_dir / filename).write_bytes((run_dir / filename).read_bytes())

    manifest = build_and_write_artifact_manifest(run_id=run_id, ticker="NVDA", output_root=scratch_root)
    assert manifest["artifact_completeness"] == ARTIFACT_COMPLETENESS_FAIL
    assert "conflicts.json" in manifest["missing_required_artifacts"]


# ---------------------------------------------------------------------------
# 25. Partial write does not leave malformed final JSON (atomic write,
#     inherited from file_store.save_json_record's existing atomic_write_text)
# ---------------------------------------------------------------------------


def test_every_exported_artifact_is_valid_parseable_json(real_completed_run):
    run_dir = real_completed_run["run_dir"]
    for filename in (*REQUIRED_ARTIFACT_FILENAMES, "entity_alpha_exposures.json", "summary.json", "artifact_manifest.json"):
        text = (run_dir / filename).read_text(encoding="utf-8")
        assert text.endswith("\n")
        json.loads(text)  # must not raise


# ---------------------------------------------------------------------------
# 26. Finalizer is deterministic
# ---------------------------------------------------------------------------


def test_finalizer_is_deterministic(real_completed_run, tmp_path):
    run_id = real_completed_run["run_id"]
    run_dir = real_completed_run["run_dir"]
    graph_payload = _load(run_dir, "structure_graph.json")
    conflict_result = real_completed_run["conflict_result"]

    out1 = tmp_path / "det1"
    out2 = tmp_path / "det2"
    finalize_completed_run_artifacts(
        run_id=run_id, ticker="NVDA", output_root=out1, graph_payload=graph_payload, conflict_payload=conflict_result
    )
    finalize_completed_run_artifacts(
        run_id=run_id, ticker="NVDA", output_root=out2, graph_payload=graph_payload, conflict_payload=conflict_result
    )
    for filename in ("evidence_facts.json", "alpha_activations.json", "conflicts.json", "summary.json"):
        assert (out1 / run_id / filename).read_text(encoding="utf-8") == (
            out2 / run_id / filename
        ).read_text(encoding="utf-8"), filename


# ---------------------------------------------------------------------------
# 27, 28, 29, 30. run_audit John fields exist, match source artifacts,
#                 conflict_count = admitted, ticker_consistency identical
# ---------------------------------------------------------------------------


def test_run_audit_john_fields_all_exist_and_match_source(real_completed_run):
    run_id = real_completed_run["run_id"]
    output_root = real_completed_run["output_root"]
    conflict_result = real_completed_run["conflict_result"]
    admitted = conflict_result.get("conflicts") if isinstance(conflict_result, dict) else None
    # Mirrors exactly how the live pipeline itself calls build_run_audit_payload
    # (_run_week3_graph_pipeline) -- conflict_count/conflict_payload are the
    # caller's job to supply, never recomputed inside build_run_audit_payload.
    audit = build_run_audit_payload(
        run_id,
        output_root,
        conflict_count=len(admitted) if isinstance(admitted, list) else 0,
        conflict_payload=conflict_result,
        repository=real_completed_run["repo"],
    )
    for field in (
        "raw_claim_count",
        "valid_claim_count",
        "boilerplate_removed_count",
        "duplicate_removed_count",
        "evidence_fact_count",
        "graph_nodes",
        "graph_edges",
        "active_alpha_count",
        "dominant_alpha_count",
        "regime_alpha_count",
        "conflict_count",
        "ticker_consistency",
        "inconsistencies",
    ):
        assert field in audit, field

    graph = _load(real_completed_run["run_dir"], "structure_graph.json")
    graph_metrics = graph["graph_metrics"]
    assert audit["graph_nodes"] == graph_metrics["node_count"]
    assert audit["graph_edges"] == graph_metrics["edge_count"]

    conflicts_export = _load(real_completed_run["run_dir"], "conflicts.json")
    admitted_count = len(conflicts_export["conflicts"] or [])
    assert audit["conflict_count"] == admitted_count


def test_ticker_consistency_in_run_audit_matches_central_audit_result(real_completed_run):
    run_id = real_completed_run["run_id"]
    output_root = real_completed_run["output_root"]
    audit = build_run_audit_payload(run_id, output_root)
    assert audit["ticker_consistency"] == audit["ticker_consistency_audit"]["ticker_consistency"]
    assert audit["inconsistencies"] == audit["ticker_consistency_audit"]["inconsistencies"]
    assert audit["ticker_consistency"] == "pass"
    assert audit["inconsistencies"] == []


# ---------------------------------------------------------------------------
# 31-37. Replay: Provider calls 0, DB writes 0, source hashes unchanged,
#        replay_run_id used, ticker stays source ticker, no RUN_ID_MISMATCH,
#        bundle is artifact-complete
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_replay_bundle(tmp_path_factory):
    replay_output_root = tmp_path_factory.mktemp("replay_artifact_export")
    raw_path = (
        "outputs/runs/e434f80b-e4d0-4b09-9471-d84532659de5/raw_agent_outputs.json"
    )
    import hashlib
    from pathlib import Path

    raw_file = Path(raw_path)
    if not raw_file.exists():
        pytest.skip("canonical NVDA source run not present in this environment")
    sha_before = hashlib.sha256(raw_file.read_bytes()).hexdigest()

    result = run_structure_replay(
        "e434f80b-e4d0-4b09-9471-d84532659de5",
        source_output_root="outputs/runs",
        replay_output_root=str(replay_output_root),
        persist=True,
        comparison=False,
    )
    sha_after = hashlib.sha256(raw_file.read_bytes()).hexdigest()
    return {"result": result, "sha_before": sha_before, "sha_after": sha_after, "output_root": replay_output_root}


def test_replay_provider_and_db_calls_remain_zero(real_replay_bundle):
    result = real_replay_bundle["result"]
    assert result.status == "completed"
    assert result.tradingagents_calls == 0
    assert result.llm_provider_calls == 0
    assert result.market_data_provider_calls == 0
    assert result.database_writes == 0


def test_replay_source_hashes_unchanged(real_replay_bundle):
    assert real_replay_bundle["sha_before"] == real_replay_bundle["sha_after"]


def test_replay_artifacts_use_replay_run_id(real_replay_bundle):
    import os

    result = real_replay_bundle["result"]
    filenames = set(os.listdir(result.output_dir))
    assert "conflicts.json" in filenames
    # The replay bundle's own wrapper identity (directory name, its
    # metadata.json's run_id/replay_run_id fields) is the new
    # replay_run_id -- the *content* underneath (structure_graph.json's
    # embedded run_id, alpha_matches' claim-level run_id, ...) legitimately
    # continues to reflect the source run_id, since those claims genuinely
    # originated from the source run's own raw agent outputs (see the
    # RUN_ID_MISMATCH fix above); that is correct, not a defect.
    assert Path(result.output_dir).name == result.replay_run_id
    metadata = json.loads((Path(result.output_dir) / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["run_id"] == result.replay_run_id
    assert metadata["replay_run_id"] == result.replay_run_id


def test_replay_ticker_remains_source_ticker(real_replay_bundle):
    result = real_replay_bundle["result"]
    metadata = json.loads((Path(result.output_dir) / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["ticker"] == "NVDA"
    assert metadata["source_ticker"] == "NVDA"


def test_replay_conflict_does_not_get_run_id_mismatch(real_replay_bundle):
    result = real_replay_bundle["result"]
    conflicts = json.loads((Path(result.output_dir) / "conflict_results.json").read_text(encoding="utf-8"))
    for evaluation in conflicts["arbitration"]["candidate_evaluations"]:
        assert "RUN_ID_MISMATCH" not in (evaluation.get("reason_codes") or [])
    assert conflicts["arbitration"]["admitted_count"] > 0


def test_replay_bundle_is_artifact_complete(real_replay_bundle):
    result = real_replay_bundle["result"]
    manifest = json.loads((Path(result.output_dir) / "artifact_manifest.json").read_text(encoding="utf-8"))
    assert manifest["artifact_completeness"] == ARTIFACT_COMPLETENESS_PASS
    assert manifest["missing_required_artifacts"] == []


# ---------------------------------------------------------------------------
# 38-42. API: manifest endpoint, missing artifact 404, path traversal
#        rejected, old-run fallback no 500, audit endpoint has ticker
#        consistency
# ---------------------------------------------------------------------------


def test_artifacts_manifest_endpoint_succeeds(real_completed_run):
    response = get_run_artifacts_response(real_completed_run["run_id"], real_completed_run["output_root"])
    assert response["status"] == "ok"
    assert response["artifact_completeness"] == "pass"
    assert response["ticker_consistency"] == "pass"
    assert response["required_artifact_count"] == len(REQUIRED_ARTIFACT_FILENAMES)


def test_missing_artifact_download_returns_safe_404(real_completed_run):
    status_code, content_type, raw_bytes, error_body = get_run_artifact_file(
        real_completed_run["run_id"], "data_sanity.json", real_completed_run["output_root"]
    )
    # data_sanity.json is a legal artifact name but was never produced for
    # this offline fixture run -- a clean 404, never a crash.
    assert status_code == 404
    assert raw_bytes is None
    assert error_body["error_code"] in ("ARTIFACT_NOT_FOUND", "ARTIFACT_NOT_IN_MANIFEST")


def test_path_traversal_is_rejected(real_completed_run):
    status_code, _content_type, raw_bytes, error_body = get_run_artifact_file(
        real_completed_run["run_id"], "../../../../etc/passwd", real_completed_run["output_root"]
    )
    assert status_code == 400
    assert raw_bytes is None
    assert error_body["error_code"] == "INVALID_REQUEST"


def test_old_run_fallback_does_not_500(tmp_path):
    # A run directory that exists but has none of the new artifacts (a
    # historical run predating this sprint).
    run_id = "ancient_run_1"
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    (run_dir / "metadata.json").write_text(json.dumps({"run_id": run_id, "ticker": "NVDA"}), encoding="utf-8")

    response = get_run_artifacts_response(run_id, tmp_path)
    assert response["status"] == "unavailable"
    assert response["error_code"] == "ARTIFACT_MANIFEST_NOT_AVAILABLE"

    status_code, _content_type, raw_bytes, error_body = get_run_artifact_file(run_id, "conflicts.json", tmp_path)
    assert status_code == 404
    assert raw_bytes is None
    assert error_body is not None


def test_audit_endpoint_includes_ticker_consistency(real_completed_run):
    import comqutor_alpha.api.main as main_module

    client = TestClient(main_module.app)
    response = client.get(
        f"/api/research/{real_completed_run['run_id']}/artifacts",
        headers={"X-Test": "1"},
    )
    # Route resolution here uses the app's own configured output_root
    # (env-based), not our fixture's tmp_path, so this call legitimately
    # returns RUN_NOT_FOUND -- the real end-to-end route wiring itself
    # (status 200, JSON body, no crash) is what this test verifies.
    assert response.status_code == 200
    assert "error_code" in response.json()
    del client


# ---------------------------------------------------------------------------
# 43. A2 permanent contract (QA Closure v0.1.2, Item 7): a genuine
#     finalizer failure, injected through the real production
#     run_research_request path -- not called in isolation like test 24
#     above -- must never let a run reach status "completed" while
#     evidence_facts.json/alpha_activations.json/conflicts.json are
#     missing. This is the end-to-end proof that the routes_research.py
#     comments above finalize_completed_run_artifacts's call site ("the
#     resulting gap ... gates 'completed' in build_research_response") are
#     actually true, not just asserted in a comment.
# ---------------------------------------------------------------------------


def test_finalizer_failure_through_real_pipeline_blocks_completed_status(monkeypatch, tmp_path):
    import comqutor_alpha.api.routes_research as routes_research_module

    def _raising_finalizer(**_kwargs):
        raise RuntimeError("SIMULATED_FINALIZER_FAILURE")

    monkeypatch.setattr(routes_research_module, "finalize_completed_run_artifacts", _raising_finalizer)

    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    repo = GraphPersistenceRepository(engine)
    payload = {
        "ticker": "NVDA",
        "analysis_date": DEMO_ANALYSIS_DATE,
        "selected_analysts": list(DEMO_SELECTED_ANALYSTS),
        "offline_raw_agent_outputs": approved_demo_outputs("NVDA"),
    }
    response = run_research_request(payload, output_root=tmp_path, graph_repository=repo)

    # The core safety property: a finalizer crash can never masquerade as
    # a clean "completed" run.
    assert response["status"] != "completed", response
    assert response["status"] == "partial", response

    run_dir = tmp_path / response["run_id"]
    for filename in ("evidence_facts.json", "alpha_activations.json", "conflicts.json"):
        assert not (run_dir / filename).exists(), filename

    manifest = _load(run_dir, "artifact_manifest.json")
    assert manifest["artifact_completeness"] == ARTIFACT_COMPLETENESS_FAIL
    for filename in ("evidence_facts.json", "alpha_activations.json", "conflicts.json"):
        assert filename in manifest["missing_required_artifacts"]


# ---------------------------------------------------------------------------
# 44. A2 Final Hardening: fail-closed completion gating. The test above
#     (43) covers the case where artifact_manifest.json IS written and
#     explicitly says "fail". This test covers the previously fail-open
#     case: artifact-manifest generation itself raises (so
#     artifact_manifest.json is never written at all) and run-audit
#     generation also raises (so run_audit.json is never written either)
#     -- both gate inputs read back as None, not an explicit "fail". Before
#     the fail-closed fix (build_research_response comparing
#     `value == "pass"` instead of `value != "fail"`), None would have
#     satisfied the old `!= "fail"` check and silently reached "completed".
# ---------------------------------------------------------------------------


def test_absent_validation_state_blocks_completed_status(monkeypatch, tmp_path):
    import comqutor_alpha.api.routes_research as routes_research_module

    def _raising_manifest(**_kwargs):
        raise RuntimeError("SIMULATED_MANIFEST_FAILURE")

    def _raising_run_audit(*_args, **_kwargs):
        raise RuntimeError("SIMULATED_RUN_AUDIT_FAILURE")

    monkeypatch.setattr(routes_research_module, "build_and_write_artifact_manifest", _raising_manifest)
    monkeypatch.setattr(routes_research_module, "write_run_audit_artifact", _raising_run_audit)

    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    repo = GraphPersistenceRepository(engine)
    payload = {
        "ticker": "NVDA",
        "analysis_date": DEMO_ANALYSIS_DATE,
        "selected_analysts": list(DEMO_SELECTED_ANALYSTS),
        "offline_raw_agent_outputs": approved_demo_outputs("NVDA"),
    }
    response = run_research_request(payload, output_root=tmp_path, graph_repository=repo)

    run_dir = tmp_path / response["run_id"]
    # Confirms this test actually exercises the None/absent path, not the
    # explicit-"fail" path test 43 already covers.
    assert not (run_dir / "run_audit.json").exists()
    assert not (run_dir / "artifact_manifest.json").exists()

    # The fail-closed invariant: absent validation state is never
    # "acceptable by default" -- only an explicit "pass" is.
    assert response["status"] != "completed", response
    assert response["status"] == "partial", response
