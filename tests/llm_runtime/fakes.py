"""Network-free test doubles and valid contract fixtures."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from comqutor_alpha.llm_runtime.cache import build_llm_cache_key
from comqutor_alpha.llm_runtime.canonical_json import sha256_canonical_json, sha256_text
from comqutor_alpha.llm_runtime.contracts import SEMANTIC_CALL_SCHEMA_VERSION


class FakeRedisClient:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}
        self.ttls: dict[str, int] = {}
        self.calls: list[tuple[Any, ...]] = []

    def get(self, key: str) -> Any:
        self.calls.append(("get", key))
        return self.values.get(key)

    def set(self, key: str, value: Any, *, ex: int | None = None) -> bool:
        self.calls.append(("set", key, ex))
        self.values[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    def delete(self, key: str) -> int:
        self.calls.append(("delete", key))
        return int(self.values.pop(key, None) is not None)

    def ping(self) -> bool:
        self.calls.append(("ping",))
        return True


class InMemoryFakeCache:
    """Protocol-compatible fake; deliberately lives only in tests."""

    def __init__(self) -> None:
        self.values: dict[str, dict[str, Any]] = {}

    def get(self, cache_key: str) -> dict[str, Any] | None:
        value = self.values.get(cache_key)
        return deepcopy(value) if value is not None else None

    def put(
        self,
        cache_key: str,
        entry: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> None:
        del ttl_seconds
        self.values[cache_key] = deepcopy(entry)

    def delete(self, cache_key: str) -> None:
        self.values.pop(cache_key, None)

    def healthcheck(self) -> bool:
        return True


def make_record(
    *,
    call_id: str = "call-0",
    run_id: str = "run-test",
    call_sequence: int = 0,
    task: str = "structured_adapter",
    execution_mode: str = "test",
    **overrides: Any,
) -> dict[str, Any]:
    input_payload = deepcopy(overrides.pop("input_payload", {"ticker": "AAPL", "text": "fact"}))
    validated_output = deepcopy(overrides.pop("validated_output", {"claims": []}))
    raw_output_text = overrides.pop("raw_output_text", '{"claims":[]}')
    prompt_sha256 = overrides.pop("prompt_sha256", sha256_text("prompt-v1"))
    input_sha256 = overrides.pop("input_sha256", sha256_canonical_json(input_payload))
    validated_output_sha256 = overrides.pop(
        "validated_output_sha256",
        sha256_canonical_json(validated_output) if validated_output is not None else None,
    )
    raw_output_sha256 = overrides.pop(
        "raw_output_sha256",
        sha256_text(raw_output_text) if raw_output_text is not None else None,
    )
    provider = overrides.get("provider", "fake-provider")
    model = overrides.get("model", "fake-model")
    input_schema_version = overrides.get("input_schema_version", "input.v1")
    output_schema_version = overrides.get("output_schema_version", "output.v1")
    taxonomy_version = overrides.get("taxonomy_version")
    cache_key = build_llm_cache_key(
        task=task,
        prompt_version=overrides.get("prompt_version", "prompt.v1"),
        prompt_sha256=prompt_sha256,
        provider=provider,
        model=model,
        input_schema_version=input_schema_version,
        output_schema_version=output_schema_version,
        input_sha256=input_sha256,
        taxonomy_version=taxonomy_version,
    )
    record: dict[str, Any] = {
        "schema_version": SEMANTIC_CALL_SCHEMA_VERSION,
        "call_id": call_id,
        "run_id": run_id,
        "call_sequence": call_sequence,
        "task": task,
        "execution_mode": execution_mode,
        "prompt_version": "prompt.v1",
        "prompt_sha256": prompt_sha256,
        "input_schema_version": "input.v1",
        "output_schema_version": "output.v1",
        "provider": "fake-provider",
        "model": "fake-model",
        "taxonomy_version": None,
        "input_payload": input_payload,
        "input_sha256": input_sha256,
        "raw_output_text": raw_output_text,
        "raw_output_sha256": raw_output_sha256,
        "validated_output": validated_output,
        "validated_output_sha256": validated_output_sha256,
        "started_at": "2026-01-01T00:00:00+00:00",
        "completed_at": "2026-01-01T00:00:00.010000+00:00",
        "latency_ms": 10,
        "token_usage": {"input_tokens": 4, "output_tokens": 2, "total_tokens": 6},
        "cache": {"cache_key": cache_key, "hit": False},
        "retry_count": 0,
        "validation_status": "accepted",
        "provider_status": "success",
        "fallback_used": False,
        "fallback_reason": None,
        "error_code": None,
        "error_message": None,
    }
    record.update(overrides)
    return record
