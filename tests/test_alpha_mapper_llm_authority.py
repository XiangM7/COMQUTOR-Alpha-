"""Pure-LLM Alpha semantic authority (see
comqutor_alpha/structure_engine/alpha_mapper.py and week2_llm.py's
`alpha_classifier` v3 prompt).

The LLM is the SOLE source of the semantic Alpha result: it sees the FULL
canonical taxonomy (never a deterministically pre-restricted subset) and
resolves to exactly one of two successful outcomes -- "select" (exactly one
canonical Alpha) or "none" (no canonical Alpha materially fits). There is no
successful "cannot decide"/"defer" outcome. Deterministic scoring is NEVER a
fallback source for the semantic result on any failure (disabled, provider
timeout/error, malformed/invalid output, unknown Alpha ID) -- it survives
only as a diagnostic/counterfactual (`deterministic_top_alpha`/
`deterministic_match_status`), and every operational failure reports
match_status="unavailable" instead.

These tests prove the new authority model directly, using a fake
llm_gateway that speaks the same wire contract
(`{"decision": "select"|"none", "selected_alpha_id": ...}`) the real
Provider prompt requires and the same `invoke_json`/validator seam
`Week2LLMGateway.invoke_json` exposes -- no real Provider call anywhere in
this file. Tests are lettered A-M to match the task spec's required
scenario list; N ("select and none both replay-bind correctly") lives in
tests/replay/test_semantic_call_artifact_binding.py, since it needs the
Exact Semantic Replay bundle/binding-audit machinery that only exists there.
"""

from __future__ import annotations

import json

import pytest

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.conflict_engine.conflict_admissibility import stance_for_alpha
from comqutor_alpha.conflict_engine.conflict_detector import detect_alpha_conflicts
from comqutor_alpha.graph_engine.activation_scorer_v2 import score_alpha_activations_v2
from comqutor_alpha.structure_engine.alpha_mapper import map_claim_to_alpha

ALL_ALPHA_IDS = {"A001", "A003", "A101", "A102", "A103", "A201", "A301", "A304", "A501", "A601"}


def _record(text, *, factors=None, direction="neutral", ticker="NVDA"):
    return {
        "run_id": "run1",
        "ticker": ticker,
        "agent": "news_agent",
        "claim": text,
        "evidence": text,
        "factors": factors or [],
        "direction": direction,
        "confidence": 0.8,
        "source_agent_output_id": "run1:news_agent:news_report",
    }


class _FakeLLMGateway:
    """Speaks the exact `invoke_json(task, payload, validator)` seam the
    real Week2LLMGateway exposes, without the semantic_runtime cache/trace
    machinery -- `_classify_alpha_with_llm` falls back to `invoke_json` for
    any gateway without a callable `invoke_json_with_trace`."""

    invoke_json_with_trace = None  # not callable -> forces the invoke_json path

    def __init__(self, response=None, raise_exc: BaseException | None = None):
        self._response = response
        self._raise_exc = raise_exc
        self.calls: list[dict] = []
        self.semantic_runtime = None

    def invoke_json(self, task, payload, validator):
        """Mirrors Week2LLMGateway._invoke_json_legacy: a validator
        TypeError/ValueError/KeyError is caught internally and reported as
        "no valid result" (None), never propagated to the caller."""
        self.calls.append({"task": task, "payload": payload})
        if self._raise_exc is not None:
            raise self._raise_exc
        try:
            return validator(self._response)
        except (TypeError, ValueError, KeyError):
            return None


_AI_DEMAND_RECORD_TEXT = "AI training demand is accelerating and GPU demand is rising for NVDA."
_AI_DEMAND_FACTORS = ["AI Demand", "GPU Demand"]


def _ai_demand_record():
    return _record(_AI_DEMAND_RECORD_TEXT, factors=_AI_DEMAND_FACTORS, direction="positive")


# ---------------------------------------------------------------------------
# A. LLM SELECT OVERRIDES DETERMINISTIC -- the core acceptance criterion
# ---------------------------------------------------------------------------


