"""Phase 1 Master evidence-alignment fix: Week2GatewaySemanticInvokerV3 /
run_real_provider_shadow_smoke_for_report_v3 -- the real-Gateway wiring that
lets scripts/run_phase1_master.py actually send the v3 verbatim-quote
request and resolve responses deterministically.

All tests use a FakeModel (mimicking the LLM client's own ``.invoke(prompt)``
surface) -- never a real Provider, never real network access. Mirrors
test_shadow_provider_invoker_v2.py's coverage exactly.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from comqutor_alpha.llm_runtime.cache import NullLLMResponseCache
from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
from comqutor_alpha.structure_engine.structured_output_shadow_provider import (
    Week2GatewaySemanticInvokerV3,
    run_real_provider_shadow_smoke_for_report_v3,
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


def _valid_v3_proposal() -> dict[str, Any]:
    quote = "Datacenter capex rose sharply in Q2."
    return {
        "claims": [
            {
                "claim": quote,
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


def test_accepted_v3_output_flows_through_to_canonical_shadow_bundle(tmp_path):
    session = SemanticRuntimeSession(
        run_id="phase1-master-v3-test",
        output_directory=tmp_path,
        execution_mode="shadow",
        provider="fake-provider",
        model="fake-model",
        cache=NullLLMResponseCache(),
    )
    model = FakeModel([_content(_valid_v3_proposal())])
    gateway = _gateway(model, session, tmp_path)
    bundle, invoker, candidates, resolution_log = run_real_provider_shadow_smoke_for_report_v3(
        gateway=gateway,
        source_report=REPORT,
        run_id="phase1-master-v3-test",
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
    # The real request sent to the model must be the small v3 shape. The
    # OUTPUT SHAPE the fixed instruction asks the model to PRODUCE never
    # mentions start/end (only supporting_quotes) -- "start"/"end" still
    # legitimately appear elsewhere, inside the optional, caller-owned
    # candidate_hints the model may only READ, never write.
    assert len(model.prompts[0]) < 8000
    assert "claim_hint" not in model.prompts[0]
    output_shape_text = model.prompts[0].split("OUTPUT SHAPE", 1)[1].split("SYNTHETIC", 1)[0]
    assert "start" not in output_shape_text
    assert "end" not in output_shape_text
    assert "supporting_quotes" in output_shape_text
    assert candidates  # still persisted for audit, even though not sent to the Provider
    assert resolution_log == [
        {"claim_index": 0, "quote_index": 0, "status": "UNIQUE_EXACT_MATCH", "match_count": 1}
    ]


def test_malformed_json_never_crashes_and_produces_failsoft_bundle(tmp_path):
    session = SemanticRuntimeSession(
        run_id="phase1-master-v3-test-2",
        output_directory=tmp_path,
        execution_mode="shadow",
        provider="fake-provider",
        model="fake-model",
        cache=NullLLMResponseCache(),
    )
    model = FakeModel([SimpleNamespace(content="not json{{{")])
    gateway = _gateway(model, session, tmp_path, max_retries=0)
    bundle, invoker, _candidates, resolution_log = run_real_provider_shadow_smoke_for_report_v3(
        gateway=gateway,
        source_report=REPORT,
        run_id="phase1-master-v3-test-2",
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
    assert resolution_log == []


def test_v3_proposal_with_fabricated_quote_is_rejected_not_admitted(tmp_path):
    session = SemanticRuntimeSession(
        run_id="phase1-master-v3-test-3",
        output_directory=tmp_path,
        execution_mode="shadow",
        provider="fake-provider",
        model="fake-model",
        cache=NullLLMResponseCache(),
    )
    bad_payload = {
        "claims": [
            {
                "claim": "Datacenter capex rose sharply in Q2.",
                "supporting_quotes": ["Datacenter capex rose sharply in Q4, a fabricated claim."],
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
    bundle, invoker, _candidates, resolution_log = run_real_provider_shadow_smoke_for_report_v3(
        gateway=gateway,
        source_report=REPORT,
        run_id="phase1-master-v3-test-3",
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


def test_v3_proposal_missing_required_field_is_rejected_not_admitted(tmp_path):
    session = SemanticRuntimeSession(
        run_id="phase1-master-v3-test-4",
        output_directory=tmp_path,
        execution_mode="shadow",
        provider="fake-provider",
        model="fake-model",
        cache=NullLLMResponseCache(),
    )
    # Valid JSON, but a claim missing 'supporting_quotes' entirely.
    bad_payload = {
        "claims": [{"claim": "x", "entities": [], "factors": [], "direction": "unknown", "confidence": 0.5}],
        "abstentions": [],
    }
    model = FakeModel([_content(bad_payload)])
    gateway = _gateway(model, session, tmp_path, max_retries=0)
    bundle, invoker, _candidates, _resolution_log = run_real_provider_shadow_smoke_for_report_v3(
        gateway=gateway,
        source_report=REPORT,
        run_id="phase1-master-v3-test-4",
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
        run_id="phase1-master-v3-single-call",
        output_directory=tmp_path,
        execution_mode="shadow",
        provider="fake-provider",
        model="fake-model",
        cache=NullLLMResponseCache(),
    )
    model = FakeModel([_content(_valid_v3_proposal())])
    gateway = _gateway(model, session, tmp_path)
    run_real_provider_shadow_smoke_for_report_v3(
        gateway=gateway,
        source_report=REPORT,
        run_id="phase1-master-v3-single-call",
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
    assert record["prompt_version"] == "structured_adapter.claim_extraction_shadow.v3"
    assert record["raw_output_text"] is None
    assert record["raw_output_sha256"] is None


def test_invoker_is_semantic_invoker_protocol_instance():
    class _StubGateway:
        pass

    invoker = Week2GatewaySemanticInvokerV3(_StubGateway())
    assert hasattr(invoker, "invoke")
    assert invoker.last_invocation is None


def test_gateway_level_disambiguation_uses_only_the_wire_requests_own_hints(tmp_path):
    """A repeated sentence in the report, disambiguated via a candidate_ids
    reference the model itself supplied, must resolve identically at the
    Gateway pre-validation layer (which only has {id,start,end} hints, no
    real candidate_segment_id strings) and the authoritative parser layer
    (which has both) -- this proves the Gateway-level closure does not
    spuriously reject (and burn a retry) a genuinely resolvable disambiguated
    claim."""

    report = "Disclaimer text. Unrelated filler content in between. Disclaimer text."
    second_occurrence_start = report.rindex("Disclaimer text.")
    payload = {
        "claims": [
            {
                "claim": "Disclaimer applies to the report.",
                "supporting_quotes": ["Disclaimer text."],
                "entities": [],
                "factors": [],
                "direction": "unknown",
                "confidence": 0.5,
                "candidate_ids": [0],
            }
        ],
        "abstentions": [],
    }
    session = SemanticRuntimeSession(
        run_id="phase1-master-v3-disambiguation",
        output_directory=tmp_path,
        execution_mode="shadow",
        provider="fake-provider",
        model="fake-model",
        cache=NullLLMResponseCache(),
    )
    model = FakeModel([_content(payload)])
    gateway = _gateway(model, session, tmp_path)

    from comqutor_alpha.structure_engine.structured_output_shadow import build_candidate_segments

    candidate_segments, _filtered = build_candidate_segments(
        report, agent_output_id="run-x:fundamental_agent:fundamentals_report"
    )
    # Force candidate index 0's located span to the SECOND occurrence, so a
    # correct disambiguation must pick that one, not the first.
    if candidate_segments:
        candidate_segments[0] = dict(candidate_segments[0])
        candidate_segments[0]["candidate_index"] = 0
        candidate_segments[0]["source_spans"] = [
            {
                "start": second_occurrence_start,
                "end": second_occurrence_start + len("Disclaimer text."),
                "exact_quote": "Disclaimer text.",
            }
        ]

    from comqutor_alpha.structure_engine.structured_output_shadow_provider import (
        Week2GatewaySemanticInvokerV3,
    )
    from comqutor_alpha.structure_engine.structured_output_shadow_v3 import (
        StructuredOutputShadowParserV3,
    )

    invoker = Week2GatewaySemanticInvokerV3(gateway)
    parser = StructuredOutputShadowParserV3(invoker, factor_vocabulary=[])
    bundle = parser.parse_report_shadow_v3(
        source_report=report,
        run_id="phase1-master-v3-disambiguation",
        ticker="NVDA",
        agent="fundamental_agent",
        agent_output_id="run-x:fundamental_agent:fundamentals_report",
        candidate_segments=candidate_segments,
    )
    session.finalize_manifest(complete=True)
    # The Gateway-level closure must not have rejected this (which would
    # show up as a retry/second prompt attempt or a provider_error status).
    assert invoker.last_invocation.provider_status == "success"
    assert invoker.last_invocation.validation_accepted is True
    assert bundle["validation_summary"]["valid"] is True
    assert bundle["claims"][0]["source_spans"][0]["start"] == second_occurrence_start
