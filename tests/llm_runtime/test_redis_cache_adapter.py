from __future__ import annotations

import json

import pytest

from comqutor_alpha.llm_runtime.cache import RedisLLMResponseCache
from comqutor_alpha.llm_runtime.canonical_json import canonical_json_text
from comqutor_alpha.llm_runtime.contracts import cache_entry_from_record
from comqutor_alpha.llm_runtime.errors import CacheCorruptionError, ContractValidationError
from tests.llm_runtime.fakes import FakeRedisClient, make_record


def cache_entry() -> dict[str, object]:
    return cache_entry_from_record(
        make_record(),
        created_at="2026-01-01T00:00:01+00:00",
        expires_at="2026-01-01T01:00:01+00:00",
    ).to_dict()


def test_construction_performs_no_client_io() -> None:
    client = FakeRedisClient()
    RedisLLMResponseCache(client)
    assert client.calls == []


def test_fake_redis_round_trip_and_ttl_propagation() -> None:
    client = FakeRedisClient()
    cache = RedisLLMResponseCache(client)
    entry = cache_entry()
    cache.put(entry["cache_key"], entry, ttl_seconds=90)

    assert client.ttls[entry["cache_key"]] == 90
    assert cache.get(entry["cache_key"]) == entry
    assert cache.healthcheck() is True
    cache.delete(entry["cache_key"])
    assert cache.get(entry["cache_key"]) is None


@pytest.mark.parametrize("ttl", [0, -1, True, 1.5])
def test_invalid_ttl_is_rejected(ttl: object) -> None:
    entry = cache_entry()
    with pytest.raises(ValueError, match="LLM_CACHE_TTL_INVALID"):
        RedisLLMResponseCache(FakeRedisClient()).put(
            entry["cache_key"], entry, ttl_seconds=ttl  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("raw", [b"not json", b"\xff", 42])
def test_corrupt_cache_payload_fails_explicitly(raw: object) -> None:
    client = FakeRedisClient()
    entry = cache_entry()
    client.values[entry["cache_key"]] = raw
    with pytest.raises(CacheCorruptionError):
        RedisLLMResponseCache(client).get(entry["cache_key"])


def test_tampered_cached_output_fails_hash_validation() -> None:
    client = FakeRedisClient()
    entry = cache_entry()
    entry["validated_output"] = {"claims": ["tampered"]}
    client.values[entry["cache_key"]] = canonical_json_text(entry)
    with pytest.raises(CacheCorruptionError) as caught:
        RedisLLMResponseCache(client).get(entry["cache_key"])
    assert caught.value.reason_code == "CACHE_ENTRY_OUTPUT_HASH_MISMATCH"


def test_key_mismatch_is_corruption() -> None:
    client = FakeRedisClient()
    entry = cache_entry()
    client.values["comqutor:llm:v1:" + "1" * 64] = json.dumps(entry)
    with pytest.raises(CacheCorruptionError) as caught:
        RedisLLMResponseCache(client).get("comqutor:llm:v1:" + "1" * 64)
    assert caught.value.reason_code == "CACHE_ENTRY_KEY_MISMATCH"


def test_invalid_or_rejected_content_cannot_be_written() -> None:
    entry = cache_entry()
    entry["validated_output"] = None
    with pytest.raises(ContractValidationError):
        RedisLLMResponseCache(FakeRedisClient()).put(entry["cache_key"], entry)
