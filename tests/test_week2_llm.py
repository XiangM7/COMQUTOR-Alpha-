import json
import os
import time

import pytest
from dotenv import load_dotenv

from comqutor_alpha.structure_engine.alpha_mapper import map_claim_to_alpha
from comqutor_alpha.structure_engine.structure_extractor import extract_structures_from_records
from comqutor_alpha.structure_engine.structured_output_adapter import adapt_raw_agent_outputs
from comqutor_alpha.structure_engine.week2_llm import (
    Week2LLMGateway,
    build_server_week2_llm_gateway,
)


class _Response:
    def __init__(self, content):
        self.content = content


class _SequenceModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def invoke(self, _prompt):
        response = self.responses[self.calls]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        if callable(response):
            response = response()
        return _Response(response)


def _gateway(tmp_path, model, **kwargs):
    (tmp_path / "run1").mkdir(exist_ok=True)
    return Week2LLMGateway(
        model,
        run_id="run1",
        output_root=tmp_path,
        timeout_seconds=kwargs.get("timeout_seconds", 0.2),
        max_retries=kwargs.get("max_retries", 1),
        max_calls=kwargs.get("max_calls", 8),
    )


def _record(text, factors=None):
    raw_id = "run1:news_agent:news_report"
    return {
        "run_id": "run1",
        "ticker": "NVDA",
        "agent": "news_agent",
        "claim_id": f"{raw_id}:claim:1",
        "agent_output_id": f"{raw_id}:claim:1",
        "source_agent_output_id": raw_id,
        "claim": text,
        "evidence": text,
        "factors": factors or [],
        "direction": "neutral",
        "confidence": 0.8,
    }


def test_gateway_retries_invalid_json_then_returns_validated_result(tmp_path):
    model = _SequenceModel(["not json", '{"value": 7}'])
    gateway = _gateway(tmp_path, model)

    result = gateway.invoke_json(
        "alpha_classifier",
        {"allowed_alpha_ids": ["A101"]},
        lambda payload: payload["value"],
    )

    assert result == 7
    assert model.calls == 2
    log = (tmp_path / "run1" / "error_logs" / "week2_llm_errors.jsonl").read_text()
    assert "WEEK2_LLM_INVALID_JSON" in log


def test_gateway_exhaustion_logs_only_safe_codes(tmp_path):
    secret = "sk-provider-secret"
    model = _SequenceModel([f"api_key={secret}", f"token={secret}"])
    gateway = _gateway(tmp_path, model)

    result = gateway.invoke_json("alpha_classifier", {}, lambda payload: payload)
    log = (tmp_path / "run1" / "error_logs" / "week2_llm_errors.jsonl").read_text()

    assert result is None
    assert model.calls == 2
    assert secret not in log
    assert "api_key" not in log
    assert "WEEK2_LLM_INVALID_JSON" in log


def test_gateway_enforces_wall_clock_timeout(tmp_path):
    def slow_response():
        time.sleep(0.2)
        return '{"value": 1}'

    model = _SequenceModel([slow_response])
    gateway = _gateway(tmp_path, model, timeout_seconds=0.02, max_retries=0)
    started = time.monotonic()

    result = gateway.invoke_json("alpha_classifier", {}, lambda payload: payload)

    assert result is None
    assert time.monotonic() - started < 0.15
    log = (tmp_path / "run1" / "error_logs" / "week2_llm_errors.jsonl").read_text()
    assert "WEEK2_LLM_TIMEOUT" in log


def test_server_gateway_is_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("COMQUTOR_WEEK2_LLM_ENABLED", raising=False)

    assert build_server_week2_llm_gateway("run1", tmp_path) is None


def test_server_gateway_uses_existing_provider_factory_only_after_opt_in(tmp_path, monkeypatch):
    import tradingagents.llm_clients as llm_clients

    captured = {}
    model = _SequenceModel([])

    class FakeClient:
        def get_llm(self):
            return model

    def fake_factory(**kwargs):
        captured.update(kwargs)
        return FakeClient()

    (tmp_path / "run1").mkdir()
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "1")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_PROVIDER", "fake-provider")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MODEL", "fake-model")
    monkeypatch.setattr(llm_clients, "create_llm_client", fake_factory)

    gateway = build_server_week2_llm_gateway("run1", tmp_path)

    assert gateway is not None
    assert captured["provider"] == "fake-provider"
    assert captured["model"] == "fake-model"
    assert captured["max_retries"] == 0
    assert "api_key" not in captured


