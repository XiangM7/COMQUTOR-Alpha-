"""John's named T3 consumption cases (005, 006, 019, 027R, 028, 037, 038, 040): the four defects fixed on 2026-10-13 under
``alpha_evidence_consumption.v2``, each with a regression that fails on the old behaviour.

1. a negator that does not govern the Alpha's statement (citation marker, contrast alternative, negated protection of a risk,
   another clause) excluded a supporting claim (T3 005 / 006 / 027R; NVDA claims 8, 38, 68, 85, ...);
2. a model-judged, ledger-corroborated opposing / background / mention-only stance still counted as POSITIVE direction evidence
   through the old text-rule relation (T3 037 / 038 / 040; R-1 already kept it out of the positive pool);
3. a selection the A001 gate vetoed was counted as a "valid NONE" (T3 019 / 027R / 028);
4. a canonical graph relation lost the negation of its own quote: "a no-cut regime ..." became Rate Cut Cycle -causal-> Valuation Risk.

The case texts are copied verbatim from the saved T3 inputs (round26_t3_closeout_20261008/05_offline_replay/after_all_fixes/
l4_inputs_by_sample.json) and the saved NVDA run 12591384, so the unit tests run without local evidence; the tests that read the saved
files skip when they are absent. Every case keeps the other gates: a model "supports" never bypasses the text rule, R-1 or the source
gate, and T3 005 stays out of the verified pool (its content support is CONDITIONAL).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from comqutor_alpha import consumption_recompute as cr
from comqutor_alpha.api.artifact_export import build_evidence_stance_audit
from comqutor_alpha.api.evidence_trace import build_claim_trace, load_trace_context
from comqutor_alpha.graph_engine import activation_scorer_v2 as scorer, pipeline as graph_pipeline
from comqutor_alpha.graph_engine.canonical_edge_scope import (
    REASON_CONDITIONAL,
    REASON_NEGATES_SOURCE,
    apply_canonical_edge_scope,
    relation_scope,
)
from comqutor_alpha.graph_engine.evidence_consumption import (
    CONSUMPTION_BLOCK_KEY,
    CONSUMPTION_CONTRACT_V2,
    REASON_DECISION_INCONSISTENT,
    EvidenceConsumptionError,
    StanceLedgerIndex,
    apply_alpha_evidence_consumption,
    block_for_match,
    effective_text_rule,
)
from comqutor_alpha.graph_engine.evidence_fact_index import (
    REASON_ASSERTION_NEGATED,
    REASON_RELATION_NOT_SUPPORTING,
    REASON_STANCE_NOT_SUPPORTING,
    select_supporting_alpha_claims,
)
from comqutor_alpha.graph_engine.statement_scope import (
    BASIS_CITATION_MARKER,
    BASIS_CONTRAST_ALTERNATIVE,
    BASIS_NEGATED_PROTECTION,
    BASIS_OTHER_CLAUSE,
    statement_scope,
)
from comqutor_alpha.source_provenance import compute_verified_support_eligibility
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from comqutor_alpha.structure_engine.alpha_mapper import compute_alpha_classification_completion
from comqutor_alpha.structure_engine.evidence_stance_llm import LLM_CLASSIFIER_VERSION

REPO_ROOT = Path(__file__).resolve().parents[1]
T3_INPUTS = REPO_ROOT / "docs/audit_artifacts/round_source_linking_t0_t2/round26_t3_closeout_20261008/05_offline_replay/after_all_fixes/l4_inputs_by_sample.json"
NVDA_RUN_ID = "12591384-0b26-470d-a99d-a49c00be440b"
NVDA_SOURCE_RUN = REPO_ROOT / "outputs" / "t4_runs" / NVDA_RUN_ID
needs_t3_inputs = pytest.mark.skipif(not T3_INPUTS.is_file(), reason="the saved T3 inputs are local evidence, absent in a fresh clone")
needs_nvda_run = pytest.mark.skipif(not (NVDA_SOURCE_RUN / "alpha_matches.json").is_file(), reason="the saved NVDA run is local run data")

NEGATED = {"relation": "mention", "assertion_status": "negated", "semantic_polarity": "mention"}

# verbatim texts (T3 sample ids / NVDA claim numbers)
T3_005 = (
    "Reasoning: The Research Manager's verdict is Underweight: the bear won the two decisive exchanges (the forward P/E of 41.67x rests "
    "on an EPS estimate of $15.72 [fragmentid: src7e133fa786f7aaa0:frag:0] that requires a 3x acceleration from the current $1.38 "
    "quarterly / $5.52 annualized run-rate [fragmentid: src582ac24bf4319648:frag:0], and net cash does not immunize a 167x trailing "
    "multiple from duration-driven compression"
)
T3_006 = (
    'His second overreach is the PEG defense — he calls 0.64 "priced for a ramp that the last four quarters of data actually support," '
    "but the last four quarters support a trailing inflection, not a forward EPS of $15.72 [fragmentid: src7e133fa786f7aaa0:frag:0] "
    "against a current quarterly run-rate of $1.38 [fragmentid: src582ac24bf4319648:frag:0]."
)
T3_027R = '"Gold Edges Higher as Weak US Jobs Data Reduces Fed Rate-Hike Expectations" (InvestorsHub) — [fragmentid: not provided]'
NVDA_63 = '"Tech rebounds as AI trade jitters ease: AlphaCheck" [fragmentid: not provided] — the AI complex is recovering from a jitter episode.'
NVDA_38 = "This is a reflexive-flows observation, not a fundamental one."
NVDA_68 = "It's not — it's a Price/Book of 24.33 on a company whose book value per share is $9.48 against a price of $230."
NVDA_85 = "Recession risk is not the threat; valuation and crowding are."
# saved AMD run c904d4cc (verification execution of 2026-10-13): two negated statements that the unanchored v1 rule read as support
AMD_NEWS_18 = "This is a textbook bear-steepening / term-premium repricing, not a growth scare."
AMD_RM_10 = 'He asserted "the ramp is already showing up in the prints," but the prints show a $5.52 annualized run-rate, not $15.72.'
NO_CUT_QUOTE = (
    "A no-cut regime means discount rates stay elevated, which mechanically compresses the present value of long-duration growth "
    "cash flows."
)


# ------------------------------------------------------------------------------------------------- 1. negation scope (unit level)
# the citation marker and the negated protection need no anchor; a contrast is removed only with the ledger-corroborated
# "supports_alpha" anchor (the T3 006 / NVDA 38 / NVDA 68 pairs carry one in their own runs)
@pytest.mark.parametrize(("text", "alpha", "basis", "anchored"), [
    (T3_027R, "A001", BASIS_CITATION_MARKER, False),
    (NVDA_63, "A601", BASIS_CITATION_MARKER, False),
    (T3_006, "A304", BASIS_CONTRAST_ALTERNATIVE, True),
    (NVDA_38, "A601", BASIS_CONTRAST_ALTERNATIVE, True),
    (NVDA_68, "A304", BASIS_CONTRAST_ALTERNATIVE, True),
    ("This is not a fundamentals story but a crowded-trade story.", "A601", BASIS_CONTRAST_ALTERNATIVE, True),
    (T3_005, "A304", BASIS_NEGATED_PROTECTION, False),
])
def test_a_negator_that_does_not_govern_the_alphas_statement_no_longer_negates_it(text, alpha, basis, anchored):
    scope = statement_scope(text, alpha, text_rule=NEGATED, terms=[], model_supports=anchored)
    assert scope["applies"] and not scope["governing_negation"] and scope["remaining_negators"] == []
    assert basis in {item["basis"] for item in scope["removed"]} and scope["not_applied"] == []
    assert scope["effective"]["assertion_status"] != "negated"
    assert scope["changed"] is True


@pytest.mark.parametrize(("text", "alpha"), [(T3_006, "A304"), (AMD_NEWS_18, "A501"), (AMD_RM_10, "A301")])
def test_without_the_anchor_a_contrast_is_not_removed_and_the_text_rule_stands(text, alpha):
    # AMD news 18 negates the recession Alpha's own statement ("not a growth scare") and RM 10 the growth ramp ("not $15.72"):
    # the words alone cannot tell which side carries the Alpha's statement, so without a model "supports" nothing is removed
    scope = statement_scope(text, alpha, text_rule=NEGATED, terms=[])
    assert scope["governing_negation"] is True and scope["changed"] is False and scope["effective"] == NEGATED
    assert scope["anchor"] is None and BASIS_CONTRAST_ALTERNATIVE in {i["basis"] for i in scope["not_applied"]}
    assert BASIS_CONTRAST_ALTERNATIVE not in {i["basis"] for i in scope["removed"]}


def test_the_re_read_keeps_the_text_rules_own_reading_of_what_is_left():
    # 027R: removing the citation marker does not turn a hawkish A001 reading into support -- the text rule still says invalidation
    assert statement_scope(T3_027R, "A001", text_rule=NEGATED, terms=[])["effective"]["relation"] == "invalidation"
    assert statement_scope(T3_006, "A304", text_rule=NEGATED, terms=[], model_supports=True)["effective"] == {
        "relation": "activation", "assertion_status": "asserted", "semantic_polarity": "activation"}


def test_a_negated_protection_affirms_a_risk_only_for_the_risk_alphas():
    assert statement_scope(T3_005, "A304", text_rule=NEGATED, terms=[])["governing_negation"] is False
    assert statement_scope(T3_005, "A301", text_rule=NEGATED, terms=[], model_supports=True)["governing_negation"] is True


def test_a_negation_in_another_clause_only_counts_against_the_alpha_whose_terms_it_carries():
    scoped = statement_scope(NVDA_85, "A304", text_rule=NEGATED, terms=["valuation"], model_supports=True)
    assert scoped["governing_negation"] is False and BASIS_OTHER_CLAUSE in {i["basis"] for i in scoped["removed"]}
    assert statement_scope(NVDA_85, "A501", text_rule=NEGATED, terms=["recession"], model_supports=True)["governing_negation"] is True
    assert statement_scope(NVDA_85, "A304", text_rule=NEGATED, terms=[], model_supports=True)["governing_negation"] is True  # no terms
    unanchored = statement_scope(NVDA_85, "A304", text_rule=NEGATED, terms=["valuation"])
    assert unanchored["governing_negation"] is True and BASIS_OTHER_CLAUSE in {i["basis"] for i in unanchored["not_applied"]}


@pytest.mark.parametrize("anchored", [False, True])
@pytest.mark.parametrize(("text", "alpha", "terms"), [
    ("Revenue at NVIDIA did not slow.", "A301", []),  # a real negation of the predicate
    ("NVIDIA will not raise guidance this quarter.", "A301", ["guidance"]),
    ("Recession risk is elevated. At 6% and falling, that risk is not the market's base case.", "A501", ["recession"]),  # back-reference
    ("This is a flows story, not a valuation story.", "A304", ["valuation"]),  # this Alpha's term is in the rejected alternative
])
def test_a_negation_that_governs_the_statement_still_negates_it_even_with_a_model_supports(text, alpha, terms, anchored):
    scope = statement_scope(text, alpha, text_rule=NEGATED, terms=terms, model_supports=anchored)
    assert scope["governing_negation"] is True and scope["changed"] is False and scope["effective"] == NEGATED


def test_the_scope_only_applies_when_the_text_rule_said_negated():
    stored = {"relation": "activation", "assertion_status": "asserted", "semantic_polarity": "activation"}
    scope = statement_scope(NVDA_63, "A601", text_rule=stored, terms=[])
    assert scope["applies"] is False and scope["effective"] == stored and scope["removed"] == []


# ------------------------------------------------------------------------------------ 1. negation scope through the contract and gates
def _candidate(alpha, *, relation, stance, terms=()):
    return {"alpha_id": alpha, "alpha_name": alpha, "score": 0.5, "keyword_score": 0.5, "factor_score": 0.0, "direction_score": 0.0,
            "semantic_score": 0.0, "relation": relation, "eligible": True, "ai_gate_passed": True, "evidence_stance": stance,
            "stance_method": "llm", "evidence_stance_version": LLM_CLASSIFIER_VERSION, "stance_fallback_reason": None, "counter_alpha_id": None,
            "requires_manual_review": False, "stance_confidence_band": None, "stance_reason_codes": [], "matched_keywords": list(terms),
            "matched_factors": []}


def _match(claim_id, text, alpha, *, relation="mention", assertion="negated", polarity="mention", stance="supports_alpha", terms=()):
    candidate = _candidate(alpha, relation=relation, stance=stance, terms=terms)
    return {"run_id": "r1", "ticker": "AMD", "agent": "fundamental_agent", "claim_id": claim_id, "claim": text, "evidence": text,
            "match_status": "matched", "matched_alpha": alpha, "score": 0.5, "assertion_status": assertion, "semantic_polarity": polarity,
            "claim_quality": "analytical", "direction": "positive", "factors": [], "candidate_scores": [candidate],
            "top_candidates": [copy.deepcopy(candidate)], "eligible_candidates": [copy.deepcopy(candidate)], "secondary_alphas": [],
            "llm_selected_alpha_id": alpha, "alpha_match_method": "llm"}


def _ledger(payload):
    pairs = {}
    for m in payload["matches"]:
        cand = next(c for c in m["candidate_scores"] if c["alpha_id"] == m["matched_alpha"])
        pairs[(m["claim_id"], m["matched_alpha"])] = {(cand["evidence_stance"], None)}
    return StanceLedgerIndex(pairs, path="synthetic", sha256="0" * 64, integrity="NO_MANIFEST", accepted_batches=1)


def _v2(payload):
    return apply_alpha_evidence_consumption(payload, [], None, ticker="AMD", contract=CONSUMPTION_CONTRACT_V2, ledger=_ledger(payload))


def _pool(payload, alpha):
    eligible, excluded, _ = select_supporting_alpha_claims(payload["matches"], alpha)
    return [r["claim_id"] for r in eligible], {e["claim_id"]: e["reason"] for e in excluded}


def test_t3_006_is_admitted_at_the_text_gates_under_the_contract_and_stays_excluded_on_the_legacy_path():
    legacy = {"ticker": "AMD", "matches": [_match("t3v3-006", T3_006, "A304")]}
    assert _pool(legacy, "A304") == ([], {"t3v3-006": REASON_RELATION_NOT_SUPPORTING})  # unchanged legacy behaviour
    assert effective_text_rule(legacy["matches"][0], "A304") is None
    v2 = copy.deepcopy(legacy)
    summary = _v2(v2)
    assert _pool(v2, "A304") == (["t3v3-006"], {})
    block = block_for_match(v2["matches"][0])
    assert block["text_rule"] == NEGATED  # the stored text-rule fields are recorded unchanged
    assert v2["matches"][0]["assertion_status"] == "negated" and v2["matches"][0]["candidate_scores"][0]["relation"] == "mention"
    assert summary["statement_scope"]["negation_not_governing"] == 1


def test_the_weights_read_the_re_read_statement_not_negated_zero():
    v2 = {"ticker": "AMD", "matches": [_match("t3v3-006", T3_006, "A304")]}
    _v2(v2)
    qualifying, _ = scorer._gather_qualifying_evidence({"matches": v2["matches"]}, "A304", {})  # noqa: SLF001
    assert [(q["claim_id"], q["relation"], q["assertion_status"]) for q in qualifying] == [("t3v3-006", "activation", "asserted")]
    weight = scorer.RELATION_WEIGHTS[qualifying[0]["relation"]] * scorer.ASSERTION_WEIGHTS[qualifying[0]["assertion_status"]]
    assert weight == 1.0


def test_the_v2_evidence_detail_records_what_the_v2_scorers_weighted_and_v1_keeps_the_stored_reading():
    # the trace computes a pooled claim's weight from evidence_detail: it must read the fields the scorer weighted
    v2 = {"ticker": "AMD", "matches": [_match("t3v3-006", T3_006, "A304")]}
    _v2(v2)
    v2_view = [{"alpha_id": "A304", "claim_ids": ["t3v3-006"]}]
    graph_pipeline._attach_evidence_detail(v2_view, v2, statement_scope_reading=True)  # noqa: SLF001
    detail = v2_view[0]["evidence_detail"][0]
    assert (detail["relation"], detail["assertion_status"]) == ("activation", "asserted")
    assert (detail["text_rule_relation"], detail["text_rule_assertion_status"]) == ("mention", "negated")
    assert detail["reading_policy"] == "alpha_statement_scope.v2"
    # v1 weights the stored text-rule fields, and a legacy record has no block: both read exactly as before
    v1_view = [{"alpha_id": "A304", "claim_ids": ["t3v3-006"]}]
    graph_pipeline._attach_evidence_detail(v1_view, v2)  # noqa: SLF001
    legacy = {"ticker": "AMD", "matches": [_match("t3v3-006", T3_006, "A304")]}
    legacy_view = [{"alpha_id": "A304", "claim_ids": ["t3v3-006"]}]
    graph_pipeline._attach_evidence_detail(legacy_view, legacy, statement_scope_reading=True)  # noqa: SLF001
    for view in (v1_view, legacy_view):
        stored = view[0]["evidence_detail"][0]
        assert (stored["relation"], stored["assertion_status"]) == ("mention", "negated") and "text_rule_relation" not in stored


def test_a_model_supports_never_bypasses_r1_or_the_other_gates():
    # same text, but a ledger-corroborated opposing stance: that is no anchor, so the contrast is not removed and the relation gate
    # keeps the claim out (R-1 would as well)
    v2 = {"ticker": "AMD", "matches": [_match("x", T3_006, "A304", stance="opposes_alpha")]}
    _v2(v2)
    assert _pool(v2, "A304") == ([], {"x": REASON_RELATION_NOT_SUPPORTING})
    assert block_for_match(v2["matches"][0])["statement_scope"]["not_applied"]
    # without a ledger every stance is unjudged: no anchor, so the negated readings stand (the v1 false supports of AMD news 18 / RM 10)
    no_ledger = {"ticker": "AMD", "matches": [_match("t3v3-006", T3_006, "A304"), _match("news-18", AMD_NEWS_18, "A501"),
                                              _match("rm-10", AMD_RM_10, "A301")]}
    apply_alpha_evidence_consumption(no_ledger, [], None, ticker="AMD", contract=CONSUMPTION_CONTRACT_V2, ledger=None)
    for claim_id, alpha in (("t3v3-006", "A304"), ("news-18", "A501"), ("rm-10", "A301")):
        assert _pool(no_ledger, alpha) == ([], {claim_id: REASON_RELATION_NOT_SUPPORTING})
    # a governing negation stays excluded whatever the stance says
    still = {"ticker": "AMD", "matches": [_match("y", "Revenue at AMD did not slow.", "A301")]}
    _v2(still)
    assert _pool(still, "A301") == ([], {"y": REASON_RELATION_NOT_SUPPORTING})


def test_t3_005_is_re_read_at_the_text_gates_but_never_gains_source_eligibility():
    v2 = {"ticker": "AMD", "matches": [_match("t3v3-005", T3_005, "A304")]}
    _v2(v2)
    assert _pool(v2, "A304")[0] == ["t3v3-005"]  # the negation no longer excludes it at the text gates ...
    block = block_for_match(v2["matches"][0])
    assert block["source_support"]["verified_eligible"] is False  # ... but the unchanged source gate still does (no record, no source)


@needs_t3_inputs
def test_the_saved_t3_005_record_keeps_its_source_problem():
    record = json.loads(T3_INPUTS.read_text(encoding="utf-8"))["t3v3-005"]["record_after_L1"]
    assert record["content_support_status"] == "CONDITIONAL"
    assert compute_verified_support_eligibility(record, []) == {"eligible": False, "reason_code": "SUPPORT_STATUS_NOT_RESOLVED"}


def test_an_edited_scope_decision_is_rejected_as_inconsistent():
    v2 = {"ticker": "AMD", "matches": [_match("t3v3-006", T3_006, "A304")]}
    _v2(v2)
    block = block_for_match(v2["matches"][0])
    block["statement_scope"]["effective"]["relation"] = "activation"
    block["statement_scope"]["governing_negation"] = True  # contradicts the stored inputs
    with pytest.raises(EvidenceConsumptionError) as raised:
        select_supporting_alpha_claims(v2["matches"], "A304")
    assert raised.value.reason_code == REASON_DECISION_INCONSISTENT


def test_a_negated_claim_with_a_governing_negation_is_still_reported_as_assertion_negated():
    v2 = {"ticker": "AMD", "matches": [_match("z", "Valuation risk is not elevated for AMD.", "A304", relation="activation", polarity="activation")]}
    _v2(v2)
    assert _pool(v2, "A304") == ([], {"z": REASON_ASSERTION_NEGATED})


# ------------------------------------------------------------------------------------------------ 2. direction consistency (R-1)
def test_a_model_judged_opposition_is_no_longer_positive_direction_evidence():
    matches = [
        _match("inv", "A501 recession thesis invalidated: recession is unlikely.", "A501", relation="invalidation", assertion="asserted",
               polarity="invalidation", stance="opposes_alpha"),
        _match("t3v3-037", "Category: Recession risk; Signal: Low & falling; Evidence: US 8% (−1.0pp); UK 7%; Japan 4%", "A501",
               relation="activation", assertion="asserted", polarity="activation", stance="opposes_alpha"),
        _match("t3v3-038", "Market: Japan recession in 2026; Implied Probability: 4% Yes; Volume: $4K; 1-Week Move: —", "A501",
               relation="activation", assertion="asserted", polarity="activation", stance="neutral_background"),
        _match("sup", "US recession odds jumped to 45% after the payrolls miss.", "A501", relation="activation", assertion="asserted",
               polarity="activation", stance="supports_alpha"),
    ]
    legacy = {"ticker": "AMD", "matches": copy.deepcopy(matches)}
    legacy_groups = scorer._gather_direction_evidence(legacy, "A501", {})  # noqa: SLF001
    assert sorted(g["relation"] for g in legacy_groups.values()) == ["activation", "activation", "activation", "invalidation"]
    v2 = {"ticker": "AMD", "matches": copy.deepcopy(matches)}
    _v2(v2)
    v2_groups = scorer._gather_direction_evidence(v2, "A501", {})  # noqa: SLF001
    assert sorted(g["relation"] for g in v2_groups.values()) == ["activation", "invalidation"]  # 037 and 038 no longer count as positive
    raw_legacy, _ = scorer._direction_consistency_component(legacy_groups)  # noqa: SLF001
    raw_v2, _ = scorer._direction_consistency_component(v2_groups)  # noqa: SLF001
    assert raw_v2 < raw_legacy  # the old labels no longer inflate the risk Alpha's direction consistency
    assert _pool(v2, "A501")[0] == ["sup"]  # the positive pool was already R-1 filtered


# ----------------------------------------------------------------------------------------------- 3. gate-vetoed selection is not NONE
def test_a_selection_the_a001_gate_vetoed_is_not_a_valid_none():
    def record(selected, **flags):
        return {"alpha_match_method": "llm", "alpha_match_fallback_reason": None, "matched_alpha": None, "llm_selected_alpha_id": selected, **flags}

    payload = {"matches": [
        record("A001", alpha_specific_invalidation_override=True),  # 019 / 027R / 028
        record("A001", alpha_positive_requirement_override=True),
        record("A304"),
        record(None),
        {"alpha_match_method": "llm", "alpha_match_fallback_reason": None, "matched_alpha": "A301", "llm_selected_alpha_id": "A301"},
    ]}
    completion = compute_alpha_classification_completion(payload)
    assert completion["valid_none_count"] == 1 and completion["valid_select_count"] == 1
    assert completion["gate_overridden_selection_count"] == 3
    assert completion["gate_overridden_by_gate"] == {"alpha_specific_invalidation": 1, "alpha_positive_requirement": 1, "other_gate": 1}
    assert completion["complete"] is True


@needs_t3_inputs
def test_the_saved_t3_gate_cases_are_counted_as_gate_overridden():
    saved = json.loads(T3_INPUTS.read_text(encoding="utf-8"))
    completion = compute_alpha_classification_completion({"matches": [saved[sid]["match"] for sid in ("t3v3-019", "t3v3-027R", "t3v3-028")]})
    assert completion["gate_overridden_selection_count"] == 3 and completion["valid_none_count"] == 0


# -------------------------------------------------------------------------------------------- 4. canonical relations keep negation
def _relation(rid, quote, source="Rate Cut Cycle", target="Valuation Risk", relation_type="causal"):
    return {"relation_id": rid, "source_factor_id": source, "source_factor_display_name": source, "target_factor_id": target,
            "target_factor_display_name": target, "relation_type": relation_type, "evidence_quote": quote, "assertion_status": "asserted",
            "candidate_edge_created": True}


@pytest.mark.parametrize(("quote", "reason"), [
    (NO_CUT_QUOTE, REASON_NEGATES_SOURCE),
    ("The Fed will not cut rates this year, which keeps valuations under pressure.", REASON_NEGATES_SOURCE),
    ("If the Fed cuts rates, multiples could expand.", REASON_CONDITIONAL),
])
def test_a_relation_whose_quote_negates_an_endpoint_or_is_conditional_is_withheld(quote, reason):
    decision = relation_scope(_relation("canrel_x", quote))
    assert decision["withheld"] is True and reason in decision["reasons"]


@pytest.mark.parametrize("quote", [
    "Each rate cut lowers the discount rate and lifts long-duration valuations.",
    "Recession risk at 6% and falling.",
    "A coiled spring with deteriorating momentum is not the same as a coiled spring with improving momentum.",
])
def test_a_relation_whose_quote_asserts_both_endpoints_is_kept(quote):
    assert relation_scope(_relation("canrel_y", quote))["withheld"] is False


def test_only_the_withheld_canonical_edges_are_removed_and_the_input_is_untouched():
    payload = {"edges": [
        {"source": "rate_cut_cycle", "target": "valuation_risk", "edge_type": "causal", "rule_name": "tradingagents_canonical_relation", "relation_id": "canrel_neg"},
        {"source": "rate_cut_cycle", "target": "valuation_risk", "edge_type": "causal", "rule_name": "tradingagents_canonical_relation", "relation_id": "canrel_ok"},
        {"source": "rate_cut_cycle", "target": "valuation_risk", "edge_type": "causal", "rule_name": "relation_grammar", "relation_id": "canrel_neg"},
    ], "nodes": [
        {"id": "only_from_negated", "source_records": ["canrel_neg"]},
        {"id": "rate_cut_cycle", "source_records": ["canrel_neg", "canrel_ok"]},
    ]}
    before = copy.deepcopy(payload)
    relations = [_relation("canrel_neg", NO_CUT_QUOTE), _relation("canrel_ok", "Each rate cut lowers the discount rate.")]
    filtered, summary = apply_canonical_edge_scope(payload, relations)
    assert payload == before
    assert [e["relation_id"] for e in filtered["edges"]] == ["canrel_ok", "canrel_neg"]  # the grammar edge is never touched
    assert [n["id"] for n in filtered["nodes"]] == ["rate_cut_cycle"]
    assert summary["withheld_relation_count"] == 1 and summary["withheld"][0]["relation_id"] == "canrel_neg"


# ------------------------------------------------------------------------------- end to end on a copy of the saved NVDA run (local data)
def _repo():
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    return GraphPersistenceRepository(engine)


@pytest.fixture
def nvda_copy(tmp_path):
    result = cr.copy_saved_run(NVDA_SOURCE_RUN, tmp_path / "verification")
    assert result["status"] == "ok"
    return tmp_path / "verification"


def _execution(root: Path, contract: str) -> Path:
    result = cr.derive_consumption_execution(NVDA_RUN_ID, contract=contract, output_root=root, graph_repository=_repo())
    assert result["status"] == "ok", result
    return root / result["execution_id"]


@needs_nvda_run
def test_the_saved_nvda_run_under_the_contract_withholds_the_no_cut_relations_and_rereads_the_negations(nvda_copy):
    v2 = _execution(nvda_copy, "v2")
    graph = json.loads((v2 / "structure_graph.json").read_text(encoding="utf-8"))
    scope = graph["evidence_consumption"]["canonical_edge_scope"]
    assert scope["withheld_relation_count"] == 3 and {r["reasons"][0] for r in scope["withheld"]} == {REASON_NEGATES_SOURCE}
    edge = next(e for e in graph["edges"] if (e["source"], e["target"]) == ("rate_cut_cycle", "valuation_risk"))
    assert len(edge["claim_ids"]) == 1  # was 4: three of its relations said "no-cut"
    statement = graph["evidence_consumption"]["statement_scope"]
    assert statement["negation_not_governing"] > 0 and statement["negation_still_governing"] > 0
    matches = json.loads((v2 / "alpha_matches.json").read_text(encoding="utf-8"))["matches"]
    eligible, excluded, _ = select_supporting_alpha_claims(matches, "A304")
    reasons = {e["claim_id"].split(":")[-3] + ":" + e["claim_id"].split(":")[-1]: e["reason"] for e in excluded if e["claim_id"]}
    admitted = {r["claim_id"].split(":")[-3] + ":" + r["claim_id"].split(":")[-1] for r in eligible}
    # "They're not -- they're a measure of how much growth is already embedded in consensus." now passes every gate for A304
    assert "risk_debate_state.conservative_history:12" in admitted
    # "It's not -- it's a Price/Book of 24.33 ...": its negation no longer governs, but the unchanged claim-quality gate still applies
    claim_68 = next(m for m in matches if m["claim_id"].endswith("bear_history:claim:68"))
    assert block_for_match(claim_68)["statement_scope"]["governing_negation"] is False
    assert reasons["investment_debate_state.bear_history:68"] == "NON_ANALYTICAL_QUALITY"

    # the trace explains the relation the gates used: the re-read one, or the text rule's when its negation still governs
    ctx = load_trace_context(v2.name, nvda_copy)
    reread = build_claim_trace(ctx, f"{NVDA_RUN_ID}:conservative_risk_analyst:risk_debate_state.conservative_history:claim:12")
    assert reread["consumption"]["statement_scope"]["changed"] is True
    assert reread["stance"]["status_code"] == "MODEL_JUDGED"
    assert (reread["stance"]["relation"], reread["stance"]["assertion_status"]) == ("activation", "asserted")
    assert "alpha_statement_scope.v2" in reread["stance"]["relation_basis"]
    governed = build_claim_trace(ctx, f"{NVDA_RUN_ID}:research_manager:investment_plan:claim:38")
    assert governed["consumption"]["statement_scope"]["governing_negation"] is True
    assert governed["stance"]["status_code"] == "RELATION_UNRESOLVED"
    assert (governed["stance"]["relation"], governed["stance"]["relation_basis"]) == ("mention", "text rule (claim_semantics)")
    # the diagnostic v2 view's evidence detail records the reading it weighted; v1 weighted (and records) the stored fields
    v2_a304 = next(a for a in graph["activation_versions"]["v2"]["alphas"] if a["alpha_id"] == "A304")
    detail_12 = next(d for d in v2_a304["evidence_detail"] if d["claim_id"] == reread["claim_id"])
    assert (detail_12["relation"], detail_12["assertion_status"], detail_12["text_rule_relation"]) == ("activation", "asserted", "mention")
    v1_a304 = next(a for a in graph["activation_versions"]["v1"]["alphas"] if a["alpha_id"] == "A304")
    assert all("text_rule_relation" not in d for d in v1_a304["evidence_detail"])
    # the export's stance audit keeps the stored text-rule fields and reports the reading the gates used beside them
    matches_payload = json.loads((v2 / "alpha_matches.json").read_text(encoding="utf-8"))
    audit = build_evidence_stance_audit(run_id=v2.name, ticker="NVDA", alpha_matches_payload=matches_payload, graph_payload=graph)
    row = next(r for r in audit["records"] if r["claim_id"] == reread["claim_id"] and r["target_alpha_id"] == "A304")
    assert (row["relation"], row["assertion_status"]) == ("mention", "negated")
    assert row["statement_scope"]["changed"] is True and row["statement_scope"]["removed_bases"] == ["CONTRAST_ALTERNATIVE"]
    assert (row["statement_scope"]["effective"]["relation"], row["statement_scope"]["effective"]["assertion_status"]) == ("activation", "asserted")

    legacy = _execution(nvda_copy, "legacy")
    legacy_graph = json.loads((legacy / "structure_graph.json").read_text(encoding="utf-8"))
    assert "evidence_consumption" not in legacy_graph  # the legacy choice is untouched by every 2026-10-13 rule
    legacy_edge = next(e for e in legacy_graph["edges"] if (e["source"], e["target"]) == ("rate_cut_cycle", "valuation_risk"))
    assert len(legacy_edge["claim_ids"]) == 4
    legacy_matches = json.loads((legacy / "alpha_matches.json").read_text(encoding="utf-8"))["matches"]
    assert not any(CONSUMPTION_BLOCK_KEY in c for m in legacy_matches for c in m.get("candidate_scores") or [])
