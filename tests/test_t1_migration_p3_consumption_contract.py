"""alpha_evidence_consumption.v2 (T1 follow-up migration, round 36): the contract, the R-1 stance exclusion and the name rule.

Synthetic records only -- no saved run, no model, no network, no database; it runs in a fresh clone.

What is proven here
  * R-1 uses an explicit ``positive_admission`` field, never a rewritten ``relation``; the original selection, stance, text
    relation, assertion, polarity and lexical score are untouched and the contract is additive (strip restores the payload);
  * MODEL_JUDGED needs a valid model result bound to the right claim and Alpha -- ``method == "llm"`` plus a legal label is not
    enough; an unjudged stance (missing / timeout / parse failure / fallback / unverifiable) never excludes anything;
  * a model "supports" cannot bypass the source gate or the text-rule gates; an exclusion for one Alpha never reaches another;
  * the reverse-evidence channel and DirectionConsistency inputs do not move;
  * the name rule: fixed matching conditions and counter-examples; "name present" is not "subject determined";
  * every entry that needs the decision (Activation, conflict side, unclassified findings) reads the same one;
  * failure is explicit: unknown contract version, ticker / pair mismatch, stale binding, tampered decision;
  * apply is idempotent and recomputes from today's inputs; the relevance block is a labelled fallback, not a model strength;
  * the default path adds no relevance request (P4 phase 1's experimental relevance task is registered but wired into no pipeline).
"""

from __future__ import annotations

import copy
import hashlib
import json

import pytest

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.conflict_engine.conflict_detector import _gather_qualifying_evidence
from comqutor_alpha.graph_engine import activation_scorer_v2 as scorer
from comqutor_alpha.graph_engine.company_attribution import (
    CATEGORY_ISSUER,
    CATEGORY_NONE,
    CATEGORY_OTHER_ONLY,
    CATEGORY_PRODUCT,
    CATEGORY_SYMBOL,
    LIMIT_NAME_PRESENCE,
    resolve_name_attribution,
)
from comqutor_alpha.graph_engine.evidence_consumption import (
    CONSUMPTION_BLOCK_KEY,
    CONSUMPTION_CONTRACT_V2,
    PAYLOAD_CONTRACT_KEY,
    R1_EXCLUDING_STANCES,
    REASON_BINDING_STALE,
    REASON_DECISION_INCONSISTENT,
    REASON_ILLEGAL_CONTRACT_VERSION,
    REASON_PAIR_MISMATCH,
    REASON_STANCE_MODEL_NOT_SUPPORTING,
    REASON_TICKER_MISMATCH,
    EvidenceConsumptionError,
    StanceLedgerIndex,
    apply_alpha_evidence_consumption,
    attribution_decision_for_record,
    block_for_match,
    load_stance_ledger,
    positive_admission_exclusion,
    strip_alpha_evidence_consumption,
    verify_payload,
)
from comqutor_alpha.graph_engine.evidence_fact_index import (
    REASON_RELATION_NOT_SUPPORTING,
    REASON_STANCE_NOT_SUPPORTING,
    relation_for_match,
    select_supporting_alpha_claims,
)
from comqutor_alpha.graph_engine.issuer_aliases import company_names_for_ticker
from comqutor_alpha.graph_engine.verified_evidence_gate import score_alpha_activations_v2_verified
from comqutor_alpha.structure_engine.evidence_stance import canonical_conflict_partners
from comqutor_alpha.structure_engine.evidence_stance_llm import LLM_CLASSIFIER_VERSION

V2 = CONSUMPTION_CONTRACT_V2
DET_VERSION = "evidence_stance.deterministic.v1"


# ---------------------------------------------------------------------------
# Synthetic builders
# ---------------------------------------------------------------------------


def make_candidate(alpha_id, *, relation="activation", score=0.5, stance="supports_alpha", method="llm", version=LLM_CLASSIFIER_VERSION,
                   fallback=None, counter=None, manual=False, band=None, codes=()):
    return {
        "alpha_id": alpha_id, "alpha_name": alpha_id, "score": score, "keyword_score": 0.5, "factor_score": 0.0, "direction_score": 0.0,
        "semantic_score": 0.0, "relation": relation, "eligible": True, "ai_gate_passed": True, "evidence_stance": stance,
        "stance_method": method, "evidence_stance_version": version, "stance_fallback_reason": fallback, "counter_alpha_id": counter,
        "requires_manual_review": manual, "stance_confidence_band": band, "stance_reason_codes": list(codes),
    }


def make_match(claim_id, text, *, alpha="A301", ticker="NVDA", score=0.5, relation="activation", assertion="asserted", polarity="activation",
               agent="fundamental_agent", status="matched", extra_candidates=(), **candidate_kwargs):
    candidate = make_candidate(alpha, relation=relation, score=score, **candidate_kwargs)
    candidates = [candidate, *extra_candidates]
    matched = status == "matched"
    return {
        "run_id": "r1", "ticker": ticker, "agent": agent, "claim_id": claim_id, "claim": text, "evidence": text, "match_status": status,
        "matched_alpha": alpha if matched else None, "score": score if matched else 0.0, "assertion_status": assertion,
        "semantic_polarity": polarity, "claim_quality": "analytical", "direction": "positive", "factors": [],
        "candidate_scores": candidates, "top_candidates": copy.deepcopy(candidates), "eligible_candidates": copy.deepcopy(candidates),
        "secondary_alphas": [], "llm_selected_alpha_id": alpha if matched else None, "alpha_match_method": "llm",
    }