def test_a_llm_selects_alpha_absent_from_deterministic_tier1_candidates():
    """An Alpha absent from deterministic Tier-1 candidates can still become
    the final semantic matched_alpha_id when the valid LLM semantic
    classifier selects it. Uses a competition/substitution claim that
    deterministic scoring explicitly excludes A101 from (see
    test_week2_semantics.py::test_competition_and_substitution_do_not_force_ai_alpha)."""
    record = _record(
        "Etched is a niche competitor and not an immediate threat to NVIDIA AI inference.",
        factors=["Inference Demand"],
        direction="negative",
    )

    baseline = map_claim_to_alpha(record, classifier_enabled=True, llm_gateway=_FakeLLMGateway(
        response={"decision": "none", "selected_alpha_id": None}
    ))
    assert baseline["deterministic_match_status"] == "no_match"
    assert baseline["deterministic_top_alpha"] is None
    assert baseline["eligible_candidates"] == []
    a101_baseline = next(c for c in baseline["candidate_scores"] if c["alpha_id"] == "A101")
    assert a101_baseline["eligible"] is False

    gateway = _FakeLLMGateway(response={"decision": "select", "selected_alpha_id": "A101"})
    result = map_claim_to_alpha(record, classifier_enabled=True, llm_gateway=gateway)

    assert result["match_status"] == "matched"
    assert result["matched_alpha"] == "A101"
    assert result["alpha_match_method"] == "llm"
    assert result["alpha_match_fallback_reason"] is None
    assert result["classifier"]["status"] == "llm_selected"
    # Deterministic diagnostics preserved, unchanged from the baseline above.
    assert result["deterministic_match_status"] == "no_match"
    assert result["deterministic_top_alpha"] is None

    # Plumbing: the matched Alpha's own diagnostic dict (score components,
    # relation, and B1 evidence_stance) must now be reachable through
    # candidate_scores even though deterministic scoring alone never
    # admitted it -- this is what B1's own LLM upgrade pass, B2
    # admissibility, and B4 activation all rely on (see dependency audit).
    matched_candidate = next(c for c in result["candidate_scores"] if c["alpha_id"] == "A101")
    assert matched_candidate["evidence_stance"] is not None
    assert result["matched_evidence_stance"] == matched_candidate["evidence_stance"]

    # Confirm the sent request carried the FULL taxonomy, not a restricted set.
    sent_payload = gateway.calls[0]["payload"]
    assert {a["alpha_id"] for a in sent_payload["alpha_taxonomy"]} == ALL_ALPHA_IDS
    assert "allowed_alpha_ids" not in sent_payload
    assert "candidates" not in sent_payload


def test_a_full_taxonomy_ids_match_canonical_registry_not_a_hardcoded_list():
    """The request must be built by reading the canonical taxonomy registry
    directly, so it always reflects load_alpha_taxonomy() -- not a second,
    separately hardcoded ID list that could silently drift from it."""
    gateway = _FakeLLMGateway(response={"decision": "none", "selected_alpha_id": None})
    map_claim_to_alpha(
        _record("Generic commentary with no strong signal."),
        classifier_enabled=True,
        llm_gateway=gateway,
    )
    sent_ids = {a["alpha_id"] for a in gateway.calls[0]["payload"]["alpha_taxonomy"]}
    assert sent_ids == set(load_alpha_taxonomy())


