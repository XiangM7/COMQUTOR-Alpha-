"""Step 5A (v0.1.2.1) Week2 Alpha Mapper runtime-capacity repair -- offline
tests (task spec section 13, revised after real controlled-Provider
validation showed multi-claim batching unreliable against DeepSeek
deepseek-v4-flash regardless of batch size/timeout -- see
docs/audit_artifacts/week2_runtime_capacity_repair_v0.1.2.1.md). The
production repair is: single-claim semantics (proven reliable, ~1.8-2s per
call) + a workload-aware bounded call budget + controlled bounded
concurrency. Every test here runs with a fake gateway double; no network,
no real Provider, no real timing anywhere in this file.
"""

from __future__ import annotations

import threading
import time

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.regression import semantic_execution_health as seh
from comqutor_alpha.structure_engine.alpha_mapper import (
    _classify_alpha_batch_with_llm,
    _classify_alpha_concurrent_with_llm,
    map_claim_to_alpha,
    map_structured_records,
)
from comqutor_alpha.structure_engine.week2_llm import (
    CALL_BUDGET_SAFETY_MARGIN,
    DEFAULT_MAX_CALLS,
    DEFAULT_MAX_RETRIES,
    ENRICHMENT_BATCH_SIZE,
    MAX_EXPECTED_CLAIMS_PER_TICKER,
    MAX_SERVER_CALLS,
    OTHER_TASK_CALL_ALLOWANCE,
    compute_workload_aware_max_calls,
)

TAXONOMY = load_alpha_taxonomy()
_TIMEOUT = object()


def _record(claim_id, *, factors=None, direction="neutral", ticker="NVDA"):
    text = f"AI training demand is accelerating and GPU demand is rising for {ticker} ({claim_id})."
    return {
        "run_id": "run1",
        "ticker": ticker,
        "agent": "news_agent",
        "claim_id": claim_id,
        "claim": text,
        "evidence": text,
        "factors": factors or ["AI Demand", "GPU Demand"],
        "direction": direction,
        "confidence": 0.8,
        "source_agent_output_id": "run1:news_agent:news_report",
    }


class _FakeInvocation:
    def __init__(self, *, validation_accepted, validated_output=None, provider_status="success", error_code=None, provider_attempt_count=1):
        self.validation_accepted = validation_accepted
        self.validated_output = validated_output
        self.provider_status = provider_status
        self.error_code = error_code
        self.provider_attempt_count = provider_attempt_count


class _BudgetedFakeGateway:
    """Mimics Week2LLMGateway's observable invoke_json_with_trace/
    finalize_semantic_invocation/_reserve_call contract for offline tests,
    INCLUDING its real thread-safety properties (a lock-protected shared
    call counter) so concurrency-safety tests are genuine, not merely
    assumed. ``responder`` is called once per logical call (not per
    attempt) with the request payload and must return a raw response dict,
    or the ``_TIMEOUT`` sentinel (every attempt for that logical call times
    out)."""

    def __init__(self, responder, *, max_calls=10_000, max_retries=DEFAULT_MAX_RETRIES, latency_seconds=0.0):
        self.semantic_runtime = True
        self._responder = responder
        self.max_calls = max_calls
        self.max_retries = max_retries
        self._call_count = 0
        self._lock = threading.Lock()
        self.calls: list[tuple[str, dict]] = []
        self.finalized: list[tuple[bool, str | None]] = []
        self.latency_seconds = latency_seconds

    def _reserve_call(self) -> bool:
        with self._lock:
            if self._call_count >= self.max_calls:
                return False
            self._call_count += 1
            return True

    def invoke_json_with_trace(self, task, payload, validator):
        last_attempt_count = 0
        for attempt in range(1, self.max_retries + 2):
            if not self._reserve_call():
                return _FakeInvocation(
                    validation_accepted=False, provider_status="budget_exhausted",
                    error_code="WEEK2_LLM_CALL_BUDGET_EXHAUSTED", provider_attempt_count=last_attempt_count,
                )
            last_attempt_count = attempt
            with self._lock:
                self.calls.append((task, payload))
            if self.latency_seconds:
                time.sleep(self.latency_seconds)
            raw = self._responder(payload)  # called fresh per attempt, matching a real provider call
            if raw is _TIMEOUT:
                continue
            try:
                validated = validator(raw)
            except Exception:
                return _FakeInvocation(
                    validation_accepted=False, provider_status="success",
                    error_code="WEEK2_LLM_VALIDATION_FAILED", provider_attempt_count=attempt,
                )
            return _FakeInvocation(
                validation_accepted=True, validated_output=validated,
                provider_status="success", provider_attempt_count=attempt,
            )
        return _FakeInvocation(
            validation_accepted=False, provider_status="timeout",
            error_code="WEEK2_LLM_TIMEOUT", provider_attempt_count=last_attempt_count,
        )

    def finalize_semantic_invocation(self, invocation, *, accepted, fallback_reason=None):
        with self._lock:
            self.finalized.append((accepted, fallback_reason))

    @property
    def call_count(self):
        with self._lock:
            return self._call_count


