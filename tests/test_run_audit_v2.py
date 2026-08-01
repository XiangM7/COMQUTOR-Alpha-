"""MVP Audit, Evaluation, Golden Fixtures, and Delivery Readiness Sprint,
Track A: Run Audit v2 consolidation tests.

Covers the ten required audit-test items from the sprint spec: v1 stays
readable, v2 sections are present/shaped correctly, missing provenance
becomes an honest null+warning (never a guess), artifact hashes are
deterministic, claim/edge accounting invariants are verified against real
arithmetic (not asserted blindly), every declared conflict pair is included
(not only admitted ones), production/shadow counts are reused rather than
recomputed by a second algorithm, DB/file round-trips preserve the new
fields, and audit generation never mutates the source artifacts it reads.
"""

from __future__ import annotations

import json

from comqutor_alpha.api.routes_research import (
    RUN_AUDIT_SCHEMA_VERSION,
    build_run_audit_payload,
    write_run_audit_artifact,
)
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from comqutor_alpha.storage.db.schema import research_runs


def _write_json(run_dir, name, payload):
    (run_dir / name).write_text(json.dumps(payload), encoding="utf-8")


def _seed_rich_run(tmp_path, run_id="runauditv2", *, ticker="SNDK", with_conflict_fields=True):
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    _write_json(
        run_dir,
        "metadata.json",
        {
            "run_id": run_id,
            "ticker": ticker,
            "agents": ["a", "b"],
            "analysis_date": "2026-07-30",
            "created_at": "2026-07-30T12:00:00Z",
        },
    )
    _write_json(
        run_dir,
        "raw_agent_outputs.json",
        {"run_id": run_id, "ticker": ticker, "agent_outputs": [{}, {}]},
    )
    _write_json(
        run_dir,
        "structured_agent_outputs.json",
        {
            "run_id": run_id,
            "ticker": ticker,
            "adapter_version": "week1.claim_extraction.v2",
            "records": [
                {"claim_id": "c1", "duplicate_group_id": "g1", "claim_quality": "analytical"},
                {"claim_id": "c2", "duplicate_group_id": "g2", "claim_quality": "analytical"},
                {"claim_id": "c3", "duplicate_group_id": "g3", "claim_quality": "context_only"},
            ],
            "canonical_relations": [
                {"relation_id": "r1", "validation_status": "accepted"},
                {"relation_id": "r2", "validation_status": "accepted"},
                {"relation_id": "r3", "validation_status": "rejected", "validation_rejection_reasons": ["evidence_not_found"]},
            ],
            "metadata": {
                "raw_output_count": 2,
                "raw_claim_count": 5,
                "candidate_segment_count": 6,
                "retained_claim_count": 3,
                "boilerplate_removed_count": 2,
                "disclaimer_removed_count": 1,
                "duplicate_removed_count": 0,
                "analytical_claim_count": 2,
                "context_only_claim_count": 1,
                "non_substantive_removed_count": 3,
            },
        },
    )
    _write_json(
        run_dir,
        "alpha_matches.json",
        {
            "run_id": run_id,
            "ticker": ticker,
            "matches": [
                {"match_status": "matched"},
                {"match_status": "matched"},
                {"match_status": "ambiguous"},
                {"match_status": "no_match"},
            ],
        },
    )
    _write_json(
        run_dir,
        "structure_graph.json",
        {
            "run_id": run_id,
            "ticker": ticker,
            "schema_version": "week3.structure_graph.v2",
            "primary_activation_version": "activation.v2.evidence_local_structure.v1",
            "graph_metrics": {
                "node_count": 4,
                "edge_count": 1,
                "duplicate_edges_merged": 1,
                "rejected_edges": {"self_loop": 1, "dangling_reference": 0},
            },
            "edges": [
                {
                    "source": "a",
                    "target": "b",
                    "relation_ids": ["r1"],
                    "source_claim_ids": ["c1"],
                    "alpha_ids": ["A101"],
                    "alpha_link_reason_codes": [],
                }
            ],
            "activation": {
                "alphas": [
                    {"alpha_id": "A101", "status": "regime_level", "activation_score": 91.0},
                    {"alpha_id": "A102", "status": "dominant", "activation_score": 80.0},
                    {"alpha_id": "A001", "status": "watch", "activation_score": 40.0},
                ]
            },
            "activation_versions": {
                "v2": {
                    "alphas": [
                        {
                            "alpha_id": "A101",
                            "status": "regime_level",
                            "activation_score": 91.0,
                            "direction": "bullish",
                            "raw_supporting_claim_count": 5,
                            "unique_evidence_fact_count": 3,
                            "distinct_supporting_agent_count": 2,
                            "evidence_overlap_ratio": 0.4,
                            "high_overlap_warning": False,
                            "components": {
                                "local_structure_support": {
                                    "incident_graph_edge_count": 1,
                                    "qualifying_local_edge_count": 1,
                                    "nonqualifying_local_edge_count": 0,
                                    "local_edge_exclusion_reasons": [],
                                }
                            },
                        },
                        {
                            "alpha_id": "A102",
                            "status": "dominant",
                            "activation_score": 80.0,
                            "raw_supporting_claim_count": 4,
                            "unique_evidence_fact_count": 4,
                            "distinct_supporting_agent_count": 3,
                            "evidence_overlap_ratio": 0.0,
                        },
                        {"alpha_id": "A001", "status": "watch", "activation_score": 40.0},
                    ]
                }
            },
        },
    )
    _write_json(
        run_dir,
        "tradingagents_comqutor_vocabulary_snapshot.json",
        {
            "taxonomy_version": "structure_engine.factor_aliases.v1",
            "taxonomy_sha256": "deadbeef",
            "relation_registry_version": "structure_engine.canonical_relation_registry.v1",
            "prompt_contract_version": "comqutor_structure_output_contract.v1",
            "prompt_contract_sha256": "cafebabe",
        },
    )
    if with_conflict_fields:
        conflict_payload = {
            "formula_version": "week4.conflict_score.mvp_v1",
            "main_conflict": {"conflict_id": "A101__A102"},
            "conflicts": [
                {
                    "alpha_a": "A101",
                    "alpha_b": "A102",
                    "conflict_id": "A101__A102",
                    "conflict_score": 42.0,
                    "conflict_level": "high",
                    "bull_raw_claim_count": 5,
                    "bull_unique_fact_count": 3,
                    "bull_distinct_agent_count": 2,
                    "bear_raw_claim_count": 4,
                    "bear_unique_fact_count": 4,
                    "bear_distinct_agent_count": 3,
                    "shared_fact_group_count": 0,
                    "shared_fact_group_ids": [],
                }
            ],
            "arbitration": {
                "declared_pair_count": 2,
                "admitted_count": 1,
                "suppressed_count": 1,
                "rejected_count": 0,
                "candidate_evaluations": [
                    {
                        "alpha_a": "A001",
                        "alpha_b": "A101",
                        "outcome": "suppressed",
                        "reason_codes": ["BELOW_ACTIVATION_THRESHOLD"],
                    },
                    {"alpha_a": "A101", "alpha_b": "A102", "outcome": "admitted", "reason_codes": []},
                ],
            },
        }
    else:
        conflict_payload = None
    return run_dir, conflict_payload


