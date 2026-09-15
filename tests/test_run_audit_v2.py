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
# 7b. v0.1.3 QA Closure, Section E: ADMITTED / CANDIDATE / SUPPRESSED /
# REJECTED conflict-pair collections are strictly separated, main_conflict
# comes only from admitted, and the new conservation invariants catch drift.
# ---------------------------------------------------------------------------


def test_conflict_accounting_invariants_pass_on_a_consistent_fixture(tmp_path):
    run_dir, conflict_payload = _seed_rich_run(tmp_path)
    audit = build_run_audit_payload("runauditv2", tmp_path, conflict_payload=conflict_payload)
    invariants = {item["name"]: item for item in audit["accounting_invariants"]}
    assert invariants["conflict_pairs_conserved"]["passed"] is True
    assert invariants["conflict_pairs_conserved"]["expected"] == 2
    assert invariants["conflict_pairs_conserved"]["actual"] == 2
    assert invariants["candidate_conflicts_are_a_subset_of_suppressed"]["passed"] is True
    assert "ACCOUNTING_INVARIANT_FAILED" not in audit["audit_validation"]["warnings"]


def test_conflict_pair_conservation_invariant_fails_when_counts_do_not_sum(tmp_path):
    """A tampered arbitration block (declared_pair_count inflated beyond what
    admitted+suppressed+rejected actually account for) must surface FAIL,
    never be silently reported as consistent."""
    run_dir, conflict_payload = _seed_rich_run(tmp_path)
    conflict_payload["arbitration"]["declared_pair_count"] = 5
    audit = build_run_audit_payload("runauditv2", tmp_path, conflict_payload=conflict_payload)
    invariants = {item["name"]: item for item in audit["accounting_invariants"]}
    assert invariants["conflict_pairs_conserved"]["passed"] is False
    assert audit["audit_validation"]["overall_status"] == "FAIL"
    assert "ACCOUNTING_INVARIANT_FAILED" in audit["audit_validation"]["warnings"]


def test_b2_denied_candidate_pair_is_counted_as_candidate_never_admitted_never_main(tmp_path):
    """A pair that reached B2 evaluation but was denied admission
    (admissibility.status == "candidate") must be counted under
    candidate_conflict_count, must have outcome "suppressed" (never
    "admitted"), and must never become main_conflict -- proving CANDIDATE
    cannot leak into ADMITTED at the audit layer."""
    run_dir, conflict_payload = _seed_rich_run(tmp_path)
    conflict_payload["arbitration"]["candidate_evaluations"][0]["admissibility"] = {
        "status": "candidate",
        "reason_codes": ["INSUFFICIENT_BULL_SUPPORTING_EVIDENCE"],
    }
    audit = build_run_audit_payload("runauditv2", tmp_path, conflict_payload=conflict_payload)
    summary = audit["conflict_summary"]
    assert summary["candidate_conflict_count"] == 1
    denied_entry = next(item for item in summary["per_pair"] if item["pair_id"] == "A001__A101")
    assert denied_entry["outcome"] == "suppressed"
    assert denied_entry["is_main"] is False
    assert summary["main_conflict_id"] == "A101__A102"
    invariants = {item["name"]: item for item in audit["accounting_invariants"]}
    assert invariants["candidate_conflicts_are_a_subset_of_suppressed"]["passed"] is True


# ---------------------------------------------------------------------------
# 7c. v0.1.3 QA Closure, Item 3: seed_status_consistency. entity_exposure_
# audit.current_seed_status must always equal an independent, freshly-
# resolved call against the live seed file for this run's own ticker -- one
# canonical status, never two call sites that happen to usually agree.
# ---------------------------------------------------------------------------