def make_payload(*matches, ticker="NVDA"):
    return {"ticker": ticker, "matches": list(matches)}


def ledger_for(payload):
    """A ledger that holds an accepted validated output for every LLM-method pair in the payload (so corroboration succeeds)."""
    pairs = {}
    for m in payload["matches"]:
        if m.get("match_status") != "matched":
            continue
        cand = next(c for c in m["candidate_scores"] if c["alpha_id"] == m["matched_alpha"])
        if cand.get("stance_method") == "llm":
            pairs[(m["claim_id"], m["matched_alpha"])] = {(cand["evidence_stance"], cand.get("counter_alpha_id"))}
    return StanceLedgerIndex(pairs, path="synthetic", sha256="0" * 64, integrity="NO_MANIFEST", accepted_batches=1)


def apply_v2(payload, *, records=None, sources=None, ledger="auto", ticker=None):
    ticker = ticker or payload["ticker"]
    return apply_alpha_evidence_consumption(
        payload, records if records is not None else [], sources, ticker=ticker, contract=V2,
        ledger=ledger_for(payload) if ledger == "auto" else ledger,
    )


def block_of(payload, claim_id):
    match = next(m for m in payload["matches"] if m["claim_id"] == claim_id)
    return block_for_match(match)


def pool_ids(payload, alpha_id="A301"):
    eligible, excluded, _ = select_supporting_alpha_claims(payload["matches"], alpha_id)
    return [r["claim_id"] for r in eligible], {e["claim_id"]: e for e in excluded}


# ---------------------------------------------------------------------------
# R-1: the explicit positive-admission field
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("label", ["supports_alpha", "opposes_alpha", "mentions_alpha", "neutral_background", "supports_counter_alpha"])
def test_r1_excludes_exactly_the_four_approved_labels_and_only_through_the_explicit_field(label):
    taxonomy = load_alpha_taxonomy()
    counter = sorted(canonical_conflict_partners("A301", taxonomy))
    if label == "supports_counter_alpha" and not counter:
        pytest.skip("A301 declares no conflict partner in this taxonomy")
    payload = make_payload(make_match("c1", "Revenue at NVIDIA grew.", stance=label, counter=counter[0] if label == "supports_counter_alpha" else None))
    apply_v2(payload)
    block = block_of(payload, "c1")
    admitted_ids, excluded = pool_ids(payload)
    if label in R1_EXCLUDING_STANCES:
        assert block["positive_admission"] == {"admitted": False, "reason_code": REASON_STANCE_MODEL_NOT_SUPPORTING, "label": label, "policy": "alpha_stance_policy.v1"}
        assert admitted_ids == [] and excluded["c1"]["reason"] == REASON_STANCE_NOT_SUPPORTING == REASON_STANCE_MODEL_NOT_SUPPORTING
    else:
        assert block["positive_admission"]["admitted"] is True and admitted_ids == ["c1"]


def test_r1_never_rewrites_relation_selection_stance_assertion_or_score_and_the_contract_is_additive():
    original = make_payload(
        make_match("c1", "Revenue at NVIDIA grew.", stance="opposes_alpha"),
        make_match("c2", "Revenue is not slowing at NVIDIA.", relation="mention", assertion="negated", stance="supports_alpha"),
        make_match("c3", "Macro chatter.", status="no_match", stance="mentions_alpha"),
    )
    payload = copy.deepcopy(original)
    apply_v2(payload)
    for before, after in zip(original["matches"], payload["matches"], strict=True):
        for key in ("matched_alpha", "match_status", "llm_selected_alpha_id", "assertion_status", "semantic_polarity", "score", "direction"):
            assert before[key] == after[key]
        assert relation_for_match(before, "A301") == relation_for_match(after, "A301")
        assert [(c["alpha_id"], c["relation"], c["evidence_stance"], c["stance_method"]) for c in before["candidate_scores"]] == \
               [(c["alpha_id"], c["relation"], c["evidence_stance"], c["stance_method"]) for c in after["candidate_scores"]]
    assert payload[PAYLOAD_CONTRACT_KEY] == V2
    assert strip_alpha_evidence_consumption(payload) is True
    assert payload == original and json.dumps(payload, sort_keys=False) == json.dumps(original, sort_keys=False)  # byte-identical once serialised


def test_apply_is_idempotent_and_strip_on_a_legacy_payload_is_a_no_op():
    payload = make_payload(make_match("c1", "Revenue at NVIDIA grew.", stance="opposes_alpha"), make_match("c2", "Other.", status="no_match"))
    apply_v2(payload)
    once = copy.deepcopy(payload)
    apply_v2(payload)
    assert payload == once
    legacy = make_payload(make_match("c1", "Revenue at NVIDIA grew."))
    assert strip_alpha_evidence_consumption(legacy) is False and legacy == make_payload(make_match("c1", "Revenue at NVIDIA grew."))