# ---------------------------------------------------------------------------
# 1. run_audit.v1 remains readable (minimal, pre-v2 fixture still parses).
# ---------------------------------------------------------------------------


def test_minimal_v1_style_fixture_still_produces_a_valid_v2_payload(tmp_path):
    run_id = "legacyrun1"
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    _write_json(run_dir, "metadata.json", {"run_id": run_id, "ticker": "SNDK"})
    _write_json(run_dir, "raw_agent_outputs.json", {"agent_outputs": []})
    _write_json(
        run_dir,
        "structured_agent_outputs.json",
        {"records": [], "metadata": {"raw_claim_count": 0}},
    )
    _write_json(run_dir, "alpha_matches.json", {"matches": []})
    _write_json(run_dir, "structure_graph.json", {"graph_metrics": {}})

    audit = build_run_audit_payload(run_id, tmp_path)
    assert audit["schema_version"] == RUN_AUDIT_SCHEMA_VERSION
    # Every v1 field is still present and computed the same way.
    assert audit["valid_claim_count"] == 0
    assert audit["graph_node_count"] == 0
    # New v2 sections never crash on a run with none of the new instrumentation.
    assert audit["run_identity"]["run_id"] == run_id
    assert audit["configuration_versions"]["taxonomy_version"]["value"] is None
    assert audit["audit_validation"]["overall_status"] in {"PASS", "PASS_WITH_WARNINGS", "FAIL"}


