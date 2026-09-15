"""John Requirement B, Phase B2 Slice 2B -- bounded concurrency for
structured_adapter.

Every test here runs with a fake/delayed Provider double; no network, no
Provider, no LLM call anywhere in this file. These tests are additive to
(never a replacement for) tests/test_structured_output_adapter.py's existing
behavioral tests, which continue to pass unmodified against the serial
(concurrency=1) default of every existing caller in that file.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from comqutor_alpha.llm_runtime.cache import InMemoryLLMResponseCache, NullLLMResponseCache
from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
from comqutor_alpha.structure_engine.structured_output_adapter import adapt_run_outputs
from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway


class _Response:
    def __init__(self, content: str) -> None:
        self.content = content


class DelayedFakeAdapterModel:
    """Thread-safe fake Provider model that sleeps ``delay_seconds`` per call
    before returning a scripted response, and tracks simultaneous in-flight
    calls. ``response_fn`` defaults to a uniform "accept every segment"
    enrichment response."""

    def __init__(self, *, delay_seconds: float = 0.05, response_fn=None) -> None:
        self._delay_seconds = delay_seconds
        self._response_fn = response_fn or self._default_response
        self._lock = threading.Lock()
        self.calls: list[dict] = []
        self._in_flight = 0
        self.max_in_flight = 0

    @staticmethod
    def _default_response(payload):
        return {
            "claims": [
                {**segment, "entities": ["X"], "factors": ["F"], "direction": "positive", "confidence": 0.9}
                for segment in payload["segments"]
            ]
        }

    def invoke(self, prompt: str):
        payload = json.loads(prompt.split("\nINPUT_JSON:\n", 1)[1])
        with self._lock:
            self.calls.append(payload)
            self._in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self._in_flight)
        try:
            time.sleep(self._delay_seconds)
            raw = self._response_fn(payload)
            return _Response(json.dumps(raw))
        finally:
            with self._lock:
                self._in_flight -= 1


def _make_run(tmp_path: Path, run_id: str, agents: list[str], sentences_per_agent: int = 5) -> Path:
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    outputs = []
    for i, agent in enumerate(agents):
        text = " ".join(
            f"Sentence {i}-{j} about AI demand and GPU growth for the ticker."
            for j in range(sentences_per_agent)
        )
        outputs.append({"agent": agent, "raw_output": text})
    (run_dir / "raw_agent_outputs.json").write_text(
        json.dumps({"run_id": run_id, "ticker": "NVDA", "agent_outputs": outputs})
    )
    return run_dir


_FOUR_AGENTS = ["market_agent", "sentiment_agent", "news_agent", "fundamental_agent"]


def _build_gateway(tmp_path: Path, run_dir: Path, run_id: str, model, *, cache=None):
    session = SemanticRuntimeSession(
        run_id=run_id,
        output_directory=run_dir,
        execution_mode="test",
        provider="fake-provider",
        model="fake-model",
        cache=cache if cache is not None else NullLLMResponseCache(),
    )
    gateway = Week2LLMGateway(
        model,
        run_id=run_id,
        output_root=tmp_path,
        timeout_seconds=1.0,
        max_retries=0,
        max_calls=32,
        provider="fake-provider",
        model_name="fake-model",
        semantic_runtime=session,
    )
    return gateway, session


# ---------------------------------------------------------------------------
# 1/2. Synthetic wall-clock test + max-in-flight test
# ---------------------------------------------------------------------------


def test_adapter_calls_overlap_concurrently_and_bounded_concurrency_is_respected(tmp_path: Path):
    run_dir = _make_run(tmp_path, "overlap-run", _FOUR_AGENTS)
    model = DelayedFakeAdapterModel(delay_seconds=0.1)
    gateway, _session = _build_gateway(tmp_path, run_dir, "overlap-run", model)

    start = time.monotonic()
    result = adapt_run_outputs(run_dir, llm_gateway=gateway, concurrency=4)
    elapsed = time.monotonic() - start

    assert model.calls.__len__() == 4
    # Serial would take ~0.4s (4 x 0.1s); with concurrency=4 all four agent
    # calls run at once, so wall clock should be close to one call's delay.
    assert elapsed < 0.3, f"expected overlap (<0.3s), took {elapsed:.3f}s"
    assert model.max_in_flight > 1
    assert model.max_in_flight <= 4
    assert len(result["records"]) == 20


def test_max_in_flight_never_exceeds_configured_limit(tmp_path: Path):
    run_dir = _make_run(tmp_path, "bounded-run", _FOUR_AGENTS)
    model = DelayedFakeAdapterModel(delay_seconds=0.05)
    gateway, _session = _build_gateway(tmp_path, run_dir, "bounded-run", model)

    adapt_run_outputs(run_dir, llm_gateway=gateway, concurrency=2)

    assert model.max_in_flight <= 2
    assert model.max_in_flight > 1


# ---------------------------------------------------------------------------
# 3/4/5. Deterministic output order, semantic equivalence, long-tail
# ---------------------------------------------------------------------------


def test_concurrency_1_and_concurrency_4_produce_identical_semantic_output(tmp_path: Path):
    run_dir_serial = _make_run(tmp_path, "serial-run", _FOUR_AGENTS)
    run_dir_concurrent = _make_run(tmp_path, "concurrent-run", _FOUR_AGENTS)

    model_serial = DelayedFakeAdapterModel(delay_seconds=0.01)
    gateway_serial, _ = _build_gateway(tmp_path, run_dir_serial, "serial-run", model_serial)
    result_serial = adapt_run_outputs(run_dir_serial, llm_gateway=gateway_serial, concurrency=1)

    model_concurrent = DelayedFakeAdapterModel(delay_seconds=0.01)
    gateway_concurrent, _ = _build_gateway(tmp_path, run_dir_concurrent, "concurrent-run", model_concurrent)
    result_concurrent = adapt_run_outputs(run_dir_concurrent, llm_gateway=gateway_concurrent, concurrency=4)

    def normalize(records):
        return [{k: v for k, v in r.items() if k not in ("run_id", "timestamp")} for r in records]

    assert normalize(result_serial["records"]) == normalize(result_concurrent["records"])
    assert result_serial["metadata"]["raw_claim_count"] == result_concurrent["metadata"]["raw_claim_count"]
    assert result_serial["metadata"]["llm_batch_count"] == result_concurrent["metadata"]["llm_batch_count"]
    assert result_serial["metadata"]["agent_coverage"] == result_concurrent["metadata"]["agent_coverage"]


def test_configured_concurrency_1_reproduces_exact_serial_behavior(tmp_path: Path):
    run_dir = _make_run(tmp_path, "forced-serial-run", _FOUR_AGENTS)
    model = DelayedFakeAdapterModel(delay_seconds=0.0)
    gateway, _session = _build_gateway(tmp_path, run_dir, "forced-serial-run", model)
    adapt_run_outputs(run_dir, llm_gateway=gateway, concurrency=1)
    assert model.max_in_flight == 1


def test_one_slow_agent_does_not_reorder_or_corrupt_other_agents_records(tmp_path: Path):
    run_dir = _make_run(tmp_path, "long-tail-run", _FOUR_AGENTS)

    def variable_delay(payload):
        # market_agent's segments are slow; everyone else is fast -- market
        # is submitted FIRST but finishes LAST.
        agent_marker = payload["segments"][0]["claim"]
        delay = 0.2 if agent_marker.startswith("Sentence 0-") else 0.02
        time.sleep(delay)
        return DelayedFakeAdapterModel._default_response(payload)

    model = DelayedFakeAdapterModel(delay_seconds=0.0, response_fn=variable_delay)
    gateway, _session = _build_gateway(tmp_path, run_dir, "long-tail-run", model)

    result = adapt_run_outputs(run_dir, llm_gateway=gateway, concurrency=4)

    # Original agent order (market, sentiment, news, fundamental) must be
    # preserved in the final records list regardless of which agent's
    # Provider call actually finished last.
    agents_in_order = [r["agent"] for r in result["records"]]
    assert agents_in_order == (
        ["market_agent"] * 5 + ["sentiment_agent"] * 5 + ["news_agent"] * 5 + ["fundamental_agent"] * 5
    )
    assert all(r["extraction_method"] == "llm_strict_json" for r in result["records"])


# ---------------------------------------------------------------------------
# 6. Error isolation
# ---------------------------------------------------------------------------


def test_one_failed_agent_call_preserves_fallback_semantics_for_itself_only(tmp_path: Path):
    run_dir = _make_run(tmp_path, "error-isolation-run", _FOUR_AGENTS)

    def selective_failure(payload):
        agent_marker = payload["segments"][0]["claim"]
        if agent_marker.startswith("Sentence 1-"):  # sentiment_agent
            raise RuntimeError("synthetic provider failure")
        return DelayedFakeAdapterModel._default_response(payload)

    model = DelayedFakeAdapterModel(delay_seconds=0.0, response_fn=selective_failure)
    gateway, _session = _build_gateway(tmp_path, run_dir, "error-isolation-run", model)

    result = adapt_run_outputs(run_dir, llm_gateway=gateway, concurrency=4)

    by_agent = {}
    for record in result["records"]:
        by_agent.setdefault(record["agent"], []).append(record)

    assert all(r["extraction_method"] == "deterministic_splitter" for r in by_agent["sentiment_agent"])
    assert all(r["extraction_method"] == "llm_strict_json" for r in by_agent["market_agent"])
    assert all(r["extraction_method"] == "llm_strict_json" for r in by_agent["news_agent"])
    assert all(r["extraction_method"] == "llm_strict_json" for r in by_agent["fundamental_agent"])
    assert result["metadata"]["llm_batch_fallback_count"] == 1


# ---------------------------------------------------------------------------
# 9/10/14. Telemetry accuracy and recorder ordering (real SemanticRuntimeSession)
# ---------------------------------------------------------------------------


def test_telemetry_and_recorder_sequencing_remain_valid_under_concurrency(tmp_path: Path):
    run_dir = _make_run(tmp_path, "telemetry-run", _FOUR_AGENTS)
    model = DelayedFakeAdapterModel(delay_seconds=0.02)
    gateway, session = _build_gateway(tmp_path, run_dir, "telemetry-run", model)

    result = adapt_run_outputs(run_dir, llm_gateway=gateway, concurrency=4)

    assert result["metadata"]["llm_batch_count"] == 4
    assert model.calls.__len__() == 4

    session.finalize_manifest(complete=True)
    records = session.recorder.read_all()
    assert len(records) == 4
    call_sequences = sorted(r["call_sequence"] for r in records)
    assert call_sequences == [0, 1, 2, 3]  # no gaps, no duplicates
    assert all(r["task"] == "structured_adapter" for r in records)
    assert all(r["validation_status"] == "accepted" for r in records)
    assert all(r["provider_status"] == "success" for r in records)


# ---------------------------------------------------------------------------
# 12/19. Cache correctness under concurrency (Slice 1's real cache backend)
# ---------------------------------------------------------------------------


def test_cache_correct_under_concurrent_adapter_calls(tmp_path: Path):
    run_dir = _make_run(tmp_path, "cache-run", _FOUR_AGENTS)
    cache = InMemoryLLMResponseCache()
    model = DelayedFakeAdapterModel(delay_seconds=0.02)
    gateway, _session = _build_gateway(tmp_path, run_dir, "cache-run", model, cache=cache)

    result_1 = adapt_run_outputs(run_dir, llm_gateway=gateway, concurrency=4)
    assert model.calls.__len__() == 4  # 4 distinct agents -> 4 distinct cache keys -> 4 real calls, no exception

    # A second, independent gateway sharing the SAME cache instance, given
    # the identical raw agent outputs, must be served entirely from cache.
    run_dir_2 = _make_run(tmp_path, "cache-run-2", _FOUR_AGENTS)
    model_2 = DelayedFakeAdapterModel(delay_seconds=0.02)
    gateway_2, _session_2 = _build_gateway(tmp_path, run_dir_2, "cache-run-2", model_2, cache=cache)
    result_2 = adapt_run_outputs(run_dir_2, llm_gateway=gateway_2, concurrency=4)

    assert model_2.calls.__len__() == 0  # every agent call served from cache, no corruption, no exception

    def normalize(records):
        return [{k: v for k, v in r.items() if k not in ("run_id", "timestamp")} for r in records]

    assert normalize(result_1["records"]) == normalize(result_2["records"])


# ---------------------------------------------------------------------------
# 7/8. Edge cases
# ---------------------------------------------------------------------------


def test_empty_agent_outputs_works_under_concurrency_config(tmp_path: Path):
    run_dir = tmp_path / "empty-run"
    run_dir.mkdir()
    (run_dir / "raw_agent_outputs.json").write_text(
        json.dumps({"run_id": "empty-run", "ticker": "NVDA", "agent_outputs": []})
    )
    model = DelayedFakeAdapterModel(delay_seconds=0.01)
    gateway, _session = _build_gateway(tmp_path, run_dir, "empty-run", model)
    result = adapt_run_outputs(run_dir, llm_gateway=gateway, concurrency=4)
    assert result["records"] == []
    assert model.calls.__len__() == 0


def test_single_agent_output_uses_serial_path_even_with_concurrency_configured(tmp_path: Path):
    run_dir = _make_run(tmp_path, "single-agent-run", ["market_agent"])
    model = DelayedFakeAdapterModel(delay_seconds=0.01)
    gateway, _session = _build_gateway(tmp_path, run_dir, "single-agent-run", model)
    result = adapt_run_outputs(run_dir, llm_gateway=gateway, concurrency=4)
    assert model.max_in_flight == 1
    assert len(result["records"]) == 5


# ---------------------------------------------------------------------------
# Default concurrency resolution (env var, mirroring alpha_classifier/stance)
# ---------------------------------------------------------------------------


def test_default_concurrency_resolves_from_env_var(monkeypatch: pytest.MonkeyPatch):
    from comqutor_alpha.structure_engine.week2_llm import resolve_structured_adapter_concurrency

    monkeypatch.delenv("COMQUTOR_WEEK2_ADAPTER_CONCURRENCY", raising=False)
    assert resolve_structured_adapter_concurrency() == 4  # DEFAULT_STRUCTURED_ADAPTER_CONCURRENCY

    monkeypatch.setenv("COMQUTOR_WEEK2_ADAPTER_CONCURRENCY", "2")
    assert resolve_structured_adapter_concurrency() == 2

    monkeypatch.setenv("COMQUTOR_WEEK2_ADAPTER_CONCURRENCY", "999")
    assert resolve_structured_adapter_concurrency() == 8  # MAX_STRUCTURED_ADAPTER_CONCURRENCY clamp


def test_adapt_run_outputs_uses_env_resolved_concurrency_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COMQUTOR_WEEK2_ADAPTER_CONCURRENCY", "1")
    run_dir = _make_run(tmp_path, "env-default-run", _FOUR_AGENTS)
    model = DelayedFakeAdapterModel(delay_seconds=0.01)
    gateway, _session = _build_gateway(tmp_path, run_dir, "env-default-run", model)
    adapt_run_outputs(run_dir, llm_gateway=gateway)  # concurrency omitted
    assert model.max_in_flight == 1  # env var forced serial


# ---------------------------------------------------------------------------
# QQQ A001 unaffected: alpha_mapper/claim_semantics are not on this code path
# at all -- structured_adapter concurrency touches zero Alpha-mapping logic.
# ---------------------------------------------------------------------------


def test_structured_adapter_concurrency_touches_no_alpha_mapping_code():
    """A direct, structural proof (not just an assertion) that this slice's
    own new code -- and structured_output_adapter.py as a whole -- never
    references alpha_mapper.py's own module, or either of its A001-
    remediation-specific functions (alpha_specific_invalidation_matched /
    alpha_positive_requirement_satisfied) -- the A001 remediation lives
    entirely outside structured_adapter's own module and code path."""
    import comqutor_alpha.structure_engine.structured_output_adapter as soa

    module_source = Path(soa.__file__).read_text(encoding="utf-8")
    assert "alpha_mapper" not in module_source
    assert "alpha_specific_invalidation_matched" not in module_source
    assert "alpha_positive_requirement_satisfied" not in module_source
