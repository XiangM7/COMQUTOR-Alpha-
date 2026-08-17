"""Phase 1B.1: human review bundle generation from a real-invoker-shaped
(FakeModel-produced) Shadow bundle -- distinct from Phase 1A's pure
FakeSemanticInvoker-level review tests, this exercises the CSV/instructions
builders against output that passed through Week2GatewaySemanticInvoker.
"""

from __future__ import annotations

import csv
import io
import json
from types import SimpleNamespace

from comqutor_alpha.llm_runtime.cache import NullLLMResponseCache
from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
from comqutor_alpha.structure_engine.structured_output_adapter import adapt_raw_agent_outputs
from comqutor_alpha.structure_engine.structured_output_shadow_provider import (
    run_real_provider_shadow_smoke_for_report,
)
from comqutor_alpha.structure_engine.structured_output_shadow_review import (
    REVIEW_CSV_FIELDS,
    build_blank_review_rows,
    compare_legacy_and_shadow,
    render_blank_review_csv,
)
from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

REPORT = (
    "Cloud infrastructure spending increased materially this quarter. "
    "Management raised full-year guidance."
)


class FakeModel:
    def __init__(self, response_payload):
        self.response_payload = response_payload
        self.calls = 0

    def invoke(self, prompt):
        self.calls += 1
        request = json.loads(prompt.split("SHADOW_REQUEST_JSON:\n", 1)[1])
        payload = dict(self.response_payload)
        payload.update(
            {
                "run_id": request["run_id"],
                "ticker": request["ticker"],
                "agent": request["agent"],
                "agent_output_id": request["agent_output_id"],
                "source_report_sha256": request["source_report_sha256"],
                "prompt_version": request["prompt_version"],
                "prompt_sha256": request["prompt_sha256"],
            }
        )
        return SimpleNamespace(content=json.dumps(payload))


def _raw_record(agent_output_id: str) -> dict:
    return {
        "agent_output_id": agent_output_id,
        "run_id": "review-test-run",
        "ticker": "NVDA",
        "agent": "news_agent",
        "raw_output": REPORT,
        "source_path": "news_report",
        "source_field": "news_report",
    }


def test_review_csv_has_blank_judgment_columns_for_real_invoker_output(tmp_path):
    session = SemanticRuntimeSession(
        run_id="review-test-run",
        output_directory=tmp_path,
        execution_mode="shadow",
        provider="fake-provider",
        model="fake-model",
        cache=NullLLMResponseCache(),
    )
    payload = {
        "schema_version": "comqutor.structured_claim_shadow.v1",
        "claims": [],
        "abstentions": [
            {"candidate_segment_ids": [], "reason_code": "NO_RELIABLE_CLAIM", "notes": ""}
        ],
        "validation_summary": {},
        "shadow_only": True,
        "production_authority": False,
    }
    model = FakeModel(payload)
    gateway = Week2LLMGateway(
        model,
        run_id="review-test-run",
        output_root=str(tmp_path),
        provider="fake-provider",
        model_name="fake-model",
        semantic_runtime=session,
    )
    agent_output_id = "review-test-run:news_agent:news_report"
    bundle, invoker, _candidates = run_real_provider_shadow_smoke_for_report(
        gateway=gateway,
        source_report=REPORT,
        run_id="review-test-run",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id=agent_output_id,
        factor_vocabulary=[],
    )
    assert invoker.last_invocation.validation_accepted is True
    assert bundle["validation_summary"]["status"] == "abstained"

    legacy = adapt_raw_agent_outputs(
        _raw_record(agent_output_id), "review-test-run", "NVDA", llm_gateway=None
    )
    comparison = compare_legacy_and_shadow(legacy, bundle)
    assert comparison["semantic_quality_judgment"] is False
    assert comparison["gold_labels"] is False

    rows = build_blank_review_rows(comparison=comparison, legacy_outputs=legacy, shadow_bundle=bundle)
    assert rows  # at least the abstention/legacy navigation rows
    csv_text = render_blank_review_csv(rows)
    reader = csv.DictReader(io.StringIO(csv_text))
    parsed_rows = list(reader)
    assert reader.fieldnames == list(REVIEW_CSV_FIELDS)
    judgment_fields = ("review_dimension", "review_label", "severity", "reviewer", "review_timestamp", "notes")
    for row in parsed_rows:
        for field in judgment_fields:
            assert row[field] == ""
    for row in parsed_rows:
        assert row["source_run_id"] == "review-test-run"
        assert row["agent_output_id"] == agent_output_id


def test_review_csv_never_contains_llm_or_codex_generated_labels(tmp_path):
    # Structural guarantee: build_blank_review_rows has no parameter through
    # which a caller could inject a label -- verified by signature shape.
    import inspect

    signature = inspect.signature(build_blank_review_rows)
    label_like_params = {
        name
        for name in signature.parameters
        if any(token in name for token in ("label", "severity", "reviewer", "disposition"))
    }
    assert label_like_params == set()


def test_accepted_claim_review_rows_reference_real_shadow_claim_ids(tmp_path):
    session = SemanticRuntimeSession(
        run_id="review-test-run-2",
        output_directory=tmp_path,
        execution_mode="shadow",
        provider="fake-provider",
        model="fake-model",
        cache=NullLLMResponseCache(),
    )
    quote = "Cloud infrastructure spending increased materially this quarter."
    start = REPORT.index(quote)
    payload = {
        "schema_version": "comqutor.structured_claim_shadow.v1",
        "claims": [
            {
                "shadow_claim_id": "",
                "claim": quote,
                "evidence": quote,
                "source_spans": [{"start": start, "end": start + len(quote), "exact_quote": quote}],
                "entities": [],
                "factors": [],
                "direction": "positive",
                "confidence": 0.75,
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
    model = FakeModel(payload)
    gateway = Week2LLMGateway(
        model,
        run_id="review-test-run-2",
        output_root=str(tmp_path),
        provider="fake-provider",
        model_name="fake-model",
        semantic_runtime=session,
    )
    agent_output_id = "review-test-run-2:news_agent:news_report"
    bundle, invoker, _candidates = run_real_provider_shadow_smoke_for_report(
        gateway=gateway,
        source_report=REPORT,
        run_id="review-test-run-2",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id=agent_output_id,
        factor_vocabulary=[],
    )
    assert invoker.last_invocation.validation_accepted is True
    assert len(bundle["claims"]) == 1
    shadow_claim_id = bundle["claims"][0]["shadow_claim_id"]
    assert shadow_claim_id.startswith("shadow-claim-v1-")

    legacy = adapt_raw_agent_outputs(
        _raw_record(agent_output_id), "review-test-run-2", "NVDA", llm_gateway=None
    )
    comparison = compare_legacy_and_shadow(legacy, bundle)
    rows = build_blank_review_rows(comparison=comparison, legacy_outputs=legacy, shadow_bundle=bundle)
    assert any(row["shadow_claim_id"] == shadow_claim_id for row in rows)
