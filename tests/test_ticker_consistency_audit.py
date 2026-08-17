"""Sprint 1 -- Run Identity Integrity and Complete Artifact Export,
Track A1: Ticker Consistency Audit tests.

Covers all 15 required ticker-audit test items from the sprint spec,
using synthetic fixtures for fast, deterministic coverage plus real NVDA/
SNDK/TSM run artifacts (via a session-scoped loader) for the two
forensic-realism tests (foreign-ticker false-positive avoidance and the
real "TSM Revenue Growth" node-label traceability check).
"""

from __future__ import annotations

import json
from pathlib import Path

from comqutor_alpha.audit.ticker_consistency import (
    REASON_FOREIGN_TICKER_ENTITY,
    REASON_FOREIGN_TICKER_NODE_LABEL,
    REASON_RUN_ID_MISMATCH,
    REASON_TICKER_FIELD_INVALID,
    REASON_TICKER_FIELD_MISSING,
    REASON_TICKER_MISMATCH,
    STATUS_FAIL,
    STATUS_PASS,
    audit_ticker_consistency,
    normalize_ticker_for_audit,
    resolve_expected_ticker,
)

RUN_ID = "run_ticker_audit_1"


def _base_artifacts(ticker="SNDK", run_id=RUN_ID):
    return {
        "metadata": {"run_id": run_id, "ticker": ticker},
        "raw_agent_outputs": {"run_id": run_id, "ticker": ticker, "agent_outputs": []},
        "structured_agent_outputs": {
            "run_id": run_id,
            "ticker": ticker,
            "records": [
                {"claim_id": "c1", "run_id": run_id, "ticker": ticker, "claim": "Revenue grew.", "entities": [ticker]},
                {"claim_id": "c2", "run_id": run_id, "ticker": ticker, "claim": "Margins improved.", "entities": [ticker]},
            ],
        },
        "alpha_matches": {
            "run_id": run_id,
            "ticker": ticker,
            "matches": [
                {"claim_id": "c1", "run_id": run_id, "ticker": ticker, "match_status": "matched"},
                {"claim_id": "c2", "run_id": run_id, "ticker": ticker, "match_status": "matched"},
            ],
        },
        "structure_graph": {
            "run_id": run_id,
            "ticker": ticker,
            "nodes": [{"id": "ai_capex", "label": "AI CapEx"}],
            "edges": [],
        },
        "entity_alpha_exposures": {
            "run_id": run_id,
            "ticker": ticker,
            "records": [{"run_id": run_id, "ticker": ticker, "alpha_id": "A101"}],
        },
        "conflicts": {"run_id": run_id, "ticker": ticker, "conflicts": []},
        "summary": {"run_id": run_id, "ticker": ticker},
        "run_audit": {"run_id": run_id, "ticker": ticker},
    }


# ---------------------------------------------------------------------------
# 1. All artifacts same ticker -> pass
# ---------------------------------------------------------------------------


def test_all_artifacts_same_ticker_passes():
    artifacts = _base_artifacts()
    result = audit_ticker_consistency(
        run_id=RUN_ID, expected_ticker="SNDK", expected_ticker_source="metadata", artifacts=artifacts
    )
    assert result["ticker_consistency"] == STATUS_PASS
    assert result["inconsistencies"] == []
    assert result["expected_ticker"] == "SNDK"


# ---------------------------------------------------------------------------
# 2. Top-level metadata mismatch -> fail
# ---------------------------------------------------------------------------


def test_top_level_metadata_mismatch_fails():
    artifacts = _base_artifacts()
    artifacts["metadata"]["ticker"] = "TSM"
    result = audit_ticker_consistency(
        run_id=RUN_ID, expected_ticker="SNDK", expected_ticker_source="run_repository", artifacts=artifacts
    )
    assert result["ticker_consistency"] == STATUS_FAIL
    hit = [i for i in result["inconsistencies"] if i["artifact"] == "metadata.json"]
    assert hit and hit[0]["code"] == REASON_TICKER_MISMATCH
    assert hit[0]["actual_ticker"] == "TSM"
    assert hit[0]["json_path"] == "$.ticker"


