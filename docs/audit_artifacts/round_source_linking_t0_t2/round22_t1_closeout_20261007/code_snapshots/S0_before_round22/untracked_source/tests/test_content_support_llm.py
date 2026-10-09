"""Round 9 (2026-10-06): real LLM content-support verification -- offline
tests (task spec section 7/20 style, mirroring test_evidence_stance_llm.py).

Every test here runs with a fake gateway double; no network, no Provider, no
real LLM call anywhere in this file. The fake gateway's
``invoke_json_with_trace`` runs the REAL ``_validate_batch_shape`` validator
``content_support_llm.py`` passes it, so these tests exercise the real
batch-shape/per-item validation and fallback logic, faking only the Provider
boundary itself -- exactly the "fixed response only at the external model
boundary" scope this round's own task explicitly allows, and explicitly NOT
a claim that real semantic quality has been verified (that requires the
separately-approved limited real run, see round9's own plan document).
"""

from __future__ import annotations

import threading

from comqutor_alpha.source_provenance import (
    SOURCE_LINK_VALID,
    SUPPORT_BACKGROUND,
    SUPPORT_CITATION_ONLY,
    SUPPORT_CONDITIONAL,
    SUPPORT_OPPOSES,
    SUPPORT_PENDING_REVIEW,
    SUPPORT_SUPPORTS,
    build_source_record,
    compute_verified_support_eligibility,
)
from comqutor_alpha.structure_engine import content_support_llm as csl
from tests._content_support_v2_fixture_helpers import v2_response

_RETRIEVED_AT = "2026-10-05T17:36:24Z"


# ---------------------------------------------------------------------------
# Fake gateway: implements exactly the Week2LLMGateway surface this module
# calls, letting the real per-batch validator run against canned responses.
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
_BUDGET_EXHAUSTED = object()


class FakeContentSupportGateway:
    def __init__(self, responses):
        self._responses = list(responses)
        self._lock = threading.Lock()
        self.calls: list[tuple[str, dict]] = []
        self.finalized: list[tuple[bool, str | None]] = []

    def invoke_json_with_trace(self, task, payload, validator):
        with self._lock:
            self.calls.append((task, dict(payload)))
            assert len(self.calls) <= len(self._responses), "fake gateway received more calls than scripted"
            raw = self._responses[len(self.calls) - 1]
        if callable(raw) and raw not in (_TIMEOUT, _PROVIDER_ERROR, _BUDGET_EXHAUSTED):
            raw = raw(payload)
        if raw is _TIMEOUT:
            return _FakeInvocation(validation_accepted=False, provider_status="timeout", error_code="WEEK2_LLM_TIMEOUT")
        if raw is _PROVIDER_ERROR:
            return _FakeInvocation(validation_accepted=False, provider_status="provider_error", error_code="WEEK2_LLM_PROVIDER_ERROR")
        if raw is _BUDGET_EXHAUSTED:
            return _FakeInvocation(
                validation_accepted=False, provider_status="budget_exhausted", error_code="WEEK2_LLM_CALL_BUDGET_EXHAUSTED",
                provider_attempt_count=0,
            )
        try:
            items = validator(raw)
        except Exception:
            return _FakeInvocation(validation_accepted=False, provider_status="success", error_code="WEEK2_LLM_VALIDATION_FAILED")
        return _FakeInvocation(validation_accepted=True, validated_output=items, provider_status="success")

    def finalize_semantic_invocation(self, invocation, *, accepted, fallback_reason=None):
        with self._lock:
            self.finalized.append((accepted, fallback_reason))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _analytical_source(**overrides):
    base = dict(
        source_type="financial",
        name="Yahoo Finance",
        title="AMD income statement snapshot",
        url="",
        published_at="2026-07-30T00:00:00",
        retrieved_at=_RETRIEVED_AT,
        excerpt="AMD income statement (quarterly) Gross Profit: 2026-06-30=6203000000.0; 2026-03-31=5416000000.0",
        instrument="AMD",
        observation_date="2026-06-30",
        unit="UNKNOWN_CURRENCY",
        data_snapshot={"line_item": "Gross Profit", "periods": {"2026-06-30": 6203000000.0, "2026-03-31": 5416000000.0}},
    )
    base.update(overrides)
    return build_source_record(**base)


