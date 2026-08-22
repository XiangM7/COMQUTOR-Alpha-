from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from comqutor_alpha.llm_runtime.canonical_json import sha256_canonical_json
from comqutor_alpha.llm_runtime.recorder import SemanticCallRecorder
from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
from comqutor_alpha.structure_engine import structured_output_adapter
from comqutor_alpha.structure_engine.alpha_mapper import map_claim_to_alpha
from comqutor_alpha.structure_engine.structure_extractor import extract_structures_from_records
from comqutor_alpha.structure_engine.structured_output_adapter import adapt_raw_agent_outputs
from comqutor_alpha.structure_engine.week2_llm import (
    DEFAULT_MAX_CALLS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    Week2LLMGateway,
)
from tests.llm_runtime.fakes import InMemoryFakeCache


class _Response:
    def __init__(self, content):
        self.content = content


class _SequenceModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        response = self.responses[self.calls]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        if callable(response):
            response = response()
        return _Response(response)


def _runtime_gateway(
    tmp_path: Path,
    model,
    *,
    cache=None,
    max_retries=0,
    max_calls=16,
    recorder=None,
):
    run_dir = tmp_path / "run-semantic"
    run_dir.mkdir(parents=True, exist_ok=True)
    session = SemanticRuntimeSession(
        run_id="run-semantic",
        output_directory=run_dir,
        execution_mode="test",
        provider="fake-provider",
        model="fake-model",
        cache=cache,
        recorder=recorder,
    )
    gateway = Week2LLMGateway(
        model,
        run_id="run-semantic",
        output_root=tmp_path,
        timeout_seconds=0.03,
        max_retries=max_retries,
        max_calls=max_calls,
        provider="fake-provider",
        model_name="fake-model",
        semantic_runtime=session,
    )
    return gateway, session


def _raw_record(text="AI demand drives GPU demand."):
    raw_id = "run-semantic:news_agent:news_report"
    return {
        "agent_output_id": raw_id,
        "agent": "news_agent",
        "raw_output": text,
    }


def _claim_record(text="AI demand drives GPU demand.", factors=None):
    raw_id = "run-semantic:news_agent:news_report"
    return {
        "run_id": "run-semantic",
        "ticker": "NVDA",
        "agent": "news_agent",
        "claim_id": f"{raw_id}:claim:1",
        "agent_output_id": f"{raw_id}:claim:1",
        "source_agent_output_id": raw_id,
        "claim": text,
        "evidence": text,
        "factors": factors or ["AI Demand", "GPU Demand"],
        "direction": "neutral",
        "confidence": 0.8,
    }


def _enrichment(text="AI demand drives GPU demand."):
    return {
        "claims": [
            {
                "segment_id": "run-semantic:news_agent:news_report:segment:0",
                "claim": text,
                "evidence": text,
                "source_section": None,
                "entities": ["AI", "GPU"],
                "factors": ["AI Demand", "GPU Demand"],
                "direction": "positive",
                "confidence": 0.9,
            }
        ]
    }


