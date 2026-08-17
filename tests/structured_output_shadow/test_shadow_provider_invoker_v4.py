"""Phase 1 Master evidence-alignment fix, round 2: Week2GatewaySemanticInvokerV4 /
run_real_provider_shadow_smoke_for_report_v4 -- the real-Gateway wiring that
lets scripts/run_phase1_master.py actually send the v4 markdown-formatting-
fidelity request. Mirrors test_shadow_provider_invoker_v3.py's coverage.
FakeModel only; never a real Provider, never real network access.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from comqutor_alpha.llm_runtime.cache import NullLLMResponseCache
from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
from comqutor_alpha.structure_engine.structured_output_shadow_provider import (
    Week2GatewaySemanticInvokerV4,
    run_real_provider_shadow_smoke_for_report_v4,
)
from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

REPORT = "**Datacenter capex rose sharply in Q2.** Inference demand also increased."


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


def _valid_v4_proposal() -> dict[str, Any]:
    quote = "**Datacenter capex rose sharply in Q2.**"
    return {
        "claims": [
            {
                "claim": "Datacenter capex rose sharply in Q2.",
                "supporting_quotes": [quote],
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


def test_accepted_v4_output_with_preserved_markdown_flows_to_canonical_bundle(tmp_path):
    session = SemanticRuntimeSession(
        run_id="phase1-master-v4-test",
        output_directory=tmp_path,
        execution_mode="shadow",
        provider="fake-provider",
        model="fake-model",
        cache=NullLLMResponseCache(),
    )
    model = FakeModel([_content(_valid_v4_proposal())])
    gateway = _gateway(model, session, tmp_path)
    bundle, invoker, candidates, resolution_log = run_real_provider_shadow_smoke_for_report_v4(
        gateway=gateway,
        source_report=REPORT,
        run_id="phase1-master-v4-test",
        ticker="NVDA",
        agent="fundamental_agent",
        agent_output_id="run-x:fundamental_agent:fundamentals_report",
        factor_vocabulary=[],
    )
    session.finalize_manifest(complete=True)
    assert bundle["schema_version"] == "comqutor.structured_claim_shadow.v1"
    assert bundle["prompt_version"] == "structured_adapter.claim_extraction_shadow.v4"
    assert bundle["validation_summary"]["valid"] is True
    assert bundle["claims"][0]["evidence"] == "**Datacenter capex rose sharply in Q2.**"
    assert invoker.last_invocation.provider_status == "success"
    assert candidates
    assert resolution_log == [
        {"claim_index": 0, "quote_index": 0, "status": "UNIQUE_EXACT_MATCH", "match_count": 1}
    ]


def test_malformed_json_never_crashes_and_produces_failsoft_bundle(tmp_path):
    session = SemanticRuntimeSession(
        run_id="phase1-master-v4-test-2",
        output_directory=tmp_path,
        execution_mode="shadow",
        provider="fake-provider",
        model="fake-model",
        cache=NullLLMResponseCache(),
    )
    model = FakeModel([SimpleNamespace(content="not json{{{")])
    gateway = _gateway(model, session, tmp_path, max_retries=0)
    bundle, invoker, _candidates, resolution_log = run_real_provider_shadow_smoke_for_report_v4(
        gateway=gateway,
        source_report=REPORT,
        run_id="phase1-master-v4-test-2",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id="run-x:news_agent:news_report",
        factor_vocabulary=[],
    )
    session.finalize_manifest(complete=True)
    assert bundle["claims"] == []
    assert bundle["shadow_only"] is True
    assert invoker.last_invocation.provider_status in {"provider_error", "timeout", "budget_exhausted"}
    assert resolution_log == []


def test_markdown_stripped_quote_still_rejected_through_real_gateway_path(tmp_path):
    """Confirms the fix is real end-to-end: even through the Gateway-level
    pre-validation closure (which only has offset hints, not full candidate
    metadata -- see Week2GatewaySemanticInvokerV3's docstring, reused
    unchanged by V4), a markdown-stripped quote is still rejected.

    Uses a report where ** wraps only PART of the intended quote span (the
    real v3 failure shape) -- a quote where ** happens to wrap its ENTIRE
    span would have its stripped inner text remain trivially a substring
    regardless, which would not exercise this rejection path at all."""

    partial_bold_report = (
        "**Datacenter capex rose sharply in Q2**, well above prior guidance. "
        "Inference demand also increased."
    )
    session = SemanticRuntimeSession(
        run_id="phase1-master-v4-test-3",
        output_directory=tmp_path,
        execution_mode="shadow",
        provider="fake-provider",
        model="fake-model",
        cache=NullLLMResponseCache(),
    )
    stripped_quote = "Datacenter capex rose sharply in Q2, well above prior guidance."
    assert stripped_quote not in partial_bold_report  # sanity: genuinely not a substring
    bad_payload = {
        "claims": [
            {
                "claim": "Datacenter capex rose sharply in Q2.",
                "supporting_quotes": [stripped_quote],
                "entities": [],
                "factors": [],
                "direction": "unknown",
                "confidence": 0.5,
            }
        ],
        "abstentions": [],
    }
    model = FakeModel([_content(bad_payload)])
    gateway = _gateway(model, session, tmp_path, max_retries=0)
    bundle, invoker, _candidates, resolution_log = run_real_provider_shadow_smoke_for_report_v4(
        gateway=gateway,
        source_report=partial_bold_report,
        run_id="phase1-master-v4-test-3",
        ticker="NVDA",
        agent="sentiment_agent",
        agent_output_id="run-x:sentiment_agent:sentiment_report",
        factor_vocabulary=[],
    )
    session.finalize_manifest(complete=True)
    assert bundle["claims"] == []
    assert bundle["validation_summary"]["valid"] is False
    assert invoker.last_invocation.validation_accepted is False
    assert resolution_log[0]["status"] == "NO_EXACT_MATCH"


def test_gateway_persists_exactly_one_semantic_call_record(tmp_path):
    session = SemanticRuntimeSession(
        run_id="phase1-master-v4-single-call",
        output_directory=tmp_path,
        execution_mode="shadow",
        provider="fake-provider",
        model="fake-model",
        cache=NullLLMResponseCache(),
    )
    model = FakeModel([_content(_valid_v4_proposal())])
    gateway = _gateway(model, session, tmp_path)
    run_real_provider_shadow_smoke_for_report_v4(
        gateway=gateway,
        source_report=REPORT,
        run_id="phase1-master-v4-single-call",
        ticker="NVDA",
        agent="market_agent",
        agent_output_id="run-x:market_agent:market_report",
        factor_vocabulary=[],
    )
    session.finalize_manifest(complete=True)
    records = session.recorder.read_all()
    assert len(records) == 1
    assert records[0]["prompt_version"] == "structured_adapter.claim_extraction_shadow.v4"


def test_invoker_is_semantic_invoker_protocol_instance():
    class _StubGateway:
        pass

    invoker = Week2GatewaySemanticInvokerV4(_StubGateway())
    assert hasattr(invoker, "invoke")
    assert invoker.last_invocation is None
