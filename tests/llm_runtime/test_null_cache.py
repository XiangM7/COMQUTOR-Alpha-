from __future__ import annotations

from comqutor_alpha.llm_runtime.cache import NullLLMResponseCache


def test_null_cache_never_hits_and_mutations_are_noops() -> None:
    cache = NullLLMResponseCache()
    assert cache.healthcheck() is True
    assert cache.get("anything") is None
    cache.put("anything", {"not": "validated"}, ttl_seconds=1)
    cache.delete("anything")
    assert cache.get("anything") is None
