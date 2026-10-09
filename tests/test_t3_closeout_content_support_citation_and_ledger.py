"""2026-10-08 (T3 closeout): content-support citation validation and its
semantic-ledger record.

Execution t3joint-20261008T170322Z-bd99811e rejected six real replies as
quote_or_data_not_found. Five of them cite parts that the cited candidate's
own excerpt prints verbatim (``_segmented_literal_citation_valid``); one
(t3v3-002) quotes text the excerpt does not contain and stays rejected.

The first group of tests replays the SAVED real replies (read from the
execution's wire audit, never retyped) against the production-built request
items through the unmodified ``_process_batch``. The second group uses small
constructed fixtures -- labeled as such -- for the cases no real reply
exercised (fragments, wrong bindings, invented parts). The last group checks
the semantic-ledger record through the production gateway builder with only
the HTTP transport replaced. Zero network.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
from comqutor_alpha.structure_engine import content_support_llm as cs
from tests._content_support_v2_fixture_helpers import v2_response

REPO = Path(__file__).resolve().parents[1]
DRIVER = REPO / "docs/audit_artifacts/round_source_linking_t0_t2/t3_joint_sample_driver.py"
MANIFEST = REPO / "docs/audit_artifacts/round_source_linking_t0_t2/round25_t3_minimal_prep_20261008/B1_samples_v4/joint_sample_v4_manifest.json"
EXECUTION_ID = "t3joint-20261008T170322Z-bd99811e"
EXECUTION_DIR = REPO / "outputs/t3_joint_evaluations" / EXECUTION_ID
CS_LOGS = EXECUTION_DIR / "content_support_verification" / EXECUTION_ID / "error_logs"


@lru_cache(maxsize=1)
def _driver():
    spec = importlib.util.spec_from_file_location("t3_joint_driver_closeout_tests", DRIVER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _t3_items_and_replies():
    driver = _driver()
    samples = driver.load_samples(MANIFEST)
    for s in samples:
        driver.strip_saved_llm_content_verdict(s["record"])
    items = {i.claim_id: i for run_items in driver.content_support_request_items(samples).values() for i in run_items}
    requests = [json.loads(line) for line in (CS_LOGS / "week2_llm_provider_request_audit.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    responses = {r["attempt_id"]: r for r in (json.loads(line) for line in (CS_LOGS / "week2_llm_provider_response_audit.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())}
    replies, bodies = {}, {}
    for req in requests:
        body = responses[req["attempt_id"]]["body"]
        bodies[req["claim_ids"][0]] = body
        replies[req["claim_ids"][0]] = json.loads(json.loads(body)["choices"][0]["message"]["content"])["items"][0]
    sample_of = {s["record"]["claim_id"]: s["sample_id"] for s in samples}
    claim_of = {sid: cid for cid, sid in sample_of.items()}
    sources_of = {s["sample_id"]: s["sources"] for s in samples}
    return items, replies, bodies, sample_of, claim_of, sources_of


class _ReplayGateway:
    """The unmodified _process_batch with a canned invocation wrapping a saved reply (no network)."""

    model_name = "deepseek-v4-flash"
    provider = "deepseek"

    def __init__(self, returned_items):
        self._returned_items = returned_items
        self.finalized = []

    def invoke_json_with_trace(self, task, payload, validator):
        return SimpleNamespace(provider_attempt_count=1, provider_status="success", error_code=None, cache_hit=False,
                               validation_accepted=True, request_control=None, provider_response_metadata=None, token_usage=None,
                               attempt_history=(), validated_output=validator({"items": self._returned_items}))

    def finalize_semantic_invocation(self, invocation, accepted, fallback_reason=None):
        self.finalized.append((accepted, fallback_reason))


def _run(item, reply):
    gateway = _ReplayGateway([reply])
    results = {}
    cs._process_batch([item], gateway, cs.ContentSupportRunStats(), results)
    return results[item.claim_id], gateway


# ---------------------------------------------------------------------------------------------------------------------
# real saved replies
# ---------------------------------------------------------------------------------------------------------------------

EXPECTED_AFTER_FIX = {
    "t3v3-002": ("quote_or_data_not_found", None),  # "Diluted EPS 2026-06-30=1.38" is not in the excerpt ("Diluted EPS: 2026-06-30=1.38")
    "t3v3-005": (None, "CONDITIONAL"),
    "t3v3-015": (None, "CONDITIONAL"),
    "t3v3-019": (None, "CONDITIONAL"),
    "t3v3-029": (None, "SUPPORTS"),
    "t3v3-031": (None, "SUPPORTS"),
}


@pytest.mark.parametrize("sample_id", sorted(EXPECTED_AFTER_FIX))
def test_six_rejected_real_replies_replayed_through_the_production_batch_processor(sample_id):
    items, replies, _, _, claim_of, _ = _t3_items_and_replies()
    claim_id = claim_of[sample_id]
    record, gateway = _run(items[claim_id], replies[claim_id])
    expected_reason, expected_status = EXPECTED_AFTER_FIX[sample_id]
    assert record["content_support_llm_fallback_reason"] == expected_reason
    if expected_status is None:
        assert record.get("content_support_llm_detail") is None
        assert gateway.finalized == [(False, "quote_or_data_not_found")]
    else:
        assert record["content_support_status"] == expected_status
        assert record["content_support_llm_detail"]["supporting_quote_or_data"] == replies[claim_id]["supporting_quote_or_data"]
        assert gateway.finalized == [(True, None)]


def test_the_eleven_replies_the_execution_accepted_get_the_same_verdict():
    items, replies, _, sample_of, _, _ = _t3_items_and_replies()
    predictions = {json.loads(line)["sample_id"]: json.loads(line) for line in (EXECUTION_DIR / "joint_predictions.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()}
    checked = 0
    for claim_id, item in items.items():
        sid = sample_of[claim_id]
        if predictions[sid]["L1"]["status"] != "LLM_RESULT":
            continue
        record, _ = _run(item, replies[claim_id])
        assert record["content_support_llm_fallback_reason"] is None, sid
        assert record["content_support_status"] == predictions[sid]["L1"]["content_support_status"], sid
        checked += 1
    assert checked == 11


# ---------------------------------------------------------------------------------------------------------------------
# constructed fixtures (not real replies): the reality rule still holds per part
# ---------------------------------------------------------------------------------------------------------------------

CANDIDATE = {
    "source_id": "src_fixture",
    "excerpt": "AMD fundamentals Forward PE=41.668015 PEG Ratio=0.64 Forward EPS=15.72189 PE Ratio (TTM)=167.11734 Beta=2.454",
    "data_snapshot": {"forward_pe": 41.668015, "peg_ratio": 0.64, "forward_eps": 15.72189, "trailing_pe": 167.11734, "beta": 2.454},
}


def _reason(used_location: str, quote: str):
    requested = cs.ContentSupportRequestItem(claim_id="c1", payload={"claim_id": "c1", "proposition": "x", "allowed_candidates": [CANDIDATE]},
                                             record={"claim_id": "c1"}, candidates_by_id={CANDIDATE["source_id"]: CANDIDATE})
    returned = v2_response(claim_id="c1", status="SUPPORTS", used_source_id="src_fixture", used_location=used_location,
                           supporting_quote_or_data=quote)
    return cs._validate_response_item(requested, returned)[1]


def test_fixture_verbatim_parts_bound_to_matching_paths_are_accepted():
    assert _reason("data_snapshot.forward_pe; data_snapshot.forward_eps; data_snapshot.trailing_pe",
                   "Forward PE=41.668015; Forward EPS=15.72189; PE Ratio (TTM)=167.11734") is None


def test_fixture_verbatim_parts_with_a_free_text_location_are_accepted():
    assert _reason("excerpt containing the PEG and EPS figures", "PEG Ratio=0.64; Forward EPS=15.72189") is None


def test_fixture_reformatted_part_not_in_the_excerpt_is_rejected():
    assert _reason("excerpt", "Forward PE 41.668015; Forward EPS=15.72189") == cs.FALLBACK_QUOTE_OR_DATA_NOT_FOUND


def test_fixture_fragment_of_a_longer_number_is_rejected():
    # "Forward PE=41.66" is a substring of "Forward PE=41.668015" but not a whole token
    assert _reason("excerpt", "Forward PE=41.66; Forward EPS=15.72189") == cs.FALLBACK_QUOTE_OR_DATA_NOT_FOUND


def test_fixture_label_split_from_its_value_is_rejected():
    assert _reason("excerpt", "Forward PE; =41.668015") == cs.FALLBACK_QUOTE_OR_DATA_NOT_FOUND


def test_fixture_invented_part_is_rejected():
    assert _reason("excerpt", "Forward PE=41.668015; Dividend Yield=9.99") == cs.FALLBACK_QUOTE_OR_DATA_NOT_FOUND


def test_fixture_real_excerpt_pair_cited_against_the_wrong_path_is_rejected():
    assert _reason("data_snapshot.trailing_pe; data_snapshot.forward_eps",
                   "Forward PE=41.668015; Forward EPS=15.72189") == cs.FALLBACK_QUOTE_OR_DATA_NOT_FOUND


def test_fixture_path_count_different_from_part_count_is_rejected():
    assert _reason("data_snapshot.forward_pe; data_snapshot.forward_eps; data_snapshot.trailing_pe",
                   "Forward PE=41.668015; Forward EPS=15.72189") == cs.FALLBACK_QUOTE_OR_DATA_NOT_FOUND


def test_fixture_unknown_path_is_rejected():
    assert _reason("data_snapshot.forward_pe; data_snapshot.not_a_field",
                   "Forward PE=41.668015; Forward EPS=15.72189") == cs.FALLBACK_QUOTE_OR_DATA_NOT_FOUND


# ---------------------------------------------------------------------------------------------------------------------
# semantic ledger: production gateway builder, real session, saved responses as the only fake (the HTTP transport)
# ---------------------------------------------------------------------------------------------------------------------


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


def test_content_support_calls_are_recorded_in_the_semantic_ledger_with_item_outcome(tmp_path, profile_env):
    from comqutor_alpha.structure_engine.week2_llm import (
        Week2LLMGateway,
        build_server_week2_llm_gateway,
    )

    items, _, bodies, _, claim_of, _ = _t3_items_and_replies()
    wanted = {"t3v3-029": claim_of["t3v3-029"], "t3v3-002": claim_of["t3v3-002"]}

    def handler(request: httpx.Request) -> httpx.Response:
        content = json.loads(request.content)["messages"][0]["content"]
        claim_id = json.loads(content[content.index('{"items"'):])["items"][0]["claim_id"]
        return httpx.Response(200, content=bodies[claim_id].encode("utf-8"), headers={"content-type": "application/json"})

    run_id = "closeout-ledger-test"
    (tmp_path / run_id).mkdir()
    gateway = build_server_week2_llm_gateway(run_id, tmp_path, execution_id=run_id, _base_transport_for_testing=httpx.MockTransport(handler))
    assert gateway is not None
    session = SemanticRuntimeSession(run_id=run_id, output_directory=tmp_path / run_id, execution_mode="test", provider="deepseek",
                                     model="deepseek-v4-flash")
    gateway.attach_semantic_runtime(session)
    results = {}
    for claim_id in wanted.values():
        cs._process_batch([items[claim_id]], gateway, cs.ContentSupportRunStats(), results)

    assert not session.incomplete and "SEMANTIC_RUNTIME_CALL_START_FAILED" not in session.degraded_reason_codes
    ledger = [json.loads(line) for line in (tmp_path / run_id / "llm_semantic_calls.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(ledger) == 2
    by_claim = {r["claim_ids"][0]: r for r in ledger}
    for record in ledger:
        assert record["task"] == "content_support_verification"
        assert record["prompt_version"] == "content_support.llm.v2.1"
        assert record["prompt_sha256"] == Week2LLMGateway.prompt_identity_sha256("content_support_verification")
        assert record["provider"] == "deepseek" and record["model"] == "deepseek-v4-flash"
        assert record["token_usage"] and record["token_usage"].get("input_tokens") and record["token_usage"].get("output_tokens")
        assert record["request_attempts"] and record["request_attempts"][0].get("attempt_id")
        assert record["retry_count"] == 0
    accepted = by_claim[wanted["t3v3-029"]]
    rejected = by_claim[wanted["t3v3-002"]]
    assert accepted["validation_status"] == "accepted" and accepted["fallback_reason"] is None
    assert rejected["validation_status"] == "rejected" and rejected["fallback_reason"] == "quote_or_data_not_found"
    assert results[wanted["t3v3-002"]]["content_support_llm_fallback_reason"] == "quote_or_data_not_found"