def test_a_model_support_never_admits_a_claim_the_text_rule_or_the_source_gate_rejects():
    payload = make_payload(make_match("c1", "Revenue at NVIDIA did not slow.", relation="mention", assertion="negated", stance="supports_alpha"))
    apply_v2(payload)
    assert block_of(payload, "c1")["positive_admission"]["admitted"] is True  # the stance policy has no objection ...
    ids, excluded = pool_ids(payload)
    assert ids == [] and excluded["c1"]["reason"] == REASON_RELATION_NOT_SUPPORTING  # ... but the text-rule gate still decides (no R-2)

    sourced = make_payload(make_match("c2", "Revenue at NVIDIA grew.", stance="supports_alpha"))
    apply_v2(sourced)
    unlinked = [{"claim_id": "c2", "source_link_status": "NOT_PROVIDED", "linked_source_id": None}]
    activation = score_alpha_activations_v2_verified(sourced, structured_records=unlinked, sources=[], ticker="NVDA", company_names=company_names_for_ticker("NVDA"))
    a301 = next(a for a in activation["alphas"] if a["alpha_id"] == "A301")
    assert pool_ids(sourced)[0] == ["c2"]  # the raw selector admits it ...
    assert a301["evidence_count"] == 0  # ... the source gate (separate, unchanged) keeps it out of the verified result


@pytest.mark.parametrize(
    "candidate_kwargs, category, reason",
    [
        ({"method": None}, "MISSING", "no_stance_result"),
        ({"method": "deterministic_fallback", "version": DET_VERSION, "fallback": "missing_result", "band": "high", "codes": ["X"]}, "MISSING", "missing_result"),
        ({"method": "deterministic_fallback", "version": DET_VERSION, "fallback": "timeout", "band": "high", "codes": ["X"]}, "TIMEOUT", "timeout"),
        ({"method": "deterministic_fallback", "version": DET_VERSION, "fallback": "malformed_response", "band": "high", "codes": ["X"]}, "PARSE_FAILED", "malformed_response"),
        ({"method": "deterministic_fallback", "version": DET_VERSION, "fallback": "invalid_stance", "band": "high", "codes": ["X"]}, "PARSE_FAILED", "invalid_stance"),
        ({"method": "deterministic_fallback", "version": DET_VERSION, "fallback": "identity_mismatch", "band": "high", "codes": ["X"]}, "PARSE_FAILED", "identity_mismatch"),
        ({"method": "deterministic_fallback", "version": DET_VERSION, "fallback": "provider_error", "band": "high", "codes": ["X"]}, "FALLBACK", "provider_error"),
        ({"method": "deterministic_fallback", "version": DET_VERSION, "fallback": "input_too_large", "band": "high", "codes": ["X"]}, "FALLBACK", "input_too_large"),
        ({"method": "deterministic_fallback", "version": DET_VERSION, "fallback": "provider_stopped", "band": "high", "codes": ["X"]}, "FALLBACK", "provider_stopped"),
        ({"method": "carrier_pigeon"}, "UNVERIFIED", "unknown_method"),
    ],
)
def test_an_unjudged_stance_never_excludes_and_is_disclosed_by_its_own_category(candidate_kwargs, category, reason):
    # the unjudged candidate carries the label a deterministic classifier would have produced -- an "opposes" one, to prove
    # that it is NOT read as an explicit opposition
    payload = make_payload(make_match("c1", "Revenue at NVIDIA grew.", stance="opposes_alpha", **candidate_kwargs))
    summary = apply_v2(payload)
    block = block_of(payload, "c1")
    assert block["stance"]["state"] == "UNJUDGED" and block["stance"]["unjudged_category"] == category and block["stance"]["unjudged_reason"] == reason
    assert block["positive_admission"]["admitted"] is True and pool_ids(payload)[0] == ["c1"]
    assert summary["stance"]["unjudged_by_category"] == {category: 1} and summary["stance"]["unjudged_by_reason"] == {reason: 1}


@pytest.mark.parametrize(
    "mutate, reason",
    [
        (lambda c, m: c.update(evidence_stance_version="evidence_stance.llm.v0"), "version_mismatch"),
        (lambda c, m: c.update(stance_fallback_reason="timeout"), "fallback_reason_on_model_result"),
        (lambda c, m: c.update(evidence_stance="supports_everything"), "illegal_label"),
        (lambda c, m: c.update(requires_manual_review=True), "manual_review_flag"),
        (lambda c, m: c.update(stance_confidence_band="high"), "deterministic_residue_on_model_result"),
        (lambda c, m: c.update(stance_reason_codes=["RISK_ALPHA_ACTIVATION"]), "deterministic_residue_on_model_result"),
        (lambda c, m: c.update(counter_alpha_id="A304"), "counter_alpha_unexpected"),
        (lambda c, m: m["top_candidates"][0].update(evidence_stance="supports_alpha"), "candidate_copies_disagree"),
    ],
)
def test_method_llm_plus_a_legal_label_is_not_enough_for_model_judged(mutate, reason):
    payload = make_payload(make_match("c1", "Revenue at NVIDIA grew.", stance="opposes_alpha"))
    match = payload["matches"][0]
    mutate(match["candidate_scores"][0], match)
    apply_v2(payload, ledger=ledger_for(make_payload(make_match("c1", "x", stance="opposes_alpha"))))
    stance = block_of(payload, "c1")["stance"]
    assert stance["state"] == "UNJUDGED" and stance["unjudged_category"] == "UNVERIFIED" and stance["unjudged_reason"] == reason
    assert block_of(payload, "c1")["positive_admission"]["admitted"] is True


