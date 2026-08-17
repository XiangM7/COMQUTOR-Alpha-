from __future__ import annotations

import ast
import socket
from pathlib import Path

from conftest import FakeSemanticInvoker, bundle_for

from comqutor_alpha.structure_engine.structured_output_shadow import StructuredOutputShadowParser

REPO_ROOT = Path(__file__).resolve().parents[2]
SHADOW_MODULE = "comqutor_alpha.structure_engine.structured_output_shadow"
LIVE_SHADOW_MODULE = "comqutor_alpha.structure_engine.structured_output_live_shadow"
PRODUCTION_SCOPES = (
    "comqutor_alpha/api",
    "comqutor_alpha/replay",
    "comqutor_alpha/graph_engine",
    "comqutor_alpha/conflict_engine",
    "comqutor_alpha/exposure",
    "tradingagents",
)
PROTECTED_FILES = (
    "comqutor_alpha/exposure_engine.py",
    "comqutor_alpha/structure_engine/structured_output_adapter.py",
    "comqutor_alpha/structure_engine/week2_llm.py",
    "comqutor_alpha/structure_engine/alpha_mapper.py",
    "comqutor_alpha/structure_engine/structure_extractor.py",
)


def _imports_shadow(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and str(node.module or "") == SHADOW_MODULE:
            return True
        if isinstance(node, ast.Import) and any(alias.name == SHADOW_MODULE for alias in node.names):
            return True
    return False


def _imports_live_shadow(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and str(node.module or "") == LIVE_SHADOW_MODULE:
            return True
        if isinstance(node, ast.Import) and any(
            alias.name == LIVE_SHADOW_MODULE for alias in node.names
        ):
            return True
    return False


def test_live_production_importer_count_is_zero():
    files = [REPO_ROOT / path for path in PROTECTED_FILES]
    for scope in PRODUCTION_SCOPES:
        files.extend((REPO_ROOT / scope).rglob("*.py"))
    importers = sorted(str(path.relative_to(REPO_ROOT)) for path in files if _imports_shadow(path))
    assert importers == []


def test_stage_e_live_shadow_has_one_allowlisted_production_importer():
    files = [REPO_ROOT / path for path in PROTECTED_FILES]
    for scope in PRODUCTION_SCOPES:
        files.extend((REPO_ROOT / scope).rglob("*.py"))
    importers = sorted(
        str(path.relative_to(REPO_ROOT)) for path in files if _imports_live_shadow(path)
    )
    assert importers == ["comqutor_alpha/api/routes_research.py"]


def test_fake_parse_makes_no_network_connection(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    report = "Formatting complete. End of report."
    result = StructuredOutputShadowParser(FakeSemanticInvoker(bundle_for(report))).parse_report_shadow(
        source_report=report,
        run_id="run-shadow-1",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id="run-shadow-1:news_agent:news_report",
    )
    assert result["production_authority"] is False


def test_shadow_modules_contain_no_provider_route_cache_or_database_imports():
    forbidden = ("week2_llm", "llm_runtime", "sqlalchemy", "redis", "requests", "httpx", "socket")
    for path in (REPO_ROOT / "comqutor_alpha/structure_engine").glob("structured_output_shadow*.py"):
        text = path.read_text(encoding="utf-8")
        assert not any(f"import {name}" in text or f"from {name}" in text for name in forbidden)
