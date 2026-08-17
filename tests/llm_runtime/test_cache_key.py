from __future__ import annotations

import re

import pytest

from comqutor_alpha.llm_runtime.cache import build_llm_cache_key
from comqutor_alpha.llm_runtime.canonical_json import sha256_text


def key(**changes: str | None) -> str:
    values: dict[str, str | None] = {
        "task": "alpha_classifier",
        "prompt_version": "prompt.v1",
        "prompt_sha256": sha256_text("prompt"),
        "provider": "fake-provider",
        "model": "fake-model",
        "input_schema_version": "input.v1",
        "output_schema_version": "output.v1",
        "input_sha256": sha256_text("input"),
        "taxonomy_version": "taxonomy.v1",
        "semantic_call_schema_version": "comqutor.semantic_call.v1",
        "run_id": "run-a",
    }
    values.update(changes)
    return build_llm_cache_key(**values)  # type: ignore[arg-type]


def test_key_is_deterministic_versioned_and_contains_no_raw_data() -> None:
    first = key()
    assert first == key()
    assert re.fullmatch(r"comqutor:llm:v1:[0-9a-f]{64}", first)
    assert "prompt" not in first
    assert "input" not in first


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("prompt_version", "prompt.v2"),
        ("prompt_sha256", sha256_text("changed prompt")),
        ("provider", "other-provider"),
        ("model", "other-model"),
        ("input_schema_version", "input.v2"),
        ("output_schema_version", "output.v2"),
        ("input_sha256", sha256_text("changed input")),
        ("taxonomy_version", "taxonomy.v2"),
        ("semantic_call_schema_version", "comqutor.semantic_call.v2"),
    ],
)
def test_every_semantic_identity_change_changes_key(field: str, value: str) -> None:
    assert key(**{field: value}) != key()


def test_run_id_does_not_change_key() -> None:
    assert key(run_id="run-a") == key(run_id="run-b")
