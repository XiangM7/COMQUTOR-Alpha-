from __future__ import annotations

from pathlib import Path

import pytest

from comqutor_alpha.llm_runtime.cache import RedisLLMResponseCache
from comqutor_alpha.llm_runtime.errors import CacheCorruptionError, RecorderIntegrityError
from comqutor_alpha.llm_runtime.manifest import SEMANTIC_MANIFEST_FILENAME, verify_semantic_manifest
from comqutor_alpha.llm_runtime.recorder import SEMANTIC_CALLS_FILENAME, SemanticCallRecorder
from tests.llm_runtime.fakes import FakeRedisClient


def test_invalid_manifest_json_returns_stable_reason_code(tmp_path: Path) -> None:
    path = tmp_path / SEMANTIC_MANIFEST_FILENAME
    path.write_bytes(b'{"broken":')
    result = verify_semantic_manifest(path)
    assert result.reason_codes == ("SEMANTIC_MANIFEST_JSON_INVALID",)


def test_non_object_jsonl_record_fails_closed(tmp_path: Path) -> None:
    (tmp_path / SEMANTIC_CALLS_FILENAME).write_bytes(b"[]\n")
    with pytest.raises(RecorderIntegrityError) as caught:
        SemanticCallRecorder(run_id="run-test", output_directory=tmp_path, mode="test")
    assert caught.value.reason_code == "RECORDER_RECORD_NOT_OBJECT"


def test_unknown_cache_schema_fails_closed() -> None:
    key = "comqutor:llm:v1:" + "0" * 64
    client = FakeRedisClient()
    client.values[key] = '{"schema_version":"unknown"}'
    with pytest.raises(CacheCorruptionError) as caught:
        RedisLLMResponseCache(client).get(key)
    assert caught.value.reason_code == "CACHE_ENTRY_REQUIRED_FIELD_MISSING"