# ---------------------------------------------------------------------------
# 2. run_audit.v2 contains the required sections.
# ---------------------------------------------------------------------------


def test_v2_required_sections_are_present(tmp_path):
    run_dir, conflict_payload = _seed_rich_run(tmp_path)
    audit = build_run_audit_payload("runauditv2", tmp_path, conflict_payload=conflict_payload)
    for key in (
        "run_identity",
        "code_provenance",
        "configuration_versions",
        "artifact_manifest",
        "claims",
        "relations",
        "graph",
        "accounting_invariants",
        "graph_lineage",
        "activation_summary",
        "conflict_summary",
        "audit_validation",
    ):
        assert key in audit, key
    # v1 sections are untouched, not replaced.
    assert "canonical_relation_lineage" in audit
    assert "evidence_fact_integrity" in audit


# ---------------------------------------------------------------------------
# 3. Historical missing versions become explicit null + warning, never a guess.
# ---------------------------------------------------------------------------


def test_missing_configuration_version_is_null_with_warning_not_guessed(tmp_path):
    run_dir, conflict_payload = _seed_rich_run(tmp_path)
    audit = build_run_audit_payload("runauditv2", tmp_path, conflict_payload=conflict_payload)
    versions = audit["configuration_versions"]
    # No conflict-registry version constant exists anywhere in the codebase.
    assert versions["conflict_registry_version"]["value"] is None
    assert versions["conflict_registry_version"]["source"] == "not_recorded"
    assert versions["conflict_registry_version"]["warning"] == "VERSION_NOT_CAPTURED_AT_RUN_TIME"
    # A value that IS recorded is never mistaken for a provenance gap.
    assert versions["taxonomy_version"]["value"] == "structure_engine.factor_aliases.v1"
    assert "warning" not in versions["taxonomy_version"]
    assert versions["taxonomy_version"]["value"] not in (None, "")


def test_execution_mode_is_null_when_not_recorded_never_defaulted(tmp_path):
    """metadata.json with no ``run_type`` field must never be silently
    labeled "live_research" -- absence of replay lineage fields is not
    proof of a live run (see sprint boundary: "不得猜测")."""
    run_dir, conflict_payload = _seed_rich_run(tmp_path)
    audit = build_run_audit_payload("runauditv2", tmp_path, conflict_payload=conflict_payload)
    assert audit["run_identity"]["execution_mode"] is None


def test_execution_mode_reads_real_replay_lineage_when_present(tmp_path):
    run_id = "replayrun1"
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    _write_json(
        run_dir,
        "metadata.json",
        {"run_id": run_id, "ticker": "SNDK", "run_type": "architecture_replay", "source_run_id": "srcrun1"},
    )
    _write_json(run_dir, "raw_agent_outputs.json", {"agent_outputs": []})
    _write_json(run_dir, "structured_agent_outputs.json", {"records": [], "metadata": {}})
    _write_json(run_dir, "alpha_matches.json", {"matches": []})
    _write_json(run_dir, "structure_graph.json", {"graph_metrics": {}})

    audit = build_run_audit_payload(run_id, tmp_path)
    assert audit["run_identity"]["execution_mode"] == "architecture_replay"
    assert audit["run_identity"]["source_run_id"] == "srcrun1"


# ---------------------------------------------------------------------------
# 4. Artifact hashes are deterministic.
# ---------------------------------------------------------------------------


def test_artifact_manifest_hashes_are_deterministic_and_missing_files_are_explicit(tmp_path):
    run_dir, conflict_payload = _seed_rich_run(tmp_path)
    audit_1 = build_run_audit_payload("runauditv2", tmp_path, conflict_payload=conflict_payload)
    audit_2 = build_run_audit_payload("runauditv2", tmp_path, conflict_payload=conflict_payload)
    manifest_1 = {item["name"]: item for item in audit_1["artifact_manifest"]}
    manifest_2 = {item["name"]: item for item in audit_2["artifact_manifest"]}
    for name in manifest_1:
        assert manifest_1[name]["sha256"] == manifest_2[name]["sha256"], name
        if manifest_1[name]["exists"]:
            assert manifest_1[name]["sha256"] is not None

    # data_sanity.json / market_data_snapshot.json / run_audit.json /
    # week3_pipeline_status.json were never written by the fixture above --
    # must be reported as explicitly not present, never fabricated as empty.
    for name in ("data_sanity.json", "market_data_snapshot.json", "run_audit.json", "week3_pipeline_status.json"):
        assert manifest_1[name]["exists"] is False
        assert manifest_1[name]["status"] == "NOT_PRESENT"
        assert manifest_1[name]["sha256"] is None


