from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from comqutor_alpha.replay.exact_semantic import run_exact_semantic_replay
from comqutor_alpha.replay.source_bundle import (
    EXACT_REPLAY_SEMANTIC_ARTIFACT_MISSING,
    EXACT_REPLAY_SEMANTIC_CALL_CORRUPTED,
    EXACT_REPLAY_SEMANTIC_MANIFEST_INVALID,
    EXACT_REPLAY_SEMANTIC_NOT_READY,
    EXACT_REPLAY_SEMANTIC_RUN_ID_MISMATCH,
    EXACT_REPLAY_SEMANTIC_VERSION_MISMATCH,
    EXACT_REPLAY_SOURCE_ARTIFACT_INVALID,
    EXACT_REPLAY_TICKER_IDENTITY_MISMATCH,
    ExactReplayError,
    load_exact_semantic_source_bundle,
)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


@pytest.mark.parametrize(
    "filename",
    ["llm_semantic_calls.jsonl", "llm_semantic_manifest.json"],
)
def test_missing_semantic_sidecar_fails_closed(
    tmp_path: Path,
    eligible_live_source: Path,
    filename: str,
) -> None:
    (eligible_live_source / filename).unlink()

    with pytest.raises(ExactReplayError) as caught:
        run_exact_semantic_replay(eligible_live_source, tmp_path / "replays")

    assert caught.value.reason_code == EXACT_REPLAY_SEMANTIC_ARTIFACT_MISSING
    assert not (tmp_path / "replays").exists()


def test_manifest_not_ready_stops_before_downstream(
    tmp_path: Path,
    eligible_live_source: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = eligible_live_source / "llm_semantic_manifest.json"
    manifest = _json(path)
    manifest["exact_replay_ready"] = False
    _write_json(path, manifest)
    monkeypatch.setattr(
        "comqutor_alpha.replay.exact_semantic._run_deterministic_downstream",
        lambda *args, **kwargs: pytest.fail("downstream must not run"),
    )

    with pytest.raises(ExactReplayError) as caught:
        run_exact_semantic_replay(eligible_live_source, tmp_path / "replays")

    assert caught.value.reason_code == EXACT_REPLAY_SEMANTIC_NOT_READY
    assert not (tmp_path / "replays").exists()


def test_manifest_invalid_json_has_stable_manifest_error(
    eligible_live_source: Path,
) -> None:
    (eligible_live_source / "llm_semantic_manifest.json").write_text("not-json\n")

    with pytest.raises(ExactReplayError) as caught:
        load_exact_semantic_source_bundle(eligible_live_source)

    assert caught.value.reason_code == EXACT_REPLAY_SEMANTIC_MANIFEST_INVALID


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("calls_file_sha256", "0" * 64, EXACT_REPLAY_SEMANTIC_CALL_CORRUPTED),
        ("record_count", 99, EXACT_REPLAY_SEMANTIC_MANIFEST_INVALID),
        ("tasks", {"structured_adapter": 3}, EXACT_REPLAY_SEMANTIC_MANIFEST_INVALID),
        ("schema_version", "unsupported", EXACT_REPLAY_SEMANTIC_VERSION_MISMATCH),
        ("accepted_count", 0, EXACT_REPLAY_SEMANTIC_MANIFEST_INVALID),
    ],
)
def test_manifest_corruption_fails_closed(
    eligible_live_source: Path,
    field: str,
    value,
    expected: str,
) -> None:
    path = eligible_live_source / "llm_semantic_manifest.json"
    manifest = _json(path)
    manifest[field] = value
    _write_json(path, manifest)

    with pytest.raises(ExactReplayError) as caught:
        load_exact_semantic_source_bundle(eligible_live_source)

    assert caught.value.reason_code == expected


@pytest.mark.parametrize(
    "mutation",
    ["invalid_json", "middle_corruption", "tail_corruption", "duplicate_call", "sequence", "hash"],
)
def test_semantic_call_corruption_fails_closed(
    eligible_live_source: Path,
    mutation: str,
) -> None:
    path = eligible_live_source / "llm_semantic_calls.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    if mutation == "invalid_json":
        path.write_text("not-json\n", encoding="utf-8")
    elif mutation == "middle_corruption":
        path.write_text(f"{lines[0]}\nnot-json\n{lines[2]}\n", encoding="utf-8")
    elif mutation == "tail_corruption":
        path.write_text("\n".join(lines), encoding="utf-8")
    elif mutation == "duplicate_call":
        records[1]["call_id"] = records[0]["call_id"]
        path.write_text("".join(json.dumps(item) + "\n" for item in records))
    elif mutation == "sequence":
        records[1]["call_sequence"] = 4
        path.write_text("".join(json.dumps(item) + "\n" for item in records))
    else:
        records[0]["input_sha256"] = "0" * 64
        path.write_text("".join(json.dumps(item) + "\n" for item in records))

    with pytest.raises(ExactReplayError) as caught:
        load_exact_semantic_source_bundle(eligible_live_source)

    assert caught.value.reason_code == EXACT_REPLAY_SEMANTIC_CALL_CORRUPTED


def test_semantic_call_schema_version_mismatch_has_stable_version_error(
    eligible_live_source: Path,
) -> None:
    path = eligible_live_source / "llm_semantic_calls.jsonl"
    records = [json.loads(line) for line in path.read_text().splitlines()]
    records[0]["schema_version"] = "unsupported"
    path.write_text("".join(json.dumps(item) + "\n" for item in records))

    with pytest.raises(ExactReplayError) as caught:
        load_exact_semantic_source_bundle(eligible_live_source)

    assert caught.value.reason_code == EXACT_REPLAY_SEMANTIC_VERSION_MISMATCH


def test_wrong_run_and_ticker_identities_fail_closed(
    eligible_live_source: Path,
) -> None:
    metadata_path = eligible_live_source / "metadata.json"
    metadata = _json(metadata_path)
    metadata["run_id"] = "other-run"
    _write_json(metadata_path, metadata)
    with pytest.raises(ExactReplayError) as wrong_run:
        load_exact_semantic_source_bundle(eligible_live_source)
    assert wrong_run.value.reason_code == EXACT_REPLAY_SEMANTIC_RUN_ID_MISMATCH


def test_wrong_ticker_identity_fails_closed(eligible_live_source: Path) -> None:
    path = eligible_live_source / "structured_agent_outputs.json"
    payload = _json(path)
    payload["ticker"] = "AMD"
    _write_json(path, payload)
    with pytest.raises(ExactReplayError) as caught:
        load_exact_semantic_source_bundle(eligible_live_source)
    assert caught.value.reason_code == EXACT_REPLAY_TICKER_IDENTITY_MISMATCH


def test_path_traversal_and_symlink_escape_are_rejected(
    tmp_path: Path,
    eligible_live_source: Path,
) -> None:
    traversal = eligible_live_source.parent / "unused" / ".." / eligible_live_source.name
    with pytest.raises(ExactReplayError) as traversed:
        load_exact_semantic_source_bundle(traversal)
    assert traversed.value.reason_code == EXACT_REPLAY_SOURCE_ARTIFACT_INVALID

    calls = eligible_live_source / "llm_semantic_calls.jsonl"
    outside = tmp_path / "outside.jsonl"
    outside.write_bytes(calls.read_bytes())
    calls.unlink()
    os.symlink(outside, calls)
    with pytest.raises(ExactReplayError) as escaped:
        load_exact_semantic_source_bundle(eligible_live_source)
    assert escaped.value.reason_code == EXACT_REPLAY_SOURCE_ARTIFACT_INVALID