def _single_claim_none_responder(_payload):
    return {"decision": "none", "selected_alpha_id": None}


def _echo_by_claim_responder(payload):
    """Deterministic per-claim response derived from the request content
    itself (never from call order/timing) -- selects A101 if the request's
    own claim text contains 'select-me', else none. Used to prove
    concurrent workers never cross-contaminate results."""
    if "select-me" in payload.get("claim", ""):
        return {"decision": "select", "selected_alpha_id": "A101"}
    return {"decision": "none", "selected_alpha_id": None}


# ---------------------------------------------------------------------------
# CASE 1: N eligible claims, single-claim semantics, workload-aware budget
# covers them all.
# ---------------------------------------------------------------------------


def test_case1_800_claims_all_processed_within_workload_aware_budget():
    records = [_record(f"c{i}") for i in range(800)]
    gateway = _BudgetedFakeGateway(_single_claim_none_responder, max_calls=DEFAULT_MAX_CALLS, max_retries=0)

    results = map_structured_records(records, TAXONOMY, llm_gateway=gateway, concurrency=4)

    assert len(results) == 800
    assert all(r["match_status"] == "no_match" for r in results)
    assert len(gateway.calls) == 800


# ---------------------------------------------------------------------------
# CASE 2: call budget remains bounded (single-claim formula).
# ---------------------------------------------------------------------------


