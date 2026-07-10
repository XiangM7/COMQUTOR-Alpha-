import json
from pathlib import Path

from comqutor_alpha.api.routes_research import (
    build_research_response,
    get_research_run,
    run_research_request,
)
from comqutor_alpha.structure_engine.alpha_mapper import save_alpha_matches
from comqutor_alpha.structure_engine.structure_extractor import save_extracted_structures


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
    run_dir = tmp_path / response["run_id"]
    assert (run_dir / "metadata.json").exists()
    assert (run_dir / "raw_agent_outputs.json").exists()
    assert (run_dir / "structured_agent_outputs.json").exists()
    assert response["artifacts"] == {
        "metadata": True,
        "raw_agent_outputs": True,
        "structured_agent_outputs": True,
        "final_report": False,
        # Week 2 artifacts are produced by a separate, explicit step
        # (save_alpha_matches / save_extracted_structures), not automatically
        # by run_research_request, so they are absent for this offline run.
        "alpha_matches": False,
        "extracted_structures": False,
        "structured_output_error_logs": False,
    }
    assert response["agent_output_count"] == 4
    assert response["structured_output_count"] == 4


def test_offline_raw_outputs_use_hardened_schema(tmp_path):
    response = run_research_request(_payload(), output_root=tmp_path)
    raw = json.loads((tmp_path / response["run_id"] / "raw_agent_outputs.json").read_text())
    first = raw["agent_outputs"][0]

    assert raw["schema_version"] == "week1a.raw_agent_outputs.v1"
    for field in (
        "agent_output_id",
        "run_id",
        "ticker",
        "agent",
        "tradingagents_agent",
        "source_field",
        "source_path",
        "source_candidates",
        "raw_output",
        "content_length",
        "original_content_length",
        "truncated",
        "created_at",
    ):
        assert field in first
    assert first["source_field"] == "offline_raw_agent_outputs"
    assert first["source_candidates"] == ["offline_raw_agent_outputs"]


def test_research_response_has_structured_rows(tmp_path):
    response = run_research_request(_payload(), output_root=tmp_path)
    structured = json.loads((tmp_path / response["run_id"] / "structured_agent_outputs.json").read_text())

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
    assert loaded["artifacts"]["raw_agent_outputs"] is True
    assert loaded["artifacts"]["structured_agent_outputs"] is True


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
    assert (tmp_path / "fake_runner_week1a" / "structured_agent_outputs.json").exists()


def test_research_response_reports_week2_artifact_booleans(tmp_path):
    response = run_research_request(_payload(), output_root=tmp_path)
    run_id = response["run_id"]

    assert response["artifacts"]["alpha_matches"] is False
    assert response["artifacts"]["extracted_structures"] is False
    assert response["artifacts"]["structured_output_error_logs"] is False

    save_alpha_matches(run_id, output_root=tmp_path)
    save_extracted_structures(run_id, output_root=tmp_path)

    updated = get_research_run(run_id, output_root=tmp_path)
    serialized = json.dumps(updated, ensure_ascii=False)

    assert updated["artifacts"]["alpha_matches"] is True
    assert updated["artifacts"]["extracted_structures"] is True
    # No Week2/Week1A error occurred for this offline run, so the error log
    # artifact should still be absent even though the other two now exist.
    assert updated["artifacts"]["structured_output_error_logs"] is False
    assert str(tmp_path) not in serialized
    assert "run_dir" not in updated


