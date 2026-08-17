"""Phase 1B.1: Week2GatewaySemanticInvoker / build_real_provider_gateway.

All tests use a FakeModel (mimicking the LLM client's own ``.invoke(prompt)``
surface) -- never a real Provider, never real network access.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from comqutor_alpha.llm_runtime.cache import NullLLMResponseCache
from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
from comqutor_alpha.research_profiles import get_research_profile
from comqutor_alpha.structure_engine.structured_output_shadow_prompt import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
)
from comqutor_alpha.structure_engine.structured_output_shadow_provider import (
    SHADOW_WEEK2_ERROR_LOG_ARTIFACT_PATH,
    ProviderSmokeAuthorizationError,
    Week2GatewaySemanticInvoker,
    build_real_provider_gateway,
    run_real_provider_shadow_smoke_for_report,
)
from comqutor_alpha.structure_engine.structured_output_shadow_schema import sha256_text
from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway


class FakeModel:
    """Mimics the underlying LLM client object's ``.invoke(prompt)``."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> Any:
        self.prompts.append(prompt)
        if not self._responses:
            raise RuntimeError("FakeModel exhausted")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _content(payload: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(content=json.dumps(payload))


REPORT = "Datacenter capex rose sharply in Q2. Inference demand also increased."


def _valid_shadow_payload(agent_output_id: str, run_id: str) -> dict[str, Any]:
    return {
        "schema_version": "comqutor.structured_claim_shadow.v1",
        "run_id": run_id,
        "ticker": "NVDA",
        "agent": "fundamental_agent",
        "agent_output_id": agent_output_id,
        "source_report_sha256": sha256_text(REPORT),
        "prompt_version": STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
        "prompt_sha256": STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
        "claims": [
            {
                "shadow_claim_id": "",
                "claim": "Datacenter capex rose sharply in Q2.",
                "evidence": "Datacenter capex rose sharply in Q2.",
                "source_spans": [
                    {
                        "start": REPORT.index("Datacenter capex rose sharply in Q2."),
                        "end": REPORT.index("Datacenter capex rose sharply in Q2.")
                        + len("Datacenter capex rose sharply in Q2."),
                        "exact_quote": "Datacenter capex rose sharply in Q2.",
                    }
                ],
                "entities": [],
                "factors": [],
                "direction": "positive",
                "confidence": 0.7,
                "source_type": "unknown",
                "source_refs": [],
                "candidate_segment_ids": [],
                "extraction_status": "proposed",
            }
        ],
        "abstentions": [],
        "validation_summary": {},
        "shadow_only": True,
        "production_authority": False,
    }


@pytest.fixture
def semantic_session(tmp_path):
    session = SemanticRuntimeSession(
        run_id="phase1b1-test-run",
        output_directory=tmp_path,
        execution_mode="shadow",
        provider="fake-provider",
        model="fake-model",
        cache=NullLLMResponseCache(),
    )
    yield session
    session.finalize_manifest(complete=True)


def test_accepted_real_output_flows_through_to_shadow_bundle(semantic_session):
    agent_output_id = "run-x:fundamental_agent:fundamentals_report"
    payload = _valid_shadow_payload(agent_output_id, "phase1b1-test-run")
    model = FakeModel([_content(payload)])
    gateway = Week2LLMGateway(
        model,
        run_id="phase1b1-test-run",
        output_root=str(semantic_session.output_directory),
        provider="fake-provider",
        model_name="fake-model",
        semantic_runtime=semantic_session,
    )
    bundle, invoker, candidates = run_real_provider_shadow_smoke_for_report(
        gateway=gateway,
        source_report=REPORT,
        run_id="phase1b1-test-run",
        ticker="NVDA",
        agent="fundamental_agent",
        agent_output_id=agent_output_id,
        factor_vocabulary=[],
    )
    assert bundle["shadow_only"] is True
    assert bundle["production_authority"] is False
    assert bundle["validation_summary"]["valid"] is True
    assert invoker.last_invocation.provider_status == "success"
    assert invoker.last_invocation.validation_accepted is True
    assert len(model.prompts) == 1
    assert candidates is not None


def test_malformed_json_never_crashes_and_produces_failsoft_bundle(semantic_session):
    agent_output_id = "run-x:news_agent:news_report"
    model = FakeModel([SimpleNamespace(content="not json{{{")])
    gateway = Week2LLMGateway(
        model,
        run_id="phase1b1-test-run",
        output_root=str(semantic_session.output_directory),
        max_retries=0,
        provider="fake-provider",
        model_name="fake-model",
        semantic_runtime=semantic_session,
    )
    bundle, invoker, _candidates = run_real_provider_shadow_smoke_for_report(
        gateway=gateway,
        source_report=REPORT,
        run_id="phase1b1-test-run",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id=agent_output_id,
        factor_vocabulary=[],
    )
    assert bundle["claims"] == []
    assert bundle["shadow_only"] is True
    assert bundle["production_authority"] is False
    assert invoker.last_invocation.provider_status in {"provider_error", "timeout", "budget_exhausted"}


def test_schema_invalid_json_is_rejected_not_admitted(semantic_session):
    agent_output_id = "run-x:sentiment_agent:sentiment_report"
    # Valid JSON, but violates the Shadow schema (unapproved field).
    bad_payload = {"schema_version": "comqutor.structured_claim_shadow.v1", "bogus_field": True}
    model = FakeModel([_content(bad_payload)])
    gateway = Week2LLMGateway(
        model,
        run_id="phase1b1-test-run",
        output_root=str(semantic_session.output_directory),
        max_retries=0,
        provider="fake-provider",
        model_name="fake-model",
        semantic_runtime=semantic_session,
    )
    bundle, invoker, _candidates = run_real_provider_shadow_smoke_for_report(
        gateway=gateway,
        source_report=REPORT,
        run_id="phase1b1-test-run",
        ticker="NVDA",
        agent="sentiment_agent",
        agent_output_id=agent_output_id,
        factor_vocabulary=[],
    )
    assert bundle["claims"] == []
    assert bundle["validation_summary"]["valid"] is False
    assert invoker.last_invocation.validation_accepted is False


def test_gateway_persists_exactly_one_semantic_call_record(tmp_path):
    session = SemanticRuntimeSession(
        run_id="phase1b1-single-call",
        output_directory=tmp_path,
        execution_mode="shadow",
        provider="fake-provider",
        model="fake-model",
        cache=NullLLMResponseCache(),
    )
    agent_output_id = "run-x:market_agent:market_report"
    payload = _valid_shadow_payload(agent_output_id, "phase1b1-single-call")
    model = FakeModel([_content(payload)])
    gateway = Week2LLMGateway(
        model,
        run_id="phase1b1-single-call",
        output_root=str(tmp_path),
        provider="fake-provider",
        model_name="fake-model",
        semantic_runtime=session,
    )
    run_real_provider_shadow_smoke_for_report(
        gateway=gateway,
        source_report=REPORT,
        run_id="phase1b1-single-call",
        ticker="NVDA",
        agent="market_agent",
        agent_output_id=agent_output_id,
        factor_vocabulary=[],
    )
    session.finalize_manifest(complete=True)
    records = session.recorder.read_all()
    assert len(records) == 1
    record = records[0]
    assert record["task"] == "structured_claim_shadow"
    assert record["raw_output_text"] is None
    assert record["raw_output_sha256"] is None
    assert record["cache"]["hit"] is False


def test_build_real_provider_gateway_never_reads_week2_enabled_env(monkeypatch, tmp_path):
    # Even if the unrelated live-route flag is explicitly enabled (and even
    # if COMQUTOR_WEEK2_LLM_ENABLED is unset elsewhere), Phase 1B.1's gateway
    # construction must not be influenced by it -- it reads only the
    # explicit ResearchProfile, and never calls build_server_week2_llm_gateway.
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "true")
    profile = get_research_profile("comqutor_deepseek_default_v1")

    def _boom(*_args, **_kwargs):
        raise AssertionError("build_server_week2_llm_gateway must never be called by Phase 1B.1")

    monkeypatch.setattr(
        "comqutor_alpha.structure_engine.week2_llm.build_server_week2_llm_gateway", _boom
    )
    fake_model = FakeModel([])
    monkeypatch.setattr(
        "tradingagents.llm_clients.create_llm_client",
        lambda **_kwargs: SimpleNamespace(get_llm=lambda: fake_model),
    )
    gateway, info = build_real_provider_gateway(
        profile=profile,
        run_id="phase1b1-env-independence",
        output_root=str(tmp_path),
        logical_call_limit=4,
    )
    assert info.provider == profile.llm_provider
    assert info.model == profile.quick_think_llm
    assert info.max_provider_attempts == 8  # 4 * (1 + DEFAULT_MAX_RETRIES=1)
    assert gateway.provider == profile.llm_provider
    assert gateway.error_log_artifact_path == SHADOW_WEEK2_ERROR_LOG_ARTIFACT_PATH


def test_logical_call_limit_bounds_derived_max_provider_attempts(tmp_path, monkeypatch):
    profile = get_research_profile("comqutor_deepseek_default_v1")
    with pytest.raises(ProviderSmokeAuthorizationError):
        build_real_provider_gateway(
            profile=profile,
            run_id="r",
            output_root=str(tmp_path),
            logical_call_limit=5,
        )
    with pytest.raises(ProviderSmokeAuthorizationError):
        build_real_provider_gateway(
            profile=profile,
            run_id="r",
            output_root=str(tmp_path),
            logical_call_limit=0,
        )


def test_invoker_is_semantic_invoker_protocol_instance():
    class _StubGateway:
        pass

    invoker = Week2GatewaySemanticInvoker(_StubGateway())
    assert hasattr(invoker, "invoke")
    assert invoker.last_invocation is None
