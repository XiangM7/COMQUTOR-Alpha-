"""T2 verification, 2026-09-29 follow-up, item 3(c): prove that Architecture
Replay's own UNAVAILABLE Alpha semantic state is never displayed through the
real production summary path as a formal pass or as "the market has no
conflict".

The real mechanism (comqutor_alpha.api.routes_research._load_week4_response_
fields / _build_research_summary) reads dominant_alphas/main_conflict/
conflict_status EXCLUSIVELY from the database via graph_repository.get_graph
(its own docstring: "never read from a local conflicts.json (none is ever
written)"). comqutor_alpha.replay.pipeline.run_structure_replay's own module
docstring independently confirms Architecture Replay NEVER persists to the
database at all -- every artifact goes to a brand-new outputs/replays/<id>/
directory only. These two facts combined mean a replay_run_id can never
produce a database row for repository.get_graph to find, so the ONLY
possible summary this real production path can produce for one is "not
ready" -- confirmed directly below with a REAL repository (a real SQLite-
backed GraphPersistenceRepository, never populated with the replay's own
row, exactly matching what actually happens in production) and a REAL
Architecture Replay of a real historical run.

Zero Provider calls, zero network, zero writes to any historical run
directory.
"""

from __future__ import annotations

import json

import pytest

from comqutor_alpha.api.routes_research import _build_research_summary, _load_week4_response_fields
from comqutor_alpha.regression.acceptance_engine import (
    FORMAL_STATUS_ALPHA_SEMANTIC_UNAVAILABLE,
    run_formal_acceptance,
)
from comqutor_alpha.replay.pipeline import run_structure_replay
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository

SOURCE_RUN_ID = "e434f80b-e4d0-4b09-9471-d84532659de5"  # the canonical NVDA run, unchanged, read-only


def _repo():
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    return GraphPersistenceRepository(engine)


def test_a_real_architecture_replay_run_id_is_reported_not_ready_never_no_conflict_never_pass(tmp_path):
    repo = _repo()
    result = run_structure_replay(
        SOURCE_RUN_ID,
        source_output_root="outputs/runs",
        replay_output_root=str(tmp_path),
        persist=True,
        comparison=False,
    )
    assert result.status == "completed"
    replay_run_id = result.replay_run_id

    # The real production repository genuinely has no row for this replay
    # run_id -- Architecture Replay never calls persist_run/persist_week4_
    # results at all (see run_structure_replay's own module docstring).
    assert repo.get_graph(replay_run_id) is None

    dominant_alphas, main_conflict, conflict_status, evidence_gate_applied, has_verified_evidence = (
        _load_week4_response_fields(replay_run_id, str(tmp_path), repo)
    )
    assert conflict_status == "not_ready"
    assert dominant_alphas == []
    assert main_conflict is None

    summary = _build_research_summary(
        conflict_status, main_conflict, dominant_alphas, evidence_gate_applied, has_verified_evidence
    )
    # The exact, real message a genuinely UNAVAILABLE Architecture Replay
    # run produces through this real production path -- never "no conflict
    # was identified" (which would imply a real, evaluated absence of
    # conflict) and never anything resembling a pass/admission.
    assert summary == "Conflict analysis is not ready for this research run."
    assert "no conflict" not in summary.lower()
    assert "pass" not in summary.lower()


def test_run_formal_acceptance_never_defaults_to_pass_for_an_all_unavailable_replay(tmp_path):
    """The SEPARATE, genuine gap this round found and closed: without
    alpha_matches_payload wired in, a ticker with no required/allowed
    conflicts declared (or none reaching the evidence-present bar) would
    otherwise fall through every rule family's own empty-result default
    straight to formal_status="pass" -- even when every one of its claims
    is genuinely match_status=="unavailable" (Architecture Replay's own
    real, deterministic signal, confirmed here from a REAL replay of a real
    historical run, never fabricated)."""
    result = run_structure_replay(
        SOURCE_RUN_ID,
        source_output_root="outputs/runs",
        replay_output_root=str(tmp_path),
        persist=True,
        comparison=False,
    )
    assert result.status == "completed"
    replay_dir = tmp_path / result.replay_run_id
    alpha_matches_payload = json.loads((replay_dir / "alpha_matches.json").read_text(encoding="utf-8"))
    assert alpha_matches_payload["matches"], "expected the real replay to still carry real claims"
    assert all(m.get("match_status") == "unavailable" for m in alpha_matches_payload["matches"])

    acceptance = run_formal_acceptance(
        ticker="NVDA",
        ticker_v2_label={},  # no required/allowed conflicts declared -- the exact condition that used to fall through to "pass"
        label_block_v1={},
        evaluate_ticker_result={
            "run_selection_status": "selected",
            "offline_reprocess_status": "completed",
            "artifact_completeness": "pass",
            "admitted_conflicts": [],
        },
        conflict_payload={"arbitration": {"candidate_evaluations": []}},
        graph_payload=json.loads((replay_dir / "structure_graph.json").read_text(encoding="utf-8")),
        alpha_matches_payload=alpha_matches_payload,
    )
    assert acceptance["formal_status"] == FORMAL_STATUS_ALPHA_SEMANTIC_UNAVAILABLE
    assert acceptance["formal_status"] != "pass"
    assert acceptance["rule_family_results"] == {}


def test_omitting_alpha_matches_payload_entirely_is_now_a_hard_error_never_a_silent_pass():
    """2026-09-30 closing fix: the PRIOR version of this parameter was
    optional with a None default, so a real caller (the six-ticker script)
    could simply never pass it and silently get the old, pre-gate
    behavior back -- exactly the bypass John's own follow-up flagged.
    alpha_matches_payload is now a REQUIRED keyword argument with no
    default: a caller can no longer omit it at all (Python itself refuses
    the call), and a caller that explicitly passes None hits the
    ALPHA_SEMANTIC_UNAVAILABLE gate instead of a silent pass -- see
    test_missing_alpha_matches_payload_is_never_a_pass in
    tests/test_acceptance_engine.py for that explicit-None case."""
    with pytest.raises(TypeError):
        run_formal_acceptance(
            ticker="NVDA",
            ticker_v2_label={},
            label_block_v1={},
            evaluate_ticker_result={
                "run_selection_status": "selected",
                "offline_reprocess_status": "completed",
                "artifact_completeness": "pass",
                "admitted_conflicts": [],
            },
            conflict_payload={"arbitration": {"candidate_evaluations": []}},
            graph_payload={},
        )
