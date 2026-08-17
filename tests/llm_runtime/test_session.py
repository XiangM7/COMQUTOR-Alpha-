from __future__ import annotations

import json
from pathlib import Path

import pytest

from comqutor_alpha.llm_runtime.canonical_json import sha256_canonical_json, sha256_text
from comqutor_alpha.llm_runtime.manifest import verify_semantic_manifest
from comqutor_alpha.llm_runtime.recorder import SemanticCallRecorder
from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
from tests.llm_runtime.fakes import InMemoryFakeCache


def _start(session: SemanticRuntimeSession, payload=None):
    return session.start_call(
        task="alpha_classifier",
        prompt_version="week2.alpha_classifier.v1",
        prompt_sha256=sha256_text("fixed prompt"),
        input_schema_version="week2.alpha_classifier.input.v1",
        output_schema_version="week2.alpha_classifier.output.v1",
        taxonomy_version="alpha_taxonomy_v1",
        input_payload=payload or {"allowed_alpha_ids": ["A101"]},
    )


def _session(tmp_path: Path, **kwargs) -> SemanticRuntimeSession:
    return SemanticRuntimeSession(
        run_id=kwargs.pop("run_id", "run-session"),
        output_directory=tmp_path,
        execution_mode="test",
        provider="fake-provider",
        model="fake-model",
        **kwargs,
    )


def test_session_persists_one_accepted_record_and_cache_entry(tmp_path: Path) -> None:
    cache = InMemoryFakeCache()
    session = _session(tmp_path, cache=cache)
    started = _start(session)
    accepted = {"decision": "select", "selected_alpha_id": "A101"}

    assert session.finalize_call(
        started.trace_handle,
        provider_status="success",
        retry_count=1,
        validation_status="accepted",
        accepted_candidate=accepted,
        fallback_used=False,
        fallback_reason=None,
        error_code=None,
    )
    manifest_path = session.finalize_manifest(complete=True)

    records = session.recorder.read_all()
    assert len(records) == 1
    assert records[0]["call_sequence"] == 0
    assert records[0]["validated_output"] == accepted
    assert records[0]["validated_output_sha256"] == sha256_canonical_json(accepted)
    assert records[0]["raw_output_text"] is None
    assert records[0]["raw_output_sha256"] is None
    assert list(cache.values) == [started.trace_handle.cache_key]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["provider_call_count"] == 2
    assert manifest["exact_replay_ready"] is True
    assert verify_semantic_manifest(manifest_path).valid


def test_cross_run_cache_hit_reuses_identity_but_requires_accepted_finalization(
    tmp_path: Path,
) -> None:
    cache = InMemoryFakeCache()
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first = _session(first_dir, cache=cache, run_id="run-first")
    first_call = _start(first)
    candidate = {"decision": "defer", "selected_alpha_id": None}
    first.finalize_call(
        first_call.trace_handle,
        provider_status="success",
        retry_count=0,
        validation_status="accepted",
        accepted_candidate=candidate,
        fallback_used=False,
        fallback_reason=None,
        error_code=None,
    )

    second = _session(second_dir, cache=cache, run_id="run-second")
    second_call = _start(second)

    assert first_call.trace_handle.cache_key == second_call.trace_handle.cache_key
    assert first_call.trace_handle.input_sha256 == second_call.trace_handle.input_sha256
    assert second_call.cached_candidate == candidate
    assert second_call.trace_handle.cache_hit is True
    second.finalize_call(
        second_call.trace_handle,
        provider_status="not_called",
        retry_count=0,
        validation_status="accepted",
        accepted_candidate=candidate,
        fallback_used=False,
        fallback_reason=None,
        error_code=None,
    )
    second.finalize_manifest(complete=True)
    assert second.recorder.read_all()[0]["cache"]["hit"] is True