# ---------------------------------------------------------------------------
# 5 & 6. Claim accounting invariants and edge-merge accounting are correct.
# ---------------------------------------------------------------------------


def test_claim_accounting_invariants_hold_on_a_consistent_fixture(tmp_path):
    run_dir, conflict_payload = _seed_rich_run(tmp_path)
    audit = build_run_audit_payload("runauditv2", tmp_path, conflict_payload=conflict_payload)
    invariants = {item["name"]: item for item in audit["accounting_invariants"]}
    assert invariants["candidate_segments_conserved"]["passed"] is True
    assert invariants["valid_claim_count_after_dedup"]["passed"] is True
    assert invariants["graph_edge_candidate_conservation"]["passed"] is True

    claims = audit["claims"]
    assert claims["candidate_segment_count"] == 6
    assert claims["retained_claim_count"] == 3
    assert claims["duplicate_group_count"] == 3

    graph = audit["graph"]
    # 1 admitted edge + 1 duplicate/rejected collapsed == 2 raw candidates.
    assert graph["merged_unique_edge_count"] == 1
    assert graph["claim_level_edge_candidate_count"] == 2


def test_accounting_invariant_failure_is_reported_not_hidden(tmp_path):
    """A genuinely inconsistent fixture must surface FAIL, not be silently
    marked passing -- this audit's job is to catch real drift."""
    run_id = "brokenrun1"
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    _write_json(run_dir, "metadata.json", {"run_id": run_id, "ticker": "SNDK"})
    _write_json(run_dir, "raw_agent_outputs.json", {"agent_outputs": []})
    _write_json(
        run_dir,
        "structured_agent_outputs.json",
        {
            "records": [],
            "metadata": {
                "candidate_segment_count": 100,
                "retained_claim_count": 1,
                "non_substantive_removed_count": 1,
            },
        },
    )
    _write_json(run_dir, "alpha_matches.json", {"matches": []})
    _write_json(run_dir, "structure_graph.json", {"graph_metrics": {}})

    audit = build_run_audit_payload(run_id, tmp_path)
    invariants = {item["name"]: item for item in audit["accounting_invariants"]}
    assert invariants["candidate_segments_conserved"]["passed"] is False
    assert audit["audit_validation"]["overall_status"] == "FAIL"
    assert "ACCOUNTING_INVARIANT_FAILED" in audit["audit_validation"]["warnings"]


def test_graph_lineage_edge_counts_match_real_edges(tmp_path):
    run_dir, conflict_payload = _seed_rich_run(tmp_path)
    audit = build_run_audit_payload("runauditv2", tmp_path, conflict_payload=conflict_payload)
    lineage = audit["graph_lineage"]
    assert lineage["edges_with_relation_ids"] == 1
    assert lineage["edges_with_source_claim_ids"] == 1
    assert lineage["edges_with_alpha_ids"] == 1
    assert lineage["edges_without_alpha_ids"] == 0


# ---------------------------------------------------------------------------
# 7. All conflict outcomes are included, not only admitted ones.
# ---------------------------------------------------------------------------


def test_conflict_summary_includes_every_declared_pair(tmp_path):
    run_dir, conflict_payload = _seed_rich_run(tmp_path)
    audit = build_run_audit_payload("runauditv2", tmp_path, conflict_payload=conflict_payload)
    summary = audit["conflict_summary"]
    assert summary["declared_pair_count"] == 2
    assert summary["evaluated_pair_count"] == 2
    assert summary["admitted_count"] == 1
    assert summary["suppressed_count"] == 1
    outcomes = {item["pair_id"]: item["outcome"] for item in summary["per_pair"]}
    assert outcomes["A001__A101"] == "suppressed"
    assert outcomes["A101__A102"] == "admitted"
    admitted_entry = next(item for item in summary["per_pair"] if item["pair_id"] == "A101__A102")
    assert admitted_entry["conflict_score"] == 42.0
    assert admitted_entry["is_main"] is True
    suppressed_entry = next(item for item in summary["per_pair"] if item["pair_id"] == "A001__A101")
    assert suppressed_entry["conflict_score"] is None
    assert suppressed_entry["is_main"] is False