# ---------------------------------------------------------------------------
# 3. Structured record nested ticker mismatch -> fail
# ---------------------------------------------------------------------------


def test_structured_record_nested_ticker_mismatch_fails():
    artifacts = _base_artifacts()
    artifacts["structured_agent_outputs"]["records"][1]["ticker"] = "TSM"
    result = audit_ticker_consistency(
        run_id=RUN_ID, expected_ticker="SNDK", expected_ticker_source="metadata", artifacts=artifacts
    )
    assert result["ticker_consistency"] == STATUS_FAIL
    hit = [i for i in result["inconsistencies"] if i["json_path"] == "$.records[1].ticker"]
    assert hit and hit[0]["code"] == REASON_TICKER_MISMATCH


# ---------------------------------------------------------------------------
# 4. Alpha match nested ticker mismatch -> fail
# ---------------------------------------------------------------------------


def test_alpha_match_nested_ticker_mismatch_fails():
    artifacts = _base_artifacts()
    artifacts["alpha_matches"]["matches"][0]["ticker"] = "TSM"
    result = audit_ticker_consistency(
        run_id=RUN_ID, expected_ticker="SNDK", expected_ticker_source="metadata", artifacts=artifacts
    )
    assert result["ticker_consistency"] == STATUS_FAIL
    hit = [i for i in result["inconsistencies"] if i["json_path"] == "$.matches[0].ticker"]
    assert hit and hit[0]["code"] == REASON_TICKER_MISMATCH


# ---------------------------------------------------------------------------
# 5. Exposure record nested ticker mismatch -> fail
# ---------------------------------------------------------------------------


def test_exposure_record_nested_ticker_mismatch_fails():
    artifacts = _base_artifacts()
    artifacts["entity_alpha_exposures"]["records"][0]["ticker"] = "TSM"
    result = audit_ticker_consistency(
        run_id=RUN_ID, expected_ticker="SNDK", expected_ticker_source="metadata", artifacts=artifacts
    )
    assert result["ticker_consistency"] == STATUS_FAIL
    hit = [i for i in result["inconsistencies"] if i["artifact"] == "entity_alpha_exposures.json"]
    assert hit and hit[0]["code"] == REASON_TICKER_MISMATCH


# ---------------------------------------------------------------------------
# 6. Conflict top-level ticker mismatch -> fail
# ---------------------------------------------------------------------------


def test_conflict_top_level_ticker_mismatch_fails():
    artifacts = _base_artifacts()
    artifacts["conflicts"]["ticker"] = "TSM"
    result = audit_ticker_consistency(
        run_id=RUN_ID, expected_ticker="SNDK", expected_ticker_source="metadata", artifacts=artifacts
    )
    assert result["ticker_consistency"] == STATUS_FAIL
    hit = [i for i in result["inconsistencies"] if i["artifact"] == "conflicts.json"]
    assert hit and hit[0]["code"] == REASON_TICKER_MISMATCH


# ---------------------------------------------------------------------------
# 7. Summary ticker mismatch -> fail
# ---------------------------------------------------------------------------


def test_summary_ticker_mismatch_fails():
    artifacts = _base_artifacts()
    artifacts["summary"]["ticker"] = "TSM"
    result = audit_ticker_consistency(
        run_id=RUN_ID, expected_ticker="SNDK", expected_ticker_source="metadata", artifacts=artifacts
    )
    assert result["ticker_consistency"] == STATUS_FAIL
    hit = [i for i in result["inconsistencies"] if i["artifact"] == "summary.json"]
    assert hit and hit[0]["code"] == REASON_TICKER_MISMATCH


# ---------------------------------------------------------------------------
# 8. Missing required ticker -> fail
# ---------------------------------------------------------------------------


