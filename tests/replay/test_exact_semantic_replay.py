from __future__ import annotations

import json
from pathlib import Path

from comqutor_alpha.replay.exact_semantic import run_exact_semantic_replay
from comqutor_alpha.replay.source_bundle import SEMANTIC_ARTIFACT_COPY_FILENAMES
from tests.replay.conftest import file_tree_snapshot


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
    assert binding["uniquely_bound_records"] == binding["total_semantic_records"] == 3
    assert comparison["semantic_inputs_reused_exactly"] is True
    assert comparison["deterministic_downstream_equivalent"] is True
    assert snapshot["semantic_artifact_copies_byte_identical"] is True


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
