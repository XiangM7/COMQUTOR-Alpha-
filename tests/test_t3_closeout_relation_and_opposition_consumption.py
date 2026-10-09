"""2026-10-08 (T3 closeout): which field each production gate reads when a
claim could become positive activation evidence.

Contract (docs/specs/product_decisions_and_unknowns.md PD-006, NOT_APPROVED;
docs/specs/semantic_authority_matrix.csv "evidence stance": "No production
authority", "CURRENT effect is SHADOW_ONLY"): the LLM direction cannot affect
Activation. The activation-evidence selector therefore reads the mapper's
deterministic ``relation`` and ``assertion_status``; these tests pin that an
LLM ``supports_alpha`` never lifts a claim past those gates or past the
verified-support gate, and that background, citation-only, conditional,
opposing and insufficient content-support verdicts never count as verified
support.

What these tests do NOT claim: a claim the LLM judged opposes_alpha or
neutral_background but whose text rule says ``activation`` (T3 samples 037,
038, 040) passes every selector gate today and is kept out of the pool only
by the source gate -- recorded in the closeout report as an open product
decision, not asserted here.

Match records are constructed (fields as the production mapper writes them,
values as observed for t3v3-005/006); the content-support case replays the
real saved t3v3-006 reply. Zero network.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pytest

from comqutor_alpha.graph_engine.evidence_fact_index import (
    REASON_ASSERTION_NEGATED,
    REASON_RELATION_NOT_SUPPORTING,
    select_supporting_alpha_claims,
)
from comqutor_alpha.source_provenance import compute_verified_support_eligibility
from comqutor_alpha.structure_engine import content_support_llm as cs
from tests._content_support_v2_fixture_helpers import v2_response

REPO = Path(__file__).resolve().parents[1]
DRIVERS = REPO / "docs/audit_artifacts/round_source_linking_t0_t2"
MANIFEST = DRIVERS / "round25_t3_minimal_prep_20261008/B1_samples_v4/joint_sample_v4_manifest.json"
EXECUTION_ID = "t3joint-20261008T170322Z-bd99811e"
CS_LOGS = REPO / "outputs/t3_joint_evaluations" / EXECUTION_ID / "content_support_verification" / EXECUTION_ID / "error_logs"


def _match(*, relation: str, assertion_status: str, stance: str, stance_method: str | None = "llm") -> dict:
    candidate = {"alpha_id": "A304", "relation": relation, "evidence_stance": stance, "stance_method": stance_method, "score": 0.0}
    return {"claim_id": "run:portfolio_manager:claim:1", "match_status": "matched", "matched_alpha": "A304", "llm_selected_alpha_id": "A304",
            "claim": "x", "evidence": "the last four quarters support a trailing inflection, not a forward EPS of $15.72", "score": 0.0,
            "claim_quality": "analytical", "assertion_status": assertion_status, "eligible_candidates": [], "top_candidates": [candidate],
            "candidate_scores": [candidate], "matched_evidence_stance": stance}


def test_llm_supports_does_not_lift_a_text_rule_mention_into_the_activation_pool():
    # t3v3-005 / 006 as consumed: LLM selected A304, LLM direction supports_alpha, text rule relation=mention, assertion=negated
    eligible, excluded, _ = select_supporting_alpha_claims([_match(relation="mention", assertion_status="negated", stance="supports_alpha")], "A304")
    assert eligible == []
    assert excluded[0]["reason"] == REASON_RELATION_NOT_SUPPORTING


def test_the_negated_assertion_gate_still_applies_behind_the_relation_gate():
    eligible, excluded, _ = select_supporting_alpha_claims([_match(relation="activation", assertion_status="negated", stance="supports_alpha")], "A304")
    assert eligible == []
    assert excluded[0]["reason"] == REASON_ASSERTION_NEGATED


@pytest.mark.parametrize("relation", ["invalidation", "risk_relief", "mention"])
@pytest.mark.parametrize("stance", ["supports_alpha", "opposes_alpha", "neutral_background", "mentions_alpha"])
def test_text_rule_opposition_relief_and_mention_never_enter_the_pool_whatever_the_llm_direction(relation, stance):
    eligible, excluded, _ = select_supporting_alpha_claims([_match(relation=relation, assertion_status="asserted", stance=stance)], "A304")
    assert eligible == []
    assert excluded[0]["reason"] == REASON_RELATION_NOT_SUPPORTING


def test_the_selector_reads_the_mapper_relation_not_the_llm_direction():
    """Same text-rule relation, opposite LLM directions: identical selector outcome (the direction has no production authority)."""
    supports = select_supporting_alpha_claims([_match(relation="activation", assertion_status="asserted", stance="supports_alpha")], "A304")
    opposes = select_supporting_alpha_claims([_match(relation="activation", assertion_status="asserted", stance="opposes_alpha")], "A304")
    assert [r["claim_id"] for r in supports[0]] == [r["claim_id"] for r in opposes[0]]


@lru_cache(maxsize=1)
def _t3_006():
    spec = importlib.util.spec_from_file_location("t3_joint_driver_relation_tests", DRIVERS / "t3_joint_sample_driver.py")
    assert spec is not None and spec.loader is not None
    driver = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = driver
    spec.loader.exec_module(driver)
    samples = driver.load_samples(MANIFEST)
    for s in samples:
        driver.strip_saved_llm_content_verdict(s["record"])
    sample = next(s for s in samples if s["sample_id"] == "t3v3-006")
    item = next(i for v in driver.content_support_request_items(samples).values() for i in v if i.claim_id == sample["record"]["claim_id"])
    requests = [json.loads(line) for line in (CS_LOGS / "week2_llm_provider_request_audit.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    responses = {r["attempt_id"]: r for r in (json.loads(line) for line in (CS_LOGS / "week2_llm_provider_response_audit.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())}
    req = next(r for r in requests if r["claim_ids"] == [item.claim_id])
    reply = json.loads(json.loads(responses[req["attempt_id"]]["body"])["choices"][0]["message"]["content"])["items"][0]
    return item, reply, sample["sources"]


class _ReplayGateway:
    model_name, provider = "deepseek-v4-flash", "deepseek"

    def __init__(self, reply):
        self.reply = reply

    def invoke_json_with_trace(self, task, payload, validator):
        return SimpleNamespace(provider_attempt_count=1, provider_status="success", error_code=None, cache_hit=False, validation_accepted=True,
                               request_control=None, provider_response_metadata=None, token_usage=None, attempt_history=(),
                               validated_output=validator({"items": [self.reply]}))

    def finalize_semantic_invocation(self, invocation, accepted, fallback_reason=None):
        pass


def _verified(reply) -> dict:
    item, _, sources = _t3_006()
    results = {}
    cs._process_batch([item], _ReplayGateway(reply), cs.ContentSupportRunStats(), results)
    return compute_verified_support_eligibility(results[item.claim_id], sources)


def test_control_the_real_t3v3_006_supports_reply_is_verified_support():
    _, reply, _ = _t3_006()
    assert reply["status"] == "SUPPORTS"
    assert _verified(reply)["eligible"] is True


@pytest.mark.parametrize("status,remainder", [("BACKGROUND", ""), ("CITATION_ONLY", ""), ("INSUFFICIENT", ""), ("OPPOSES", ""),
                                              ("CONDITIONAL", "a condition the material leaves open"), ("SUPPORTS", "a material unsupported remainder")])
def test_background_citation_insufficient_opposing_and_conditional_verdicts_are_never_verified_support(status, remainder):
    """Same real request and the same real cited excerpt as the control; only the verdict differs (constructed reply)."""
    _, real, _ = _t3_006()
    reply = v2_response(claim_id=real["claim_id"], status=status, used_source_id=real["used_source_id"], used_location=real["used_location"],
                        supporting_quote_or_data=real["supporting_quote_or_data"], unsupported_remainder=remainder,
                        materiality="MATERIAL" if remainder else None)
    if status == "INSUFFICIENT":
        reply.update({"used_source_id": None, "used_location": None, "supporting_quote_or_data": None})
    verdict = _verified(reply)
    assert verdict["eligible"] is False, (status, verdict)