def test_supports_counter_alpha_needs_a_legal_counter_alpha():
    taxonomy = load_alpha_taxonomy()
    partners = sorted(canonical_conflict_partners("A301", taxonomy))
    if not partners:
        pytest.skip("A301 declares no conflict partner in this taxonomy")
    for counter, expected in ((partners[0], "MODEL_JUDGED"), (None, "UNJUDGED"), ("A301", "UNJUDGED"), ("A999", "UNJUDGED")):
        payload = make_payload(make_match("c1", "Revenue at NVIDIA grew.", stance="supports_counter_alpha", counter=counter))
        apply_v2(payload)
        assert block_of(payload, "c1")["stance"]["state"] == expected, counter


def test_a_model_result_must_be_corroborated_by_the_runs_own_validated_ledger_output():
    base = make_payload(make_match("c1", "Revenue at NVIDIA grew.", stance="opposes_alpha"))
    cases = {
        "ledger_unavailable": None,
        "pair_not_in_ledger": StanceLedgerIndex({}, path="x", sha256="0", integrity="NO_MANIFEST", accepted_batches=1),
        "ledger_label_mismatch": StanceLedgerIndex({("c1", "A301"): {("supports_alpha", None)}}, path="x", sha256="0", integrity="NO_MANIFEST", accepted_batches=1),
        "ledger_conflict": StanceLedgerIndex({("c1", "A301"): {("opposes_alpha", None), ("supports_alpha", None)}}, path="x", sha256="0", integrity="NO_MANIFEST", accepted_batches=1),
        "ledger_integrity_failed": StanceLedgerIndex({("c1", "A301"): {("opposes_alpha", None)}}, path="x", sha256="0", integrity="MISMATCH_MANIFEST", accepted_batches=1),
    }
    for reason, ledger in cases.items():
        payload = copy.deepcopy(base)
        apply_v2(payload, ledger=ledger)
        stance = block_of(payload, "c1")["stance"]
        assert (stance["state"], stance["unjudged_reason"]) == ("UNJUDGED", reason), reason
        assert block_of(payload, "c1")["positive_admission"]["admitted"] is True
    corroborated = copy.deepcopy(base)
    apply_v2(corroborated)
    assert block_of(corroborated, "c1")["stance"]["state"] == "MODEL_JUDGED" and block_of(corroborated, "c1")["stance"]["ledger"] == "VERIFIED"


def test_the_stance_ledger_index_reads_accepted_outputs_only_and_checks_the_manifest_hash(tmp_path):
    def record(status, validation, items):
        return {"task": "evidence_stance_classifier", "provider_status": status, "validation_status": validation, "validated_output": {"items": items}}

    lines = [
        record("success", "accepted", [{"claim_id": "c1", "target_alpha_id": "A301", "stance": "opposes_alpha"}]),
        record("success", "rejected", [{"claim_id": "c2", "target_alpha_id": "A301", "stance": "supports_alpha"}]),
        record("timeout", "accepted", [{"claim_id": "c3", "target_alpha_id": "A301", "stance": "supports_alpha"}]),
        {"task": "alpha_classifier", "provider_status": "success", "validation_status": "accepted", "validated_output": {"items": [{"claim_id": "c4", "target_alpha_id": "A301", "stance": "x"}]}},
    ]
    ledger_path = tmp_path / "llm_semantic_calls.jsonl"
    ledger_path.write_text("\n".join(json.dumps(r) for r in lines) + "\n", encoding="utf-8")
    sha = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
    (tmp_path / "llm_semantic_manifest.json").write_text(json.dumps({"calls_file_sha256": sha}), encoding="utf-8")
    index = load_stance_ledger(tmp_path)
    assert index.pairs == {("c1", "A301"): {("opposes_alpha", None)}} and index.integrity == "MATCHES_MANIFEST" and index.usable
    (tmp_path / "llm_semantic_manifest.json").write_text(json.dumps({"calls_file_sha256": "0" * 64}), encoding="utf-8")
    assert load_stance_ledger(tmp_path).integrity == "MISMATCH_MANIFEST" and not load_stance_ledger(tmp_path).usable
    (tmp_path / "llm_semantic_manifest.json").unlink()
    assert load_stance_ledger(tmp_path).integrity == "NO_MANIFEST"
    assert load_stance_ledger(tmp_path / "missing") is None


def test_an_exclusion_for_one_alpha_never_reaches_another_alpha_or_another_claim():
    a, b = make_match("cA", "Revenue at NVIDIA grew.", alpha="A301", stance="opposes_alpha"), make_match("cB", "Valuation multiples compress.", alpha="A304", stance="supports_alpha")
    payload = make_payload(a, b)
    apply_v2(payload)
    assert pool_ids(payload, "A301")[0] == [] and pool_ids(payload, "A304")[0] == ["cB"]
    assert positive_admission_exclusion(payload["matches"][0], "A304") is None  # asking for another Alpha never returns A301's exclusion
    assert block_of(payload, "cB")["positive_admission"]["admitted"] is True


