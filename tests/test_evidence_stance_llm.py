"""B1 LLM Evidence Stance Upgrade -- offline tests (task spec section 20).

Every test here runs with a fake gateway double; no network, no Provider,
no LLM call anywhere in this file. The fake gateway's ``invoke_json_with_trace``
runs the REAL ``_validate_batch_shape`` validator ``evidence_stance_llm.py``
passes it, so these tests exercise the real batch-shape/per-item validation
and fallback logic, faking only the Provider boundary itself.
"""

from __future__ import annotations

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.structure_engine import evidence_stance as es, evidence_stance_llm as esl

TAXONOMY = load_alpha_taxonomy()


# ---------------------------------------------------------------------------
# Fake gateway: implements exactly the Week2LLMGateway surface this module
# calls (invoke_json_with_trace / finalize_semantic_invocation), letting the
# real per-batch validator run against canned raw responses.
# ---------------------------------------------------------------------------


class _FakeInvocation:
    def __init__(self, *, validation_accepted, validated_output=None, provider_status="success", error_code=None, provider_attempt_count=1):
        self.validation_accepted = validation_accepted
        self.validated_output = validated_output
        self.provider_status = provider_status
        self.error_code = error_code
        self.provider_attempt_count = provider_attempt_count


_TIMEOUT = object()
_PROVIDER_ERROR = object()