def test_seed_status_consistency_invariant_passes_for_an_approved_ticker(tmp_path):
    run_dir, conflict_payload = _seed_rich_run(tmp_path, ticker="SNDK")
    audit = build_run_audit_payload("runauditv2", tmp_path, conflict_payload=conflict_payload)
    invariants = {item["name"]: item for item in audit["accounting_invariants"]}
    seed_invariant = invariants["seed_status_consistency"]
    assert seed_invariant["passed"] is True
    assert seed_invariant["expected"] == "approved_gating"
    assert seed_invariant["actual"] == "approved_gating"
    assert audit["entity_exposure"]["current_seed_status"] == "approved_gating"
    assert "ACCOUNTING_INVARIANT_FAILED" not in audit["audit_validation"]["warnings"]


def test_seed_status_consistency_invariant_reflects_draft_shadow_for_unconfigured_ticker(tmp_path):
    run_dir, conflict_payload = _seed_rich_run(tmp_path, ticker="GOOGL")
    audit = build_run_audit_payload("runauditv2", tmp_path, conflict_payload=conflict_payload)
    invariants = {item["name"]: item for item in audit["accounting_invariants"]}
    assert invariants["seed_status_consistency"]["passed"] is True
    assert audit["entity_exposure"]["current_seed_status"] == "draft_shadow"


# ---------------------------------------------------------------------------
# 7d. Alpha Memory Implementation Step 2: additive alpha_memory section,
# SHADOW ONLY, atomic edge phi as the primary identity, whole-Alpha
# aggregate fingerprint demoted to a secondary diagnostic, and proof that
# activation_summary/conflict_summary are completely unaffected.
# ---------------------------------------------------------------------------


def test_alpha_memory_section_is_present_shadow_only_and_never_modulates(tmp_path):
    run_dir, conflict_payload = _seed_rich_run(tmp_path)
    audit = build_run_audit_payload("runauditv2", tmp_path, conflict_payload=conflict_payload)
    alpha_memory = audit["alpha_memory"]
    assert alpha_memory["mode"] == "shadow"
    assert alpha_memory["activation_modulation_applied"] is False
    assert alpha_memory["identity_model"] == "atomic_edge_phi"
    assert alpha_memory["identity_version"] == "alpha_memory.phi_edge.v1"
    # The fixture's own structure_graph.json edge (a->b, alpha_ids=["A101"])
    # produces exactly one atomic phi structure, with its history merged in.
    assert len(alpha_memory["phi_structures"]) == 1
    structure = alpha_memory["phi_structures"][0]
    assert structure["alpha_id"] == "A101"
    assert structure["prior_run_ids"] == []
    # The secondary aggregate fingerprint is present, separately labeled.
    assert len(alpha_memory["aggregate_fingerprints"]) == 1
    assert "aggregate_fingerprint_id" in alpha_memory["aggregate_fingerprints"][0]
    assert alpha_memory["aggregate_fingerprints"][0]["identity_version"] == "alpha_memory.aggregate_fingerprint.v1"
    # Alpha-level descriptive summary.
    assert alpha_memory["alpha_memory_summary"] == [
        {
            "alpha_id": "A101",
            "current_phi_count": 1,
            "first_seen_phi_count": 1,
            "recurring_phi_count": 0,
            "historically_matched_phi_count": 0,
            "unmatched_phi_count": 1,
            "recurrence_ratio": 0.0,
            "prior_observation_total": 0,
        }
    ]
    # No instability signals for a single, standalone run.
    assert alpha_memory["instability_signals"]["alpha_attribution_variance"] == []
    assert alpha_memory["instability_signals"]["edge_type_variance"] == []


def test_alpha_memory_section_does_not_change_activation_or_conflict_summary(tmp_path):
    """Proof that the alpha_memory section changes nothing about the
    pre-existing activation_summary/conflict_summary/audit_validation
    values -- computed from the exact same fixture used by
    test_activation_summary_reuses_v2_alpha_counts_verbatim and
    test_conflict_summary_includes_every_declared_pair below, whose own
    assertions on those two sections remain byte-identical with
    alpha_memory now present."""
    run_dir, conflict_payload = _seed_rich_run(tmp_path)
    audit = build_run_audit_payload("runauditv2", tmp_path, conflict_payload=conflict_payload)
    assert audit["activation_summary"]["active_count"] == 0
    assert audit["activation_summary"]["dominant_count"] == 1
    assert audit["activation_summary"]["regime_level_count"] == 1
    assert audit["conflict_summary"]["admitted_count"] == 1
    assert audit["conflict_summary"]["main_conflict_id"] == "A101__A102"
    assert audit["audit_validation"]["overall_status"] in ("PASS", "PASS_WITH_WARNINGS")
    assert "ACCOUNTING_INVARIANT_FAILED" not in audit["audit_validation"]["warnings"]


