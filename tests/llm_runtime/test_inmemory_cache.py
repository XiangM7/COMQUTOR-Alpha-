from __future__ import annotations

import pytest

from comqutor_alpha.llm_runtime.cache import (
    InMemoryLLMResponseCache,
    NullLLMResponseCache,
    build_llm_cache_key,
)
from comqutor_alpha.llm_runtime.errors import CacheCorruptionError, ContractValidationError
from tests.llm_runtime.fakes import make_record
from comqutor_alpha.llm_runtime.contracts import cache_entry_from_record


def cache_entry() -> dict[str, object]:
    return cache_entry_from_record(
        make_record(),
        created_at="2026-01-01T00:00:01+00:00",
        expires_at="2026-01-01T01:00:01+00:00",
    ).to_dict()


# --- Protocol conformance / basic round trip ---------------------------------


def test_starts_empty_and_healthcheck_true() -> None:
    cache = InMemoryLLMResponseCache()
    entry = cache_entry()
    assert cache.get(entry["cache_key"]) is None
    assert cache.healthcheck() is True


def test_round_trip_get_put_delete() -> None:
    cache = InMemoryLLMResponseCache()
    entry = cache_entry()
    cache.put(entry["cache_key"], entry)
    assert cache.get(entry["cache_key"]) == entry
    cache.delete(entry["cache_key"])
    assert cache.get(entry["cache_key"]) is None


def test_get_returns_a_copy_not_the_stored_object() -> None:
    """Mutating the returned dict must never corrupt the cache's own copy --
    a real backend (Redis, a database) would never let a caller mutate its
    storage by reference either."""
    cache = InMemoryLLMResponseCache()
    entry = cache_entry()
    cache.put(entry["cache_key"], entry)
    returned = cache.get(entry["cache_key"])
    returned["validated_output"] = {"tampered": True}
    assert cache.get(entry["cache_key"]) == entry


# --- TTL behavior --------------------------------------------------------


def test_ttl_expiry_causes_a_later_get_to_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_time = [1000.0]
    monkeypatch.setattr("comqutor_alpha.llm_runtime.cache._monotonic", lambda: fake_time[0])
    cache = InMemoryLLMResponseCache()
    entry = cache_entry()
    cache.put(entry["cache_key"], entry, ttl_seconds=60)
    assert cache.get(entry["cache_key"]) == entry
    fake_time[0] += 61
    assert cache.get(entry["cache_key"]) is None


def test_no_ttl_never_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_time = [0.0]
    monkeypatch.setattr("comqutor_alpha.llm_runtime.cache._monotonic", lambda: fake_time[0])
    cache = InMemoryLLMResponseCache()
    entry = cache_entry()
    cache.put(entry["cache_key"], entry)
    fake_time[0] += 10_000_000
    assert cache.get(entry["cache_key"]) == entry


@pytest.mark.parametrize("ttl", [0, -1, True, 1.5])
def test_invalid_ttl_is_rejected(ttl: object) -> None:
    entry = cache_entry()
    with pytest.raises(ValueError, match="LLM_CACHE_TTL_INVALID"):
        InMemoryLLMResponseCache().put(entry["cache_key"], entry, ttl_seconds=ttl)  # type: ignore[arg-type]


# --- Corruption / identity mismatch (same contract as RedisLLMResponseCache) -


def test_tampered_cached_output_fails_hash_validation() -> None:
    cache = InMemoryLLMResponseCache()
    entry = cache_entry()
    cache.put(entry["cache_key"], entry)
    # Simulate a corrupted stored entry -- reach into the private store the
    # way a real corrupted backend read would surface a bad payload.
    cache._values[entry["cache_key"]]["validated_output"] = {"claims": ["tampered"]}
    with pytest.raises(CacheCorruptionError) as caught:
        cache.get(entry["cache_key"])
    assert caught.value.reason_code == "CACHE_ENTRY_OUTPUT_HASH_MISMATCH"


def test_key_mismatch_is_corruption() -> None:
    cache = InMemoryLLMResponseCache()
    entry = cache_entry()
    wrong_key = "comqutor:llm:v1:" + "1" * 64
    cache._values[wrong_key] = entry  # stored under a key that disagrees with entry["cache_key"]
    with pytest.raises(CacheCorruptionError) as caught:
        cache.get(wrong_key)
    assert caught.value.reason_code == "CACHE_ENTRY_KEY_MISMATCH"