def _analytical_record(source, *, claim: str, claim_id: str = "claim-1") -> dict:
    return {
        "claim_id": claim_id,
        "claim": claim,
        "evidence": claim,
        "ticker": "AMD",
        "source_section": "fundamentals",
        "agent": "fundamental_agent",
        "source_link_status": SOURCE_LINK_VALID,
        "linked_source_id": source["fragment_id"],
    }


def _good_response(claim_id, source_id, quote):
    return {
        "items": [
            v2_response(
                claim_id=claim_id,
                status=csl.STATUS_SUPPORTS,
                used_source_id=source_id,
                used_location="data_snapshot.periods.2026-06-30",
                supporting_quote_or_data=quote,
                rationale="The source states this exact figure for this period.",
                supported_proposition="Gross profit was this value for this period.",
            )
        ]
    }


# ---------------------------------------------------------------------------
# No-op default
# ---------------------------------------------------------------------------


def test_no_llm_gateway_is_a_zero_cost_noop():
    source = _analytical_source()
    record = _analytical_record(source, claim="Gross margin recovery is the most important inflection point this quarter.")
    records, stats = csl.apply_llm_content_support_verification([record], [source], llm_gateway=None)
    assert records == [record]
    assert stats.llm_gateway_used is False
    assert stats.requested_count == 0


def test_claim_with_no_source_link_is_never_submitted():
    source = _analytical_source()
    record = {"claim_id": "c1", "claim": "something", "source_link_status": "NOT_PROVIDED"}
    gateway = FakeContentSupportGateway([])
    records, stats = csl.apply_llm_content_support_verification([record], [source], llm_gateway=gateway)
    assert records == [record]
    assert stats.requested_count == 0
    assert gateway.calls == []


def test_pure_data_fact_claim_never_reaches_the_llm_round8_already_resolves_it():
    source = _analytical_source()
    record = _analytical_record(source, claim="Line Item: Gross Profit; 2026-06-30: $6,203M; 2026-03-31: $5,416M")
    gateway = FakeContentSupportGateway([])
    records, stats = csl.apply_llm_content_support_verification([record], [source], llm_gateway=gateway)
    assert stats.requested_count == 0
    assert gateway.calls == []  # no Provider call spent on something the deterministic checker already proves


# ---------------------------------------------------------------------------
# Positive: a real SUPPORTS verdict reaches full, automatic eligibility
# ---------------------------------------------------------------------------


def test_valid_supports_verdict_reaches_eligible_without_any_human_review():
    source = _analytical_source()
    claim = "Gross margin expanded meaningfully this quarter, with gross profit reaching $6,203M."
    record = _analytical_record(source, claim=claim)
    gateway = FakeContentSupportGateway([_good_response("claim-1", source["source_id"], "6203000000.0")])
    records, stats = csl.apply_llm_content_support_verification([record], [source], llm_gateway=gateway)
    updated = records[0]
    assert updated["content_support_status"] == SUPPORT_SUPPORTS
    assert updated["content_support_method"] == csl.REVIEW_METHOD_LLM_CONTENT_SUPPORT_VERIFIED
    assert updated["content_support_review"]["reviewer"] is None  # never disguised as a human
    eligibility = compute_verified_support_eligibility(updated, [source])
    assert eligibility["eligible"] is True
    assert stats.llm_verified_count == 1
    assert gateway.finalized == [(True, None)]


# ---------------------------------------------------------------------------
# Negative: non-SUPPORTS statuses never count as direct support
# ---------------------------------------------------------------------------