def test_a_record_rematched_after_the_contract_was_applied_fails_explicitly_instead_of_ignoring_a_stray_block():
    payload = make_payload(make_match("c1", "Revenue at NVIDIA grew.", alpha="A301", stance="opposes_alpha", extra_candidates=[make_candidate("A304")]))
    apply_v2(payload)
    match = payload["matches"][0]
    match["matched_alpha"] = "A304"  # a later step re-matched the claim; A301's block is now stray
    with pytest.raises(EvidenceConsumptionError) as raised:
        positive_admission_exclusion(match, "A304")
    assert raised.value.reason_code == REASON_PAIR_MISMATCH
    with pytest.raises(EvidenceConsumptionError):
        attribution_decision_for_record(match, "NVDA")
    match["match_status"] = "no_match"  # un-matched: still a stray block
    with pytest.raises(EvidenceConsumptionError):
        attribution_decision_for_record(match, "NVDA")


def test_reverse_evidence_is_unchanged_and_r1_exclusions_no_longer_count_as_positive_direction():
    # Round 36 kept DirectionConsistency untouched by R-1; on 2026-10-13 the owner's instruction (John's T3 037 / 038 / 040: a
    # ledger-corroborated opposition must not be promoted to positive support by the old text-rule label) added
    # alpha_direction_stance_policy.v1: a claim R-1 keeps out of the positive pool is not POSITIVE direction evidence either.
    # Negative and neutral signs (the reverse-evidence channel) are unchanged.
    payload = make_payload(
        make_match("inv", "NVIDIA revenue growth is invalidated by the guidance cut.", relation="invalidation", stance="opposes_alpha", polarity="invalidation"),
        make_match("opp", "Revenue at NVIDIA grew.", stance="opposes_alpha"),  # text relation 'activation' but a model-judged opposition
        make_match("sup", "Revenue at NVIDIA accelerated.", stance="supports_alpha"),
    )
    before = scorer._gather_direction_evidence(payload, "A301", {})  # noqa: SLF001
    apply_v2(payload)
    after = scorer._gather_direction_evidence(payload, "A301", {})  # noqa: SLF001
    assert sorted(v["relation"] for v in before.values()) == ["activation", "activation", "invalidation"]
    assert sorted(v["relation"] for v in after.values()) == ["activation", "invalidation"]  # "opp" no longer counts as positive
    assert {k: v for k, v in before.items() if v["relation"] == "invalidation"} == {k: v for k, v in after.items() if v["relation"] == "invalidation"}
    assert scorer._direction_consistency_component(after)[0] < scorer._direction_consistency_component(before)[0]  # noqa: SLF001
    assert pool_ids(payload)[0] == ["sup"]


def test_the_conflict_side_pool_is_not_changed_by_the_stance_policy():
    payload = make_payload(make_match("opp", "Revenue at NVIDIA grew.", stance="opposes_alpha"), make_match("sup", "Revenue at NVIDIA accelerated.", stance="supports_alpha"))
    legacy_ids = [q["claim_id"] for q in _gather_qualifying_evidence("A301", payload["matches"], {}).qualifying]
    apply_v2(payload)
    v2_members = _gather_qualifying_evidence("A301", payload["matches"], {}).qualifying
    assert [q["claim_id"] for q in v2_members] == legacy_ids == ["opp", "sup"]  # R-1 is not applied to B2 / conflict scoring inputs
    assert all(CONSUMPTION_BLOCK_KEY in q and set(q[CONSUMPTION_BLOCK_KEY]) == {"contract", "ticker", "claim_id", "alpha_id", "attribution"} for q in v2_members)


# ---------------------------------------------------------------------------
# Failure states: explicit, never a silent fallback
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("contract", ["v3", "alpha_evidence_consumption.v1", "", 2, True, 1.0, None, [V2], {"contract": V2}])
def test_an_unknown_contract_version_fails_explicitly_and_leaves_the_payload_untouched(contract):
    payload = make_payload(make_match("c1", "Revenue at NVIDIA grew."))
    original = copy.deepcopy(payload)
    with pytest.raises(EvidenceConsumptionError) as raised:
        apply_alpha_evidence_consumption(payload, [], None, ticker="NVDA", contract=contract)
    assert raised.value.reason_code == REASON_ILLEGAL_CONTRACT_VERSION and payload == original


def test_ticker_mismatches_fail_explicitly():
    with pytest.raises(EvidenceConsumptionError) as raised:
        apply_alpha_evidence_consumption(make_payload(make_match("c1", "x"), ticker="NVDA"), [], None, ticker="AMD", contract=V2)
    assert raised.value.reason_code == REASON_TICKER_MISMATCH
    foreign = make_payload(make_match("c1", "x", ticker="AMD"), ticker="NVDA")
    with pytest.raises(EvidenceConsumptionError) as raised:
        apply_alpha_evidence_consumption(foreign, [], None, ticker="NVDA", contract=V2)
    assert raised.value.reason_code == REASON_TICKER_MISMATCH
    payload = make_payload(make_match("c1", "Revenue at NVIDIA grew."))
    apply_v2(payload)
    with pytest.raises(EvidenceConsumptionError) as raised:  # a gate reading the block under another target ticker
        attribution_decision_for_record(payload["matches"][0], "AMD")
    assert raised.value.reason_code == REASON_TICKER_MISMATCH


