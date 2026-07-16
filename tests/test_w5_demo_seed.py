from __future__ import annotations

import json
from pathlib import Path

import pytest

from comqutor_alpha.research_lifecycle import submit_research_request
from scripts.seed_w5_demo import (
    DEFAULT_DEMO_ROOT,
    DEMO_RUN_IDS,
    DemoSeedError,
    resolve_demo_targets,
    seed_w5_demo,
)


def _targets(tmp_path: Path):
    demo_root = tmp_path / ".demo" / "w5"
    return resolve_demo_targets(
        demo_root / "outputs" / "runs",
        f"sqlite:///{demo_root / 'comqutor_demo.db'}",
        allow_unsafe_target=True,
    )


def test_default_targets_are_isolated_under_demo_root():
    targets = resolve_demo_targets()
    assert targets.output_root.is_relative_to(DEFAULT_DEMO_ROOT)
    assert targets.database_path is not None
    assert targets.database_path.is_relative_to(DEFAULT_DEMO_ROOT)


@pytest.mark.parametrize(
    ("output_root", "database_url", "environment"),
    [
        ("outputs/runs", "sqlite:///.demo/w5/comqutor_demo.db", {}),
        (".demo/w5/outputs/runs", "sqlite:///normal-development.db", {}),
        (".demo/w5/outputs/runs", "postgresql://localhost/comqutor", {}),
        (
            ".demo/w5/outputs/runs",
            "sqlite:///.demo/w5/comqutor_demo.db",
            {"COMQUTOR_ENV": "production"},
        ),
    ],
)
def test_unsafe_targets_require_explicit_confirmation(output_root, database_url, environment):
    with pytest.raises(DemoSeedError, match="UNSAFE_DEMO_TARGET_REQUIRES_CONFIRMATION"):
        resolve_demo_targets(output_root, database_url, environment=environment)


def test_seed_is_complete_idempotent_and_reusable_without_provider(tmp_path, monkeypatch):
    targets = _targets(tmp_path)
    monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "true")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "true")

    first = seed_w5_demo(targets)
    second = seed_w5_demo(targets)
    assert first == second
    assert {item["ticker"] for item in first} == {"NVDA", "QQQ"}
    assert all(item["status"] == "completed" for item in first)
    assert all(item["history_count"] == 1 for item in first)

    from comqutor_alpha.storage.db.engine import build_engine
    from comqutor_alpha.storage.db.repository import GraphPersistenceRepository

    repository = GraphPersistenceRepository(
        build_engine(targets.database_url), database_url=targets.database_url
    )
    for ticker, run_id in DEMO_RUN_IDS.items():
        ui_payload = {
            "ticker": ticker,
            "analysis_date": "2026-06-30",
            "selected_analysts": ["market", "news", "fundamentals", "sentiment"],
        }
        monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "false")
        reused = submit_research_request(
            ui_payload,
            output_root=targets.output_root,
            graph_repository=repository,
            executor=lambda *args, **kwargs: pytest.fail("completed cache executed pipeline"),
        )
        assert reused["run_id"] == run_id
        assert reused["status"] == "completed"
        assert reused["cache_disposition"] == "reused_completed"

        metadata = json.loads(
            (targets.output_root / run_id / "metadata.json").read_text(encoding="utf-8")
        )
        assert metadata["demo_fixture"] is True
        assert metadata["source"] == "approved_offline_golden_fixture"
        assert metadata["live_provider_used"] is False
        assert repository.count_agent_outputs(run_id) > 0


def test_only_nvda_and_qqq_are_seeded(tmp_path):
    results = seed_w5_demo(_targets(tmp_path))
    assert [item["ticker"] for item in results] == ["NVDA", "QQQ"]
    assert results[0]["main_conflict"] == "A101__A304"
    assert {"A001__A501", "A003__A501"}.issubset(results[1]["conflicts"])
