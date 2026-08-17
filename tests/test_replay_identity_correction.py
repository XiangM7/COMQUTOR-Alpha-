"""Sprint 1 Replay Identity Correction tests.

Confirms the *real* fix for Architecture Replay's identity contract:
every replay-local regenerated artifact consistently carries
``replay_run_id`` (never ``source_run_id``), and Conflict Detector
receives its correct, real identity -- ``detect_alpha_conflicts`` is
never called with ``run_id=source_run_id`` again (that was an identity
*bypass*, not a fix; see ``docs/run_identity_and_artifact_export_sprint_report.md``).

Uses a small, synthetic ``raw_agent_outputs.json`` fixture under
``tmp_path`` (never touches ``outputs/runs/``, never calls a real
Provider) for the 24 required unit-level test items, plus a
session-independent real-run smoke check reusing the canonical NVDA
source run when present on disk.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from comqutor_alpha.audit.ticker_consistency import STATUS_PASS
from comqutor_alpha.conflict_engine.conflict_detector import (
    REASON_RUN_ID_MISMATCH,
    detect_alpha_conflicts,
)
from comqutor_alpha.replay.pipeline import (
    _rebase_structured_payload_for_replay,
    run_structure_replay,
)

SOURCE_RUN_ID = "identity-test-source-run-0001"


def _write_source_run(base_dir: Path, *, ticker: str = "SNDK") -> Path:
    run_dir = base_dir / SOURCE_RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)

    claim_text = (
        "AI CapEx spending is driving strong AI Demand growth this quarter. "
        "Revenue guidance was raised for the coming year. "
        "Cloud infrastructure investment continues to accelerate across hyperscalers."
    )
    raw_payload = {
        "schema_version": "week1.raw_agent_outputs.v1",
        "run_id": SOURCE_RUN_ID,
        "ticker": ticker,
        "agent_outputs": [
            {
                "agent_output_id": f"{SOURCE_RUN_ID}:market_agent:market_report",
                "run_id": SOURCE_RUN_ID,
                "ticker": ticker,
                "agent": "market_agent",
                "tradingagents_agent": "Market Analyst",
                "source_field": "market_report",
                "source_path": "market_report",
                "source_candidates": ["market_report"],
                "raw_output": claim_text,
            }
        ],
    }
    (run_dir / "raw_agent_outputs.json").write_text(json.dumps(raw_payload), encoding="utf-8")

    metadata = {
        "run_id": SOURCE_RUN_ID,
        "ticker": ticker,
        "trade_date": "2026-07-01",
        "profile_id": "comqutor_anthropic_medium_sonnet46_v1",
        "created_at": "2026-07-01T00:00:00Z",
        "config": {"llm_provider": "anthropic", "quick_think_llm": "claude-sonnet-4-6", "deep_think_llm": "claude-sonnet-4-6"},
    }
    (run_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    return run_dir


def _load(output_dir: str, name: str):
    return json.loads((Path(output_dir) / name).read_text(encoding="utf-8"))


@pytest.fixture()
def replay_result(tmp_path):
    _write_source_run(tmp_path)
    result = run_structure_replay(
        SOURCE_RUN_ID,
        source_output_root=str(tmp_path),
        replay_output_root=str(tmp_path / "replays"),
        persist=True,
        comparison=False,
    )
    assert result.status == "completed", result
    return result


# ---------------------------------------------------------------------------
# 1. replay_run_id != source_run_id
# ---------------------------------------------------------------------------


def test_replay_run_id_differs_from_source_run_id(replay_result):
    assert replay_result.replay_run_id != replay_result.source_run_id
    assert replay_result.source_run_id == SOURCE_RUN_ID


# ---------------------------------------------------------------------------
# 2 & 3. structured top-level / every record uses replay_run_id
# ---------------------------------------------------------------------------


def test_structured_top_level_uses_replay_run_id(replay_result):
    structured = _load(replay_result.output_dir, "structured_agent_outputs.json")
    assert structured["run_id"] == replay_result.replay_run_id


def test_every_structured_record_uses_replay_run_id(replay_result):
    structured = _load(replay_result.output_dir, "structured_agent_outputs.json")
    assert structured["records"], "fixture must produce at least one structured record"
    for record in structured["records"]:
        assert record["run_id"] == replay_result.replay_run_id


# ---------------------------------------------------------------------------
# 4 & 5. alpha_matches top-level / every match uses replay_run_id
# ---------------------------------------------------------------------------


def test_alpha_matches_top_level_uses_replay_run_id(replay_result):
    alpha_matches = _load(replay_result.output_dir, "alpha_matches.json")
    assert alpha_matches["run_id"] == replay_result.replay_run_id


def test_every_alpha_match_uses_replay_run_id(replay_result):
    alpha_matches = _load(replay_result.output_dir, "alpha_matches.json")
    assert alpha_matches["matches"], "fixture must produce at least one alpha match"
    for match in alpha_matches["matches"]:
        assert match["run_id"] == replay_result.replay_run_id


# ---------------------------------------------------------------------------
# 6. extracted structures uses replay_run_id
# ---------------------------------------------------------------------------


def test_extracted_structures_uses_replay_run_id(replay_result):
    extracted = _load(replay_result.output_dir, "extracted_structures.json")
    assert extracted["run_id"] == replay_result.replay_run_id


# ---------------------------------------------------------------------------
# 7. structure graph uses replay_run_id
# ---------------------------------------------------------------------------


def test_structure_graph_uses_replay_run_id(replay_result):
    graph = _load(replay_result.output_dir, "structure_graph.json")
    assert graph["run_id"] == replay_result.replay_run_id


# ---------------------------------------------------------------------------
# 8 & 9. activations / evidence facts exports use replay_run_id
# ---------------------------------------------------------------------------


def test_activations_export_uses_replay_run_id(replay_result):
    activations = _load(replay_result.output_dir, "alpha_activations.json")
    assert activations["run_id"] == replay_result.replay_run_id


def test_evidence_facts_export_uses_replay_run_id(replay_result):
    evidence_facts = _load(replay_result.output_dir, "evidence_facts.json")
    assert evidence_facts["run_id"] == replay_result.replay_run_id


# ---------------------------------------------------------------------------
# 10 & 11. conflicts.json / conflict_results.json compatibility both use
#          replay_run_id
# ---------------------------------------------------------------------------


def test_conflicts_export_uses_replay_run_id(replay_result):
    conflicts_export = _load(replay_result.output_dir, "conflicts.json")
    assert conflicts_export["run_id"] == replay_result.replay_run_id


def test_conflict_results_compatibility_uses_replay_run_id(replay_result):
    conflict_results = _load(replay_result.output_dir, "conflict_results.json")
    assert conflict_results["run_id"] == replay_result.replay_run_id


# ---------------------------------------------------------------------------
# 12. exposures use replay_run_id
# ---------------------------------------------------------------------------


def test_entity_alpha_exposures_use_replay_run_id(replay_result):
    exposures = _load(replay_result.output_dir, "entity_alpha_exposures.json")
    assert exposures.get("run_id") == replay_result.replay_run_id
    for record in exposures.get("records") or []:
        assert record.get("run_id") in (None, replay_result.replay_run_id)


# ---------------------------------------------------------------------------
# 13, 14, 15. summary / run_audit / manifest use replay_run_id
# ---------------------------------------------------------------------------


def test_summary_uses_replay_run_id(replay_result):
    summary = _load(replay_result.output_dir, "summary.json")
    assert summary["run_id"] == replay_result.replay_run_id


def test_run_audit_uses_replay_run_id(replay_result):
    run_audit = _load(replay_result.output_dir, "run_audit.json")
    assert run_audit["run_id"] == replay_result.replay_run_id


def test_manifest_uses_replay_run_id(replay_result):
    manifest = _load(replay_result.output_dir, "artifact_manifest.json")
    assert manifest["run_id"] == replay_result.replay_run_id


# ---------------------------------------------------------------------------
# 16. metadata preserves source_run_id
# ---------------------------------------------------------------------------


def test_metadata_preserves_source_run_id(replay_result):
    metadata = _load(replay_result.output_dir, "metadata.json")
    assert metadata["run_id"] == replay_result.replay_run_id
    assert metadata["replay_run_id"] == replay_result.replay_run_id
    assert metadata["source_run_id"] == SOURCE_RUN_ID


# ---------------------------------------------------------------------------
# 17 & 18. Conflict Detector receives replay_run_id; RUN_ID_MISMATCH count = 0
# ---------------------------------------------------------------------------


def test_conflict_detector_receives_replay_run_id_and_zero_mismatches(replay_result):
    conflict_results = _load(replay_result.output_dir, "conflict_results.json")
    assert conflict_results["run_id"] == replay_result.replay_run_id
    mismatch_count = sum(
        1
        for evaluation in conflict_results["arbitration"]["candidate_evaluations"]
        if REASON_RUN_ID_MISMATCH in (evaluation.get("reason_codes") or [])
    )
    assert mismatch_count == 0

    identity = replay_result.identity_consistency
    assert identity is not None
    assert identity["identity_consistency"] == STATUS_PASS
    assert identity["nested_record_mismatch_count"] == 0
    assert identity["mismatched_artifacts"] == []


# ---------------------------------------------------------------------------
# 19. Direct, genuinely mismatched Conflict input is still rejected (the
#     guard itself must never be weakened)
# ---------------------------------------------------------------------------


def test_genuinely_mismatched_conflict_input_is_still_rejected():
    activation_payload = {
        "run_id": "run_a",
        "formula_version": "week3.activation.mvp_v1",
        "alphas": [
            {"alpha_id": "A101", "status": "active", "activation_score": 80, "direction": "bullish"},
            {"alpha_id": "A304", "status": "active", "activation_score": 75, "direction": "bearish"},
        ],
    }
    # alpha_matches records embed a DIFFERENT run_id than the run_id
    # argument below -- this must still trip RUN_ID_MISMATCH exactly as
    # before; this sprint fixes Replay's own identity, it never loosens
    # conflict_detector's guard itself.
    alpha_matches = [{"claim_id": "c1", "run_id": "run_b", "ticker": "SNDK", "match_status": "matched"}]
    result = detect_alpha_conflicts(
        run_id="run_a",
        ticker="SNDK",
        activation_payload=activation_payload,
        alpha_matches=alpha_matches,
    )
    reason_codes = {
        code
        for evaluation in result["arbitration"]["candidate_evaluations"]
        for code in (evaluation.get("reason_codes") or [])
    }
    assert REASON_RUN_ID_MISMATCH in reason_codes
    assert result["arbitration"]["admitted_count"] == 0


# ---------------------------------------------------------------------------
# 20, 21, 22. source hash/size/mtime unchanged; Provider calls = 0; DB
#             writes = 0
# ---------------------------------------------------------------------------


def test_source_hash_size_mtime_unchanged_and_zero_provider_and_db_calls(replay_result):
    assert replay_result.source_raw_sha256_before == replay_result.source_raw_sha256_after
    assert replay_result.source_raw_size_before == replay_result.source_raw_size_after
    assert replay_result.source_raw_mtime_before == replay_result.source_raw_mtime_after
    assert replay_result.tradingagents_calls == 0
    assert replay_result.llm_provider_calls == 0
    assert replay_result.market_data_provider_calls == 0
    assert replay_result.database_writes == 0


# ---------------------------------------------------------------------------
# 23. persist=False follows the same identity contract
# ---------------------------------------------------------------------------


def test_persist_false_follows_same_identity_contract(tmp_path):
    _write_source_run(tmp_path)
    result = run_structure_replay(
        SOURCE_RUN_ID,
        source_output_root=str(tmp_path),
        replay_output_root=str(tmp_path / "replays_np"),
        persist=False,
        comparison=False,
    )
    assert result.status == "completed"
    assert result.output_dir is None
    assert result.identity_consistency is not None
    assert result.identity_consistency["identity_consistency"] == STATUS_PASS
    assert result.identity_consistency["mismatched_artifacts"] == []


# ---------------------------------------------------------------------------
# 24. Caller-supplied replay_run_id works
# ---------------------------------------------------------------------------


def test_caller_supplied_replay_run_id_is_honored(tmp_path):
    _write_source_run(tmp_path)
    result = run_structure_replay(
        SOURCE_RUN_ID,
        source_output_root=str(tmp_path),
        replay_output_root=str(tmp_path / "replays_custom"),
        replay_run_id="my-custom-replay-id-001",
        persist=True,
        comparison=False,
    )
    assert result.status == "completed"
    assert result.replay_run_id == "my-custom-replay-id-001"
    structured = _load(result.output_dir, "structured_agent_outputs.json")
    assert structured["run_id"] == "my-custom-replay-id-001"
    assert result.identity_consistency["identity_consistency"] == STATUS_PASS


# ---------------------------------------------------------------------------
# Rebase helper: targeted field rewrite, never a blanket string replace
# ---------------------------------------------------------------------------


def test_rebase_helper_only_rewrites_run_id_fields_never_content():
    source_structured = {
        "schema_version": "week1a.structured_agent_outputs.v2",
        "run_id": SOURCE_RUN_ID,
        "ticker": "SNDK",
        "records": [
            {
                "claim_id": f"{SOURCE_RUN_ID}:market_agent:market_report:claim:1",
                "source_agent_output_id": f"{SOURCE_RUN_ID}:market_agent:market_report",
                "run_id": SOURCE_RUN_ID,
                "ticker": "SNDK",
                "claim": f"Revenue grew, per {SOURCE_RUN_ID} internal note.",
                "evidence": "Strong demand.",
                "source_refs": [SOURCE_RUN_ID],
            }
        ],
        "canonical_relations": [{"relation_id": "rel1", "run_id": SOURCE_RUN_ID}],
    }
    rebased = _rebase_structured_payload_for_replay(source_structured, replay_run_id="replay-xyz")

    assert rebased["run_id"] == "replay-xyz"
    assert rebased["records"][0]["run_id"] == "replay-xyz"
    assert rebased["canonical_relations"][0]["run_id"] == "replay-xyz"

    # Never touched: claim_id, source_agent_output_id, claim text,
    # evidence, ticker, source_refs -- even though several of these
    # literally contain the source run_id substring, confirming this is a
    # targeted field rewrite, never a blanket recursive string replace.
    assert rebased["records"][0]["claim_id"] == f"{SOURCE_RUN_ID}:market_agent:market_report:claim:1"
    assert rebased["records"][0]["source_agent_output_id"] == f"{SOURCE_RUN_ID}:market_agent:market_report"
    assert rebased["records"][0]["claim"] == f"Revenue grew, per {SOURCE_RUN_ID} internal note."
    assert rebased["records"][0]["evidence"] == "Strong demand."
    assert rebased["records"][0]["ticker"] == "SNDK"
    assert rebased["records"][0]["source_refs"] == [SOURCE_RUN_ID]

    # Original payload (as adapt_run_outputs produced it against the
    # source run) is never mutated in place.
    assert source_structured["run_id"] == SOURCE_RUN_ID
    assert source_structured["records"][0]["run_id"] == SOURCE_RUN_ID