def test_rejected_fallback_is_recorded_but_never_cached(tmp_path: Path) -> None:
    cache = InMemoryFakeCache()
    session = _session(tmp_path, cache=cache)
    started = _start(session)
    session.finalize_call(
        started.trace_handle,
        provider_status="success",
        retry_count=0,
        validation_status="rejected",
        accepted_candidate=None,
        fallback_used=True,
        fallback_reason="WEEK2_LLM_ALPHA_CLASSIFIER_FALLBACK",
        error_code=None,
    )
    manifest_path = session.finalize_manifest(complete=True)

    record = session.recorder.read_all()[0]
    assert record["validation_status"] == "rejected"
    assert record["fallback_used"] is True
    assert cache.values == {}
    assert json.loads(manifest_path.read_text())["exact_replay_ready"] is False


class _AppendFailingRecorder(SemanticCallRecorder):
    def append(self, record) -> None:
        del record
        raise OSError("synthetic disk error")


class _WriteFailingCache(InMemoryFakeCache):
    def put(self, cache_key, entry, ttl_seconds=None) -> None:
        del cache_key, entry, ttl_seconds
        raise OSError("synthetic cache error")


def test_recorder_append_failure_is_fail_soft_and_manifest_is_incomplete(
    tmp_path: Path,
) -> None:
    recorder = _AppendFailingRecorder(
        run_id="run-session",
        output_directory=tmp_path,
        mode="test",
    )
    session = _session(tmp_path, recorder=recorder)
    started = _start(session)

    assert not session.finalize_call(
        started.trace_handle,
        provider_status="success",
        retry_count=0,
        validation_status="accepted",
        accepted_candidate={"decision": "defer", "selected_alpha_id": None},
        fallback_used=False,
        fallback_reason=None,
        error_code=None,
    )
    manifest_path = session.finalize_manifest(complete=True)

    assert session.incomplete
    assert "SEMANTIC_RECORDER_APPEND_FAILED" in session.degraded_reason_codes
    assert json.loads(manifest_path.read_text())["complete"] is False


def test_cache_write_failure_does_not_invalidate_saved_accepted_result(tmp_path: Path) -> None:
    session = _session(tmp_path, cache=_WriteFailingCache())
    started = _start(session)
    candidate = {"decision": "defer", "selected_alpha_id": None}

    assert session.finalize_call(
        started.trace_handle,
        provider_status="success",
        retry_count=0,
        validation_status="accepted",
        accepted_candidate=candidate,
        fallback_used=False,
        fallback_reason=None,
        error_code=None,
    )

    assert session.recorder.read_all()[0]["validated_output"] == candidate
    assert "SEMANTIC_CACHE_WRITE_FAILED" in session.degraded_reason_codes
    assert session.incomplete is False


def test_sensitive_input_and_output_are_redacted_and_fail_closed(tmp_path: Path) -> None:
    session = _session(tmp_path)
    started = _start(
        session,
        {
            "Authorization": "Bearer top-secret-token",
            "claim": "file /Users/private-name/research.txt api_key=sk-sensitive-value",
            "hidden_reasoning": "never persist this",
        },
    )
    session.finalize_call(
        started.trace_handle,
        provider_status="success",
        retry_count=0,
        validation_status="accepted",
        accepted_candidate={
            "decision": "defer",
            "selected_alpha_id": None,
            "note": "/Users/private-name/research.txt",
        },
        fallback_used=False,
        fallback_reason=None,
        error_code=None,
    )
    manifest_path = session.finalize_manifest(complete=True)

    persisted = (tmp_path / "llm_semantic_calls.jsonl").read_text(encoding="utf-8")
    assert "top-secret-token" not in persisted
    assert "sk-sensitive-value" not in persisted
    assert "never persist this" not in persisted
    assert "/Users/private-name" not in persisted
    assert "[REDACTED" in persisted
    manifest = json.loads(manifest_path.read_text())
    assert manifest["complete"] is False
    assert manifest["exact_replay_ready"] is False


def test_manifest_write_failure_is_contained(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session(tmp_path)

    def fail_write(**kwargs):
        del kwargs
        raise OSError("synthetic manifest error")

    monkeypatch.setattr(
        "comqutor_alpha.llm_runtime.session.write_semantic_manifest_atomic",
        fail_write,
    )

    assert session.finalize_manifest(complete=True) is None
    assert "SEMANTIC_MANIFEST_FINALIZATION_FAILED" in session.degraded_reason_codes
