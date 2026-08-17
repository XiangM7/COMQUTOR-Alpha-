"""Phase 1 Master prompt-size fix: Week2GatewaySemanticInvokerV2 /
run_real_provider_shadow_smoke_for_report_v2 -- the real-Gateway wiring that
lets scripts/run_phase1_master.py actually send the v2 minimal request.

All tests use a FakeModel (mimicking the LLM client's own ``.invoke(prompt)``
surface) -- never a real Provider, never real network access. Mirrors
test_shadow_provider_invoker.py's v1 coverage exactly.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from comqutor_alpha.llm_runtime.cache import NullLLMResponseCache
from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
from comqutor_alpha.structure_engine.structured_output_shadow_provider import (
    Week2GatewaySemanticInvokerV2,
    run_real_provider_shadow_smoke_for_report_v2,
)
from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

REPORT = "Datacenter capex rose sharply in Q2. Inference demand also increased."


class FakeModel:
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


def _valid_v2_proposal() -> dict[str, Any]:
    quote = "Datacenter capex rose sharply in Q2."
    start = REPORT.index(quote)
    return {
        "claims": [
            {
                "claim": quote,
                "source_spans": [{"start": start, "end": start + len(quote)}],
                "entities": [],
                "factors": [],
                "direction": "positive",
                "confidence": 0.7,
            }
        ],
        "abstentions": [],
    }


def _gateway(model: FakeModel, session: SemanticRuntimeSession, output_root, **kwargs) -> Week2LLMGateway:
    return Week2LLMGateway(
        model,
        run_id=session.run_id,
        output_root=str(output_root),
        provider="fake-provider",
        model_name="fake-model",
        semantic_runtime=session,
        **kwargs,
    )


def test_accepted_v2_output_flows_through_to_canonical_shadow_bundle(tmp_path):
    session = SemanticRuntimeSession(
        run_id="phase1-master-v2-test",
        output_directory=tmp_path,
        execution_mode="shadow",
        provider="fake-provider",
        model="fake-model",
        cache=NullLLMResponseCache(),
    )
    model = FakeModel([_content(_valid_v2_proposal())])
    gateway = _gateway(model, session, tmp_path)
    bundle, invoker, candidates = run_real_provider_shadow_smoke_for_report_v2(
        gateway=gateway,
        source_report=REPORT,
        run_id="phase1-master-v2-test",
        ticker="NVDA",
        agent="fundamental_agent",
        agent_output_id="run-x:fundamental_agent:fundamentals_report",
        factor_vocabulary=[],
    )
    session.finalize_manifest(complete=True)
    assert bundle["schema_version"] == "comqutor.structured_claim_shadow.v1"
    assert bundle["shadow_only"] is True
    assert bundle["production_authority"] is False
    assert bundle["validation_summary"]["valid"] is True
    assert bundle["claims"][0]["claim"] == "Datacenter capex rose sharply in Q2."
    assert bundle["claims"][0]["evidence"] == "Datacenter capex rose sharply in Q2."
    assert invoker.last_invocation.provider_status == "success"
    assert invoker.last_invocation.validation_accepted is True
    assert len(model.prompts) == 1
    # The real request sent to the model must be the small v2 shape.
    assert len(model.prompts[0]) < 5000
    assert "claim_hint" not in model.prompts[0]
    assert candidates  # still persisted for audit, even though not sent to the Provider


def test_malformed_json_never_crashes_and_produces_failsoft_bundle(tmp_path):
    session = SemanticRuntimeSession(
        run_id="phase1-master-v2-test-2",
        output_directory=tmp_path,
        execution_mode="shadow",
        provider="fake-provider",
        model="fake-model",
        cache=NullLLMResponseCache(),
    )
    model = FakeModel([SimpleNamespace(content="not json{{{")])
    gateway = _gateway(model, session, tmp_path, max_retries=0)
    bundle, invoker, _candidates = run_real_provider_shadow_smoke_for_report_v2(
        gateway=gateway,
        source_report=REPORT,
        run_id="phase1-master-v2-test-2",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id="run-x:news_agent:news_report",
        factor_vocabulary=[],
    )
    session.finalize_manifest(complete=True)
    assert bundle["claims"] == []
    assert bundle["shadow_only"] is True
    assert bundle["production_authority"] is False
    assert invoker.last_invocation.provider_status in {"provider_error", "timeout", "budget_exhausted"}


def test_v2_proposal_missing_required_field_is_rejected_not_admitted(tmp_path):
    session = SemanticRuntimeSession(
        run_id="phase1-master-v2-test-3",
        output_directory=tmp_path,
        execution_mode="shadow",
        provider="fake-provider",
        model="fake-model",
        cache=NullLLMResponseCache(),
    )
    # Valid JSON, but a claim missing 'source_spans' entirely.
    bad_payload = {"claims": [{"claim": "x", "entities": [], "factors": [], "direction": "unknown", "confidence": 0.5}], "abstentions": []}
    model = FakeModel([_content(bad_payload)])
    gateway = _gateway(model, session, tmp_path, max_retries=0)
    bundle, invoker, _candidates = run_real_provider_shadow_smoke_for_report_v2(
        gateway=gateway,
        source_report=REPORT,
        run_id="phase1-master-v2-test-3",
        ticker="NVDA",
        agent="sentiment_agent",
        agent_output_id="run-x:sentiment_agent:sentiment_report",
        factor_vocabulary=[],
    )
    session.finalize_manifest(complete=True)
    assert bundle["claims"] == []
    assert bundle["validation_summary"]["valid"] is False
    assert invoker.last_invocation.validation_accepted is False


def test_gateway_persists_exactly_one_semantic_call_record(tmp_path):
    session = SemanticRuntimeSession(
        run_id="phase1-master-v2-single-call",
        output_directory=tmp_path,
        execution_mode="shadow",
        provider="fake-provider",
        model="fake-model",
        cache=NullLLMResponseCache(),
    )
    model = FakeModel([_content(_valid_v2_proposal())])
    gateway = _gateway(model, session, tmp_path)
    run_real_provider_shadow_smoke_for_report_v2(
        gateway=gateway,
        source_report=REPORT,
        run_id="phase1-master-v2-single-call",
        ticker="NVDA",
        agent="market_agent",
        agent_output_id="run-x:market_agent:market_report",
        factor_vocabulary=[],
    )
    session.finalize_manifest(complete=True)
    records = session.recorder.read_all()
    assert len(records) == 1
    record = records[0]
    assert record["task"] == "structured_claim_shadow"
    assert record["prompt_version"] == "structured_adapter.claim_extraction_shadow.v2"
    assert record["raw_output_text"] is None
    assert record["raw_output_sha256"] is None


def test_invoker_is_semantic_invoker_protocol_instance():
    class _StubGateway:
        pass

    invoker = Week2GatewaySemanticInvokerV2(_StubGateway())
    assert hasattr(invoker, "invoke")
    assert invoker.last_invocation is None
