"""W4.3 Agent Outputs API tests.

GET /api/research/{run_id}/agent-outputs is structured-only by design (see
docs/w4_3_gate_contract.md section 5/7.6 -- the spec-owner resolution of the
raw-transcript-exposure conflict discovered while drafting the gate
contract). These tests lock in that the endpoint never reads, and never
returns any content from, raw_agent_outputs.json.
"""

from __future__ import annotations

import json
import pathlib

from comqutor_alpha.api.agent_output_reader import get_agent_outputs_response

_SCHEMA_VERSION = "week1a.structured_agent_outputs.v2"


def _sample_record(claim_id, *, agent="news_agent", source_agent_output_id="o_1"):
    return {
        "claim_id": claim_id,
        "agent_output_id": claim_id,
        "run_id": "irrelevant_to_record_validation",
        "ticker": "NVDA",
        "agent": agent,
        "claim": f"claim text for {claim_id}",
        "evidence": f"evidence text for {claim_id}",
        "entities": ["NVDA"],
        "factors": ["demand"],
        "direction": "positive",
        "confidence": 0.7,
        "source_type": "analyst_report",
        "source_agent_output_id": source_agent_output_id,
        "assertion_status": "asserted",
        "semantic_polarity": "activation",
    }


def _seed_run(
    tmp_path,
    run_id,
    *,
    ticker="NVDA",
    write_raw=True,
    raw_text=None,
    structured_records=None,
    structured_payload=None,
    schema_version=_SCHEMA_VERSION,
):
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    if write_raw:
        (run_dir / "raw_agent_outputs.json").write_text(
            raw_text
            if raw_text is not None
            else json.dumps(
                {
                    "run_id": run_id,
                    "ticker": ticker,
                    "agent_outputs": [
                        {
                            "agent": "news_agent",
                            "raw_output": "full free-text analyst report goes here " * 20,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    if structured_payload is not None:
        (run_dir / "structured_agent_outputs.json").write_text(
            structured_payload, encoding="utf-8"
        )
    elif structured_records is not None:
        payload = {
            "schema_version": schema_version,
            "run_id": run_id,
            "ticker": ticker,
            "records": structured_records,
        }
        (run_dir / "structured_agent_outputs.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    return run_dir


# ---------------------------------------------------------------------------
# Normal structured-only response
# ---------------------------------------------------------------------------


def test_normal_response_is_structured_only(tmp_path):
    records = [_sample_record("c1"), _sample_record("c2", agent="market_agent")]
    _seed_run(tmp_path, "normal_run", structured_records=records)

    result = get_agent_outputs_response("normal_run", output_root=tmp_path)

    assert result["status"] == "ok"
    assert result["run_id"] == "normal_run"
    assert result["ticker"] == "NVDA"
    assert result["schema_version"] == _SCHEMA_VERSION
    assert result["structured_agent_outputs"] == records
    assert result["count"] == 2

    assert "raw_agent_outputs" not in result
    assert "raw_output" not in result
    assert "raw_schema_version" not in result
    assert "raw_count" not in result
    for record in result["structured_agent_outputs"]:
        assert "raw_output" not in record


def test_count_is_correct(tmp_path):
    records = [_sample_record(f"c{i}") for i in range(5)]
    _seed_run(tmp_path, "count_run", structured_records=records)

    result = get_agent_outputs_response("count_run", output_root=tmp_path)
    assert result["count"] == 5
    assert len(result["structured_agent_outputs"]) == 5


def test_record_order_is_preserved(tmp_path):
    # Deliberately not alphabetical/sorted -- proves the reader does not
    # reorder records.
    records = [_sample_record("z9"), _sample_record("a1"), _sample_record("m5")]
    _seed_run(tmp_path, "order_run", structured_records=records)

    result = get_agent_outputs_response("order_run", output_root=tmp_path)
    assert [r["claim_id"] for r in result["structured_agent_outputs"]] == ["z9", "a1", "m5"]


def test_provenance_fields_preserved(tmp_path):
    records = [_sample_record("c1", source_agent_output_id="o_market_1")]
    _seed_run(tmp_path, "provenance_run", structured_records=records)

    result = get_agent_outputs_response("provenance_run", output_root=tmp_path)
    record = result["structured_agent_outputs"][0]
    assert record["claim_id"] == "c1"
    assert record["source_agent_output_id"] == "o_market_1"
    assert record["agent"] == "news_agent"
    assert record["claim"]
    assert record["evidence"]
    assert record["entities"] == ["NVDA"]
    assert record["factors"] == ["demand"]
    assert record["direction"] == "positive"
    assert record["confidence"] == 0.7
    assert record["source_type"] == "analyst_report"
    assert record["assertion_status"] == "asserted"
    assert record["semantic_polarity"] == "activation"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_invalid_run_id():
    result = get_agent_outputs_response("../secret", output_root="unused")
    assert result["status"] == "failed"
    assert result["error_code"] == "INVALID_RUN_ID"


def test_missing_run(tmp_path):
    result = get_agent_outputs_response("no_such_run", output_root=tmp_path)
    assert result["status"] == "failed"
    assert result["error_code"] == "RUN_NOT_FOUND"


def test_structured_artifact_missing_when_only_raw_exists(tmp_path):
    _seed_run(tmp_path, "raw_only_run", write_raw=True, structured_records=None)

    result = get_agent_outputs_response("raw_only_run", output_root=tmp_path)
    assert result["status"] == "failed"
    assert result["error_code"] == "AGENT_OUTPUTS_NOT_READY"


def test_malformed_payload_not_a_dict(tmp_path):
    _seed_run(tmp_path, "malformed_run", structured_payload=json.dumps([1, 2, 3]))

    result = get_agent_outputs_response("malformed_run", output_root=tmp_path)
    assert result["status"] == "failed"
    assert result["error_code"] == "AGENT_OUTPUTS_CORRUPTED"


def test_malformed_payload_unparseable_json(tmp_path):
    _seed_run(tmp_path, "unparseable_run", structured_payload="{not valid json!!")

    result = get_agent_outputs_response("unparseable_run", output_root=tmp_path)
    assert result["status"] == "failed"
    assert result["error_code"] == "AGENT_OUTPUTS_CORRUPTED"


def test_run_id_mismatch(tmp_path):
    run_dir = tmp_path / "mismatch_run"
    run_dir.mkdir()
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "run_id": "a_completely_different_run",
        "ticker": "NVDA",
        "records": [],
    }
    (run_dir / "structured_agent_outputs.json").write_text(json.dumps(payload), encoding="utf-8")

    result = get_agent_outputs_response("mismatch_run", output_root=tmp_path)
    assert result["status"] == "failed"
    assert result["error_code"] == "AGENT_OUTPUTS_CORRUPTED"


def test_records_not_a_list(tmp_path):
    run_dir = tmp_path / "records_not_list_run"
    run_dir.mkdir()
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "run_id": "records_not_list_run",
        "ticker": "NVDA",
        "records": {"not": "a list"},
    }
    (run_dir / "structured_agent_outputs.json").write_text(json.dumps(payload), encoding="utf-8")

    result = get_agent_outputs_response("records_not_list_run", output_root=tmp_path)
    assert result["status"] == "failed"
    assert result["error_code"] == "AGENT_OUTPUTS_CORRUPTED"


def test_record_not_a_dict(tmp_path):
    run_dir = tmp_path / "record_not_dict_run"
    run_dir.mkdir()
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "run_id": "record_not_dict_run",
        "ticker": "NVDA",
        "records": [_sample_record("c1"), "not_a_dict_record"],
    }
    (run_dir / "structured_agent_outputs.json").write_text(json.dumps(payload), encoding="utf-8")

    result = get_agent_outputs_response("record_not_dict_run", output_root=tmp_path)
    assert result["status"] == "failed"
    assert result["error_code"] == "AGENT_OUTPUTS_CORRUPTED"


def test_empty_ticker_is_corrupted(tmp_path):
    run_dir = tmp_path / "empty_ticker_run"
    run_dir.mkdir()
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "run_id": "empty_ticker_run",
        "ticker": "",
        "records": [],
    }
    (run_dir / "structured_agent_outputs.json").write_text(json.dumps(payload), encoding="utf-8")

    result = get_agent_outputs_response("empty_ticker_run", output_root=tmp_path)
    assert result["status"] == "failed"
    assert result["error_code"] == "AGENT_OUTPUTS_CORRUPTED"


# ---------------------------------------------------------------------------
# Raw exposure boundary (the resolved spec conflict)
# ---------------------------------------------------------------------------


def test_response_never_contains_a_local_path(tmp_path):
    records = [_sample_record("c1")]
    _seed_run(tmp_path, "no_path_run", structured_records=records)

    result = get_agent_outputs_response("no_path_run", output_root=tmp_path)
    serialized = json.dumps(result)
    assert str(tmp_path) not in serialized
    assert "no_path_run/structured_agent_outputs.json" not in serialized


def test_endpoint_succeeds_even_when_raw_agent_outputs_json_is_corrupted(tmp_path):
    """Proves the endpoint's success does not depend on raw_agent_outputs.json
    being valid -- a corrupted raw file must never surface as a failure of
    this structured-only endpoint."""
    records = [_sample_record("c1")]
    _seed_run(tmp_path, "corrupt_raw_run", raw_text="{{{ not json at all", structured_records=records)

    result = get_agent_outputs_response("corrupt_raw_run", output_root=tmp_path)
    assert result["status"] == "ok"
    assert result["structured_agent_outputs"] == records


def test_reader_never_opens_raw_agent_outputs_json(tmp_path, monkeypatch):
    records = [_sample_record("c1")]
    _seed_run(tmp_path, "never_opened_run", raw_text="{{{ not json at all", structured_records=records)

    opened_names = []
    original_open = pathlib.Path.open

    def tracking_open(self, *args, **kwargs):
        opened_names.append(self.name)
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "open", tracking_open)

    result = get_agent_outputs_response("never_opened_run", output_root=tmp_path)

    assert result["status"] == "ok"
    assert "raw_agent_outputs.json" not in opened_names
    assert "structured_agent_outputs.json" in opened_names
