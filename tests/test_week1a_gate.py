import json
from pathlib import Path

from comqutor_alpha.api.routes_research import get_research_run, run_research_request


def _offline_outputs():
    return [
        {
            "agent": "technical_agent",
            "raw_output": "NVDA shows positive momentum but high valuation creates downside risk.",
        },
        {
            "agent": "news_agent",
            "raw_output": "AI capex is increasing and driving GPU demand.",
        },
        {
            "agent": "fundamental_agent",
            "raw_output": "Revenue guidance was raised due to strong customer demand.",
        },
        {
            "agent": "sentiment_agent",
            "raw_output": "AI stocks are rising due to strong investor attention and narrative momentum.",
        },
    ]


def _payload():
    return {
        "ticker": "NVDA",
        "analysis_date": "2026-06-30",
        "selected_analysts": ["market", "news", "fundamentals", "sentiment"],
        "offline_raw_agent_outputs": _offline_outputs(),
    }


def test_run_research_request_with_offline_raw_outputs(tmp_path):
    response = run_research_request(_payload(), output_root=tmp_path)

    assert response["status"] == "completed"
    assert response["run_id"]
    assert Path(response["metadata_path"]).exists()
    assert Path(response["raw_agent_outputs_path"]).exists()
    assert Path(response["structured_agent_outputs_path"]).exists()
    assert response["agent_output_count"] == 4
    assert response["structured_output_count"] == 4


def test_research_response_has_structured_rows(tmp_path):
    response = run_research_request(_payload(), output_root=tmp_path)
    structured = json.loads(Path(response["structured_agent_outputs_path"]).read_text())

    assert "records" in structured
    for record in structured["records"]:
        for field in (
            "run_id",
            "ticker",
            "agent",
            "claim",
            "evidence",
            "factors",
            "direction",
            "confidence",
            "source_type",
        ):
            assert field in record


def test_get_research_run(tmp_path):
    response = run_research_request(_payload(), output_root=tmp_path)
    loaded = get_research_run(response["run_id"], output_root=tmp_path)

    assert loaded["run_id"] == response["run_id"]
    assert loaded["ticker"] == "NVDA"
    assert loaded["agent_output_count"] == 4
    assert loaded["structured_output_count"] == 4
    assert loaded["raw_agent_outputs_path"]
    assert loaded["structured_agent_outputs_path"]


def test_fake_runner_injection(tmp_path):
    def fake_runner(payload, output_root):
        run_id = "fake_runner_week1a"
        run_dir = Path(output_root) / run_id
        run_dir.mkdir(parents=True)
        metadata = {
            "run_id": run_id,
            "ticker": payload["ticker"],
            "analysis_date": payload["analysis_date"],
        }
        raw = {
            "run_id": run_id,
            "ticker": payload["ticker"],
            "agent_outputs": _offline_outputs(),
        }
        (run_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        (run_dir / "raw_agent_outputs.json").write_text(json.dumps(raw), encoding="utf-8")
        return run_dir

    response = run_research_request(
        {
            "ticker": "NVDA",
            "analysis_date": "2026-06-30",
            "selected_analysts": ["market", "news", "fundamentals", "sentiment"],
        },
        runner=fake_runner,
        output_root=tmp_path,
    )

    assert response["status"] == "completed"
    assert response["run_id"] == "fake_runner_week1a"
    assert response["structured_output_count"] == 4
    assert Path(response["structured_agent_outputs_path"]).exists()


def test_api_module_imports_without_server():
    import comqutor_alpha.api.main as api_main

    assert hasattr(api_main, "app")