def test_gateway_call_budget_prevents_unbounded_retries(tmp_path):
    model = _SequenceModel(["not json", '{"value": 2}'])
    gateway = _gateway(tmp_path, model, max_calls=1)

    result = gateway.invoke_json("alpha_classifier", {}, lambda payload: payload)
    log = (tmp_path / "run1" / "error_logs" / "week2_llm_errors.jsonl").read_text()

    assert result is None
    assert model.calls == 1
    assert "WEEK2_LLM_CALL_BUDGET_EXHAUSTED" in log


def test_structured_adapter_uses_valid_llm_claims(tmp_path):
    raw_text = "AI demand is rising because GPU orders increased 20%."
    response = {
        "claims": [
            {
                "claim": "AI demand is rising.",
                "evidence": raw_text,
                "entities": ["AI", "GPU"],
                "factors": ["AI Demand", "GPU Demand"],
                "direction": "positive",
                "confidence": 0.9,
                "source_section": "Demand",
            }
        ]
    }
    gateway = _gateway(tmp_path, _SequenceModel([json.dumps(response)]), max_retries=0)
    raw_id = "run1:news_agent:news_report"

    records = adapt_raw_agent_outputs(
        {"agent_output_id": raw_id, "agent": "news_agent", "raw_output": raw_text},
        "run1",
        "NVDA",
        llm_gateway=gateway,
    )

    assert records[0]["extraction_method"] == "llm_strict_json"
    assert records[0]["claim_id"] == f"{raw_id}:claim:1"
    assert records[0]["source_agent_output_id"] == raw_id
    assert records[0]["evidence"] == raw_text


def test_structured_adapter_falls_back_after_invalid_llm_fields(tmp_path):
    raw_text = "AI demand drives GPU demand."
    invalid = json.dumps(
        {
            "claims": [
                {
                    "claim": "AI demand drives GPU demand.",
                    "evidence": raw_text,
                    "entities": [],
                    "factors": ["AI Demand", "GPU Demand"],
                    "direction": "positive",
                    "confidence": 4,
                    "source_section": None,
                }
            ]
        }
    )
    model = _SequenceModel([invalid, invalid])
    gateway = _gateway(tmp_path, model)

    records = adapt_raw_agent_outputs(
        {"agent": "news_agent", "raw_output": raw_text},
        "run1",
        "NVDA",
        llm_gateway=gateway,
    )

    assert model.calls == 2
    assert records[0]["extraction_method"] == "deterministic_splitter"
    assert records[0]["claim"] == raw_text


def test_mapper_llm_selects_only_from_admissible_candidates(tmp_path):
    model = _SequenceModel(
        [json.dumps({"decision": "select", "selected_alpha_id": "A101"})]
    )
    gateway = _gateway(tmp_path, model, max_retries=0)
    record = _record(
        "AI demand is strong, but rich valuation creates downside risk.",
        ["AI Demand", "Valuation Risk"],
    )

    result = map_claim_to_alpha(record, llm_gateway=gateway)

    assert result["match_status"] == "matched"
    assert result["matched_alpha"] == "A101"
    assert result["classifier"]["status"] == "applied"


def test_mapper_invalid_llm_candidate_falls_back_without_response_leak(tmp_path):
    invalid = json.dumps(
        {
            "decision": "select",
            "selected_alpha_id": "A999",
            "hidden_reasoning": "provider-private-text",
        }
    )
    gateway = _gateway(tmp_path, _SequenceModel([invalid, invalid]))
    record = _record(
        "AI demand is strong, but rich valuation creates downside risk.",
        ["AI Demand", "Valuation Risk"],
    )

    result = map_claim_to_alpha(record, llm_gateway=gateway)

    assert result["match_status"] == "ambiguous"
    assert result["classifier"]["status"] == "fallback"
    assert "provider-private-text" not in json.dumps(result)
    assert "A999" not in json.dumps(result)