def test_build_research_response_reports_week2_artifacts_without_local_paths(tmp_path):
    run_id = "manual_week2_artifacts"
    run_dir = tmp_path / run_id
    error_dir = run_dir / "error_logs"
    error_dir.mkdir(parents=True)

    (run_dir / "metadata.json").write_text(
        json.dumps({"run_id": run_id, "ticker": "NVDA"}),
        encoding="utf-8",
    )
    (run_dir / "raw_agent_outputs.json").write_text(
        json.dumps({"run_id": run_id, "ticker": "NVDA", "agent_outputs": []}),
        encoding="utf-8",
    )
    (run_dir / "structured_agent_outputs.json").write_text(
        json.dumps({"run_id": run_id, "ticker": "NVDA", "records": []}),
        encoding="utf-8",
    )
    (run_dir / "alpha_matches.json").write_text(
        json.dumps({"run_id": run_id, "matches": []}),
        encoding="utf-8",
    )
    (run_dir / "extracted_structures.json").write_text(
        json.dumps({"run_id": run_id, "nodes": [], "edges": []}),
        encoding="utf-8",
    )
    (error_dir / "structured_output_adapter_errors.jsonl").write_text(
        json.dumps({"run_id": run_id, "error_code": "EMPTY_RAW_OUTPUT"}) + "\n",
        encoding="utf-8",
    )

    response = build_research_response(run_id, output_root=tmp_path)
    serialized = json.dumps(response, ensure_ascii=False)

    assert response["artifacts"]["alpha_matches"] is True
    assert response["artifacts"]["extracted_structures"] is True
    assert response["artifacts"]["structured_output_error_logs"] is True
    assert str(tmp_path) not in serialized


def test_research_response_does_not_expose_raw_output_paths_or_config(tmp_path):
    response = run_research_request(_payload(), output_root=tmp_path)
    serialized = json.dumps(response, ensure_ascii=False)

    assert "raw_output" not in serialized
    assert "metadata_path" not in response
    assert "raw_agent_outputs_path" not in response
    assert "structured_agent_outputs_path" not in response
    assert "run_dir" not in response
    assert "config" not in response
    assert str(tmp_path) not in serialized
    assert response["artifacts"]["metadata"] is True
    assert response["artifacts"]["raw_agent_outputs"] is True


def test_real_tradingagents_run_is_blocked_by_default(tmp_path):
    response = run_research_request(
        {
            "ticker": "NVDA",
            "analysis_date": "2026-06-30",
            "selected_analysts": ["market"],
        },
        output_root=tmp_path,
    )

    assert response["status"] == "failed"
    assert response["error_code"] == "REAL_RUN_DISABLED"
    assert "disabled by default" in response["message"]


def test_invalid_run_id_returns_stable_error_code(tmp_path):
    response = run_research_request(
        {
            "run_id": "../secret",
            "ticker": "NVDA",
            "offline_raw_agent_outputs": [],
        },
        output_root=tmp_path,
    )

    assert response["status"] == "failed"
    assert response["error_code"] == "INVALID_RUN_ID"
    assert response["message"] == "Invalid run_id."


def test_too_many_offline_outputs_returns_stable_error_code(tmp_path):
    response = run_research_request(
        {
            "ticker": "NVDA",
            "offline_raw_agent_outputs": [
                {"agent": f"agent_{index}", "raw_output": "text"} for index in range(21)
            ],
        },
        output_root=tmp_path,
    )

    assert response["status"] == "failed"
    assert response["error_code"] == "INVALID_OFFLINE_OUTPUTS"


def test_non_list_offline_outputs_returns_stable_error_code(tmp_path):
    response = run_research_request(
        {
            "ticker": "NVDA",
            "offline_raw_agent_outputs": "not-a-list",
        },
        output_root=tmp_path,
    )

    assert response["status"] == "failed"
    assert response["error_code"] == "INVALID_OFFLINE_OUTPUTS"


def test_get_research_run_invalid_run_id_returns_stable_error_code(tmp_path):
    response = get_research_run("../secret", output_root=tmp_path)

    assert response["status"] == "failed"
    assert response["error_code"] == "INVALID_RUN_ID"
    assert response["message"] == "Invalid run_id."


def test_api_module_imports_without_server():
    import comqutor_alpha.api.main as api_main

    assert hasattr(api_main, "app")