# ---------------------------------------------------------------------------
# 8. Production/shadow counts are reused, not recomputed by a second algorithm.
# ---------------------------------------------------------------------------


def test_activation_summary_reuses_v2_alpha_counts_verbatim(tmp_path):
    run_dir, conflict_payload = _seed_rich_run(tmp_path)
    audit = build_run_audit_payload("runauditv2", tmp_path, conflict_payload=conflict_payload)
    per_alpha = audit["activation_summary"]["per_alpha"]
    assert per_alpha["A101"]["raw_supporting_claim_count"] == 5
    assert per_alpha["A101"]["unique_evidence_fact_count"] == 3
    # Identical to what evidence_eligibility (existing, unchanged section)
    # already reports for the same alpha -- never a second independent count.
    assert (
        per_alpha["A101"]["raw_supporting_claim_count"]
        == audit["evidence_eligibility"]["counts_by_alpha"]["A101"]["raw_supporting_claim_count"]
    )
    assert (
        per_alpha["A101"]["unique_evidence_fact_count"]
        == audit["evidence_eligibility"]["counts_by_alpha"]["A101"]["unique_evidence_fact_count"]
    )


# ---------------------------------------------------------------------------
# 9. DB/file round-trip preserves audit fields (repository is optional and
#    best-effort; its absence never breaks the payload, its presence is read
#    read-only and never mutated by this function).
# ---------------------------------------------------------------------------


def test_repository_is_used_read_only_and_optional(tmp_path):
    run_dir, conflict_payload = _seed_rich_run(tmp_path)

    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    repository = GraphPersistenceRepository(engine)
    with engine.begin() as conn:
        conn.execute(
            research_runs.insert().values(
                run_id="runauditv2",
                request_fingerprint="fp1",
                ticker="SNDK",
                analysis_date="2026-07-30",
                selected_analysts=[],
                execution_mode="real",
                provider_identity="anthropic",
                model_identity="claude",
                pipeline_identity={},
                status="completed",
                stage=None,
            )
        )

    audit_without_repo = build_run_audit_payload("runauditv2", tmp_path, conflict_payload=conflict_payload)
    assert audit_without_repo["run_identity"]["status"] is None

    audit_with_repo = build_run_audit_payload(
        "runauditv2", tmp_path, conflict_payload=conflict_payload, repository=repository
    )
    assert audit_with_repo["run_identity"]["status"] == "completed"
    assert audit_with_repo["run_identity"]["request_execution_mode"] == "real"

    # Read-only: the DB row is untouched by generating the audit.
    row = repository.get_research_run_record("runauditv2")
    assert row["status"] == "completed"


def test_run_audit_artifact_write_is_additive_with_repository(tmp_path):
    run_dir, conflict_payload = _seed_rich_run(tmp_path)
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    repository = GraphPersistenceRepository(engine)

    before = sorted(path.name for path in run_dir.iterdir())
    write_run_audit_artifact(
        "runauditv2", tmp_path, conflict_payload=conflict_payload, repository=repository
    )
    after = sorted(path.name for path in run_dir.iterdir())
    assert set(after) - set(before) == {"run_audit.json"}
    written = json.loads((run_dir / "run_audit.json").read_text(encoding="utf-8"))
    assert written["schema_version"] == RUN_AUDIT_SCHEMA_VERSION
    assert "run_identity" in written
    assert "audit_validation" in written


# ---------------------------------------------------------------------------
# 10. Audit generation never mutates the source artifacts it reads.
# ---------------------------------------------------------------------------


def test_audit_generation_does_not_mutate_source_artifacts(tmp_path):
    run_dir, conflict_payload = _seed_rich_run(tmp_path)
    before = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in run_dir.iterdir()
        if path.name != "run_audit.json"
    }
    build_run_audit_payload("runauditv2", tmp_path, conflict_payload=conflict_payload)
    after = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in run_dir.iterdir()
        if path.name != "run_audit.json"
    }
    assert before == after
