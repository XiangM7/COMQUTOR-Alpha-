"""T4 request-level statistics offline prep: verify comqutor_alpha.llm.usage_stats
correctly counts success/retry/failure/missing-usage using FIXED Provider
responses routed through the REAL Week2LLMGateway/SemanticRuntimeSession call
wrapper -- the same production classes every real run uses -- rather than a
separate test-only statistics system. Every response object below is a fixed
fixture (zero network, zero paid calls); only comqutor_alpha.llm.usage_stats
itself and comqutor_alpha.llm.cost_basis are new code from this round.
"""

from __future__ import annotations

from pathlib import Path

from comqutor_alpha.llm.usage_stats import compute_usage_stats
from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway
from tests.llm_runtime.fakes import InMemoryFakeCache


class _Response:
    def __init__(self, content, usage_metadata=None):
        self.content = content
        if usage_metadata is not None:
            self.usage_metadata = usage_metadata


class _SequenceModel:
    """Returns fixed, pre-scripted responses -- never a live Provider call."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def invoke(self, _prompt):
        item = self.responses[self.calls]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        if isinstance(item, str):
            return _Response(item)
        return item


def _runtime_gateway(tmp_path: Path, model, *, max_retries=0, max_calls=16):
    run_dir = tmp_path / "run-usage-stats"
    run_dir.mkdir(parents=True, exist_ok=True)
    session = SemanticRuntimeSession(
        run_id="run-usage-stats",
        output_directory=run_dir,
        execution_mode="test",
        provider="fake-provider",
        model="fake-model",
        cache=InMemoryFakeCache(),
    )
    gateway = Week2LLMGateway(
        model,
        run_id="run-usage-stats",
        output_root=tmp_path,
        timeout_seconds=0.05,
        max_retries=max_retries,
        max_calls=max_calls,
        provider="fake-provider",
        model_name="fake-model",
        semantic_runtime=session,
    )
    return gateway, session


def _run_one(gateway, *, payload=None):
    """Exercises the real call wrapper end to end for one logical task call."""
    invocation = gateway.invoke_json_with_trace(
        "alpha_classifier", payload or {}, lambda value: value
    )
    gateway.finalize_semantic_invocation(invocation, accepted=invocation.validation_accepted)
    return invocation


def test_usage_stats_counts_success_retry_failure_and_missing_usage_via_real_gateway(
    tmp_path: Path,
) -> None:
    gateway, session = _runtime_gateway(tmp_path, _SequenceModel([]), max_retries=1)

    # 1) Clean success, Provider returns real usage.
    gateway._model = _SequenceModel(
        [_Response('{"decision": "none", "selected_alpha_id": null}', usage_metadata={"input_tokens": 120, "output_tokens": 30, "total_tokens": 150})]
    )
    _run_one(gateway, payload={"case": "success_with_usage"})

    # 2) Success, but the Provider response never carries usage metadata --
    # must be counted as missing, never fabricated as zero.
    gateway._model = _SequenceModel(['{"decision": "none", "selected_alpha_id": null}'])
    _run_one(gateway, payload={"case": "success_missing_usage"})

    # 3) One retry (invalid JSON on attempt 1) then success with usage.
    gateway._model = _SequenceModel(
        [
            "not json",
            _Response('{"decision": "none", "selected_alpha_id": null}', usage_metadata={"input_tokens": 80, "output_tokens": 20, "total_tokens": 100}),
        ]
    )
    _run_one(gateway, payload={"case": "retry_then_success"})

    # 4) Real Provider failure, retries exhausted.
    gateway._model = _SequenceModel([RuntimeError("boom"), RuntimeError("boom again")])
    _run_one(gateway, payload={"case": "provider_failure"})

    records = session.recorder.read_all()
    assert len(records) == 4

    stats = compute_usage_stats(records)

    assert stats.logical_call_count == 4
    # request counts: case1=1, case2=1, case3=2 (1 retry), case4=2 (1 retry) => 6
    assert stats.actual_request_count == 6
    # retries: case3 has 1, case4 has 1 => 2
    assert stats.retry_count_total == 2
    assert stats.calls_with_usage == 2
    assert stats.calls_missing_usage == 2
    assert stats.missing_usage_ratio == 0.5
    assert stats.total_input_tokens == 120 + 80
    assert stats.total_output_tokens == 30 + 20
    assert stats.total_tokens_known == 150 + 100
    assert stats.provider_status_counts.get("success") == 3
    assert stats.provider_status_counts.get("provider_error") == 1
    # no confirmed pricing table entry exists for "fake-provider"/"fake-model"
    # (or for any provider/model, per comqutor_alpha.llm.cost_basis) --
    # cost must stay None, never a guess.
    assert stats.total_cost_usd is None
    assert stats.cost_basis_notes == {"no_pricing_table_entry_for_provider_model": 4}


def test_usage_stats_reports_cache_hit_and_zero_requests_for_cached_call(tmp_path: Path) -> None:
    gateway, session = _runtime_gateway(
        tmp_path,
        _SequenceModel(['{"decision": "select", "selected_alpha_id": "A101"}']),
    )
    payload = {"allowed_alpha_ids": ["A101"], "claim": "shared payload"}

    _run_one(gateway, payload=payload)  # populates the cache
    _run_one(gateway, payload=payload)  # identical payload -> cache hit, zero Provider calls

    records = session.recorder.read_all()
    assert len(records) == 2
    stats = compute_usage_stats(records)

    assert stats.logical_call_count == 2
    assert stats.cache_hit_count == 1
    # the cache hit never reached the Provider (provider_status == "not_called"),
    # so it contributes zero to actual_request_count -- only the first, real
    # call does.
    assert stats.actual_request_count == 1
    assert stats.provider_status_counts.get("not_called") == 1


def test_empty_input_never_divides_by_zero() -> None:
    stats = compute_usage_stats([])
    assert stats.logical_call_count == 0
    assert stats.missing_usage_ratio is None
    assert stats.total_cost_usd is None
