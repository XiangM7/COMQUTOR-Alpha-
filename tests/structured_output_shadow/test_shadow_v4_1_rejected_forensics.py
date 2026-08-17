"""Offline rejected-candidate persistence and replay tests for v4.1."""

from __future__ import annotations

import json
from types import SimpleNamespace

from comqutor_alpha.llm_runtime.cache import NullLLMResponseCache
from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
from comqutor_alpha.structure_engine.structured_output_shadow import (
    build_candidate_segments,
)
from comqutor_alpha.structure_engine.structured_output_shadow_provider import (
    run_real_provider_shadow_smoke_for_report_v4_1,
)
from comqutor_alpha.structure_engine.structured_output_shadow_v4_1 import (
    StructuredOutputShadowParserV4_1,
    build_rejected_forensic_record_v4_1,
    replay_rejected_forensic_record_v4_1,
)
from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

QUOTE = "Demand increased 20%."
REPORT = f"{QUOTE} {QUOTE}"
RUN_ID = "v4-1-rejected-forensics"
AGENT_OUTPUT_ID = f"{RUN_ID}:news_agent:news_report"


def _rejected_proposal(candidate_id=None) -> dict:
    return {
        "claims": [
            {
                "claim": "Demand increased 20%.",
                "supporting_evidence": [
                    {"quote": QUOTE, "candidate_id": candidate_id}
                ],
                "entities": [],
                "factors": [],
                "direction": "positive",
                "confidence": 0.8,
                "commentary": "arbitrary provider prose must not persist",
            }
        ],
        "abstentions": [],
        "hidden_reasoning": "must never persist",
    }


def test_rejected_candidate_forensics_are_bounded_and_provider_zero_replayable():
    candidates, _ = build_candidate_segments(REPORT, agent_output_id=AGENT_OUTPUT_ID)
    selected_id = candidates[0]["candidate_segment_id"]
    parser = StructuredOutputShadowParserV4_1(
        lambda **_kwargs: _rejected_proposal(selected_id), factor_vocabulary=[]
    )
    bundle = parser.parse_report_shadow_v4_1(
        source_report=REPORT,
        run_id=RUN_ID,
        ticker="TEST",
        agent="news_agent",
        agent_output_id=AGENT_OUTPUT_ID,
        candidate_segments=candidates,
    )
    forensic = build_rejected_forensic_record_v4_1(
        parser=parser,
        bundle=bundle,
        provider="offline-fixture",
        model="fixture-model",
        semantic_call_id="call-fixture",
    )

    assert bundle["claims"] == []
    assert bundle["validation_summary"]["valid"] is False
    assert forensic is not None
    assert forensic["non_authoritative"] is True
    assert forensic["forensic_only"] is True
    assert forensic["admitted_claim_count"] == 0
    persisted = json.dumps(forensic)
    assert "arbitrary provider prose" not in persisted
    assert "must never persist" not in persisted
    diagnostic = forensic["resolver_diagnostics"][0]
    assert diagnostic["quote"] == QUOTE
    assert diagnostic["global_exact_match_count"] == 2
    assert diagnostic["global_exact_match_offsets"] == [0, len(QUOTE) + 1]
    assert diagnostic["selected_candidate_id"] == selected_id
    assert diagnostic["candidate_source_start"] == 0
    assert diagnostic["candidate_source_end"] == len(REPORT)
    assert diagnostic["candidate_local_match_offsets"] == [0, len(QUOTE) + 1]
    assert diagnostic["resolution_status"] == "CANDIDATE_LOCAL_MULTIPLE_MATCHES"

    replay = replay_rejected_forensic_record_v4_1(forensic, source_report=REPORT)
    assert replay["status"] == "PASS"
    assert replay["provider_calls"] == 0
    assert replay["provider_zero"] is True
    assert replay["resolver_diagnostics_equal"] is True


class FakeModel:
    def invoke(self, prompt: str):
        request = json.loads(prompt.split("SHADOW_REQUEST_JSON:\n", 1)[1])
        candidate_id = request["candidate_hints"][0]["candidate_id"]
        return SimpleNamespace(content=json.dumps(_rejected_proposal(candidate_id)))


def test_gateway_exposes_bounded_forensic_for_sidecar_without_semantic_admission(tmp_path):
    session = SemanticRuntimeSession(
        run_id=RUN_ID,
        output_directory=tmp_path,
        execution_mode="shadow",
        provider="fake-provider",
        model="fake-model",
        cache=NullLLMResponseCache(),
    )
    gateway = Week2LLMGateway(
        FakeModel(),
        run_id=RUN_ID,
        output_root=tmp_path,
        provider="fake-provider",
        model_name="fake-model",
        semantic_runtime=session,
        max_retries=0,
    )
    bundle, invoker, _candidates, diagnostics, forensic = (
        run_real_provider_shadow_smoke_for_report_v4_1(
            gateway=gateway,
            source_report=REPORT,
            run_id=RUN_ID,
            ticker="TEST",
            agent="news_agent",
            agent_output_id=AGENT_OUTPUT_ID,
            factor_vocabulary=[],
        )
    )
    session.finalize_manifest(complete=True)

    record = session.recorder.read_all()[0]
    assert bundle["claims"] == []
    assert invoker.last_invocation is not None
    assert invoker.last_invocation.provider_called is True
    assert record["validation_status"] == "rejected"
    assert record["validated_output"] is None
    assert diagnostics[0]["global_exact_match_count"] == 2
    assert forensic is not None
    assert forensic["semantic_call_id"] == record["call_id"]
    assert forensic["parsed_candidate_payload"]["claims"][0]["claim"]
    assert "commentary" not in forensic["parsed_candidate_payload"]["claims"][0]
    assert "hidden_reasoning" not in forensic["parsed_candidate_payload"]
    assert forensic["parsed_candidate_payload_sha256"]


def test_invalid_json_has_no_parsed_rejected_candidate():
    parser = StructuredOutputShadowParserV4_1(
        lambda **_kwargs: "not-json{{", factor_vocabulary=[]
    )
    bundle = parser.parse_report_shadow_v4_1(
        source_report=REPORT,
        run_id=RUN_ID,
        ticker="TEST",
        agent="news_agent",
        agent_output_id=AGENT_OUTPUT_ID,
    )
    assert bundle["claims"] == []
    assert parser.last_rejected_candidate_payload is None
    assert (
        build_rejected_forensic_record_v4_1(
            parser=parser,
            bundle=bundle,
            provider="offline-fixture",
            model="fixture-model",
            semantic_call_id=None,
        )
        is None
    )