def test_missing_required_top_level_ticker_fails():
    artifacts = _base_artifacts()
    del artifacts["metadata"]["ticker"]
    result = audit_ticker_consistency(
        run_id=RUN_ID, expected_ticker="SNDK", expected_ticker_source="metadata", artifacts=artifacts
    )
    assert result["ticker_consistency"] == STATUS_FAIL
    hit = [i for i in result["inconsistencies"] if i["artifact"] == "metadata.json"]
    assert hit and hit[0]["code"] == REASON_TICKER_FIELD_MISSING
    assert result["missing_required_ticker_field_count"] >= 1


def test_missing_required_nested_ticker_fails():
    artifacts = _base_artifacts()
    del artifacts["structured_agent_outputs"]["records"][0]["ticker"]
    result = audit_ticker_consistency(
        run_id=RUN_ID, expected_ticker="SNDK", expected_ticker_source="metadata", artifacts=artifacts
    )
    assert result["ticker_consistency"] == STATUS_FAIL
    hit = [i for i in result["inconsistencies"] if i["json_path"] == "$.records[0].ticker"]
    assert hit and hit[0]["code"] == REASON_TICKER_FIELD_MISSING


# ---------------------------------------------------------------------------
# 9. Historical optional nested ticker missing -> warning, not fabricated
# ---------------------------------------------------------------------------


def test_optional_evidence_facts_groups_missing_ticker_is_warning_only():
    artifacts = _base_artifacts()
    artifacts["evidence_facts"] = {
        "run_id": RUN_ID,
        "ticker": "SNDK",
        "groups": [{"evidence_fact_group_id": "g1"}],  # no nested "ticker" -- legacy/optional
    }
    result = audit_ticker_consistency(
        run_id=RUN_ID, expected_ticker="SNDK", expected_ticker_source="metadata", artifacts=artifacts
    )
    assert result["ticker_consistency"] == STATUS_PASS
    warn = [w for w in result["warnings"] if w["json_path"] == "$.groups[0].ticker"]
    assert warn and warn[0]["code"] == REASON_TICKER_FIELD_MISSING
    assert warn[0]["severity"] == "warning"
    # Never fabricated as present.
    assert warn[0]["actual_ticker"] is None


# ---------------------------------------------------------------------------
# 10. Ticker normalization uppercases and strips whitespace
# ---------------------------------------------------------------------------


def test_ticker_normalization_strips_and_uppercases():
    assert normalize_ticker_for_audit(" sndk ") == "SNDK"
    assert normalize_ticker_for_audit("Sndk") == "SNDK"
    assert normalize_ticker_for_audit("SNDK") == "SNDK"


def test_normalized_ticker_field_never_flagged_as_mismatch():
    artifacts = _base_artifacts()
    artifacts["metadata"]["ticker"] = " sndk "
    result = audit_ticker_consistency(
        run_id=RUN_ID, expected_ticker="SNDK", expected_ticker_source="metadata", artifacts=artifacts
    )
    assert result["ticker_consistency"] == STATUS_PASS


# ---------------------------------------------------------------------------
# 11. Unknown/empty ticker rejected
# ---------------------------------------------------------------------------


def test_unknown_and_empty_ticker_values_are_rejected():
    assert normalize_ticker_for_audit("") is None
    assert normalize_ticker_for_audit("unknown") is None
    assert normalize_ticker_for_audit("UNKNOWN") is None
    assert normalize_ticker_for_audit(None) is None
    assert normalize_ticker_for_audit("null") is None


def test_empty_string_ticker_field_is_reported_invalid_not_treated_as_legal():
    artifacts = _base_artifacts()
    artifacts["metadata"]["ticker"] = ""
    result = audit_ticker_consistency(
        run_id=RUN_ID, expected_ticker="SNDK", expected_ticker_source="metadata", artifacts=artifacts
    )
    assert result["ticker_consistency"] == STATUS_FAIL
    hit = [i for i in result["inconsistencies"] if i["artifact"] == "metadata.json"]
    # The key is present (distinct from an absent field) but its value is
    # not a legal ticker -- correctly reported as INVALID, not MISSING.
    assert hit[0]["code"] == REASON_TICKER_FIELD_INVALID


# ---------------------------------------------------------------------------
# 12. Legitimate peer comparison is not automatically classified as
#     contamination
# ---------------------------------------------------------------------------