def test_a_stale_binding_fails_at_every_gate_and_is_reported_by_the_verifier():
    for tamper in (lambda m: m["candidate_scores"][0].update(evidence_stance="supports_alpha"),
                   lambda m: m.update(claim="Revenue at NVIDIA collapsed."),
                   lambda m: m.update(score=0.9),
                   lambda m: m["candidate_scores"][0].update(relation="mention")):
        payload = make_payload(make_match("c1", "Revenue at NVIDIA grew.", stance="opposes_alpha"))
        apply_v2(payload)
        tamper(payload["matches"][0])
        with pytest.raises(EvidenceConsumptionError) as raised:
            select_supporting_alpha_claims(payload["matches"], "A301")
        assert raised.value.reason_code == REASON_BINDING_STALE
        assert verify_payload(payload, [], None, ticker="NVDA")[0]["state"] == f"INVALID:{REASON_BINDING_STALE}"


def test_a_tampered_decision_that_contradicts_its_own_stance_is_detected():
    payload = make_payload(make_match("c1", "Revenue at NVIDIA grew.", stance="opposes_alpha"))
    apply_v2(payload)
    block_of(payload, "c1")["positive_admission"] = {"admitted": True, "reason_code": None, "label": None, "policy": "alpha_stance_policy.v1"}
    with pytest.raises(EvidenceConsumptionError) as raised:
        select_supporting_alpha_claims(payload["matches"], "A301")
    assert raised.value.reason_code == REASON_DECISION_INCONSISTENT


def _tamper_block(payload, change):
    change(block_of(payload, "c1"))


@pytest.mark.parametrize(
    "change, reason",
    [
        (lambda b: b.update(contract=[V2]), REASON_ILLEGAL_CONTRACT_VERSION),
        (lambda b: b.update(contract={"v": V2}), REASON_ILLEGAL_CONTRACT_VERSION),
        (lambda b: b.update(binding="sha"), REASON_BINDING_STALE),
        (lambda b: b.update(binding=None), REASON_BINDING_STALE),
        (lambda b: b["binding"].update(input_sha256="0" * 64), REASON_BINDING_STALE),
        (lambda b: b.update(stance=["MODEL_JUDGED"]), REASON_DECISION_INCONSISTENT),
        (lambda b: b.update(positive_admission="admitted"), REASON_DECISION_INCONSISTENT),
        (lambda b: b.update(attribution=["TARGET_NAME_SYMBOL"]), REASON_DECISION_INCONSISTENT),
        (lambda b: b["attribution"].update(ticker_specific="false"), REASON_DECISION_INCONSISTENT),
        (lambda b: b["attribution"].update(ticker_specific=False, category=CATEGORY_NONE), REASON_DECISION_INCONSISTENT),
    ],
)
def test_a_malformed_or_separately_edited_block_fails_with_the_contracts_own_code_never_a_generic_error(change, reason):
    payload = make_payload(make_match("c1", "Revenue at NVIDIA grew."))
    apply_v2(payload)
    _tamper_block(payload, change)
    for entry in (lambda: select_supporting_alpha_claims(payload["matches"], "A301"),
                  lambda: attribution_decision_for_record(payload["matches"][0], "NVDA")):
        with pytest.raises(EvidenceConsumptionError) as raised:
            entry()
        assert raised.value.reason_code == reason
    assert verify_payload(payload, [], None, ticker="NVDA", ledger=ledger_for(payload))[0]["state"] == f"INVALID:{reason}"


def test_a_pass_through_member_with_a_non_boolean_name_decision_is_rejected_not_coerced():
    member = {"claim_id": "c1", "consumption": {"contract": V2, "ticker": "NVDA", "claim_id": "c1", "alpha_id": "A301", "attribution": {"ticker_specific": "false"}}}
    with pytest.raises(EvidenceConsumptionError) as raised:
        attribution_decision_for_record(member, "NVDA")
    assert raised.value.reason_code == REASON_DECISION_INCONSISTENT  # bool("false") would have been True: a silent misread
    member["consumption"]["attribution"] = ["ticker_specific"]
    with pytest.raises(EvidenceConsumptionError):
        attribution_decision_for_record(member, "NVDA")


def test_reapplying_recomputes_from_todays_source_state_and_the_old_block_is_reported_stale():
    payload = make_payload(make_match("c1", "Revenue at NVIDIA grew."))
    record = {"claim_id": "c1", "source_link_status": "NOT_PROVIDED", "linked_source_id": None, "content_support_status": "NOT_APPLICABLE"}
    apply_v2(payload, records=[record])
    first = copy.deepcopy(block_of(payload, "c1"))
    assert first["source_support"]["verified_eligible"] is False
    changed = dict(record, source_link_status="CANDIDATE_ONLY", content_support_status="PENDING_REVIEW")  # the verification moved
    assert verify_payload(payload, [changed], None, ticker="NVDA", ledger=ledger_for(payload))[0]["state"] == "STALE"
    apply_v2(payload, records=[changed])
    second = block_of(payload, "c1")
    assert second["binding"]["source_state_sha256"] != first["binding"]["source_state_sha256"]
    assert verify_payload(payload, [changed], None, ticker="NVDA", ledger=ledger_for(payload))[0]["state"] == "CURRENT"
    assert second["binding"]["input_sha256"] == first["binding"]["input_sha256"]  # the record-level inputs did not change