def test_a_llm_select_overrides_deterministic_top_candidate():
    """Deterministic scoring has a perfectly clear, different top candidate
    (A304) -- a valid LLM select of a different Alpha (A301) still wins."""
    record = _record(
        "Rich valuation creates downside risk even as revenue growth continues.",
        factors=["Valuation Risk", "Revenue Growth"],
        direction="negative",
    )

    baseline = map_claim_to_alpha(record, classifier_enabled=True, llm_gateway=_FakeLLMGateway(
        response={"decision": "none", "selected_alpha_id": None}
    ))
    scores_by_id = {c["alpha_id"]: c["score"] for c in baseline["candidate_scores"]}
    assert baseline["deterministic_top_alpha"] == "A304"
    assert baseline["deterministic_match_status"] == "matched"
    assert "A301" in scores_by_id
    assert scores_by_id["A304"] > scores_by_id["A301"]

    gateway = _FakeLLMGateway(response={"decision": "select", "selected_alpha_id": "A301"})
    result = map_claim_to_alpha(record, classifier_enabled=True, llm_gateway=gateway)

    assert result["matched_alpha"] == "A301"
    assert result["alpha_match_method"] == "llm"
    # The deterministic top's own diagnostics remain observable, unmodified,
    # alongside the LLM's winning choice -- nothing is deleted or rewritten.
    assert result["deterministic_top_alpha"] == "A304"
    still_present = {c["alpha_id"]: c["score"] for c in result["candidate_scores"]}
    assert still_present["A304"] == scores_by_id["A304"]


# ---------------------------------------------------------------------------
# B. DETERMINISTIC SCORE THRESHOLD CANNOT ERASE A VALID LLM SEMANTIC MATCH
# ---------------------------------------------------------------------------


def test_b_score_below_threshold_cannot_erase_valid_llm_match():
    from comqutor_alpha.structure_engine.alpha_mapper import DEFAULT_MIN_MATCH_SCORE, keyword_score

    record = _record("Traders have mixed opinions on where the stock goes next.", direction="neutral")
    a601_keyword_score = keyword_score(record["evidence"], load_alpha_taxonomy()["A601"])
    assert a601_keyword_score < DEFAULT_MIN_MATCH_SCORE

    baseline = map_claim_to_alpha(record, classifier_enabled=True, llm_gateway=_FakeLLMGateway(
        response={"decision": "none", "selected_alpha_id": None}
    ))
    assert baseline["deterministic_match_status"] == "no_match"  # deterministic alone finds nothing here

    gateway = _FakeLLMGateway(response={"decision": "select", "selected_alpha_id": "A601"})
    result = map_claim_to_alpha(record, classifier_enabled=True, llm_gateway=gateway)

    assert result["match_status"] == "matched"
    assert result["matched_alpha"] == "A601"
    assert result["score"] < DEFAULT_MIN_MATCH_SCORE  # the low deterministic score remains observable, not erased
    assert result["alpha_match_method"] == "llm"
    # Plumbing: A601 must now be reachable through candidate_scores even
    # though it did not rank in the deterministic top 5.
    matched_candidate = next(c for c in result["candidate_scores"] if c["alpha_id"] == "A601")
    assert matched_candidate["score"] < DEFAULT_MIN_MATCH_SCORE


# ---------------------------------------------------------------------------
# C. AI HARD GATE CANNOT HIDE A SEMANTIC OPTION FROM THE LLM
# ---------------------------------------------------------------------------


def test_c_ai_hard_gate_cannot_hide_semantic_option_from_llm():
    record = _record("AI continues to be a strategic priority for the company.", direction="positive")

    baseline = map_claim_to_alpha(record, classifier_enabled=True, llm_gateway=_FakeLLMGateway(
        response={"decision": "none", "selected_alpha_id": None}
    ))
    a101_baseline = next((c for c in baseline["candidate_scores"] if c["alpha_id"] == "A101"), None)
    assert a101_baseline is not None
    assert a101_baseline["ai_gate_passed"] is False
    assert a101_baseline["eligible"] is False
    assert "A101" not in {c["alpha_id"] for c in baseline["eligible_candidates"]}

    gateway = _FakeLLMGateway(response={"decision": "select", "selected_alpha_id": "A101"})
    result = map_claim_to_alpha(record, classifier_enabled=True, llm_gateway=gateway)

    assert result["matched_alpha"] == "A101"
    assert result["alpha_match_method"] == "llm"
    matched_candidate = next(c for c in result["candidate_scores"] if c["alpha_id"] == "A101")
    # The gate result remains visible as a downstream diagnostic -- it is
    # not deleted, silently flipped, or hidden -- it simply no longer blocks
    # the semantic classification itself.
    assert matched_candidate["ai_gate_passed"] is False


