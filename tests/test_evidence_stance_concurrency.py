"""John Requirement B, Phase B2 Slice 2A -- bounded concurrency for
evidence_stance_classifier.

Every test here runs with a fake/delayed gateway double; no network, no
Provider, no LLM call anywhere in this file. These tests are additive to
(never a replacement for) tests/test_evidence_stance_llm.py's existing 90
offline behavioral tests, which continue to pass unmodified against the
serial (concurrency=1) default of every existing caller in that file.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from comqutor_alpha.llm_runtime.cache import InMemoryLLMResponseCache, NullLLMResponseCache
from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
from comqutor_alpha.structure_engine import evidence_stance_llm as esl
from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway
from tests.test_evidence_stance_llm import TAXONOMY, _candidate_for, _match


class _FakeInvocation:
    def __init__(self, *, validation_accepted, validated_output=None, provider_status="success", error_code=None, provider_attempt_count=1):
        self.validation_accepted = validation_accepted
        self.validated_output = validated_output
        self.provider_status = provider_status
        self.error_code = error_code
        self.provider_attempt_count = provider_attempt_count


class DelayedFakeStanceGateway:
    """Thread-safe fake gateway that sleeps ``delay_seconds`` per call before
    returning a scripted response, and tracks simultaneous in-flight calls.
    ``responses`` is one entry per expected call, in ARRIVAL order (the
    order calls actually reach this fake, which under concurrency need not
    match submission order) -- most tests here use a uniform response
    (matching every request) rather than a fixed sequence, to avoid
    depending on scheduling order at all.
    """

    def __init__(self, *, delay_seconds: float = 0.05, response_fn=None):
        self._delay_seconds = delay_seconds
        self._response_fn = response_fn or (lambda payload: {"items": [
            {"claim_id": item["claim_id"], "target_alpha_id": item["target_alpha_id"], "stance": "supports_alpha"}
            for item in payload["items"]
        ]})
        self._lock = threading.Lock()
        self.calls: list[dict] = []
        self.finalized: list[tuple[bool, str | None]] = []
        self._in_flight = 0
        self.max_in_flight = 0

    def invoke_json_with_trace(self, task, payload, validator):
        with self._lock:
            self.calls.append(dict(payload))
            self._in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self._in_flight)
        try:
            time.sleep(self._delay_seconds)
            raw = self._response_fn(payload)
            if raw == "TIMEOUT":
                return _FakeInvocation(validation_accepted=False, provider_status="timeout", error_code="WEEK2_LLM_TIMEOUT")
            items = validator(raw)
            return _FakeInvocation(validation_accepted=True, validated_output=items, provider_status="success")
        finally:
            with self._lock:
                self._in_flight -= 1

    def finalize_semantic_invocation(self, invocation, *, accepted, fallback_reason=None):
        with self._lock:
            self.finalized.append((accepted, fallback_reason))


def _matches(n: int, alpha_id: str = "A101"):
    return [_match(f"claim-{i}", alpha_id) for i in range(n)]


# ---------------------------------------------------------------------------
# 1/2. Synthetic wall-clock test + max-in-flight test
# ---------------------------------------------------------------------------


def test_stance_calls_overlap_concurrently_and_bounded_concurrency_is_respected():
    matches = _matches(40)  # 4 batches of 10 -> BATCH_SIZE
    gateway = DelayedFakeStanceGateway(delay_seconds=0.1)

    start = time.monotonic()
    stats = esl.apply_llm_stance_upgrade(matches, TAXONOMY, llm_gateway=gateway, concurrency=4)
    elapsed = time.monotonic() - start

    assert stats.batch_count == 4
    assert len(gateway.calls) == 4
    # Serial would take ~0.4s (4 x 0.1s); with concurrency=4 all four
    # batches run at once, so wall clock should be close to one batch's
    # delay, not four. Generous ratio (not millisecond-exact) to avoid
    # flakiness.
    assert elapsed < 0.3, f"expected overlap (<0.3s), took {elapsed:.3f}s"
    # Proves BOTH real concurrency (>1) and boundedness (<=configured limit).
    assert gateway.max_in_flight > 1
    assert gateway.max_in_flight <= 4


def test_max_in_flight_never_exceeds_configured_limit():
    matches = _matches(80)  # 8 batches
    gateway = DelayedFakeStanceGateway(delay_seconds=0.05)

    esl.apply_llm_stance_upgrade(matches, TAXONOMY, llm_gateway=gateway, concurrency=3)

    assert gateway.max_in_flight <= 3
    assert gateway.max_in_flight > 1


# ---------------------------------------------------------------------------
# 3/5. Deterministic output order, even with a slow outlier batch
# ---------------------------------------------------------------------------


def test_one_slow_batch_does_not_reorder_or_corrupt_other_results():
    matches = _matches(30)  # 3 batches

    def variable_delay(payload):
        # The FIRST claim_id in the batch determines the delay -- batch 0
        # (claim-0..9) is slow, batches 1/2 are fast, so batch 0 finishes
        # LAST despite being submitted FIRST.
        first_claim = payload["items"][0]["claim_id"]
        delay = 0.2 if first_claim == "claim-0" else 0.02
        time.sleep(delay)
        return {"items": [
            {"claim_id": item["claim_id"], "target_alpha_id": item["target_alpha_id"], "stance": "supports_alpha"}
            for item in payload["items"]
        ]}

    gateway = DelayedFakeStanceGateway(delay_seconds=0.0, response_fn=variable_delay)
    esl.apply_llm_stance_upgrade(matches, TAXONOMY, llm_gateway=gateway, concurrency=3)

    # Regardless of which batch finished last, every match's own candidate
    # (referenced by position in the original `matches` list, not by
    # completion order) has the correct LLM result -- results are written
    # onto pre-existing objects by reference, never appended to a
    # completion-order-dependent list.
    for i, match in enumerate(matches):
        candidate = _candidate_for(match, "A101")
        assert candidate["evidence_stance"] == "supports_alpha", f"claim-{i} incorrect"
        assert candidate["stance_method"] == esl.STANCE_METHOD_LLM
    assert [m["claim_id"] for m in matches] == [f"claim-{i}" for i in range(30)]


# ---------------------------------------------------------------------------
# 4/11. Semantic equivalence between concurrency=1 and concurrency=4
# ---------------------------------------------------------------------------


def test_concurrency_1_and_concurrency_4_produce_identical_semantic_results():
    matches_serial = _matches(25)
    matches_concurrent = _matches(25)

    gateway_serial = DelayedFakeStanceGateway(delay_seconds=0.01)
    gateway_concurrent = DelayedFakeStanceGateway(delay_seconds=0.01)

    stats_serial = esl.apply_llm_stance_upgrade(matches_serial, TAXONOMY, llm_gateway=gateway_serial, concurrency=1)
    stats_concurrent = esl.apply_llm_stance_upgrade(matches_concurrent, TAXONOMY, llm_gateway=gateway_concurrent, concurrency=4)

    def stance_view(matches):
        return [
            {
                "claim_id": m["claim_id"],
                "stance": _candidate_for(m, "A101")["evidence_stance"],
                "method": _candidate_for(m, "A101")["stance_method"],
            }
            for m in matches
        ]

    assert stance_view(matches_serial) == stance_view(matches_concurrent)
    assert stats_serial.to_dict()["llm_result_count"] == stats_concurrent.to_dict()["llm_result_count"]
    assert stats_serial.to_dict()["deterministic_fallback_count"] == stats_concurrent.to_dict()["deterministic_fallback_count"]
    assert stats_serial.batch_count == stats_concurrent.batch_count == 3


def test_configured_concurrency_1_reproduces_exact_serial_behavior():
    matches = _matches(15)
    gateway = DelayedFakeStanceGateway(delay_seconds=0.0)
    esl.apply_llm_stance_upgrade(matches, TAXONOMY, llm_gateway=gateway, concurrency=1)
    assert gateway.max_in_flight == 1


# ---------------------------------------------------------------------------
# 6. Error isolation: one failed batch does not affect others
# ---------------------------------------------------------------------------


def test_one_timed_out_batch_preserves_fallback_semantics_for_itself_only():
    matches = _matches(30)  # batch 0 = claim-0..9, batch 1 = claim-10..19, batch 2 = claim-20..29

    def selective_timeout(payload):
        if payload["items"][0]["claim_id"] == "claim-10":
            return "TIMEOUT"
        return {"items": [
            {"claim_id": item["claim_id"], "target_alpha_id": item["target_alpha_id"], "stance": "supports_alpha"}
            for item in payload["items"]
        ]}

    gateway = DelayedFakeStanceGateway(delay_seconds=0.0, response_fn=selective_timeout)
    stats = esl.apply_llm_stance_upgrade(matches, TAXONOMY, llm_gateway=gateway, concurrency=3)

    for i, match in enumerate(matches):
        candidate = _candidate_for(match, "A101")
        if 10 <= i <= 19:
            assert candidate["stance_method"] == esl.STANCE_METHOD_DETERMINISTIC_FALLBACK
            assert candidate["stance_fallback_reason"] == esl.FALLBACK_TIMEOUT
        else:
            assert candidate["stance_method"] == esl.STANCE_METHOD_LLM
    assert stats.deterministic_fallback_count == 10
    assert stats.llm_result_count == 20
    assert stats.batch_count == 3


# ---------------------------------------------------------------------------
# 9/10. Telemetry accuracy under concurrency (real SemanticRuntimeSession)
# ---------------------------------------------------------------------------


def test_telemetry_counts_and_jsonl_manifest_remain_valid_under_concurrency(tmp_path):
    matches = _matches(40)
    run_dir = tmp_path / "run-stance-concurrency"
    run_dir.mkdir()
    session = SemanticRuntimeSession(
        run_id="run-stance-concurrency",
        output_directory=run_dir,
        execution_mode="test",
        provider="fake-provider",
        model="fake-model",
        cache=NullLLMResponseCache(),
    )
    gateway = Week2LLMGateway(
        _RealisticStanceModel(),
        run_id="run-stance-concurrency",
        output_root=tmp_path,
        timeout_seconds=1.0,
        max_retries=0,
        max_calls=32,
        provider="fake-provider",
        model_name="fake-model",
        semantic_runtime=session,
    )

    stats = esl.apply_llm_stance_upgrade(matches, TAXONOMY, llm_gateway=gateway, concurrency=4)

    assert stats.batch_count == 4
    assert stats.requested_count == 40
    assert stats.llm_result_count == 40

    session.finalize_manifest(complete=True)
    records = session.recorder.read_all()
    assert len(records) == 4
    call_sequences = sorted(r["call_sequence"] for r in records)
    assert call_sequences == [0, 1, 2, 3]  # no duplicate/missing sequence numbers
    assert all(r["task"] == "evidence_stance_classifier" for r in records)
    assert all(r["validation_status"] == "accepted" for r in records)
    assert all(r["provider_status"] == "success" for r in records)


class _RealisticStanceModel:
    """A Week2LLMGateway-shaped model double (real gateway, real
    SemanticRuntimeSession, fake only at the outermost model.invoke
    boundary) that answers evidence_stance_classifier batches."""

    def __init__(self, delay_seconds: float = 0.0) -> None:
        self._delay = delay_seconds
        self.calls = 0
        self._lock = threading.Lock()

    def invoke(self, prompt: str):
        import json

        with self._lock:
            self.calls += 1
        if self._delay:
            time.sleep(self._delay)
        payload = json.loads(prompt.split("\nINPUT_JSON:\n", 1)[1])
        items = [
            {"claim_id": item["claim_id"], "target_alpha_id": item["target_alpha_id"], "stance": "supports_alpha"}
            for item in payload["items"]
        ]

        class _Resp:
            def __init__(self, content):
                self.content = content

        return _Resp(json.dumps({"items": items}))


# ---------------------------------------------------------------------------
# 8/19. Cache correctness under concurrency (Slice 1's real cache backend)
# ---------------------------------------------------------------------------


def test_cache_correct_under_concurrent_stance_batches(tmp_path):
    """Distinct batches never collide in the shared cache (different
    input_sha256 per batch); no race-induced exception; Provider-call
    accounting stays correct."""
    matches = _matches(40)
    run_dir = tmp_path / "run-stance-cache"
    run_dir.mkdir()
    cache = InMemoryLLMResponseCache()
    session = SemanticRuntimeSession(
        run_id="run-stance-cache",
        output_directory=run_dir,
        execution_mode="test",
        provider="fake-provider",
        model="fake-model",
        cache=cache,
    )
    model = _RealisticStanceModel(delay_seconds=0.02)
    gateway = Week2LLMGateway(
        model,
        run_id="run-stance-cache",
        output_root=tmp_path,
        timeout_seconds=1.0,
        max_retries=0,
        max_calls=32,
        provider="fake-provider",
        model_name="fake-model",
        semantic_runtime=session,
    )

    esl.apply_llm_stance_upgrade(matches, TAXONOMY, llm_gateway=gateway, concurrency=4)
    assert model.calls == 4  # 4 distinct batches -> 4 distinct cache keys -> 4 real calls, no exception

    # Re-running the identical 40-claim set through a SECOND, independent
    # cache-sharing gateway (same cache instance) must hit cache for every
    # batch -- proving the cache survived concurrent writes uncorrupted.
    matches_2 = _matches(40)
    run_dir_2 = tmp_path / "run-stance-cache-2"
    run_dir_2.mkdir()
    model_2 = _RealisticStanceModel(delay_seconds=0.02)
    gateway_2 = Week2LLMGateway(
        model_2,
        run_id="run-stance-cache-2",
        output_root=tmp_path,
        timeout_seconds=1.0,
        max_retries=0,
        max_calls=32,
        provider="fake-provider",
        model_name="fake-model",
        semantic_runtime=SemanticRuntimeSession(
            run_id="run-stance-cache-2",
            output_directory=run_dir_2,
            execution_mode="test",
            provider="fake-provider",
            model="fake-model",
            cache=cache,
        ),
    )
    esl.apply_llm_stance_upgrade(matches_2, TAXONOMY, llm_gateway=gateway_2, concurrency=4)
    assert model_2.calls == 0  # every batch served from cache, no corruption, no exception

    def stance_view(matches):
        return [_candidate_for(m, "A101")["evidence_stance"] for m in matches]

    assert stance_view(matches) == stance_view(matches_2)


# ---------------------------------------------------------------------------
# 12/13. Edge cases
# ---------------------------------------------------------------------------


def test_empty_input_works_under_concurrency_config():
    gateway = DelayedFakeStanceGateway(delay_seconds=0.01)
    stats = esl.apply_llm_stance_upgrade([], TAXONOMY, llm_gateway=gateway, concurrency=4)
    assert stats.requested_count == 0
    assert stats.batch_count == 0
    assert len(gateway.calls) == 0


def test_single_item_input_uses_serial_path_even_with_concurrency_configured():
    matches = _matches(1)
    gateway = DelayedFakeStanceGateway(delay_seconds=0.01)
    stats = esl.apply_llm_stance_upgrade(matches, TAXONOMY, llm_gateway=gateway, concurrency=4)
    assert stats.batch_count == 1
    assert gateway.max_in_flight == 1
    assert _candidate_for(matches[0], "A101")["evidence_stance"] == "supports_alpha"


# ---------------------------------------------------------------------------
# Default concurrency resolution (env var, mirroring alpha_classifier)
# ---------------------------------------------------------------------------


def test_default_concurrency_resolves_from_env_var(monkeypatch: pytest.MonkeyPatch):
    from comqutor_alpha.structure_engine.week2_llm import resolve_evidence_stance_concurrency

    monkeypatch.delenv("COMQUTOR_WEEK2_STANCE_CONCURRENCY", raising=False)
    assert resolve_evidence_stance_concurrency() == 4  # DEFAULT_EVIDENCE_STANCE_CONCURRENCY

    monkeypatch.setenv("COMQUTOR_WEEK2_STANCE_CONCURRENCY", "2")
    assert resolve_evidence_stance_concurrency() == 2

    monkeypatch.setenv("COMQUTOR_WEEK2_STANCE_CONCURRENCY", "999")
    assert resolve_evidence_stance_concurrency() == 8  # MAX_EVIDENCE_STANCE_CONCURRENCY clamp


def test_apply_llm_stance_upgrade_uses_env_resolved_concurrency_by_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COMQUTOR_WEEK2_STANCE_CONCURRENCY", "1")
    matches = _matches(20)
    gateway = DelayedFakeStanceGateway(delay_seconds=0.01)
    esl.apply_llm_stance_upgrade(matches, TAXONOMY, llm_gateway=gateway)  # concurrency omitted
    assert gateway.max_in_flight == 1  # env var forced serial