def test_the_relevance_block_is_a_labelled_lexical_fallback_never_a_model_strength():
    payload = make_payload(make_match("zero", "Revenue at NVIDIA grew.", score=0.0), make_match("some", "Revenue at NVIDIA accelerated.", score=0.1873))
    summary = apply_v2(payload)
    for claim_id, expected in (("zero", 0.0), ("some", 0.1873)):
        relevance = block_of(payload, claim_id)["relevance"]
        assert relevance["model_weight"] is None and relevance["model_level"] is None and relevance["state"] == "UNJUDGED"
        assert relevance["lexical_baseline"] == relevance["effective_weight"] == expected  # a truly-zero lexical score stays 0.0 and is labelled
        assert relevance["weight_authority"] == "LEXICAL_RULE_FALLBACK"
        assert next(m for m in payload["matches"] if m["claim_id"] == claim_id)["score"] == expected  # what the scorers consume is untouched
    assert summary["relevance"]["model_weights"] == 0 and summary["relevance"]["lexical_zero_pairs"] == 1


def test_the_default_path_adds_no_relevance_request():
    """P4 phase 1 (2026-10-12) registered an experimental relevance task (``alpha_relevance_judge``) for the semantic recorder. The
    consumption contract still cannot send anything: it takes no gateway, the task has no entry in the Week 2 prompt tables, and only
    the explicit experiment entry runs it (proved in tests/test_p4_alpha_relevance_contract.py and ..._chain.py)."""
    from comqutor_alpha.llm_runtime.contracts import SEMANTIC_TASKS
    from comqutor_alpha.structure_engine import week2_llm
    from comqutor_alpha.structure_engine.alpha_relevance_llm import LLM_TASK_NAME

    assert [name for name in SEMANTIC_TASKS if "relevance" in name] == [LLM_TASK_NAME]
    assert not [name for name in week2_llm._TASK_INSTRUCTIONS if "relevance" in name]  # noqa: SLF001
    assert not [name for name in week2_llm._TASK_RUNTIME_METADATA if "relevance" in name]  # noqa: SLF001
    import inspect

    assert "gateway" not in inspect.signature(apply_alpha_evidence_consumption).parameters  # the contract is pure: it can send nothing


# ---------------------------------------------------------------------------
# The name rule: fixed matching conditions and counter-examples
# ---------------------------------------------------------------------------

NAME_CASES = [
    # (ticker, text, category, target name present)
    ("AMD", "AMD guided data-center revenue higher.", CATEGORY_SYMBOL, True),
    ("AMD", "amd guided data-center revenue higher.", CATEGORY_SYMBOL, True),  # the symbol is case-insensitive (long-standing behaviour)
    ("AMD", "Advanced Micro Devices, Inc.", CATEGORY_ISSUER, True),  # the full name is equivalent to the symbol
    ("AMD", "Advanced Micro Devices raised guidance.", CATEGORY_ISSUER, True),
    ("AMD", "AMD Instinct MI300X shipments ramp.", CATEGORY_SYMBOL, True),
    ("AMD", "Instinct MI325X demand is strong.", CATEGORY_PRODUCT, True),  # product alias with a model code
    ("AMD", "Instinct GPUs are gaining share.", CATEGORY_PRODUCT, True),
    ("AMD", "GPUs (Instinct data-center accelerators, Radeon) and EPYC servers.", CATEGORY_PRODUCT, True),
    ("AMD", "EPYC server share is rising.", CATEGORY_PRODUCT, True),
    ("AMD", "Ryzen AI notebooks launch.", CATEGORY_PRODUCT, True),
    # counter-examples: ordinary words and context-free aliases never count
    ("AMD", "Your instinct is going to be that a 167x multiple is a screaming sell.", CATEGORY_NONE, False),
    ("AMD", "Instinct says hold.", CATEGORY_NONE, False),  # capitalised, but no product context
    ("AMD", "Instinct is that GPUs will win.", CATEGORY_NONE, False),  # product noun not directly attached
    ("AMD", "survival instincts", CATEGORY_NONE, False),
    ("AMD", "ryzen is spelled in lower case here", CATEGORY_NONE, False),  # product aliases are case-sensitive
    ("AMD", "the instinct mi300x ramps", CATEGORY_NONE, False),  # lower case WITH a product context still does not count
    ("AMD", "instinct accelerators sell well", CATEGORY_NONE, False),
    ("AMD", "INSTINCT GPUs sell well", CATEGORY_NONE, False),  # only the brand's own casing counts
    ("AMD", "the epyc server share", CATEGORY_NONE, False),
    ("AMD", "AMDX is a different ticker.", CATEGORY_NONE, False),  # whole token only
    ("AMD", "Advanced Micro is a partial name.", CATEGORY_NONE, False),
    ("AMD", "Radeon and Xilinx are not registered names.", CATEGORY_NONE, False),
    ("AMD", "Nasdaq, Nvidia post record highs as tech strength outshines bond weakness.", CATEGORY_OTHER_ONLY, False),  # peer only
    ("AMD", "Semiconductor demand is rising across the industry.", CATEGORY_NONE, False),  # industry statement
    ("NVDA", "NVIDIA Corporation reported record revenue.", CATEGORY_ISSUER, True),
    ("NVDA", "Nvidia-backed Firmus is set to postpone its IPO.", CATEGORY_ISSUER, True),  # KNOWN LIMITATION: name present, subject is Firmus
    ("NVDA", "[10-06] AMD breakout post that cites 'NVDA run gave me some confidence'.", CATEGORY_SYMBOL, True),
    ("NVDA", "Prediction markets for TSMC (12%), OpenAI (14%) and Anduril (25%).", CATEGORY_OTHER_ONLY, False),
]


