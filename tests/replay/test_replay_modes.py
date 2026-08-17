from __future__ import annotations

import json
from pathlib import Path

import pytest

from comqutor_alpha.replay.cli import main as replay_cli_main
from comqutor_alpha.replay.modes import ReplayMode, require_replay_mode
from comqutor_alpha.replay.pipeline import run_structure_replay


def _write_raw_source(root: Path) -> str:
    run_id = "raw-rebuild-source"
    run_dir = root / run_id
    run_dir.mkdir()
    raw = {
        "schema_version": "week1.raw_agent_outputs.v1",
        "run_id": run_id,
        "ticker": "MSFT",
        "agent_outputs": [
            {
                "agent_output_id": f"{run_id}:news_agent:report",
                "run_id": run_id,
                "ticker": "MSFT",
                "agent": "news_agent",
                "source_field": "news_report",
                "raw_output": "AI demand is driving cloud revenue growth.",
            }
        ],
    }
    metadata = {
        "run_id": run_id,
        "ticker": "MSFT",
        "analysis_date": "2026-07-01",
        "created_at": "2026-07-01T00:00:00Z",
    }
    (run_dir / "raw_agent_outputs.json").write_text(json.dumps(raw))
    (run_dir / "metadata.json").write_text(json.dumps(metadata))
    return run_id


def test_only_two_strict_versioned_replay_modes_exist() -> None:
    assert {item.value for item in ReplayMode} == {
        "EXACT_SEMANTIC_REPLAY",
        "RAW_REBUILD_DIAGNOSTIC",
    }
    assert require_replay_mode("EXACT_SEMANTIC_REPLAY") is ReplayMode.EXACT_SEMANTIC_REPLAY
    assert require_replay_mode("RAW_REBUILD_DIAGNOSTIC") is ReplayMode.RAW_REBUILD_DIAGNOSTIC
    for ambiguous in ("exact", "normal", "default", "legacy", "structure-only"):
        with pytest.raises(ValueError):
            require_replay_mode(ambiguous)


def test_existing_raw_rebuild_entrypoint_remains_compatible(tmp_path: Path) -> None:
    run_id = _write_raw_source(tmp_path)

    result = run_structure_replay(
        run_id,
        source_output_root=str(tmp_path),
        replay_output_root=str(tmp_path / "raw-replays"),
        replay_run_id="raw-compatible",
    )

    replay_dir = Path(result.output_dir)
    assert result.status == "completed"
    assert result.replay_mode == "RAW_REBUILD_DIAGNOSTIC"
    assert result.semantic_source == "raw_rebuild"
    assert result.provider_zero is True
    assert (replay_dir / "structured_agent_outputs.json").is_file()
    assert (replay_dir / "conflict_results.json").is_file()
    metadata = json.loads((replay_dir / "metadata.json").read_text())
    assert metadata["replay_mode"] == "RAW_REBUILD_DIAGNOSTIC"
    assert metadata["semantic_source"] == "raw_rebuild"
    assert metadata["provider_zero"] is True


def test_cli_explicit_exact_mode_dispatches_without_raw_fallback(
    tmp_path: Path,
    eligible_live_source: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = replay_cli_main(
        [
            "--source-run-id",
            eligible_live_source.name,
            "--source-output-root",
            str(eligible_live_source.parent),
            "--output-root",
            str(tmp_path / "cli-replays"),
            "--replay-run-id",
            "cli-exact",
            "--mode",
            "EXACT_SEMANTIC_REPLAY",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["replay_mode"] == "EXACT_SEMANTIC_REPLAY"
    assert payload["semantic_source"] == "saved_validated_artifacts"
    assert payload["provider_calls"] == 0