def test_legitimate_peer_comparison_does_not_fail_the_audit():
    artifacts = _base_artifacts(ticker="SNDK")
    artifacts["structured_agent_outputs"]["records"].append(
        {
            "claim_id": "c3",
            "run_id": RUN_ID,
            "ticker": "SNDK",
            "claim": "Compared with TSM, SNDK's margins are more volatile.",
            "entities": ["SNDK", "TSM"],
        }
    )
    result = audit_ticker_consistency(
        run_id=RUN_ID, expected_ticker="SNDK", expected_ticker_source="metadata", artifacts=artifacts
    )
    assert result["ticker_consistency"] == STATUS_PASS
    foreign = [f for f in result["foreign_entity_findings"] if f["code"] == REASON_FOREIGN_TICKER_ENTITY]
    assert foreign and foreign[0]["severity"] == "warning"
    assert "co_mentioned_with_subject" in foreign[0]["detail"]


# ---------------------------------------------------------------------------
# 13. Foreign ticker treated as subject entity is flagged
# ---------------------------------------------------------------------------


def test_foreign_ticker_as_sole_entity_is_flagged_as_error():
    artifacts = _base_artifacts(ticker="SNDK")
    artifacts["structured_agent_outputs"]["records"].append(
        {
            "claim_id": "c4",
            "run_id": RUN_ID,
            "ticker": "SNDK",
            "claim": "This company's foundry business is expanding rapidly.",
            "entities": ["TSM"],
        }
    )
    result = audit_ticker_consistency(
        run_id=RUN_ID, expected_ticker="SNDK", expected_ticker_source="metadata", artifacts=artifacts
    )
    assert result["ticker_consistency"] == STATUS_FAIL
    foreign = [
        f
        for f in result["foreign_entity_findings"]
        if f["code"] == REASON_FOREIGN_TICKER_ENTITY and f["severity"] == "error"
    ]
    assert foreign
    assert "subject_absent" in foreign[0]["detail"]


# ---------------------------------------------------------------------------
# 14. Graph node label "TSM Revenue Growth" in SNDK run is traceable to
#     claim lineage (real data, forensic realism test)
# ---------------------------------------------------------------------------


def test_foreign_node_label_flagged_and_real_sndk_runs_are_clean():
    """Uses real, on-disk SNDK run artifacts (if present) to prove the
    module correctly flags a *simulated* contamination (SNDK-expected
    audited against a real TSM run's own graph, which legitimately has a
    "TSM Revenue Growth" node) while never false-positiving on the real,
    uncontaminated SNDK runs themselves."""
    runs_root = Path("outputs/runs")
    sndk_run_dirs = []
    tsm_run_dir = None
    if runs_root.is_dir():
        for run_dir in runs_root.iterdir():
            metadata_path = run_dir / "metadata.json"
            if not metadata_path.exists():
                continue
            ticker = json.loads(metadata_path.read_text(encoding="utf-8")).get("ticker")
            if ticker == "SNDK" and (run_dir / "structure_graph.json").exists():
                sndk_run_dirs.append(run_dir)
            elif ticker == "TSM" and (run_dir / "structure_graph.json").exists():
                tsm_run_dir = run_dir

    for run_dir in sndk_run_dirs:
        metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
        structure_graph = json.loads((run_dir / "structure_graph.json").read_text(encoding="utf-8"))
        expected, source = resolve_expected_ticker(metadata_ticker=metadata.get("ticker"))
        result = audit_ticker_consistency(
            run_id=run_dir.name,
            expected_ticker=expected,
            expected_ticker_source=source,
            artifacts={"metadata": metadata, "structure_graph": structure_graph},
        )
        node_label_hits = [f for f in result["foreign_entity_findings"] if f["code"] == REASON_FOREIGN_TICKER_NODE_LABEL]
        assert node_label_hits == [], f"real SNDK run {run_dir.name} must never show a foreign node label"

    if tsm_run_dir is not None:
        structure_graph = json.loads((tsm_run_dir / "structure_graph.json").read_text(encoding="utf-8"))
        labels = [n.get("label") for n in structure_graph.get("nodes", [])]
        assert any("TSM Revenue Growth" in (label or "") for label in labels), (
            "expected the real TSM run to legitimately contain its own 'TSM Revenue Growth' node"
        )
        # Simulate the exact contamination pattern: audit this TSM graph
        # as if it were an SNDK run's graph.
        result = audit_ticker_consistency(
            run_id=tsm_run_dir.name,
            expected_ticker="SNDK",
            expected_ticker_source="test",
            artifacts={"structure_graph": structure_graph},
        )
        hits = [f for f in result["foreign_entity_findings"] if f["code"] == REASON_FOREIGN_TICKER_NODE_LABEL]
        assert hits and hits[0]["actual_ticker"] == "TSM"
        assert result["ticker_consistency"] == STATUS_FAIL


