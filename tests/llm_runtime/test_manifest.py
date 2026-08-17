from __future__ import annotations

import json
from pathlib import Path

from comqutor_alpha.llm_runtime.canonical_json import sha256_bytes
from comqutor_alpha.llm_runtime.manifest import (
    SEMANTIC_MANIFEST_FILENAME,
    build_semantic_manifest,
    verify_semantic_manifest,
    write_semantic_manifest_atomic,
)
from comqutor_alpha.llm_runtime.recorder import SemanticCallRecorder
from tests.llm_runtime.fakes import make_record

CREATED_AT = "2026-01-01T00:00:01+00:00"
FINALIZED_AT = "2026-01-01T00:00:02+00:00"


def record_artifact(tmp_path: Path) -> SemanticCallRecorder:
    recorder = SemanticCallRecorder(run_id="run-test", output_directory=tmp_path, mode="test")
    recorder.append(make_record())
    recorder.append(
        make_record(
            call_id="call-1",
            call_sequence=1,
            task="alpha_classifier",
            provider_status="timeout",
            raw_output_text=None,
            token_usage={"input_tokens": None, "output_tokens": None, "total_tokens": None},
            fallback_used=True,
            fallback_reason="safe deterministic fallback",
            error_code="PROVIDER_TIMEOUT",
            error_message="Provider timed out",
        )
    )
    cache_hit = make_record(
        call_id="call-2",
        call_sequence=2,
        task="structure_extractor",
        provider_status="not_called",
        raw_output_text=None,
        token_usage={"input_tokens": None, "output_tokens": None, "total_tokens": None},
        prompt_version="prompt.v2",
        model="fake-model-v2",
    )
    cache_hit["cache"] = {"cache_key": cache_hit["cache"]["cache_key"], "hit": True}
    recorder.append(cache_hit)
    return recorder


def test_manifest_counts_hash_and_fallback_closes_exact_readiness(tmp_path: Path) -> None:
    recorder = record_artifact(tmp_path)
    manifest = build_semantic_manifest(
        run_id="run-test",
        calls_path=recorder.calls_path,
        complete=True,
        created_at=CREATED_AT,
        finalized_at=FINALIZED_AT,
    )

    assert manifest["record_count"] == 3
    assert manifest["tasks"] == {
        "alpha_classifier": 1,
        "structure_extractor": 1,
        "structured_adapter": 1,
    }
    assert manifest["accepted_count"] == 3
    assert manifest["rejected_count"] == 0
    assert manifest["fallback_count"] == 1
    assert manifest["cache_hit_count"] == 1
    assert manifest["provider_call_count"] == 2
    assert manifest["prompt_versions"] == ["prompt.v1", "prompt.v2"]
    assert manifest["models"] == ["fake-model", "fake-model-v2"]
    assert manifest["calls_file_sha256"] == sha256_bytes(recorder.calls_path.read_bytes())
    assert manifest["exact_replay_ready"] is False


def test_complete_all_accepted_manifest_is_exact_ready(tmp_path: Path) -> None:
    recorder = SemanticCallRecorder(run_id="run-test", output_directory=tmp_path, mode="test")
    recorder.append(make_record())

    manifest = build_semantic_manifest(
        run_id="run-test",
        calls_path=recorder.calls_path,
        complete=True,
        created_at=CREATED_AT,
        finalized_at=FINALIZED_AT,
    )

    assert manifest["exact_replay_ready"] is True


def test_complete_zero_record_manifest_is_not_exact_ready(tmp_path: Path) -> None:
    recorder = SemanticCallRecorder(run_id="run-test", output_directory=tmp_path, mode="test")
    recorder.ensure_artifact()

    manifest = build_semantic_manifest(
        run_id="run-test",
        calls_path=recorder.calls_path,
        complete=True,
        created_at=CREATED_AT,
        finalized_at=FINALIZED_AT,
    )

    assert manifest["record_count"] == 0
    assert manifest["provider_call_count"] == 0
    assert manifest["exact_replay_ready"] is False


def test_atomic_write_round_trip_leaves_no_temporary_file(tmp_path: Path) -> None:
    recorder = record_artifact(tmp_path)
    manifest = build_semantic_manifest(
        run_id="run-test",
        calls_path=recorder.calls_path,
        complete=True,
        created_at=CREATED_AT,
        finalized_at=FINALIZED_AT,
    )
    path = write_semantic_manifest_atomic(manifest=manifest, output_directory=tmp_path, fsync=True)

    assert path == tmp_path / SEMANTIC_MANIFEST_FILENAME
    assert verify_semantic_manifest(path).valid
    assert list(tmp_path.glob(f".{SEMANTIC_MANIFEST_FILENAME}.*.tmp")) == []


def test_calls_file_mutation_is_detected(tmp_path: Path) -> None:
    recorder = record_artifact(tmp_path)
    manifest = build_semantic_manifest(
        run_id="run-test",
        calls_path=recorder.calls_path,
        complete=True,
        created_at=CREATED_AT,
        finalized_at=FINALIZED_AT,
    )
    path = write_semantic_manifest_atomic(manifest=manifest, output_directory=tmp_path)
    recorder.calls_path.write_bytes(recorder.calls_path.read_bytes() + b"\n")

    result = verify_semantic_manifest(path)
    assert not result.valid
    assert "SEMANTIC_MANIFEST_CALLS_MIDDLE_CORRUPTED" in result.reason_codes


def test_manifest_count_or_hash_tampering_is_detected(tmp_path: Path) -> None:
    recorder = record_artifact(tmp_path)
    manifest = build_semantic_manifest(
        run_id="run-test",
        calls_path=recorder.calls_path,
        complete=True,
        created_at=CREATED_AT,
        finalized_at=FINALIZED_AT,
    )
    path = write_semantic_manifest_atomic(manifest=manifest, output_directory=tmp_path)
    stored = json.loads(path.read_text())
    stored["record_count"] = 99
    path.write_text(json.dumps(stored), encoding="utf-8")
    assert "SEMANTIC_MANIFEST_DERIVED_FIELD_MISMATCH" in verify_semantic_manifest(path).reason_codes


def test_incomplete_manifest_cannot_be_exact_replay_ready(tmp_path: Path) -> None:
    recorder = record_artifact(tmp_path)
    manifest = build_semantic_manifest(
        run_id="run-test",
        calls_path=recorder.calls_path,
        complete=False,
        created_at=CREATED_AT,
    )
    assert manifest["complete"] is False
    assert manifest["exact_replay_ready"] is False


def test_rejected_record_makes_complete_manifest_not_replay_ready(tmp_path: Path) -> None:
    recorder = SemanticCallRecorder(run_id="run-test", output_directory=tmp_path, mode="test")
    recorder.append(
        make_record(
            provider_status="provider_error",
            validation_status="rejected",
            validated_output=None,
            raw_output_text=None,
            token_usage={"input_tokens": None, "output_tokens": None, "total_tokens": None},
            error_code="PROVIDER_ERROR",
            error_message="Provider failed",
        )
    )
    manifest = build_semantic_manifest(
        run_id="run-test",
        calls_path=recorder.calls_path,
        complete=True,
        created_at=CREATED_AT,
        finalized_at=FINALIZED_AT,
    )
    assert manifest["rejected_count"] == 1
    assert manifest["exact_replay_ready"] is False