def test_opposes_is_recorded_but_never_eligible_as_direct_support():
    source = _analytical_source()
    record = _analytical_record(source, claim="Gross margin actually compressed this quarter despite the headline revenue beat.")
    response = {
        "items": [
            v2_response(
                claim_id="claim-1",
                status=csl.STATUS_OPPOSES,
                used_source_id=source["source_id"],
                used_location="data_snapshot.periods",
                supporting_quote_or_data="6203000000.0",
                rationale="The source shows gross profit INCREASED, rebutting the claim.",
            )
        ]
    }
    gateway = FakeContentSupportGateway([response])
    records, stats = csl.apply_llm_content_support_verification([record], [source], llm_gateway=gateway)
    updated = records[0]
    assert updated["content_support_status"] == SUPPORT_OPPOSES
    eligibility = compute_verified_support_eligibility(updated, [source])
    assert eligibility["eligible"] is False
    assert eligibility["reason_code"] == "SOURCE_OPPOSES_CLAIM"


def test_background_and_citation_only_and_insufficient_are_never_eligible():
    source = _analytical_source()
    for status, expected in (
        (csl.STATUS_BACKGROUND, SUPPORT_BACKGROUND),
        (csl.STATUS_CITATION_ONLY, SUPPORT_CITATION_ONLY),
    ):
        record = _analytical_record(source, claim="Some contextual statement.", claim_id="c-" + status)
        response = {
            "items": [
                v2_response(
                    claim_id="c-" + status,
                    status=status,
                    used_source_id=source["source_id"],
                    used_location="data_snapshot.periods",
                    supporting_quote_or_data="6203000000.0",
                    rationale="context only",
                )
            ]
        }
        gateway = FakeContentSupportGateway([response])
        records, _ = csl.apply_llm_content_support_verification([record], [source], llm_gateway=gateway)
        updated = records[0]
        assert updated["content_support_status"] == expected
        assert compute_verified_support_eligibility(updated, [source])["eligible"] is False

    record = _analytical_record(source, claim="Some unrelated proposition.", claim_id="c-insufficient")
    response = {
        "items": [
            v2_response(
                claim_id="c-insufficient",
                status=csl.STATUS_INSUFFICIENT,
                rationale="No saved material bears on this claim.",
                unsupported_remainder="the whole claim",
            )
        ]
    }
    gateway = FakeContentSupportGateway([response])
    records, _ = csl.apply_llm_content_support_verification([record], [source], llm_gateway=gateway)
    updated = records[0]
    assert updated["content_support_status"] == SUPPORT_PENDING_REVIEW
    assert compute_verified_support_eligibility(updated, [source])["eligible"] is False


# ---------------------------------------------------------------------------
# Negative: partial support is never upgraded to full support (section 5)
# ---------------------------------------------------------------------------


def test_partial_support_with_unsupported_remainder_is_downgraded_to_conditional():
    source = _analytical_source()
    claim = "Gross profit hit $6,203M, confirming the AI-driven margin thesis is now fully playing out."
    record = _analytical_record(source, claim=claim)
    response = {
        "items": [
            v2_response(
                claim_id="claim-1",
                status=csl.STATUS_SUPPORTS,
                used_source_id=source["source_id"],
                used_location="data_snapshot.periods.2026-06-30",
                supporting_quote_or_data="6203000000.0",
                rationale="The figure is real; the broader thesis claim is not addressed by this material.",
                supported_proposition="Gross profit was $6,203M this period.",
                unsupported_remainder="confirming the AI-driven margin thesis is now fully playing out",
                materiality="MATERIAL",
            )
        ]
    }
    gateway = FakeContentSupportGateway([response])
    records, _ = csl.apply_llm_content_support_verification([record], [source], llm_gateway=gateway)
    updated = records[0]
    # Downgraded, never full SUPPORTS, even though the LLM's own top-level
    # status field said SUPPORTS -- the backend applies the compound-claim
    # rule itself, never trusting the top-level label alone.
    assert updated["content_support_status"] == SUPPORT_CONDITIONAL
    assert compute_verified_support_eligibility(updated, [source])["eligible"] is False
    assert updated["content_support_llm_detail"]["unsupported_remainder"]


# ---------------------------------------------------------------------------
# Negative: forged/invalid citations are rejected, never silently accepted
# ---------------------------------------------------------------------------