def test_invalid_or_rejected_content_cannot_be_written() -> None:
    entry = cache_entry()
    entry["validated_output"] = None
    with pytest.raises(ContractValidationError):
        InMemoryLLMResponseCache().put(entry["cache_key"], entry)


# --- Task / semantic-identity isolation (Section 19) -------------------------


def test_task_identity_prevents_cross_task_collision() -> None:
    cache = InMemoryLLMResponseCache()
    alpha_entry = cache_entry()
    alpha_key = alpha_entry["cache_key"]
    cache.put(alpha_key, alpha_entry)

    stance_key = build_llm_cache_key(
        task="evidence_stance_classifier",
        prompt_version="prompt.v1",
        prompt_sha256=alpha_entry["prompt_sha256"],
        provider=alpha_entry["provider"],
        model=alpha_entry["model"],
        input_schema_version=alpha_entry["output_schema_version"],
        output_schema_version=alpha_entry["output_schema_version"],
        input_sha256=alpha_entry["input_sha256"],
    )
    assert stance_key != alpha_key
    assert cache.get(stance_key) is None
    # The alpha_classifier entry is completely unaffected/unreachable from
    # evidence_stance_classifier's own key -- no collision either direction.
    assert cache.get(alpha_key) == alpha_entry


@pytest.mark.parametrize(
    "field,value",
    [
        ("input_sha256", "1" * 64),
        ("model", "a-different-model"),
        ("provider", "a-different-provider"),
        ("prompt_version", "prompt.v2"),
        ("output_schema_version", "output.v2"),
    ],
)
def test_semantic_identity_change_is_a_cache_miss_not_stale_reuse(field: str, value: str) -> None:
    """A changed semantic authority (model, prompt version, schema version,
    or the input itself) must produce a fresh cache key and therefore a
    miss -- never a silently-reused stale answer."""
    cache = InMemoryLLMResponseCache()
    base_entry = cache_entry()
    cache.put(base_entry["cache_key"], base_entry)

    kwargs = {
        "task": base_entry["task"],
        "prompt_version": "prompt.v1",
        "prompt_sha256": base_entry["prompt_sha256"],
        "provider": base_entry["provider"],
        "model": base_entry["model"],
        "input_schema_version": "input.v1",
        "output_schema_version": base_entry["output_schema_version"],
        "input_sha256": base_entry["input_sha256"],
    }
    if field == "prompt_version":
        kwargs["prompt_version"] = value
    else:
        kwargs[field] = value
    changed_key = build_llm_cache_key(**kwargs)
    assert changed_key != base_entry["cache_key"]
    assert cache.get(changed_key) is None


def test_run_id_does_not_partition_the_cache() -> None:
    """The key design (build_llm_cache_key) deliberately excludes run_id --
    an in-memory cache instance scoped to a single run therefore need not
    (and does not) do anything extra to be run-local: it simply never
    outlives one run_research_request call. This test only confirms the key
    itself is run_id-agnostic, matching tests/llm_runtime/test_cache_key.py's
    existing assertion, for this backend's own direct behavior."""
    entry = cache_entry()
    key_a = build_llm_cache_key(
        task=entry["task"],
        prompt_version="prompt.v1",
        prompt_sha256=entry["prompt_sha256"],
        provider=entry["provider"],
        model=entry["model"],
        input_schema_version="input.v1",
        output_schema_version=entry["output_schema_version"],
        input_sha256=entry["input_sha256"],
        run_id="run-a",
    )
    key_b = build_llm_cache_key(
        task=entry["task"],
        prompt_version="prompt.v1",
        prompt_sha256=entry["prompt_sha256"],
        provider=entry["provider"],
        model=entry["model"],
        input_schema_version="input.v1",
        output_schema_version=entry["output_schema_version"],
        input_sha256=entry["input_sha256"],
        run_id="run-b",
    )
    assert key_a == key_b


# --- Explicit disable still available ----------------------------------


def test_null_cache_remains_available_and_always_misses() -> None:
    cache = NullLLMResponseCache()
    entry = cache_entry()
    cache.put(entry["cache_key"], entry)
    assert cache.get(entry["cache_key"]) is None
    assert cache.healthcheck() is True
