from __future__ import annotations

import json
from pathlib import Path

from comqutor_alpha.replay.exact_semantic import run_exact_semantic_replay
from comqutor_alpha.replay.source_bundle import SEMANTIC_ARTIFACT_COPY_FILENAMES
from tests.replay.conftest import file_tree_snapshot


# Pure-LLM Alpha Production Boundary Hardening test L: Exact Semantic
# Replay with a recorded MATCHED (decision=select) Alpha decision verifies
# the replayed alpha_matches.json carries that same matched Alpha, never a
# re-derived or fabricated one -- see the byte-identical copy assertions
# and binding["final_status"]=="PASS" below.
def test_eligible_exact_replay_is_atomic_byte_identical_and_source_read_only(
    tmp_path: Path,
    eligible_live_source: Path,
) -> None:
    before = file_tree_snapshot(eligible_live_source)
    output_root = tmp_path / "exact-replays"

    result = run_exact_semantic_replay(
        eligible_live_source,
        output_root,
        replay_id="exact-replay-fixture",
    )

    replay_dir = output_root / "exact-replay-fixture"
    assert result.status == "completed"
    assert result.replay_mode == "EXACT_SEMANTIC_REPLAY"
    assert result.semantic_source == "saved_validated_artifacts"
    assert result.provider_calls == 0
    assert result.tradingagents_calls == 0
    assert result.market_data_calls == 0
    assert result.database_writes == 0
    assert replay_dir.is_dir()
    assert not list(output_root.glob(".exact-semantic-replay-staging-*"))
    assert file_tree_snapshot(eligible_live_source) == before

    for filename in SEMANTIC_ARTIFACT_COPY_FILENAMES:
        assert (replay_dir / filename).read_bytes() == (
            eligible_live_source / filename
        ).read_bytes()

    metadata = json.loads((replay_dir / "metadata.json").read_text())
    binding = json.loads((replay_dir / "semantic_binding_audit.json").read_text())
    comparison = json.loads((replay_dir / "exact_replay_comparison.json").read_text())
    snapshot = json.loads(
        (replay_dir / "exact_semantic_source_snapshot.json").read_text()
    )
    assert metadata["semantic_artifact_owner_run_id"] == eligible_live_source.name
    assert metadata["downstream_output_owner_run_id"] == "exact-replay-fixture"
    assert binding["final_status"] == "PASS"
    # 4, not the pre-Alpha-Authority-Migration 3: this fixture's
    # alpha_classifier mock genuinely selects an Alpha (Pure-LLM semantic
    # authority: matched_alpha is a real, non-null LLM decision), which
    # legitimately triggers a 4th call -- B1's own evidence_stance_classifier
    # upgrade -- that now binds successfully. See
    # tests/replay/conftest.py::eligible_live_source's own comment.
    assert binding["uniquely_bound_records"] == binding["total_semantic_records"] == 4
    assert comparison["semantic_inputs_reused_exactly"] is True
    assert comparison["deterministic_downstream_equivalent"] is True
    assert snapshot["semantic_artifact_copies_byte_identical"] is True


# Pure-LLM Alpha Production Boundary Hardening test M: Exact Semantic
# Replay with a recorded NONE (decision=none) Alpha decision verifies the
# replayed alpha_matches.json carries that same genuine semantic NONE
# (matched_alpha=null, match_status="no_match") -- never fabricating a
# matched Alpha, and never confusing it with UNAVAILABLE (a NONE decision
# has a real, accepted semantic call record to bind to; an UNAVAILABLE
# claim has none, which is exactly what Exact Replay's own upstream
# readiness gate -- "every persisted call must be accepted" -- prevents
# from ever reaching this far in the first place).
def test_exact_replay_with_recorded_none_decision_preserves_semantic_none(
    tmp_path: Path,
    eligible_live_source_alpha_none: Path,
) -> None:
    source = eligible_live_source_alpha_none
    output_root = tmp_path / "exact-replays-none"

    result = run_exact_semantic_replay(
        source,
        output_root,
        replay_id="exact-replay-alpha-none",
    )

    replay_dir = output_root / "exact-replay-alpha-none"
    assert result.status == "completed"
    assert result.provider_calls == 0

    binding = json.loads((replay_dir / "semantic_binding_audit.json").read_text())
    assert binding["final_status"] == "PASS"
    # 3, not 4: no matched_alpha means B1's stance upgrade never fired for
    # this claim (see eligible_live_source_alpha_none's own comment).
    assert binding["uniquely_bound_records"] == binding["total_semantic_records"] == 3

    replayed_matches = json.loads((replay_dir / "alpha_matches.json").read_text())
    matches = replayed_matches["matches"]
    assert matches
    for match in matches:
        assert match["matched_alpha"] is None
        assert match["match_status"] == "no_match"
        assert match["alpha_match_method"] == "llm"
        assert match["alpha_match_fallback_reason"] is None
        assert match["classifier"]["status"] == "llm_none"

    # Byte-identical to the source's own already-persisted artifact --
    # replayed, never re-derived.
    assert (replay_dir / "alpha_matches.json").read_bytes() == (
        source / "alpha_matches.json"
    ).read_bytes()


def test_exact_replay_no_persist_leaves_no_bundle(
    tmp_path: Path,
    eligible_live_source: Path,
) -> None:
    output_root = tmp_path / "no-persist"
    result = run_exact_semantic_replay(
        eligible_live_source,
        output_root,
        replay_id="exact-no-persist",
        persist=False,
    )

    assert result.status == "completed"
    assert result.output_dir is None
    assert list(output_root.iterdir()) == []
