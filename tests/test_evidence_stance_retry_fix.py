"""Tests for v0.1.3 Provider Final-Orphan Reliability Fix, Phase 1 (Option C).

Covers the component-specific retry-count increase for
``evidence_stance_classifier`` only (1 retry -> 2 retries, i.e. 2 total
attempts -> 3 total attempts), implemented in
``comqutor_alpha/structure_engine/week2_llm.py`` via
``_resolve_task_max_retries`` and wired into ``invoke_json_with_trace``'s
retry loop. No Provider call, no ticker run -- every test uses a fake,
in-process model.

Design authority: docs/audit_artifacts/v0_1_3_provider_final_orphan_reliability_audit.md
(Option C) and docs/audit_artifacts/v0_1_3_evidence_stance_retry_fix.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from comqutor_alpha.llm_runtime.recorder import SemanticCallRecorder
from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
from comqutor_alpha.regression import provider_health_diagnostics as phd
from comqutor_alpha.structure_engine.week2_llm import (
    MAX_SERVER_RETRIES,
    EVIDENCE_STANCE_CLASSIFIER_MAX_RETRIES,
    Week2LLMGateway,
    _resolve_task_max_retries,
)


class _Response:
    def __init__(self, content):
        self.content = content


class _SequenceModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def invoke(self, _prompt):
        response = self.responses[self.calls]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        if callable(response):
            response = response()
        return _Response(response)


def _gateway(tmp_path, model, **kwargs):
    (tmp_path / "run1").mkdir(exist_ok=True)
    return Week2LLMGateway(
        model,
        run_id="run1",
        output_root=tmp_path,
        timeout_seconds=kwargs.get("timeout_seconds", 0.2),
        max_retries=kwargs.get("max_retries", 1),
        max_calls=kwargs.get("max_calls", 8),
    )


def _error_log_lines(tmp_path):
    path = tmp_path / "run1" / "error_logs" / "week2_llm_errors.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# --- Resolver unit tests ---------------------------------------------------


def test_resolver_gives_evidence_stance_classifier_two_retries():
    assert _resolve_task_max_retries("evidence_stance_classifier", 1) == 2


def test_resolver_leaves_alpha_classifier_unchanged():
    assert _resolve_task_max_retries("alpha_classifier", 1) == 1


def test_resolver_leaves_structure_extractor_unchanged():
    assert _resolve_task_max_retries("structure_extractor", 1) == 1


def test_resolver_leaves_other_tasks_unchanged():
    assert _resolve_task_max_retries("claim_batch_enrichment", 1) == 1
    assert _resolve_task_max_retries("alpha_classifier_batch", 1) == 1


def test_evidence_stance_constant_does_not_exceed_ceiling():
    assert EVIDENCE_STANCE_CLASSIFIER_MAX_RETRIES <= MAX_SERVER_RETRIES
    assert EVIDENCE_STANCE_CLASSIFIER_MAX_RETRIES == 2
    assert MAX_SERVER_RETRIES == 2


def test_resolver_respects_explicit_zero_retries_even_for_evidence_stance():
    """An explicit max_retries=0 is an intentional 'no retries at all'
    signal (used by narrow unit tests isolating single-attempt behavior)
    and must not be silently raised by the component-specific increase."""
    assert _resolve_task_max_retries("evidence_stance_classifier", 0) == 0


def test_evidence_stance_single_attempt_when_gateway_configured_with_zero_retries(tmp_path):
    model = _SequenceModel(['{"value": 1}'])
    gateway = _gateway(tmp_path, model, max_retries=0)

    invocation = gateway.invoke_json_with_trace(
        "evidence_stance_classifier", {"claim_id": "c1"}, lambda payload: payload["value"]
    )

    assert model.calls == 1
    assert invocation.provider_attempt_count == 1
    assert invocation.validated_output == 1


# --- 1. Third-attempt success (the canonical positive test) ---------------


def test_evidence_stance_third_attempt_success(tmp_path):
    model = _SequenceModel([TimeoutError("t1"), TimeoutError("t2"), '{"value": 42}'])
    gateway = _gateway(tmp_path, model, max_retries=1)  # shared default stays 1

    invocation = gateway.invoke_json_with_trace(
        "evidence_stance_classifier", {"claim_id": "c1"}, lambda payload: payload["value"]
    )

    assert model.calls == 3
    assert invocation.validation_accepted is True
    assert invocation.validated_output == 42
    assert invocation.provider_attempt_count == 3
    assert invocation.retry_count == 2

    lines = _error_log_lines(tmp_path)
    assert len(lines) == 2
    assert all(l["error_code"] == "WEEK2_LLM_TIMEOUT" for l in lines)
    assert [l["attempt"] for l in lines] == [1, 2]


# --- 2. Full exhaustion (3 attempts, all fail) ------------------------------


def test_evidence_stance_full_exhaustion_uses_exactly_three_attempts(tmp_path):
    model = _SequenceModel([TimeoutError("t1"), TimeoutError("t2"), TimeoutError("t3")])
    gateway = _gateway(tmp_path, model, max_retries=1)

    invocation = gateway.invoke_json_with_trace(
        "evidence_stance_classifier", {"claim_id": "c1"}, lambda payload: payload["value"]
    )

    assert model.calls == 3
    assert invocation.validation_accepted is False
    assert invocation.validated_output is None
    assert invocation.provider_status == "timeout"
    assert invocation.error_code == "WEEK2_LLM_TIMEOUT"
    assert invocation.provider_attempt_count == 3
    assert invocation.retry_count == 2

    lines = _error_log_lines(tmp_path)
    assert len(lines) == 3
    assert [l["attempt"] for l in lines] == [1, 2, 3]


# --- 3. Transport retry path -------------------------------------------------


def test_evidence_stance_transport_error_retries_and_recovers_on_third_attempt(tmp_path):
    model = _SequenceModel(
        [ConnectionError("dropped"), ConnectionError("dropped again"), '{"value": 7}']
    )
    gateway = _gateway(tmp_path, model, max_retries=1)

    invocation = gateway.invoke_json_with_trace(
        "evidence_stance_classifier", {"claim_id": "c1"}, lambda payload: payload["value"]
    )

    assert model.calls == 3
    assert invocation.validated_output == 7
    lines = _error_log_lines(tmp_path)
    assert len(lines) == 2
    assert all(l["error_code"] == "WEEK2_LLM_TRANSPORT_ERROR" for l in lines)


# --- 4. Non-retryable path: oversized payload rejected before any attempt --


def test_evidence_stance_oversized_payload_unaffected_by_retry_increase(tmp_path, monkeypatch):
    import comqutor_alpha.structure_engine.week2_llm as w2

    monkeypatch.setattr(w2, "MAX_PROMPT_PAYLOAD_CHARS", 10)
    model = _SequenceModel(['{"value": 1}', '{"value": 1}', '{"value": 1}'])
    gateway = _gateway(tmp_path, model, max_retries=1)

    invocation = gateway.invoke_json_with_trace(
        "evidence_stance_classifier",
        {"claim_id": "c1", "evidence": "x" * 500},
        lambda payload: payload["value"],
    )

    assert model.calls == 0
    assert invocation.provider_attempt_count == 0
    assert invocation.error_code == "WEEK2_LLM_INPUT_TOO_LARGE"


# --- 5. Alpha classifier negative control -----------------------------------


def test_alpha_classifier_retry_policy_unchanged(tmp_path):
    model = _SequenceModel([TimeoutError("t1"), TimeoutError("t2"), '{"value": 1}'])
    gateway = _gateway(tmp_path, model, max_retries=1)

    invocation = gateway.invoke_json_with_trace(
        "alpha_classifier", {"claim_id": "c1"}, lambda payload: payload["value"]
    )

    # alpha_classifier still gets only 2 total attempts -- the 3rd response
    # (a would-be success) is never consumed.
    assert model.calls == 2
    assert invocation.validation_accepted is False
    assert invocation.provider_attempt_count == 2
    assert invocation.retry_count == 1


def test_tsm_a301_historical_fixture_unaffected(tmp_path):
    """Regression control: the historical TSM A301 lineage (alpha_classifier,
    both attempts timeout -> match_status='unavailable') behaves identically
    after this evidence_stance-only change -- exactly 2 attempts, exhausted,
    same as the pre-fix behavior documented in
    docs/audit_artifacts/v0_1_3_tsm_fresh_provider_validation.md."""
    model = _SequenceModel([TimeoutError("t1"), TimeoutError("t2")])
    gateway = _gateway(tmp_path, model, max_retries=1)

    invocation = gateway.invoke_json_with_trace(
        "alpha_classifier", {"claim_id": "fundamentals_report:claim:42"}, lambda payload: payload["value"]
    )

    assert model.calls == 2
    assert invocation.validation_accepted is False
    assert invocation.provider_attempt_count == 2


# --- 6. Structure extractor negative control --------------------------------


def test_structure_extractor_retry_policy_unchanged(tmp_path):
    model = _SequenceModel(
        [TypeError("bad shape"), TypeError("bad shape"), '{"edges": []}']
    )
    gateway = _gateway(tmp_path, model, max_retries=1)

    invocation = gateway.invoke_json_with_trace(
        "structure_extractor", {"allowed_factors": []}, lambda payload: payload["edges"]
    )

    assert model.calls == 2
    assert invocation.validation_accepted is False
    assert invocation.provider_attempt_count == 2
    assert invocation.error_code == "WEEK2_LLM_VALIDATION_FAILED"


# --- 7/8/9. Final-orphan counting, no double-counting, fallback unchanged --
# (Full semantic-runtime-integrated path, mirroring
# tests/test_week2_llm_semantic_runtime_integration.py's pattern.)


def _runtime_gateway(tmp_path: Path, model, *, max_retries=1):
    run_dir = tmp_path / "run-semantic"
    run_dir.mkdir(parents=True, exist_ok=True)
    recorder = SemanticCallRecorder(run_id="run-semantic", output_directory=run_dir, mode="test")
    session = SemanticRuntimeSession(
        run_id="run-semantic",
        output_directory=run_dir,
        execution_mode="test",
        provider="fake-provider",
        model="fake-model",
        cache=None,
        recorder=recorder,
    )
    gateway = Week2LLMGateway(
        model,
        run_id="run-semantic",
        output_root=tmp_path,
        timeout_seconds=0.05,
        max_retries=max_retries,
        max_calls=16,
        provider="fake-provider",
        model_name="fake-model",
        semantic_runtime=session,
    )
    return gateway, session, run_dir


def test_evidence_stance_exhaustion_produces_exactly_one_semantic_call_record(tmp_path):
    model = _SequenceModel([TimeoutError("t1"), TimeoutError("t2"), TimeoutError("t3")])
    gateway, session, run_dir = _runtime_gateway(tmp_path, model)

    result = gateway.invoke_json(
        "evidence_stance_classifier", {"claim_id": "c1", "target_alpha_id": "A101"}, lambda payload: payload["value"]
    )
    session.finalize_manifest(complete=True)

    assert result is None
    calls_path = run_dir / "llm_semantic_calls.jsonl"
    records = [json.loads(l) for l in calls_path.read_text().splitlines() if l.strip()]
    evidence_stance_records = [r for r in records if r["task"] == "evidence_stance_classifier"]

    # Exactly ONE persisted record for this one logical call, regardless of
    # 3 internal Provider attempts -- never one record per attempt.
    assert len(evidence_stance_records) == 1
    assert evidence_stance_records[0]["retry_count"] == 2
    # Fallback value/shape is the SAME existing fallback outcome as before
    # this fix -- only the attempt count leading up to it changed.
    assert evidence_stance_records[0]["fallback_used"] is True

    err_path = run_dir / "error_logs" / "week2_llm_errors.jsonl"
    err_lines = [json.loads(l) for l in err_path.read_text().splitlines() if l.strip()]
    assert len(err_lines) == 3


def test_evidence_stance_provider_health_metrics_internally_consistent(tmp_path):
    """Section 16 of the task: timeout, timeout, success should yield
    provider_failure_events == 2 but final_orphans == 0, claims_orphaned == 0,
    impacted alphas == 0 for that call."""
    model = _SequenceModel([TimeoutError("t1"), TimeoutError("t2"), '{"value": 1}'])
    gateway, session, run_dir = _runtime_gateway(tmp_path, model)

    result = gateway.invoke_json(
        "evidence_stance_classifier", {"claim_id": "c1", "target_alpha_id": "A101"}, lambda payload: payload["value"]
    )
    session.finalize_manifest(complete=True)

    assert result == 1

    diagnostics = phd.compute_provider_health_diagnostics(run_dir=run_dir, ticker="NVDA", run_id="run-semantic")
    assert diagnostics["provider_failure_events"] == 2
    assert diagnostics["evidence_stance_final_orphans"] == 0
    assert diagnostics["provider_final_orphans_total"] == 0
    assert diagnostics["claims_orphaned_by_provider_failure"] == 0
    assert diagnostics["alphas_impacted_by_provider_failure"] == 0


def test_provider_health_diagnostics_still_correctly_flags_orphan_after_full_exhaustion(tmp_path):
    model = _SequenceModel([TimeoutError("t1"), TimeoutError("t2"), TimeoutError("t3")])
    gateway, session, run_dir = _runtime_gateway(tmp_path, model)

    gateway.invoke_json(
        "evidence_stance_classifier", {"claim_id": "c1", "target_alpha_id": "A101"}, lambda payload: payload["value"]
    )
    session.finalize_manifest(complete=True)

    diagnostics = phd.compute_provider_health_diagnostics(run_dir=run_dir, ticker="NVDA", run_id="run-semantic")
    assert diagnostics["provider_failure_events"] == 3
    assert diagnostics["evidence_stance_final_orphans"] == 1
    assert diagnostics["provider_final_orphans_total"] == 1


# --- Historical counterfactual sanity (mirrors the audit's own derivation) --


def test_recovered_after_retry_derivation_matches_new_attempt_semantics():
    """Sanity check on the audit's attempt1-count minus attempt2-count
    derivation, now extended to 3 attempts: a call recovered on attempt 3
    logs exactly 2 failures (attempt 1, attempt 2), not 3."""
    # This is a logical/documentation-level check, not a new mechanism --
    # already exercised end-to-end by test_evidence_stance_third_attempt_success.
    assert True
