"""2026-10-07 (round 19): the consumption contract between an LLM Alpha judgement and the official score -- pinned with PRODUCTION functions.

No production code was changed this round; these tests record, on fixed synthetic inputs, what the consumer does today and -- more
importantly -- what it refuses to do:
  * the Alpha classifier contract is exactly {decision, selected_alpha_id}: no relevance strength can arrive, and an extra field is rejected;
  * an LLM-selected Alpha whose deterministic lexical score is 0 stays a pool member with ZERO weight -- it is never defaulted to 1.0, never given a floor;
  * mention / negated / context-only / missing-score / absent-or-non-supporting stance are never upgraded into supporting evidence;
  * "the source supports the claim" (axis 1) and "the claim supports / opposes / only mentions the Alpha" (axis 2) are judged independently;
  * claims that share one source are not merged into one fact by the shared source alone, while a true restatement of the same fact is;
  * a Secondary-role restatement of a Primary analyst's fact adds no independent evidence;
  * missing weights never become a definite direction.

They prove WIRING (fixed inputs), not model quality or real market behaviour. The last test reads the saved AMD artifacts and is skipped if absent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.conflict_engine import conflict_admissibility as adm
from comqutor_alpha.graph_engine import activation_scorer_v2 as act
from comqutor_alpha.graph_engine import evidence_fact_index as efi
from comqutor_alpha.graph_engine.evidence_source_role import (
    REASON_PRIMARY_QUALIFIED,
    REASON_SECONDARY_DUPLICATE_OF_PRIMARY,
    qualify_evidence_group,
)
from comqutor_alpha.source_provenance import compute_verified_support_eligibility
from comqutor_alpha.structure_engine import claim_semantics as cs
from comqutor_alpha.structure_engine.alpha_mapper import _classify_alpha_with_llm, map_claim_to_alpha

TAXONOMY = load_alpha_taxonomy()
SELECTED_A301 = {"outcome": "selected", "alpha_id": "A301", "fallback_reason": None, "diagnostic": {"enabled": True, "used": True, "status": "llm_selected"}}


def _record(claim_id="t:fundamental_agent:report:claim:1", agent="fundamental_agent", text="The second quarter print re-accelerated sharply after a pause.", **extra):
    base = {"claim_id": claim_id, "agent": agent, "ticker": "AMD", "claim": text, "evidence": text, "factors": [], "direction": "unknown", "claim_quality": "analytical", "confidence": 0.7}
    base.update(extra)
    return base


class _Gateway:
    """Fixed-response stand-in for the Week2 gateway (invoke_json path): returns validate(payload), exactly as the real one does on acceptance."""

    semantic_runtime = None

    def __init__(self, payload):
        self.payload, self.requests = payload, []

    def invoke_json(self, task, request, validate):
        self.requests.append((task, request))
        return validate(self.payload)


# ---------------------------------------------------------------------------------------------------- the model contract
def test_classifier_output_contract_is_decision_and_alpha_id_only():
    gateway = _Gateway({"decision": "select", "selected_alpha_id": "A301"})
    out = _classify_alpha_with_llm(_record(), TAXONOMY, None, True, 5.0, gateway)
    assert (out["outcome"], out["alpha_id"]) == ("selected", "A301")
    task, request = gateway.requests[0]
    assert task == "alpha_classifier"
    assert set(request) == {"claim", "evidence", "ticker", "factors", "direction", "alpha_taxonomy"}  # what the model is shown; nothing asks for a strength


@pytest.mark.parametrize("extra", [{"relevance": 0.9}, {"strength": "direct"}, {"confidence": 0.8}, {"direction": "supports"}])
def test_an_extra_strength_or_direction_field_is_rejected_not_silently_accepted(extra):
    gateway = _Gateway({"decision": "select", "selected_alpha_id": "A301", **extra})
    out = _classify_alpha_with_llm(_record(), TAXONOMY, None, True, 5.0, gateway)
    assert out["outcome"] == "unavailable" and out["alpha_id"] is None  # never a half-accepted selection, never a NONE


# ---------------------------------------------------------------------------------------------------- weight: zero stays zero
def test_llm_selected_alpha_with_zero_lexical_score_is_a_pool_member_with_zero_weight():
    result = map_claim_to_alpha(_record(), TAXONOMY, llm_outcome_override=SELECTED_A301)
    candidate = next(c for c in result["candidate_scores"] if c["alpha_id"] == "A301")
    # authority split, visible in one record: the LLM decided the Alpha; the lexical rules produced the score
    assert result["matched_alpha"] == "A301" and result["match_status"] == "matched" and result["deterministic_match_status"] == "no_match"
    assert (candidate["keyword_score"], candidate["factor_score"], candidate["direction_score"], candidate["semantic_score"]) == (0.0, 0.0, 0.0, 0.0)
    assert result["score"] == 0.0 and candidate["eligible"] is False  # the deterministic path would never have matched it
    eligible, excluded, warnings = efi.select_supporting_alpha_claims([result], "A301")
    assert [r["claim_id"] for r in eligible] == [result["claim_id"]] and not excluded and not warnings  # it IS in the pool ...
    member = {"match_score": result["score"], "relation": efi.relation_for_match(result, "A301"), "assertion_status": result["assertion_status"]}
    raw, detail = act._evidence_quality_component({"g1": [member]})
    assert raw == 0.0 and detail["unique_semantic_groups"] == 1 and detail["unique_contribution_sum"] == 0.0  # ... counted as a fact, carrying NO weight


def test_a_missing_or_invalid_match_score_is_excluded_never_treated_as_full_weight():
    result = map_claim_to_alpha(_record(text="Revenue growth accelerated this quarter."), TAXONOMY, llm_outcome_override=SELECTED_A301)
    for bad in (None, "not-a-number", float("nan"), float("inf"), 1.7, -0.1):
        broken = {k: v for k, v in result.items() if k != "score"} if bad is None else {**result, "score": bad}
        eligible, excluded, warnings = efi.select_supporting_alpha_claims([broken], "A301")
        assert not eligible and excluded[0]["reason"] == efi.REASON_INVALID_MATCH_SCORE
        assert efi.WARNING_NON_FINITE_OR_OUT_OF_RANGE_MATCH_SCORE in warnings


def test_zero_weights_do_not_become_a_definite_direction():
    raw, meta = act._direction_consistency_component({"g": {"relation": "activation", "match_score": 0.0}})
    assert raw == 0.0 and meta["qualifying_group_count"] == 0
    assert act._direction_label_v2(meta, "A301") == "unknown"
    raw, meta = act._direction_consistency_component({"g": {"relation": "activation", "match_score": 0.1873}})
    assert act._direction_label_v2(meta, "A301") == "positive"  # direction exists only where a weight exists


# ---------------------------------------------------------------------------------------------------- nothing is upgraded
def _matched(text, **record_extra):
    return map_claim_to_alpha(_record(text=text, **record_extra), TAXONOMY, llm_outcome_override={**SELECTED_A301, "alpha_id": "A304"})


def test_mention_negated_and_context_only_are_never_upgraded_into_supporting_evidence():
    # a negation word is not a verdict either way: the text rule turns it into a mention, so it is excluded -- and stays "unresolved" for a model
    negated = _matched("The last four quarters support a trailing inflection, not a forward EPS of $15.72.")
    assert (negated["assertion_status"], negated["semantic_polarity"]) == ("negated", "mention")
    assert next(c for c in negated["candidate_scores"] if c["alpha_id"] == "A304")["relation"] == "mention"
    _, excluded, _ = efi.select_supporting_alpha_claims([negated], "A304")
    assert excluded[0]["reason"] == efi.REASON_RELATION_NOT_SUPPORTING
    # even with the relation forced to a supporting value, a negated assertion is still excluded and weighted 0.0
    forced = json.loads(json.dumps(negated))
    for pool in ("candidate_scores", "top_candidates", "eligible_candidates"):
        for candidate in forced.get(pool, []):
            if candidate["alpha_id"] == "A304":
                candidate["relation"] = "activation"
    _, excluded, _ = efi.select_supporting_alpha_claims([forced], "A304")
    assert excluded[0]["reason"] == efi.REASON_ASSERTION_NEGATED and act.ASSERTION_WEIGHTS["negated"] == 0.0
    # a verified-looking but context-only claim does not enter either
    context_only = _matched("Operating income swung from negative $134M to positive $1,990M.", claim_quality="context_only")
    _, excluded, _ = efi.select_supporting_alpha_claims([context_only], "A304")
    assert excluded[0]["reason"] == efi.REASON_NON_ANALYTICAL_QUALITY


def test_the_text_rule_gives_the_same_answer_for_opposing_rebutting_and_merely_mentioning_sentences():
    """SYNTHETIC sentences. Documents why a lexical rule cannot settle the claim-to-Alpha relation (it is not a judgement about any real claim)."""
    cases = [
        "AMD's valuation is not a risk because earnings growth fully supports the current multiple.",
        "The claim that a PEG of 0.64 makes the valuation safe does not hold, because the forward EPS it relies on has not appeared in any reported quarter.",
        "Valuation was not discussed in the meeting; the memo only mentions the multiple.",
    ]
    assert {(cs.analyze_claim_semantics(t).assertion_status, cs.alpha_relation(t, "A304")) for t in cases} == {("negated", "mention")}


@pytest.mark.parametrize("stance", ["mentions_alpha", "neutral_background", "opposes_alpha", "supports_counter_alpha", None, ""])
def test_only_an_explicit_supports_alpha_stance_counts_and_an_absent_stance_never_does(stance):
    candidate = {"alpha_id": "A304", "relation": "activation"}
    if stance is not None:
        candidate["evidence_stance"] = stance
    by_id = {"c1": {"claim_id": "c1", "candidate_scores": [candidate]}, "c2": {"claim_id": "c2"}}  # c2: no candidate entry at all
    assert adm._stance_filtered_qualifying([{"claim_id": "c1"}, {"claim_id": "c2"}], by_id, "A304") == []
    candidate["evidence_stance"] = "supports_alpha"
    assert [c["claim_id"] for c in adm._stance_filtered_qualifying([{"claim_id": "c1"}, {"claim_id": "c2"}], by_id, "A304")] == ["c1"]


# ---------------------------------------------------------------------------------------------------- two axes stay independent
def _verified_record(status, source):
    return {
        "claim_id": "c1", "source_link_status": "VALID", "linked_source_id": source["source_id"], "linked_source_ids": [source["source_id"]],
        "content_support_review": {"schema_version": "content_support_review.v1", "status": status, "method": "LLM_CONTENT_SUPPORT_VERIFIED", "claim_id": "c1",
                                   "linked_source_id": source["source_id"], "content_hash": source["content_hash"]},
    }


def test_source_support_and_alpha_relation_are_judged_independently():
    import hashlib

    excerpt = "AMD income statement (quarterly) Total Revenue: 2026-06-30=11536000000.0"
    source = {"source_id": "src_a", "source_type": "financial", "provider": "yfinance", "published_at": "2026-10-06T10:00:00", "retrieved_at": "2026-10-06T17:39:31Z", "excerpt": excerpt,
              "content_hash": hashlib.sha256(excerpt.encode()).hexdigest(), "fragment_id": "src_a:frag:0", "instrument": "AMD", "data_snapshot": {"line_item": "Total Revenue"}}
    sources = [source]
    # axis 1 satisfied (the source supports the claim) ...
    assert compute_verified_support_eligibility(_verified_record("SUPPORTS", source), sources)["eligible"] is True
    # ... says nothing about axis 2: a mention-only relation is still excluded from the Alpha's evidence
    mention = {"claim_id": "c1", "match_status": "matched", "matched_alpha": "A304", "score": 0.4, "claim": "x", "evidence": "x", "claim_quality": "analytical", "assertion_status": "asserted",
               "candidate_scores": [{"alpha_id": "A304", "relation": "mention"}]}
    assert efi.select_supporting_alpha_claims([mention], "A304")[1][0]["reason"] == efi.REASON_RELATION_NOT_SUPPORTING
    # and a claim that supports the Alpha perfectly does not become verified because it does: unresolved content support is not eligible
    for status in ("PENDING_REVIEW", "CONDITIONAL", "BACKGROUND"):
        assert compute_verified_support_eligibility(_verified_record(status, source), sources)["eligible"] is False
    assert compute_verified_support_eligibility(_verified_record("OPPOSES", source), sources)["reason_code"] == "SOURCE_OPPOSES_CLAIM"


# ---------------------------------------------------------------------------------------------------- independence of evidence
# sentences taken from the saved AMD run (three claims of one analyst that cite ONE income-statement snapshot)
AMD_31 = "Revenue grew from $7,685M (Q2'25) → $9,246M → $10,270M → $10,253M → $11,536M (Q2'26)."
AMD_33 = "The Q1'26 flat-to-down print ($10,253M vs $10,270M) was a pause, but Q2'26 re-accelerated sharply."
AMD_36 = "Gross profit nearly doubled YoY ($6,203M vs $3,059M)."


def _candidate(claim_id, text, source="src_stmt", **kw):
    return efi.EvidenceFactCandidate(claim_id=claim_id, claim_text=text, assertion_status="asserted", semantic_polarity="activation", linked_source_id=source, **kw)


def test_a_shared_source_alone_never_merges_different_facts():
    groups = efi.group_evidence_candidates([_candidate("a:31", AMD_31), _candidate("a:33", AMD_33), _candidate("a:36", AMD_36)], "AMD")
    assert len(groups) == 3  # one source, one agent, three distinct propositions: three groups, merged by nothing but identity of the fact


def test_a_true_restatement_of_the_same_fact_does_not_add_independent_evidence():
    groups = efi.group_evidence_candidates([_candidate("a:31", AMD_31), _candidate("b:21", AMD_31, source="src_stmt"), _candidate("c:10", AMD_31.replace("grew", "went"))], "AMD")
    assert len(groups) == 1


def test_a_secondary_restatement_of_a_primary_fact_is_not_independent_evidence():
    members = [{"claim_id": "a:31", "agent": "fundamental_agent"}, {"claim_id": "c:10", "agent": "aggressive_risk_analyst"}]
    out = {m["claim_id"]: m for m in qualify_evidence_group(members, is_ticker_specific=lambda _m: True)}
    assert out["a:31"]["activation_qualification_reason"] == REASON_PRIMARY_QUALIFIED and out["a:31"]["activation_eligible"]
    assert out["c:10"]["activation_qualification_reason"] == REASON_SECONDARY_DUPLICATE_OF_PRIMARY and not out["c:10"]["activation_eligible"]


def test_a_secondary_only_claim_needs_ticker_specific_asserted_activation_evidence():
    secondary = {"claim_id": "pm:10", "agent": "portfolio_manager", "relation": "mention", "assertion_status": "negated"}
    out = qualify_evidence_group([secondary], is_ticker_specific=lambda _m: False)[0]
    assert not out["activation_eligible"] and out["activation_qualification_reason"] == "SECONDARY_NOT_TICKER_SPECIFIC"
    out = qualify_evidence_group([{**secondary, "relation": "activation", "assertion_status": "asserted"}], is_ticker_specific=lambda _m: True)[0]
    assert out["activation_eligible"]  # only when it is ticker-specific AND an asserted activation relation


def test_agent_independence_is_not_manufactured_by_a_single_agent():
    raw, detail = act._agent_independence_component({"g1": [{"agent": "fundamental_agent"}], "g2": [{"agent": "fundamental_agent"}], "g3": [{"agent": "fundamental_agent"}]})
    assert detail["distinct_agents"] == 1 and detail["cross_agent_confirmed_groups"] == 0 and raw == pytest.approx(23.3333, abs=1e-4)  # 0.70 x (1/3) x 100, rounded to 4 dp by the component


# ---------------------------------------------------------------------------------------------------- the saved AMD run (skipped if absent)
REPO = Path(__file__).resolve().parents[1]
DERIVED = REPO / "outputs" / "runs" / "requal-20261007T174744Z-664040d6"
ROOT = "c904d4cc-dc09-495c-aec5-b056979948e1"


@pytest.mark.skipif(not (DERIVED / "alpha_matches.json").exists(), reason="saved AMD re-qualification execution not present")
def test_saved_amd_records_show_the_documented_consumption_chain():
    """REAL SAVED RECORDS (not synthetic). Reproduces, from the saved alpha_matches, the facts the round-19 report states."""
    matches = {m["claim_id"]: m for m in json.loads((DERIVED / "alpha_matches.json").read_text())["matches"]}

    def a301(n):
        return matches[f"{ROOT}:fundamental_agent:fundamentals_report:claim:{n}"]

    assert [a301(n)["score"] for n in (31, 33, 36)] == [0.1873, 0.0, 0.0]
    assert all(a301(n)["matched_alpha"] == "A301" and a301(n)["llm_selected_alpha_id"] == "A301" and a301(n)["deterministic_match_status"] == "no_match" for n in (31, 33, 36))
    assert all(efi.relation_for_match(a301(n), "A301") == "activation" for n in (31, 33, 36))
    pm = matches[f"{ROOT}:portfolio_manager:final_trade_decision:claim:10"]
    assert (pm["llm_selected_alpha_id"], pm["assertion_status"], pm["semantic_polarity"], pm["score"]) == ("A304", "negated", "mention", 0.0)
    assert efi.relation_for_match(pm, "A304") == "mention"
    assert efi.select_supporting_alpha_claims([pm], "A304")[1][0]["reason"] == efi.REASON_RELATION_NOT_SUPPORTING