# ---------------------------------------------------------------------------
# D. LLM NONE WITH A DETERMINISTIC CANDIDATE PRESENT -> matched_alpha=null,
#    ABSOLUTELY MUST NOT become the deterministic Alpha.
# ---------------------------------------------------------------------------


def test_d_llm_none_with_deterministic_candidate_present_is_never_promoted():
    record = _ai_demand_record()
    baseline = map_claim_to_alpha(record, classifier_enabled=True, llm_gateway=_FakeLLMGateway(
        response={"decision": "select", "selected_alpha_id": "A101"}
    ))
    assert baseline["deterministic_top_alpha"] == "A101"
    assert baseline["deterministic_match_status"] == "matched"

    gateway = _FakeLLMGateway(response={"decision": "none", "selected_alpha_id": None})
    result = map_claim_to_alpha(record, classifier_enabled=True, llm_gateway=gateway)

    assert result["matched_alpha"] is None
    assert result["matched_alpha_name"] is None
    assert result["match_status"] == "no_match"
    assert result["alpha_match_method"] == "llm"
    assert result["alpha_match_fallback_reason"] is None
    assert result["classifier"]["status"] == "llm_none"
    # The deterministic candidate (A101) existed and is preserved as a
    # diagnostic/counterfactual -- but it is NEVER promoted to matched_alpha.
    assert result["deterministic_top_alpha"] == "A101"
    assert result["deterministic_match_status"] == "matched"


# ---------------------------------------------------------------------------
# E / F. PROVIDER FAILURE / TIMEOUT -> UNAVAILABLE, NEVER A DETERMINISTIC ALPHA
# ---------------------------------------------------------------------------


def test_e_provider_error_reports_unavailable_never_deterministic():
    record = _ai_demand_record()
    gateway = _FakeLLMGateway(raise_exc=RuntimeError("provider transport failed"))
    result = map_claim_to_alpha(record, classifier_enabled=True, llm_gateway=gateway)

    assert result["matched_alpha"] is None
    assert result["match_status"] == "unavailable"
    assert result["alpha_match_method"] == "llm_unavailable"
    assert result["alpha_match_fallback_reason"] == "provider_error"
    assert result["classifier"]["status"] == "provider_error"
    # Diagnostics survive: deterministic scoring still found A101 here, it
    # is simply never used as the semantic answer.
    assert result["deterministic_top_alpha"] == "A101"
    assert result["deterministic_match_status"] == "matched"


def test_f_timeout_reports_unavailable_without_leaking_details():
    record = _ai_demand_record()
    gateway = _FakeLLMGateway(raise_exc=TimeoutError("provider timeout with sensitive internal details"))
    result = map_claim_to_alpha(record, classifier_enabled=True, llm_gateway=gateway)

    assert result["matched_alpha"] is None
    assert result["match_status"] == "unavailable"
    assert result["alpha_match_method"] == "llm_unavailable"
    assert result["alpha_match_fallback_reason"] == "provider_timeout"
    assert result["deterministic_top_alpha"] == "A101"
    assert "sensitive internal details" not in json.dumps(result)


# ---------------------------------------------------------------------------
# G. INVALID ALPHA ID (A999) -> FAIL CLOSED, NEVER A DETERMINISTIC FALLBACK
# ---------------------------------------------------------------------------


def test_g_unknown_alpha_id_is_rejected_at_the_gateway_validator():
    """The gateway path's validator rejects an unknown Alpha ID before it
    ever reaches map_claim_to_alpha -- Week2LLMGateway.invoke_json catches
    that rejection internally and reports "no valid result", which
    _classify_alpha_with_llm treats as invalid_output, never a deterministic
    fallback."""
    record = _ai_demand_record()
    gateway = _FakeLLMGateway(response={"decision": "select", "selected_alpha_id": "A999"})
    result = map_claim_to_alpha(record, classifier_enabled=True, llm_gateway=gateway)

    assert result["matched_alpha"] is None
    assert result["match_status"] == "unavailable"
    assert result["alpha_match_method"] == "llm_unavailable"
    assert result["alpha_match_fallback_reason"] == "invalid_output"
    assert result["classifier"]["status"] == "invalid_output"
    assert result["deterministic_top_alpha"] == "A101"