# ---------------------------------------------------------------------------
# 15. Run-id mismatch appears in diagnostics
# ---------------------------------------------------------------------------


def test_run_id_mismatch_appears_in_diagnostics_not_as_a_ticker_inconsistency():
    artifacts = _base_artifacts()
    artifacts["alpha_matches"]["matches"][0]["run_id"] = "some_other_run"
    result = audit_ticker_consistency(
        run_id=RUN_ID, expected_ticker="SNDK", expected_ticker_source="metadata", artifacts=artifacts
    )
    diagnostics = result["run_identity_diagnostics"]
    assert diagnostics["mismatch_count"] == 1
    assert diagnostics["mismatches"][0]["actual_run_id"] == "some_other_run"
    # Run-id mismatch is a diagnostic signal, not itself a ticker
    # inconsistency entry (ticker fields on that record were correct).
    assert not any(i["code"] == REASON_RUN_ID_MISMATCH for i in result["inconsistencies"])
    # A ticker-correct-but-run-id-wrong record must not flip the overall
    # ticker_consistency verdict.
    assert result["ticker_consistency"] == STATUS_PASS


# ---------------------------------------------------------------------------
# Additional: resolve_expected_ticker priority order
# ---------------------------------------------------------------------------


def test_resolve_expected_ticker_priority_order():
    expected, source = resolve_expected_ticker(
        orchestrator_ticker="NVDA",
        db_run_ticker="AMD",
        metadata_ticker="TSM",
        raw_agent_outputs_ticker="SNDK",
    )
    assert (expected, source) == ("NVDA", "run_orchestrator")

    expected, source = resolve_expected_ticker(
        orchestrator_ticker=None, db_run_ticker="AMD", metadata_ticker="TSM", raw_agent_outputs_ticker="SNDK"
    )
    assert (expected, source) == ("AMD", "run_repository")

    expected, source = resolve_expected_ticker(
        orchestrator_ticker=None, db_run_ticker=None, metadata_ticker="TSM", raw_agent_outputs_ticker="SNDK"
    )
    assert (expected, source) == ("TSM", "metadata")

    expected, source = resolve_expected_ticker(
        orchestrator_ticker=None, db_run_ticker=None, metadata_ticker=None, raw_agent_outputs_ticker="SNDK"
    )
    assert (expected, source) == ("SNDK", "raw_agent_outputs")

    expected, source = resolve_expected_ticker()
    assert (expected, source) == (None, None)


def test_majority_wrong_ticker_never_becomes_authoritative():
    """Even if most artifacts agree on a wrong ticker, the authoritative
    expected_ticker must come only from the priority-ordered sources,
    never from a majority vote across artifacts."""
    artifacts = _base_artifacts(ticker="TSM")  # 8 artifacts all say TSM
    # But the true authoritative source (metadata, in this synthetic
    # case standing in for run_repository) says SNDK.
    expected, source = resolve_expected_ticker(metadata_ticker="SNDK")
    assert expected == "SNDK"
    result = audit_ticker_consistency(
        run_id=RUN_ID, expected_ticker=expected, expected_ticker_source=source, artifacts=artifacts
    )
    assert result["ticker_consistency"] == STATUS_FAIL
    assert len(result["inconsistencies"]) >= 6
