from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.contract
def test_offline_upstream_baseline_verifier() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/verify_upstream_baseline.py"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["status"] == "pass"
    assert result["offline"] is True
    assert result["report_keys"] == [
        "market_report",
        "sentiment_report",
        "news_report",
        "fundamentals_report",
    ]


@pytest.mark.contract
def test_sanitized_fixture_keeps_upstream_decision_outside_reports() -> None:
    fixture_path = ROOT / "tests/comqutor_alpha/fixtures/upstream_state_minimal.json"
    final_state, processed_decision = json.loads(fixture_path.read_text())["return_value"]
    assert processed_decision.startswith("comparison-only")
    assert final_state["final_trade_decision"].startswith("comparison-only")
    for key in ("market_report", "sentiment_report", "news_report", "fundamentals_report"):
        assert "comparison-only" not in final_state[key]
