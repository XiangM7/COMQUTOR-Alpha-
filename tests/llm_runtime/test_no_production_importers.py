from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from comqutor_alpha.llm_runtime.cache import RedisLLMResponseCache
from tests.llm_runtime.fakes import FakeRedisClient

REPOSITORY = Path(__file__).resolve().parents[2]
RUNTIME = REPOSITORY / "comqutor_alpha/llm_runtime"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_only_approved_runtime_integration_points_import_runtime() -> None:
    importers: list[str] = []
    for root_name in ("comqutor_alpha", "tradingagents"):
        for path in (REPOSITORY / root_name).rglob("*.py"):
            if RUNTIME in path.parents:
                continue
            if any(module.startswith("comqutor_alpha.llm_runtime") for module in imported_modules(path)):
                importers.append(str(path.relative_to(REPOSITORY)))
        assert sorted(importers) == [
            "comqutor_alpha/api/routes_research.py",
            "comqutor_alpha/structure_engine/structured_output_live_shadow.py",
            "comqutor_alpha/structure_engine/structured_output_shadow_provider.py",
            "comqutor_alpha/structure_engine/structured_output_shadow_replay.py",
            "comqutor_alpha/structure_engine/week2_llm.py",
    ]


def test_runtime_has_no_network_provider_redis_or_database_imports() -> None:
    forbidden_roots = {
        "anthropic",
        "boto3",
        "cohere",
        "google.generativeai",
        "httpx",
        "openai",
        "psycopg",
        "psycopg2",
        "redis",
        "requests",
        "socket",
        "sqlalchemy",
        "urllib.request",
    }
    violations: list[str] = []
    for path in RUNTIME.glob("*.py"):
        for module in imported_modules(path):
            if any(module == root or module.startswith(f"{root}.") for root in forbidden_roots):
                violations.append(f"{path.name}:{module}")
    assert violations == []


def test_import_and_adapter_construction_do_not_touch_network_or_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_connection(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("network access attempted")

    import socket

    monkeypatch.setattr(socket, "create_connection", forbidden_connection)
    imported = importlib.import_module("comqutor_alpha.llm_runtime")
    assert imported.SEMANTIC_CALL_SCHEMA_VERSION == "comqutor.semantic_call.v1"
    client = FakeRedisClient()
    RedisLLMResponseCache(client)
    assert client.calls == []


def test_runtime_contains_only_expected_source_files() -> None:
    assert {path.name for path in RUNTIME.glob("*.py")} == {
        "__init__.py",
        "cache.py",
        "canonical_json.py",
        "contracts.py",
        "errors.py",
        "manifest.py",
        "recorder.py",
        "session.py",
    }
