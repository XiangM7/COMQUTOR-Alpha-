"""Offline cache-key primitives and injected LLM response-cache adapters."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from comqutor_alpha.llm_runtime.canonical_json import canonical_json_text, sha256_canonical_json
from comqutor_alpha.llm_runtime.contracts import (
    SEMANTIC_CALL_SCHEMA_VERSION,
    SEMANTIC_TASKS,
    LLMCacheEntry,
    validate_cache_entry,
)
from comqutor_alpha.llm_runtime.errors import CacheCorruptionError, ContractValidationError

LLM_CACHE_KEY_VERSION = "comqutor.llm_cache_key.v1"
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@runtime_checkable
class LLMResponseCache(Protocol):
    def get(self, cache_key: str) -> dict[str, Any] | None: ...

    def put(
        self,
        cache_key: str,
        entry: Mapping[str, Any] | LLMCacheEntry,
        ttl_seconds: int | None = None,
    ) -> None: ...

    def delete(self, cache_key: str) -> None: ...

    def healthcheck(self) -> bool: ...


def build_llm_cache_key(
    *,
    task: str,
    prompt_version: str,
    prompt_sha256: str,
    provider: str,
    model: str,
    input_schema_version: str,
    output_schema_version: str,
    input_sha256: str,
    taxonomy_version: str | None = None,
    semantic_call_schema_version: str = SEMANTIC_CALL_SCHEMA_VERSION,
    run_id: str | None = None,
) -> str:
    """Build a versioned key from semantic identity only.

    ``run_id`` is accepted solely to make the cross-run rule explicit; it is
    intentionally excluded from the hashed key material.
    """

    del run_id
    if task not in SEMANTIC_TASKS:
        raise ValueError("CACHE_KEY_TASK_INVALID")
    fields = {
        "prompt_version": prompt_version,
        "provider": provider,
        "model": model,
        "input_schema_version": input_schema_version,
        "output_schema_version": output_schema_version,
        "semantic_call_schema_version": semantic_call_schema_version,
    }
    if any(not isinstance(value, str) or not value.strip() for value in fields.values()):
        raise ValueError("CACHE_KEY_VERSION_FIELD_INVALID")
    for value in (prompt_sha256, input_sha256):
        if not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value):
            raise ValueError("CACHE_KEY_SHA256_INVALID")
    if taxonomy_version is not None and (
        not isinstance(taxonomy_version, str) or not taxonomy_version.strip()
    ):
        raise ValueError("CACHE_KEY_TAXONOMY_VERSION_INVALID")
    identity = {
        "cache_key_version": LLM_CACHE_KEY_VERSION,
        "semantic_call_schema_version": semantic_call_schema_version,
        "task": task,
        "prompt_version": prompt_version,
        "prompt_sha256": prompt_sha256,
        "provider": provider,
        "model": model,
        "input_schema_version": input_schema_version,
        "output_schema_version": output_schema_version,
        "input_sha256": input_sha256,
        "taxonomy_version": taxonomy_version,
    }
    return f"comqutor:llm:v1:{sha256_canonical_json(identity)}"


class NullLLMResponseCache:
    """A network-free cache implementation that always misses."""

    def get(self, cache_key: str) -> None:
        del cache_key
        return None

    def put(
        self,
        cache_key: str,
        entry: Mapping[str, Any] | LLMCacheEntry,
        ttl_seconds: int | None = None,
    ) -> None:
        del cache_key, entry, ttl_seconds

    def delete(self, cache_key: str) -> None:
        del cache_key

    def healthcheck(self) -> bool:
        return True


class RedisLLMResponseCache:
    """Strict JSON adapter over an injected Redis-like client.

    Construction performs no I/O and imports no Redis factory. Corrupt entries
    raise ``CacheCorruptionError`` rather than being silently trusted or deleted.
    """

    def __init__(self, client: Any) -> None:
        required_methods = ("get", "set", "delete", "ping")
        if client is None or any(not callable(getattr(client, name, None)) for name in required_methods):
            raise TypeError("RedisLLMResponseCache requires an injected Redis-like client")
        self._client = client

    def get(self, cache_key: str) -> dict[str, Any] | None:
        raw = self._client.get(cache_key)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise CacheCorruptionError(
                    "LLM_CACHE_ENTRY_UTF8_INVALID",
                    "Cache entry is not valid UTF-8",
                ) from exc
        elif isinstance(raw, str):
            text = raw
        else:
            raise CacheCorruptionError(
                "LLM_CACHE_ENTRY_TYPE_INVALID",
                "Cache client returned neither bytes nor text",
            )
        try:
            entry = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CacheCorruptionError(
                "LLM_CACHE_ENTRY_JSON_INVALID",
                "Cache entry is not valid JSON",
            ) from exc
        result = validate_cache_entry(entry, expected_cache_key=cache_key)
        if not result.valid:
            raise CacheCorruptionError(
                result.reason_codes[0],
                f"Cache entry failed validation: {','.join(result.reason_codes)}",
            )
        return dict(entry)

    def put(
        self,
        cache_key: str,
        entry: Mapping[str, Any] | LLMCacheEntry,
        ttl_seconds: int | None = None,
    ) -> None:
        if ttl_seconds is not None and (
            not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or ttl_seconds <= 0
        ):
            raise ValueError("LLM_CACHE_TTL_INVALID")
        result = validate_cache_entry(entry, expected_cache_key=cache_key)
        if not result.valid:
            raise ContractValidationError(result, "Cache entry validation failed")
        value = entry.to_dict() if isinstance(entry, LLMCacheEntry) else dict(entry)
        payload = canonical_json_text(value)
        if ttl_seconds is None:
            self._client.set(cache_key, payload)
        else:
            self._client.set(cache_key, payload, ex=ttl_seconds)

    def delete(self, cache_key: str) -> None:
        self._client.delete(cache_key)

    def healthcheck(self) -> bool:
        return bool(self._client.ping())