def test_source_id_outside_the_allowed_candidate_set_is_rejected():
    source = _analytical_source()
    other_source = _analytical_source(title="A genuinely different source title")  # real, but NOT this claim's own candidate
    assert other_source["source_id"] != source["source_id"]  # sanity: fixture must not accidentally collide
    record = _analytical_record(source, claim="Gross margin is improving meaningfully.")
    response = {
        "items": [
            v2_response(
                claim_id="claim-1",
                status=csl.STATUS_SUPPORTS,
                used_source_id=other_source["source_id"],  # forged -- not in this claim's own candidates
                used_location="data_snapshot.periods",
                supporting_quote_or_data="6203000000.0",
            )
        ]
    }
    gateway = FakeContentSupportGateway([response])
    records, stats = csl.apply_llm_content_support_verification([record], [source], llm_gateway=gateway)
    updated = records[0]
    assert "content_support_status" not in updated or updated.get("content_support_status") is None
    assert updated["content_support_llm_fallback_reason"] == csl.FALLBACK_SOURCE_NOT_IN_CANDIDATES
    assert stats.fallback_reason_counts[csl.FALLBACK_SOURCE_NOT_IN_CANDIDATES] == 1


def test_quote_not_actually_present_in_the_source_is_rejected():
    source = _analytical_source()
    record = _analytical_record(source, claim="Gross margin is improving meaningfully.")
    response = {
        "items": [
            v2_response(
                claim_id="claim-1",
                status=csl.STATUS_SUPPORTS,
                used_source_id=source["source_id"],
                used_location="data_snapshot.periods",
                supporting_quote_or_data="99999999999.0",  # not a real value in this source
            )
        ]
    }
    gateway = FakeContentSupportGateway([response])
    records, stats = csl.apply_llm_content_support_verification([record], [source], llm_gateway=gateway)
    updated = records[0]
    assert updated["content_support_llm_fallback_reason"] == csl.FALLBACK_QUOTE_OR_DATA_NOT_FOUND
    assert stats.fallback_reason_counts[csl.FALLBACK_QUOTE_OR_DATA_NOT_FOUND] == 1


def test_malformed_status_is_rejected():
    source = _analytical_source()
    record = _analytical_record(source, claim="Gross margin is improving meaningfully.")
    response = {"items": [{"claim_id": "claim-1", "status": "DEFINITELY_TRUE"}]}
    gateway = FakeContentSupportGateway([response])
    records, stats = csl.apply_llm_content_support_verification([record], [source], llm_gateway=gateway)
    assert records[0]["content_support_llm_fallback_reason"] == csl.FALLBACK_INVALID_STATUS
    assert stats.fallback_reason_counts[csl.FALLBACK_INVALID_STATUS] == 1


def test_identity_mismatch_is_rejected():
    source = _analytical_source()
    record = _analytical_record(source, claim="Gross margin is improving meaningfully.")
    response = _good_response("some-other-claim-id", source["source_id"], "6203000000.0")
    gateway = FakeContentSupportGateway([response])
    records, stats = csl.apply_llm_content_support_verification([record], [source], llm_gateway=gateway)
    assert records[0]["content_support_llm_fallback_reason"] == csl.FALLBACK_MISSING_RESULT


# ---------------------------------------------------------------------------
# Negative: request failure / truncation / budget exhaustion are preserved
# distinctly -- never silently converted to NONE or SUPPORTS (section 4)
# ---------------------------------------------------------------------------


def test_timeout_is_recorded_distinctly_and_record_is_left_unchanged():
    source = _analytical_source()
    record = _analytical_record(source, claim="Gross margin is improving meaningfully.")
    gateway = FakeContentSupportGateway([_TIMEOUT])
    records, stats = csl.apply_llm_content_support_verification([record], [source], llm_gateway=gateway)
    updated = records[0]
    assert updated["content_support_llm_fallback_reason"] == csl.FALLBACK_TIMEOUT
    assert "content_support_status" not in updated or updated.get("content_support_status") is None
    assert stats.fallback_reason_counts[csl.FALLBACK_TIMEOUT] == 1