def test_g_unknown_alpha_id_from_a_raw_classifier_is_rejected():
    """The lower-level raw-classifier-callable seam (used directly by
    tests/test_week2_semantics.py) performs its own post-hoc contract check
    (outcome vocabulary, Alpha ID membership) rather than routing through a
    gateway validator -- an unknown Alpha ID must be rejected there too,
    producing the more specific invalid_alpha_id reason and never a
    deterministic fallback."""
    record = _ai_demand_record()

    def classifier(_request, *, timeout_seconds):
        del timeout_seconds
        return {"outcome": "selected", "alpha_id": "A999"}

    result = map_claim_to_alpha(record, classifier=classifier, classifier_enabled=True)

    assert result["matched_alpha"] is None
    assert result["match_status"] == "unavailable"
    assert result["alpha_match_method"] == "llm_unavailable"
    assert result["alpha_match_fallback_reason"] == "invalid_alpha_id"
    assert result["classifier"]["status"] == "invalid_alpha_id"


# ---------------------------------------------------------------------------
# H. MALFORMED / UNEXPECTED-SHAPE OUTPUT -> UNAVAILABLE, NEVER DETERMINISTIC
# ---------------------------------------------------------------------------


def test_h_malformed_gateway_response_is_unavailable_not_deterministic():
    record = _ai_demand_record()
    # Missing selected_alpha_id entirely -> the wire validator's own field
    # check (`set(payload) != {"decision", "selected_alpha_id"}`) rejects it.
    gateway = _FakeLLMGateway(response={"decision": "select"})
    result = map_claim_to_alpha(record, classifier_enabled=True, llm_gateway=gateway)

    assert result["matched_alpha"] is None
    assert result["match_status"] == "unavailable"
    assert result["alpha_match_method"] == "llm_unavailable"
    assert result["alpha_match_fallback_reason"] == "invalid_output"
    assert result["deterministic_top_alpha"] == "A101"


def test_h_non_mapping_raw_classifier_response_is_unavailable_not_deterministic():
    record = _ai_demand_record()

    def classifier(_request, *, timeout_seconds):
        del timeout_seconds
        return "not a mapping at all"

    result = map_claim_to_alpha(record, classifier=classifier, classifier_enabled=True)

    assert result["matched_alpha"] is None
    assert result["match_status"] == "unavailable"
    assert result["alpha_match_method"] == "llm_unavailable"
    assert result["alpha_match_fallback_reason"] == "invalid_output"


# ---------------------------------------------------------------------------
# I. AMBIGUOUS-LOOKING CASE -> THE LLM SELECTS ONE BEST ALPHA; NO VALID
#    "DEFER" OUTCOME EXISTS ANYMORE.
# ---------------------------------------------------------------------------


def _mixed_ambiguous_record():
    return _record(
        "AI training demand is rising, but rich valuation creates downside risk.",
        factors=["AI Demand", "Valuation Risk"],
    )


def test_i_llm_selects_the_closer_alpha_on_a_deterministically_ambiguous_claim():
    baseline = map_claim_to_alpha(_mixed_ambiguous_record(), classifier_enabled=True, llm_gateway=_FakeLLMGateway(
        response={"decision": "none", "selected_alpha_id": None}
    ))
    assert baseline["deterministic_match_status"] == "ambiguous"
    assert baseline["deterministic_top_alpha"] is None
    assert {"A101", "A304"}.issubset(set(baseline["plausible_alphas"]))

    gateway = _FakeLLMGateway(response={"decision": "select", "selected_alpha_id": "A304"})
    result = map_claim_to_alpha(_mixed_ambiguous_record(), classifier_enabled=True, llm_gateway=gateway)

    assert result["match_status"] == "matched"
    assert result["matched_alpha"] == "A304"
    assert result["alpha_match_method"] == "llm"
    # The deterministic ambiguity is preserved purely as a diagnostic --
    # never surfaced at the top level, and never a reason to withhold a
    # semantic answer.
    assert result["deterministic_match_status"] == "ambiguous"
    assert "ambiguous" not in {result["match_status"]}


