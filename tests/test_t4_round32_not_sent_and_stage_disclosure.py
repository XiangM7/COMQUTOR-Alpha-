"""T4 round 32 (2026-10-09): a request refused locally because its input is too large is recorded as "not sent"
(never as a malformed model response), and every run discloses which model-assisted sub-steps fell back.

Zero provider calls. The content-support tests use the production gateway builder, a real semantic session and the
unmodified ``_process_batch`` with the SAVED payloads of the second NVDA Fresh run (12591384) -- the oversized request
it never sent and one request it sent -- plus that run's saved real response body as the only fake (the bottom HTTP
transport). The end-to-end test reuses the round-28 harness (real research pipeline, fixed responses at the transport).
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
from comqutor_alpha.structure_engine import content_support_llm as cs, evidence_stance_llm as esl
from tests.test_t4_round28_provider_stop import (  # noqa: F401
    MockWeek2Provider,
    _install,
    _run,
    needs_source,
    week2_env,
)

REPO = Path(__file__).resolve().parents[1]
FRESH2 = REPO / "outputs" / "t4_runs" / "12591384-0b26-470d-a99d-a49c00be440b"
needs_fresh2 = pytest.mark.skipif(not (FRESH2 / "llm_semantic_calls.jsonl").is_file(), reason="saved NVDA Fresh run 12591384 not present")


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.is_file() else []


def _fresh2_cs_calls():
    ledger = _jsonl(FRESH2 / "llm_semantic_calls.jsonl")
    calls = [r for r in ledger if r["task"] == "content_support_verification"]
    oversized = [r for r in calls if r.get("error_code") == "WEEK2_LLM_INPUT_TOO_LARGE"]
    sent_supports = [r for r in calls if r.get("request_attempts") and r["validation_status"] == "accepted"]
    records = {r["claim_id"]: r for r in json.loads((FRESH2 / "structured_agent_outputs.json").read_text(encoding="utf-8"))["records"]}
    responses = {r["attempt_id"]: r for r in _jsonl(FRESH2 / "error_logs" / "week2_llm_provider_response_audit.jsonl")}
    return oversized, sent_supports, records, responses


def _item(call: dict, records: dict) -> cs.ContentSupportRequestItem:
    """The production request builder applied to the run's saved records and source registry; its payload must be
    exactly the payload the run recorded for this call (the request body is unchanged)."""
    sources = json.loads((FRESH2 / "source_registry.json").read_text(encoding="utf-8"))["sources"]
    claim_id = call["claim_ids"][0]
    item = next(i for i in cs.build_content_support_request_items(list(records.values()), sources) if i.claim_id == claim_id)
    assert item.payload == call["input_payload"]["items"][0]
    return item


@pytest.fixture
def profile_env(monkeypatch):
    for name, value in {
        "COMQUTOR_WEEK2_LLM_ENABLED": "1",
        "COMQUTOR_WEEK2_LLM_PROVIDER": "deepseek",
        "COMQUTOR_WEEK2_LLM_MODEL": "deepseek-v4-flash",
        "COMQUTOR_WEEK2_LLM_BASE_URL": "https://api.deepseek.com",
        "COMQUTOR_WEEK2_LLM_PROFILE": "t3_verified_20261008",
        "DEEPSEEK_API_KEY": "test-not-a-key",
    }.items():
        monkeypatch.setenv(name, value)


def test_not_sent_reason_mapping_is_input_too_large_for_content_support_and_stance():
    refused = SimpleNamespace(provider_status="not_called", error_code="WEEK2_LLM_INPUT_TOO_LARGE")
    assert cs._reason_from_invocation(refused) == cs.FALLBACK_INPUT_TOO_LARGE == "input_too_large"
    assert esl._reason_from_invocation(refused) == esl.FALLBACK_INPUT_TOO_LARGE == "input_too_large"
    # a real malformed reply keeps its own reason
    for module in (cs, esl):
        assert module._reason_from_invocation(SimpleNamespace(provider_status="success", error_code="WEEK2_LLM_VALIDATION_FAILED")) == "malformed_response"
        assert module.FALLBACK_INPUT_TOO_LARGE in module.VALID_FALLBACK_REASONS


@needs_fresh2
def test_saved_oversized_request_is_not_sent_and_the_saved_sent_request_behaves_as_before(tmp_path, profile_env):
    from comqutor_alpha.structure_engine.week2_llm import (
        MAX_PROMPT_PAYLOAD_CHARS,
        build_server_week2_llm_gateway,
    )

    oversized, sent_supports, records, responses = _fresh2_cs_calls()
    assert len(oversized) == 5
    big, normal = _item(oversized[0], records), _item(sent_supports[0], records)
    normal_body = responses[sent_supports[0]["request_attempts"][0]["attempt_id"]]["body"]
    arrivals: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        content = json.loads(request.content)["messages"][0]["content"]
        claim_id = json.loads(content[content.index('{"items"'):])["items"][0]["claim_id"]
        arrivals.append(claim_id)
        assert claim_id == normal.claim_id, "the oversized request reached the transport"
        return httpx.Response(200, content=normal_body.encode("utf-8"), headers={"content-type": "application/json"})

    run_id = "r32-not-sent"
    (tmp_path / run_id).mkdir()
    gateway = build_server_week2_llm_gateway(run_id, tmp_path, execution_id=run_id, _base_transport_for_testing=httpx.MockTransport(handler))
    session = SemanticRuntimeSession(run_id=run_id, output_directory=tmp_path / run_id, execution_mode="test", provider="deepseek", model="deepseek-v4-flash")
    gateway.attach_semantic_runtime(session)
    stats, results = cs.ContentSupportRunStats(), {}

    reservations_before = gateway.call_count
    cs._process_batch([big], gateway, stats, results)
    assert arrivals == [] and gateway.call_count == reservations_before  # no HTTP request, no budget reservation
    cs._process_batch([normal], gateway, stats, results)
    assert arrivals == [normal.claim_id] and gateway.call_count == reservations_before + 1

    # the claim: technical "not sent", never a verdict and never a malformed model response
    refused = results[big.claim_id]
    assert refused["content_support_llm_fallback_reason"] == "input_too_large"
    assert refused["content_support_status"] == records[big.claim_id]["content_support_status"] == "PENDING_REVIEW"
    assert refused.get("content_support_llm_detail") is None
    # the ledger: not_called, no attempt, no usage, the measured size and the limit
    ledger = {r["claim_ids"][0]: r for r in _jsonl(tmp_path / run_id / "llm_semantic_calls.jsonl")}
    rec = ledger[big.claim_id]
    serialized = json.dumps({"items": [big.payload]}, ensure_ascii=False, default=str)
    assert len(serialized) > MAX_PROMPT_PAYLOAD_CHARS
    assert rec["provider_status"] == "not_called" and not rec.get("request_attempts") and rec["validation_status"] == "not_run"
    assert rec["error_code"] == "WEEK2_LLM_INPUT_TOO_LARGE" and rec["fallback_reason"] == "input_too_large"
    assert f"input of {len(serialized)} characters exceeds the {MAX_PROMPT_PAYLOAD_CHARS}-character limit" in rec["error_message"]
    assert rec["token_usage"] == {"input_tokens": None, "output_tokens": None, "total_tokens": None}
    attempt_log = {tuple(e["claim_ids"]): e for e in stats.attempt_log}
    assert attempt_log[(big.claim_id,)]["input_chars"] == len(serialized)
    assert attempt_log[(big.claim_id,)]["input_limit_chars"] == MAX_PROMPT_PAYLOAD_CHARS
    assert attempt_log[(big.claim_id,)]["provider_attempt_count"] == 0
    # the legitimate request: same verdict as the Fresh run saved, error_message stays empty
    assert results[normal.claim_id]["content_support_status"] == records[normal.claim_id]["content_support_status"]
    assert ledger[normal.claim_id]["validation_status"] == "accepted" and ledger[normal.claim_id]["error_message"] is None
    assert stats.fallback_reason_counts["input_too_large"] == 1 and stats.fallback_reason_counts["malformed_response"] == 0


def test_evidence_trace_reads_input_too_large_as_not_sent():
    from comqutor_alpha.api.evidence_trace import _source_support_status

    out = _source_support_status({"source_link_status": "VALID", "content_support_status": "PENDING_REVIEW",
                                  "content_support_llm_fallback_reason": "input_too_large"}, {"eligible": False}, {})
    assert out["status_code"] == "TECHNICAL_INCOMPLETE"
    assert "not sent" in out["reason"] and "format" not in out["reason"]


@needs_fresh2
def test_stage_disclosure_of_the_saved_fresh_run_reads_the_ledger_not_the_old_label():
    from comqutor_alpha.api.stage_disclosure import build_stage_disclosure

    disclosure = build_stage_disclosure(FRESH2)
    stages = {s["stage"]: s for s in disclosure["stages"]}
    assert disclosure["degraded_stages"] == ["claim_enrichment", "content_support_verification", "structure_extraction"]
    assert stages["claim_enrichment"]["status"] == "model_not_used"
    assert stages["claim_enrichment"]["outcomes"] == {"not_sent_input_too_large": 1, "reply_not_accepted:WEEK2_LLM_VALIDATION_FAILED": 1, "timeout": 7}
    assert stages["claim_enrichment"]["fields_from_deterministic_processing"] == ["entities", "factors", "direction", "confidence", "cited_source_id"]
    # the five never-sent verifications are disclosed as not sent although their saved label is malformed_response
    assert stages["content_support_verification"]["outcomes"]["not_sent_input_too_large"] == 5
    assert stages["content_support_verification"]["outcomes"]["reply_not_accepted:malformed_response"] == 3
    assert stages["alpha_classification"]["status"] == "model_complete"
    assert stages["structure_extraction"]["outcomes"] == {"reply_not_accepted:WEEK2_LLM_VALIDATION_FAILED": 1, "valid_empty_result_not_used": 1}
    assert stages["structure_extraction"]["extracted_edges_by_source"] == {"model_structure_extraction": 0, "deterministic_grammar": 0,
                                                                            "tradingagents_canonical_relations": 16}
    assert stages["structure_graph"]["status"] == "built"  # graph built is reported separately from extraction success


def test_stage_disclosure_without_a_ledger_is_not_recorded(tmp_path):
    from comqutor_alpha.api.stage_disclosure import build_stage_disclosure

    disclosure = build_stage_disclosure(tmp_path)
    assert disclosure["stages"] == [] and disclosure["source"].startswith("not_recorded")


@needs_source
def test_pipeline_api_and_export_carry_the_same_stage_disclosure(week2_env, monkeypatch):  # noqa: F811
    from comqutor_alpha.api.routes_research import build_research_response, get_run_export_bundle

    provider = MockWeek2Provider()  # fixed responses; the enrichment reply follows the prompt's eight fields
    _install(monkeypatch, provider)
    response, run_dir = _run(week2_env, provider, "r32-disclosure")
    disclosure = response["stage_disclosure"]
    stages = {s["stage"]: s for s in disclosure["stages"]}
    assert set(stages) == {"claim_enrichment", "content_support_verification", "alpha_classification", "evidence_stance",
                           "structure_extraction", "structure_graph"}
    saved = json.loads((run_dir / "stage_disclosure.json").read_text(encoding="utf-8"))
    assert saved == disclosure == build_research_response(response["run_id"], str(week2_env["output_root"]))["stage_disclosure"]
    manifest = json.loads((run_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
    assert any(a["artifact_name"] == "stage_disclosure.json" and a["status"] == "valid" for a in manifest["artifacts"])
    code, _, body, _, _ = get_run_export_bundle(response["run_id"], str(week2_env["output_root"]))
    assert code == 200
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        assert json.loads(zf.read("stage_disclosure.json")) == disclosure