def test_alpha_memory_finds_a_real_prior_atomic_match_across_two_runs(tmp_path):
    """End-to-end proof (still fully synthetic/offline) that the cross-run
    reader finds an atomic edge match when a second run for the same
    ticker genuinely shares the same edge."""
    _seed_rich_run(tmp_path, run_id="runauditv2_a", ticker="MSFT")
    _seed_rich_run(tmp_path, run_id="runauditv2_b", ticker="MSFT")
    audit_b = build_run_audit_payload("runauditv2_b", tmp_path)
    structures = audit_b["alpha_memory"]["phi_structures"]
    a101_structure = next(s for s in structures if s["alpha_id"] == "A101")
    assert a101_structure["prior_run_ids"] == ["runauditv2_a"]
    assert a101_structure["prior_observation_count"] == 1
    summary = next(s for s in audit_b["alpha_memory"]["alpha_memory_summary"] if s["alpha_id"] == "A101")
    assert summary["historically_matched_phi_count"] == 1
    assert summary["unmatched_phi_count"] == 0


def test_alpha_memory_instability_signals_are_detected_but_never_change_official_sections(tmp_path):
    """Two runs for the same ticker with a genuinely different alpha
    attribution on the identical edge -- proves the diagnostic fires, and
    that activation_summary/conflict_summary/audit_validation and B4's own
    activation_level_alignment tests all remain completely unaffected by
    its presence (points 13-16 of Implementation Step 2's test list)."""
    run_a_dir, conflict_payload = _seed_rich_run(tmp_path, run_id="runauditv2_c", ticker="SNDK")
    # Second run: same edge, but linked to an ADDITIONAL alpha (A999) on
    # top of the fixture's own A101 -- a genuine attribution variance.
    graph_path = tmp_path / "runauditv2_c" / "structure_graph.json"
    graph_payload = json.loads(graph_path.read_text())
    variant_edges = [dict(e) for e in graph_payload["edges"]]
    for e in variant_edges:
        e["alpha_ids"] = list(e.get("alpha_ids") or []) + ["A999"]
    run_b_dir = tmp_path / "runauditv2_d"
    run_b_dir.mkdir()
    for name in ("metadata.json", "alpha_matches.json", "structure_graph.json"):
        payload = json.loads((tmp_path / "runauditv2_c" / name).read_text())
        if name == "metadata.json":
            payload["run_id"] = "runauditv2_d"
        if name == "structure_graph.json":
            payload["run_id"] = "runauditv2_d"
            payload["edges"] = variant_edges
        _write_json(run_b_dir, name, payload)
    for name in ("raw_agent_outputs.json", "tradingagents_comqutor_vocabulary_snapshot.json"):
        payload = json.loads((tmp_path / "runauditv2_c" / name).read_text())
        _write_json(run_b_dir, name, payload)

    audit_d = build_run_audit_payload("runauditv2_d", tmp_path, conflict_payload=conflict_payload)
    signals = audit_d["alpha_memory"]["instability_signals"]["alpha_attribution_variance"]
    assert len(signals) == 1
    variant_alpha_sets = {tuple(v["alpha_ids"]) for v in signals[0]["observed_variants"]}
    assert ("A101",) in variant_alpha_sets
    assert ("A101", "A999") in variant_alpha_sets

    # Official sections are completely unaffected by the diagnostic firing.
    assert audit_d["activation_summary"]["dominant_count"] == 1
    assert audit_d["activation_summary"]["regime_level_count"] == 1
    assert audit_d["conflict_summary"]["main_conflict_id"] == "A101__A102"
    assert audit_d["audit_validation"]["overall_status"] in ("PASS", "PASS_WITH_WARNINGS")
    assert "ACCOUNTING_INVARIANT_FAILED" not in audit_d["audit_validation"]["warnings"]
    assert audit_d["alpha_memory"]["activation_modulation_applied"] is False


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