def test_i_no_valid_defer_outcome_exists_a_legacy_defer_response_is_rejected():
    """A gateway (e.g. a stale Provider/prompt combination) that still
    returns the retired decision=defer wire value must be rejected as an
    unrecognized decision -- never silently treated as a successful
    "cannot decide" outcome, and never allowed to fall back to the
    deterministic Alpha."""
    record = _ai_demand_record()
    gateway = _FakeLLMGateway(response={"decision": "defer", "selected_alpha_id": None})
    result = map_claim_to_alpha(record, classifier_enabled=True, llm_gateway=gateway)

    assert result["matched_alpha"] is None
    assert result["match_status"] == "unavailable"
    assert result["alpha_match_method"] == "llm_unavailable"
    assert result["alpha_match_fallback_reason"] == "invalid_output"
    assert result["deterministic_top_alpha"] == "A101"


# ---------------------------------------------------------------------------
# J. SEMANTIC NONE PRESERVED WHEN GENUINELY NO FIT (never confused with
#    UNAVAILABLE, which has a distinct fallback_reason and method).
# ---------------------------------------------------------------------------


def test_j_semantic_none_is_preserved_and_distinct_from_unavailable():
    record = _record("The company signed an ordinary office lease with no market signal.")
    gateway = _FakeLLMGateway(response={"decision": "none", "selected_alpha_id": None})
    result = map_claim_to_alpha(record, classifier_enabled=True, llm_gateway=gateway)

    assert result["match_status"] == "no_match"
    assert result["matched_alpha"] is None
    assert result["alpha_match_method"] == "llm"
    assert result["alpha_match_fallback_reason"] is None  # distinct from unavailable's non-None reason
    assert result["classifier"]["status"] == "llm_none"
    assert result["deterministic_match_status"] == "no_match"


# ---------------------------------------------------------------------------
# K. DETERMINISTIC DIAGNOSTICS REMAIN INSPECTABLE EVEN WHEN THE SEMANTIC
#    RESULT IS NONE OR UNAVAILABLE.
# ---------------------------------------------------------------------------


def test_k_deterministic_diagnostics_remain_inspectable_under_none_and_unavailable():
    record = _ai_demand_record()

    none_result = map_claim_to_alpha(
        record, classifier_enabled=True,
        llm_gateway=_FakeLLMGateway(response={"decision": "none", "selected_alpha_id": None}),
    )
    assert none_result["matched_alpha"] is None
    assert none_result["candidate_scores"]
    assert none_result["eligible_candidates"]
    assert any(c["alpha_id"] == "A101" for c in none_result["eligible_candidates"])
    assert none_result["deterministic_top_alpha"] == "A101"

    unavailable_result = map_claim_to_alpha(
        record, classifier_enabled=True,
        llm_gateway=_FakeLLMGateway(raise_exc=RuntimeError("boom")),
    )
    assert unavailable_result["matched_alpha"] is None
    assert unavailable_result["candidate_scores"]
    assert unavailable_result["eligible_candidates"]
    assert unavailable_result["deterministic_top_alpha"] == "A101"
    assert unavailable_result["deterministic_match_status"] == "matched"


# ---------------------------------------------------------------------------
# L. B1 INTEGRATION -- the plumbing fix the dependency audit required
# ---------------------------------------------------------------------------