def test_provider_error_is_recorded_distinctly():
    source = _analytical_source()
    record = _analytical_record(source, claim="Gross margin is improving meaningfully.")
    gateway = FakeContentSupportGateway([_PROVIDER_ERROR])
    records, stats = csl.apply_llm_content_support_verification([record], [source], llm_gateway=gateway)
    assert records[0]["content_support_llm_fallback_reason"] == csl.FALLBACK_PROVIDER_ERROR
    assert stats.fallback_reason_counts[csl.FALLBACK_PROVIDER_ERROR] == 1


def test_budget_exhausted_is_recorded_distinctly_never_as_none_or_supports():
    source = _analytical_source()
    record = _analytical_record(source, claim="Gross margin is improving meaningfully.")
    gateway = FakeContentSupportGateway([_BUDGET_EXHAUSTED])
    records, stats = csl.apply_llm_content_support_verification([record], [source], llm_gateway=gateway)
    updated = records[0]
    assert updated["content_support_llm_fallback_reason"] == csl.FALLBACK_BUDGET_EXHAUSTED
    assert updated.get("content_support_status") != SUPPORT_SUPPORTS
    assert stats.fallback_reason_counts[csl.FALLBACK_BUDGET_EXHAUSTED] == 1


def test_a_truncated_malformed_json_response_is_recorded_as_malformed_not_retried_into_supports():
    source = _analytical_source()
    record = _analytical_record(source, claim="Gross margin is improving meaningfully.")
    gateway = FakeContentSupportGateway([{"not_items_at_all": True}])
    records, stats = csl.apply_llm_content_support_verification([record], [source], llm_gateway=gateway)
    updated = records[0]
    assert updated["content_support_llm_fallback_reason"] == csl.FALLBACK_MALFORMED_RESPONSE
    assert updated.get("content_support_status") != SUPPORT_SUPPORTS


def test_duplicate_results_for_the_same_claim_are_rejected_not_arbitrarily_picked():
    source = _analytical_source()
    record = _analytical_record(source, claim="Gross margin is improving meaningfully.")
    response = {
        "items": [
            v2_response(
                claim_id="claim-1",
                status=csl.STATUS_SUPPORTS,
                used_source_id=source["source_id"],
                used_location="x",
                supporting_quote_or_data="6203000000.0",
                rationale="a",
                supported_proposition="a",
            ),
            v2_response(
                claim_id="claim-1",
                status=csl.STATUS_OPPOSES,
                used_source_id=source["source_id"],
                used_location="x",
                supporting_quote_or_data="6203000000.0",
                rationale="b",
            ),
        ]
    }
    gateway = FakeContentSupportGateway([response])
    records, stats = csl.apply_llm_content_support_verification([record], [source], llm_gateway=gateway)
    assert records[0]["content_support_llm_fallback_reason"] == csl.FALLBACK_DUPLICATE_RESULT
    assert stats.fallback_reason_counts[csl.FALLBACK_DUPLICATE_RESULT] == 1


# ---------------------------------------------------------------------------
# Batching: multiple claims across more than one batch
# ---------------------------------------------------------------------------


def test_multiple_claims_batch_correctly_and_each_gets_its_own_result():
    source = _analytical_source()
    records_in = [
        _analytical_record(source, claim=f"Gross margin claim number {i} with real figure $6,203M.", claim_id=f"claim-{i}")
        for i in range(7)  # > BATCH_SIZE(5) -- exercises two batches
    ]

    def _respond(payload):
        return {
            "items": [
                v2_response(
                    claim_id=item["claim_id"],
                    status=csl.STATUS_SUPPORTS,
                    used_source_id=source["source_id"],
                    used_location="data_snapshot.periods.2026-06-30",
                    supporting_quote_or_data="6203000000.0",
                )
                for item in payload["items"]
            ]
        }

    gateway = FakeContentSupportGateway([_respond, _respond])
    records_out, stats = csl.apply_llm_content_support_verification(records_in, [source], llm_gateway=gateway)
    assert len(gateway.calls) == 2
    assert stats.llm_verified_count == 7
    assert all(r["content_support_status"] == SUPPORT_SUPPORTS for r in records_out)
