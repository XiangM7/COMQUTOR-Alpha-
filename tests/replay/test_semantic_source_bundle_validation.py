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


# ---------------------------------------------------------------------------
# 2026-10-01: alpha_classifier v6/v7 Exact Replay identity compatibility.
# _SUPPORTED_CALL_IDENTITIES["alpha_classifier"] now accepts two independent
# identities (v6 and v7) instead of one, so a real prompt version bump never
# retroactively breaks Exact Replay for bundles saved under the prior
# version. These tests go through the real public entry point
# (load_exact_semantic_source_bundle), never calling _validate_call_versions
# directly.
# ---------------------------------------------------------------------------

_V6_IDENTITY = {
    "prompt_version": "week2.alpha_classifier.v6",
    "prompt_sha256": "bb2dbdf0f3fc9a43291233494c2f355275b4fe6fddc71cd63fd1377f9ba109d9",
}
_V7_IDENTITY = {
    "prompt_version": "week2.alpha_classifier.v7",
    "prompt_sha256": "ac48723f15cf347590ad2cb175f76cd438dbc4181c7b781aa0cfffaafe589b95",
}


def _set_alpha_classifier_identity(source: Path, *, prompt_version: str, prompt_sha256: str) -> None:
    """Rewrites the alpha_classifier call record's own identity fields on
    disk, then re-derives and rewrites ONLY the manifest fields that
    actually depend on calls-file content (calls_file_sha256,
    prompt_versions) using the real production derivation function
    (source_bundle._derived_manifest) -- never hand-computed -- so the
    mutated bundle is otherwise exactly as valid as the original, and any
    error raised is attributable only to the identity fields under test."""
    from comqutor_alpha.replay import source_bundle as _sb

    calls_path = source / "llm_semantic_calls.jsonl"
    records = [json.loads(line) for line in calls_path.read_text().splitlines()]
    found = False
    for record in records:
        if record["task"] == "alpha_classifier":
            record["prompt_version"] = prompt_version
            record["prompt_sha256"] = prompt_sha256
            found = True
    assert found, "fixture has no alpha_classifier call record to mutate"
    calls_path.write_text("".join(json.dumps(item) + "\n" for item in records))

    manifest_path = source / "llm_semantic_manifest.json"
    manifest = _json(manifest_path)
    derived = _sb._derived_manifest(source, manifest, tuple(records))
    manifest["calls_file_sha256"] = derived["calls_file_sha256"]
    manifest["prompt_versions"] = derived["prompt_versions"]
    _write_json(manifest_path, manifest)


def test_legal_v6_alpha_classifier_record_still_passes_exact_replay(
    eligible_live_source: Path,
) -> None:
    """A record identified as v6 (the prior real production prompt, used by
    t3live_20261001T014648Z_1fb9c9d5 and others) must keep passing Exact
    Replay exactly as before the v7 prompt edit -- the version bump must
    never retroactively break it."""
    _set_alpha_classifier_identity(eligible_live_source, **_V6_IDENTITY)

    bundle = load_exact_semantic_source_bundle(eligible_live_source)

    alpha_call = next(c for c in bundle.semantic_calls if c["task"] == "alpha_classifier")
    assert alpha_call["prompt_version"] == "week2.alpha_classifier.v6"
    assert alpha_call["prompt_sha256"] == _V6_IDENTITY["prompt_sha256"]


def test_legal_v7_alpha_classifier_record_passes_exact_replay(
    eligible_live_source: Path,
) -> None:
    """eligible_live_source already exercises the real, current production
    prompt (v7, after this round's edit) without any mutation -- this test
    makes that fact explicit and asserts it is indeed v7, not accidentally
    still v6, so this isn't silently testing the wrong version."""
    bundle = load_exact_semantic_source_bundle(eligible_live_source)

    alpha_call = next(c for c in bundle.semantic_calls if c["task"] == "alpha_classifier")
    assert alpha_call["prompt_version"] == "week2.alpha_classifier.v7"
    assert alpha_call["prompt_sha256"] == _V7_IDENTITY["prompt_sha256"]


def test_v7_version_with_v6_hash_is_rejected_not_interpreted_as_either_identity(
    eligible_live_source: Path,
) -> None:
    """A record claiming prompt_version=v7 but carrying v6's own
    prompt_sha256 (a cross-identity field combination -- e.g. a corrupted or
    hand-edited record) must match neither accepted identity and fail
    closed, exactly like an unrecognized version. This is the core
    assertion that identities are matched as whole units, never field-by-
    field across different accepted candidates."""
    _set_alpha_classifier_identity(
        eligible_live_source,
        prompt_version=_V7_IDENTITY["prompt_version"],
        prompt_sha256=_V6_IDENTITY["prompt_sha256"],
    )

    with pytest.raises(ExactReplayError) as caught:
        load_exact_semantic_source_bundle(eligible_live_source)

    assert caught.value.reason_code == EXACT_REPLAY_SEMANTIC_VERSION_MISMATCH


def test_unknown_alpha_classifier_prompt_version_is_rejected(
    eligible_live_source: Path,
) -> None:
    """A prompt_version string that is neither v6 nor v7 (nor any other
    registered identity) must fail closed -- new versions are never
    accepted merely because they look well-formed."""
    _set_alpha_classifier_identity(
        eligible_live_source,
        prompt_version="week2.alpha_classifier.v99-not-a-real-version",
        prompt_sha256=_V7_IDENTITY["prompt_sha256"],
    )

    with pytest.raises(ExactReplayError) as caught:
        load_exact_semantic_source_bundle(eligible_live_source)

    assert caught.value.reason_code == EXACT_REPLAY_SEMANTIC_VERSION_MISMATCH


def test_modified_v7_prompt_hash_is_rejected(eligible_live_source: Path) -> None:
    """prompt_version=v7 paired with a hash that matches NEITHER v6 nor v7
    (simulating a modified/corrupted prompt text) must fail closed."""
    _set_alpha_classifier_identity(
        eligible_live_source,
        prompt_version=_V7_IDENTITY["prompt_version"],
        prompt_sha256="0" * 64,
    )

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


def test_derived_manifest_original_tasks_constant_matches_manifest_module() -> None:
    """source_bundle.py deliberately duplicates (never imports -- see
    tests/llm_runtime/test_no_production_importers.py's closed allowlist)
    llm_runtime/manifest.py's MANIFEST_ORIGINAL_TASKS, so _derived_manifest
    can reproduce the live manifest writer's exact "tasks" dict shape (the
    original three tasks always present, any later-added task only when at
    least one such record is actually present). This test is the guard
    against the two copies silently drifting apart -- a production test
    file may import from llm_runtime even though production code may not."""
    from comqutor_alpha.llm_runtime.manifest import MANIFEST_ORIGINAL_TASKS
    from comqutor_alpha.replay.source_bundle import _MANIFEST_ORIGINAL_TASKS

    assert _MANIFEST_ORIGINAL_TASKS == MANIFEST_ORIGINAL_TASKS
