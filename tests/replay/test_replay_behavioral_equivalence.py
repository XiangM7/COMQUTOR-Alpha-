from __future__ import annotations

import hashlib
import json
from pathlib import Path

from comqutor_alpha.replay.exact_semantic import run_exact_semantic_replay
from comqutor_alpha.replay.source_bundle import SEMANTIC_ARTIFACT_COPY_FILENAMES


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_saved_semantics_and_all_deterministic_outputs_are_equivalent(
    tmp_path: Path,
    eligible_live_source: Path,
) -> None:
    result = run_exact_semantic_replay(
        eligible_live_source,
        tmp_path / "replays",
        replay_id="behavioral-equivalence",
    )
    replay_dir = Path(result.output_dir)

    assert result.comparison["semantic_inputs_reused_exactly"] is True
    assert result.comparison["deterministic_downstream_equivalent"] is True
    assert result.comparison["deterministic_engine_delta"] is False
    assert result.comparison["final_status"] == "PASS"
    for component in ("graph", "activation", "exposure", "conflict"):
        item = result.comparison["comparisons"][component]
        assert item["semantically_equivalent"] is True
        assert item["source_normalized_sha256"] == item["replay_normalized_sha256"]

    assert {
        name: _sha(eligible_live_source / name)
        for name in SEMANTIC_ARTIFACT_COPY_FILENAMES
    } == {
        name: _sha(replay_dir / name)
        for name in SEMANTIC_ARTIFACT_COPY_FILENAMES
    }
    metadata = json.loads((replay_dir / "metadata.json").read_text(encoding="utf-8"))
    source_structured = json.loads(
        (eligible_live_source / "structured_agent_outputs.json").read_text(encoding="utf-8")
    )
    replay_structured = json.loads(
        (replay_dir / "structured_agent_outputs.json").read_text(encoding="utf-8")
    )
    replay_graph = json.loads(
        (replay_dir / "structure_graph.json").read_text(encoding="utf-8")
    )
    assert metadata["source_run_id"] == source_structured["run_id"]
    assert source_structured == replay_structured
    assert replay_graph["run_id"] == metadata["replay_id"]
    assert metadata["source_run_id"] != metadata["replay_id"]