def test_l_b2_stance_for_alpha_finds_the_llm_matched_alpha_outside_top5():
    """B2's conflict_admissibility.stance_for_alpha reads a claim's B1
    stance by scanning eligible_candidates/top_candidates/candidate_scores
    for a dict matching matched_alpha -- it must still find it when
    matched_alpha was selected by the LLM from outside deterministic
    Tier-1, or B2 would silently treat a valid supports_alpha match as if
    it had no stance at all."""
    record = _record(
        "Etched is a niche competitor and not an immediate threat to NVIDIA AI inference.",
        factors=["Inference Demand"],
        direction="negative",
    )
    gateway = _FakeLLMGateway(response={"decision": "select", "selected_alpha_id": "A101"})
    result = map_claim_to_alpha(record, classifier_enabled=True, llm_gateway=gateway)

    assert result["matched_alpha"] == "A101"
    found_stance = stance_for_alpha(result, "A101")
    assert found_stance is not None
    assert found_stance == result["matched_evidence_stance"]


def test_l_b1_and_b2_existing_suites_are_unaffected_by_default():
    """No llm_gateway, classifier disabled (the default for every existing
    caller that doesn't opt in): under Pure-LLM semantic authority this is
    now just another "no semantic decision available" case -- matched_alpha
    is None/unavailable, exactly like a provider failure -- never a silent
    reuse of the deterministic result as if it were a semantic answer (see
    Section 8). The deterministic conclusion remains fully inspectable via
    deterministic_top_alpha/deterministic_match_status."""
    record = _ai_demand_record()
    result = map_claim_to_alpha(record)

    assert result["match_status"] == "unavailable"
    assert result["matched_alpha"] is None
    assert result["alpha_match_method"] == "llm_unavailable"
    assert result["alpha_match_fallback_reason"] == "disabled"
    assert result["classifier"]["status"] == "disabled"
    assert result["deterministic_top_alpha"] == "A101"
    assert result["deterministic_match_status"] == "matched"


# ---------------------------------------------------------------------------
# M. B2 / B4 FAIL-SAFE -- NONE/UNAVAILABLE MUST NOT CRASH OR INVENT A
#    CONFLICT OR AN ACTIVATION.
# ---------------------------------------------------------------------------


def test_m_b2_and_b4_fail_safely_on_none_and_unavailable_results():
    record = _ai_demand_record()
    none_result = map_claim_to_alpha(
        record, classifier_enabled=True,
        llm_gateway=_FakeLLMGateway(response={"decision": "none", "selected_alpha_id": None}),
    )
    unavailable_result = map_claim_to_alpha(
        record, classifier_enabled=True,
        llm_gateway=_FakeLLMGateway(raise_exc=RuntimeError("boom")),
    )

    for result in (none_result, unavailable_result):
        assert result["matched_alpha"] is None
        # A101 still has real candidate-level B1 stance data (candidate-
        # level stance is independent of the top-level semantic result --
        # task spec section 13) -- stance_for_alpha correctly finds it when
        # asked directly, it simply never becomes qualifying evidence FOR
        # A101 without a "matched" match_status (verified below via the
        # real conflict engine, not reimplemented here).
        assert stance_for_alpha(result, "A101") is not None
        # Looking up the record's OWN (null) matched_alpha is always safe.
        assert stance_for_alpha(result, result["matched_alpha"]) is None

    # B4: scoring a payload built entirely from none/unavailable results
    # must not crash, and must not fabricate a dominant activation for an
    # Alpha that was never a real semantic match.
    payload = {"matches": [none_result, unavailable_result]}
    activations = score_alpha_activations_v2(payload, ticker="NVDA")
    assert activations["dominant_alphas"] == []
    a101_activation = next(a for a in activations["alphas"] if a["alpha_id"] == "A101")
    assert a101_activation["evidence_count"] == 0

    # B2: the real conflict engine, given only none/unavailable records,
    # must not raise and must not admit any conflict -- match_status !=
    # "matched" correctly excludes both records from qualifying evidence for
    # every canonical pair, even though A101 appears in their candidate_scores.
    conflict_result = detect_alpha_conflicts(
        run_id="run1",
        ticker="NVDA",
        activation_payload=activations,
        alpha_matches=[none_result, unavailable_result],
    )
    assert conflict_result["conflicts"] == []
    assert conflict_result["main_conflict"] is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