@pytest.mark.parametrize("ticker, text, category, present", NAME_CASES)
def test_name_rule_fixed_matching_conditions(ticker, text, category, present):
    result = resolve_name_attribution({"claim": text}, ticker)
    assert (result["category"], result["ticker_specific"]) == (category, present), text
    assert result["subject_determined"] is False  # name presence is never claimed to be the subject
    assert (LIMIT_NAME_PRESENCE in result["limits"]) is present


def test_the_known_limitation_name_present_is_not_subject_determined_is_explicit():
    result = resolve_name_attribution({"claim": "Nvidia-backed Firmus is set to postpone its IPO."}, "NVDA")
    assert result["ticker_specific"] is True and result["subject_determined"] is False and LIMIT_NAME_PRESENCE in result["limits"]


def test_the_run_ticker_entities_and_provider_never_prove_attribution():
    match = make_match("c1", "Semiconductor demand is rising across the industry.", ticker="AMD")
    match["entities"] = ["AMD"]
    match["source_provider"] = "AMD News Feed"
    payload = make_payload(match, ticker="AMD")
    apply_v2(payload)
    assert block_of(payload, "c1")["attribution"]["category"] == CATEGORY_NONE
    assert scorer._is_ticker_specific(payload["matches"][0], "AMD", company_names_for_ticker("AMD"), {"c1": ["AMD"]}) is False  # noqa: SLF001


def test_target_by_source_object_is_disabled_even_with_a_perfect_data_source():
    match = make_match("c1", "Revenue grew 106% from $46.7B to $96.2B in four quarters.", ticker="NVDA")
    record = {"claim_id": "c1", "source_link_status": "VALID", "linked_source_id": "src_x", "content_support_status": "SUPPORTS"}
    source = {"source_id": "src_x", "source_type": "financial", "instrument": "NVDA", "data_snapshot": {"line_item": "Total Revenue"}}
    payload = make_payload(match)
    apply_v2(payload, records=[record], sources=[source])
    attribution = block_of(payload, "c1")["attribution"]
    assert attribution["category"] == CATEGORY_NONE and attribution["ticker_specific"] is False
    assert payload["matches"][0]["candidate_scores"][0][CONSUMPTION_BLOCK_KEY]["attribution"]["policy"] == "company_attribution.name.v1"


def test_every_entry_reads_the_same_name_decision():
    texts = {"full": "Advanced Micro Devices raised guidance.", "none": "Semiconductor demand is rising.", "inst": "Your instinct is going to be hold.", "sym": "AMD raised guidance."}
    matches = [make_match(k, t, ticker="AMD", alpha="A101") for k, t in texts.items()]
    unmatched = make_match("um", "Advanced Micro Devices said nothing about Alphas.", ticker="AMD", status="no_match")
    legacy = make_payload(*copy.deepcopy(matches), copy.deepcopy(unmatched), ticker="AMD")
    payload = make_payload(*matches, unmatched, ticker="AMD")
    apply_v2(payload)
    names = company_names_for_ticker("AMD")
    expected = {"full": True, "none": False, "inst": False, "sym": True}
    members = {q["claim_id"]: q for q in _gather_qualifying_evidence("A101", payload["matches"], {}).qualifying}
    for key, want in expected.items():
        match = next(m for m in payload["matches"] if m["claim_id"] == key)
        assert scorer._is_ticker_specific(match, "AMD", names, {}) is want  # noqa: SLF001 -- Activation
        assert scorer._is_ticker_specific(members[key], "AMD", (), {}) is want  # noqa: SLF001 -- conflict side (B2, roles, evidence display)
    assert scorer._is_ticker_specific(payload["matches"][-1], "AMD", (), {}) is True  # noqa: SLF001 -- unclassified findings (unmatched claim)
    # legacy, documented: the conflict side only recognised the symbol, Activation also the product alias in any casing
    legacy_members = {q["claim_id"]: q for q in _gather_qualifying_evidence("A101", legacy["matches"], {}).qualifying}
    assert scorer._is_ticker_specific(legacy_members["full"], "AMD", (), {}) is False  # noqa: SLF001
    assert scorer._is_ticker_specific(legacy["matches"][2], "AMD", names, {}) is True  # noqa: SLF001 -- the 'instinct' false positive


def test_name_blocks_validate_contract_ticker_and_text_binding():
    payload = make_payload(make_match("c1", "Advanced Micro Devices raised guidance.", ticker="AMD", alpha="A101"), make_match("um", "Advanced Micro Devices.", ticker="AMD", status="no_match"), ticker="AMD")
    apply_v2(payload)
    um = payload["matches"][1]
    assert attribution_decision_for_record(um, "AMD") is True
    um["claim"] = "A different sentence now."  # the claim text moved after the block was written
    with pytest.raises(EvidenceConsumptionError) as raised:
        attribution_decision_for_record(um, "AMD")
    assert raised.value.reason_code == REASON_BINDING_STALE
    um[CONSUMPTION_BLOCK_KEY]["contract"] = "alpha_evidence_consumption.v9"
    with pytest.raises(EvidenceConsumptionError) as raised:
        attribution_decision_for_record(um, "AMD")
    assert raised.value.reason_code == REASON_ILLEGAL_CONTRACT_VERSION
