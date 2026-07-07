import json

from comqutor_alpha.structure_engine.structured_output_adapter import (
    adapt_raw_agent_output,
    save_structured_agent_outputs,
)


def test_empty_raw_output_returns_safe_default():
    record = adapt_raw_agent_output({"agent": "news_agent", "raw_output": ""}, "run1", "NVDA")
    assert record["claim"] == "unknown"
    assert record["direction"] == "unknown"
    assert record["confidence"] == 0.0


def test_nvda_ai_text_extracts_factors_and_source_type():
    text = "NVDA AI demand and GPU demand are rising as datacenter capex increases."
    record = adapt_raw_agent_output({"agent": "technical_agent", "raw_output": text}, "run1", "NVDA")
    assert "AI Demand" in record["factors"]
    assert "GPU Demand" in record["factors"]
    assert "Datacenter CapEx" in record["factors"]
    assert record["source_type"] == "technical"


def test_adapter_writes_file_and_logs_invalid_rows(tmp_path):
    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    (run_dir / "raw_agent_outputs.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "ticker": "NVDA",
                "agent_outputs": [
                    {"agent": "news_agent", "raw_output": "AI demand supports GPU demand."},
                    {"agent": "fundamental_agent", "raw_output": ""},
                ],
            }
        )
    )
    path = save_structured_agent_outputs(run_dir)
    assert path.exists()
    payload = json.loads(path.read_text())
    assert len(payload["records"]) == 2
    assert (run_dir / "error_logs" / "structured_output_adapter_errors.jsonl").exists()