def _edge_response():
    return {
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


def test_legacy_prompt_payload_api_and_defaults_are_byte_compatible(tmp_path: Path) -> None:
    model = _SequenceModel(['{"decision":"none","selected_alpha_id":null}'])
    (tmp_path / "legacy").mkdir()
    gateway = Week2LLMGateway(model, run_id="legacy", output_root=tmp_path)
    payload = {"allowed_alpha_ids": ["A101"], "claim": "增长"}

    result = gateway.invoke_json("alpha_classifier", payload, lambda value: dict(value))

    instruction = (
        "Classify the Evidence against the FULL supplied Alpha taxonomy (alpha_taxonomy) -- every "
        "canonical Alpha is a legitimate candidate, none has been pre-filtered or pre-admitted by "
        "any other program logic. Select the single Alpha whose core thesis and causal/economic "
        "mechanism the Evidence most directly and substantively supports or opposes -- never an "
        "Alpha that merely shares surface words or a topic with the Evidence. Several Alphas can "
        "share overlapping keywords (for example AI capex, GPU demand, or data center activity can "
        "each relate to more than one Alpha); when more than one Alpha looks plausible, compare "
        "them directly against each other and select whichever one's own stated mechanism the "
        "Evidence engages with more closely and substantively -- never by keyword overlap alone, "
        "and never by declining to choose merely because the comparison is close. A difficult or "
        "close classification is still a classification task: decision=none is not a way to avoid "
        "choosing between two or more plausible Alphas. For example, if both A101 and A103 seem "
        "plausible, deciding decision=none because 'both are plausible' is WRONG; if A103 is the "
        "closer, more substantive fit, the required answer is decision=select with "
        "selected_alpha_id=A103. Use decision=none with selected_alpha_id=null only when no single "
        "canonical Alpha materially fits the Evidence at all -- when the Evidence does not "
        "substantively engage any Alpha's thesis, or is generic or background market commentary "
        "with no specific Alpha-relevant mechanism. Judge only from the claim, the evidence, and "
        "each Alpha's own definition. Return one JSON object with decision set to select or none "
        "and selected_alpha_id set to exactly one alpha_id from the supplied alpha_taxonomy when "
        "decision is select, or null when decision is none. Never invent an Alpha ID that is not "
        "in the supplied taxonomy, never select more than one Alpha, and never provide a trading "
        "decision or recommendation."
    )
    expected_prompt = (
        "You are a constrained COMQUTOR extraction component. Return strict JSON only, with "
        "no markdown and no hidden reasoning. "
        f"{instruction}\nINPUT_JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False, default=str)}"
    )
    assert result == {"decision": "none", "selected_alpha_id": None}
    assert model.prompts == [expected_prompt]
    assert gateway.semantic_runtime is None
    assert gateway.timeout_seconds == DEFAULT_TIMEOUT_SECONDS
    assert gateway.max_retries == DEFAULT_MAX_RETRIES
    assert gateway.max_calls == DEFAULT_MAX_CALLS


def test_three_real_callers_persist_accepted_outputs_in_one_session(tmp_path: Path) -> None:
    cache = InMemoryFakeCache()
    model = _SequenceModel(
        [
            json.dumps(_enrichment()),
            json.dumps({"decision": "select", "selected_alpha_id": "A101"}),
            json.dumps(_edge_response()),
        ]
    )
    gateway, session = _runtime_gateway(tmp_path, model, cache=cache)

    claims = adapt_raw_agent_outputs(
        _raw_record(),
        "run-semantic",
        "NVDA",
        llm_gateway=gateway,
    )
    mapped = map_claim_to_alpha(
        _claim_record(
            "AI training demand is rising, but rich valuation creates downside risk.",
            ["AI Demand", "Valuation Risk"],
        ),
        llm_gateway=gateway,
    )
    structures = extract_structures_from_records(
        [_claim_record()],
        llm_gateway=gateway,
    )
    manifest_path = session.finalize_manifest(complete=True)

    assert claims[0]["extraction_method"] == "llm_strict_json"
    assert mapped["matched_alpha"] == "A101"
    assert structures["edges"][0]["extraction_method"] == "llm_strict_json"
    records = session.recorder.read_all()
    assert [record["call_sequence"] for record in records] == [0, 1, 2]
    assert {record["task"] for record in records} == {
        "structured_adapter",
        "alpha_classifier",
        "structure_extractor",
    }
    assert all(record["validation_status"] == "accepted" for record in records)
    assert all(record["raw_output_text"] is None for record in records)
    assert len(cache.values) == 3
    manifest = json.loads(manifest_path.read_text())
    assert manifest["record_count"] == 3
    assert manifest["provider_call_count"] == 3
    assert manifest["exact_replay_ready"] is True


def test_three_real_callers_preserve_fallbacks_and_never_cache_rejections(
    tmp_path: Path,
) -> None:
    invalid_enrichment = _enrichment()
    invalid_enrichment["claims"][0]["confidence"] = 4
    invalid_edge = _edge_response()
    invalid_edge["edges"][0]["source_factor"] = "Invented Factor"
    model = _SequenceModel(
        [
            json.dumps(invalid_enrichment),
            json.dumps({"decision": "select", "selected_alpha_id": "A999"}),
            json.dumps(invalid_edge),
        ]
    )
    cache = InMemoryFakeCache()
    gateway, session = _runtime_gateway(tmp_path, model, cache=cache)

    claims = adapt_raw_agent_outputs(
        _raw_record(),
        "run-semantic",
        "NVDA",
        llm_gateway=gateway,
    )
    mapped = map_claim_to_alpha(
        _claim_record(
            "AI training demand is rising, but rich valuation creates downside risk.",
            ["AI Demand", "Valuation Risk"],
        ),
        llm_gateway=gateway,
    )
    structures = extract_structures_from_records(
        [_claim_record()],
        llm_gateway=gateway,
    )
    manifest_path = session.finalize_manifest(complete=True)

    assert claims[0]["extraction_method"] == "deterministic_splitter"
    # A999 is rejected by the wire validator (outside the canonical
    # taxonomy) -- Pure-LLM Alpha semantic authority reports this as an
    # operational failure (invalid_output), never a deterministic fallback.
    assert mapped["classifier"]["status"] == "invalid_output"
    assert mapped["match_status"] == "unavailable"
    assert mapped["matched_alpha"] is None
    assert structures["edges"][0]["extraction_method"] == "deterministic_rules"
    records = session.recorder.read_all()
    assert len(records) == 3
    assert all(record["validation_status"] == "rejected" for record in records)
    assert all(record["fallback_used"] is True for record in records)
    assert cache.values == {}
    assert json.loads(manifest_path.read_text())["exact_replay_ready"] is False


def test_cache_hit_reexecutes_real_task_validator_without_provider_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _SequenceModel([json.dumps(_enrichment())])
    cache = InMemoryFakeCache()
    gateway, session = _runtime_gateway(tmp_path, model, cache=cache)
    real_validator = structured_output_adapter._validate_llm_batch_enrichment
    validator_calls = 0

    def counting_validator(payload, segments):
        nonlocal validator_calls
        validator_calls += 1
        return real_validator(payload, segments)

    monkeypatch.setattr(
        structured_output_adapter,
        "_validate_llm_batch_enrichment",
        counting_validator,
    )

    first = adapt_raw_agent_outputs(
        _raw_record(), "run-semantic", "NVDA", llm_gateway=gateway
    )
    second = adapt_raw_agent_outputs(
        _raw_record(), "run-semantic", "NVDA", llm_gateway=gateway
    )

    assert first == second
    assert validator_calls == 2
    assert model.calls == 1
    assert gateway.call_count == 1
    records = session.recorder.read_all()
    assert records[1]["cache"]["hit"] is True
    assert records[1]["provider_status"] == "not_called"


def test_invalid_cache_candidate_is_revalidated_then_treated_as_provider_miss(
    tmp_path: Path,
) -> None:
    cache = InMemoryFakeCache()
    model = _SequenceModel([json.dumps({"decision": "none", "selected_alpha_id": None})])
    gateway, session = _runtime_gateway(tmp_path, model, cache=cache)
    payload = {"allowed_alpha_ids": ["A101"]}
    seeded = session.start_call(
        task="alpha_classifier",
        prompt_version="week2.alpha_classifier.v3",
        prompt_sha256=gateway.prompt_identity_sha256("alpha_classifier"),
        input_schema_version="week2.alpha_classifier.input.v2",
        output_schema_version="week2.alpha_classifier.output.v2",
        taxonomy_version="alpha_taxonomy_v1",
        input_payload=payload,
    )
    trace = seeded.trace_handle
    cache.values[trace.cache_key] = {
        "schema_version": "comqutor.llm_cache_entry.v1",
        "cache_key": trace.cache_key,
        "task": trace.task,
        "prompt_sha256": trace.prompt_sha256,
        "input_sha256": trace.input_sha256,
        "provider": session.provider,
        "model": session.model,
        "output_schema_version": trace.output_schema_version,
        "validated_output": {"bad": "candidate"},
        "validated_output_sha256": sha256_canonical_json({"bad": "candidate"}),
        "created_at": "2026-08-05T00:00:00+00:00",
        "expires_at": None,
    }
    validations = 0

    def validator(candidate):
        nonlocal validations
        validations += 1
        if set(candidate) != {"decision", "selected_alpha_id"}:
            raise ValueError("bad candidate")
        return dict(candidate)

    invocation = gateway.invoke_json_with_trace("alpha_classifier", payload, validator)
    gateway.finalize_semantic_invocation(invocation, accepted=True)

    assert validations == 2
    assert model.calls == 1
    assert invocation.cache_hit is False
    assert invocation.validation_accepted is True
    assert invocation.cache_error_code == "WEEK2_LLM_CACHE_VALIDATION_FAILED"
    assert "WEEK2_LLM_CACHE_VALIDATION_FAILED" in session.degraded_reason_codes
    assert session.recorder.read_all()[0]["cache"]["hit"] is False


@pytest.mark.parametrize(
    ("response", "provider_status", "error_code"),
    [
        (RuntimeError("provider failed"), "provider_error", "WEEK2_LLM_PROVIDER_ERROR"),
        ("not-json", "provider_error", "WEEK2_LLM_INVALID_JSON"),
    ],
)
def test_provider_failure_records_fallback_without_cache(
    tmp_path: Path,
    response,
    provider_status: str,
    error_code: str,
) -> None:
    cache = InMemoryFakeCache()
    gateway, session = _runtime_gateway(tmp_path, _SequenceModel([response]), cache=cache)
    invocation = gateway.invoke_json_with_trace("alpha_classifier", {}, lambda value: value)
    gateway.finalize_semantic_invocation(invocation, accepted=False)

    record = session.recorder.read_all()[0]
    assert record["provider_status"] == provider_status
    assert record["error_code"] == error_code
    assert record["fallback_used"] is True
    assert cache.values == {}


def test_timeout_and_fresh_budget_exhaustion_are_audited(tmp_path: Path) -> None:
    def slow_response():
        time.sleep(0.1)
        return "{}"

    timeout_gateway, timeout_session = _runtime_gateway(
        tmp_path / "timeout",
        _SequenceModel([slow_response]),
    )
    timeout_call = timeout_gateway.invoke_json_with_trace(
        "alpha_classifier", {}, lambda value: value
    )
    timeout_gateway.finalize_semantic_invocation(timeout_call, accepted=False)
    assert timeout_session.recorder.read_all()[0]["provider_status"] == "timeout"

    budget_gateway, budget_session = _runtime_gateway(
        tmp_path / "budget",
        _SequenceModel([]),
        max_calls=1,
    )
    budget_gateway._call_count = 1
    budget_call = budget_gateway.invoke_json_with_trace(
        "alpha_classifier", {}, lambda value: value
    )
    budget_gateway.finalize_semantic_invocation(budget_call, accepted=False)
    record = budget_session.recorder.read_all()[0]
    assert record["provider_status"] == "budget_exhausted"
    assert record["error_code"] == "WEEK2_LLM_CALL_BUDGET_EXHAUSTED"
    assert budget_gateway.call_count == 1


class _FailingRecorder(SemanticCallRecorder):
    def append(self, record) -> None:
        del record
        raise OSError("synthetic disk failure")


def test_recorder_failure_does_not_change_caller_result_or_repeat_provider(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run-semantic"
    run_dir.mkdir()
    recorder = _FailingRecorder(
        run_id="run-semantic",
        output_directory=run_dir,
        mode="test",
    )
    model = _SequenceModel([json.dumps(_enrichment())])
    gateway, session = _runtime_gateway(tmp_path, model, recorder=recorder)

    claims = adapt_raw_agent_outputs(
        _raw_record(), "run-semantic", "NVDA", llm_gateway=gateway
    )

    assert claims[0]["extraction_method"] == "llm_strict_json"
    assert model.calls == 1
    assert session.incomplete is True
    assert "SEMANTIC_RECORDER_APPEND_FAILED" in session.degraded_reason_codes