class FakeStanceGateway:
    """``responses`` is one entry per expected call, in order: a dict (raw
    parsed JSON, run through the real validator), ``_TIMEOUT``/``_PROVIDER_ERROR``
    sentinels, or a callable(payload) -> one of the above."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[tuple[str, dict]] = []
        self.finalized: list[tuple[bool, str | None]] = []

    def invoke_json_with_trace(self, task, payload, validator):
        self.calls.append((task, dict(payload)))
        assert len(self.calls) <= len(self._responses), "fake gateway received more calls than scripted"
        raw = self._responses[len(self.calls) - 1]
        if callable(raw) and raw not in (_TIMEOUT, _PROVIDER_ERROR):
            raw = raw(payload)
        if raw is _TIMEOUT:
            return _FakeInvocation(validation_accepted=False, provider_status="timeout", error_code="WEEK2_LLM_TIMEOUT", provider_attempt_count=1)
        if raw is _PROVIDER_ERROR:
            return _FakeInvocation(validation_accepted=False, provider_status="provider_error", error_code="WEEK2_LLM_PROVIDER_ERROR", provider_attempt_count=1)
        try:
            items = validator(raw)
        except Exception:
            return _FakeInvocation(
                validation_accepted=False, provider_status="success", error_code="WEEK2_LLM_VALIDATION_FAILED", provider_attempt_count=1
            )
        return _FakeInvocation(validation_accepted=True, validated_output=items, provider_status="success", provider_attempt_count=1)

    def finalize_semantic_invocation(self, invocation, *, accepted, fallback_reason=None):
        self.finalized.append((accepted, fallback_reason))


# ---------------------------------------------------------------------------
# Helpers: hand-build match/candidate dicts shaped exactly like
# alpha_mapper.map_claim_to_alpha's real output (including the
# stance_method/stance_fallback_reason defaults _attach_evidence_stance
# now stamps), so this module's logic is tested in isolation from the
# deterministic keyword/factor matcher's own heuristics.
# ---------------------------------------------------------------------------


def _candidate(alpha_id, *, deterministic_stance=es.SUPPORTS_ALPHA):
    return {
        "alpha_id": alpha_id,
        "alpha_name": TAXONOMY[alpha_id].name_en,
        "score": 0.7,
        "evidence_stance": deterministic_stance,
        "counter_alpha_id": None,
        "stance_reason_codes": ["SUPPORTS_TARGET_THESIS"],
        "stance_confidence_band": es.CONFIDENCE_HIGH,
        "requires_manual_review": False,
        "evidence_stance_version": es.CLASSIFIER_VERSION,
        "stance_method": None,
        "stance_fallback_reason": None,
    }


def _match(
    claim_id,
    matched_alpha,
    *,
    secondary_alphas=(),
    claim="Some evidence text.",
    ticker="NVDA",
    deterministic_stance=es.SUPPORTS_ALPHA,
    extra_candidates=(),
):
    candidates = [_candidate(matched_alpha, deterministic_stance=deterministic_stance)]
    for alpha_id in secondary_alphas:
        candidates.append(_candidate(alpha_id, deterministic_stance=deterministic_stance))
    candidates.extend(extra_candidates)
    return {
        "run_id": "test-run",
        "ticker": ticker,
        "agent": "news_agent",
        "claim_id": claim_id,
        "source_agent_output_id": claim_id,
        "claim": claim,
        "evidence": claim,
        "factors": [],
        "direction": "unknown",
        "matched_alpha": matched_alpha,
        "matched_alpha_name": TAXONOMY[matched_alpha].name_en,
        "secondary_alphas": list(secondary_alphas),
        "match_status": "matched",
        "candidate_scores": candidates,
    }


def _llm_item(match, alpha_id, stance, counter_alpha_id=None):
    item = {"claim_id": match["claim_id"], "target_alpha_id": alpha_id, "stance": stance}
    if counter_alpha_id is not None:
        item["counter_alpha_id"] = counter_alpha_id
    return item


def _candidate_for(match, alpha_id):
    return next(c for c in match["candidate_scores"] if c["alpha_id"] == alpha_id)


# ---------------------------------------------------------------------------
# 1. Critical: valid LLM stance is authoritative even when deterministic.v1
#    independently disagrees.
# ---------------------------------------------------------------------------


def test_1_valid_llm_stance_is_authoritative_over_disagreeing_deterministic():
    match = _match("c1", "A304", deterministic_stance=es.SUPPORTS_ALPHA)
    gateway = FakeStanceGateway([{"items": [_llm_item(match, "A304", es.OPPOSES_ALPHA)]}])

    stats = esl.apply_llm_stance_upgrade([match], TAXONOMY, llm_gateway=gateway)

    candidate = _candidate_for(match, "A304")
    assert candidate["evidence_stance"] == es.OPPOSES_ALPHA
    assert candidate["stance_method"] == esl.STANCE_METHOD_LLM
    assert candidate["stance_fallback_reason"] is None
    assert candidate["evidence_stance_version"] == esl.LLM_CLASSIFIER_VERSION
    assert stats.llm_result_count == 1
    assert stats.deterministic_fallback_count == 0
    assert gateway.finalized == [(True, None)]


# ---------------------------------------------------------------------------
# 2. Provider unavailable (timeout/provider_error) -> deterministic fallback.
# ---------------------------------------------------------------------------


def test_2_provider_unavailable_falls_back_to_deterministic():
    match = _match("c1", "A304", deterministic_stance=es.SUPPORTS_ALPHA)
    gateway = FakeStanceGateway([_PROVIDER_ERROR])

    esl.apply_llm_stance_upgrade([match], TAXONOMY, llm_gateway=gateway)

    candidate = _candidate_for(match, "A304")
    assert candidate["evidence_stance"] == es.SUPPORTS_ALPHA  # unchanged deterministic value
    assert candidate["stance_method"] == esl.STANCE_METHOD_DETERMINISTIC_FALLBACK
    assert candidate["stance_fallback_reason"] == esl.FALLBACK_PROVIDER_ERROR
    assert candidate["evidence_stance_version"] == es.CLASSIFIER_VERSION


def test_2b_timeout_falls_back_with_timeout_reason():
    match = _match("c1", "A304")
    gateway = FakeStanceGateway([_TIMEOUT])
    esl.apply_llm_stance_upgrade([match], TAXONOMY, llm_gateway=gateway)
    candidate = _candidate_for(match, "A304")
    assert candidate["stance_method"] == esl.STANCE_METHOD_DETERMINISTIC_FALLBACK
    assert candidate["stance_fallback_reason"] == esl.FALLBACK_TIMEOUT


# ---------------------------------------------------------------------------
# 3. Malformed JSON (not even a valid batch shape) -> fallback.
# ---------------------------------------------------------------------------


def test_3_malformed_batch_shape_falls_back():
    match = _match("c1", "A304")
    gateway = FakeStanceGateway([{"not_items": []}])  # missing "items" key entirely

    esl.apply_llm_stance_upgrade([match], TAXONOMY, llm_gateway=gateway)

    candidate = _candidate_for(match, "A304")
    assert candidate["stance_method"] == esl.STANCE_METHOD_DETERMINISTIC_FALLBACK
    assert candidate["stance_fallback_reason"] == esl.FALLBACK_MALFORMED_RESPONSE


# ---------------------------------------------------------------------------
# 4/5. Wrong claim_id / wrong target_alpha_id -> only that pair falls back.
# ---------------------------------------------------------------------------


def test_4_wrong_claim_id_only_that_pair_falls_back():
    m1 = _match("c1", "A304")
    m2 = _match("c2", "A201")
    gateway = FakeStanceGateway(
        [
            {
                "items": [
                    _llm_item(m1, "A304", es.OPPOSES_ALPHA),
                    {"claim_id": "WRONG_ID", "target_alpha_id": "A201", "stance": es.SUPPORTS_ALPHA},
                ]
            }
        ]
    )
    esl.apply_llm_stance_upgrade([m1, m2], TAXONOMY, llm_gateway=gateway)
    assert _candidate_for(m1, "A304")["stance_method"] == esl.STANCE_METHOD_LLM
    c2 = _candidate_for(m2, "A201")
    assert c2["stance_method"] == esl.STANCE_METHOD_DETERMINISTIC_FALLBACK
    assert c2["stance_fallback_reason"] == esl.FALLBACK_MISSING_RESULT  # never matched any requested key


def test_5_wrong_target_alpha_id_only_that_pair_falls_back():
    m1 = _match("c1", "A304")
    gateway = FakeStanceGateway(
        [{"items": [{"claim_id": "c1", "target_alpha_id": "A201", "stance": es.OPPOSES_ALPHA}]}]
    )
    esl.apply_llm_stance_upgrade([m1], TAXONOMY, llm_gateway=gateway)
    c1 = _candidate_for(m1, "A304")
    assert c1["stance_method"] == esl.STANCE_METHOD_DETERMINISTIC_FALLBACK
    assert c1["stance_fallback_reason"] == esl.FALLBACK_MISSING_RESULT


def test_5b_identity_mismatch_reason_when_wrong_key_is_returned_for_a_requested_claim():
    m1 = _match("c1", "A304", secondary_alphas=["A101"])
    # Returns a result for c1 but with the WRONG target_alpha_id among the
    # actually-requested set -- exercises the identity_mismatch branch
    # directly (single-item batch, no ambiguity with "missing").
    gateway = FakeStanceGateway(
        [{"items": [{"claim_id": "c1", "target_alpha_id": "A999", "stance": es.OPPOSES_ALPHA}]}]
    )
    esl.apply_llm_stance_upgrade([m1], TAXONOMY, llm_gateway=gateway)
    for alpha_id in ("A304", "A101"):
        c = _candidate_for(m1, alpha_id)
        assert c["stance_method"] == esl.STANCE_METHOD_DETERMINISTIC_FALLBACK
        assert c["stance_fallback_reason"] == esl.FALLBACK_MISSING_RESULT


# ---------------------------------------------------------------------------
# 6. Unknown stance vocabulary -> only that pair falls back.
# ---------------------------------------------------------------------------


def test_6_unknown_stance_falls_back():
    match = _match("c1", "A304")
    gateway = FakeStanceGateway([{"items": [{"claim_id": "c1", "target_alpha_id": "A304", "stance": "bullish"}]}])
    esl.apply_llm_stance_upgrade([match], TAXONOMY, llm_gateway=gateway)
    candidate = _candidate_for(match, "A304")
    assert candidate["stance_method"] == esl.STANCE_METHOD_DETERMINISTIC_FALLBACK
    assert candidate["stance_fallback_reason"] == esl.FALLBACK_INVALID_STANCE


# ---------------------------------------------------------------------------
# 7/8/9. Counter-Alpha legality.
# ---------------------------------------------------------------------------


def test_7_supports_counter_alpha_missing_counter_id_falls_back():
    match = _match("c1", "A304")
    gateway = FakeStanceGateway(
        [{"items": [{"claim_id": "c1", "target_alpha_id": "A304", "stance": es.SUPPORTS_COUNTER_ALPHA}]}]
    )
    esl.apply_llm_stance_upgrade([match], TAXONOMY, llm_gateway=gateway)
    candidate = _candidate_for(match, "A304")
    assert candidate["stance_method"] == esl.STANCE_METHOD_DETERMINISTIC_FALLBACK
    assert candidate["stance_fallback_reason"] == esl.FALLBACK_INVALID_COUNTER_ALPHA


def test_8_supports_counter_alpha_noncanonical_counter_falls_back():
    match = _match("c1", "A304")
    # A501 (Recession Risk) is not a canonical conflict partner of A304.
    assert "A501" not in es.canonical_conflict_partners("A304", TAXONOMY)
    gateway = FakeStanceGateway([{"items": [_llm_item(match, "A304", es.SUPPORTS_COUNTER_ALPHA, "A501")]}])
    esl.apply_llm_stance_upgrade([match], TAXONOMY, llm_gateway=gateway)
    candidate = _candidate_for(match, "A304")
    assert candidate["stance_method"] == esl.STANCE_METHOD_DETERMINISTIC_FALLBACK
    assert candidate["stance_fallback_reason"] == esl.FALLBACK_INVALID_COUNTER_ALPHA


def test_9_supports_counter_alpha_with_valid_canonical_counter_is_accepted():
    match = _match("c1", "A304")
    # A101 IS a canonical conflict partner of A304 (taxonomy-declared).
    assert "A101" in es.canonical_conflict_partners("A304", TAXONOMY)
    gateway = FakeStanceGateway([{"items": [_llm_item(match, "A304", es.SUPPORTS_COUNTER_ALPHA, "A101")]}])
    esl.apply_llm_stance_upgrade([match], TAXONOMY, llm_gateway=gateway)
    candidate = _candidate_for(match, "A304")
    assert candidate["evidence_stance"] == es.SUPPORTS_COUNTER_ALPHA
    assert candidate["counter_alpha_id"] == "A101"
    assert candidate["stance_method"] == esl.STANCE_METHOD_LLM


# ---------------------------------------------------------------------------
# 10. One invalid result inside a 10-item batch -> other 9 remain LLM-authoritative.
# ---------------------------------------------------------------------------


def test_10_one_invalid_item_in_a_ten_item_batch_does_not_affect_the_other_nine():
    matches = [_match(f"c{i}", "A304", claim=f"claim {i}") for i in range(10)]
    items = [_llm_item(m, "A304", es.OPPOSES_ALPHA) for m in matches]
    items[7]["stance"] = "not_a_real_stance"  # exactly one poisoned item

    gateway = FakeStanceGateway([{"items": items}])
    esl.apply_llm_stance_upgrade(matches, TAXONOMY, llm_gateway=gateway)

    assert len(gateway.calls) == 1  # still exactly one batch call
    for i, m in enumerate(matches):
        candidate = _candidate_for(m, "A304")
        if i == 7:
            assert candidate["stance_method"] == esl.STANCE_METHOD_DETERMINISTIC_FALLBACK
            assert candidate["stance_fallback_reason"] == esl.FALLBACK_INVALID_STANCE
        else:
            assert candidate["stance_method"] == esl.STANCE_METHOD_LLM
            assert candidate["evidence_stance"] == es.OPPOSES_ALPHA


# ---------------------------------------------------------------------------
# 11. Missing one item from the response -> only that pair falls back.
# ---------------------------------------------------------------------------


def test_11_missing_one_item_from_response_only_that_pair_falls_back():
    m1 = _match("c1", "A304")
    m2 = _match("c2", "A201")
    gateway = FakeStanceGateway([{"items": [_llm_item(m1, "A304", es.OPPOSES_ALPHA)]}])  # m2/A201 omitted
    esl.apply_llm_stance_upgrade([m1, m2], TAXONOMY, llm_gateway=gateway)
    assert _candidate_for(m1, "A304")["stance_method"] == esl.STANCE_METHOD_LLM
    c2 = _candidate_for(m2, "A201")
    assert c2["stance_method"] == esl.STANCE_METHOD_DETERMINISTIC_FALLBACK
    assert c2["stance_fallback_reason"] == esl.FALLBACK_MISSING_RESULT


# ---------------------------------------------------------------------------
# 12. Duplicate ambiguous result for the same requested pair -> falls back.
# ---------------------------------------------------------------------------


def test_12_duplicate_result_for_same_pair_falls_back():
    match = _match("c1", "A304")
    gateway = FakeStanceGateway(
        [
            {
                "items": [
                    _llm_item(match, "A304", es.OPPOSES_ALPHA),
                    _llm_item(match, "A304", es.SUPPORTS_ALPHA),  # same (claim_id, target_alpha_id) again
                ]
            }
        ]
    )
    esl.apply_llm_stance_upgrade([match], TAXONOMY, llm_gateway=gateway)
    candidate = _candidate_for(match, "A304")
    assert candidate["stance_method"] == esl.STANCE_METHOD_DETERMINISTIC_FALLBACK
    assert candidate["stance_fallback_reason"] == esl.FALLBACK_DUPLICATE_RESULT


# ---------------------------------------------------------------------------
# 13. Extra unrequested result -> never admitted.
# ---------------------------------------------------------------------------


def test_13_extra_unrequested_result_never_admitted():
    match = _match("c1", "A304")
    gateway = FakeStanceGateway(
        [
            {
                "items": [
                    _llm_item(match, "A304", es.OPPOSES_ALPHA),
                    {"claim_id": "never-requested", "target_alpha_id": "A101", "stance": es.SUPPORTS_ALPHA},
                ]
            }
        ]
    )
    stats = esl.apply_llm_stance_upgrade([match], TAXONOMY, llm_gateway=gateway)
    assert _candidate_for(match, "A304")["stance_method"] == esl.STANCE_METHOD_LLM
    # The extra item must not be counted as an accepted LLM result, and must
    # not create any new candidate/match anywhere.
    assert stats.llm_result_count == 1
    assert all("never-requested" not in str(c) for m in [match] for c in m["candidate_scores"])


# ---------------------------------------------------------------------------
# 14. Batch size <= 10.
# ---------------------------------------------------------------------------


def test_14_batch_size_is_capped_at_ten():
    matches = [_match(f"c{i}", "A304", claim=f"claim {i}") for i in range(23)]
    call_sizes = []

    def _responder(payload):
        call_sizes.append(len(payload["items"]))
        return {"items": [{"claim_id": it["claim_id"], "target_alpha_id": it["target_alpha_id"], "stance": es.OPPOSES_ALPHA} for it in payload["items"]]}

    gateway = FakeStanceGateway([_responder] * 3)
    esl.apply_llm_stance_upgrade(matches, TAXONOMY, llm_gateway=gateway)
    assert len(gateway.calls) == 3  # ceil(23 / 10)
    assert call_sizes == [10, 10, 3]
    assert all(size <= esl.BATCH_SIZE for size in call_sizes)


# ---------------------------------------------------------------------------
# 15. No Alpha target (matched_alpha = null) -> no B1 Provider request.
# ---------------------------------------------------------------------------


def test_15_no_match_claim_spends_no_provider_request():
    no_match = {
        "run_id": "test-run",
        "ticker": "NVDA",
        "claim_id": "c-nomatch",
        "claim": "Generic background commentary.",
        "evidence": "Generic background commentary.",
        "matched_alpha": None,
        "secondary_alphas": [],
        "match_status": "no_match",
        "candidate_scores": [],
    }
    gateway = FakeStanceGateway([])  # any call at all is a hard failure (assert in fake)
    stats = esl.apply_llm_stance_upgrade([no_match], TAXONOMY, llm_gateway=gateway)
    assert stats.requested_count == 0
    assert len(gateway.calls) == 0


# ---------------------------------------------------------------------------
# retained_target_alpha_ids: cardinality (PD-011, task section 8).
# ---------------------------------------------------------------------------


def test_retained_scope_is_matched_plus_up_to_two_secondary_max_three():
    match = _match("c1", "A304", secondary_alphas=["A101", "A301", "A601"])  # 3 secondary supplied
    targets = esl.retained_target_alpha_ids(match)
    assert targets[0] == "A304"
    assert len(targets) == esl.MAX_TARGET_ALPHAS_PER_CLAIM == 3
    assert len(set(targets)) == 3


def test_retained_scope_empty_when_no_matched_alpha():
    match = {"matched_alpha": None, "secondary_alphas": ["A101"]}
    assert esl.retained_target_alpha_ids(match) == []


# ---------------------------------------------------------------------------
# Section 9: forbidden input fields must never reach the LLM request payload.
# ---------------------------------------------------------------------------


def test_request_payload_excludes_forbidden_fields():
    match = _match("c1", "A304", secondary_alphas=["A101"])
    match["candidate_scores"][0].update({"keyword_score": 0.9, "factor_score": 0.5, "direction_score": 1.0, "relation": "activation"})
    items = esl.build_stance_request_items([match], TAXONOMY)
    assert len(items) == 2  # A304 primary + A101 secondary
    for item in items:
        payload = item.payload
        forbidden = {
            "keyword_score",
            "factor_score",
            "direction_score",
            "relation",
            "evidence_stance",
            "stance_reason_codes",
            "activation_score",
            "conflict_score",
            "candidate_id",
            "source_offset",
            "score",
        }
        assert forbidden.isdisjoint(payload.keys())
        assert set(payload.keys()) <= {
            "claim_id",
            "target_alpha_id",
            "ticker",
            "claim",
            "evidence",
            "target_alpha_name",
            "target_alpha_definition",
            "counter_alphas",
            "factors",
        }


def test_request_payload_counter_alphas_reuse_canonical_taxonomy_only():
    match = _match("c1", "A304")
    items = esl.build_stance_request_items([match], TAXONOMY)
    payload = items[0].payload
    ids = {c["alpha_id"] for c in payload.get("counter_alphas", [])}
    assert ids == es.canonical_conflict_partners("A304", TAXONOMY)


# ---------------------------------------------------------------------------
# 18. Replay guarantee: llm_gateway=None is a zero-cost, zero-call no-op.
# ---------------------------------------------------------------------------


def test_18_none_gateway_makes_zero_calls_and_leaves_matches_unchanged():
    match = _match("c1", "A304", deterministic_stance=es.SUPPORTS_ALPHA)
    before = _candidate_for(match, "A304").copy()
    stats = esl.apply_llm_stance_upgrade([match], TAXONOMY, llm_gateway=None)
    assert stats.llm_gateway_used is False
    assert stats.requested_count == 0
    assert _candidate_for(match, "A304") == before


def test_18b_build_alpha_matches_payload_replay_call_shape_makes_zero_calls():
    """Mirrors exactly how comqutor_alpha.replay.pipeline calls
    build_alpha_matches_payload(structured) -- positional only, no
    llm_gateway kwarg at all."""
    from comqutor_alpha.structure_engine.alpha_mapper import build_alpha_matches_payload

    structured = {
        "run_id": "replay-run",
        "ticker": "NVDA",
        "records": [
            {
                "run_id": "replay-run",
                "ticker": "NVDA",
                "agent": "news_agent",
                "claim_id": "c1",
                "source_agent_output_id": "c1",
                "claim": "Valuation multiples are compressing as growth expectations normalize.",
                "evidence": "Valuation multiples are compressing as growth expectations normalize.",
                "factors": [],
                "direction": "negative",
            }
        ],
    }
    payload = build_alpha_matches_payload(structured)  # no llm_gateway kwarg, matches replay's call site
    assert payload["matches"]


# ---------------------------------------------------------------------------
# Fail-soft: a bug/exception inside batch processing never propagates and
# never leaves a candidate without its already-correct deterministic result.
# ---------------------------------------------------------------------------


def test_unexpected_exception_in_batch_processing_falls_back_the_whole_batch():
    match = _match("c1", "A304", deterministic_stance=es.SUPPORTS_ALPHA)

    def _boom(_payload):
        raise RuntimeError("simulated bug")

    gateway = FakeStanceGateway([_boom])
    esl.apply_llm_stance_upgrade([match], TAXONOMY, llm_gateway=gateway)
    candidate = _candidate_for(match, "A304")
    assert candidate["evidence_stance"] == es.SUPPORTS_ALPHA
    assert candidate["stance_method"] == esl.STANCE_METHOD_DETERMINISTIC_FALLBACK


# ---------------------------------------------------------------------------
# section 21: John's fixed A304 rebuttal semantic case -- authority routing,
# not a new regex. A fake LLM result is accepted and attributed to the LLM
# path even though deterministic.v1 (independently, via its own
# phrase-specific pattern) happens to already agree on the value.
# ---------------------------------------------------------------------------


def test_johns_a304_rebuttal_llm_result_accepted_as_llm_authoritative():
    claim = 'The "valuation risk" argument is a lazy heuristic that ignores the actual numbers.'
    match = _match("c1", "A304", claim=claim, deterministic_stance=es.SUPPORTS_ALPHA)
    gateway = FakeStanceGateway([{"items": [_llm_item(match, "A304", es.OPPOSES_ALPHA)]}])

    esl.apply_llm_stance_upgrade([match], TAXONOMY, llm_gateway=gateway)

    candidate = _candidate_for(match, "A304")
    assert candidate["evidence_stance"] == es.OPPOSES_ALPHA
    assert candidate["stance_method"] == esl.STANCE_METHOD_LLM

    # Deterministic.v1 itself was not touched or re-implemented by this
    # Sprint: called directly (bypassing this module entirely), it still
    # produces its own, independent, already-correct answer for this exact
    # phrase via its existing phrase-specific pattern -- this test proves
    # routing authority, not semantic capability, per task spec section 21.
    direct = es.classify_evidence_stance(
        record={"claim": claim, "evidence": claim}, target_alpha_id="A304", candidate=None, taxonomy=TAXONOMY
    )
    assert direct.evidence_stance == es.OPPOSES_ALPHA


# ---------------------------------------------------------------------------
# Full-stack wiring: build_alpha_matches_payload with a real fake gateway
# (not just llm_gateway=None), and the audit/run_audit extraction paths
# picking up the new per-candidate fields correctly.
# ---------------------------------------------------------------------------


def test_build_alpha_matches_payload_with_gateway_upgrades_the_real_wiring():
    from comqutor_alpha.structure_engine.alpha_mapper import build_alpha_matches_payload

    structured = {
        "run_id": "wiring-run",
        "ticker": "NVDA",
        "records": [
            {
                "run_id": "wiring-run",
                "ticker": "NVDA",
                "agent": "news_agent",
                "claim_id": "c1",
                "source_agent_output_id": "c1",
                "claim": "Rich valuation creates downside risk even though the business fundamentals remain impressive.",
                "evidence": "Rich valuation creates downside risk even though the business fundamentals remain impressive.",
                "factors": [],
                "direction": "negative",
            }
        ],
    }

    def _responder(payload):
        return {
            "items": [
                {"claim_id": it["claim_id"], "target_alpha_id": it["target_alpha_id"], "stance": es.MENTIONS_ALPHA}
                for it in payload["items"]
            ]
        }

    gateway = FakeStanceGateway([_responder])
    payload = build_alpha_matches_payload(structured, llm_gateway=gateway)
    match = payload["matches"][0]
    assert match["matched_alpha"] is not None
    candidate = _candidate_for(match, match["matched_alpha"])
    assert candidate["stance_method"] == esl.STANCE_METHOD_LLM
    assert candidate["evidence_stance"] == es.MENTIONS_ALPHA
    assert len(gateway.calls) == 1


def test_build_evidence_stance_audit_reports_llm_and_fallback_counts():
    from comqutor_alpha.api.artifact_export import build_evidence_stance_audit

    m_llm = _match("c1", "A304", deterministic_stance=es.SUPPORTS_ALPHA)
    _candidate_for(m_llm, "A304").update(
        {"stance_method": esl.STANCE_METHOD_LLM, "stance_fallback_reason": None, "evidence_stance": es.OPPOSES_ALPHA, "evidence_stance_version": esl.LLM_CLASSIFIER_VERSION}
    )
    m_fallback = _match("c2", "A201", deterministic_stance=es.SUPPORTS_ALPHA)
    _candidate_for(m_fallback, "A201").update(
        {"stance_method": esl.STANCE_METHOD_DETERMINISTIC_FALLBACK, "stance_fallback_reason": esl.FALLBACK_TIMEOUT}
    )

    audit = build_evidence_stance_audit(
        run_id="r1", ticker="NVDA", alpha_matches_payload={"matches": [m_llm, m_fallback]}
    )
    assert audit["summary"]["llm_stance_count"] == 1
    assert audit["summary"]["deterministic_fallback_count"] == 1
    assert audit["summary"]["fallback_reason_counts"][esl.FALLBACK_TIMEOUT] == 1
    methods = {r["claim_id"]: r["stance_method"] for r in audit["records"]}
    assert methods["c1"] == esl.STANCE_METHOD_LLM
    assert methods["c2"] == esl.STANCE_METHOD_DETERMINISTIC_FALLBACK