def test_structure_extractor_uses_validated_llm_edge(tmp_path):
    response = {
        "edges": [
            {
                "source_factor": "AI Demand",
                "target_factor": "GPU Demand",
                "edge_type": "causal",
                "assertion_status": "asserted",
                "confidence": 0.91,
            }
        ]
    }
    gateway = _gateway(tmp_path, _SequenceModel([json.dumps(response)]), max_retries=0)

    payload = extract_structures_from_records(
        [_record("AI demand drives GPU demand.", ["AI Demand", "GPU Demand"])],
        llm_gateway=gateway,
    )

    assert len(payload["edges"]) == 1
    assert payload["edges"][0]["extraction_method"] == "llm_strict_json"
    assert payload["edges"][0]["evidence"] == "AI demand drives GPU demand."


def test_structure_extractor_invalid_llm_edge_uses_deterministic_fallback(tmp_path):
    invalid = json.dumps(
        {
            "edges": [
                {
                    "source_factor": "Invented Factor",
                    "target_factor": "GPU Demand",
                    "edge_type": "causal",
                    "assertion_status": "asserted",
                    "confidence": 0.9,
                }
            ]
        }
    )
    gateway = _gateway(tmp_path, _SequenceModel([invalid, invalid]))

    payload = extract_structures_from_records(
        [_record("AI demand drives GPU demand.", ["AI Demand", "GPU Demand"])],
        llm_gateway=gateway,
    )

    assert len(payload["edges"]) == 1
    assert payload["edges"][0]["extraction_method"] == "deterministic_rules"
    assert payload["metadata"]["deterministic_edge_count"] == 1


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("COMQUTOR_RUN_WEEK2_PROVIDER_SMOKE") != "1",
    reason="set COMQUTOR_RUN_WEEK2_PROVIDER_SMOKE=1 to allow three provider calls",
)
def test_explicit_low_cost_provider_smoke(tmp_path, monkeypatch):
    """Exercise the three Week 2 LLM tasks with a three-call hard limit."""
    load_dotenv()
    from tradingagents.llm_clients.api_key_env import get_api_key_env

    provider = (
        os.getenv("COMQUTOR_WEEK2_LLM_PROVIDER")
        or os.getenv("TRADINGAGENTS_LLM_PROVIDER")
        or ""
    ).strip()
    model = (
        os.getenv("COMQUTOR_WEEK2_LLM_MODEL")
        or os.getenv("TRADINGAGENTS_QUICK_THINK_LLM")
        or ""
    ).strip()
    key_env = get_api_key_env(provider)
    if not provider or not model or not key_env or not os.getenv(key_env):
        pytest.skip("configured API-key-backed provider credentials are unavailable")

    run_id = "provider-smoke"
    (tmp_path / run_id).mkdir()
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "1")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MAX_RETRIES", "0")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MAX_CALLS", "3")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS", "30")
    gateway = build_server_week2_llm_gateway(run_id, tmp_path)
    assert gateway is not None

    raw_text = "AI demand is rising because GPU demand is increasing."
    records = adapt_raw_agent_outputs(
        {
            "agent_output_id": f"{run_id}:news_agent:news_report",
            "agent": "news_agent",
            "raw_output": raw_text,
        },
        run_id,
        "NVDA",
        llm_gateway=gateway,
    )
    assert records and records[0]["extraction_method"] == "llm_strict_json"

    classification = map_claim_to_alpha(
        _record(
            "AI demand is strong, but rich valuation creates downside risk.",
            ["AI Demand", "Valuation Risk"],
        ),
        llm_gateway=gateway,
    )
    assert classification["classifier"]["used"] is True
    assert classification["match_status"] == "ambiguous" or (
        classification["match_status"] == "matched"
        and classification["matched_alpha"] in classification["plausible_alphas"]
    )

    structures = extract_structures_from_records(
        [_record("AI demand drives GPU demand.", ["AI Demand", "GPU Demand"])],
        llm_gateway=gateway,
    )
    assert structures["metadata"]["llm_edge_count"] >= 1
    assert gateway.call_count == 3
