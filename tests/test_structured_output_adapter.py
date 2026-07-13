import json

from comqutor_alpha.adapters.tradingagents_output_writer import build_raw_agent_output_record
from comqutor_alpha.structure_engine.structured_output_adapter import (
    SCHEMA_VERSION,
    _error_payload,
    adapt_raw_agent_output,
    adapt_raw_agent_outputs,
    safe_default_record,
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


def _raw_record(raw_output, agent="news_agent"):
    return build_raw_agent_output_record(
        run_id="run1",
        ticker="NVDA",
        agent=agent,
        tradingagents_agent="News Analyst",
        source_field="news_report",
        source_path="news_report",
        source_candidates=["news_report"],
        raw_value=raw_output,
        created_at="2026-07-01T00:00:00Z",
    )


def test_structured_record_traces_back_to_raw_agent_output_id():
    raw_record = _raw_record("AI demand supports GPU demand and datacenter capex.")

    structured = adapt_raw_agent_output(raw_record, "run1", "NVDA")

    assert structured["claim_id"] == f"{raw_record['agent_output_id']}:claim:1"
    assert structured["agent_output_id"] == structured["claim_id"]
    assert structured["claim_id"] != raw_record["agent_output_id"]
    assert structured["source_agent_output_id"] == raw_record["agent_output_id"]
    assert structured["source_refs"] == [raw_record["agent_output_id"]]


def test_safe_default_record_preserves_traceability_for_empty_raw_output():
    raw_record = _raw_record("")

    structured = adapt_raw_agent_output(raw_record, "run1", "NVDA")

    assert structured["claim"] == "unknown"
    assert structured["adapter_warning"] == "raw output is empty"
    assert structured["claim_id"] == f"{raw_record['agent_output_id']}:claim:1"
    assert structured["source_agent_output_id"] == raw_record["agent_output_id"]
    assert structured["source_refs"] == [raw_record["agent_output_id"]]


def test_safe_default_record_has_no_traceability_when_raw_row_is_invalid():
    structured = adapt_raw_agent_output("not-a-mapping", "run1", "NVDA")

    assert structured["adapter_warning"] == "raw row is not an object"
    assert structured["source_refs"] == []
    assert structured["source_agent_output_id"] is None
    assert structured["claim_id"] == "unknown_agent_default:claim:1"


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
    assert payload["schema_version"] == SCHEMA_VERSION
    assert SCHEMA_VERSION == "week1a.structured_agent_outputs.v2"
    assert len(payload["records"]) == 2
    log_path = run_dir / "error_logs" / "structured_output_adapter_errors.jsonl"
    assert log_path.exists()

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert entries[0]["run_id"] == "run1"
    assert entries[0]["ticker"] == "NVDA"
    assert entries[0]["agent"] == "fundamental_agent"
    assert entries[0]["error_code"] == "EMPTY_RAW_OUTPUT"
    assert "raw_preview" in entries[0]
    assert "record_preview" in entries[0]
    assert str(tmp_path) not in json.dumps(entries[0])


def test_error_log_redacts_secret_like_tokens_from_previews():
    raw_record = {
        "agent": "news_agent",
        "raw_output": "Leaked credential api_key=sk-testsecret123 in the report.",
    }
    structured_record = safe_default_record(
        "run1",
        "NVDA",
        "news_agent",
        raw_record["raw_output"],
        "structured record failed validation",
        error_code="STRUCTURED_VALIDATION_FAILED",
    )

    payload = _error_payload("run1", "NVDA", raw_record, structured_record)

    assert "sk-testsecret123" not in json.dumps(payload)
    assert "api_key=[REDACTED]" in payload["raw_preview"]


def test_error_log_redacts_quoted_json_style_secrets_from_previews():
    """raw_record is a dict, so _safe_preview() serializes it with json.dumps(),
    which double-quotes both keys and values (e.g. `"token": "abcdef123456"`).
    The plain key=value redaction pattern cannot match through that extra
    quoting, so the JSON-aware pattern must catch it instead.
    """
    raw_record = {
        "agent": "news_agent",
        "raw_output": "Some innocuous claim text.",
        "api_key": "sk-jsonstyle123",
        "token": "abcdef123456",
        "password": "hunter2",
        "secret": "topsecret",
    }
    structured_record = safe_default_record(
        "run1",
        "NVDA",
        "news_agent",
        raw_record["raw_output"],
        "structured record failed validation",
        error_code="STRUCTURED_VALIDATION_FAILED",
    )

    payload = _error_payload("run1", "NVDA", raw_record, structured_record)
    serialized = json.dumps(payload)

    assert "sk-jsonstyle123" not in serialized
    assert "abcdef123456" not in serialized
    assert "hunter2" not in serialized
    assert "topsecret" not in serialized
    assert '"api_key": "[REDACTED]"' in payload["raw_preview"]
    assert '"token": "[REDACTED]"' in payload["raw_preview"]
    assert '"password": "[REDACTED]"' in payload["raw_preview"]
    assert '"secret": "[REDACTED]"' in payload["raw_preview"]


def test_malformed_raw_record_does_not_crash_full_run(tmp_path):
    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    (run_dir / "raw_agent_outputs.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "ticker": "NVDA",
                "agent_outputs": [
                    "not-a-mapping",
                    {"agent": "news_agent", "raw_output": "AI demand drives GPU demand."},
                ],
            }
        ),
        encoding="utf-8",
    )

    path = save_structured_agent_outputs(run_dir)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert len(payload["records"]) == 2
    assert payload["records"][0]["adapter_error_code"] == "INVALID_RAW_RECORD"
    assert payload["records"][1]["claim"] != "unknown"


def test_long_markdown_report_splits_into_traceable_claims():
    report = """# NVDA Outlook

## Demand
- AI training demand is accelerating and GPU demand is rising.
- Datacenter power and cooling spending supports infrastructure growth.

| Metric | Change |
| --- | --- |
| Revenue | +20% |

Disclaimer: This report is not investment advice.

## Risk
Custom silicon could reduce NVIDIA dependency over time.
"""
    raw_record = _raw_record(report)

    records = adapt_raw_agent_outputs(raw_record, "run1", "NVDA")

    assert len(records) == 3
    assert len({record["claim_id"] for record in records}) == 3
    assert {record["source_section"] for record in records} == {"Demand", "Risk"}
    assert all(record["source_agent_output_id"] == raw_record["agent_output_id"] for record in records)
    assert all(record["source_refs"] == [raw_record["agent_output_id"]] for record in records)
    serialized = json.dumps(records).lower()
    assert "disclaimer" not in serialized
    assert "metric" not in serialized


def test_legacy_raw_record_without_agent_output_id_still_adapts():
    records = adapt_raw_agent_outputs(
        {
            "agent": "news_agent",
            "raw_output": "AI demand is increasing and GPU demand is rising.",
        },
        "run1",
        "NVDA",
    )

    assert len(records) == 1
    assert records[0]["agent_output_id"].startswith("news_agent_")
    assert records[0]["source_agent_output_id"].startswith("news_agent_")
    assert records[0]["claim_id"].endswith(":claim:1")
    assert records[0]["claim_id"] != records[0]["source_agent_output_id"]