# ---------------------------------------------------------------------------
# Pure-LLM Alpha Production Boundary Hardening: run_audit.json must let an
# operator distinguish A) matched, B) semantic NONE, C) the Alpha
# classifier not successfully running at all -- see
# comqutor_alpha/structure_engine/alpha_mapper.py's match_status="unavailable"
# state and tests/test_alpha_production_boundary_hardening.py for the
# per-claim contract this run-level rollup is built from.
# ---------------------------------------------------------------------------


def _seed_run_with_alpha_matches(tmp_path, run_id, matches):
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    _write_json(run_dir, "metadata.json", {"run_id": run_id, "ticker": "SNDK"})
    _write_json(run_dir, "raw_agent_outputs.json", {"agent_outputs": []})
    _write_json(
        run_dir,
        "structured_agent_outputs.json",
        {"records": [], "metadata": {"raw_claim_count": 0}},
    )
    _write_json(run_dir, "alpha_matches.json", {"matches": matches})
    _write_json(run_dir, "structure_graph.json", {"graph_metrics": {}})
    return run_dir


def test_unavailable_alpha_count_and_reason_breakdown_are_computed(tmp_path):
    _seed_run_with_alpha_matches(
        tmp_path,
        "run_unavail",
        [
            {"match_status": "matched"},
            {"match_status": "no_match"},
            {"match_status": "unavailable", "alpha_match_fallback_reason": "provider_timeout"},
            {"match_status": "unavailable", "alpha_match_fallback_reason": "provider_timeout"},
            {"match_status": "unavailable", "alpha_match_fallback_reason": "invalid_alpha_id"},
        ],
    )
    audit = build_run_audit_payload("run_unavail", tmp_path)
    assert audit["matched_alpha_count"] == 1
    assert audit["no_match_count"] == 1
    assert audit["unavailable_alpha_count"] == 3
    assert audit["alpha_unavailable_reason_counts"] == {
        "provider_timeout": 2,
        "invalid_alpha_id": 1,
    }
    # A genuine operational failure (not merely "disabled") is a degraded
    # run state, not just informational.
    assert "ALPHA_SEMANTIC_DEGRADED" in audit["warnings"]
    assert "ALPHA_SEMANTIC_DISABLED" not in audit["warnings"]


def test_purely_disabled_alpha_classifier_warns_disabled_not_degraded(tmp_path):
    _seed_run_with_alpha_matches(
        tmp_path,
        "run_disabled",
        [
            {"match_status": "unavailable", "alpha_match_fallback_reason": "disabled"},
            {"match_status": "unavailable", "alpha_match_fallback_reason": "disabled"},
        ],
    )
    audit = build_run_audit_payload("run_disabled", tmp_path)
    assert audit["unavailable_alpha_count"] == 2
    assert audit["alpha_unavailable_reason_counts"] == {"disabled": 2}
    assert "ALPHA_SEMANTIC_DISABLED" in audit["warnings"]
    assert "ALPHA_SEMANTIC_DEGRADED" not in audit["warnings"]


def test_no_unavailable_claims_means_no_alpha_semantic_warning(tmp_path):
    _seed_run_with_alpha_matches(
        tmp_path,
        "run_all_matched",
        [{"match_status": "matched"}, {"match_status": "no_match"}],
    )
    audit = build_run_audit_payload("run_all_matched", tmp_path)
    assert audit["unavailable_alpha_count"] == 0
    assert audit["alpha_unavailable_reason_counts"] == {}
    assert "ALPHA_SEMANTIC_DISABLED" not in audit["warnings"]
    assert "ALPHA_SEMANTIC_DEGRADED" not in audit["warnings"]
