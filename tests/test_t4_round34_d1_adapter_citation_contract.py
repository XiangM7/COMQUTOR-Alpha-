"""T4 round 34 (2026-10-09), D1: the claim-enrichment (structured adapter) output contract now asks for cited_source_id.

Zero provider calls. Every test goes through the production path -- the server gateway builder
(build_server_week2_llm_gateway), a real semantic session, the production entry
structured_output_adapter.save_structured_agent_outputs (segmentation, _llm_batch_enrichment, the response parser and
validator, record building and source linking, persistence) and the API reader -- with ONE fake: the bottom HTTP transport,
which answers with a fixed reply built from the request it actually received. The network guard fails any test that
attempts a real outbound connection.

Fixed replies prove the contract and its handling only. They say nothing about how a real model answers the v2 prompt.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest

from comqutor_alpha.api.agent_output_reader import get_agent_outputs_response
from comqutor_alpha.graph_engine.verified_evidence_gate import filter_verified_qualifying_claims
from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
from comqutor_alpha.replay.source_bundle import _SUPPORTED_CALL_IDENTITIES
from comqutor_alpha.source_provenance import (
    build_source_registry,
    compute_verified_support_eligibility,
)
from comqutor_alpha.storage.file_store import save_json_record
from comqutor_alpha.structure_engine import structured_output_adapter as adapter
from comqutor_alpha.structure_engine.week2_llm import (
    _TASK_RUNTIME_METADATA,
    Week2LLMGateway,
    build_server_week2_llm_gateway,
)
from tests._network_guard import network_guard  # noqa: F401  (fixture, applied to every test below)

pytestmark = pytest.mark.usefixtures("network_guard")

REPO = Path(__file__).resolve().parents[1]
FRESH2 = REPO / "outputs" / "t4_runs" / "12591384-0b26-470d-a99d-a49c00be440b"
RUN_ID = "r34-d1-contract"
TICKER = "NVDA"
SEP = "\nINPUT_JSON:\n"
REQUIRED = ["segment_id", "claim", "evidence", "source_section", "entities", "factors", "direction", "confidence", "cited_source_id"]
DC = "NVDA reported strong data center revenue growth this quarter, beating analyst estimates."
GAMING = "NVDA gaming revenue declined as channel inventory normalized during the quarter."
OTHER = "Management expects supply constraints to ease over the next two quarters."
AMD = "AMD outlined its next-generation roadmap at its annual investor day event."
V1 = {"prompt_version": "week2.claim_batch_enrichment.v1", "prompt_sha256": "c6822099e2171c6fbad72c36bf2881bcd59bd4d4ad2fc20e10ab62af50b5bfd9"}


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


def _registry(tmp_path):
    """A real registry (production build_source_registry): DC is carried verbatim by two publishers (two candidates for one
    segment), GAMING by one, AMD by one (real, but matching no segment), nothing for OTHER."""
    registry = build_source_registry(run_id=RUN_ID, ticker=TICKER, retrieved_at="2026-08-10T00:00:00Z", captured_records=[
        {"source_type": "news", "name": "Reuters", "title": "NVDA data center", "url": "https://reuters.com/nvda-dc",
         "published_at": "2026-08-05T00:00:00", "excerpt": DC},
        {"source_type": "news", "name": "Bloomberg", "title": "NVDA data center (syndicated)", "url": "https://bloomberg.com/nvda-dc",
         "published_at": "2026-08-05T00:00:00", "excerpt": DC},
        {"source_type": "news", "name": "Reuters", "title": "NVDA gaming", "url": "https://reuters.com/nvda-gaming",
         "published_at": "2026-08-05T00:00:00", "excerpt": GAMING},
        {"source_type": "news", "name": "Barron's", "title": "AMD roadmap", "url": "https://barrons.com/amd-roadmap",
         "published_at": "2026-08-05T00:00:00", "excerpt": AMD},
    ])
    save_json_record(RUN_ID, "metadata.json", {"run_id": RUN_ID, "ticker": TICKER, "analysis_date": "2026-08-10"}, output_root=str(tmp_path))
    save_json_record(RUN_ID, "raw_agent_outputs.json", {"schema_version": "raw.v1", "run_id": RUN_ID, "ticker": TICKER, "agent_outputs": [
        {"agent": "news_agent", "agent_output_id": f"{RUN_ID}:news_agent:news_report", "raw_output": f"{DC} {GAMING} {OTHER}"}]},
        output_root=str(tmp_path))
    save_json_record(RUN_ID, "source_registry.json", registry, output_root=str(tmp_path))
    by_excerpt = {}
    for s in registry["sources"]:
        by_excerpt.setdefault(s["excerpt"], []).append(s)
    return registry["sources"], by_excerpt


def _chat_body(content: dict) -> bytes:
    return json.dumps({"id": "fixed", "object": "chat.completion", "created": 0, "model": "deepseek-flash",
                       "choices": [{"index": 0, "message": {"role": "assistant", "content": json.dumps(content)}, "finish_reason": "stop"}],
                       "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}).encode("utf-8")


def _segment_of(payload, text):
    return next(s for s in payload["segments"] if text in s["claim"] or text in s["evidence"])


CONTENT_SUPPORT_REQUESTS: list[dict] = []


def _run(tmp_path, reply_for):
    """Production run of the adapter stage. ``reply_for(request_payload) -> {"claims": [...]}`` is the fixed enrichment
    reply. The same stage then sends content-support verification requests for linked claims (``items`` payloads); they
    are recorded in CONTENT_SUPPORT_REQUESTS and answered with a reply that is not a verdict, so no support judgment is
    simulated and those claims stay pending review."""
    sent: list[dict] = []
    CONTENT_SUPPORT_REQUESTS.clear()

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        prompt = body["messages"][0]["content"]
        payload = json.loads(prompt.split(SEP, 1)[1])
        if "segments" in payload:
            sent.append({"prompt": prompt.split(SEP, 1)[0], "payload": payload})
            return httpx.Response(200, content=_chat_body(reply_for(payload)), headers={"content-type": "application/json"})
        CONTENT_SUPPORT_REQUESTS.append(payload)
        return httpx.Response(200, content=_chat_body({}), headers={"content-type": "application/json"})

    run_dir = tmp_path / RUN_ID
    gateway = build_server_week2_llm_gateway(RUN_ID, tmp_path, execution_id=RUN_ID, _base_transport_for_testing=httpx.MockTransport(handler))
    gateway.attach_semantic_runtime(SemanticRuntimeSession(run_id=RUN_ID, output_directory=run_dir, execution_mode="test",
                                                           provider="deepseek", model="deepseek-v4-flash"))
    adapter.save_structured_agent_outputs(run_dir, llm_gateway=gateway)
    ledger = [json.loads(x) for x in (run_dir / "llm_semantic_calls.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    records = json.loads((run_dir / "structured_agent_outputs.json").read_text(encoding="utf-8"))["records"]
    adapter_calls = [r for r in ledger if r["task"] == "structured_adapter"]
    assert all(r["validation_status"] != "accepted" for r in ledger if r["task"] == "content_support_verification")
    return sent, adapter_calls, records


def _items(payload, cite):
    """The full nine-field item for every segment; ``cite(segment) -> id or None``."""
    return {"claims": [{**{k: seg[k] for k in ("segment_id", "claim", "evidence", "source_section")},
                        "entities": ["NVIDIA"], "factors": ["Revenue Growth"], "direction": "positive", "confidence": 0.8,
                        "cited_source_id": cite(seg)} for seg in payload["segments"]]}


def _record(records, text):
    return next(r for r in records if text in (r.get("evidence") or "") or text in (r.get("claim") or ""))


def _assert_rejected_and_fell_back(adapter_calls, records):
    """Failure is never a valid NONE or a successful enrichment: the call is a recorded rejection, and every record comes
    from deterministic extraction with no agent citation and no support verdict."""
    assert len(adapter_calls) == 1
    call = adapter_calls[0]
    assert (call["validation_status"], call["fallback_reason"], call["fallback_used"]) == ("rejected", "WEEK2_LLM_VALIDATION_FAILED", True)
    assert call["validated_output"] is None
    for r in records:
        assert r["extraction_method"] == "deterministic_splitter"
        assert r["source_link_method"] != "AGENT_CITED"
        assert r["content_support_status"] != "SUPPORTS"


# 1. the request the transport receives
def test_transport_request_asks_for_all_nine_fields_and_scopes_candidates_per_segment(tmp_path, profile_env):
    sources, by_excerpt = _registry(tmp_path)
    sent, adapter_calls, _ = _run(tmp_path, lambda p: _items(p, lambda seg: None))
    assert len(sent) == 1
    prompt, payload = sent[0]["prompt"], sent[0]["payload"]
    assert "Each item must contain segment_id, claim, evidence, source_section, entities, factors, direction, confidence, and cited_source_id" in prompt
    assert all(field in prompt for field in REQUIRED) and "segment_ids" in prompt and "null" in prompt
    # the ledger records the v2 identity, equal to the live identity and to the replay registry's v2 entry
    call = adapter_calls[0]
    assert call["prompt_version"] == _TASK_RUNTIME_METADATA["claim_batch_enrichment"]["prompt_version"] == "week2.claim_batch_enrichment.v2"
    assert call["prompt_sha256"] == Week2LLMGateway.prompt_identity_sha256("claim_batch_enrichment")
    assert (call["input_schema_version"], call["output_schema_version"]) == ("week2.claim_batch_enrichment.input.v2", "week2.claim_batch_enrichment.output.v2")
    assert {k: call[k] for k in ("prompt_version", "prompt_sha256", "input_schema_version", "output_schema_version", "taxonomy_version")} in list(_SUPPORTED_CALL_IDENTITIES["structured_adapter"])
    # candidates: real registry entries, with their material, each listing exactly the segments whose text carries it
    dc_seg, gaming_seg, other_seg = (_segment_of(payload, t)["segment_id"] for t in (DC, GAMING, OTHER))
    offered = {c["fragment_id"]: c for c in payload["candidate_sources"]}
    registry = {s["fragment_id"]: s for s in sources}
    for fid, cand in offered.items():
        assert (cand["source_id"], cand["excerpt"]) == (registry[fid]["source_id"], registry[fid]["excerpt"])
    assert {fid: cand["segment_ids"] for fid, cand in offered.items()} == {
        by_excerpt[DC][0]["fragment_id"]: [dc_seg], by_excerpt[DC][1]["fragment_id"]: [dc_seg], by_excerpt[GAMING][0]["fragment_id"]: [gaming_seg]}
    assert by_excerpt[AMD][0]["fragment_id"] not in offered  # real but matching no segment: never offered
    assert not any(other_seg in c["segment_ids"] for c in offered.values())


# 2 + 6 + 7. a full reply with in-scope citations is accepted, persisted, consumed -- and still not support or score
def test_valid_citations_are_accepted_persisted_and_consumed_without_becoming_support(tmp_path, profile_env):
    sources, by_excerpt = _registry(tmp_path)
    dc_b, gaming = by_excerpt[DC][1], by_excerpt[GAMING][0]  # DC cites the SECOND of its two candidates: the model's choice

    def cite(seg):
        return {DC: dc_b["fragment_id"], GAMING: gaming["fragment_id"]}.get(next((t for t in (DC, GAMING) if t in seg["claim"] or t in seg["evidence"]), None))

    _, adapter_calls, records = _run(tmp_path, lambda p: _items(p, cite))
    call = adapter_calls[0]
    assert (call["validation_status"], call["fallback_used"]) == ("accepted", False)
    dc_rec, gaming_rec, other_rec = (_record(records, t) for t in (DC, GAMING, OTHER))
    for rec, src in ((dc_rec, dc_b), (gaming_rec, gaming)):
        assert rec["extraction_method"] == "llm_strict_json"
        assert (rec["source_link_method"], rec["source_link_status"], rec["linked_source_id"]) == ("AGENT_CITED", "VALID", src["source_id"])
    assert dc_rec["linked_source_id"] != by_excerpt[DC][0]["source_id"]  # never re-picked as the first candidate
    # downstream consumption: the content-support request for each cited claim offers exactly the cited source
    cs_by_claim = {item["claim_id"]: item for req in CONTENT_SUPPORT_REQUESTS for item in req["items"]}
    for rec, src in ((dc_rec, dc_b), (gaming_rec, gaming)):
        assert [c["source_id"] for c in cs_by_claim[rec["claim_id"]]["allowed_candidates"]] == [src["source_id"]]
    # a link is not support and not scoring eligibility
    for rec in (dc_rec, gaming_rec):
        assert rec["content_support_status"] == "PENDING_REVIEW"
        assert compute_verified_support_eligibility(rec, sources)["eligible"] is False
    index = {r["claim_id"]: r for r in records}
    assert filter_verified_qualifying_claims([{"claim_id": dc_rec["claim_id"]}, {"claim_id": gaming_rec["claim_id"]}], index, sources) == []
    # the API reader shows the same citation
    api = {r["claim_id"]: r for r in get_agent_outputs_response(RUN_ID, output_root=str(tmp_path))["structured_agent_outputs"]}
    assert api[dc_rec["claim_id"]]["source_link_method"] == "AGENT_CITED"
    assert api[dc_rec["claim_id"]]["linked_source"]["source_id"] == dc_b["source_id"]
    # 3. the segment with no candidate answered null: no reference, no support, no eligibility
    assert other_rec["source_link_method"] == "NONE" and other_rec["source_link_status"] != "VALID"
    assert other_rec["content_support_status"] == "NOT_APPLICABLE"


# 3 + 6. null where candidates exist: the adapter never fills in or chooses a citation
def test_null_citation_with_two_candidates_is_never_turned_into_an_agent_citation(tmp_path, profile_env):
    sources, _ = _registry(tmp_path)
    _, adapter_calls, records = _run(tmp_path, lambda p: _items(p, lambda seg: None))
    assert (adapter_calls[0]["validation_status"], adapter_calls[0]["fallback_used"]) == ("accepted", False)
    for rec in records:
        assert rec["extraction_method"] == "llm_strict_json"
        assert rec["source_link_method"] != "AGENT_CITED"
        assert rec["content_support_status"] != "SUPPORTS"
        assert compute_verified_support_eligibility(rec, sources)["eligible"] is False
    # the pre-existing deterministic content matcher still runs on its own and is labelled as such -- never as a citation
    assert _record(records, DC)["source_link_method"] == "CONTENT_MATCH_CANDIDATE"
    assert _record(records, OTHER)["source_link_method"] == "NONE"


# 4 + 6 + 8. missing field, invented id, a real id never offered, and another segment's candidate are all rejected
@pytest.mark.parametrize("case", ["missing_field", "invented_id", "real_id_never_offered", "other_segments_candidate", "source_id_of_other_segment"])
def test_missing_field_invented_out_of_scope_and_crossed_citations_are_rejected(tmp_path, profile_env, case):
    _, by_excerpt = _registry(tmp_path)

    def reply(payload):
        def cite(seg):
            if case == "invented_id" and DC in seg["claim"]:
                return "src_model_invented_0001:frag:0"
            if case == "real_id_never_offered" and DC in seg["claim"]:
                return by_excerpt[AMD][0]["fragment_id"]
            if case == "other_segments_candidate" and GAMING in seg["claim"]:
                return by_excerpt[DC][0]["fragment_id"]
            if case == "source_id_of_other_segment" and GAMING in seg["claim"]:
                return by_excerpt[DC][0]["source_id"]
            return None
        items = _items(payload, cite)
        if case == "missing_field":  # exactly the eight fields of the v1 prompt
            for item in items["claims"]:
                del item["cited_source_id"]
        return items

    _, adapter_calls, records = _run(tmp_path, reply)
    _assert_rejected_and_fell_back(adapter_calls, records)


# 5 + 8. the existing contract errors are still rejected
@pytest.mark.parametrize("case", ["invalid_direction", "claim_rewritten", "segment_omitted", "confidence_out_of_range"])
def test_existing_contract_violations_are_still_rejected(tmp_path, profile_env, case):
    _registry(tmp_path)

    def reply(payload):
        items = _items(payload, lambda seg: None)
        if case == "invalid_direction":
            items["claims"][0]["direction"] = "sideways"
        elif case == "claim_rewritten":
            items["claims"][0]["claim"] += " (rewritten)"
        elif case == "segment_omitted":
            items["claims"].pop()
        else:
            items["claims"][0]["confidence"] = 1.5
        return items

    _, adapter_calls, records = _run(tmp_path, reply)
    _assert_rejected_and_fell_back(adapter_calls, records)


# the validator itself: per-segment scope, and no fallback to the batch-wide set when the mapping is given
def test_validator_checks_each_citation_against_its_own_segment_only():
    segments = [{"segment_id": s, "claim": s, "evidence": s, "source_section": "x"} for s in ("a", "b")]

    def payload(cite_a, cite_b):
        return {"claims": [{"segment_id": s, "claim": s, "evidence": s, "source_section": "x", "entities": [], "factors": [],
                            "direction": "unknown", "confidence": 0.5, "cited_source_id": c} for s, c in (("a", cite_a), ("b", cite_b))]}

    scope = {"a": frozenset({"src_1", "src_1:frag:0"}), "b": frozenset()}
    out = adapter._validate_llm_batch_enrichment(payload("src_1:frag:0", None), segments, candidate_source_ids_by_segment=scope)
    assert (out["a"]["cited_source_id"], out["b"]["cited_source_id"]) == ("src_1:frag:0", None)
    for bad in (payload(None, "src_1:frag:0"), payload("src_2:frag:0", None), payload("", None)):
        with pytest.raises(ValueError):
            adapter._validate_llm_batch_enrichment(bad, segments, candidate_source_ids_by_segment=scope)


# version registry: v1 retired verbatim, v2 live
def test_v1_prompt_is_retired_verbatim_and_both_identities_stay_registered_for_replay():
    assert Week2LLMGateway.retired_prompt_identity_sha256("week2.claim_batch_enrichment.v1") == V1["prompt_sha256"]
    versions = {i["prompt_version"]: i["prompt_sha256"] for i in _SUPPORTED_CALL_IDENTITIES["structured_adapter"]}
    assert versions == {V1["prompt_version"]: V1["prompt_sha256"],
                        "week2.claim_batch_enrichment.v2": Week2LLMGateway.prompt_identity_sha256("claim_batch_enrichment")}
    assert Week2LLMGateway.prompt_identity_sha256("claim_batch_enrichment") != V1["prompt_sha256"]


# the two real replies of the second Fresh run, unchanged, are still rejected after the fix (they lack the field)
@pytest.mark.skipif(not (FRESH2 / "llm_semantic_calls.jsonl").is_file(), reason="saved NVDA Fresh run 12591384 not present")
def test_the_second_fresh_runs_two_saved_replies_are_still_rejected_unchanged(tmp_path, profile_env):
    ledger = [json.loads(x) for x in (FRESH2 / "llm_semantic_calls.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    replies = {json.loads(x)["attempt_id"]: json.loads(x) for x in (FRESH2 / "error_logs" / "week2_llm_provider_response_audit.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()}
    sources = json.loads((FRESH2 / "source_registry.json").read_text(encoding="utf-8"))["sources"]
    checked = 0
    for call in (r for r in ledger if r["task"] == "structured_adapter"):
        reply = next((replies[a["attempt_id"]] for a in call.get("request_attempts") or [] if a["attempt_id"] in replies), None)
        if reply is None:
            continue
        assert hashlib.sha256(reply["body"].encode("utf-8")).hexdigest() == reply["body_sha256"]  # the saved reply, unchanged
        payload = call["input_payload"]
        run_id = f"r34-fresh2-{call['call_sequence']}"
        (tmp_path / run_id).mkdir()
        gw = build_server_week2_llm_gateway(run_id, tmp_path, execution_id=run_id, _base_transport_for_testing=httpx.MockTransport(
            lambda request, body=reply["body"]: httpx.Response(200, content=body.encode("utf-8"), headers={"content-type": "application/json"})))
        gw.attach_semantic_runtime(SemanticRuntimeSession(run_id=run_id, output_directory=tmp_path / run_id, execution_mode="test",
                                                          provider="deepseek", model="deepseek-v4-flash"))
        out = adapter._llm_batch_enrichment(gw, ticker=payload["ticker"], agent=payload["agent"], batch_segments=payload["segments"],
                                            sources=adapter.scope_sources_for_agent(payload["agent"], sources))
        rec = json.loads((tmp_path / run_id / "llm_semantic_calls.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        assert out is None
        assert (rec["prompt_version"], rec["validation_status"], rec["fallback_reason"]) == ("week2.claim_batch_enrichment.v2", "rejected", "WEEK2_LLM_VALIDATION_FAILED")
        items = json.loads(json.loads(reply["body"])["choices"][0]["message"]["content"])["claims"]
        assert all("cited_source_id" not in item for item in items)
        checked += 1
    assert checked == 2