def test_case2_call_budget_formula_stays_bounded():
    breakdown = compute_workload_aware_max_calls()
    assert breakdown["total_call_budget"] == DEFAULT_MAX_CALLS
    assert breakdown["eligible_claim_count"] == MAX_EXPECTED_CLAIMS_PER_TICKER
    assert DEFAULT_MAX_CALLS <= MAX_SERVER_CALLS
    assert isinstance(DEFAULT_MAX_CALLS, int)

    manual_base = (
        MAX_EXPECTED_CLAIMS_PER_TICKER
        + -(-MAX_EXPECTED_CLAIMS_PER_TICKER // ENRICHMENT_BATCH_SIZE)
        + OTHER_TASK_CALL_ALLOWANCE
    )
    manual_total = manual_base + manual_base * DEFAULT_MAX_RETRIES + CALL_BUDGET_SAFETY_MARGIN
    assert breakdown["base_call_budget"] == manual_base
    assert breakdown["total_call_budget"] == manual_total

    # Grows with real eligible_claim_count, still always a specific bounded integer.
    real = compute_workload_aware_max_calls(eligible_claim_count=874)
    assert real["eligible_claim_count"] == 874
    assert real["total_call_budget"] < DEFAULT_MAX_CALLS  # 874 < MAX_EXPECTED_CLAIMS_PER_TICKER


# ---------------------------------------------------------------------------
# CASE 3: one timeout + retry -> remaining claims still process if retry
# budget allows.
# ---------------------------------------------------------------------------


def test_case3_timeout_then_retry_succeeds_and_remaining_claims_still_process():
    calls_seen = {"n": 0}

    def flaky_responder(_payload):
        calls_seen["n"] += 1
        if calls_seen["n"] == 1:
            return _TIMEOUT  # first attempt on the first claim only
        return {"decision": "none", "selected_alpha_id": None}

    records = [_record(f"c{i}") for i in range(5)]
    gateway = _BudgetedFakeGateway(flaky_responder, max_calls=20, max_retries=1)
    results = map_structured_records(records, TAXONOMY, llm_gateway=gateway, concurrency=1)

    assert len(results) == 5
    assert all(r["match_status"] == "no_match" for r in results)


# ---------------------------------------------------------------------------
# CASE 4: budget exhausted -> remaining rows become UNAVAILABLE, never NONE.
# ---------------------------------------------------------------------------


def test_case4_budget_exhausted_leaves_remaining_claims_unavailable_never_none():
    records = [_record(f"c{i}") for i in range(10)]
    gateway = _BudgetedFakeGateway(_single_claim_none_responder, max_calls=4, max_retries=0)
    results = map_structured_records(records, TAXONOMY, llm_gateway=gateway, concurrency=1)

    matched_or_none = [r for r in results if r["match_status"] == "no_match"]
    unavailable = [r for r in results if r["match_status"] == "unavailable"]
    assert len(matched_or_none) == 4
    assert len(unavailable) == 6
    assert all(r["alpha_match_fallback_reason"] == "call_budget_exhausted" for r in unavailable)
    assert not any(r["match_status"] == "no_match" and r in unavailable for r in results)


# ---------------------------------------------------------------------------
# CASE 5: batching (DEFERRED for v0.1.2.1) row-level salvage still works at
# the unit level -- the code is kept, offline-tested, not deleted.
# ---------------------------------------------------------------------------


def test_case5_deferred_batching_path_still_has_row_level_salvage():
    records = [_record(f"c{i}") for i in range(5)]

    def batch_responder(payload):
        decisions = [{"claim_id": c["claim_id"], "decision": "none", "selected_alpha_id": None} for c in payload["claims"]]
        decisions[2]["decision"] = "maybe"  # corrupt exactly one row
        return {"decisions": decisions}

    gateway = _BudgetedFakeGateway(batch_responder, max_calls=5, max_retries=0)
    outcomes = _classify_alpha_batch_with_llm([(r["claim_id"], r) for r in records], TAXONOMY, gateway)
    assert len(outcomes) == 5
    for i, r in enumerate(records):
        if i == 2:
            assert outcomes[r["claim_id"]]["outcome"] == "unavailable"
        else:
            assert outcomes[r["claim_id"]]["outcome"] == "none"


# ---------------------------------------------------------------------------
# CASE 6: semantic-health FAIL prevents QA baseline promotion.
# ---------------------------------------------------------------------------


def test_case6_semantic_health_fail_prevents_qa_baseline_promotion():
    fail_health = {"semantic_execution_health_status": seh.HEALTH_FAIL}
    pass_health = {"semantic_execution_health_status": seh.HEALTH_PASS}
    degraded_health = {"semantic_execution_health_status": seh.HEALTH_DEGRADED}
    assert seh.is_valid_for_qa_baseline_promotion(fail_health) is False
    assert seh.is_valid_for_qa_baseline_promotion(pass_health) is True
    assert seh.is_valid_for_qa_baseline_promotion(degraded_health) is False


# ---------------------------------------------------------------------------
# CASE 7: 9/9 artifact completeness does NOT imply semantic health PASS.
# ---------------------------------------------------------------------------


def test_case7_technical_completeness_does_not_imply_semantic_health():
    fail_health = {
        "semantic_execution_health_status": seh.HEALTH_FAIL,
        "semantic_execution_health_status_reason": "EXCESSIVE_ALPHA_MAPPER_UNAVAILABLE",
    }
    status = seh.technical_vs_semantic_status(artifact_completeness_status="9/9", health=fail_health)
    assert status["technical_completeness"] == "PASS"
    assert status["semantic_execution_health"] == "FAIL"
    assert status["qa_baseline_eligible"] is False


# ---------------------------------------------------------------------------
# CASE 8: classifier disabled -> configuration failure remains
# distinguishable from runtime Provider failure.
# ---------------------------------------------------------------------------


def test_case8_disabled_classifier_distinct_from_runtime_provider_failure():
    disabled_result = map_claim_to_alpha(_record("c1"), TAXONOMY, classifier_enabled=False)
    assert disabled_result["alpha_match_fallback_reason"] == "disabled"

    def timeout_responder(_payload):
        return _TIMEOUT

    gateway = _BudgetedFakeGateway(timeout_responder, max_calls=10, max_retries=0)
    timeout_result = map_claim_to_alpha(_record("c2"), TAXONOMY, classifier_enabled=True, llm_gateway=gateway)
    assert timeout_result["alpha_match_fallback_reason"] == "provider_timeout"
    assert timeout_result["alpha_match_fallback_reason"] != disabled_result["alpha_match_fallback_reason"]


# ---------------------------------------------------------------------------
# CASE 9 (Section 5 concurrency safety): every eligible claim gets exactly
# one outcome under concurrency, no duplicates, no drops, no cross-claim
# leakage -- each claim's result must be derived from ITS OWN request
# content, never another claim's, regardless of concurrent completion order.
# ---------------------------------------------------------------------------


def test_case9_concurrency_no_duplicates_no_drops_no_cross_claim_leakage():
    records = []
    for i in range(30):
        text_marker = "select-me" if i % 3 == 0 else "background noise only"
        r = _record(f"c{i}")
        r["claim"] = text_marker
        r["evidence"] = text_marker
        records.append(r)

    gateway = _BudgetedFakeGateway(_echo_by_claim_responder, max_calls=200, max_retries=0, latency_seconds=0.01)
    results = map_structured_records(records, TAXONOMY, llm_gateway=gateway, concurrency=8)

    assert len(results) == 30
    claim_ids = [r["claim_id"] for r in results]
    assert len(claim_ids) == len(set(claim_ids)) == 30  # no duplicates, no drops, identity by claim_id not order
    for i, r in enumerate(results):
        if i % 3 == 0:
            assert r["matched_alpha"] == "A101", f"claim {i} should have matched A101 from its OWN request content"
        else:
            assert r["matched_alpha"] is None


def test_case9b_concurrent_workers_cannot_overshoot_shared_call_budget():
    records = [_record(f"c{i}") for i in range(50)]
    gateway = _BudgetedFakeGateway(_single_claim_none_responder, max_calls=20, max_retries=0, latency_seconds=0.005)
    results = map_structured_records(records, TAXONOMY, llm_gateway=gateway, concurrency=8)

    assert gateway.call_count == 20  # never overshoots, even with 8 concurrent workers racing _reserve_call
    unavailable = [r for r in results if r["match_status"] == "unavailable"]
    assert len(unavailable) == 30
    assert all(r["alpha_match_fallback_reason"] == "call_budget_exhausted" for r in unavailable)


def test_case9c_concurrency_1_matches_serial_helper_directly():
    records = [_record(f"c{i}") for i in range(6)]
    gateway = _BudgetedFakeGateway(_single_claim_none_responder, max_calls=20, max_retries=0)
    pairs = [(r["claim_id"], r) for r in records]
    serial = _classify_alpha_concurrent_with_llm(pairs, TAXONOMY, None, True, 5.0, gateway, concurrency=1)
    assert len(serial) == 6
    assert all(v["outcome"] == "none" for v in serial.values())


# ---------------------------------------------------------------------------
# CASE 10: no regression expectation enters the single-claim classification
# request.
# ---------------------------------------------------------------------------


def test_case10_no_regression_expectation_in_classification_request():
    records = [_record(f"c{i}") for i in range(3)]
    captured = []

    def capturing_responder(payload):
        captured.append(payload)
        return {"decision": "none", "selected_alpha_id": None}

    gateway = _BudgetedFakeGateway(capturing_responder, max_calls=10, max_retries=0)
    map_structured_records(records, TAXONOMY, llm_gateway=gateway, concurrency=1)

    assert len(captured) == 3
    import json

    for payload in captured:
        assert set(payload) == {"claim", "evidence", "ticker", "factors", "direction", "alpha_taxonomy"}
        serialized = json.dumps(payload).lower()
        for forbidden in ("expected_alpha", "regression_label", "gold", "provisional_regression", "john"):
            assert forbidden not in serialized
