import json
from pathlib import Path

import pytest

from comqutor_alpha.api.routes_research import run_research_request
from comqutor_alpha.structure_engine.structured_output_adapter import extract_entities


def _offline_outputs():
    return [
        {
            "agent": "technical_agent",
            "raw_output": "NVDA shows positive momentum but high valuation creates downside risk.",
        },
    ]


@pytest.mark.parametrize(
    "bad_ticker",
    [
        "'; DROP TABLE agent_outputs; --",
        "TOO-LONG-TICKER-XYZ",
        "",
        "../etc/passwd",
    ],
)
def test_rejects_malformed_tickers(tmp_path, bad_ticker):
    response = run_research_request(
        {
            "ticker": bad_ticker,
            "offline_raw_agent_outputs": _offline_outputs(),
        },
        output_root=tmp_path,
    )

    assert response["status"] == "failed"
    assert response["error_code"] == "INVALID_TICKER"
    assert list(tmp_path.iterdir()) == []


def test_normalizes_valid_lowercase_ticker(tmp_path):
    response = run_research_request(
        {
            "ticker": "nvda",
            "offline_raw_agent_outputs": _offline_outputs(),
        },
        output_root=tmp_path,
    )

    assert response["status"] == "completed"
    assert response["ticker"] == "NVDA"


def test_offline_disabled_in_production(tmp_path, monkeypatch):
    monkeypatch.setenv("COMQUTOR_ENV", "production")

    response = run_research_request(
        {
            "ticker": "NVDA",
            "offline_raw_agent_outputs": _offline_outputs(),
        },
        output_root=tmp_path,
    )

    assert response["status"] == "failed"
    assert response["error_code"] == "OFFLINE_DISABLED"


def test_injected_runner_with_invalid_run_id_fails_safely(tmp_path):
    def bad_runner(payload, output_root):
        run_dir = Path(output_root) / "bad run id!"
        run_dir.mkdir(parents=True)
        (run_dir / "raw_agent_outputs.json").write_text(
            json.dumps({"run_id": "bad run id!", "ticker": payload["ticker"], "agent_outputs": []}),
            encoding="utf-8",
        )
        return run_dir

    response = run_research_request(
        {"ticker": "NVDA"},
        runner=bad_runner,
        output_root=tmp_path,
    )

    assert response["status"] == "failed"
    assert response["error_code"] == "INVALID_RUN_ID"
    assert not (tmp_path / "bad run id!" / "structured_agent_outputs.json").exists()


def test_extract_entities_uses_word_boundaries():
    entities = extract_entities(
        "The firm is maintaining certain guidance while training staff",
        ticker="MSFT",
    )

    assert entities == ["MSFT"]
    assert "AI" not in entities


def _model_field_names(model_cls):
    fields = getattr(model_cls, "model_fields", None)  # Pydantic v2
    if fields is None:
        fields = model_cls.__fields__  # Pydantic v1
    return set(fields.keys())


try:
    from fastapi.testclient import TestClient

    from comqutor_alpha.api.routes_research import router

    FASTAPI_AVAILABLE = router is not None
except ImportError:
    FASTAPI_AVAILABLE = False


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="fastapi is not installed")
def test_api_router_loads_with_installed_pydantic():
    from comqutor_alpha.api.routes_research import ResearchRequest

    assert router is not None
    field_names = _model_field_names(ResearchRequest)
    assert field_names == {
        "ticker",
        "analysis_date",
        "selected_analysts",
        "offline_raw_agent_outputs",
        "run_id",
    }
    assert "allow_real_tradingagents_run" not in field_names
    assert "config" not in field_names


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="fastapi is not installed")
def test_api_rejects_malformed_ticker_and_hides_real_run_toggle():
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post("/api/research", json={"ticker": "'; DROP"})

    assert response.status_code == 422
    body = response.json()
    assert "allow_real_tradingagents_run" not in body
